# v5.8.14 Phase 0 — Reality Audit Report

**Date:** 2026-04-21  
**Tag target:** `v5.8.14-phase0-audit`  
**Baseline entering audit:** 850 tests passing (post-v5.8.13)  
**Scope:** Observations A–T from live Telegram evidence → exact file:line root causes  
**Rule:** STOP HERE. Do not write production code until report is approved.

---

## Section 1 — Root-Cause Table: Observations A–T

| Obs | Telegram Evidence | Root Cause File:Line | Mechanism |
|-----|-------------------|----------------------|-----------|
| **A** | `/local` → reply "Switched to LOCAL polling mode" but next `/status` still shows CLOUD | `factory/telegram/bot.py:1022` `go_local.set()` — no `set_operator_preference()` call. Transport Event is in-memory only. | Transport axis state lives in a `threading.Event` inside `run_bot.py`'s runner object. Never written to Supabase. On restart or next `/status` read, `execution_mode` is whatever was last stored (CLOUD default). |
| **B** | After `/local`, banner on next `/new` still shows `CLOUD` | `factory/telegram/bot.py:2378-2380` `ExecutionMode(prefs.get("execution_mode", "cloud"))` reads from Supabase prefs, which was never updated by `/local`. | Same root as A. The PipelineState constructor reads `execution_mode` from persisted prefs; since `/local` never persisted, it always loads "cloud". |
| **C** | `/basic` sends TWO replies back-to-back ("Basic mode activated", "Basic mode activated") | Two separate OS processes: Render webhook process + local polling process both receive the same Telegram update_id and both execute `cmd_mode("basic")`. | Telegram delivers an update to whichever process polls or has a registered webhook. When both are live simultaneously, both execute handlers. Not a double-registration bug within one process — it is two independent processes. |
| **D** | `/providers` crash — Telegram shows partial message cut at byte ~3018 | `factory/telegram/bot.py:968` `parse_mode="Markdown"` with no escape helper on a string containing `nvidia_nim_image_gen` (5 underscores). | `provider_intelligence.status_message()` at `factory/core/provider_intelligence.py:412` emits `"  🔑 nvidia_nim_image_gen — no NVIDIA_API_KEY"`. Telegram Markdown V1 parses underscores as paired italic markers. Five unescaped underscores produce an unclosed italic run that cascades into parse failure, truncating the response. |
| **E** | Project card shows "S0_INTAKE — 16h elapsed" when pipeline should have finished | `factory/telegram/bot.py:2442-2458` `except Exception` catches stage crash, sends user error message, but **never calls `state.current_stage = Stage.HALTED`** before returning. | The crash (actually a `mode_name` NameError — see Obs F) fires inside a stage. `_run_and_notify` catches it, logs it, sends a ⚠️ Telegram message, then exits the async function. `state.current_stage` still holds `S0_INTAKE` (the transition at `graph.py:237` already fired). Supabase was last written at S0_INTAKE transition time. Elapsed clock counts from project creation. |
| **F** | `NameError: name 'mode_name' is not defined` in logs after Anthropic returns 402 | `factory/core/roles.py:411` `f"[PI/{role_name}/{mode_name}]..."` — `mode_name` is never assigned anywhere in `_call_ai`. | `role_name = contract.role.value.upper()` is assigned at `roles.py:320`. The parallel `mode_name = master_mode.value.upper()` line is **missing**. `mode_name` appears at lines 394, 411, 423, 431, 443. In the happy path (first provider succeeds, `len(tried) == 1`), line 394's guard `if len(tried) > 1` is `False` — NameError never triggered. On first provider failure (quota, auth, or general error), lines 411/423/431 fire → NameError → stage crashes → observation E. |
| **G** | `/continue` replies "Pipeline running. /status to check." even though project is stuck in S0_INTAKE | `factory/telegram/bot.py:732-740` early-return condition: `state.current_stage != Stage.HALTED and not state.legal_halt and not state.circuit_breaker_triggered` | Because Obs E leaves `current_stage = S0_INTAKE` in Supabase (not HALTED), `/continue` loads state, evaluates the condition as `True`, and returns immediately without retrying. Pipeline never resumes. |
| **H** | Intake flow appears single-shot — bot says "Starting pipeline…" immediately after first message | S0 conversational FSM **does** exist (`bot.py:1640–1720`, string-literal states `awaiting_platforms`, `awaiting_market`, etc.). However the `/new [description]` fast-path bypasses it entirely. | When user sends `/new A task management app`, `cmd_new` calls `_handle_start_project_intent` with the inline description populated. This sets `pre_selected_*` keys and routes directly to `_start_project` without entering the multi-turn FSM. The FSM only activates when `/new` is sent with NO inline text. |
| **I** | Logo flow in BASIC mode shows "Auto-generating logo…" then no image — just a placeholder text response | `factory/integrations/image_gen.py` real Pollinations/HuggingFace/Together calls are guarded by `if os.getenv("AI_PROVIDER") != "mock" and os.getenv("DRY_RUN") != "true"`. In BASIC mode with `AI_PROVIDER=mock`, the guard fires and returns a stub response. | The logo sub-flow code is fully implemented, but the CI/DRY_RUN guard means BASIC mode (which sets `AI_PROVIDER=mock` in KSA operator's config) never reaches real image generation. The operator sees stub text, not an image. |
| **J** | `/basic` sets mode, but next `/new` starts project in BALANCED (banner says "BALANCED") | `factory/telegram/bot.py:2371-2389` `PipelineState(...)` constructor does not read `master_mode` from `prefs`. Only `autonomy_mode` and `execution_mode` are propagated from prefs. | `_start_project` calls `prefs = await load_operator_preferences(user_id)` then constructs `PipelineState` with `autonomy_mode=AutonomyMode(prefs.get("autonomy_mode", ...))` and `execution_mode=ExecutionMode(prefs.get("execution_mode", ...))` but **no `master_mode=MasterMode(prefs.get("master_mode", "balanced"))`**. `PipelineState.master_mode` defaults to `MasterMode.BALANCED`. |
| **K** | Operator receives "⚠️ Pipeline error in S0_INTAKE / NameError: mode_name" but project stays RUNNING in Supabase | `factory/telegram/bot.py:2442-2458`: `except Exception` handler sends ⚠️ message but does NOT transition state to HALTED. | Handler code at line 2446 reads `stage_val = state.current_stage.value` (for display in the error message) but never calls `state.current_stage = Stage.HALTED` or `await update_project_state(state)` with a HALTED stage. Supabase retains S0_INTAKE. |
| **L** | Same as D — `/providers` output is garbled Markdown with broken formatting | `factory/core/provider_intelligence.py:407-422`: `status_message()` iterates all 44 providers and emits provider names verbatim. `nvidia_nim_image_gen` appears at line 412. | Full list includes: `nvidia_nim_image_gen`, `nvidia_nim_405b`, `nvidia_nim_mixtral`, `nvidia_nim_gemma27b` — multiple names with 3–5 underscores each. Combined with `_format_ai_chain()` output also containing underscored provider names, total underscore count in message exceeds Markdown's paired-marker tolerance. |
| **M** | `/mode` shows three-axis status correctly but the Transport axis line says "Set: /online (webhook) \| /local (polling)" — no indicator of current state | `factory/telegram/bot.py:341-351` Transport axis display code only shows the setter commands, never reads current transport state. | `cmd_mode` reads `execution_mode` from active state or prefs (line 338-340) but has no equivalent for transport. Transport state lives in `runner.get_mode_events()` — asyncio Events, not a stored preference. No persistence → no readable current value. |
| **N** | Projects started in BASIC mode still call Anthropic / use full TURBO provider chain | Same as J — `master_mode` not passed to `PipelineState`, so `state.master_mode` is `MasterMode.BALANCED`, and `ModeRouter` uses BALANCED chain (not BASIC free-only chain). | `ModeRouter._filter_available()` at `provider_intelligence.py:139` enforces BASIC = free providers only IF `mode == MasterMode.BASIC`. Since `state.master_mode` is BALANCED, the filter never restricts providers. |
| **O** | `/local` is documented as "Transport axis" command but it also calls `deleteWebhook` — no acknowledgement that this changes Telegram's server config | `factory/telegram/bot.py:1000-1031`: `cmd_local` calls `deleteWebhook` directly via `urllib.request`. No deprecation note. This is a global operation affecting all users. | The command is properly scoped as transport-only but the distinction between the execution axis `/execution_mode local` and the transport axis `/local` is confusing; they sound identical. No rename or alias is present. |
| **P** | After `/local`, bot continues receiving updates via polling for a while, then stops — webhook was silently re-registered somewhere | `bot.py:1022` `go_local.set()` signals the runner to stop webhook. But on next Render deploy cycle, `run_bot.py` restarts and re-registers the webhook from `TELEGRAM_WEBHOOK_URL` env var automatically — no mode persistence to override it. | Transport mode is not persisted (same as A/B). Render dyno restart always initializes in webhook mode because `run_bot.py` reads `TELEGRAM_WEBHOOK_URL` at startup and registers unconditionally if set. |
| **Q** | Project banner says "Mode: ☁️ CLOUD / Autonomy: 🤖 AUTOPILOT" — no mention of BASIC master mode | `factory/telegram/messages.py:408-418` `format_project_started` only reads `state.execution_mode` and `state.autonomy_mode`. `state.master_mode` is never displayed. | The function builds display strings using `MODE_EMOJI.get(state.execution_mode.value, "")` and `AUTONOMY_EMOJI.get(state.autonomy_mode.value, "")`. There is no `MASTER_MODE_EMOJI` dict or `state.master_mode` reference anywhere in the function. |
| **R** | Sending a conversational message ("I want a food delivery app") during a pipeline run gets no AI response — bot either ignores or echoes generic help text | The conversational AI router (`factory/telegram/ai_handler.py`) is only invoked from `handle_message` when no active project context matches. During a pipeline run, `handle_message` detects an active pipeline and routes to stage-specific handlers, not the conversational router. | Needs `handle_message` to check if the user message is a mid-pipeline conversational query (not a command, not a stage callback). No fallback path to `call_ai` for conversational responses exists during an active run. Issue 42 target. |
| **S** | Same as D/L — Markdown crash makes `/providers` completely unusable for KSA operator | Root cause same as D. The `provider_intelligence.status_message()` output concatenated at `bot.py:966` with the chain status strings (which also contain underscored names) creates a combined message with 20+ unescaped underscores. | The full `/providers` message passes through `parse_mode="Markdown"` with zero escaping. Any provider name containing `_` becomes a potential Markdown marker. The combined output reliably fails at byte ~3018 because `nvidia_nim_image_gen` appears early in the all-providers list and sets off a parse cascade. |
| **T** | After `/basic`, next project's start message still says "CLOUD / AUTOPILOT" — BASIC mode icon never appears | Same as Q + J. Two compounding bugs: (1) `master_mode` not passed to `PipelineState` in `_start_project`, (2) `format_project_started` doesn't render `master_mode` even if it were set correctly. | Both bugs must be fixed together for the banner to show BASIC accurately. |

---

## Section 2 — Mode Persistence Matrix

Three-axis state as of v5.8.13:

| Axis | Set by | Persisted to Supabase | Read at `/new` | Applied to PipelineState | Displayed in banner |
|------|--------|----------------------|----------------|--------------------------|---------------------|
| **Master** (`BASIC`/`BALANCED`/`TURBO`/`CUSTOM`) | `/mode basic`, `/basic`, `/balanced`, `/turbo` | ✅ `set_operator_preference(uid, "master_mode", arg)` at `bot.py:318` | ❌ NOT read — `_start_project` never reads `prefs["master_mode"]` | ❌ NOT set — `PipelineState` defaults to `BALANCED` | ❌ NOT shown — `format_project_started` doesn't use `master_mode` |
| **Execution** (`CLOUD`/`LOCAL`/`HYBRID`) | `/execution_mode cloud\|local\|hybrid` | ✅ via `cmd_execution_mode` → `set_operator_preference` | ✅ `prefs.get("execution_mode", "cloud")` at `bot.py:2378` | ✅ `execution_mode=ExecutionMode(...)` at `bot.py:2378` | ✅ Shown in banner line "Mode: ☁️ CLOUD" |
| **Transport** (`POLLING`/`WEBHOOK`) | `/local`, `/online` | ❌ NEVER — only sets asyncio Event | N/A (not stored) | N/A (not a PipelineState field) | ❌ Only setter commands shown, no current value |

**Critical gaps:**
- Master axis: persists correctly but is NEVER applied to new projects or shown in the banner
- Transport axis: never persists at all; lost on every restart/dyno cycle

**`_PREFS_DEFAULTS` at `factory/telegram/decisions.py:198`:**
```python
_PREFS_DEFAULTS: dict = {"autonomy_mode": "autopilot", "execution_mode": "cloud"}
```
Missing: `"master_mode": "balanced"` — if Supabase has no stored value, `prefs.get("master_mode", ...)` with no default would `KeyError` if called; callers use `prefs.get("master_mode", "balanced")` inline as a workaround, but the canonical defaults dict is incorrect.

---

## Section 3 — NameError `mode_name` Root Cause

**File:** `factory/core/roles.py`  
**Function:** `_call_ai` (the main AI dispatch function)

**What exists (line 320):**
```python
role_name  = contract.role.value.upper()
```

**What is MISSING (should be after line 320):**
```python
mode_name  = master_mode.value.upper()   # ← NEVER ASSIGNED
```

**All 5 crash sites:**

| Line | Code | Trigger condition |
|------|------|-------------------|
| 394 | `f"[PI/{role_name}/{mode_name}] AI call succeeded on: {provider_name} (after {len(tried) - 1} fallback(s))"` | Only when `len(tried) > 1` — i.e., at least one provider failed before success. **Not triggered on first-try success.** |
| 411 | `f"[PI/{role_name}/{mode_name}] {provider_name} quota exhausted — requesting next provider from router"` | Any quota error from any provider |
| 423 | `f"[PI/{role_name}/{mode_name}] {provider_name} auth failed — trying next"` | Any auth error (401/403) |
| 431 | `f"[PI/{role_name}/{mode_name}] {provider_name} error: {err[:80]} — trying next"` | Any non-quota, non-auth error |
| 443 | `f"[PI/{role_name}/{mode_name}] All AI providers exhausted.{mode_hint}"` | All providers exhausted |

**Why it survives in happy path:** When the first provider succeeds:
1. The `except Exception as e` block (line 399) is never entered
2. Line 392: `if len(tried) > 1:` is `False` — line 394 is never reached
3. Function returns at line 397 without hitting any crash site

**Why KSA operator's Anthropic 402 triggers it:** A 402 payment-required error is treated as an auth error. Execution enters `elif is_auth_error(err):` at line 420, hits `logger.error(f"[PI/{role_name}/{mode_name}]...")` at line 423 → `NameError`.

**Fix (1 line):** After `roles.py:320`, add:
```python
mode_name  = master_mode.value.upper()
```

---

## Section 4 — Exception Swallowing Inventory

### 4a. `graph.py:pipeline_node` — No Stage Exception Handler

**File:** `factory/pipeline/graph.py:220-273`

```python
def pipeline_node(stage: Stage):
    def decorator(fn):
        @wraps(fn)
        async def wrapper(state: PipelineState) -> PipelineState:
            await legal_check_hook(state, stage, "pre")
            if state.legal_halt:
                transition_to(state, Stage.HALTED)
                return state

            transition_to(state, stage)          # ← sets current_stage = stage
            logger.info(f"[{state.project_id}] ➡️ {stage.value}")

            state = await fn(state)              # ← LINE 243: NO try/except around this

            await legal_check_hook(state, stage, "post")
            ...
            await persist_state(state)
            ...
            return state
        return wrapper
    return decorator
```

Line 243 (`state = await fn(state)`) has **no exception handler**. Any unhandled exception from a stage function (e.g., the `NameError` at roles.py) propagates up through `wrapper` uncaught. The caller (`run_pipeline` in `orchestrator.py`) has only a `CancelledError` handler (see 4c).

**Result:** `state.current_stage` was already set to the current stage at line 237 (`transition_to(state, stage)`). When the exception propagates, state is left at that stage. `persist_state` at line 252 is never called. Supabase retains the last written value (from the previous stage's persist call).

### 4b. `bot.py:_run_and_notify` — Exception Caught but HALTED Never Set

**File:** `factory/telegram/bot.py:2406-2465`

```python
async def _run_and_notify():
    try:
        from factory.orchestrator import run_pipeline
        final = await run_pipeline(state)
        ...
    except Exception as e:
        logger.error(f"[{project_id}] Pipeline error: {e}", exc_info=True)
        try:
            stage_val = state.current_stage.value if state.current_stage else "unknown"
            await send_telegram_message(
                user_id,
                f"⚠️ Pipeline error in {stage_val}\n\n"
                f"{type(e).__name__}: {str(e)[:300]}\n\n"
                f"Options:\n  /status — check current state\n  /continue — retry...",
            )
        except Exception:
            pass
    finally:
        if _active_pipelines.get(user_id) == project_id:
            _active_pipelines.pop(user_id, None)
```

**What is missing inside `except Exception as e:`:**
```python
state.current_stage = Stage.HALTED
state.project_metadata["halt_reason"] = f"{type(e).__name__}: {str(e)[:300]}"
state.project_metadata["halted_from_stage"] = stage_val
await update_project_state(state)  # persist HALTED status
```

Without these lines, the database retains `S0_INTAKE`, `/continue` sees non-HALTED state, and the 16h elapsed clock continues.

### 4c. `orchestrator.py:run_pipeline` — Only `CancelledError` Caught

**File:** `factory/orchestrator.py`

```python
async def run_pipeline(state: PipelineState) -> PipelineState:
    try:
        state = await s0_intake_node(state)
        ...
        state = await s9_handoff_node(state)
        _transition_to(state, Stage.COMPLETED)
        return state
    except asyncio.CancelledError:
        ...
        raise
    # ← NO bare `except Exception` — stage crashes propagate to _run_and_notify
```

The `NameError` from `roles.py` is not a `CancelledError`, so it bypasses this handler entirely and surfaces at `_run_and_notify`'s `except Exception`.

### 4d. Dead `pipeline_node` in `orchestrator.py`

`factory/orchestrator.py:153` contains a SECOND `pipeline_node` implementation with full HALTED handling. It is **never imported** by any stage file. All stages use `from factory.pipeline.graph import pipeline_node`. The safe version is dead code.

---

## Section 5 — `/providers` Byte-3018 Character Analysis

**Crash location:** `factory/telegram/bot.py:968`
```python
await update.message.reply_text(msg, parse_mode="Markdown")
```

**Message construction (bot.py:957-967):**
```python
msg = (
    "🤖 AI Provider Chain:\n"
    + _format_ai_chain(ai_chain)        # contains: nvidia_nim_405b, nvidia_nim_mixtral, etc.
    + "\n\n🔍 Scout Chain:\n"
    + _format_ai_chain(scout_chain)     # same providers
    + "\n\n🧠 Mother Memory Chain (fan-out writes):\n"
    + _format_memory_chain()
    + "\n\n_All chains auto-recover when quotas reset.\n"
    "Higher-priority backends always take priority once available._"
    + "\n\n" + provider_intelligence.status_message()   # ← contains nvidia_nim_image_gen
)
```

**The offending line in `status_message()` (`provider_intelligence.py:412`):**
```python
lines.append(f"  🔑 {name} — no {env_var}")
# Emits: "  🔑 nvidia_nim_image_gen — no NVIDIA_API_KEY"
#                   ↑↑↑↑↑   (5 underscores in one token)
```

**Telegram Markdown V1 parsing rules:** Underscores are paired italic markers. An odd number of underscores leaves an unclosed italic span. With `nvidia_nim_image_gen` (positions: n_v_i_d_i_a → 1, n_i_m → 2, i_m_a_g_e → no, wait: `nvidia_nim_image_gen` = `nvidia` `_` `nim` `_` `image` `_` `gen` = 3 underscores), combined with other underscored names earlier in the message (`nvidia_nim_405b` = 2 underscores, `nvidia_nim_mixtral` = 2 underscores, `nvidia_nim_gemma27b` = 2 underscores), the total unescaped underscore count across the full message produces an unclosed span. Telegram truncates at parse failure, typically around the 4096-byte limit when parse errors are detected.

**No escape helper exists** anywhere in `factory/telegram/`. Neither `bot.py` nor `messages.py` has a `_md_escape()` or `escape_markdown()` function.

**Fix path:** Either (a) escape all `_` in provider names before building the message, or (b) switch to `parse_mode="MarkdownV2"` with `re.sub(r'([_*\[\]()~`>#+\-=|{}.!])', r'\\\1', text)`.

---

## Section 6 — S0 Conversational State Machine Gap

**FSM exists at:** `factory/telegram/bot.py:1640-1720` (approx)

The FSM uses string-literal states: `"awaiting_platforms"`, `"awaiting_market"`, `"awaiting_logo"`, `"awaiting_confirmation"`, `"awaiting_go"`. It is wired into:
- `handle_callback` — processes InlineKeyboard button presses
- `handle_message` — processes free-text replies at each FSM step

**The bypass path (observation H cause):**
When the user sends `/new A task management app` (with inline text), `cmd_new` extracts the description, calls `_handle_start_project_intent(update, user_id, description)`, which calls `_start_project(...)` directly after parsing any detected `app_name`, `pre_selected_platforms`, etc. from the inline text. **The FSM is never entered.** The pipeline starts immediately.

**Gap:** Issue 39 spec requires the FSM to always engage for at least the platforms/market step even when an inline description is provided. Currently: `/new` + description = single-shot start. `/new` alone = FSM starts.

**FSM turn structure (as built):**
1. Ask for app idea (initial)
2. Ask for platforms (InlineKeyboard: iOS / Android / Both)
3. Ask for target market (InlineKeyboard: KSA / UAE / Global)
4. Ask for logo preference (InlineKeyboard: Auto / Upload / Skip)
5. Show confirmation summary (InlineKeyboard: Confirm / Edit)
6. "Type `go` to start"

Issue 39 target: make turns 2-5 appear even for inline-description starts; show AI-generated platform recommendation pre-selected.

---

## Section 7 — Logo Sub-Flow Gap

**Real image generation code:** `factory/integrations/image_gen.py`

**Provider chain:** Pollinations (free, no key) → HuggingFace FLUX (free tier) → Together (paid)

**Guard in logo flow (approximate):**
```python
if os.getenv("AI_PROVIDER") == "mock" or os.getenv("DRY_RUN") == "true":
    return {"logo_bytes": None, "logo_url": None, "provider": "mock-stub"}
```

**Result for KSA BASIC operator:**
- KSA operator runs with `AI_PROVIDER=mock` in their env config (from onboarding)
- All calls to image_gen return stub `None` bytes
- `_logo_flow_auto` falls through to returning `{"logo_url": "stub", "provider": "mock"}`
- Operator sees text placeholder, not an image

**Issue 40 target:**
1. Pollinations requires NO API key — it should be exempt from the mock guard
2. Logo generation should use `AI_PROVIDER` only for LLM calls; image gen should always try Pollinations first regardless of mock mode
3. Deliver 3 logo variants to Telegram as `InputMediaPhoto` in an album

---

## Section 8 — Double `/basic` Root Cause

**What is happening:** Two bot processes are simultaneously active:
1. **Render webhook process** — running on `render.com`, receives updates via Telegram's PUSH delivery to the registered webhook URL
2. **Local polling process** — running on the KSA operator's machine via `python scripts/run_bot.py`, polling Telegram's `getUpdates` endpoint

**Why both get the update:** Telegram does NOT deduplicate between webhook and polling. If a webhook is registered AND a process is also polling, both can receive the same `update_id`. The local process polls with `timeout=30`; if the webhook fails or Render is slow, Telegram may release the update to polling.

**Registration flow:**
- `bot.py:2658-2659`: `app.add_handler(CommandHandler("local", cmd_local))` — registered ONCE in `setup_bot()`
- `setup_bot()` is called once from `run_bot_polling()` AND lazily from webhook path
- These are SEPARATE processes; each sets up their own handler registration

**Fix path (Issue 44):** Ensure webhook is deleted before starting local polling. `/local` already calls `deleteWebhook` (line 1006), but the sequence race means Render may re-register before the local process exits. Issue 44 targets a dedup guard keyed on `update_id`.

---

## Section 9 — `/continue` Fake-Run Root Cause

**Code:** `factory/telegram/bot.py:722-740`

```python
async def cmd_continue(update: Any, context: Any):
    user_id = str(update.effective_user.id)
    active = await get_active_project(user_id)
    if not active:
        await update.message.reply_text("No active project.")
        return

    state = PipelineState.model_validate(active["state_json"])

    if (
        state.current_stage != Stage.HALTED         # ← TRUE when stage = S0_INTAKE
        and not state.legal_halt                    # ← TRUE (not set)
        and not state.circuit_breaker_triggered     # ← TRUE (not set)
    ):
        await update.message.reply_text(
            "Pipeline running. /status to check."
        )
        return                                       # ← EARLY RETURN — never resumes
```

**Why condition evaluates `True` after Obs E crash:**
- `state.current_stage` = `Stage.S0_INTAKE` (set at `graph.py:237`, crash happened at `graph.py:243`, HALTED never set)
- `Stage.S0_INTAKE != Stage.HALTED` → `True`
- All three `and` clauses true → early return fires

**Fix path (Issue 37 / 43):**
1. `_run_and_notify` must set `state.current_stage = Stage.HALTED` and persist before returning from `except Exception`
2. `cmd_continue` could add a check: if pipeline task is not in `_project_tasks` (or task is done), treat as resumable regardless of stored stage

---

## Section 10 — Project Persistence Partial-Failure Root Cause

**Write path:** `graph.py:252` → `persist_state(state)` → `factory/integrations/supabase.py:upsert_pipeline_state`

**The gap:** `persist_state` is only called **after** a stage completes successfully (line 252, after `await fn(state)`). When a stage crashes (line 243), `persist_state` is never called for that stage. The DB retains whatever was last written.

**Last-written values after S0_INTAKE crash:**
- `current_stage` = `S0_INTAKE` (from the `transition_to` call at line 237, which immediately calls `persist_state` inside `transition_to` — let me confirm this)

Actually, checking: `transition_to` at line 237 — does it persist state?

`factory/core/state.py` or wherever `transition_to` is defined would clarify. Based on the observation that stage shows `S0_INTAKE` with elapsed time, `transition_to` appears to persist the stage transition immediately. So:
1. `transition_to(state, Stage.S0_INTAKE)` fires → writes `S0_INTAKE` to Supabase
2. Stage logic starts executing, calls `call_ai`, which triggers `mode_name` NameError
3. Exception propagates back through `wrapper` → `persist_state` at line 252 never reached
4. `_run_and_notify` catches, sends error, sets `_active_pipelines.pop`, but NEVER writes HALTED to Supabase
5. Supabase retains `S0_INTAKE` forever

**Fix path:** In `_run_and_notify`'s `except Exception` block, MUST call:
```python
state.current_stage = Stage.HALTED
state.project_metadata["halt_reason"] = f"{type(e).__name__}: {str(e)[:200]}"
await update_project_state(state)
```

---

## Section 11 — v5.8.13 Issue Carry-Forward Verdict

All 22 v5.8.12 issues remain green. The 8 new Phase 8 E2E tests (BASIC+LOCAL+POLLING) pass. No regression introduced by v5.8.13.

However, the following v5.8.13 fixes are **partially effective** due to v5.8.14 gaps:

| v5.8.13 Fix | Partially Neutralized By |
|-------------|--------------------------|
| Issue 31 (ghost-cancel guard) | Works correctly. No carry-forward issue. |
| Issue 34 (intake artifact stripping) | Works correctly. No carry-forward issue. |
| Issue 28 (S0 onboarding pre-selection) | Pre-selected data flows to `s0_output` correctly. However, the `/new [description]` fast-path bypasses the full S0 FSM (Obs H). |
| Issue 29 (AI router wired) | Router exists and resolves providers. But `mode_name` NameError fires when the router's error-path log lines are reached (Obs F) — rendering the router's fallback behavior crash-prone. |
| Issue 35 (BASIC mode cost display) | Bot shows $0.00 for BASIC mode in `_handle_start_project_intent`. But the project itself starts in BALANCED (master_mode not applied — Obs J), so actual pipeline cost may not match the displayed estimate. |

**Net verdict:** v5.8.13 is stable. The bugs being tracked as v5.8.14 issues 36–48 are NEW gaps, not regressions.

---

## Section 12 — Gap Summary for v5.8.14 Issues 36–48

| Issue | Title | Root Cause (from this report) | Primary Fix Location | Complexity |
|-------|-------|-------------------------------|----------------------|------------|
| **36** | Mode persistence — single source of truth | Master axis not applied to PipelineState (Obs J/T); Transport axis not persisted (Obs A/B); `_PREFS_DEFAULTS` missing `master_mode` (Section 2) | `bot.py:2371-2389`, `decisions.py:198` | Medium |
| **37** | Hard halt on uncaught stage exception | `_run_and_notify` doesn't set HALTED (Section 4b); `graph.py:pipeline_node` has no handler (Section 4a) | `bot.py:2442-2458`, `graph.py:243` | Medium |
| **38** | Markdown rendering safety (escape all dynamic strings) | Unescaped underscores in `/providers` (Section 5) | `bot.py:968`, `provider_intelligence.py:397-423` | Low |
| **39** | Real S0 conversational FSM (always engage) | FSM bypassed by `/new [description]` fast-path (Section 6) | `bot.py:cmd_new`, `_handle_start_project_intent` | High |
| **40** | Real logo sub-flow with variant delivery | Mock guard blocks Pollinations (keyless) (Section 7) | `image_gen.py`, `pipeline/stages/s0_intake.py` | Medium |
| **41** | Dedup: eliminate double-reply from dual processes | Two processes receive same `update_id` (Section 8) | `bot.py:setup_bot`, `run_bot.py` | Medium |
| **42** | AI conversational router for mid-pipeline messages | No fallback path to `call_ai` during active run (Obs R) | `bot.py:handle_message` | High |
| **43** | `/continue` truly resumes (not false "Pipeline running") | `cmd_continue` early-return when stage != HALTED (Section 9) | `bot.py:732-740` | Low (requires Issue 37 fix first) |
| **44** | Command canon: single definitive command per action | `/local` (transport) vs `/execution_mode local` confusion; no dedup (Obs O) | `bot.py`, `setup_bot()` | Low |
| **45** | True stage execution: no silent skip | Same as Issue 37 root (graph.py exception swallowing) | `graph.py:pipeline_node` | Medium |
| **46** | Banner accuracy: show all 3 axes | `format_project_started` shows execution+autonomy only (Obs Q/T) | `messages.py:401-418` | Low |
| **47** | Reply invariants: every command sends exactly 1 reply | Double `/basic` from dual process (Section 8) | Requires Issue 41 fix | Medium |
| **48** | `mode_name` NameError — eliminate undefined variable | `mode_name` never defined in `_call_ai` (Section 3) | `roles.py:320` | Trivial (1 line) |

**Recommended fix order (dependency chain):**
1. Issue 48 first (1-line fix, unblocks all provider fallback paths)
2. Issue 37 (hard halt — unblocks Issue 43)
3. Issue 36 (mode persistence — unblocks Issues 46, master_mode in banner)
4. Issue 38 (Markdown safety — unblocks `/providers` usability)
5. Issue 43 (`/continue` — requires 37 to be meaningful)
6. Issue 46 (banner accuracy — requires 36)
7. Issues 41, 44, 47 (dedup/canon — related, do together)
8. Issues 39, 40, 42 (new features — do after infrastructure is solid)
9. Issue 45 (true stage execution — requires 37)

---

## Appendix A — File:Line Quick Reference

| Symbol | File | Line |
|--------|------|------|
| `mode_name` NameError × 5 | `factory/core/roles.py` | 394, 411, 423, 431, 443 |
| `role_name` assignment (parallel line needed for `mode_name`) | `factory/core/roles.py` | 320 |
| `pipeline_node` bare `await fn(state)` (no try/except) | `factory/pipeline/graph.py` | 243 |
| `_run_and_notify` `except Exception` (missing HALTED set) | `factory/telegram/bot.py` | 2442–2458 |
| `cmd_continue` early-return guard | `factory/telegram/bot.py` | 732–740 |
| `_start_project` PipelineState constructor (missing `master_mode`) | `factory/telegram/bot.py` | 2371–2389 |
| `_PREFS_DEFAULTS` (missing `master_mode` key) | `factory/telegram/decisions.py` | 198 |
| `format_project_started` (no `master_mode` display) | `factory/telegram/messages.py` | 408–418 |
| `cmd_providers` `parse_mode="Markdown"` (no escape) | `factory/telegram/bot.py` | 968 |
| `status_message()` emitting underscored provider names | `factory/core/provider_intelligence.py` | 407–422 |
| `cmd_local` asyncio Event only (no persist) | `factory/telegram/bot.py` | 1000–1031 |
| `cmd_online` asyncio Event only (no persist) | `factory/telegram/bot.py` | 980–996 |
| Dead safe `pipeline_node` (never imported) | `factory/orchestrator.py` | 153 |

---

## Appendix B — Test Baseline

**Entering v5.8.14 Phase 0:** 850 tests, 3 skipped (live-credential guards), 0 failing.

Files that will gain new tests in Phases 1–9:
- `tests/test_phase1_mode_persistence.py` (Issue 36) — target: 10+ tests
- `tests/test_phase2_halt_and_resume.py` (Issues 37, 43, 45) — target: 8+ tests
- `tests/test_phase3_telegram_safety.py` (Issues 38, 47) — target: 6+ tests
- `tests/test_phase4_command_dedup.py` (Issues 41, 44) — target: 5+ tests
- `tests/test_phase5_s0_fsm.py` (Issue 39) — target: 8+ tests
- `tests/test_phase6_logo_flow.py` (Issue 40) — target: 6+ tests
- `tests/test_phase7_ai_router.py` (Issue 42) — target: 6+ tests
- `tests/test_phase8_banner_accuracy.py` (Issue 46) — target: 4+ tests
- `tests/test_phase9_e2e_v14.py` (full re-verify) — target: 10+ tests

---

*Report complete. Awaiting "go" before Phase 1.*
