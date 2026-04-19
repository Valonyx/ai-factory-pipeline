# AI Factory Pipeline v5.8.13 — Phase 0 Reality Report
**Audit Date:** 2026-04-19  
**Auditor:** Claude Code (claude-sonnet-4-6)  
**Audit Tag:** `pre-v5.8.13-audit-20260419`  
**Test Baseline:** 825 passed / 3 skipped (40.6 s)  
**Repo state:** clean, ahead of origin/main by 47 commits  

---

## 1. Three-Axis Mode Audit

The pipeline has **three distinct operational axes** but exposes them through an overloaded, partially ambiguous command surface.

### A. Master Mode (AI provider strategy)
| Field | Value |
|---|---|
| Options | BASIC / BALANCED / TURBO / CUSTOM |
| Where stored | `PipelineState.master_mode` (Supabase) + `operator_preferences.master_mode` |
| How set | `/mode basic\|balanced\|turbo\|custom` or shortcuts `/basic` `/balanced` `/turbo` `/custom` |
| How read | `state.master_mode` in `_call_anthropic` (roles.py:302-307) |
| Current default | `MasterMode.BALANCED` (`state.py:837`); operator preference default is `"balanced"` (bot.py:345) |
| **BUGS** | (1) Default is always BALANCED even when NO paid keys exist — should auto-detect and default to BASIC. (2) BASIC mode does NOT enforce $0.00 — hardcoded estimate shows `$0.05–$0.15` (bot.py:1716). (3) Anthropic is in BALANCED chain (ROLE_PROVIDERS["STRATEGIST"]["BALANCED"][0] = "anthropic") which will 402 immediately for a zero-credit operator. |

### B. Execution Mode (where pipeline runs)
| Field | Value |
|---|---|
| Options | CLOUD / LOCAL / HYBRID |
| Where stored | `PipelineState.execution_mode` (Supabase) + `operator_preferences.execution_mode` |
| How set | `/mode cloud\|local\|hybrid` — SAME command as Master Mode |
| How read | `ExecutionModeManager(state).execute_task(...)` in S4/S5/S6/S7/S8 |
| Current default | `ExecutionMode.CLOUD` (`state.py:836`); operator preference default `"cloud"` (bot.py:346) |
| **BUGS** | (1) Default is always CLOUD even when no GCP credentials exist — should auto-default to LOCAL. (2) No dedicated `/execution` command — overloaded through `/mode`. (3) In LOCAL mode, `_execute_local` tries a Cloudflare tunnel heartbeat (`localhost:8765`) — fails silently if no tunnel running, then auto-switches back to CLOUD (`execution.py:326-328`). This means "local" mode silently reverts to cloud on first task. (4) No startup auto-detection of missing cloud creds to set `execution=local`. |

### C. Transport Mode (Telegram delivery)
| Field | Value |
|---|---|
| Options | POLLING / WEBHOOK |
| Where stored | Not persisted — runtime state only in `run_bot.py` |
| How set | `/local` (webhook → polling) and `/online` (polling → webhook) |
| How read | `main.py:47-50` checks `IS_POLLING` env var; `run_bot.py` checks runner events |
| **BUGS** | (1) `/local` is named as if it means "run locally" but it only controls Telegram transport. A fresh operator reading `/help` would assume `/local` = run on their Mac. (2) No `/transport` command. The `/switch_mode` output does NOT mention transport mode at all. (3) `/mode` display (bot.py:357-358) shows both master and execution modes but no transport mode — the third axis is invisible to `/mode`. |

### Summary Table
| Axis | Command(s) | Separated? | Bugs |
|---|---|---|---|
| Master | `/mode basic\|balanced\|turbo\|custom` + aliases | ✅ | Wrong default, no $0 enforcement in BASIC |
| Execution | `/mode cloud\|local\|hybrid` | ❌ Shares `/mode` with Master | Wrong default, silent cloud-failover |
| Transport | `/local`, `/online` | ❌ Completely separate, confusingly named | `/local` name misleads; not shown in `/mode` display |

---

## 2. Role → Provider Resolution Table

### How Resolution Works (non-SCOUT)
1. `call_ai(role, prompt, state)` → `_call_anthropic(prompt, contract, state)` (roles.py:183)
2. Gets `role_chain = provider_intelligence.get_chain_for_role(role_name, mode_name)` (roles.py:323)
3. Filters by capability and by which providers exist in `AI_PROVIDERS` from mode_router.py
4. Creates `ModeRouter` + `QuotaTracker`, calls `router.select(role_filtered, ctx)`
5. On 402/quota: calls `provider_intelligence.on_provider_exhausted(provider_name)` AND `ai_chain.mark_quota_exhausted(provider_name)` (roles.py:410-411) ← **both updated correctly per call**
6. Cascades to next in `role_chain`

### SCOUT Exception
SCOUT **bypasses** all of the above. `call_ai(AIRole.SCOUT)` goes to `_call_perplexity_safe` (roles.py:181). This uses the old `scout_chain` ProviderChain from `provider_chain.py`, NOT `ROLE_PROVIDERS["SCOUT"]`. The `ROLE_PROVIDERS["SCOUT"]` table is only used in `/providers` display.

### Role Resolution Table (BASIC mode, no paid keys)

| Role | BASIC Chain (in ROLE_PROVIDERS) | Actual call path | Primary today | Exhaustion handler | Key-missing handler | 0-balance handler | Verdict |
|---|---|---|---|---|---|---|---|
| STRATEGIST | gemini→groq→nvidia_nim_mixtral→...→mock | `_call_anthropic` + provider_intelligence cascade | gemini (free_quality_rank=1) | ✅ cascades via roles.py:416 | ✅ provider skipped if key missing in `_call_single_ai_provider` | ✅ 402 caught at roles.py:408 | **CORRECT in BASIC** |
| ENGINEER | gemini→groq→nvidia_nim_mixtral→...→mock | same as STRATEGIST | gemini | ✅ | ✅ | ✅ | **CORRECT in BASIC** |
| QUICK_FIX | gemini→groq→nvidia_nim_gemma27b→...→mock | same | gemini | ✅ | ✅ | ✅ | **CORRECT in BASIC** |
| SCOUT | gemini→tavily→jina→perplexity→mock (table only) | `_call_perplexity_safe` → `scout_chain` | perplexity (top of scout_chain, regardless of mode) | ✅ via scout_chain | ⚠️ `PerplexityUnavailableError` raised then cascades to scout_chain next | ✅ | **WIRED-BUT-WRONG**: ROLE_PROVIDERS IGNORED; scout_chain always starts with perplexity |

### Role Resolution Table (BALANCED mode — live evidence matches)

| Role | BALANCED Chain | Primary today | Verdict |
|---|---|---|---|
| STRATEGIST | anthropic→kimi_k2→gemini→... | **anthropic** (but 402 exhausted) | **NOT-WIRED**: ProviderIntelligence._metrics["anthropic"].exhausted_until is reset on bot restart; bot.py shows "STRATEGIST → anthropic" even when ai_chain shows "quota — resets in 23h 59m" |
| ENGINEER | anthropic→gemini→... | anthropic | same stale-cache issue |
| QUICK_FIX | anthropic→gemini→... | anthropic | same |
| SCOUT | perplexity→gemini→... | perplexity | PERPLEXITY_API_KEY missing → error immediately |

### Root Cause of the Stale Provider Display
Two separate exhaustion-tracking systems that are **not synced at boot**:
1. `ProviderChain.statuses["anthropic"].quota_exhausted` (persisted in-memory per session; resets on bot restart)
2. `ProviderIntelligence._metrics["anthropic"].exhausted_until` (in-memory per session; resets on bot restart)

On bot restart, BOTH reset to "available". If anthropic was exhausted in the previous session, the bot will attempt anthropic again at S0, get a 402, THEN mark it exhausted (in both systems), then cascade to gemini. This is a 1–5s delay per role call (the 402 is fast), not a 14-min hang. The 14-min hang is caused by the SCOUT path (perplexity + possibly other providers without timeout) combined with no per-call timeout enforcement.

---

## 3. Observation → Root-Cause Map (A–T)

### A — `/providers` shows `STRATEGIST → anthropic` while anthropic is `quota — resets in 23h 59m`
**Root cause:** `provider_intelligence.status_message()` (provider_intelligence.py:260-261) calls `self.select_provider(role, "BALANCED")` which checks `ProviderIntelligence._metrics["anthropic"].is_available()`. On bot restart, `exhausted_until = None` so it returns True. The `ProviderChain.statuses["anthropic"].quota_exhausted = True` is stored in `ai_chain` (a separate object) and is NOT synced into `provider_intelligence._metrics` at startup.  
**File:line:** `provider_intelligence.py:209-215` (select_provider); `provider_chain.py:129-131` (ai_chain.mark_quota_exhausted); no sync call between them.

### B — All providers show `sr=100% lat=9999ms`
**Root cause:** `ProviderMetrics.avg_latency_ms` returns `9999.0` when `success_count == 0` (provider_intelligence.py:153). `success_rate` returns `1.0` when `total == 0` (line 158). There are NO scheduled health probes — metrics only update on actual pipeline AI calls. On a fresh boot with no pipeline run, all providers show the defaults.  
**File:line:** `provider_intelligence.py:150-158`

### C — `neo4j: offline (0 errors) (2 pending)` — writes stuck
**Root cause:** `MemoryChain._pending_writes` queues writes for offline backends (memory_chain.py) but there is no `promote_primary()` or auto-election code. The chain always reads from backends in fixed priority order (Neo4j first). If Neo4j is offline, reads fall through to Supabase, but the "primary" label in `status_report()` always assigns to the first available backend from the fixed list — there is no actual promotion logic.  
**File:line:** `memory_chain.py:16-17` (design intent says promotion; not implemented); `mother_memory.py:503-508` (status call shows offline without promotion)

### D — `/local` switches Telegram transport, not execution mode
**Root cause:** `cmd_local` (bot.py:957-988) calls `deleteWebhook` on the Telegram API, switching the bot from webhook to polling mode. This is **transport**, not execution. The function is correctly implemented for its purpose but the name `/local` implies execution mode.  
**File:line:** `bot.py:957-988`

### E — `/switch_mode` overloads `/mode` for both master and execution mode
**Root cause:** `cmd_switch_mode` is an alias for `cmd_mode` (bot.py:363-365). `cmd_mode` displays both `"*Or:* /mode basic | balanced | turbo | custom"` AND `"*Execution:* /mode cloud | local | hybrid"` in the same block (bot.py:357-358). No third transport axis is shown.  
**File:line:** `bot.py:348-358`

### F — User types "Execution: local" → hardcoded "I'm a cloud-based AI service..."
**Root cause — NOT FOUND in current code.** The `_fallback_respond` function (ai_handler.py:479-510) does NOT contain this string. The main `ai_respond` routes through Gemini or the free chain. If Gemini were to say "I'm a cloud-based AI service" that would be a model hallucination. Most likely scenario: this was from an older version's `_fallback_respond` that has since been replaced. The current fallback is reasonable.  
**File:line:** `ai_handler.py:479-510` (current fallback is fine); VERDICT: **COSMETIC/HISTORICAL** — may reappear if all AI providers fail AND `_fallback_respond` doesn't cover the "local mode" intent.

### G — Ghost cancel: `/cancel` → `/new` → immediate PIPELINE_CANCELLED
**Root cause:** Race condition between `CancelledError` handler write and new project's first write. Flow:
1. `/cancel` → `cancel_project_task(project_id)` (signals asyncio task cancellation) + `archive_project(project_id)` (removes from Supabase active_projects) + `_active_pipelines.pop(user_id)` (bot.py:760-762)
2. Background task receives `CancelledError`, sets `state.pipeline_aborted = True`, tries to call `send_telegram_message` and `upsert_pipeline_state` (orchestrator.py:562-587)
3. `/new` is sent; new fresh `PipelineState(pipeline_aborted=False)` is created; `update_project_state(new_state)` is written to Supabase `active_projects` keyed on `operator_id`
4. The old CancelledError handler's `upsert_pipeline_state` writes the OLD state (with `pipeline_aborted=True`) keyed on OLD `project_id` — this goes to `pipeline_states` table, not `active_projects`. **THIS IS NOT THE ROOT CAUSE of the ghost cancel.**
5. **ACTUAL ROOT CAUSE:** `_sb_upsert_active` in supabase.py upserts on `operator_id`. When `/cancel` fires, `archive_project` calls `_sb_archive` which deletes the operator_id row. But the `orchestrator.CancelledError` handler may ALSO call `update_project_state` → `_sb_upsert_active` **after** the archive, RE-CREATING the active_projects row with `pipeline_aborted=True` and the OLD project_id. Then `/new` reads `get_active_project(operator_id)` and finds this ghost row, thinks there's an active project, sends the "already has active project" message or starts the new pipeline with the old aborted state injected.

**File:line:** `orchestrator.py:562-587` (CancelledError handler); `bot.py:199` (`archive_project` signature mismatch — takes only `project_id` but `_sb_archive` needs `state`); `supabase.py:447-459` (`_sb_archive` deletes active row, but orchestrator's CancelledError writes it back)

### H — "ITo-do" parsing artifact
**Root cause — NOT CONFIRMED via static analysis.** The echo path:
- `raw_text = update.message.text.strip()` (bot.py:1458)
- `text = _sanitize(raw_text)` — only strips null bytes and caps at 2000 chars (ai_handler.py:166-169)
- `_handle_start_project_intent(update, user_id, text)` echoes `desc_preview = text[:400]` (bot.py:1722-1724)

There is NO `text[1:]` in this path. The spec hypothesis of `text[1:]` is **not confirmed**. Most likely cause: mobile autocorrect added "I " to the start of the operator's message, and the bot faithfully echoed it. Alternatively, the old ProviderChain (pre-v5.8.12) may have had a path where the AI response was injected into the echo. Current code does not exhibit this bug.  
**Verdict: CANNOT REPRODUCE / HISTORICAL or USER-INPUT ARTIFACT**

### I — Pipeline stuck at S0_INTAKE for 14+ minutes
**Root cause:** Three contributing issues:
1. `call_ai(AIRole.SCOUT)` → `_call_perplexity_safe` → `scout_orchestrator._run_scouts()` attempts Perplexity first. `PERPLEXITY_API_KEY` is not set → `PerplexityUnavailableError` raised. This cascades to Brave (also likely no key) → Tavily (has key? may work) → Exa → SearXNG → DDG → Wikipedia → HackerNews → Reddit → StackOverflow → GitHub → ai_scout (uses Gemini or free AI). Each provider attempt has no hard timeout in `scout_orchestrator.py`.
2. `_call_anthropic` for STRATEGIST/ENGINEER/QUICK_FIX may also attempt Anthropic (402) before cascading to Gemini. The 402 from Anthropic is fast (< 1s) but if all providers fail with network errors (no hard timeout), it can hang.
3. **No per-call timeout** exists in `_call_single_ai_provider` or `_call_perplexity_safe`. A hanging network call blocks the entire asyncio pipeline task.  
**File:line:** `roles.py:181` (SCOUT → perplexity_safe, bypasses timeout logic); `scout_orchestrator.py:376-394` (no timeout on individual scout calls)

### J — Pipeline silently forgotten after 14+ minutes
**Root cause:** `_run_and_notify` (bot.py:2045-2096) has a `finally` block that calls `_active_pipelines.pop(user_id, None)`. If `run_pipeline` raises an unhandled exception OR completes with `Stage.HALTED`, the finally runs. For `/status` to return "No active project", the Supabase `active_projects` row must also be gone. This happens if the `archive_project` from a prior `/cancel` already deleted it, AND the `update_project_state` in `_run_and_notify`'s exception handler failed (e.g., Supabase timeout). With only in-memory fallback remaining, a bot restart loses all in-memory state.  
**File:line:** `bot.py:2077-2096` (exception handler + finally); `bot.py:169` (in-memory fallback dict lost on restart)

### K — `/new` pre-name phase shows `Project 26078009`
**Root cause:** When `/cancel` + `/new` triggers the existing-project check, the display of the prior project uses `project_display_name(active)` which shows the name from the project's `state_json.idea_name` or metadata. If the project never got past S0_INTAKE (name not extracted yet), `idea_name` is None and `project_display_name` falls through to a numeric fallback or Telegram user ID.  
**File:line:** `telegram/messages.py:project_display_name()` function; `state.py:idea_name` field not set before S0 completes name extraction

### L — Snapshot counter stays at #0
**Root cause:** `_persist_snapshot` (orchestrator.py:303-312) is called inside `_notify_stage_complete`. `_notify_stage_complete` is only called AFTER a stage completes (line 471). If the pipeline is stuck inside S0_INTAKE (never completing it), `_persist_snapshot` is never called. Snapshot #0 means no stage has completed since the pipeline started.  
**File:line:** `orchestrator.py:303-312` + `orchestrator.py:471`

### M — Voice providers (ElevenLabs, Deepgram, AssemblyAI) appear in general `/providers` list
**Root cause:** `provider_intelligence.status_message()` (provider_intelligence.py:263-270) iterates `PROVIDER_CAPABILITIES.items()` which includes ALL providers regardless of capability type. The display shows `elevenlabs`, `deepgram`, `assemblyai` with `sr=100% lat=9999ms`.  
**File:line:** `provider_intelligence.py:263-270`; these providers ARE correctly absent from `AI_PROVIDERS` and `SCOUT_PROVIDERS` in mode_router.py — they won't be called for chat/scout roles.  
**Verdict: COSMETIC** — not a routing bug, just confusing display.

### N — Cost estimate shows `$0.05–$0.15` even in BASIC/free-only mode
**Root cause:** Hardcoded string `estimated_cost = "$0.05–$0.15 (Gemini free tier, no charge)"` (bot.py:1716). This value is never computed from the active master mode.  
**File:line:** `bot.py:1716`

### O — "Provider Status" block shows stale STRATEGIST/ENGINEER/QUICK_FIX → anthropic even when anthropic is exhausted
**Root cause:** Same as A. On bot restart, `ProviderIntelligence._metrics` is freshly initialized with all providers as available. The `ai_chain` ProviderChain may correctly show anthropic as "quota — resets in 23h 59m" (if that status was persisted to Supabase's `provider_chain_state` table — it isn't, it's in-memory too). Both systems reset on restart. On first actual call, the 402 from Anthropic will mark it exhausted in both systems within ~1s. The display is stale only between restart and first actual Anthropic call.  
**File:line:** `provider_intelligence.py:191-195` (fresh metrics on init); `provider_chain.py:179` (fresh ai_chain on import)

### P — Mother Memory: neo4j offline, mirrors not promoted to primary
**Root cause:** `MemoryChain` (memory_chain.py) has fan-out writes but no primary election. `status_report()` in `memory_chain.py` marks the first *available* backend as "ACTIVE (read-primary)" in `get_memory_chain_status()` (mother_memory.py:503-508). But the pending queue (`_pending_writes["neo4j"]`) for the offline primary is never drained to the new effective primary. The pending write count is tracked but there's no drain-on-promotion logic.  
**File:line:** `memory_chain.py` — no `promote_primary()` function exists; pending writes stay in `_pending_writes["neo4j"]` forever if neo4j stays offline.

### Q — No $0 enforcement in BASIC mode
**Root cause:** `ModeRouter._filter_available()` (mode_router.py:451-462) checks `if self.mode == MasterMode.BASIC and not p.is_free: continue`. This correctly filters out paid providers. BUT:
1. The cost estimate message is hardcoded `"$0.05–$0.15"` regardless of mode (bot.py:1716)
2. Gemini in `AI_PROVIDERS` has `cost_per_1k_tokens=0.0001` (mode_router.py:572) — not zero — so `_within_budget` could theoretically trigger budget checks even in BASIC mode
3. No `BASIC_MODE_COST_VIOLATION` halt code if a provider accidentally incurs a charge  
**File:line:** `mode_router.py:451-453` (correct filter); `bot.py:1716` (wrong estimate); `mode_router.py:570-572` (gemini cost > 0)

### R — No S0 conversational flow
**Root cause:** `s0_intake_node` (s0_intake.py:55-131) processes `raw_input` from `state.project_metadata["raw_input"]` in a single pass. There is no multi-turn state machine in S0. The bot's `cmd_new_project` (bot.py:245-268) prompts for description if no args given, then shows a confirmation screen, asks for app name via `_ask_app_name`, but skips platforms, markets, and logo as a conversational flow. These are handled later in the pipeline stage (S0 step 2-6 in s0_intake.py), not interactively before pipeline start.  
**File:line:** `bot.py:245-268` + `s0_intake.py:55-131`

### S — No `/execution` or `/transport` command
**Root cause:** Only `/mode cloud|local|hybrid` (via `cmd_mode`) exists for execution. Transport is set via `/local` and `/online`. There is no `/execution` or `/transport` command. Verified at `bot.py:2216-2265` (handler registration).  
**File:line:** `bot.py:2221-2263` (command registry)

### T — `/mode cloud|local|hybrid` documented but pipeline stays on cloud
**Root cause:** `/mode local` correctly sets `state.execution_mode = ExecutionMode.LOCAL` (bot.py:328). BUT `ExecutionModeManager._execute_local` (execution.py:238-254) calls `HeartbeatMonitor.ping()` which tries `localhost:8765` (the Cloudflare tunnel). If that fails, `local_heartbeat_alive` is set False after 3 failures (90s), and `execute_task` (execution.py:186-191) checks `if not self.state.local_heartbeat_alive: await self._notify_failover(...)` which silently switches back to CLOUD. Operator sees "mode = local" in `/mode` but actual execution goes through cloud path.  
**File:line:** `execution.py:186-191` (silent cloud failover); `execution.py:314-332` (heartbeat logic)

---

## 4. Missing-Credential / No-Cloud Operator Viability Matrix

| Dependency | Purpose | Free/Local Alternative | Default if Missing | Halt-or-Substitute |
|---|---|---|---|---|
| `ANTHROPIC_API_KEY` | STRATEGIST/ENGINEER/QUICK_FIX | Gemini (free), Groq, OpenRouter, etc. | Cascades to free chain | Substitute (cascade) |
| `GOOGLE_AI_API_KEY` | Gemini free-tier | Groq, NVIDIA NIM, Cerebras | Falls through to next free | Substitute |
| `PERPLEXITY_API_KEY` | Scout research | DuckDuckGo, Wikipedia, Tavily, etc. | `PerplexityUnavailableError` then cascades | Substitute (cascade) |
| `SUPABASE_URL` + `SUPABASE_KEY` | State persistence | In-memory dict (`_active_projects_fallback`) | In-memory fallback (lost on restart) | **Partial** — loses state on restart |
| `NEO4J_URI` + creds | Mother Memory primary | Supabase → Upstash → Turso → in-memory | MemoryChain routes to next backend | Substitute |
| `GCP credentials` / `GOOGLE_APPLICATION_CREDENTIALS` | Cloud Run, Cloud Build | Local execution + local workspace | `execution_mode` defaults to CLOUD but no creds = CI fails silently | **No alt** — cloud builds fail |
| `GITHUB_TOKEN` | Code push, CI dispatch | Local git operations | GitHub push fails, CI not dispatched | Partial |
| `TELEGRAM_BOT_TOKEN` | Bot operation | N/A | Bot won't start | **Hard dependency** |
| `TELEGRAM_OPERATOR_ID` | Operator auth | N/A | All messages blocked | **Hard dependency** |
| `CLOUDFLARE_TUNNEL_TOKEN` | Local webhook exposure | Polling mode | Polling works without it | Substitute |

**Critical viability judgment:** A no-budget KSA operator with `TELEGRAM_BOT_TOKEN`, `TELEGRAM_OPERATOR_ID`, and `GOOGLE_AI_API_KEY` (free Gemini) can run the pipeline end-to-end in BASIC mode with polling transport — BUT ONLY IF `execution_mode` is explicitly set to LOCAL (no auto-detection) and the Supabase fallback is accepted (state lost on restart). The pipeline will attempt Anthropic on first run (BALANCED default), get a 402, cascade to Gemini, and proceed. The 14-min hang is from the SCOUT role not having Perplexity key and hanging on scout_orchestrator with no timeout.

---

## 5. Mother Memory Chain Fan-Out State

**Why neo4j: offline (0 errors) (2 pending)?**
- `MemoryChain._pending_writes["neo4j"] = [(op, record), (op, record)]` — two writes queued
- `BackendStatus.consecutive_errors = 0` — no errors recorded (neo4j went offline before any write was attempted, not after failure)
- The "offline" status likely comes from `neo4j_backend.initialize()` returning `available=False` due to missing `NEO4J_URI`/password credentials

**Why aren't mirrors promoted to primary?**
- `status_report()` in `memory_chain.py` iterates `_backends` in order and marks the first AVAILABLE one as "ACTIVE (read-primary)". This IS promotion in the display sense.
- BUT: the `_pending_writes["neo4j"]` queue is never drained to the newly-active primary.
- `sync_backend()` exists in the design comment (memory_chain.py:27-30) but is not called when a backend goes offline → comes back online.
- The pending queue drains ONLY if neo4j comes back online and `_sync_on_restore` is called (which happens in the quota-reset checker, not the connectivity-restore path).

**Recommended fix:** On every write, for each offline backend, attempt to drain its `_pending_writes` queue into the current read-primary backend simultaneously. This is the "fan-out" that's designed but not fully implemented.

---

## 6. Provider Health Probe Audit

**Why `sr=100% lat=9999ms` everywhere?**

`ProviderMetrics` (provider_intelligence.py:141-175):
```python
@property
def avg_latency_ms(self) -> float:
    if self.success_count == 0:
        return 9999.0   # ← default when never called

@property
def success_rate(self) -> float:
    total = self.success_count + self.failure_count
    return self.success_count / total if total > 0 else 1.0  # ← 100% when never called
```

There are **no scheduled health probes**. `provider_intelligence.start_upgrade_poller()` (called from bot.py) only checks `exhausted_until` expiry — it does NOT actually probe the provider. A real probe (e.g., a cheap `/models` or 1-token call) is never made.

**Current probe budget:** 0 (no probes scheduled)  
**Required:** A 5-min background task per provider that does a cheap non-destructive request and records `record_call(provider, latency_ms, success=bool)`.

---

## 7. Conversational AI Path Audit

### Hardcoded Strings That Should Route Through AI

| Location | Hardcoded String | Should be... |
|---|---|---|
| `bot.py:1716` | `"$0.05–$0.15 (Gemini free tier, no charge)"` | Computed from active master mode |
| `bot.py:1726` | `"Reply 'yes' to start, or anything else to cancel."` | OK (UX instruction, not AI content) |
| `ai_handler.py:371` | `"Pipeline assistant is in test mode. No AI provider is active."` | Mock response (OK for test) |
| `ai_handler.py:442` | `"Sorry, I couldn't generate a response."` | Fallback when ALL providers fail (OK) |
| `bot.py:983` | `"🏠 Switched to LOCAL polling mode.\nRun python scripts/run_bot.py..."` | OK (transport command confirmation) |

**Verdict:** The "I'm a cloud-based AI service" string from the spec's evidence is **NOT in the current code**. The current fallback at `ai_handler.py:479-510` is reasonable keyword-based routing. No hardcoded AI-content strings found.

### Free-form message routing today
1. `handle_message` (bot.py:1440+)
2. Operator state intercepts (awaiting_project_description, awaiting_app_name, etc.)
3. Confirmation intercept (pending "yes/no")
4. Modification verb guard (change/update/modify → routes to modification handler)
5. `classify_intent(text)` → Gemini via `_call_ai_for_bot` (ai_handler.py:230-241)
6. Intent routing: `start_project` → `_handle_start_project_intent`; `check_status` / `cancel_project` / `ask_question` / `casual_chat` / `unclear` → `ai_respond(user_id, text, active, intent)` → Gemini via full context prompt

**AI routing IS wired.** The issue is that classify_intent and ai_respond use the `ai_chain` ProviderChain (bot's own older chain), NOT the role-aware `provider_intelligence` + `ROLE_PROVIDERS` system. So `/mode basic` does NOT affect the bot's conversational AI calls.

---

## 8. Project Persistence Audit

### Where state lives
1. **Primary:** Supabase `active_projects` table (keyed on `operator_id`) via `upsert_active_project`
2. **In-memory fallback:** `_active_projects_fallback` dict in `bot.py` (lost on restart)
3. **Snapshots:** Supabase `pipeline_states` table via `upsert_pipeline_state` (written on stage completion via `_persist_snapshot`)

### Why `/status` loses project after 14 min
1. Pipeline stuck in S0 → no `_persist_snapshot` called → Supabase `pipeline_states` has no snapshots (snapshot #0)
2. The `update_project_state` at pipeline START writes to Supabase active_projects (should be there)
3. **Most likely cause:** If Supabase is unreachable at start, `_sb_upsert_active` fails, falls through to in-memory `_active_projects_fallback`. After 14 min, if the pipeline task dies (exception), the `finally` block calls `_active_pipelines.pop(user_id, None)`. The `_active_projects_fallback[user_id]` is NOT cleared by the finally block — but `get_active_project` checks Supabase FIRST. If Supabase returns None (never wrote), it checks `_active_projects_fallback`. If the exception cleaned up the fallback... 
4. **Alternative cause:** The `_run_and_notify` exception handler sends a Telegram message but does NOT call `update_project_state` with the current (stuck) state. If the pipeline times out silently, the Supabase row shows the initial state (S0_INTAKE) but `get_active_project` in a subsequent `/status` might show the right row — UNLESS the prior `/cancel` archived it.

**Verdict:** Project loss after 14 min is consistent with: (1) Supabase `active_projects` was correctly written at start, (2) a prior `/cancel` archived it, (3) the CancelledError handler wrote back pipeline_aborted=True to active_projects (the ghost cancel bug), (4) a subsequent `/cancel` + `/new` flow archived that, leaving no active row.

### Restart rehydration
**NOT IMPLEMENTED.** On bot restart, `_active_projects_fallback` is empty. If Supabase has an `active_projects` row for the operator, `get_active_project(user_id)` will find it on the next `/status` call. BUT there is no boot-time rehydration that:
- Queries Supabase for all `RUNNING` projects
- Resumes their pipeline tasks

---

## 9. Ghost-Cancel Bug Root Cause

**Exact sequence:**
1. Operator starts project A (project_id = `proj_abc123`) → writes `active_projects[operator_id]` row with `state_json.pipeline_aborted=False`
2. Pipeline runs in `_run_and_notify` background task
3. Operator sends `/cancel` → `cancel_project_task("proj_abc123")` cancels the asyncio task → `archive_project("proj_abc123")` deletes `active_projects[operator_id]` row from Supabase → `_active_pipelines.pop(user_id)` removes guard
4. Background task receives `asyncio.CancelledError` in `run_pipeline` → sets `state.pipeline_aborted=True` → tries `send_telegram_message(...)` (may succeed) → returns `state`
5. `_run_and_notify` `finally` runs: `_active_pipelines.pop(user_id, None)` (already gone, no-op)
6. **BUT:** `orchestrator.py CancelledError handler` also calls `update_project_state(state)` via... wait, actually it doesn't. The CancelledError returns `state` which then goes back to `_run_and_notify`.
7. Actually `_run_and_notify: final = await run_pipeline(state)` — if `run_pipeline` raises CancelledError, that propagates UP to `_run_and_notify`'s `except Exception as e:` block (CancelledError is not an Exception in Python 3.8+!). **In Python 3.8+, `asyncio.CancelledError` is a subclass of `BaseException`, NOT `Exception`.** So the `except Exception` in `_run_and_notify` does NOT catch it. The `finally` block still runs.
8. Operator sends `/new` → no active project check passes → creates `proj_def456` → `_start_project` → `update_project_state(new_state)` writes to Supabase
9. **GHOST:** The CancelledError propagates UP out of `_run_and_notify` as an unhandled BaseException... except it's in an asyncio Task, so it's captured by the Task. The Task stores the exception. If the old `state` object (with `pipeline_aborted=True`) was already passed to `update_project_state` INSIDE the CancelledError handler at orchestrator.py:562-587, THEN `upsert_pipeline_state(state.project_id, state)` writes the old pipeline_aborted state... but to `pipeline_states` table keyed by `project_id`, NOT `active_projects` keyed by `operator_id`. This shouldn't cause the ghost cancel.

**Revised root cause:** Looking at `archive_project` (bot.py:199-229): it iterates `_active_projects_fallback` to find the state, calls `_sb_archive(project_id, state)`, pops from fallback, calls `cancel_project_task`. BUT if the state is in Supabase and NOT in fallback (initial write succeeded), `archive_project` goes to the else branch (bot.py:215-229) which reads from Supabase and calls `_sb_archive`. **`_sb_archive` in supabase.py:425-459 does the `active_projects.delete().eq("operator_id", ...)` BEFORE inserting into `archived_projects`**. If the subsequent `/new` `_start_project` runs and writes `_active_projects_fallback[user_id]` (because Supabase write failed or was delayed), and then the pipeline task's `_run_and_notify finally` pops it... 

**Most parsimonious root cause:** The `cmd_cancel` handler (bot.py:750-765) calls `archive_project(project_id)` which only removes from active_projects/fallback. It does NOT call `state.pipeline_aborted = True` directly on the in-memory `state` object that the running pipeline holds. The running pipeline continues briefly after `CancelledError`, and its `CancelledError` handler in orchestrator writes `pipeline_aborted=True` + `HaltReason(PIPELINE_CANCELLED)` into state, THEN `_start_project`'s `update_project_state(new_state)` creates a FRESH state with `pipeline_aborted=False`. The ghost only appears if the operator submits `/new` + `yes` confirmation so fast that `_active_pipelines` guard is bypassed — but that's guarded by `_active_pipelines` which is cleared in `finally`.

**Conclusion:** The ghost cancel OBSERVED IN THE WILD is most likely from a **timing window** where `_active_pipelines.pop(user_id)` in `/cancel` (bot.py:762) runs, clearing the duplicate-launch guard, but the old pipeline task's `CancelledError` handler hasn't finished yet. The new `/new` → `_start_project` creates a new project, but the old task is still running (briefly) and may overwrite the `active_projects` row if it calls `update_project_state`. This is a real race.

**File:line:** `bot.py:750-765` (cancel handler); `orchestrator.py:562-587` (CancelledError + state writes)

---

## 10. Intake Parsing Artifact ("ITo-do" Bug)

**Static analysis finds NO `text[1:]` in the echo path.**

The echo at `bot.py:1722-1727`:
```python
desc_preview = description if len(description) <= 400 else description[:397] + "..."
await update.message.reply_text(
    f"Got it — building:\n\"{desc_preview}\"\n\n"
    ...
)
```

`description = text = _sanitize(raw_text)` where `_sanitize` only strips null bytes and caps at 2000 chars.

**Most likely cause:** The operator typed "I" (possibly mobile autocorrect adding the first-person pronoun) at the start of the description. The bot echoed it faithfully, which is correct behavior. Alternatively: the `has_pending_reply(user_id)` check or some prior operator state injected "I" into the text — but no evidence of this in the code.

**Recommendation:** Add a unit test: confirm that an intake description starting with "T" echoes starting with "T", not "I". This will catch any regression. The ITo-do artifact appears to be either historical or a user-input artifact, not a current code bug.

**File:line:** No confirmed bug in current code.

---

## 11. S0 Flow Gap — Current vs Required

### Current S0 Flow
```
User sends /new → (no description): prompt "Describe your app"
User sends description → classify_intent → "start_project" → _handle_start_project_intent
  → shows "Got it — building..." + hardcoded cost estimate + "Reply 'yes'"
User sends "yes" → _execute_confirmed_action → _ask_app_name
  → tries regex extraction; if explicit name found, auto-proceeds
  → if no name: sets "awaiting_app_name" state, prompts "What should we call this?"
User sends name → _start_project(description, app_name) → PipelineState created
  → run_pipeline starts → S0 INTAKE STAGE processes platforms, markets, logo internally
  (no more user interaction until halt or completion)
```

### Required S0 Flow (Issue 28)
```
Step 1: Multi-modal description (text/photo/voice)
Step 2: Name confirmation with validation + /skip for AI suggestions
Step 3: Platforms multi-select (12 options)
Step 4: Target markets (4 preset + custom)
Step 5: Logo flow (upload / describe / recommend / skip)
Step 6: Final summary + /go or /edit <field>
```

### Gap Analysis
| Required Step | Current Status | Missing |
|---|---|---|
| Step 1 (description) | ✅ exists (awaiting_project_description) | Multi-modal (voice/docs) not wired in bot handler |
| Step 2 (name confirm) | ✅ `_ask_app_name` flow exists with validation | `/skip` works; validation patterns exist |
| Step 3 (platforms) | ❌ NOT in bot flow — handled in S0 pipeline stage internally | Full multi-select menu + state storage |
| Step 4 (markets) | ❌ NOT in bot flow — hardcoded default KSA in S0 stage | Market selection menu |
| Step 5 (logo) | ⚠️ PARTIAL: `/update_logo` command exists; `_logo_flow_auto` in S0 | Interactive 4-option menu in bot flow |
| Step 6 (summary + /go) | ❌ NOT implemented — pipeline starts immediately after name | Summary card + /edit <field> controls |

---

## 12. v5.8.12 Issues (1–22) Carry-Forward Verdicts

| Issue | Title | Status | Evidence |
|---|---|---|---|
| 1 | /rerun + StageRegressionEngine | COMPLETE | `test_phase6_regression_timetravel.py` + `/rerun` handler registered |
| 2 | Time travel (/snapshots, /restore, /diff) | COMPLETE | `_persist_snapshot` called; handlers registered; but snapshot #0 bug (Issue L above) |
| 3 | Per-stage artifact delivery | COMPLETE | `_STAGE_ARTIFACTS_DELIVERY` map in orchestrator.py |
| 4 | S7 deploy-less precheck | COMPLETE | `skip_store_upload` flag wired |
| 5 | Chain context injection S7/S8 | COMPLETE | `inject_chain_context` called in s7/s8/s4 |
| 6 | Real provider integrations | COMPLETE | 34+ providers wired; tests pass |
| 7 | ProviderIntelligence wired into _call_anthropic | COMPLETE | roles.py:315-437 |
| 8 | Bot commands test coverage | COMPLETE | test_issue8_bot_commands.py |
| 9 | Concurrency + duplicate pipeline prevention | COMPLETE | `_active_pipelines` guard; test_concurrency.py 15 tests |
| 10 | Phase E2E test | COMPLETE | test_phase10_e2e_pipeline.py |
| 11 | store_stage_insight in all stages | COMPLETE | wired in S2-S8 |
| 12 | Stage-specific prompts | COMPLETE | prompts.py |
| 13 | Logo path persistence | COMPLETE | state.intake["logo_path"] wired |
| 14 | App-name integrity + halt on missing | COMPLETE | explicit extractor + halt code APP_NAME_MISSING |
| 15 | No proj_<hex> leaks | COMPLETE | `project_display_name()` helper |
| 16 | Orphan task sweeper + CancelledError | COMPLETE | `_orphan_task_sweeper` + cancel handling |
| 17 | Quality gates | COMPLETE | test_quality_gates.py 13 tests |
| 18 | Credentials registry + pre-flight | COMPLETE | test_credentials.py 6 tests |
| 19 | Legal compliance gate | COMPLETE | wired |
| 20 | ProviderIntelligence + /providers | PARTIAL | Display shows stale anthropic; health probes missing (Bug B, A, O) |
| 21 | Mother Memory retrieval | COMPLETE | test_mother_memory_retrieval.py 11 tests; but Neo4j offline (Bug C, P) |
| 22 | S7 audit + stack summary | COMPLETE | test_issue22_deploy_audit.py |

---

## Summary: P1 Issues for Phase 1+

| Priority | Issue | Root Cause File | Impact |
|---|---|---|---|
| P1-BLOCKER | SCOUT always hits Perplexity first (no key) then hangs | `roles.py:181`, `scout_orchestrator.py` (no timeout) | 14-min stall |
| P1-BLOCKER | No per-call timeout on ANY provider | `_call_single_ai_provider`, `scout_orchestrator` | Silent hang |
| P1-BLOCKER | Default master_mode=BALANCED + default exec=CLOUD when no keys | `state.py:836-837` | Wrong mode for operator |
| P1-BLOCKER | Ghost cancel race condition | `bot.py:750-762`, `orchestrator.py:562-587` | Pipeline starts aborted |
| P1 | Provider status stale (ProviderIntelligence not synced at boot) | `provider_intelligence.py:191` | Misleading /providers display |
| P1 | sr=100% lat=9999ms (no health probes) | `provider_intelligence.py:150-158` | No real monitoring |
| P1 | S0 flow missing platforms/markets/logo UI | `bot.py:245-268`, `s0_intake.py` | Silent defaulting |
| P1 | Cost estimate hardcoded, BASIC mode allows $0.05+ estimate | `bot.py:1716` | Wrong UX |
| P2 | Mother Memory neo4j pending drain + mirror promotion | `memory_chain.py` | Memory writes lost |
| P2 | Three-axis mode: no /execution /transport, confusing /local | `bot.py:934-988` | Operator confusion |
| P2 | No project rehydration on restart | `bot.py` (no boot rehydration) | State lost on restart |
| P3 | ITo-do parsing artifact | No confirmed code bug | Possible user-input issue |

---

**Test Baseline: 825 passed / 3 skipped**  
**Tag applied: `pre-v5.8.13-audit-20260419`**

🛑 **PHASE 0 COMPLETE. Awaiting "go" before Phase 1.**
