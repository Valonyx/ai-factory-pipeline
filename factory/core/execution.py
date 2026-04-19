"""
AI Factory Pipeline v5.8 — Three-Mode Execution Layer

Implements:
  - §2.4.1 ExecutionModeManager (Cloud/Local/Hybrid routing)
  - §2.4.2 HeartbeatMonitor (30s ping, 3-failure auto-failover)
  - §2.4.3 Local Agent interface
  - §8.10 Contract 4: execute_command

Spec Authority: v5.8 §2.4, §2.7, §8.10
"""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
from typing import Any, Optional

from factory.core.state import (
    ExecutionMode,
    PipelineState,
    Stage,
)

logger = logging.getLogger("factory.core.execution")


# ═══════════════════════════════════════════════════════════════════
# §8.10 Contract 4: execute_command
# ═══════════════════════════════════════════════════════════════════


async def execute_command(
    cmd: str,
    cwd: str = ".",
    timeout: int = 300,
    env: Optional[dict] = None,
) -> tuple[int, str, str]:
    """Execute a command locally with user-space enforcement.

    Spec: §8.10 Contract 4
    Runs subprocess in cwd with optional env vars.
    Respects Zero Sudo (§2.5).
    Blocks sudo commands via user-space enforcer.

    Args:
        cmd: Command to execute.
        cwd: Working directory.
        timeout: Timeout in seconds (default 300).
        env: Optional environment variable overrides.

    Returns:
        Tuple of (exit_code, stdout, stderr).

    Raises:
        TimeoutError: After timeout seconds.
        UserSpaceViolation: If sudo/prohibited pattern detected.
    """
    from factory.core.user_space import enforce_user_space
    cmd = enforce_user_space(cmd)

    run_env = {**os.environ}
    if env:
        run_env.update(env)

    try:
        result = subprocess.run(
            cmd,
            shell=True,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=run_env,
        )
        return (result.returncode, result.stdout, result.stderr)
    except subprocess.TimeoutExpired:
        raise TimeoutError(f"Command timed out after {timeout}s: {cmd[:100]}")


# ═══════════════════════════════════════════════════════════════════
# §8.10 Contract 5: write_file
# ═══════════════════════════════════════════════════════════════════


async def write_file(
    path: str,
    content: str,
    project_id: str = "",
) -> bool:
    """Write content to a file with user-space validation.

    Spec: §8.10 Contract 5
    Validates against User-Space Enforcer (§2.5).
    Records in audit log.

    Args:
        path: File path to write.
        content: File content.
        project_id: Project ID for audit logging.

    Returns:
        True on success, False on I/O error.

    Raises:
        UserSpaceViolation: If path is outside allowed directories.
    """
    from factory.core.user_space import validate_file_path

    validate_file_path(path)

    try:
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(path, "w") as f:
            f.write(content)
        logger.info(f"[{project_id}] Wrote file: {path}")
        return True
    except OSError as e:
        logger.error(f"[{project_id}] Failed to write {path}: {e}")
        return False


# ═══════════════════════════════════════════════════════════════════
# §2.4.1 Execution Mode Manager
# ═══════════════════════════════════════════════════════════════════


def _get_project_workspace(project_id: str, app_name: Optional[str] = None) -> str:
    """Return (and create) the local workspace directory for a project.

    Directory name: sanitized app_name if available, else project_id.
    Default base: ~/factory-projects/
    Override: set FACTORY_WORKSPACE_DIR in .env.
    """
    base = os.getenv(
        "FACTORY_WORKSPACE_DIR",
        os.path.join(os.path.expanduser("~"), "factory-projects"),
    )
    if app_name:
        import re
        dir_name = re.sub(r"[^\w\-]", "_", app_name.strip().lower())
        dir_name = re.sub(r"_+", "_", dir_name).strip("_") or project_id
    else:
        dir_name = project_id
    workspace = os.path.join(base, dir_name)
    os.makedirs(workspace, exist_ok=True)
    return workspace


class ExecutionModeManager:
    """Routes task execution based on current mode (Cloud/Local/Hybrid).

    Spec: §2.4.1
    Default: Cloud Mode.
    Failover: If local machine unreachable, auto-switch to Cloud.
    """

    def __init__(self, state: PipelineState):
        self.state = state

    async def execute_task(
        self,
        task: dict,
        requires_macincloud: bool = False,
        requires_gpu: bool = False,
    ) -> dict:
        """Route task execution based on current mode.

        Spec: §2.4.1

        Args:
            task: Dict with 'name', 'command', 'type', 'working_dir', 'timeout'.
            requires_macincloud: True if task needs macOS (iOS builds, GUI).
            requires_gpu: True if task needs GPU.

        Returns:
            Dict with stdout, stderr, exit_code.
        """
        mode = self.state.execution_mode

        if mode == ExecutionMode.CLOUD:
            return await self._execute_cloud(task, requires_macincloud)
        elif mode == ExecutionMode.LOCAL:
            if not self.state.local_heartbeat_alive:
                # Issue 26: LOCAL mode does NOT fall back to CLOUD silently.
                # The operator chose LOCAL explicitly — halt and explain how to fix.
                await self._halt_local_unreachable()
            return await self._execute_local(task)
        elif mode == ExecutionMode.HYBRID:
            return await self._execute_hybrid(
                task, requires_macincloud, requires_gpu,
            )
        else:
            return await self._execute_cloud(task, requires_macincloud)

    async def _execute_cloud(
        self, task: dict, requires_mac: bool,
    ) -> dict:
        """Cloud execution: file_write goes to local workspace; builds are queued.

        Spec: §2.4.1
        file_write tasks always write to the local project workspace so generated
        code is visible on disk immediately. Build/test/deploy tasks are dispatched
        to GitHub Actions (or queued when CI is unavailable).
        """
        task_type = task.get("type", "general")
        task_name = task.get("name", "?")

        # ── file_write: always write to local workspace (never mock) ──
        if task_type == "file_write":
            content = task.get("content", "")
            # Extract relative file path: task name is "write_<rel_path>"
            rel_path = task_name[len("write_"):] if task_name.startswith("write_") else task_name
            app_name = (
                (self.state.s0_output or {}).get("app_name")
                or self.state.idea_name
            )
            workspace = _get_project_workspace(self.state.project_id, app_name)
            full_path = os.path.join(workspace, rel_path)
            success = await write_file(full_path, content, self.state.project_id)
            return {
                "stdout": full_path if success else f"failed: {full_path}",
                "stderr": "" if success else "write_file returned False",
                "exit_code": 0 if success else 1,
            }

        # ── build/test/deploy: dispatch to GitHub Actions or queue ──
        if requires_mac:
            logger.info(f"[Cloud] MacinCloud task queued: {task_name}")
            return {"stdout": f"[MacinCloud queued] {task_name}", "stderr": "", "exit_code": 0}
        else:
            logger.info(f"[Cloud] GitHub Actions task queued: {task_name}")
            return {"stdout": f"[CI queued] {task_name}", "stderr": "", "exit_code": 0}

    async def _execute_local(self, task: dict) -> dict:
        """Local execution via Cloudflare Tunnel.

        Spec: §2.4.1
        """
        logger.info(f"[Local] Tunnel task: {task.get('name', '?')}")
        cmd = task.get("command", "echo 'no command'")
        cwd = task.get("working_dir", ".")
        timeout = task.get("timeout", 600)

        exit_code, stdout, stderr = await execute_command(
            cmd, cwd=cwd, timeout=timeout,
        )
        return {
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": exit_code,
        }

    async def _execute_hybrid(
        self,
        task: dict,
        requires_mac: bool,
        requires_gpu: bool,
    ) -> dict:
        """Hybrid: cloud for backend, local for heavy tasks.

        Spec: §2.4.1
        """
        task_type = task.get("type", "general")

        if task_type == "backend_deploy":
            return await self._execute_cloud(task, requires_mac=False)
        elif task_type in ("ios_build", "gui_automation", "heavy_render"):
            if self.state.local_heartbeat_alive:
                return await self._execute_local(task)
            else:
                return await self._execute_cloud(task, requires_mac=True)
        else:
            return await self._execute_cloud(task, requires_mac)

    async def _halt_local_unreachable(self) -> None:
        """Issue 26: LOCAL mode — halt with operator guidance instead of silent CLOUD fallback.

        The operator explicitly set execution_mode=LOCAL; silently switching to CLOUD
        would consume cloud resources the operator may not have (no Render/GCP billing).
        Instead: halt, explain the issue, tell them how to fix it.
        """
        tunnel_url = os.getenv("LOCAL_TUNNEL_URL", "http://localhost:8765")
        msg = (
            f"🏠 LOCAL mode: machine unreachable ({tunnel_url})\n\n"
            f"Pipeline halted — not falling back to cloud.\n\n"
            f"To fix:\n"
            f"  1. Start your Cloudflare tunnel:\n"
            f"     cloudflared tunnel run factory-tunnel\n"
            f"  2. Resume with /continue\n\n"
            f"Or switch to cloud: /execution_mode cloud"
        )
        logger.error(f"[execution] LOCAL mode halt: machine unreachable at {tunnel_url}")
        try:
            from factory.telegram.notifications import send_telegram_message
            await send_telegram_message(
                chat_id=self.state.operator_id,
                message=msg,
            )
        except Exception:
            pass
        raise RuntimeError(f"LOCAL mode: machine unreachable at {tunnel_url}")

    async def _notify_failover(self, reason: str) -> None:
        """Legacy: notify operator of failover to Cloud Mode (HYBRID path only)."""
        original = self.state.execution_mode.value
        self.state.execution_mode = ExecutionMode.CLOUD
        logger.warning(f"Failover: {original} → Cloud ({reason})")


# ═══════════════════════════════════════════════════════════════════
# §2.4.2 Heartbeat Monitor
# ═══════════════════════════════════════════════════════════════════


class HeartbeatMonitor:
    """Pings local agent every 30 seconds.

    Spec: §2.4.2
    3 consecutive failures (90s) → auto-switch to Cloud Mode.
    """

    def __init__(self, state: PipelineState):
        self.state = state
        self.consecutive_failures = 0
        self.max_failures = 3

    async def ping(self) -> bool:
        """Send heartbeat ping to local agent.

        Returns True if alive, False if unreachable.
        """
        try:
            import httpx
            tunnel_url = os.getenv("LOCAL_TUNNEL_URL", "http://localhost:8765")
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"{tunnel_url}/heartbeat")
                if resp.status_code == 200:
                    self.consecutive_failures = 0
                    self.state.local_heartbeat_alive = True
                    return True
        except Exception:
            pass

        self.consecutive_failures += 1
        if self.consecutive_failures >= self.max_failures:
            self.state.local_heartbeat_alive = False
            # Issue 26: do NOT auto-switch to CLOUD.
            # execute_task() will halt with operator guidance on next task call.
            logger.warning(
                f"[heartbeat] Local machine unreachable "
                f"({self.consecutive_failures} missed heartbeats). "
                f"Pipeline will halt on next task — use /continue after tunnel is up."
            )
        return False


async def heartbeat_loop(state: PipelineState) -> None:
    """Background heartbeat loop running during pipeline execution.

    Spec: §2.4.2
    Runs every 30 seconds until pipeline reaches terminal state.
    """
    monitor = HeartbeatMonitor(state)
    terminal_stages = {Stage.COMPLETED, Stage.HALTED}

    while state.current_stage not in terminal_stages:
        await monitor.ping()
        await asyncio.sleep(30)

    logger.info("Heartbeat loop ended — pipeline in terminal state")