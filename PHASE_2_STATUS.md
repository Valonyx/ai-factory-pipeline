# Phase 2 Status — v5.8.12 Concurrency Fix (Issue 16)

## Files Changed

| File | Change |
|---|---|
| `factory/core/state.py` | Added `pipeline_aborted`, `pipeline_deadline`, `stage_visit_counts` fields to `PipelineState` |
| `factory/telegram/bot.py` | Added `_project_tasks` dict, `register_project_task()`, `cancel_project_task()`, `_orphan_task_sweeper()`, wired all three pipeline launch sites, updated `archive_project()`, updated `cmd_new_project` guard message |
| `factory/orchestrator.py` | Added `_check_deadline()`, `_abort_check()` helpers; added CancelledError wrapping to `run_pipeline`/`resume_pipeline`; added abort + deadline checks at every stage boundary; added abort + visit-cap checks in `pipeline_node` wrapper; added delivery guard to `_notify_stage_complete` |
| `tests/test_concurrency.py` | New test file — 15 tests across 8 test classes |
| `tests/test_phase_real.py` | Updated 1 existing test to match new `cmd_new_project` guard message wording |

## New Tests Added

`tests/test_concurrency.py` — 15 tests:
- `TestSingleActiveProjectGuard` (1): cmd_new blocks + shows app display name
- `TestCancelSetsAbortFlag` (3): register/cancel task registry wiring
- `TestPipelineAbortedSkipsStages` (1): abort flag prevents stage execution
- `TestStageVisitCap` (1): visit > 3 → HALTED / UNCAUGHT_EXCEPTION
- `TestDeadlineExceeded` (3): _check_deadline past/future/None
- `TestCancelledErrorHandled` (2): CancelledError handled, not propagated
- `TestOrphanSweeperRemovesDoneTasks` (2): sweeper removes done + orphan tasks
- `TestDeliveryGuardOnAborted` (2): delivery no-op on abort, active on normal

## Test Count

| | Count |
|---|---|
| Before Phase 2 | 687 |
| After Phase 2 | 702 |
| New tests | +15 |

## Judgment Calls

1. **`HaltCode` not imported in `state.py`**: The spec asked for a `HaltCode` import at the top of `state.py`, but `halt.py` already imports from `state.py`, creating a circular import. No import was added to `state.py`; `HaltCode` is used only in `orchestrator.py` and `halt.py` which already import it correctly.

2. **`STAGE_SEQUENCE` patching in tests**: `run_pipeline` iterates the module-level `STAGE_SEQUENCE` list (bound at import time), so patching individual `s0_intake_node` module attributes does not intercept calls made through the list. Tests for CancelledError behaviour patch `STAGE_SEQUENCE` directly via `patch.object`.

3. **`resume_pipeline` clears `pipeline_aborted`**: On resume, the abort flag is cleared so that a user who ran `/cancel` and then `/continue` gets a fresh pipeline run. This is intentional — the operator explicitly requested continuation.

4. **Orphan sweeper only checks `_active_projects_fallback`**: The sweeper cannot query Supabase on every 30s tick (latency + cost). Projects archived exclusively via Supabase (not through the fallback dict) will not trigger the sweeper's orphan detection unless the `archive_project()` function ran first and called `cancel_project_task()` directly — which it now does.

5. **`pipeline_deadline` set on `run_pipeline` only**: `resume_pipeline` does not reset the deadline; the 4-hour clock started when the project first launched. This is correct — the deadline should be wall-clock from project creation, not from each resume attempt.

## Remaining Concerns

- **Supabase-side cancel**: `cancel_project_task()` cancels the in-process asyncio task, but if the bot restarts while a pipeline is mid-run (e.g. Render redeploy), there is no stored "aborted" flag in Supabase. A future phase should persist `pipeline_aborted=True` to Supabase so a resumed pipeline knows to stop.
- **Multi-operator support**: `_project_tasks` and `_active_projects_fallback` are in-memory and process-local. Multi-replica deployments (multiple Render instances) would need a distributed locking layer (e.g. Redis) for the task registry.
- **`pipeline_deadline` not persisted**: The deadline is on `PipelineState` but if the state is not flushed to Supabase before a crash, the deadline resets on the next `run_pipeline` call.
