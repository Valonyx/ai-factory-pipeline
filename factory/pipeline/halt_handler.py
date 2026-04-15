"""
AI Factory Pipeline v5.8 — Halt Handler Node

Implements:
  - §4.10 Halt handler (notify operator with diagnosis)

Spec Authority: v5.6 §4.10
"""

from __future__ import annotations

import logging

from factory.core.state import PipelineState, Stage
from factory.telegram.messages import format_halt_message
from factory.telegram.notifications import send_telegram_message
from factory.pipeline.graph import register_stage_node, transition_to

logger = logging.getLogger("factory.pipeline.halt_handler")


async def halt_handler_node(state: PipelineState) -> PipelineState:
    """Handle pipeline halt — notify operator with diagnosis.

    Spec: §4.10
    """
    transition_to(state, Stage.HALTED)
    message = format_halt_message(state)
    await send_telegram_message(state.operator_id, message)

    logger.warning(
        f"[{state.project_id}] Pipeline HALTED at {state.current_stage.value}: "
        f"{state.legal_halt_reason or 'unknown reason'}"
    )
    return state


# Register with DAG
register_stage_node("halt_handler", halt_handler_node)