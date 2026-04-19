# v5.8.12 Phase 1 — Foundation Fixes Status

**Tag:** `v5.8.12-phase1-foundations`
**Baseline:** 619 tests (pre-phase1, tagged `pre-v5.8.12-phase1-20260417-2032`)
**Final:** 687 tests passing, 0 failing, 1 pre-existing async-warning

---

## Per-Issue Breakdown

### Issue 19 — Diagnostic Clarity (commit `b49568d8`)
- **New:** `factory/core/halt.py` (122 L) — `HaltCode` enum (no `UNKNOWN` member) + `HaltReason` dataclass with `format_for_telegram()`, `set_halt(state, reason)` helper.
- **Edited:** `factory/orchestrator.py` (+49 L) — outermost try/except attaches `UNCAUGHT_EXCEPTION` HaltReason with last 3 traceback lines; budget-exhausted / intake-blocked paths get typed HaltReasons; `halt_handler_node` renders struct when present, never shows the literal word "unknown".
- **Edited:** `factory/telegram/messages.py::format_halt_message` (+25 L) — prefers struct, sanitises legacy path.
- **Edited:** `factory/pipeline/s8_verify.py` (+35 L) — captures per-check failure detail (method, error, URL) and writes a `STAGE_VERIFICATION_FAILED` HaltReason on any failed check.
- **Edited:** `factory/telegram/bot.py` (3 sites) + `factory/pipeline/halt_handler.py` (1 site) — remove `"unknown"` defaults from halt-reason reads.
- **New tests:** `tests/test_no_unknown_halt.py` (6 tests) — enum guard, empty-detail rejection, regex-lint over `factory/` for hardcoded `halt_reason = "unknown"`, rendering guarantees for every `HaltCode`.

### Issue 14 — App Name Integrity (commit `0b0969bf`)
- **Edited:** `factory/pipeline/s0_intake.py` (+110 L) — priority-ordered `_APP_NAME_PATTERNS` (7 regexes, unicode-safe for ASCII / curly / Arabic quotes), `_validate_app_name()` with imperative-verb rejection + length bounds, `_extract_app_name_explicit()` including windowed fallback around the word "name". Authority order in `_extract_requirements`: pre-seeded metadata → explicit regex → validated AI → HALT with `APP_NAME_MISSING`. `_fallback_requirements` no longer fabricates a name.
- **Edited:** `factory/core/state.py` (+5 L) — adds `state.intake: dict` authoritative field.
- **Edited:** `factory/telegram/bot.py` (+40 L) — modification-verb guard (`change/update/modify/add/remove/fix/make/set/replace/rename`) redirects free-text to the modification path when an active project exists, replies with `/new` hint otherwise.
- **Edited:** `factory/pipeline/s2_blueprint.py` (1 L) — defensive `None`-safe read of `app_name` for stack metadata.
- **Updated tests:** `tests/test_prod_07_pipeline.py` (2) and `tests/test_e2e_scorecard.py` (1) — switched from asserting fabricated names to asserting the new halt-on-missing contract. `tests/conftest.py` fixture now seeds an explicit app name so the full-pipeline orchestrator test still exercises all 9 stages.
- **New tests:** `tests/test_app_name_extraction.py` (41 parametrised cases) — positive/negative extraction, validator edge cases, unicode round-trip, regression guard for `"Change platform to web"`.

### Issue 15 — Project ID Leak (commit `61ec6ab7`)
- **New helper:** `factory/telegram/messages.py::project_display_name(project_or_state) -> str` (+55 L) — prefers `state.intake["app_name"]` → `project_metadata["app_name"]` → `project["name"]` → `idea_name` → `Project <8-hex-suffix>`.
- **Edited call sites:**
  - `messages.py::format_status_message`, `format_cost_message`, `format_project_started` (3)
  - `ai_handler.py::_fallback_respond` (2 branches — status + cancel)
  - `bot.py`: `/new` active-project reply, `/cancel` reply, `/cancel` confirmed-action reply, `/snapshots` header, `/restore` prompts (two branches), restore callback prompts, MODIFY start / halt / complete / error (6 sites total in MODIFY path), `/modify` active-project guard (11 sites total)
- **New tests:** `tests/test_no_project_id_leak.py` (10 tests) — regex-lint over `factory/telegram/*.py` for `proj_id|project_id|state.project_id` interpolated into user-facing call sinks (`reply_text`, `send_telegram_message`, `edit_message_text`, `answer_callback_query`, `InlineKeyboardButton`), plus integration checks on formatters.
- **Updated tests:** `tests/test_prod_03_telegram.py::test_status_message` and `test_cost_message` — now assert app_name present AND raw id absent.

### Issue 22 — Platform / Stack Consent (commit `15c2c32a`) — FOUNDATION ONLY
- **New:** `factory/core/platform_targets.py` (60 L) — `PLATFORM_TARGET_MAP` and `resolve_deploy_targets()` that raises on empty or unknown platforms (never synthesises a default).
- **Edited:** `factory/pipeline/s0_intake.py::_select_platforms` — removed the `["ios","android"]` silent default; on empty selection sets a `PLATFORMS_NOT_SELECTED` HaltReason.
- **New tests:** `tests/test_platform_target_mapping.py` (11 tests) — explicit `web → no app_store/google_play` guard, merge de-duplication, order preservation, empty/unknown raises, desktop variants have no store targets.

---

## Test Counts
| Phase                                   | Tests | Pass | Fail |
|-----------------------------------------|-------|------|------|
| Baseline (pre-Phase-1)                  | 619   | 619  | 0    |
| After Issue 19                          | 625   | 625  | 0    |
| After Issue 14                          | 666   | 666  | 0    |
| After Issue 15                          | 676   | 676  | 0    |
| After Issue 22 (foundation)             | 687   | 687  | 0    |
| **Net +68 tests, 100% green**           |       |      |      |

All commits verified with `pytest tests/ -v` staying green between commits.

---

## Judgment Calls

1. **Issue 22 §3–§6 deferred to Phase 2.** The prompt asked for (§3) an `s7_deploy.py` audit removing App Store / Google Play paths when not selected, (§4) an S2 stack-confirmation copilot gate, (§5) a `format_stack_summary` rewrite removing the misleading "Wired (1)" count, and (§6) auto-deploy countdown suppression. Each of these touches the deploy flow and Stage-2 copilot gating, which overlaps materially with Issue 16 (concurrency/cancel) and Issue 17 (quality gates) — explicitly excluded from Phase 1. I landed the *foundation* (strict mapping + `PLATFORMS_NOT_SELECTED` halt) and left a `NOTE` in the Issue 22 commit body flagging the remaining scope. Call is made to respect the stated scope boundary rather than do a shallow partial sweep.

2. **Kept `"unknown"` in non-halt contexts.** `rg "unknown" factory/` returns ~45 hits; most are cosmetic defaults in log strings (e.g. `selected_stack.value if state.selected_stack else "unknown"` for analytics/logs), attachments (`a.get("type", "unknown")`), or `method="unknown"` in delivery-chain result dicts. Issue 19 specifically targets halt-reason strings; the lint test scopes there. Broader cleanup would be churn without user impact.

3. **MODIFY start message still shows repo name, not project_id.** Before the app name exists (S0 hasn't run), I render the GitHub repo last-segment as the identifier instead of `proj_<hex>` or a blank string. Matches the Issue 15 spirit ("never the raw id") without introducing a blocking name-prompt to the `/modify` flow.

4. **Halt on empty platforms is hard-stop in S0, not a re-prompt loop.** Could be softened to a second re-prompt, but the scope said "halt with PLATFORMS_NOT_SELECTED" — I followed that literally. Operator uses `/continue` after replying. If UX demands a re-prompt loop, that's a small follow-up.

---

## Observations Worse Than the Audit Suggested

1. **`_fallback_requirements` was fabricating names from *any three words* of the description.** Audit flagged the title-casing; actual behaviour took the first three alpha-run tokens and Title-Cased them — so `"A pulse tracker for athletes"` became `"A Pulse Tracker"`. Now returns `app_name=None`.
2. **bot.py had many more user-facing leaks than the three audit callouts.** 11 sites needed rewriting, not 3. The `/modify` flow alone had 6 interpolations of `project_id` into Telegram replies.
3. **S8 verify returned `"status": "unknown"` inside the check dict** — the audit pointed at line 252 which turned out to be `register_stage_node`. The real leak was in `_verify_mobile`'s final `else` branch. That path was returning `"unknown"` as the deployment status string, which would then render in status messages and halt-message summaries.

---

## Remaining Concerns (for Phase 2+)

- **Issue 16 (concurrency):** `/cancel` still doesn't set a pipeline_aborted flag the stages check; structured halt is now in place but stage-level cancel checks are not.
- **Issue 17 (quality gates):** Blueprint/Codegen still happily proceed with empty feature arrays.
- **Issue 18 (credentials):** `CREDENTIAL_MISSING` HaltCode reserved but not wired — preflight check remains.
- **Issue 22 remainder:** S7 deploy audit, S2 stack consent gate, stack summary rewrite, deploy-countdown suppression.
- **Mother Memory (Issue 21):** untouched per scope.
- **Legacy `halt_reason` reads** scattered across `factory/analytics`, `factory/war_room`, `factory/legal` still default to `"unknown"` for non-halt telemetry fields. These are not halt paths so the guard test passes, but renaming those defaults to something like `"unspecified"` would make log diving easier.
