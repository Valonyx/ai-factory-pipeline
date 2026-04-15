"""
AI Factory Pipeline v5.8 — Firebase App Distribution (Free Alternative)

ALWAYS FREE — Firebase App Distribution distributes pre-release builds
to testers without going through the App Store or Google Play.

This is the primary FREE alternative when:
  • No Apple Developer account ($99/year) → use Firebase for iOS distribution
  • No Google Play Developer account ($25) → use Firebase for Android distribution
  • Need instant delivery without store review delays

Limits: None for basic use. Requires Firebase project (free).

Setup:
  1. Create Firebase project (free) at console.firebase.google.com
  2. Enable App Distribution
  3. Install Firebase CLI: npm install -g firebase-tools
  4. Set FIREBASE_TOKEN or use service account

Env vars:
  FIREBASE_APP_ID_IOS      — Firebase iOS app ID (1:xxx:ios:xxx)
  FIREBASE_APP_ID_ANDROID  — Firebase Android app ID (1:xxx:android:xxx)
  FIREBASE_TOKEN           — firebase-tools auth token
  FIREBASE_TESTER_GROUPS   — Comma-separated tester group names

Spec Authority: v5.8 §4.7 (free distribution fallback)
"""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
from typing import Optional

logger = logging.getLogger("factory.delivery.firebase_distribution")


def _is_configured(platform: str) -> bool:
    key = f"FIREBASE_APP_ID_{platform.upper()}"
    return bool(os.getenv(key) and (os.getenv("FIREBASE_TOKEN") or os.getenv("GOOGLE_APPLICATION_CREDENTIALS")))


async def _run_firebase_cli(args: list[str]) -> dict:
    """Run Firebase CLI command."""
    env = {**os.environ}
    if os.getenv("FIREBASE_TOKEN"):
        env["FIREBASE_TOKEN"] = os.getenv("FIREBASE_TOKEN", "")

    cmd = ["firebase"] + args + ["--non-interactive"]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env=env,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=300)
        output = stdout.decode("utf-8", errors="replace")
        return {"exit_code": proc.returncode, "output": output}
    except asyncio.TimeoutError:
        return {"exit_code": 1, "output": "Firebase CLI timed out (5 min)"}
    except FileNotFoundError:
        return {
            "exit_code": 1,
            "output": (
                "Firebase CLI not found. "
                "Install: npm install -g firebase-tools"
            ),
        }


async def distribute_android(
    apk_or_aab_path: str,
    release_notes: str = "New release",
    tester_groups: Optional[str] = None,
) -> dict:
    """Distribute Android APK/AAB via Firebase App Distribution.

    Returns dict with success, download_url (if available), error.
    """
    app_id = os.getenv("FIREBASE_APP_ID_ANDROID", "")
    if not app_id:
        return {"success": False, "error": "FIREBASE_APP_ID_ANDROID not set"}

    groups = tester_groups or os.getenv("FIREBASE_TESTER_GROUPS", "")

    args = [
        "appdistribution:distribute",
        apk_or_aab_path,
        "--app", app_id,
        "--release-notes", release_notes[:500],
    ]
    if groups:
        args += ["--groups", groups]

    result = await _run_firebase_cli(args)
    success = result["exit_code"] == 0

    download_url = None
    for line in result["output"].split("\n"):
        if "https://" in line and "firebase" in line.lower():
            download_url = line.strip()
            break

    return {
        "success":      success,
        "provider":     "firebase_distribution",
        "platform":     "android",
        "app_id":       app_id,
        "download_url": download_url,
        "output":       result["output"][-800:],
        "error":        "" if success else result["output"][-400:],
    }


async def distribute_ios(
    ipa_path: str,
    release_notes: str = "New release",
    tester_groups: Optional[str] = None,
) -> dict:
    """Distribute iOS IPA via Firebase App Distribution.

    Note: This distributes via Firebase, NOT the App Store.
    Testers install via the Firebase App Distribution iOS app.
    """
    app_id = os.getenv("FIREBASE_APP_ID_IOS", "")
    if not app_id:
        return {"success": False, "error": "FIREBASE_APP_ID_IOS not set"}

    groups = tester_groups or os.getenv("FIREBASE_TESTER_GROUPS", "")

    args = [
        "appdistribution:distribute",
        ipa_path,
        "--app", app_id,
        "--release-notes", release_notes[:500],
    ]
    if groups:
        args += ["--groups", groups]

    result = await _run_firebase_cli(args)
    success = result["exit_code"] == 0

    download_url = None
    for line in result["output"].split("\n"):
        if "https://" in line and ("firebase" in line.lower() or "appdistribution" in line.lower()):
            download_url = line.strip()
            break

    return {
        "success":      success,
        "provider":     "firebase_distribution",
        "platform":     "ios",
        "app_id":       app_id,
        "download_url": download_url,
        "output":       result["output"][-800:],
        "error":        "" if success else result["output"][-400:],
    }


async def check_installed() -> bool:
    """Check if Firebase CLI is available."""
    try:
        result = subprocess.run(
            ["firebase", "--version"], capture_output=True, timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
