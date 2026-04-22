# AI Factory Pipeline — Test Strategy (v5.8.15 Issue 49)

## Why this exists

Through v5.8.12 / v5.8.13 / v5.8.14 the test suite reported "911 passed" while
the live Telegram pipeline did nothing — `/continue` → "✅ resumed and completed"
with `$0.00` cost and zero new artifacts. Tests passed because `tests/conftest.py`
enforced *autouse global mocks* of every external integration, so no test ever
exercised a real provider, real Supabase row, or real Telegram message.

**Tests passing is NOT evidence that a feature works.** Only live Telegram
reproduction + real on-disk artifacts are evidence.

This document defines the three-tier test strategy that makes that rule
enforceable.

## The three tiers

| Marker | Scope | Autouse mocks | Gated by | CI role |
|---|---|---|---|---|
| `@pytest.mark.unit` | Single-function logic in isolation | All 6 applied (AI / Telegram / Supabase / Neo4j / build_chain / mother_memory) | — (always runs) | Every commit |
| `@pytest.mark.integration` | Real free-tier providers + real filesystem | **None** | `INTEGRATION_TEST_MODE=1` | Pre-tag |
| `@pytest.mark.e2e` | Full pipeline run via CLI or Telegram harness | **None** | `E2E_TEST_MODE=1` | Pre-release |

### Legacy compatibility

Tests with **no marker** are auto-tagged `unit` by `conftest.pytest_collection_modifyitems`.
A banner is printed on collection showing how many legacy tests still need an
explicit marker. This preserves backwards compatibility with the ~56 pre-v5.8.15
test files without requiring a bulk rewrite.

## Enforcement rules

### Rule 1 — Integration/e2e tests MUST NOT mock core integrations

`conftest.py` scans every integration/e2e test file at collection time. Any
`patch("factory.integrations....")`, `patch("factory.pipeline....")`,
`patch("factory.core.roles.call_ai")`, or `patch("factory.orchestrator")` causes
the test to be **skipped with an error** listing the violating line numbers.

Fix: either rewrite the test to exercise the real integration (preferred) or
re-tag it as `@pytest.mark.unit`.

### Rule 2 — Integration tests skip unless explicitly enabled

Without `INTEGRATION_TEST_MODE=1` in env, every `@pytest.mark.integration` test
is skipped. Missing env vars → the test never runs and never falsely passes.

E2E tests have the parallel gate `E2E_TEST_MODE=1`.

### Rule 3 — Stage success contract (Phase 2, Issue 50)

An integration test for stage `Sx` MUST assert, after the handler returns success:

```python
assert state.metrics.provider_calls_in_stage >= 1
assert state.metrics.artifacts_produced_in_stage >= 1
assert state.metrics.mm_writes_in_stage >= 1
```

These counters do not yet exist; they arrive in Phase 2. The scaffold at
`tests/integration/test_stage_success_contract.py` documents the shape and
will be wired once Phase 2 lands.

## CLI targets

```bash
make test-unit          # fast, mocked, default
make test-integration   # INTEGRATION_TEST_MODE=1 pytest -m integration
make test-e2e           # E2E_TEST_MODE=1 pytest -m e2e
make test-all           # everything
make test-collect       # show what pytest sees (with marker gate banner)
```

## Minimum env for integration tier

```bash
# at least one of:
GEMINI_API_KEY=...
GROQ_API_KEY=...
CEREBRAS_API_KEY=...
OPENROUTER_API_KEY=...
CLOUDFLARE_AI_TOKEN=...
GITHUB_MODELS_TOKEN=...

# required for scout:
TAVILY_API_KEY=...

# optional but recommended:
SUPABASE_URL=...
SUPABASE_KEY=...
NEO4J_URI=...
NEO4J_USER=...
NEO4J_PASSWORD=...
```

No Anthropic / Perplexity / OpenAI keys required (or wanted — BASIC mode is
free-tier only by design).

## Checklist before marking a feature "done"

1. Unit tests green (`make test-unit`).
2. New integration test written if the feature touches a provider / filesystem.
3. `INTEGRATION_TEST_MODE=1 make test-integration` green with real keys.
4. **Live Telegram reproduction** of the prior failing behavior, now passing,
   captured as a screenshot.
5. `ls -la ~/factory-projects/<slug>/` showing real artifacts on disk.

Only after all five is the feature eligible for a phase tag.
