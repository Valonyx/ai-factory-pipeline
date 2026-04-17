"""
AI Factory Pipeline v5.8.12 — Stage Regression Engine
Issue 1: Allow operator to roll back to a previous stage within a live project.

Uses existing time-travel infrastructure:
  restore_state()     — rehydrate PipelineState from a Supabase snapshot
  resume_pipeline()   — run the pipeline from a given stage forward

Spec Authority: v5.8.12 §1
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger("factory.pipeline.stage_regression")

# Ordered stage names (matches orchestrator STAGE_SEQUENCE)
STAGE_ORDER = [
    "S0_INTAKE", "S1_LEGAL", "S2_BLUEPRINT", "S3_DESIGN",
    "S4_CODEGEN", "S5_BUILD", "S6_TEST", "S7_DEPLOY", "S8_VERIFY", "S9_HANDOFF",
]

# Map user-friendly aliases to canonical stage names
STAGE_ALIASES: dict[str, str] = {
    "s0": "S0_INTAKE",   "intake": "S0_INTAKE",
    "s1": "S1_LEGAL",    "legal": "S1_LEGAL",
    "s2": "S2_BLUEPRINT","blueprint": "S2_BLUEPRINT",
    "s3": "S3_DESIGN",   "design": "S3_DESIGN",
    "s4": "S4_CODEGEN",  "codegen": "S4_CODEGEN",   "code": "S4_CODEGEN",
    "s5": "S5_BUILD",    "build": "S5_BUILD",
    "s6": "S6_TEST",     "test": "S6_TEST",
    "s7": "S7_DEPLOY",   "deploy": "S7_DEPLOY",
    "s8": "S8_VERIFY",   "verify": "S8_VERIFY",
    "s9": "S9_HANDOFF",  "handoff": "S9_HANDOFF",
}


def resolve_stage(name: str) -> Optional[str]:
    """Resolve a user-provided stage name or alias to canonical stage name."""
    n = name.strip().lower()
    if n.upper() in STAGE_ORDER:
        return n.upper()
    return STAGE_ALIASES.get(n)


async def request_regression(
    project_id: str,
    target_stage: str,
    operator_id: str,
    notify_fn=None,          # async callable(str) to send Telegram messages
) -> Optional[object]:       # returns resumed PipelineState or None on failure
    """Roll back a project to a prior stage and re-run from there.

    Steps:
    1. Resolve target_stage alias to canonical name.
    2. Find the most recent snapshot at or before target_stage.
    3. Restore state from that snapshot.
    4. Reset `pipeline_aborted` and `legal_halt` flags.
    5. Set `current_stage` to target_stage.
    6. Resume pipeline from target_stage.

    Returns the final PipelineState, or None if snapshot not found.
    """
    canonical = resolve_stage(target_stage)
    if not canonical:
        msg = f"Unknown stage '{target_stage}'. Valid: {', '.join(STAGE_ALIASES.keys())}"
        logger.warning(f"[{project_id}] Stage regression rejected: {msg}")
        if notify_fn:
            await notify_fn(f"⚠️ {msg}")
        return None

    # Find snapshot at or before the target stage
    from factory.integrations.supabase import list_snapshots, restore_state
    snapshots = await list_snapshots(project_id, limit=30)
    target_idx = STAGE_ORDER.index(canonical) if canonical in STAGE_ORDER else -1

    # Pick the latest snapshot whose stage is ≤ target
    best_snap = None
    for snap in snapshots:  # already sorted desc by snapshot_id
        stage_val = (snap.get("stage") or "").upper()
        if stage_val in STAGE_ORDER:
            if STAGE_ORDER.index(stage_val) <= target_idx:
                best_snap = snap
                break

    if not best_snap:
        # No snapshot at/before target — use snapshot 1 or None
        if snapshots:
            best_snap = snapshots[-1]  # oldest available
        else:
            msg = f"No snapshots available for project. Run at least one stage first."
            logger.warning(f"[{project_id}] {msg}")
            if notify_fn:
                await notify_fn(f"⚠️ {msg}")
            return None

    snap_id = best_snap["snapshot_id"]
    if notify_fn:
        await notify_fn(
            f"⏪ Restoring to snapshot #{snap_id} (stage: {best_snap.get('stage')}) "
            f"then re-running from {canonical}…"
        )

    state = await restore_state(project_id, snap_id, validate_checksum=False)
    if state is None:
        if notify_fn:
            await notify_fn(f"❌ Could not restore snapshot #{snap_id}. Try /snapshots.")
        return None

    # Reset abort/halt flags so the pipeline can run again
    state.pipeline_aborted = False
    state.legal_halt = False
    state.legal_halt_reason = None
    state.project_metadata.pop("halt_reason_struct", None)
    state.project_metadata.pop("halt_reason", None)

    # Set stage to target
    from factory.core.state import Stage
    try:
        state.current_stage = Stage(canonical.lower().replace("_", "_"))
    except ValueError:
        # Try the exact value
        for s in Stage:
            if s.value.upper() == canonical:
                state.current_stage = s
                break

    logger.info(f"[{project_id}] Regression: restored snap #{snap_id}, resuming from {canonical}")

    from factory.orchestrator import resume_pipeline
    final_state = await resume_pipeline(state)
    return final_state


async def analyze_regression_impact(
    current_stage: str,
    target_stage: str,
) -> dict:
    """Return metadata about what a regression would affect."""
    curr_idx = STAGE_ORDER.index(current_stage) if current_stage in STAGE_ORDER else -1
    tgt_idx = STAGE_ORDER.index(target_stage) if target_stage in STAGE_ORDER else -1
    if tgt_idx < 0 or curr_idx < 0:
        return {"error": "Invalid stage name"}
    stages_to_rerun = STAGE_ORDER[tgt_idx: curr_idx + 1]
    return {
        "target_stage": target_stage,
        "current_stage": current_stage,
        "stages_to_rerun": stages_to_rerun,
        "rerun_count": len(stages_to_rerun),
        "warning": (
            "This will discard all work from "
            f"{target_stage} onwards and re-run {len(stages_to_rerun)} stage(s)."
        ),
    }
