"""
AI Factory Pipeline v5.6 — State Persistence

Thin wrapper that persists PipelineState to Supabase + in-memory fallback.
Real storage is handled by factory.integrations.supabase.

Spec Authority: v5.6 §5.6, §2.9 Triple-Write
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from factory.core.state import PipelineState

logger = logging.getLogger("factory.state.persistence")


async def persist_state(state: "PipelineState") -> bool:
    """Persist pipeline state to Supabase + in-memory fallback.

    Returns True if at least one backend succeeded.
    """
    try:
        from factory.integrations.supabase import upsert_pipeline_state, upsert_active_project
        await upsert_active_project(state.operator_id, state)
        await upsert_pipeline_state(state.project_id, state)
        return True
    except Exception as e:
        logger.debug(f"[state.persistence] Supabase persist failed: {e}")
        return False


async def load_state(project_id: str) -> "PipelineState | None":
    """Load pipeline state by project ID from Supabase."""
    try:
        from factory.integrations.supabase import get_supabase_client
        from factory.core.state import PipelineState
        client = get_supabase_client()
        if client:
            result = (
                client.table("pipeline_states")
                .select("state_json")
                .eq("project_id", project_id)
                .execute()
            )
            if result.data:
                return PipelineState.model_validate(result.data[0]["state_json"])
    except Exception as e:
        logger.debug(f"[state.persistence] Load failed for {project_id}: {e}")
    return None


async def take_snapshot(state: "PipelineState", index: int) -> bool:
    """Save a time-travel snapshot for the current stage."""
    try:
        from factory.integrations.supabase import get_supabase_client
        client = get_supabase_client()
        if client:
            client.table("state_snapshots").upsert({
                "project_id": state.project_id,
                "operator_id": state.operator_id,
                "stage": state.current_stage.value,
                "snapshot_index": index,
                "state_json": state.model_dump(mode="json"),
            }).execute()
            return True
    except Exception as e:
        logger.debug(f"[state.persistence] Snapshot failed: {e}")
    return False
