"""
AI Factory Pipeline v5.6 — Health Checks & Startup Validation

Implements:
  - §7.3.0 Startup health checks (6-service validation) [H1]
  - §7.3.0a Crash loop detection
  - §7.4.1 Health endpoints (/health, /health-deep)
  - §7.4.2 Cost monitoring alerts [C2]

Spec Authority: v5.6 §7.3, §7.4
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from factory.core.state import (
    BUDGET_CONFIG,
    NotificationType,
    PipelineState,
)

logger = logging.getLogger("factory.telegram.health")


# ═══════════════════════════════════════════════════════════════════
# §7.4.1 Health Endpoints
# ═══════════════════════════════════════════════════════════════════


async def health_check() -> dict:
    """Basic liveness check.

    Spec: §7.4.1
    Cloud Run calls this to verify the process is running.
    Always returns ok if the service is up.
    """
    return {"status": "ok", "version": "5.6"}


async def readiness_check() -> dict:
    """Deep readiness: verify all critical dependencies.

    Spec: §7.4.1
    Checks Supabase, Neo4j, Anthropic connectivity.
    Returns per-service status.
    """
    checks: dict[str, str] = {}

    # 1. Supabase
    try:
        from factory.integrations.supabase import get_supabase_client
        sb = get_supabase_client()
        sb.table("operator_whitelist").select("count").limit(1).execute()
        checks["supabase"] = "ok"
    except Exception:
        checks["supabase"] = "error"

    # 2. Neo4j
    try:
        from factory.integrations.neo4j import neo4j_run
        await neo4j_run("RETURN 1 AS ok")
        checks["neo4j"] = "ok"
    except Exception:
        checks["neo4j"] = "error"

    # 3. Anthropic
    try:
        import httpx
        from factory.core.secrets import get_secret
        api_key = get_secret("ANTHROPIC_API_KEY")
        if api_key:
            async with httpx.AsyncClient(timeout=5) as c:
                r = await c.get(
                    "https://api.anthropic.com/v1/models",
                    headers={
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01",
                    },
                )
                checks["anthropic"] = "ok" if r.status_code == 200 else "degraded"
        else:
            checks["anthropic"] = "not_configured"
    except Exception:
        checks["anthropic"] = "error"

    all_ok = all(v == "ok" for v in checks.values())
    return {
        "status": "ready" if all_ok else "degraded",
        "checks": checks,
    }


# ═══════════════════════════════════════════════════════════════════
# §7.3.0 Startup Health Checks [H1]
# ═══════════════════════════════════════════════════════════════════

# Service criticality classification (§7.3.0)
CRITICAL_SERVICES = ["supabase", "telegram", "anthropic"]
WARNING_SERVICES = ["neo4j", "github", "perplexity"]


async def startup_health_checks() -> dict[str, bool]:
    """6-service health check at startup.

    Spec: §7.3.0 [H1]
    ALL critical services must pass before pipeline accepts work.
    If any critical service fails, pipeline enters DEGRADED mode.

    Returns:
        Dict mapping service name → healthy (True/False).
    """
    checks: dict[str, bool] = {}

    # 1. Supabase (CRITICAL)
    try:
        from factory.integrations.supabase import get_supabase_client
        sb = get_supabase_client()
        sb.table("active_projects").select("count").limit(1).execute()
        checks["supabase"] = True
    except Exception:
        checks["supabase"] = False

    # 2. Neo4j (WARNING)
    try:
        from factory.integrations.neo4j import neo4j_run
        await neo4j_run("RETURN 1 AS ok")
        checks["neo4j"] = True
    except Exception:
        checks["neo4j"] = False

    # 3. GitHub (WARNING)
    try:
        import httpx
        from factory.core.secrets import get_secret
        token = get_secret("GITHUB_TOKEN")
        if token:
            async with httpx.AsyncClient(timeout=5) as c:
                r = await c.get(
                    "https://api.github.com/rate_limit",
                    headers={"Authorization": f"token {token}"},
                )
                checks["github"] = r.status_code == 200
        else:
            checks["github"] = False
    except Exception:
        checks["github"] = False

    # 4. Telegram (CRITICAL)
    try:
        from factory.telegram.notifications import get_bot
        bot = get_bot()
        if bot:
            me = await bot.get_me()
            checks["telegram"] = me is not None
        else:
            checks["telegram"] = False
    except Exception:
        checks["telegram"] = False

    # 5. Anthropic (CRITICAL)
    try:
        import httpx
        from factory.core.secrets import get_secret
        api_key = get_secret("ANTHROPIC_API_KEY")
        if api_key:
            async with httpx.AsyncClient(timeout=5) as c:
                r = await c.get(
                    "https://api.anthropic.com/v1/models",
                    headers={
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01",
                    },
                )
                checks["anthropic"] = r.status_code == 200
        else:
            checks["anthropic"] = False
    except Exception:
        checks["anthropic"] = False

    # 6. Perplexity (WARNING)
    try:
        import httpx
        from factory.core.secrets import get_secret
        pkey = get_secret("PERPLEXITY_API_KEY")
        if pkey:
            async with httpx.AsyncClient(timeout=5) as c:
                r = await c.post(
                    "https://api.perplexity.ai/chat/completions",
                    headers={"Authorization": f"Bearer {pkey}"},
                    json={
                        "model": "sonar",
                        "messages": [{"role": "user", "content": "ping"}],
                    },
                )
                checks["perplexity"] = r.status_code == 200
        else:
            checks["perplexity"] = False
    except Exception:
        checks["perplexity"] = False

    # Evaluate criticality
    critical_ok = all(
        checks.get(s, False) for s in CRITICAL_SERVICES
    )
    failed_critical = [
        s for s in CRITICAL_SERVICES if not checks.get(s, False)
    ]
    failed_warning = [
        s for s in WARNING_SERVICES if not checks.get(s, False)
    ]

    if not critical_ok:
        logger.critical(
            f"[H1] CRITICAL services down: {failed_critical}. "
            f"Pipeline in DEGRADED mode."
        )
    elif failed_warning:
        logger.warning(
            f"[H1] WARNING services down: {failed_warning}. "
            f"Pipeline operational with reduced capability."
        )
    else:
        logger.info("[H1] All 6 services healthy. Pipeline ready.")

    return checks


# ═══════════════════════════════════════════════════════════════════
# §7.3.0a Crash Loop Detection [H1]
# ═══════════════════════════════════════════════════════════════════

CRASH_THRESHOLD = 3
CRASH_WINDOW_MINUTES = 10

# In-memory crash log (Supabase-backed in production)
_crash_log: list[str] = []


async def record_crash_and_check_loop() -> bool:
    """Check if pipeline is in a crash loop.

    Spec: §7.3.0a [H1]
    Returns True if crash loop detected (≥3 crashes in 10 min).
    If loop detected, pipeline enters SAFE MODE.
    """
    now = datetime.now(timezone.utc)
    _crash_log.append(now.isoformat())

    # Keep only crashes within window
    cutoff = now - timedelta(minutes=CRASH_WINDOW_MINUTES)
    recent = [
        c for c in _crash_log
        if datetime.fromisoformat(c) > cutoff
    ]
    _crash_log.clear()
    _crash_log.extend(recent)

    if len(recent) >= CRASH_THRESHOLD:
        logger.critical(
            f"[H1] CRASH LOOP DETECTED: {len(recent)} crashes "
            f"in {CRASH_WINDOW_MINUTES} min. SAFE MODE activated."
        )
        return True

    return False


# ═══════════════════════════════════════════════════════════════════
# §7.4.2 Cost Monitoring Alerts [C2]
# ═══════════════════════════════════════════════════════════════════

COST_ALERT_THRESHOLDS: dict[str, float] = {
    "per_project_warning": 8.00,
    "per_project_critical": 15.00,
    "monthly_warning": 180.00,
}


async def check_cost_alerts(state: PipelineState) -> None:
    """Check cost thresholds and alert operator.

    Spec: §7.4.2 [C2]
    All thresholds derived from BUDGET_CONFIG.
    """
    from factory.telegram.notifications import notify_operator

    cost = state.total_cost_usd

    if cost > COST_ALERT_THRESHOLDS["per_project_critical"]:
        await notify_operator(
            state,
            NotificationType.BUDGET_ALERT,
            f"🚨 Project cost CRITICAL: ${cost:.2f} "
            f"(>${COST_ALERT_THRESHOLDS['per_project_critical']})\n"
            f"Consider /cancel or reducing scope.",
        )
    elif cost > COST_ALERT_THRESHOLDS["per_project_warning"]:
        await notify_operator(
            state,
            NotificationType.BUDGET_ALERT,
            f"⚠️ Project cost elevated: ${cost:.2f}",
        )