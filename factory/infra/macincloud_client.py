"""
AI Factory Pipeline v5.6 — MacinCloud Client

SSH-based Mac VM management for iOS/GUI builds that require real macOS.

This is the PAID provider in the Mac build chain. If MACINCLOUD_API_KEY
is not set, the build_chain.py falls back to GitHub Actions macOS runners
(free) or Codemagic (free 500 min/month).

Features:
  • SSH session management via asyncssh
  • 30-second heartbeat (keep-alive)
  • Idle kill switch — disconnects after MACINCLOUD_IDLE_MINUTES (default 30)
  • Cost estimation: $1/hr per session

Setup:
  MACINCLOUD_API_KEY=your_key
  MACINCLOUD_HOST=your-host.macincloud.com
  MACINCLOUD_PORT=22
  MACINCLOUD_USER=your_username
  MACINCLOUD_PASSWORD=your_password
  MACINCLOUD_IDLE_MINUTES=30

Spec Authority: v5.6 §2.4.1 (MacinCloud integration)
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from factory.core.state import PipelineState
    from factory.infra.build_chain import BuildResult

logger = logging.getLogger("factory.infra.macincloud_client")

_HEARTBEAT_INTERVAL = 30          # seconds
_DEFAULT_IDLE_MINUTES = 30        # kill switch
_HOURLY_COST_USD = 1.0            # approximate


class MacinCloudClient:
    """SSH client for MacinCloud Mac VM sessions.

    Usage:
        client = MacinCloudClient()
        result = await client.run_build(stack, platforms, version, project_id, state)
    """

    def __init__(self) -> None:
        self.host     = os.getenv("MACINCLOUD_HOST", "")
        self.port     = int(os.getenv("MACINCLOUD_PORT", "22"))
        self.user     = os.getenv("MACINCLOUD_USER", "")
        self.password = os.getenv("MACINCLOUD_PASSWORD", "")
        self.api_key  = os.getenv("MACINCLOUD_API_KEY", "")
        self.idle_min = int(os.getenv("MACINCLOUD_IDLE_MINUTES", str(_DEFAULT_IDLE_MINUTES)))
        self._conn    = None
        self._session_start: Optional[float] = None
        self._last_activity: Optional[float] = None
        self._heartbeat_task: Optional[asyncio.Task] = None

    # ── Connection ──────────────────────────────────────────────────

    async def connect(self) -> bool:
        """Open SSH connection to MacinCloud VM."""
        if not self.host or not self.user:
            raise ValueError(
                "MACINCLOUD_HOST / MACINCLOUD_USER not configured. "
                "Set them in .env or use GitHub Actions (free) instead."
            )
        try:
            import asyncssh
            self._conn = await asyncssh.connect(
                self.host,
                port=self.port,
                username=self.user,
                password=self.password,
                known_hosts=None,  # accept any host key (dev mode)
            )
            self._session_start = time.time()
            self._last_activity = time.time()
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
            logger.info(f"[macincloud] Connected to {self.host}:{self.port}")
            return True
        except ImportError:
            raise RuntimeError(
                "asyncssh not installed. Run: pip install asyncssh"
            )
        except Exception as e:
            raise RuntimeError(f"MacinCloud SSH connection failed: {e}")

    async def disconnect(self) -> None:
        """Close SSH connection."""
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
        if self._conn:
            self._conn.close()
            self._conn = None
        if self._session_start:
            elapsed_h = (time.time() - self._session_start) / 3600
            cost = elapsed_h * _HOURLY_COST_USD
            logger.info(
                f"[macincloud] Disconnected. Session: {elapsed_h:.2f}h "
                f"≈ ${cost:.2f}"
            )

    async def execute(self, command: str, timeout: int = 600) -> dict:
        """Run a command on the Mac VM."""
        if not self._conn:
            raise RuntimeError("Not connected. Call connect() first.")

        self._last_activity = time.time()
        try:
            result = await asyncio.wait_for(
                self._conn.run(command, check=False),
                timeout=timeout,
            )
            return {
                "stdout":    result.stdout or "",
                "stderr":    result.stderr or "",
                "exit_code": result.exit_status or 0,
            }
        except asyncio.TimeoutError:
            return {"stdout": "", "stderr": f"Command timed out ({timeout}s)", "exit_code": 1}
        except Exception as e:
            return {"stdout": "", "stderr": str(e), "exit_code": 1}

    # ── Heartbeat / Kill Switch ──────────────────────────────────────

    async def _heartbeat_loop(self) -> None:
        """Send keep-alive every 30s. Disconnect after idle limit."""
        while self._conn:
            await asyncio.sleep(_HEARTBEAT_INTERVAL)
            try:
                if self._conn:
                    await self._conn.run("echo heartbeat", check=False)
            except Exception:
                pass

            if self._last_activity:
                idle_seconds = time.time() - self._last_activity
                if idle_seconds > self.idle_min * 60:
                    logger.warning(
                        f"[macincloud] Idle kill switch: {idle_seconds/60:.1f} min idle → disconnecting"
                    )
                    await self.disconnect()
                    break

    def get_estimated_cost(self) -> float:
        """Return estimated cost for this session so far (USD)."""
        if not self._session_start:
            return 0.0
        elapsed_h = (time.time() - self._session_start) / 3600
        return elapsed_h * _HOURLY_COST_USD

    # ── Build Entry Point ────────────────────────────────────────────

    async def run_build(
        self,
        stack: str,
        platforms: list[str],
        version: str,
        project_id: str,
        state: "PipelineState",
    ) -> "BuildResult":
        """Run a full build on MacinCloud. Disconnects when done."""
        from factory.infra.build_chain import BuildResult

        start = time.time()
        try:
            await self.connect()
            commands = _build_commands_for_stack(stack, platforms, version)
            errors: list[str] = []
            artifacts: dict = {}

            for name, cmd in commands:
                logger.info(f"[macincloud] {name}: {cmd[:80]}")
                result = await self.execute(cmd, timeout=1200)
                if result["exit_code"] != 0:
                    errors.append(f"{name}: {result['stderr'][:300]}")
                else:
                    artifacts[name] = {"status": "success"}

            success = len(errors) == 0
            duration = time.time() - start
            cost = self.get_estimated_cost()

            # Update project cost tracking
            state.project_metadata["macincloud_cost_usd"] = (
                state.project_metadata.get("macincloud_cost_usd", 0.0) + cost
            )

            return BuildResult(
                success=success,
                provider="macincloud",
                artifacts=artifacts,
                duration_seconds=duration,
                error="; ".join(errors),
            )
        except Exception as e:
            return BuildResult(
                success=False,
                provider="macincloud",
                error=str(e),
                duration_seconds=time.time() - start,
            )
        finally:
            await self.disconnect()


# ── Build Command Templates ──────────────────────────────────────────

def _build_commands_for_stack(
    stack: str, platforms: list[str], version: str,
) -> list[tuple[str, str]]:
    """Return ordered (name, command) pairs for a Mac build."""
    commands: list[tuple[str, str]] = []

    if stack == "swift":
        commands += [
            ("resolve_packages", "swift package resolve || pod install"),
            ("archive", (
                "xcodebuild archive -scheme App "
                f"-destination 'generic/platform=iOS' "
                f"-archivePath ~/build/App.xcarchive"
            )),
            ("export", (
                "xcodebuild -exportArchive "
                "-archivePath ~/build/App.xcarchive "
                "-exportOptionsPlist ExportOptions.plist "
                "-exportPath ~/build/export"
            )),
        ]
    elif stack in ("flutterflow", "flutter"):
        if "android" in platforms:
            commands.append(("flutter_android", "flutter build appbundle --release"))
        if "ios" in platforms:
            commands += [
                ("flutter_ios", "flutter build ios --release --no-codesign"),
                ("create_ipa", (
                    "cd build/ios/iphoneos && mkdir Payload && "
                    "cp -r Runner.app Payload/ && zip -r App.ipa Payload/"
                )),
            ]
    elif stack == "unity":
        commands += [
            ("unity_android", (
                f"/Applications/Unity/Unity.app/Contents/MacOS/Unity "
                f"-quit -batchmode -buildTarget Android "
                f"-buildOutput ~/build/app.apk -executeMethod Builder.BuildAndroid"
            )),
            ("unity_ios", (
                f"/Applications/Unity/Unity.app/Contents/MacOS/Unity "
                f"-quit -batchmode -buildTarget iOS "
                f"-buildOutput ~/build/ios -executeMethod Builder.BuildIOS"
            )),
        ]

    return commands
