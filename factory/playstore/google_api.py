"""
AI Factory Pipeline v5.8 — Google Play Developer API Client

PAID OPTION: Requires Google Play Developer Account ($25 one-time fee).
Free alternatives handled by android_delivery_chain.py.

Uses Google Play Android Developer API (service account OAuth2).
No portal UI login required (ADR-016: API-first approach).

Required env vars:
  GOOGLE_PLAY_SERVICE_ACCOUNT_JSON — JSON content of service account key
  or
  GOOGLE_PLAY_SERVICE_ACCOUNT_PATH — Path to service account JSON file
  GOOGLE_PLAY_PACKAGE_NAME         — com.example.app (default, can be overridden per-call)

Setup:
  1. Google Play Console → Setup → API access
  2. Link to Google Cloud project
  3. Create service account with "Release manager" role
  4. Download JSON key → set GOOGLE_PLAY_SERVICE_ACCOUNT_JSON

Spec Authority: v5.6 §4.7.1
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger("factory.playstore.google_api")


def _is_configured() -> bool:
    return bool(
        os.getenv("GOOGLE_PLAY_SERVICE_ACCOUNT_JSON")
        or os.getenv("GOOGLE_PLAY_SERVICE_ACCOUNT_PATH")
    )


def _get_service_account_json() -> Optional[dict]:
    raw = os.getenv("GOOGLE_PLAY_SERVICE_ACCOUNT_JSON", "")
    if raw:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass

    path = os.getenv("GOOGLE_PLAY_SERVICE_ACCOUNT_PATH", "")
    if path and Path(path).exists():
        with open(path) as f:
            return json.load(f)

    return None


class GooglePlayAPIClient:
    """Google Play Developer API client using google-api-python-client."""

    def __init__(self, package_name: Optional[str] = None) -> None:
        self.package_name = package_name or os.getenv("GOOGLE_PLAY_PACKAGE_NAME", "")
        self._service = None

    def _build_service(self):
        """Build the googleapiclient service object."""
        if self._service:
            return self._service

        try:
            from googleapiclient.discovery import build
            from google.oauth2.service_account import Credentials
        except ImportError:
            raise RuntimeError(
                "google-api-python-client not installed. "
                "Run: pip install google-api-python-client google-auth"
            )

        sa_info = _get_service_account_json()
        if not sa_info:
            raise ValueError(
                "GOOGLE_PLAY_SERVICE_ACCOUNT_JSON or GOOGLE_PLAY_SERVICE_ACCOUNT_PATH not set"
            )

        creds = Credentials.from_service_account_info(
            sa_info,
            scopes=["https://www.googleapis.com/auth/androidpublisher"],
        )
        self._service = build("androidpublisher", "v3", credentials=creds)
        return self._service

    async def upload_aab(
        self,
        aab_path: str,
        package_name: Optional[str] = None,
        track: str = "internal",
    ) -> dict:
        """Upload an AAB to the Play Store internal track.

        Returns dict with success, version_code, track.
        """
        import asyncio
        pkg = package_name or self.package_name
        if not pkg:
            return {"success": False, "error": "package_name not set"}

        def _upload_sync() -> dict:
            try:
                service = self._build_service()
                edits = service.edits()

                # Open edit session
                edit = edits.insert(packageName=pkg, body={}).execute()
                edit_id = edit["id"]

                # Upload AAB
                from googleapiclient.http import MediaFileUpload
                media = MediaFileUpload(
                    aab_path,
                    mimetype="application/octet-stream",
                    resumable=True,
                )
                bundle = edits.bundles().upload(
                    packageName=pkg,
                    editId=edit_id,
                    media_body=media,
                ).execute()

                version_code = bundle["versionCode"]

                # Assign to track
                track_body = {
                    "track": track,
                    "releases": [{
                        "versionCodes": [version_code],
                        "status": "completed",
                    }],
                }
                edits.tracks().update(
                    packageName=pkg,
                    editId=edit_id,
                    track=track,
                    body=track_body,
                ).execute()

                # Commit edit
                edits.commit(packageName=pkg, editId=edit_id).execute()

                return {
                    "success":      True,
                    "version_code": version_code,
                    "track":        track,
                    "package":      pkg,
                }
            except Exception as e:
                return {"success": False, "error": str(e)[:500]}

        return await asyncio.get_event_loop().run_in_executor(None, _upload_sync)

    async def upload_apk(
        self,
        apk_path: str,
        package_name: Optional[str] = None,
        track: str = "internal",
    ) -> dict:
        """Upload an APK (legacy, prefer AAB)."""
        import asyncio
        pkg = package_name or self.package_name

        def _upload_sync() -> dict:
            try:
                service = self._build_service()
                edits = service.edits()
                edit = edits.insert(packageName=pkg, body={}).execute()
                edit_id = edit["id"]

                from googleapiclient.http import MediaFileUpload
                media = MediaFileUpload(apk_path, mimetype="application/vnd.android.package-archive")
                apk = edits.apks().upload(
                    packageName=pkg, editId=edit_id, media_body=media,
                ).execute()
                version_code = apk["versionCode"]

                edits.tracks().update(
                    packageName=pkg, editId=edit_id, track=track,
                    body={"track": track, "releases": [{"versionCodes": [version_code], "status": "completed"}]},
                ).execute()
                edits.commit(packageName=pkg, editId=edit_id).execute()

                return {"success": True, "version_code": version_code, "track": track}
            except Exception as e:
                return {"success": False, "error": str(e)[:500]}

        return await asyncio.get_event_loop().run_in_executor(None, _upload_sync)

    async def get_track_info(
        self, track: str = "internal", package_name: Optional[str] = None,
    ) -> Optional[dict]:
        """Get info about a release track."""
        import asyncio
        pkg = package_name or self.package_name

        def _get() -> Optional[dict]:
            try:
                service = self._build_service()
                edits = service.edits()
                edit = edits.insert(packageName=pkg, body={}).execute()
                result = edits.tracks().get(
                    packageName=pkg, editId=edit["id"], track=track,
                ).execute()
                edits.delete(packageName=pkg, editId=edit["id"]).execute()
                return result
            except Exception:
                return None

        return await asyncio.get_event_loop().run_in_executor(None, _get)
