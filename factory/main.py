"""
AI Factory Pipeline v5.6 — FastAPI Entry Point

Implements:
  - §7.4.1 /health (liveness) and /health-deep (readiness)
  - Telegram webhook endpoint (/webhook)
  - Pipeline trigger endpoint (/run)
  - Cloud Run compatible (PORT env var)

Spec Authority: v5.6 §7.4.1, §5.1
"""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from factory.monitoring.health import (
    health_check,
    readiness_check,
    PIPELINE_VERSION,
)
from factory.orchestrator import run_pipeline, run_pipeline_from_description
from factory.core.state import PipelineState, AutonomyMode

logger = logging.getLogger("factory.main")


# ═══════════════════════════════════════════════════════════════════
# Lifespan
# ═══════════════════════════════════════════════════════════════════


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown."""
    logger.info(f"AI Factory Pipeline v{PIPELINE_VERSION} starting")

    polling_task = None
    if os.getenv("TELEGRAM_POLLING", "false").lower() == "true":
        # Local dev: run bot in polling mode
        try:
            from factory.telegram.bot import run_bot_polling
            polling_task = asyncio.create_task(run_bot_polling())
            logger.info("Telegram polling started as background task")
        except Exception as e:
            logger.warning(f"Telegram polling failed to start: {e}")
    else:
        # Webhook mode (Render/production): pre-initialize bot so first
        # webhook call responds instantly instead of hanging 30+ seconds.
        async def _prewarm_bot():
            try:
                from factory.telegram.bot import handle_telegram_update as _h  # noqa
                from factory.telegram import bot as _bot_mod
                import asyncio as _a
                if _bot_mod._webhook_app_lock is None:
                    _bot_mod._webhook_app_lock = _a.Lock()
                async with _bot_mod._webhook_app_lock:
                    if _bot_mod._webhook_app is None:
                        _bot_mod._webhook_app = await _bot_mod.setup_bot()
                        if _bot_mod._webhook_app is not None:
                            await _bot_mod._webhook_app.initialize()
                            logger.info("Telegram bot pre-warmed and ready")
            except Exception as e:
                logger.warning(f"Bot pre-warm failed (will init on first request): {e}")
        asyncio.create_task(_prewarm_bot())

    yield

    if polling_task and not polling_task.done():
        polling_task.cancel()
        try:
            await polling_task
        except asyncio.CancelledError:
            pass
    logger.info("AI Factory Pipeline shutting down")


# ═══════════════════════════════════════════════════════════════════
# FastAPI App
# ═══════════════════════════════════════════════════════════════════

app = FastAPI(
    title="AI Factory Pipeline",
    version=PIPELINE_VERSION,
    description="Automated AI application factory — v5.6",
    lifespan=lifespan,
)


# ═══════════════════════════════════════════════════════════════════
# §7.4.1 Health Endpoints
# ═══════════════════════════════════════════════════════════════════


@app.get("/health")
async def health():
    """Liveness check — is the process running?

    Spec: §7.4.1
    """
    return await health_check()


@app.get("/health-deep")
async def health_deep():
    """Readiness check — are all dependencies available?

    Spec: §7.4.1

    Checks: Supabase, Neo4j, Anthropic API, Secrets.
    """
    result = await readiness_check()
    status_code = 200 if result["status"] == "ready" else 503
    return JSONResponse(content=result, status_code=status_code)


# ═══════════════════════════════════════════════════════════════════
# Telegram Webhook
# ═══════════════════════════════════════════════════════════════════


@app.post("/webhook")
async def telegram_webhook(request: Request):
    """Telegram Bot API webhook endpoint.

    Spec: §5.1

    Responds to Telegram immediately (within 5s) and dispatches the
    update to the bot handler as a background task so Telegram never
    times out waiting for us.
    """
    try:
        from factory.telegram.bot import handle_telegram_update
        body = await request.json()
        # Fire-and-forget: Telegram requires a fast 200 OK, the actual
        # processing happens asynchronously so we never block the response.
        asyncio.create_task(handle_telegram_update(body))
        return {"ok": True}
    except ImportError:
        logger.warning("Telegram bot module not fully configured")
        return JSONResponse(
            {"ok": False, "error": "bot_not_configured"},
            status_code=503,
        )
    except Exception as e:
        logger.error(f"Webhook error: {e}", exc_info=True)
        return JSONResponse(
            {"ok": False, "error": str(e)[:200]},
            status_code=500,
        )


# ═══════════════════════════════════════════════════════════════════
# Pipeline Trigger (API)
# ═══════════════════════════════════════════════════════════════════


@app.post("/run")
async def trigger_pipeline(request: Request):
    """Trigger pipeline run via API.

    Body: {
        "description": "Build a ...",
        "operator_id": "telegram-123",
        "autonomy_mode": "autopilot" | "copilot"
    }
    """
    body = await request.json()
    description = body.get("description", "")
    operator_id = body.get("operator_id", "api-operator")
    mode = body.get("autonomy_mode", "autopilot")

    if not description:
        return JSONResponse(
            {"error": "description required"},
            status_code=400,
        )

    # Run pipeline in background
    async def _run():
        try:
            state = await run_pipeline_from_description(
                description, operator_id, mode,
            )
            logger.info(
                f"Pipeline complete: {state.project_id} "
                f"stage={state.current_stage.value} "
                f"cost=${state.total_cost_usd:.2f}"
            )
        except Exception as e:
            logger.error(f"Pipeline failed: {e}", exc_info=True)

    asyncio.create_task(_run())

    return {
        "status": "started",
        "message": "Pipeline running in background",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ═══════════════════════════════════════════════════════════════════
# Status Endpoint
# ═══════════════════════════════════════════════════════════════════


@app.get("/status")
async def pipeline_status():
    """Pipeline system status."""
    from factory.monitoring.budget_governor import budget_governor
    from factory.monitoring.cost_tracker import cost_tracker

    return {
        "version": PIPELINE_VERSION,
        "budget": budget_governor.status(),
        "monthly_cost_usd": round(cost_tracker.monthly_total(), 2),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.post("/janitor")
async def janitor_run():
    """Janitor Agent — purge expired temp artifacts and TTL-expired graph nodes.

    Spec: §2.10.2 — Janitor 6-hour cycle triggered via Cloud Scheduler.
    """
    results: dict = {
        "artifacts_purged": 0,
        "neo4j_nodes_purged": 0,
        "errors": [],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    # ── Purge expired temp_artifacts from Supabase ──────────────────
    try:
        from factory.integrations.supabase import get_supabase_client
        sb = get_supabase_client()
        now_iso = datetime.now(timezone.utc).isoformat()
        resp = (
            sb.table("temp_artifacts")
            .delete()
            .lt("expires_at", now_iso)
            .execute()
        )
        count = len(resp.data) if hasattr(resp, "data") and resp.data else 0
        results["artifacts_purged"] = count
        logger.info(f"[Janitor] Purged {count} expired temp_artifacts")
    except Exception as e:
        results["errors"].append(f"supabase_purge: {e}")
        logger.warning(f"[Janitor] Supabase purge failed: {e}")

    # ── Purge TTL-expired Neo4j nodes (§2.10.2) ─────────────────────
    try:
        from factory.integrations.neo4j import neo4j_run, JANITOR_EXEMPT
        from datetime import timedelta
        ttl_cutoff = (
            datetime.now(timezone.utc) - timedelta(hours=168)  # 7-day TTL
        ).isoformat()
        exempt_labels = "|".join(JANITOR_EXEMPT)
        query = (
            f"MATCH (n) WHERE NOT n:({exempt_labels}) "
            f"AND n.created_at < $cutoff "
            f"DETACH DELETE n RETURN count(n) AS deleted"
        )
        rows = await neo4j_run(query, {"cutoff": ttl_cutoff})
        deleted = rows[0].get("deleted", 0) if rows else 0
        results["neo4j_nodes_purged"] = deleted
        logger.info(f"[Janitor] Purged {deleted} Neo4j nodes")
    except Exception as e:
        results["errors"].append(f"neo4j_purge: {e}")
        logger.debug(f"[Janitor] Neo4j purge skipped: {e}")

    return results


# ═══════════════════════════════════════════════════════════════════
# Cloud Run Entry
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8080"))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")