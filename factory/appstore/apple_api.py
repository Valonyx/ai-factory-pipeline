"""
AI Factory Pipeline v5.8 — Apple App Store Connect API Client

PAID OPTION: Requires Apple Developer Account ($99/year).
Free alternatives handled by ios_delivery_chain.py.

Uses App Store Connect API (JWT-based, no UI login needed).
ADR-016: API-first approach.

Required env vars:
  APP_STORE_API_KEY_ID    — Key ID from App Store Connect → Keys
  APP_STORE_ISSUER_ID     — Issuer ID from App Store Connect → Keys
  APP_STORE_PRIVATE_KEY   — P8 private key content (or path in APP_STORE_KEY_PATH)
  APP_STORE_KEY_PATH      — Path to .p8 key file (alternative to above)

Spec Authority: v5.8 §4.7.2, §4.7.4 (FIX-21)
"""

from __future__ import annotations

import logging
import os
import time
from typing import Optional

import aiohttp

logger = logging.getLogger("factory.appstore.apple_api")

_BASE_URL = "https://api.appstoreconnect.apple.com/v1"
_TIMEOUT = aiohttp.ClientTimeout(total=30)


def _is_configured() -> bool:
    return bool(
        os.getenv("APP_STORE_API_KEY_ID")
        and os.getenv("APP_STORE_ISSUER_ID")
        and (os.getenv("APP_STORE_PRIVATE_KEY") or os.getenv("APP_STORE_KEY_PATH"))
    )


def _generate_jwt() -> str:
    """Generate a signed JWT for App Store Connect API."""
    try:
        import jwt
    except ImportError:
        raise RuntimeError("PyJWT not installed: pip install PyJWT")

    key_id    = os.getenv("APP_STORE_API_KEY_ID", "")
    issuer_id = os.getenv("APP_STORE_ISSUER_ID", "")
    private_key_content = os.getenv("APP_STORE_PRIVATE_KEY", "")

    if not private_key_content:
        key_path = os.getenv("APP_STORE_KEY_PATH", "")
        if key_path and os.path.exists(key_path):
            with open(key_path) as f:
                private_key_content = f.read()

    if not private_key_content:
        raise ValueError("APP_STORE_PRIVATE_KEY or APP_STORE_KEY_PATH not configured")

    now = int(time.time())
    payload = {
        "iss": issuer_id,
        "iat": now,
        "exp": now + 1200,    # 20 min — max allowed
        "aud": "appstoreconnect-v1",
    }
    return jwt.encode(payload, private_key_content, algorithm="ES256",
                      headers={"kid": key_id})


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {_generate_jwt()}",
        "Content-Type": "application/json",
    }


class AppleAPIClient:
    """App Store Connect API client (JWT auth, no portal login)."""

    async def check_auth(self) -> bool:
        """Verify credentials by listing apps."""
        if not _is_configured():
            return False
        try:
            async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
                async with session.get(f"{_BASE_URL}/apps", headers=_headers()) as resp:
                    return resp.status == 200
        except Exception:
            return False

    async def get_or_create_app(
        self, bundle_id: str, app_name: str, primary_locale: str = "en-US",
    ) -> Optional[dict]:
        """Look up or create an app by bundle ID."""
        # Search existing apps
        async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
            async with session.get(
                f"{_BASE_URL}/apps",
                headers=_headers(),
                params={"filter[bundleId]": bundle_id},
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    apps = data.get("data", [])
                    if apps:
                        return apps[0]

            # Create new app
            payload = {
                "data": {
                    "type": "apps",
                    "attributes": {
                        "bundleId": bundle_id,
                        "name": app_name,
                        "primaryLocale": primary_locale,
                        "sku": bundle_id.replace(".", "-"),
                    },
                }
            }
            async with session.post(f"{_BASE_URL}/apps", headers=_headers(), json=payload) as resp:
                if resp.status in (200, 201):
                    data = await resp.json()
                    return data.get("data")
                body = await resp.text()
                logger.error(f"[apple-api] create app failed {resp.status}: {body[:300]}")
                return None

    async def get_build_status(self, build_id: str) -> Optional[dict]:
        """Get the processing status of an uploaded build."""
        async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
            async with session.get(
                f"{_BASE_URL}/builds/{build_id}", headers=_headers(),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("data", {}).get("attributes", {})
        return None

    async def submit_for_testflight(self, build_id: str) -> bool:
        """Add a build to TestFlight for beta testing."""
        payload = {
            "data": {
                "type": "betaAppReviewSubmissions",
                "relationships": {
                    "build": {"data": {"type": "builds", "id": build_id}}
                },
            }
        }
        async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
            async with session.post(
                f"{_BASE_URL}/betaAppReviewSubmissions",
                headers=_headers(), json=payload,
            ) as resp:
                return resp.status in (200, 201)

    async def submit_for_review(self, version_id: str) -> bool:
        """Submit an app version for App Store review."""
        payload = {
            "data": {
                "type": "appStoreVersionSubmissions",
                "relationships": {
                    "appStoreVersion": {
                        "data": {"type": "appStoreVersions", "id": version_id}
                    }
                },
            }
        }
        async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
            async with session.post(
                f"{_BASE_URL}/appStoreVersionSubmissions",
                headers=_headers(), json=payload,
            ) as resp:
                return resp.status in (200, 201)
