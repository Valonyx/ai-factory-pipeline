"""
AI Factory Pipeline v5.6 — Stub Stage Nodes (S6–S8)

Placeholder implementations for stages not yet built.
S3–S5 replaced by real implementations in Part 7.
S6–S8 replaced by real implementations in Part 8.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from factory.core.state import PipelineState, Stage
from factory.pipeline.graph import pipeline_node, register_stage_node

logger = logging.getLogger("factory.pipeline.stubs")


@pipeline_node(Stage.S6_DEPLOY)
async def s6_deploy_node(state: PipelineState) -> PipelineState:
    """S6 Stub: Deploy."""
    state.s6_output = {"deployments": {}, "all_success": True, "stub": True}
    logger.info(f"[{state.project_id}] S6 Deploy (stub)")
    return state


@pipeline_node(Stage.S7_VERIFY)
async def s7_verify_node(state: PipelineState) -> PipelineState:
    """S7 Stub: Verify."""
    state.s7_output = {"passed": True, "checks": [], "stub": True}
    logger.info(f"[{state.project_id}] S7 Verify (stub)")
    return state


@pipeline_node(Stage.S8_HANDOFF)
async def s8_handoff_node(state: PipelineState) -> PipelineState:
    """S8 Stub: Handoff."""
    state.s8_output = {"delivered": True, "stub": True}
    logger.info(f"[{state.project_id}] S8 Handoff (stub)")
    return state


# Register stubs with DAG
register_stage_node("s6_deploy", s6_deploy_node)
register_stage_node("s7_verify", s7_verify_node)
register_stage_node("s8_handoff", s8_handoff_node)