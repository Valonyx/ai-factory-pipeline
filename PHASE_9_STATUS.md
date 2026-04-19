# v5.8.12 Phase 9 — Issue 7 Status

**Tag:** post-phase8
**Baseline:** 792 tests (post-Phase-8)
**Final:** 804 passed, 3 skipped (live-credential guards), 0 failing

---

## Issue 7 — Provider Independence (commit `f7ab2dbb`)

**What was missing:** Every `call_ai()` site hard-called through `_call_anthropic()`, which used the flat `AI_PROVIDERS` list and `ModeRouter` without consulting `ProviderIntelligence`. The capability matrix and role-specific chains existed but were never applied at call time.

**Files changed:**
- `factory/core/roles.py` — wired ProviderIntelligence into `_call_anthropic`
- `tests/test_issue7_provider_independence.py` — 12 new tests

### What `_call_anthropic` does now

1. **Before `ModeRouter.select()`:**
   ```python
   role_name  = contract.role.value.upper()
   mode_name  = master_mode.value.upper()
   role_chain = provider_intelligence.get_chain_for_role(role_name, mode_name)
   _ai_by_name = {p.name: p for p in AI_PROVIDERS}
   role_filtered = [_ai_by_name[n] for n in role_chain if n in _ai_by_name]
   providers_to_use = role_filtered or AI_PROVIDERS
   ```
   PI's priority order is preserved; unknown names are safely skipped; fall back to full list if PI chain is empty.

2. **Per-attempt timing + metrics:**
   ```python
   t0 = _time.monotonic()
   # ... call ...
   latency_ms = (_time.monotonic() - t0) * 1000
   provider_intelligence.record_call(provider_name, latency_ms, success=True|False)
   ```

3. **Quota exhaustion pre-switch:**
   ```python
   if is_quota_error(err):
       provider_intelligence.on_provider_exhausted(provider_name, reset_in or 86400)
   ```

4. **Log prefix changed** to `[PI/{role_name}/{mode_name}]` for traceability.

### New tests

| # | Test | Verifies |
|---|------|---------|
| 1 | `test_strategist_balanced_chain_has_fallbacks` | STRATEGIST BALANCED has anthropic + ≥3 providers |
| 2 | `test_engineer_basic_chain_no_paid_providers` | BASIC chain has only free-tier providers |
| 3 | `test_quick_fix_turbo_chain_has_anthropic_first` | TURBO QUICK_FIX starts with anthropic |
| 4 | `test_all_role_chains_satisfy_required_capability` | Full capability matrix coverage |
| 5 | `test_get_chain_for_role_unknown_role_returns_mock` | Unknown role doesn't raise |
| 6 | `test_select_provider_returns_first_available` | Baseline selection logic |
| 7 | `test_select_provider_skips_exhausted` | Exhausted providers are skipped |
| 8 | `test_record_call_success_updates_metrics` | success_count + avg_latency correct |
| 9 | `test_record_call_failure_increments_failure_count` | failure_count incremented |
| 10 | `test_preswitch_marks_exhausted_when_requests_below_10` | Pre-switch at <10 remaining |
| 11 | `test_call_anthropic_mock_env_returns_mock_response` | AI_PROVIDER=mock bypass intact |
| 12 | `test_call_anthropic_consults_provider_intelligence` | `get_chain_for_role` actually called |

---

## Test Counts

| Phase                        | Tests | Pass | Skip | Fail |
|------------------------------|-------|------|------|------|
| Baseline (post-Phase-8)      | 792   | 792  | 3    | 0    |
| After Phase 9                | 804   | 804  | 3    | 0    |
| **Net +12 tests, 100% green** |       |      |      |      |

---

## Remaining (Phase 10+)

- **Phase 10:** End-to-end integration fix loop — run a real pipeline from `/new` → S9 completion in dry-run mode and verify all stages complete cleanly.
- **Issue 22 remainder:** S7 deploy audit (remove App Store/Google Play paths when not in deploy targets), S2 stack confirmation gate, `format_stack_summary` rewrite, deploy-countdown suppression.
