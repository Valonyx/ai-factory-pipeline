"""
AI Factory Pipeline v5.8 — Build Provider Chain

Provider priority for Mac-required builds (iOS, FlutterFlow, Unity):

  1. MacinCloud       — paid (~$1/hr), best quality, real Mac hardware
  2. GitHub Actions   — free 2,000 min/month macOS runners (public repo)
                        or self-hosted Mac runner — BEST FREE OPTION
  3. Codemagic        — free 500 min/month, Apple Silicon M2 runners

For non-Mac builds (Android, Python, React Native Android):
  - GitHub Actions ubuntu-latest (always free)

Switch behaviour:
  • If MacinCloud key is absent/fails → auto-fall to GitHub Actions
  • If GA free minutes exhausted → auto-fall to Codemagic
  • Provider failure is tracked per session and logged; fallback is silent

Paid-to-free flexibility:
  Set BUILD_MAC_PROVIDER=macincloud|github_actions|codemagic in .env
  to force a specific provider, or leave blank for auto-cascade.

Spec Authority: v5.6 §2.4.1, §4.5
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

import aiohttp

if TYPE_CHECKING:
    from factory.core.state import PipelineState

logger = logging.getLogger("factory.infra.build_chain")

# ═══════════════════════════════════════════════════════════════════
# Build Result
# ═══════════════════════════════════════════════════════════════════

@dataclass
class BuildResult:
    success: bool
    provider: str
    run_id: Optional[str] = None          # GitHub Actions run ID or Codemagic build ID
    artifacts: dict = field(default_factory=dict)
    artifacts_url: Optional[str] = None   # URL to download artifacts
    log_url: Optional[str] = None         # Link to build log
    duration_seconds: float = 0.0
    error: str = ""


# ═══════════════════════════════════════════════════════════════════
# Provider: GitHub Actions (free tier)
# ═══════════════════════════════════════════════════════════════════

_GA_TIMEOUT = aiohttp.ClientTimeout(total=20)
_WORKFLOW_MAP = {
    "react_native": "react-native-build.yml",
    "swift":        "swift-build.yml",
    "kotlin":       "kotlin-build.yml",
    "flutterflow":  "flutter-build.yml",
    "unity":        "flutter-build.yml",   # fallback — Unity CLI used in flutter workflow
    "python_backend": "python-backend.yml",
}


async def dispatch_github_actions(
    stack: str,
    platforms: list[str],
    version: str,
    project_id: str,
    state: "PipelineState",
) -> BuildResult:
    """Trigger a GitHub Actions workflow and poll until completion.

    Uses GITHUB_TOKEN + repo info from .env.
    Free tier: 2,000 macOS minutes/month (public repos).
    """
    token  = os.getenv("GITHUB_TOKEN", "")
    owner  = os.getenv("GITHUB_REPO_OWNER", "")
    repo   = os.getenv("GITHUB_REPO_NAME", "")

    if not all([token, owner, repo]):
        raise ValueError("GITHUB_TOKEN / GITHUB_REPO_OWNER / GITHUB_REPO_NAME not set")

    workflow_file = _WORKFLOW_MAP.get(stack)
    if not workflow_file:
        raise ValueError(f"No GitHub Actions workflow for stack: {stack}")

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    # 1. Dispatch the workflow
    dispatch_url = (
        f"https://api.github.com/repos/{owner}/{repo}"
        f"/actions/workflows/{workflow_file}/dispatches"
    )
    payload = {
        "ref": "main",
        "inputs": {
            "platforms": ",".join(platforms),
            "version":   version,
            "project_id": project_id,
        },
    }

    start = time.time()
    async with aiohttp.ClientSession(timeout=_GA_TIMEOUT) as session:
        async with session.post(dispatch_url, headers=headers, json=payload) as resp:
            if resp.status not in (204, 200):
                body = await resp.text()
                raise RuntimeError(f"GitHub Actions dispatch failed {resp.status}: {body[:300]}")

    logger.info(f"[build-chain] GitHub Actions dispatched: {workflow_file} for {stack}")

    # 2. Find the run that was just created (wait up to 30s for it to appear)
    run_id = await _find_latest_run(owner, repo, workflow_file, headers, timeout=30)
    if not run_id:
        raise RuntimeError("Could not find GitHub Actions run after dispatch")

    logger.info(f"[build-chain] GitHub Actions run_id={run_id}")

    # 3. Poll until completion
    run_url   = f"https://api.github.com/repos/{owner}/{repo}/actions/runs/{run_id}"
    poll_url  = f"https://api.github.com/repos/{owner}/{repo}/actions/runs/{run_id}"
    html_url  = f"https://github.com/{owner}/{repo}/actions/runs/{run_id}"

    status = "queued"
    conclusion = None
    async with aiohttp.ClientSession(timeout=_GA_TIMEOUT) as session:
        for _ in range(180):   # max ~90 min (30s intervals)
            await asyncio.sleep(30)
            async with session.get(poll_url, headers=headers) as resp:
                if resp.status != 200:
                    continue
                data = await resp.json()
                status     = data.get("status", "")
                conclusion = data.get("conclusion")
                logger.debug(f"[build-chain] GA run {run_id}: status={status}")
                if status == "completed":
                    break

    duration = time.time() - start
    success  = conclusion == "success"

    # 4. Get artifact URLs
    artifacts_url = await _get_artifacts_url(owner, repo, run_id, headers)

    return BuildResult(
        success=success,
        provider="github_actions",
        run_id=str(run_id),
        artifacts_url=artifacts_url,
        log_url=html_url,
        duration_seconds=duration,
        error="" if success else f"Conclusion: {conclusion}",
    )


async def _find_latest_run(
    owner: str, repo: str, workflow_file: str,
    headers: dict, timeout: int = 30,
) -> Optional[int]:
    """Poll /actions/runs until the most recent run for this workflow appears."""
    url = (
        f"https://api.github.com/repos/{owner}/{repo}/actions/workflows"
        f"/{workflow_file}/runs?per_page=5"
    )
    deadline = time.time() + timeout
    async with aiohttp.ClientSession(timeout=_GA_TIMEOUT) as session:
        while time.time() < deadline:
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    runs = data.get("workflow_runs", [])
                    if runs:
                        return runs[0]["id"]
            await asyncio.sleep(5)
    return None


async def _get_artifacts_url(
    owner: str, repo: str, run_id: int, headers: dict,
) -> Optional[str]:
    """Return the artifacts list URL for a completed run."""
    url = f"https://api.github.com/repos/{owner}/{repo}/actions/runs/{run_id}/artifacts"
    try:
        async with aiohttp.ClientSession(timeout=_GA_TIMEOUT) as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    arts = data.get("artifacts", [])
                    if arts:
                        return arts[0].get("archive_download_url")
    except Exception:
        pass
    return None


# ═══════════════════════════════════════════════════════════════════
# Provider: Codemagic (free 500 min/month)
# ═══════════════════════════════════════════════════════════════════

async def dispatch_codemagic(
    stack: str,
    platforms: list[str],
    version: str,
    project_id: str,
) -> BuildResult:
    """Trigger a Codemagic build via REST API.

    Free tier: 500 build minutes/month on Apple Silicon M2.
    Requires: CODEMAGIC_API_TOKEN + CODEMAGIC_APP_ID in .env
    """
    token  = os.getenv("CODEMAGIC_API_TOKEN", "")
    app_id = os.getenv("CODEMAGIC_APP_ID", "")

    if not token or not app_id:
        raise ValueError("CODEMAGIC_API_TOKEN / CODEMAGIC_APP_ID not configured")

    headers = {
        "x-auth-token": token,
        "Content-Type": "application/json",
    }
    payload = {
        "appId":       app_id,
        "workflowId":  f"{stack}-workflow",
        "branch":      "main",
        "environment": {
            "variables": {
                "BUILD_PLATFORMS": ",".join(platforms),
                "APP_VERSION":     version,
                "PROJECT_ID":      project_id,
            }
        },
    }

    start = time.time()
    async with aiohttp.ClientSession(timeout=_GA_TIMEOUT) as session:
        async with session.post(
            "https://api.codemagic.io/builds",
            headers=headers, json=payload,
        ) as resp:
            if resp.status not in (200, 201):
                body = await resp.text()
                raise RuntimeError(f"Codemagic dispatch failed {resp.status}: {body[:200]}")
            data = await resp.json()
            build_id = data.get("buildId") or data.get("id")

    logger.info(f"[build-chain] Codemagic build_id={build_id}")

    # Poll
    poll_url = f"https://api.codemagic.io/builds/{build_id}"
    status = "running"
    async with aiohttp.ClientSession(timeout=_GA_TIMEOUT) as session:
        for _ in range(120):
            await asyncio.sleep(30)
            async with session.get(poll_url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    status = data.get("build", {}).get("status", "running")
                    if status in ("finished", "failed", "canceled"):
                        break

    success = status == "finished"
    duration = time.time() - start
    log_url = f"https://codemagic.io/builds/{build_id}"

    return BuildResult(
        success=success,
        provider="codemagic",
        run_id=str(build_id),
        log_url=log_url,
        duration_seconds=duration,
        error="" if success else f"Codemagic status: {status}",
    )


# ═══════════════════════════════════════════════════════════════════
# Build Chain — auto-cascade across providers
# ═══════════════════════════════════════════════════════════════════

async def build_with_chain(
    stack: str,
    platforms: list[str],
    version: str,
    project_id: str,
    state: "PipelineState",
    requires_mac: bool = False,
) -> BuildResult:
    """Run a build through the provider chain, cascading on failure.

    Priority (env-overridable via BUILD_MAC_PROVIDER):
      1. MacinCloud  (paid, best quality)
      2. GitHub Actions  (free 2K min/month macOS)
      3. Codemagic   (free 500 min/month)

    Non-Mac stacks always use GitHub Actions (free ubuntu-latest).
    """
    forced = os.getenv("BUILD_MAC_PROVIDER", "").lower()

    # Non-Mac stacks: always GitHub Actions (unlimited free linux runners)
    if not requires_mac:
        logger.info(f"[build-chain] Non-Mac build → GitHub Actions (free)")
        return await dispatch_github_actions(stack, platforms, version, project_id, state)

    # Mac-required: cascade
    providers_to_try: list[str]
    if forced:
        providers_to_try = [forced]
    else:
        has_macincloud   = bool(os.getenv("MACINCLOUD_API_KEY"))
        has_codemagic    = bool(os.getenv("CODEMAGIC_API_TOKEN") and os.getenv("CODEMAGIC_APP_ID"))
        has_github_token = bool(os.getenv("GITHUB_TOKEN"))

        providers_to_try = []
        if has_macincloud:
            providers_to_try.append("macincloud")
        if has_github_token:
            providers_to_try.append("github_actions")
        if has_codemagic:
            providers_to_try.append("codemagic")

        if not providers_to_try:
            # No Mac build provider configured — use GitHub Actions even if no token
            # (will fail with clear error message)
            providers_to_try = ["github_actions"]

    last_error = ""
    for provider in providers_to_try:
        try:
            logger.info(f"[build-chain] Trying Mac build provider: {provider}")
            if provider == "macincloud":
                from factory.infra.macincloud_client import MacinCloudClient
                client = MacinCloudClient()
                return await client.run_build(stack, platforms, version, project_id, state)
            elif provider == "github_actions":
                return await dispatch_github_actions(stack, platforms, version, project_id, state)
            elif provider == "codemagic":
                return await dispatch_codemagic(stack, platforms, version, project_id)
        except Exception as e:
            last_error = str(e)
            logger.warning(f"[build-chain] {provider} failed: {e} — trying next")
            continue

    return BuildResult(
        success=False,
        provider="none",
        error=f"All build providers exhausted. Last error: {last_error}",
    )
