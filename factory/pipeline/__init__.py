"""
AI Factory Pipeline v5.8 — Pipeline Module

LangGraph DAG and all stage node implementations.
S0–S9 (10 stages): S3 Design is new in v5.8 (split from S2).
"""

# Import graph infrastructure first
from factory.pipeline.graph import (
    build_pipeline_graph,
    run_pipeline,
    pipeline_node,
    register_stage_node,
    transition_to,
    route_after_test,
    route_after_verify,
    persist_state,
    legal_check_hook,
    LEGAL_CHECKS_BY_STAGE,
    SimpleExecutor,
)

# Import all stage nodes (registers them with DAG)
from factory.pipeline.s0_intake import s0_intake_node
from factory.pipeline.s1_legal import s1_legal_node
from factory.pipeline.s2_blueprint import s2_blueprint_node
from factory.pipeline.s3_design import s3_design_node           # NEW v5.8
from factory.pipeline.s4_codegen import s4_codegen_node         # was s3_codegen
from factory.pipeline.s5_build import s5_build_node             # was s4_build
from factory.pipeline.s6_test import s6_test_node, pre_deploy_gate  # was s5_test
from factory.pipeline.s7_deploy import s7_deploy_node           # was s6_deploy
from factory.pipeline.s8_verify import s8_verify_node           # was s7_verify
from factory.pipeline.s9_handoff import s9_handoff_node         # was s8_handoff
from factory.pipeline.halt_handler import halt_handler_node

__all__ = [
    "build_pipeline_graph",
    "run_pipeline",
    "pipeline_node",
    "s0_intake_node",
    "s1_legal_node",
    "s2_blueprint_node",
    "s3_design_node",
    "s4_codegen_node",
    "s5_build_node",
    "s6_test_node",
    "pre_deploy_gate",
    "s7_deploy_node",
    "s8_verify_node",
    "s9_handoff_node",
    "halt_handler_node",
]