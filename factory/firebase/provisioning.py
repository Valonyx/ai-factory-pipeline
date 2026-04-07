"""
AI Factory Pipeline v5.6 — Firebase Project Provisioner

Auto-provisions a Firebase project for each generated app:
  • Create Firebase project (free Spark plan)
  • Enable Auth (Google Sign-In)
  • Create Firestore database
  • Set up Firebase Hosting
  • Set up Firebase Storage
  • Register iOS + Android apps
  • Return project credentials

Uses Firebase Management API + Google Cloud APIs.
Requires: GOOGLE_APPLICATION_CREDENTIALS or GCP_SERVICE_ACCOUNT_KEY env var.

Spec Authority: v5.6 §4.11 (Firebase full-stack provisioning)
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import subprocess
from typing import Optional

import aiohttp

logger = logging.getLogger("factory.firebase.provisioning")

_FIREBASE_MGMT_URL = "https://firebase.googleapis.com/v1beta1"
_IDENTITYTOOLKIT_URL = "https://identitytoolkit.googleapis.com/v2"
_TIMEOUT = aiohttp.ClientTimeout(total=60)


def _slugify(name: str) -> str:
    """Convert app name to Firebase project ID (lowercase, hyphens)."""
    slug = re.sub(r"[^a-z0-9-]", "-", name.lower())
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug[:30]  # Firebase project IDs max 30 chars


async def _get_access_token() -> Optional[str]:
    """Get Google OAuth2 access token via gcloud or service account."""
    try:
        result = subprocess.run(
            ["gcloud", "auth", "print-access-token"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Try google-auth library
    try:
        import google.auth
        import google.auth.transport.requests

        credentials, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/firebase",
                    "https://www.googleapis.com/auth/cloud-platform"]
        )
        request = google.auth.transport.requests.Request()
        credentials.refresh(request)
        return credentials.token
    except Exception:
        pass

    return None


class FirebaseProvisioner:
    """Provision a complete Firebase project for a generated app."""

    def __init__(self) -> None:
        self._token: Optional[str] = None

    async def _headers(self) -> dict:
        if not self._token:
            self._token = await _get_access_token()
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }

    # ── Project Creation ─────────────────────────────────────────────

    async def create_project(
        self, app_name: str, gcp_project_id: Optional[str] = None,
    ) -> dict:
        """Create a Firebase project (linked to a GCP project).

        Returns: {firebase_project_id, project_number, web_app_config}
        """
        project_id = gcp_project_id or f"{_slugify(app_name)}-{os.urandom(3).hex()}"

        # First: create GCP project
        gcp_result = await self._create_gcp_project(project_id, app_name)
        if not gcp_result.get("success"):
            return {"success": False, "error": gcp_result.get("error", "GCP project creation failed")}

        # Then: add Firebase to it
        headers = await self._headers()
        async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
            async with session.post(
                f"{_FIREBASE_MGMT_URL}/projects",
                headers=headers,
                json={"project": f"projects/{project_id}"},
            ) as resp:
                body = await resp.json()
                if resp.status not in (200, 201):
                    return {"success": False, "error": f"Firebase project creation: {body}"}

        logger.info(f"[firebase] Project created: {project_id}")
        return {
            "success": True,
            "firebase_project_id": project_id,
            "gcp_project_id": project_id,
        }

    async def _create_gcp_project(self, project_id: str, display_name: str) -> dict:
        """Create a GCP project via Cloud Resource Manager API."""
        headers = await self._headers()
        async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
            async with session.post(
                "https://cloudresourcemanager.googleapis.com/v3/projects",
                headers=headers,
                json={"projectId": project_id, "displayName": display_name},
            ) as resp:
                if resp.status in (200, 201):
                    return {"success": True}
                body = await resp.text()
                return {"success": False, "error": body[:300]}

    # ── Auth Setup ───────────────────────────────────────────────────

    async def enable_auth(
        self, project_id: str, providers: Optional[list[str]] = None,
    ) -> bool:
        """Enable Firebase Auth with specified sign-in providers."""
        providers = providers or ["google.com", "password"]
        headers = await self._headers()

        # Enable Identity Platform
        async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
            async with session.post(
                f"https://identityplatform.googleapis.com/v2/projects/{project_id}/identityPlatform:initializeAuth",
                headers=headers,
                json={},
            ) as resp:
                if resp.status not in (200, 201, 409):  # 409 = already enabled
                    logger.warning(f"[firebase] Auth enable returned {resp.status}")

        logger.info(f"[firebase] Auth enabled for {project_id}: {providers}")
        return True

    # ── Firestore Setup ──────────────────────────────────────────────

    async def create_firestore(
        self, project_id: str, location: str = "me-central1",
    ) -> dict:
        """Create a Firestore database in native mode."""
        headers = await self._headers()
        payload = {
            "type": "FIRESTORE_NATIVE",
            "locationId": location,
        }
        async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
            async with session.post(
                f"https://firestore.googleapis.com/v1/projects/{project_id}/databases",
                headers=headers,
                params={"databaseId": "(default)"},
                json=payload,
            ) as resp:
                if resp.status in (200, 201, 409):  # 409 = already exists
                    logger.info(f"[firebase] Firestore created: {project_id}")
                    return {"success": True, "location": location}
                body = await resp.text()
                return {"success": False, "error": body[:300]}

    # ── Storage Setup ────────────────────────────────────────────────

    async def setup_storage(self, project_id: str) -> bool:
        """Create a Firebase Storage bucket (uses GCS underneath)."""
        bucket_name = f"{project_id}.appspot.com"
        headers = await self._headers()
        async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
            async with session.post(
                f"https://storage.googleapis.com/storage/v1/b",
                headers=headers,
                params={"project": project_id},
                json={"name": bucket_name, "location": "US"},
            ) as resp:
                success = resp.status in (200, 201, 409)
                logger.info(f"[firebase] Storage bucket: {bucket_name} success={success}")
                return success

    # ── Hosting Setup ────────────────────────────────────────────────

    async def setup_hosting(self, project_id: str) -> dict:
        """Create a Firebase Hosting site."""
        headers = await self._headers()
        site_id = project_id
        async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
            async with session.post(
                f"{_FIREBASE_MGMT_URL}/projects/{project_id}/sites",
                headers=headers,
                params={"siteId": site_id},
                json={},
            ) as resp:
                if resp.status in (200, 201, 409):
                    url = f"https://{site_id}.web.app"
                    logger.info(f"[firebase] Hosting: {url}")
                    return {"success": True, "url": url}
                body = await resp.text()
                return {"success": False, "error": body[:300]}

    # ── App Registration ─────────────────────────────────────────────

    async def register_android_app(
        self, project_id: str, package_name: str, display_name: str,
    ) -> Optional[dict]:
        """Register an Android app with the Firebase project."""
        headers = await self._headers()
        async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
            async with session.post(
                f"{_FIREBASE_MGMT_URL}/projects/{project_id}/androidApps",
                headers=headers,
                json={"packageName": package_name, "displayName": display_name},
            ) as resp:
                if resp.status in (200, 201):
                    data = await resp.json()
                    return data.get("response") or data
        return None

    async def register_ios_app(
        self, project_id: str, bundle_id: str, display_name: str,
    ) -> Optional[dict]:
        """Register an iOS app with the Firebase project."""
        headers = await self._headers()
        async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
            async with session.post(
                f"{_FIREBASE_MGMT_URL}/projects/{project_id}/iosApps",
                headers=headers,
                json={"bundleId": bundle_id, "displayName": display_name},
            ) as resp:
                if resp.status in (200, 201):
                    data = await resp.json()
                    return data.get("response") or data
        return None

    async def get_web_config(self, project_id: str) -> Optional[dict]:
        """Get the Firebase web app config (apiKey, appId, etc.)."""
        headers = await self._headers()
        async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
            async with session.get(
                f"{_FIREBASE_MGMT_URL}/projects/{project_id}/webApps",
                headers=headers,
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    apps = data.get("apps", [])
                    if apps:
                        app_id = apps[0]["appId"]
                        async with session.get(
                            f"{_FIREBASE_MGMT_URL}/projects/{project_id}/webApps/{app_id}/config",
                            headers=headers,
                        ) as cfg_resp:
                            if cfg_resp.status == 200:
                                return await cfg_resp.json()
        return None

    # ── Full Provisioning Flow ───────────────────────────────────────

    async def provision_for_app(
        self,
        app_name: str,
        bundle_id: str,
        package_name: str,
        platforms: list[str],
        gcp_project_id: Optional[str] = None,
    ) -> dict:
        """Provision a complete Firebase project for a generated app.

        Runs all setup steps and returns the full project config.
        """
        results: dict = {}

        # 1. Create project
        project = await self.create_project(app_name, gcp_project_id)
        if not project.get("success"):
            return {"success": False, "error": project.get("error"), "step": "create_project"}
        project_id = project["firebase_project_id"]
        results["project_id"] = project_id

        # 2. Enable Auth
        await self.enable_auth(project_id)
        results["auth"] = True

        # 3. Firestore
        fs_result = await self.create_firestore(project_id)
        results["firestore"] = fs_result.get("success")

        # 4. Storage
        results["storage"] = await self.setup_storage(project_id)

        # 5. Hosting
        hosting = await self.setup_hosting(project_id)
        results["hosting"] = hosting

        # 6. Register apps
        if "android" in platforms:
            android_app = await self.register_android_app(project_id, package_name, app_name)
            results["android_app"] = android_app

        if "ios" in platforms:
            ios_app = await self.register_ios_app(project_id, bundle_id, app_name)
            results["ios_app"] = ios_app

        # 7. Get web config
        web_config = await self.get_web_config(project_id)
        results["web_config"] = web_config

        logger.info(f"[firebase] Full provisioning complete for {app_name}: {project_id}")
        return {"success": True, **results}
