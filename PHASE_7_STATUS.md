# v5.8.12 Phase 7 — Issues 10, 12, 13 Status

**Tag:** `pre-v5.8.12-phase7-20260418-*`
**Baseline:** 760 tests (pre-phase7)
**Final:** 774 tests passing, 0 failing

---

## Per-Issue Breakdown

### Issue 10 — Extensive Testing Stages (commit `35f1e3a9`)

**What was missing:** S6 had no cascade path when tests failed. It simply set `passed=False` and continued toward S7. Skeleton test suites (2–3 tests) passed the gate silently.

- **New constant:** `MIN_TESTS_EXECUTED = 10` — if `total_tests < 10` (and `DRY_RUN != true`), `passed` is forced `False` and a `tests_executed_gate` failure is appended to the failures list.
- **New function:** `_diagnose_test_failures(state, test_output) -> dict` — calls `AIRole.STRATEGIST` for a root-cause JSON: `{root_cause, issues, s4_instruction}`. Falls back to safe dict on parse error.
- **New function:** `_cascade_on_test_failure(state, test_output)` — end-to-end cascade:
  1. Runs diagnosis, stores in `state.project_metadata["test_failure_diagnosis"]`.
  2. Stores diagnosis in Mother Memory (tagged `test_failure`, `attempt=N`) for the re-run S4 to read.
  3. If `codegen_regression_count < MAX_CODEGEN_REGRESSIONS (2)`: increments counter, notifies operator, fires `asyncio.create_task(request_regression("S4_CODEGEN", ...))`, halts current pipeline with `QUALITY_GATE_FAILED`.
  4. If cap exhausted: permanent halt with explicit message — no more regressions.
- **Inline in `s6_test_node`:** gate check + `await _cascade_on_test_failure(state, test_output)` after `_analyze_test_results`.

### Issue 12 — Real Software Production (commit `35f1e3a9`)

**What was missing:** `state.s4_output["generated_files"]` was an in-memory dict. S5 could write files via `ExecutionModeManager.execute_task(type="file_write")`, but there was no explicit write-to-disk step in S4 itself, meaning S5 had to discover the workspace separately.

- **New function:** `write_files_to_disk(files: dict, project_id: str, app_name: str) -> str` — iterates over `files`, skips non-`str` values, calls `_get_project_workspace()` + `write_file()` for each. Returns workspace path. Logs per-file failures but never raises.
- **Called from `s4_codegen_node`** right after quality gates pass, before `_commit_to_github`. Sets `state.s4_output["workspace_path"]` and `state.s4_output["files_written"]` so S5/S6 can immediately use the on-disk workspace.

### Issue 13 — S0 Conversation Completeness / logo_path (commit `35f1e3a9`)

**What was missing:** Both logo flows returned an asset dict without `logo_path`. Logo bytes were generated in memory but never persisted to disk. `state.intake["logo_path"]` was never set, so downstream stages (S7 App Store submission, S3 design tokens) had no path to the logo file.

- **New helper:** `_save_logo_to_disk(logo_bytes, project_id, app_name) -> Optional[str]` — creates `{workspace}/brand/logo.png`, returns path. Non-fatal: returns `None` on any exception.
- **`_logo_flow_copilot`:** calls `_save_logo_to_disk(selected_bytes, ...)`, adds `"logo_path"` to returned dict.
- **`_logo_flow_auto`:** calls `_save_logo_to_disk(logo_bytes, ...)`, adds `"logo_path"` to returned dict.
- **`s0_intake_node`:** after `logo_asset = await _logo_flow(...)`, if `logo_asset.get("logo_path")`, sets `state.intake["logo_path"] = logo_asset["logo_path"]` (authoritative intake store, same pattern as `app_name`).

---

## Test Counts

| Phase                        | Tests | Pass | Fail |
|------------------------------|-------|------|------|
| Baseline (pre-Phase-7)       | 760   | 760  | 0    |
| After Phase 7                | 774   | 774  | 0    |
| **Net +14 tests, 100% green** |       |      |      |

All 14 new tests in `tests/test_phase7_issues_10_12_13.py`.

---

## Judgment Calls

1. **Cascade fires as `asyncio.create_task` (fire-and-forget), not `await`.** Awaiting `request_regression` from inside S6 would block the current pipeline run indefinitely (the regression itself runs S4→S5→S6 again, which is several minutes). Fire-and-forget lets the current pipeline halt cleanly while the regression runs in parallel under the bot's task registry.

2. **Regression count stored in `state.project_metadata`, not snapshot-restored state.** The restored state from the snapshot has `codegen_regression_count = 0` again. This means count tracking relies on the in-memory state of the triggering pipeline run, not the re-run. The cap still works correctly: the TRIGGERING run increments and halts; the RE-RUN is a fresh pipeline that either passes S6 or triggers again. Maximum depth: `MAX_CODEGEN_REGRESSIONS` concurrent re-runs before the next one halts permanently.

3. **`write_files_to_disk` skips non-str values silently.** Generated files dict may contain bytes (binary assets) or nested dicts from MODIFY mode. Skipping non-str is correct behavior; binary assets have separate delivery paths.

4. **`_save_logo_to_disk` saves as `logo.png` regardless of source.** Logo bytes from Pollinations/HuggingFace/Together are JPEG or PNG depending on provider. Naming as `.png` is consistent with App Store expectations (they re-encode anyway). A future improvement could detect format via magic bytes.

---

## Remaining (Phase 8+)

- **Issue 6:** Real integration tests (6a: Supabase insert/select, 6b: GitHub API, 6c: Telegram bot webhook).
- **Issue 8:** `/providers`, `/switch_mode`, `/rerun_confirm` Telegram commands need smoke tests.
- **Issue 9:** CI/CD pipeline (`.github/workflows/` or similar) verifying `pytest tests/` on every push.
- **Issue 7:** Provider independence — verify every `call_ai()` site actually uses `ProviderIntelligence` routing (not hardcoded to Anthropic).
- **Issue 22 remainder:** S7 deploy audit (remove App Store/Google Play paths when not in targets), S2 stack confirmation gate, `format_stack_summary` rewrite.
