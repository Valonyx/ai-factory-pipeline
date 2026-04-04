"""
AI Factory Pipeline v5.6 — Pipeline Module

LangGraph DAG and all stage node implementations.
S0–S8 are real implementations. Stubs fully replaced.
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

# Import all real stage nodes (registers them with DAG)
from factory.pipeline.s0_intake import s0_intake_node
from factory.pipeline.s1_legal import s1_legal_node
from factory.pipeline.s2_blueprint import s2_blueprint_node
from factory.pipeline.s3_codegen import s3_codegen_node
from factory.pipeline.s4_build import s4_build_node
from factory.pipeline.s5_test import s5_test_node, pre_deploy_gate
from factory.pipeline.s6_deploy import s6_deploy_node
from factory.pipeline.s7_verify import s7_verify_node
from factory.pipeline.s8_handoff import s8_handoff_node
from factory.pipeline.halt_handler import halt_handler_node

__all__ = [
    "build_pipeline_graph",
    "run_pipeline",
    "pipeline_node",
    "s0_intake_node",
    "s1_legal_node",
    "s2_blueprint_node",
    "s3_codegen_node",
    "s4_build_node",
    "s5_test_node",
    "pre_deploy_gate",
    "s6_deploy_node",
    "s7_verify_node",
    "s8_handoff_node",
    "halt_handler_node",
]