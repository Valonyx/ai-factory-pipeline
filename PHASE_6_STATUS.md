# Phase 6 Status — v5.8.12 (Issues 1–4)

**Tag:** `v5.8.12-phase6-regression-timetravel`
**Tests:** 760 passed (750 pre-existing + 10 new)
**Date:** 2026-04-18

## Commits (7)

| Commit | Change |
|--------|--------|
| 33487c2 | fix(orchestrator): `_persist_snapshot` now calls `upsert_pipeline_state` |
| f4b987b | feat(supabase): `diff_snapshots` helper |
| 342ab89 | feat(pipeline): `StageRegressionEngine` — `request_regression` + `analyze_impact` |
| ff14b93 | feat(bot): `/rerun` + `/rerun_confirm` + `/diff` commands |
| cbab85a | fix(orchestrator): comprehensive per-stage artifact delivery map |
| 4acbda4 | fix(s7): deploy-less pre-check — `skip_store_upload` flag |
| c5c9e3b | feat(tests): 10 Phase 6 tests |

## Issues Closed

- **Issue 1 (Stage Regression):** `StageRegressionEngine` in `factory/pipeline/stage_regression.py`. `/rerun <stage>` previews impact; `/rerun_confirm <stage>` executes restore+resume.
- **Issue 2 (Time Travel):** `_persist_snapshot` now writes to Supabase. `diff_snapshots` added to `supabase.py`. `/diff <a> <b>` Telegram command.
- **Issue 3 (Per-Stage File Delivery):** `_STAGE_ARTIFACTS_DELIVERY` map covers S1–S9; replaces the old 3-key stub.
- **Issue 4 (Deploy-less Delivery):** Credential pre-check in `s7_deploy_node` sets `skip_store_upload=True` and routes iOS/Android directly to `airlock_deliver` when `APPLE_ID` / `GOOGLE_PLAY_SERVICE_ACCOUNT` are absent.
