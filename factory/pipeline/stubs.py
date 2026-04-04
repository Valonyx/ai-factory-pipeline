"""
AI Factory Pipeline v5.6 — Stub Stage Nodes (S3–S8)

Placeholder implementations for stages not yet built.
Each stub transitions through the stage and produces minimal output.
These are replaced by real implementations in Parts 7–9.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from factory.core.state import PipelineState, Stage
from factory.pipeline.graph import pipeline_node, register_stage_node

logger = logging.getLogger("factory.pipeline.stubs")


@pipeline_node(Stage.S3_CODEGEN)
async def s3_codegen_node(state: PipelineState) -> PipelineState:
    """S3 Stub: CodeGen."""
    state.s3_output = {"files_generated": 0, "stub": True}
    logger.info(f"[{state.project_id}] S3 CodeGen (stub)")
    return state


@pipeline_node(Stage.S4_BUILD)
async def s4_build_node(state: PipelineState) -> PipelineState:
    """S4 Stub: Build."""
    state.s4_output = {"build_success": True, "artifacts": {}, "stub": True}
    logger.info(f"[{state.project_id}] S4 Build (stub)")
    return state


@pipeline_node(Stage.S5_TEST)
async def s5_test_node(state: PipelineState) -> PipelineState:
    """S5 Stub: Test."""
    state.s5_output = {
        "passed": True, "total_tests": 1, "passed_tests": 1,
        "failed_tests": 0, "failures": [], "stub": True,
    }
    logger.info(f"[{state.project_id}] S5 Test (stub)")
    return state


@pipeline_node(Stage.S6_DEPLOY)
async def s6_deploy_node(state: PipelineState) -> PipelineState:
    """S6 Stub: Deploy."""
    state.s6_output = {"deployments": {}, "stub": True}
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


# Register all stubs with DAG
register_stage_node("s3_codegen", s3_codegen_node)
register_stage_node("s4_build", s4_build_node)
register_stage_node("s5_test", s5_test_node)
register_stage_node("s6_deploy", s6_deploy_node)
register_stage_node("s7_verify", s7_verify_node)
register_stage_node("s8_handoff", s8_handoff_node)