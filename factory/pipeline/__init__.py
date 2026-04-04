"""
AI Factory Pipeline v5.6 — Pipeline Module

LangGraph DAG and stage node implementations.
Import this module to register all stage nodes with the DAG.
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

# Import stage nodes (registers them with DAG via register_stage_node)
from factory.pipeline.s0_intake import s0_intake_node
from factory.pipeline.s1_legal import s1_legal_node
from factory.pipeline.s2_blueprint import s2_blueprint_node
from factory.pipeline.halt_handler import halt_handler_node

# Import stubs for S3–S8 (registers them with DAG)
from factory.pipeline import stubs  # noqa: F401

__all__ = [
    "build_pipeline_graph",
    "run_pipeline",
    "pipeline_node",
    "s0_intake_node",
    "s1_legal_node",
    "s2_blueprint_node",
    "halt_handler_node",
]