"""
AI Factory Pipeline v5.8 — Fastlane Runner (Free Alternative)

FREE ALTERNATIVE to direct App Store Connect API calls.
Fastlane is open-source and handles the entire iOS upload workflow:
  - pilot (TestFlight upload)
  - deliver (App Store submission)
  - match (code signing)
  - gym (building)

Does NOT require a paid service — only an Apple Developer account ($99/year).
This is the best free path for iOS delivery.

Setup:
  gem install fastlane          # one-time
  fastlane init                 # in your project

Env vars used:
  FASTLANE_USER=apple@email.com
  FASTLANE_PASSWORD=apple_password
  FASTLANE_APPLE_APPLICATION_SPECIFIC_PASSWORD=xxxx-xxxx-xxxx-xxxx  (app-specific pwd)
  MATCH_REPOSITORY=git@github.com:org/certs.git  (for code signing)
  MATCH_PASSWORD=cert_repo_password

Spec Authority: v5.6 §4.7.2 (free iOS delivery option)
"""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
from typing import Optional

logger = logging.getLogger("factory.appstore.fastlane_runner")


def _is_configured() -> bool:
    return bool(os.getenv("FASTLANE_USER") and os.getenv("FASTLANE_PASSWORD"))


async def _run_fastlane(action: str, args: list[str], cwd: str = ".") -> dict:
    """Run a fastlane action and return result."""
    cmd = ["fastlane", action] + args
    env = {
        **os.environ,
        "FASTLANE_SKIP_UPDATE_CHECK": "true",
        "FASTLANE_HIDE_CHANGELOG": "true",
    }
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=cwd,
            env=env,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=900)
        output = stdout.decode("utf-8", errors="replace")
        return {
            "exit_code": proc.returncode,
            "output":    output,
        }
    except asyncio.TimeoutError:
        return {"exit_code": 1, "output": "fastlane timed out (15 min)"}
    except FileNotFoundError:
        return {"exit_code": 1, "output": "fastlane not installed. Run: gem install fastlane"}


async def check_installed() -> bool:
    """Return True if fastlane is available on PATH."""
    try:
        result = subprocess.run(
            ["fastlane", "--version"], capture_output=True, timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


async def upload_to_testflight(
    ipa_path: str,
    changelog: str = "New build",
    cwd: str = ".",
) -> dict:
    """Upload an IPA to TestFlight via fastlane pilot."""
    if not _is_configured():
        return {
            "success": False,
            "error": "FASTLANE_USER / FASTLANE_PASSWORD not set",
        }

    result = await _run_fastlane("pilot", [
        "upload",
        f"--ipa={ipa_path}",
        "--skip_waiting_for_build_processing",
        f"--changelog={changelog[:4000]}",
        "--skip_submission",
    ], cwd=cwd)

    success = result["exit_code"] == 0
    return {
        "success":  success,
        "provider": "fastlane_pilot",
        "output":   result["output"][-1000:],
        "error":    "" if success else result["output"][-500:],
    }


async def upload_to_appstore(
    ipa_path: str,
    metadata_path: Optional[str] = None,
    cwd: str = ".",
) -> dict:
    """Upload and submit to App Store via fastlane deliver."""
    if not _is_configured():
        return {"success": False, "error": "FASTLANE_USER / FASTLANE_PASSWORD not set"}

    args = [f"--ipa={ipa_path}", "--force", "--skip_screenshots"]
    if metadata_path:
        args.append(f"--metadata_path={metadata_path}")

    result = await _run_fastlane("deliver", args, cwd=cwd)
    success = result["exit_code"] == 0
    return {
        "success":  success,
        "provider": "fastlane_deliver",
        "output":   result["output"][-1000:],
        "error":    "" if success else result["output"][-500:],
    }
