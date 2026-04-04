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
    yield
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

    Receives updates from Telegram, dispatches to bot handler.
    """
    try:
        from factory.telegram.bot import handle_telegram_update
        body = await request.json()
        await handle_telegram_update(body)
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


# ═══════════════════════════════════════════════════════════════════
# Cloud Run Entry
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8080"))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")