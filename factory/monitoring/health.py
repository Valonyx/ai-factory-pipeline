"""
AI Factory Pipeline v5.8 — Health Monitoring

Implements:
  - §7.4.1 Health Endpoints (/health, /health-deep)
  - §2.4.2 Heartbeat Monitor (Local/Hybrid execution)
  - Service dependency checks (Supabase, Neo4j, Anthropic)
  - Pipeline readiness status

Spec Authority: v5.8 §7.4.1, §2.4.2
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Optional

from factory.core.state import (
    ExecutionMode,
    PipelineState,
    Stage,
)

logger = logging.getLogger("factory.monitoring.health")


# ═══════════════════════════════════════════════════════════════════
# §7.4.1 Health Endpoints
# ═══════════════════════════════════════════════════════════════════

PIPELINE_VERSION = "5.8"


async def health_check() -> dict:
    """Basic liveness check.

    Spec: §7.4.1 — /health endpoint
    Always returns ok if process is running.
    """
    return {
        "status": "ok",
        "version": PIPELINE_VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


async def readiness_check(
    supabase_check_fn=None,
    neo4j_check_fn=None,
    anthropic_check_fn=None,
) -> dict:
    """Deep readiness: verify all dependencies.

    Spec: §7.4.1 — /health-deep endpoint
    Checks: Supabase, Neo4j, Anthropic connectivity.
    Returns per-service status.
    """
    checks: dict[str, str] = {}

    # Supabase
    if supabase_check_fn:
        try:
            await supabase_check_fn()
            checks["supabase"] = "ok"
        except Exception:
            checks["supabase"] = "error"
    else:
        checks["supabase"] = "unchecked"

    # Neo4j
    if neo4j_check_fn:
        try:
            await neo4j_check_fn()
            checks["neo4j"] = "ok"
        except Exception:
            checks["neo4j"] = "error"
    else:
        checks["neo4j"] = "unchecked"

    # Anthropic API
    if anthropic_check_fn:
        try:
            result = await anthropic_check_fn()
            checks["anthropic"] = "ok" if result else "degraded"
        except Exception:
            checks["anthropic"] = "error"
    else:
        checks["anthropic"] = "unchecked"

    # Secrets validation
    required_secrets = [
        "ANTHROPIC_API_KEY", "SUPABASE_URL", "SUPABASE_SERVICE_KEY",
        "NEO4J_URI", "GITHUB_TOKEN", "TELEGRAM_BOT_TOKEN",
    ]
    missing = [s for s in required_secrets if not os.getenv(s)]
    checks["secrets"] = "ok" if not missing else f"missing:{len(missing)}"

    all_ok = all(v == "ok" for v in checks.values())
    return {
        "status": "ready" if all_ok else "degraded",
        "version": PIPELINE_VERSION,
        "checks": checks,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ═══════════════════════════════════════════════════════════════════
# §2.4.2 Heartbeat Monitor
# ═══════════════════════════════════════════════════════════════════


class HeartbeatMonitor:
    """Pings local agent every 30 seconds.

    Spec: §2.4.2

    3 consecutive failures (90s) → auto-switch to Cloud Mode.
    Used in Local and Hybrid execution modes.
    """

    def __init__(
        self,
        state: PipelineState,
        interval_seconds: int = 30,
        max_failures: int = 3,
        notify_fn=None,
    ):
        self.state = state
        self.interval = interval_seconds
        self.max_failures = max_failures
        self.consecutive_failures = 0
        self._notify_fn = notify_fn
        self._running = False
        self._task: Optional[asyncio.Task] = None

    @property
    def is_alive(self) -> bool:
        return self.state.local_heartbeat_alive

    async def ping(self) -> bool:
        """Single heartbeat ping to local agent.

        Spec: §2.4.2
        """
        tunnel_url = self.state.project_metadata.get("tunnel_url")
        if not tunnel_url:
            self.consecutive_failures += 1
            return self._evaluate_failures()

        try:
            import httpx
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"{tunnel_url}/heartbeat")
                if resp.status_code == 200:
                    self.consecutive_failures = 0
                    self.state.local_heartbeat_alive = True
                    return True
        except Exception:
            pass

        self.consecutive_failures += 1
        return self._evaluate_failures()

    def _evaluate_failures(self) -> bool:
        """Check if failures have hit threshold.

        Spec: §2.4.2 — 3 consecutive failures → Cloud failover.
        """
        if self.consecutive_failures >= self.max_failures:
            self.state.local_heartbeat_alive = False

            if self.state.execution_mode != ExecutionMode.CLOUD:
                original = self.state.execution_mode.value
                self.state.execution_mode = ExecutionMode.CLOUD
                logger.warning(
                    f"[{self.state.project_id}] Heartbeat: "
                    f"{self.consecutive_failures} missed pings. "
                    f"Failover {original} → Cloud."
                )
        return False

    # ───────────────────────────────────────────────────────────
    # Background Loop
    # ───────────────────────────────────────────────────────────

    async def run_loop(self) -> None:
        """Background task running during pipeline execution.

        Spec: §2.4.2
        Runs until S9_HANDOFF or HALTED.
        """
        self._running = True
        logger.info(f"[{self.state.project_id}] Heartbeat monitor started")

        while self._running:
            if self.state.current_stage in (Stage.S9_HANDOFF, Stage.HALTED):
                break

            alive = await self.ping()

            if not alive and self.consecutive_failures == self.max_failures:
                # Just hit threshold — send notification
                if self._notify_fn:
                    try:
                        await self._notify_fn(
                            self.state.operator_id,
                            f"🔴 Local machine unreachable "
                            f"({self.max_failures} missed heartbeats).\n"
                            f"Auto-switched to Cloud Mode.",
                        )
                    except Exception as e:
                        logger.error(f"Heartbeat notification failed: {e}")

            await asyncio.sleep(self.interval)

        self._running = False
        logger.info(f"[{self.state.project_id}] Heartbeat monitor stopped")

    def start(self) -> asyncio.Task:
        """Start heartbeat loop as background task."""
        self._task = asyncio.create_task(self.run_loop())
        return self._task

    def stop(self) -> None:
        """Stop heartbeat loop."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()

    def status(self) -> dict:
        """Heartbeat status for dashboards."""
        return {
            "alive": self.state.local_heartbeat_alive,
            "consecutive_failures": self.consecutive_failures,
            "max_failures": self.max_failures,
            "execution_mode": self.state.execution_mode.value,
            "running": self._running,
        }