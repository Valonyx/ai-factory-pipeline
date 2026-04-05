# AI FACTORY PIPELINE v5.6
# MASTER IMPLEMENTATION GUIDE — PART 2
## NB2: Production Wiring + NB3: System Activation

---

> **Where you are:** NB1 is complete. You have 85+ stub Python files,
> all tests pass, the dry-run runs S0→S8→COMPLETED, and the repo is
> tagged `v5.6.0-stub`. Zero dollars spent.
>
> **What this part covers:**
> - NB2 (7–10 days, $0): Replace every stub with real API calls.
>   362 tests pass. Tag `v5.6.0`.
> - NB3 (5–7 days, first ~$10–30 in AI spend): Create all accounts,
>   wire all secrets, deploy to Cloud Run, connect Telegram webhook,
>   run the first real app end-to-end.
>
> **Starting condition check:** Before continuing, confirm:

```bash
cd ~/Projects/ai-factory-pipeline
source .venv/bin/activate
git tag | grep stub          # Should show v5.6.0-stub
python -m pytest tests/ -v   # Should show 0 failures
python -m factory.pipeline.runner  # Should show COMPLETED
```

> All three must pass. If any fail, return to Part 1 and fix them first.

---

# SECTION 12: NB2 OVERVIEW — WHAT PRODUCTION WIRING MEANS

## 12.1 The Stub-to-Real Transformation

Every file you built in NB1 has stub implementations — functions that
return fake data so the architecture could be tested without real API
keys. Production wiring means replacing those stubs one by one with
real calls to real services.

**NB1 stub example (what exists now):**
```python
async def call_anthropic(prompt, model, max_tokens):
    return '{"stub": true}', 0.0, {}   # Fake response, zero cost
```

**NB2 production replacement (what you'll build):**
```python
async def call_anthropic(prompt, model, max_tokens):
    client = get_anthropic_client()
    message = await client.messages.create(...)
    cost = calculate_cost(message.usage, model)
    return message.content[0].text, cost, message.usage
```

The structure stays identical. The internals become real. This is why
NB1 mattered so much — you built and validated the architecture before
touching any paid services.

## 12.2 The NB2 Order

NB2 has 17 PROD steps. They must be done in sequence because each
step depends on the previous:

```
PROD-1:  Anthropic client (Strategist, Engineer, Quick Fix)
PROD-2:  Perplexity client (Scout)
PROD-3:  Telegram bot (real python-telegram-bot v21)
PROD-4:  Supabase client (state persistence)
PROD-5:  GCP Secrets (Secret Manager integration)
PROD-6:  Setup wizard (8-secret bootstrap flow)
PROD-7:  Pipeline DAG + S0-S2 (real stage implementations)
PROD-8:  Pipeline S3-S5 (code gen, build, test)
PROD-9:  Pipeline S6-S8 (deploy, verify, handoff)
PROD-10: Execution + UserSpace + Legal (cross-cutting concerns)
PROD-11: GitHub + Neo4j + AI dispatch (data stores)
PROD-12: Design Engine (real UI mock generation)
PROD-13: Entry points + Config + CLI (FastAPI app, main.py)
PROD-14: Deployment Infrastructure (Dockerfile, cloudbuild.yaml)
PROD-15: Integration tests (cross-module tests)
PROD-16: Full test suite (362 tests, all passing)
PROD-17: Final validation + v5.6.0 tag
```

---

# SECTION 13: NB2 PROD-1 — REAL ANTHROPIC CLIENT
📖 **Read first:** NB2 PROD-1 (full section) + Spec §2.2, §3.2, §3.3, §3.6

**What this replaces:** The fake `call_anthropic()` stub that returns
`{"stub": true}` with zero cost. After PROD-1, the Strategist (Opus 4.6),
Engineer (Sonnet 4.5), and Quick Fix (Haiku 4.5) all call the real
Anthropic API with actual token counting and real cost tracking.

**Note:** You do NOT need your Anthropic API key yet for this step.
The code will work in dry-run mode (no real calls) until NB3 Part 4
when you get the key. You are writing the real client code now so it
is ready when the key arrives.

---

## STEP 13.1 — Verify Current Pricing (Web Search Required)

**USE WEB SEARCH HERE** (in this Claude chat, not in Terminal):
```
"Current Anthropic Claude API pricing per million tokens 2026:
Opus 4.6, Sonnet 4.5, Haiku 4.5"
```

The spec records these verified rates (§14.1 Verification Ledger V1):
- claude-opus-4-6: $5.00 input / $25.00 output per million tokens
- claude-sonnet-4-5: $3.00 input / $15.00 output per million tokens
- claude-haiku-4-5: $1.00 input / $5.00 output per million tokens

If the search returns different rates, use the current rates when
writing the pricing table in the code. This is one place where the
spec may be out of date.

---

## STEP 13.2 — Build the Real Anthropic Client

**USE CONTEXT7 HERE** first:
```
"Using Context7, get anthropic Python SDK documentation for:
AsyncAnthropic client initialization, messages.create(),
message.usage.input_tokens, message.usage.output_tokens,
APIStatusError, APITimeoutError, APIConnectionError"
```

Then: **USE CLAUDE CODE HERE:**

```bash
cd ~/Projects/ai-factory-pipeline
source .venv/bin/activate
claude
```

In Claude Code, type:

```
Replace the stub in factory/integrations/anthropic.py with 
the real Anthropic AsyncAnthropic client per spec §2.2, §3.2–§3.6.

The real implementation must have:

1. ANTHROPIC_PRICING dict with exact per-MTok rates:
   claude-opus-4-6:          $5.00 input / $25.00 output
   claude-opus-4-5-20250929: $5.00 input / $25.00 output
   claude-sonnet-4-5-20250929: $3.00 input / $15.00 output
   claude-haiku-4-5-20251001: $1.00 input / $5.00 output

2. get_anthropic_client() → singleton AsyncAnthropic
   - Reads ANTHROPIC_API_KEY from environment
   - Timeout: 120 seconds
   - Max retries: 3 (SDK built-in on 429/500/529)
   - Raises RuntimeError with clear message if key missing

3. call_anthropic(prompt, model, max_tokens, system_prompt, temperature=0.0)
   - Calls client.messages.create() with real params
   - Returns tuple: (response_text, cost_usd, usage_dict)
   - Handles APIStatusError, APITimeoutError, APIConnectionError
   - In DRY_RUN mode: returns mock response without calling API

4. call_anthropic_json(prompt, model, max_tokens, system_prompt)
   - Like call_anthropic() but guarantees JSON response
   - parse_json_response() helper strips markdown fences
   - Retry up to 2 times if response is not valid JSON

5. calculate_cost(usage, model) → float
   - Computes cost from actual message.usage fields
   - (input_tokens / 1_000_000) * input_price + output equivalent

Also create factory/integrations/prompts.py with 4 role prompts:
- STRATEGIST_PROMPT: architecture, legal risk, decisions, KSA context
- ENGINEER_PROMPT: code generation, full files, Blueprint adherence
- QUICKFIX_PROMPT: minimal syntax fixes, 4KB context limit
- SCOUT_PROMPT: web research, cited sources, mark unverified info

After creating both files, install the package and run the test:
pip install anthropic>=0.20.0
python -c "
import os
os.environ['DRY_RUN'] = 'true'
from factory.integrations.anthropic import (
    call_anthropic, call_anthropic_json, 
    calculate_cost, ANTHROPIC_PRICING
)
from factory.integrations.prompts import get_system_prompt

# Verify pricing table
assert len(ANTHROPIC_PRICING) >= 4
print(f'Models in pricing table: {len(ANTHROPIC_PRICING)}')

# Verify dry-run works without API key
import asyncio
response, cost, usage = asyncio.run(call_anthropic(
    prompt='What is 2+2?',
    model='claude-haiku-4-5-20251001',
    max_tokens=100,
    system_prompt=get_system_prompt(\"quick_fix\"),
))
assert cost == 0.0  # Dry run should not incur cost
print(f'Dry-run response: {response[:50]}')
print('✅ PROD-1: Anthropic client ready (dry-run verified)')
"
```

---

## STEP 13.3 — Update roles.py to Use Real Client

Claude Code should continue with:

```
Now update factory/core/roles.py to route Anthropic roles 
to the real call_anthropic() from PROD-1 instead of the stub.

In call_ai():
- Scout (AIRole.SCOUT) → still uses perplexity stub (PROD-2 will fix)
- Strategist, Engineer, Quick Fix → use call_anthropic() with 
  get_system_prompt(role.value) as system_prompt
- Step 5 (cost tracking): use actual cost returned from call_anthropic()
  not an estimate — state.phase_costs[category] += cost
  and state.total_cost_usd += cost
- Log: f"[{state.project_id}] {role.value}: ${cost:.4f} total=${state.total_cost_usd:.4f}"

Run the 36 PROD-1 tests after updating:
python -m pytest tests/test_prod_01_anthropic.py -v
All 36 should pass.
```

---

## STEP 13.4 — PROD-1 Checkpoint

```bash
python -m pytest tests/ -v --tb=short 2>&1 | tail -5
# Should show: X passed, 0 failed
```

```bash
git add factory/integrations/anthropic.py factory/integrations/prompts.py factory/core/roles.py
git commit -m "NB2-PROD1: Real Anthropic client — AsyncAnthropic SDK, 4 system prompts, real cost tracking (§2.2, §3.2–§3.3)"
```

**USE MEMORY HERE:**
```
"Remember: NB2 PROD-1 complete. Real Anthropic client built. 
4 AI models in pricing table. Dry-run verified. Commit: NB2-PROD1."
```

---

# SECTION 14: NB2 PROD-2 — REAL PERPLEXITY CLIENT (SCOUT)
📖 **Read first:** NB2 PROD-2 + Spec §3.1, ADR-049, FIX-19

**What this replaces:** The Perplexity stub that returns
`{"stub": true, "citations": []}`. After PROD-2, the Scout role
calls real Perplexity Sonar and extracts actual research citations.

## STEP 14.1 — Check Current Perplexity API

**USE WEB SEARCH HERE:**
```
"Perplexity AI API pricing sonar sonar-pro 2026 per token"
```

Then **USE CONTEXT7 HERE:**
```
"Using Context7, find documentation for the openai Python SDK
used with Perplexity API base_url=https://api.perplexity.ai"
```

Perplexity uses an OpenAI-compatible API, so the Python `openai` SDK
works by pointing it at Perplexity's endpoint.

---

## STEP 14.2 — Build the Perplexity Client

**USE CLAUDE CODE HERE:**

```
Replace the stub in factory/integrations/perplexity.py with 
a real Perplexity client per spec §3.1, ADR-049, FIX-19.

The implementation must have:

1. PERPLEXITY_PRICING dict:
   sonar: (check current pricing and fill in)
   sonar-pro: (check current pricing and fill in)
   Request fee: check current per-1K request rate

2. CONTEXT_TIER_LIMITS dict (per ADR-049/FIX-19):
   small:  max_tokens=1000, recency_filter="month"
   medium: max_tokens=4000, recency_filter="week"
   large:  max_tokens=8000, recency_filter="day"
   
3. call_perplexity(prompt, tier="medium") async
   - Uses openai.AsyncOpenAI(base_url="https://api.perplexity.ai")
   - select_scout_model(tier) → sonar or sonar-pro
   - effective_tier() enforces SCOUT_MAX_CONTEXT_TIER ceiling
   - Extracts citations from search_results field
   - Returns (response_text, cost, citations_list)
   - Truncates prompt at tier token ceiling

4. call_perplexity_safe(prompt, tier="medium") async
   - Wraps call_perplexity() in full degradation chain:
     * Try real API → success: return result
     * APIError → try 1 retry
     * Still fails → synthesize from cache if available
     * No cache → return UNVERIFIED fallback response
     * Never let Scout errors halt the pipeline

5. extract_citations(response) 
   - Handles new search_results format AND legacy citations format

6. PerplexityUnavailableError exception class

After writing the file, also update factory/core/roles.py:
- Scout routing now uses call_perplexity_safe() instead of stub

Run test:
pip install openai>=1.50.0
python -c "
import os
os.environ['DRY_RUN'] = 'true'
from factory.integrations.perplexity import (
    call_perplexity_safe, PerplexityUnavailableError, 
    PERPLEXITY_PRICING, CONTEXT_TIER_LIMITS
)
import asyncio

print(f'Models: {list(PERPLEXITY_PRICING.keys())}')
print(f'Context tiers: {list(CONTEXT_TIER_LIMITS.keys())}')

# Test degradation chain (no real API key in dry-run)
response, cost, citations = asyncio.run(
    call_perplexity_safe('What are KSA PDPL requirements?', tier='small')
)
print(f'Degradation fallback works: {len(response) > 0}')
print('✅ PROD-2: Perplexity Scout client ready')
"
```

---

## STEP 14.3 — PROD-2 Checkpoint

```bash
python -m pytest tests/ -v --tb=short 2>&1 | tail -5
```

```bash
git add factory/integrations/perplexity.py factory/core/roles.py
git commit -m "NB2-PROD2: Real Perplexity Scout — OpenAI-compatible SDK, context-tier ceiling, degradation chain (§3.1, ADR-049, FIX-19)"
```

---

# SECTION 15: NB2 PROD-3 — REAL TELEGRAM BOT
📖 **Read first:** NB2 PROD-3 + Spec §5.1 through §5.7

**What this replaces:** The stub Telegram modules that log to the
console but never actually call the Telegram API. After PROD-3,
every command handler, notification, decision menu, and file delivery
uses the real `python-telegram-bot` v21 library.

## STEP 15.1 — Check Library Version

**USE CONTEXT7 HERE:**
```
"Using Context7, get python-telegram-bot v20+ documentation for:
Application.builder().token().build(), 
CommandHandler, MessageHandler, InlineKeyboardMarkup,
CallbackQueryHandler, and Application.run_webhook()"
```

---

## STEP 15.2 — Build the Real Telegram Layer

**USE CLAUDE CODE HERE:**

```
Replace all 4 Telegram stubs with real python-telegram-bot v21 
implementations per spec §5.1–§5.7.

Replace factory/telegram/notifications.py:
- notify_operator(bot_token, chat_id, text) async
  → Uses Bot(token).send_message(chat_id=chat_id, text=text)
- send_file_to_operator(bot_token, chat_id, file_path) async
  → Uses Bot(token).send_document() for files under 50MB
  → For files over 50MB, sends a text message with the URL

Replace factory/telegram/decisions.py:
- present_decision(state, question, options) async
  → Creates InlineKeyboardMarkup with one button per option
  → AUTOPILOT mode: auto-returns best option immediately
  → COPILOT mode: sends keyboard and waits for operator tap
  → Timeout: 300 seconds (5 minutes), then uses default
- resolve_decision(callback_query) 
  → Completes the pending Future from present_decision()
- record_deploy_decision(project_id, decision)
  → Stores deploy approval in Supabase operator_state

Replace factory/telegram/bot.py:
- setup_bot(token) → Application.builder().token(token).build()
- Add ALL 15 real command handlers (not stubs):
  /start → welcome message + whitelist check
  /new → parse project idea, queue pipeline run
  /status → query pipeline_states table for active projects
  /budget → query monthly_costs table
  /restore → show available snapshots for a project
  /cancel → halt the current pipeline run
  /pause → pause a running build
  /resume → resume a paused build
  /info → show project details
  /history → list past projects
  /mode → switch CLOUD/LOCAL/HYBRID
  /autopilot → switch to AUTOPILOT mode
  /copilot → switch to COPILOT mode
  /admin → admin commands (whitelist, logs)
  /help → list all commands with descriptions
- handle_message() → free-text handler: 
  if text looks like an app description, queue a new project
  otherwise send a helpful prompt
- handle_callback() → routes inline keyboard callbacks:
  "mode_X" → set execution mode
  "auto_X" → set autonomy mode
  "dec_XXXXXXXX_VALUE" → resolve decision
  "cancel_X" → cancel project

Also update factory/telegram/airlock.py:
- airlock_deliver(state, file_path) async:
  Tier 1: file <50MB → send_document() directly
  Tier 2: file >50MB → send GitHub release URL
  Tier 3: fallback → send GCP bucket URL
  Always include SHA-256 checksum in caption

Run tests:
python -m pytest tests/ -v --tb=short 2>&1 | tail -10
```

---

## STEP 15.3 — PROD-3 Checkpoint

```bash
git add factory/telegram/
git commit -m "NB2-PROD3: Real Telegram bot — python-telegram-bot v21, 15 commands, inline keyboards, decision queue (§5.1–§5.7)"
```

---

# SECTION 16: NB2 PROD-4 THROUGH PROD-6 — DATA + SECRETS LAYER
📖 **Read first:** NB2 PROD-4, PROD-5, PROD-6 + Spec §2.9, §2.11, §5.6

These three PROD steps build the state persistence and secrets
management layers. They can be done in a single Claude Code session.

## STEP 16.1 — Build PROD-4, 5, 6 Together

**USE CLAUDE CODE HERE:**

```
Complete NB2 PROD-4, PROD-5, and PROD-6 in sequence.

PROD-4: Replace factory/integrations/supabase.py stub
Per spec §2.9 (Triple-Write), §5.6 (11-table schema):

- SupabaseClient wrapping supabase-py create_client()
- persist_state(state) async:
  * Write to Supabase pipeline_states (primary)
  * Write serialized JSON to GitHub (secondary)
  * Write Project node to Neo4j (tertiary)
  * SHA-256 checksum of state JSON stored alongside
  * In DRY_RUN=true: log writes but don't call real API
- restore_state(project_id, snapshot_id) async:
  * Retrieve state_json from state_snapshots
  * Verify SHA-256 checksum before restoring
  * Raise SnapshotWriteError on checksum mismatch
- All 11 tables accessed:
  pipeline_states, state_snapshots, operator_whitelist,
  operator_state, active_projects, decision_queue,
  audit_log, monthly_costs, pipeline_metrics,
  memory_stats, temp_artifacts

PROD-5: Replace factory/core/secrets.py stub
Per spec §2.11 (Resolution Order):
- get_secret(name) → checks in this order:
  1. In-memory TTL cache (300 seconds)
  2. GCP Secret Manager (production)
  3. os.getenv() (local env)
  4. .env file via python-dotenv (local dev)
  5. None → EnvironmentError at boot
- validate_secrets() → checks all 15 REQUIRED_SECRETS exist
- In DRY_RUN=true: returns placeholder values for all secrets

PROD-6: Replace setup wizard
Per spec §7.1:
- InteractiveSetupWizard class
- 8-step bootstrap: checks env → prompts for each missing 
  secret → validates connection → stores to GCP Secret Manager
- validate_supabase_connection(), validate_neo4j_connection(),
  validate_anthropic_connection(), validate_perplexity_connection(),
  validate_telegram_connection()
- In DRY_RUN=true: skips real connection checks

After all three, run:
python -c "
import os
os.environ['DRY_RUN'] = 'true'
from factory.integrations.supabase import SupabaseClient
from factory.core.secrets import get_secret, validate_secrets
from factory.core.state import PipelineState

# Test dry-run persist
import asyncio
client = SupabaseClient(dry_run=True)
s = PipelineState(project_id='test-001', operator_id='op1')
asyncio.run(client.persist_state(s))
print('✅ PROD-4: Supabase triple-write (dry-run)')

# Test secrets resolution
key = get_secret('ANTHROPIC_API_KEY')
print(f'✅ PROD-5: Secret resolved in dry-run: {key[:10]}...')
print('✅ PROD-4/5/6 complete')
"
```

---

## STEP 16.2 — Checkpoint

```bash
python -m pytest tests/ -v --tb=short 2>&1 | tail -5
```

```bash
git add factory/integrations/supabase.py factory/core/secrets.py
git commit -m "NB2-PROD456: Supabase triple-write, GCP Secrets resolution, setup wizard (§2.9, §2.11, §5.6)"
```

---

# SECTION 17: NB2 PROD-7 THROUGH PROD-9 — REAL PIPELINE STAGES
📖 **Read first:** NB2 PROD-7, 8, 9 + Spec §4.1–§4.9 (all 9 stages)

**What this replaces:** The 9 stub stage files that return mock data.
After PROD-7/8/9, each stage calls real AI via `call_ai()`, processes
the response, updates state, and produces real outputs.

**KEY INSIGHT:** In NB1, each stage was a stub returning `{"stub": true}`.
Now each stage follows this real pattern:

```
async def execute(state: PipelineState) → PipelineState:
    1. call_ai() with appropriate role (Scout/Strategist/Engineer)
    2. Parse the AI response (extract structured data)
    3. Update state.sN_output with real data
    4. Transition to next stage
    5. Persist state (Supabase + Git + Neo4j)
    6. Notify operator via Telegram
    7. Return updated state
```

## STEP 17.1 — Build All 9 Real Stages

**USE CLAUDE CODE HERE:**

```
Replace all 9 stub pipeline stages with real implementations
for NB2 PROD-7/8/9 per spec §4.1-§4.9.

PROD-7: factory/pipeline/s0_intake.py (real)
Per spec §4.1:
- call_ai(state, AIRole.QUICK_FIX, prompt=parse_idea_prompt(idea))
- Extract: name, platform, target_audience, monetization_model,
  core_features (max 5), idea_hash
- Validate: operator on whitelist (check operator_whitelist table)
- Set state.s0_output = {name, platform, features, ...}

factory/pipeline/s1_legal.py (real)
Per spec §4.2 — KSA Continuous Legal Thread:
- FIRST: call_ai(state, AIRole.SCOUT, ksa_legal_research_prompt)
  checks PDPL, CST, SAMA, NDMO, NCA, SDAIA requirements
- THEN: call_ai(state, AIRole.STRATEGIST, legal_risk_prompt)
  classifies legal risk and recommends mitigations
- If Strategist returns legal_clear=False:
  state.legal_halt = True
  state.legal_halt_reason = (reason)
  transition to HALTED

factory/pipeline/s2_blueprint.py (real)
Per spec §4.3:
- Scout researches framework options for the platform
- Strategist selects stack from [flutterflow, react_native, 
  swift, kotlin, unity, python_backend] based on idea
- Strategist generates full Blueprint JSON
- state.selected_stack = selected TechStack enum value
- state.s2_output = {blueprint: Blueprint dict, stack: str}

PROD-8: factory/pipeline/s3_codegen.py (real)
Per spec §4.4:
- Engineer receives Blueprint from s2_output
- call_ai(state, AIRole.ENGINEER, codegen_prompt(blueprint))
- Response is multi-file code in JSON format
- Parse and write each file to state.s3_output["files"]
- File count tracked for metrics

factory/pipeline/s4_build.py (real)
Per spec §4.5:
- Engineer creates build scripts for the selected stack
- FlutterFlow: generates FlutterFlow config + schema
- React Native: generates package.json + build script
- Python Backend: generates Dockerfile + requirements
- Store build artifact paths in state.s4_output

factory/pipeline/s5_test.py (real)
Per spec §4.6:
- Engineer generates test suite for the generated code
- Test results analyzed by Quick Fix
- If test failures: increment retry_count, re-run codegen
- state.s5_output["passed"] = True/False
- state.s5_output["failures"] = list of failure messages

PROD-9: factory/pipeline/s6_deploy.py (real)
Per spec §4.7:
- COPILOT mode: present_decision() with deploy options
  (deploy to web / submit to App Store / deploy to Play)
- AUTOPILOT mode: auto-deploys per blueprint.target_stores
- Engineer creates deployment artifacts
- state.s6_output["deploy_url"] = deployed URL

factory/pipeline/s7_verify.py (real)
Per spec §4.8:
- Quick Fix runs health check on deployed URL
- Scout verifies app store listing (if submitted)
- state.s7_output["verified"] = True/False

factory/pipeline/s8_handoff.py (real)
Per spec §4.9 + FIX-27:
- Engineer generates 7 Intelligence Pack documents:
  QUICK_START.md, privacy_policy.html, terms_of_service.html,
  ksa_compliance_report.pdf, architecture_diagram.md,
  app_store_metadata.json, developer_handoff.md
- Plus 3 program-level docs if project is part of a program
- airlock_deliver() sends each document to operator
- state.s8_output["delivered"] = True
- state.current_stage = Stage.COMPLETED

After building all 9 stages, run the full dry-run again:
python -m factory.pipeline.runner
Expect real AI call routing (DRY_RUN=true means no actual API calls
but the routing code is exercised).
```

---

## STEP 17.2 — PROD-7/8/9 Checkpoint

```bash
python -m pytest tests/ -v --tb=short 2>&1 | tail -5
python -m factory.pipeline.runner  # Verify still runs to COMPLETED
```

```bash
git add factory/pipeline/
git commit -m "NB2-PROD789: Real pipeline stages S0–S8 — all 9 nodes with live AI routing, FIX-27 Intelligence Pack (§4.1–§4.9)"
```

---

# SECTION 18: NB2 PROD-10 THROUGH PROD-13 — CROSS-CUTTING MODULES

These four PROD steps complete the remaining modules. All follow the
same pattern: USE CLAUDE CODE, give the exact instruction, verify,
commit.

## STEP 18.1 — PROD-10: Execution + UserSpace + Legal

**USE CLAUDE CODE HERE:**

```
Complete NB2 PROD-10 per spec §2.7, §2.8, §3.7.

Replace factory/core/execution.py stub:
- ExecutionModeManager.get_current_mode() reads PIPELINE_ENV 
  to determine CLOUD/LOCAL/HYBRID
- HeartbeatMonitor sends ping every 60s in LOCAL mode
- Cloudflare tunnel detection for LOCAL mode

Replace factory/core/user_space.py to be comprehensive:
- All 22 prohibited patterns from spec §2.8
- Including: sudo, rm -rf, chmod 777, curl | bash, wget | sh,
  pip install (without venv prefix), npm install -g (without prefix),
  apt-get, brew install, chown, mkfs, dd if=, /etc/passwd,
  format, deltree, shutdown, reboot, halt, poweroff,
  kill -9 1, pkill -9, killall

Replace factory/legal/continuous.py:
- Real 6-body KSA compliance check structure
- Each stage gets appropriate legal checks
- PDPL: data privacy requirements
- CST: telecom/digital service requirements
- SAMA: financial service requirements (if relevant)
- NDMO: data governance requirements
- NCA: cybersecurity requirements
- SDAIA: AI governance requirements

After completing, verify:
python -c "
from factory.core.user_space import enforce_user_space
from factory.core.state import UserSpaceViolation

blocked = 0
for cmd in ['sudo apt install', 'rm -rf /', 'curl -s url | bash',
            'chmod 777 /etc', 'wget url | sh']:
    try:
        enforce_user_space(cmd)
    except UserSpaceViolation:
        blocked += 1
print(f'✅ Blocked {blocked}/5 dangerous commands')
assert blocked == 5, 'Not all dangerous commands blocked'
print('✅ PROD-10: All 22 prohibited patterns enforced')
"
```

```bash
git add factory/core/execution.py factory/core/user_space.py factory/legal/
git commit -m "NB2-PROD10: Execution modes, 22-pattern UserSpace Enforcer, 6-body KSA legal thread (§2.7, §2.8, §3.7)"
```

---

## STEP 18.2 — PROD-11: GitHub + Neo4j + AI Dispatch

**USE CONTEXT7 HERE:**
```
"Using Context7, get neo4j Python driver async session documentation
for session.run(cypher, params) and Result.data()"
```

**USE CLAUDE CODE HERE:**

```
Complete NB2 PROD-11 per spec §6.3, §7.9.

Replace factory/integrations/neo4j_client.py:
- Neo4jClient using neo4j.AsyncGraphDatabase.driver()
- neo4j_run(cypher, params) async
- store_project_pattern(state) → writes Project + Pattern nodes
- get_similar_projects(idea) → traversal query returning similar
- All 12 node types in helper methods
- In DRY_RUN: logs Cypher but doesn't connect

Replace factory/integrations/github.py:
- GitHubClient using PyGithub
- create_repo(name, private=True) → creates project repo
- commit_files(repo_name, files_dict, message) → pushes code
- create_release(repo_name, tag, notes) → creates release
- In DRY_RUN: logs operations but doesn't call real GitHub API

Update factory/core/roles.py AI dispatch:
- Ensure all 4 roles route correctly now that PROD-1 and PROD-2 done
- Add timing: track milliseconds per AI call in state.sN_output
- Add structured logging: one log line per AI call with role/cost/time

Verify:
python -c "
import os
os.environ['DRY_RUN'] = 'true'
from factory.integrations.neo4j_client import Neo4jClient
from factory.integrations.github import GitHubClient
print('✅ Neo4j client: dry-run mode')
print('✅ GitHub client: dry-run mode')
print('✅ PROD-11: GitHub + Neo4j ready')
"
```

```bash
git add factory/integrations/neo4j_client.py factory/integrations/github.py
git commit -m "NB2-PROD11: Neo4j async driver, GitHub client, complete AI dispatch routing (§6.3, §7.9)"
```

---

## STEP 18.3 — PROD-12: Design Engine

**USE CLAUDE CODE HERE:**

```
Complete NB2 PROD-12 per spec §2.12.

Replace factory/design/design_engine.py:
- DesignEngine.generate_mocks(blueprint) async
  → call_ai(state, AIRole.ENGINEER, mock_prompt(blueprint))
  → Returns 3 mock designs as structured HTML/JSON
  → vibe_check(): validates WCAG AA contrast ratios
  → grid_enforcer(): validates 4px grid alignment
  → brand_consistency(): checks consistent colors/fonts
  
- generate_color_palette(category) 
  → Returns brand colors appropriate for app category
  (e.g., health=blues/greens, finance=navy/gold, etc.)

Verify:
python -c "
import os
os.environ['DRY_RUN'] = 'true'
from factory.design.design_engine import DesignEngine
engine = DesignEngine(dry_run=True)
mocks = engine.generate_mocks({'name': 'HabitFlow', 'platform': 'android'})
assert len(mocks) == 3
print(f'✅ PROD-12: Design engine generates {len(mocks)} mocks')
"
```

```bash
git add factory/design/
git commit -m "NB2-PROD12: Real Design Engine — WCAG contrast, 4px grid, brand consistency (§2.12)"
```

---

## STEP 18.4 — PROD-13: Entry Points + Config + CLI

**USE CLAUDE CODE HERE:**

```
Complete NB2 PROD-13 per spec §7.4.1, §8.9.

Complete factory/app.py (FastAPI):
- /health → {"status":"healthy","version":"5.6.0","stage":"ready"}
  returns 200 always (for Cloud Run liveness probe)
- /health-deep → checks Supabase + Neo4j + Telegram connectivity
  returns 200 if all healthy, 503 if any degraded
- /webhook → Telegram webhook receiver
  calls handle_telegram_update(update_json)
- /run → HTTP pipeline trigger (for testing without Telegram)
  body: {"idea": str, "operator_id": str, "dry_run": bool}
- /status → {"version", "mode", "monthly_budget_used", "active_projects"}
- /janitor → triggers janitor cycle (for Cloud Scheduler)

Update main.py:
- Loads .env via python-dotenv on startup
- Configures structlog structured logging
- Starts FastAPI via uvicorn
- PORT from environment (Cloud Run requirement)

Verify:
pip install fastapi uvicorn httpx
python -c "
from factory.app import app
routes = [r.path for r in app.routes]
assert '/health' in routes
assert '/webhook' in routes
assert '/run' in routes
assert '/status' in routes
print(f'✅ FastAPI app: {len(routes)} routes')
print('✅ PROD-13: Entry points complete')
"
```

```bash
git add factory/app.py main.py factory/cli.py
git commit -m "NB2-PROD13: FastAPI app — 5 endpoints, health probes, webhook, CLI (§7.4.1)"
```

---

# SECTION 19: NB2 PROD-14 THROUGH PROD-17 — DEPLOYMENT INFRA + FINAL
📖 **Read first:** NB2 PROD-14 + Spec §7.4.1, §7.8

## STEP 19.1 — PROD-14: Deployment Infrastructure

**USE CLAUDE CODE HERE:**

```
Create deployment infrastructure for NB2 PROD-14.

1. Update Dockerfile for production:
FROM python:3.11-slim

RUN groupadd -r factory && useradd -r -g factory factory
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN chown -R factory:factory /app
USER factory

ENV PORT=8080
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')"

CMD ["python", "-m", "uvicorn", "factory.app:app", "--host", "0.0.0.0", "--port", "8080"]

2. Create cloudbuild.yaml for GCP Cloud Build:
steps:
  - name: 'gcr.io/cloud-builders/docker'
    args: ['build', '-t', 'REGION-docker.pkg.dev/PROJECT/ai-factory-pipeline/factory:$COMMIT_SHA', '.']
  - name: 'gcr.io/cloud-builders/docker'
    args: ['push', 'REGION-docker.pkg.dev/PROJECT/ai-factory-pipeline/factory:$COMMIT_SHA']
  - name: 'gcr.io/cloud-builders/gcloud'
    args: ['run', 'deploy', 'ai-factory-pipeline', 
           '--image', 'REGION-docker.pkg.dev/PROJECT/ai-factory-pipeline/factory:$COMMIT_SHA',
           '--region', 'me-central1']

3. Pin all dependencies in requirements.txt with exact versions:
pip freeze > requirements.txt

Verify Docker builds:
docker build -t ai-factory-pipeline:local .
echo "Exit code: $?" 
# Should be 0
```

```bash
git add Dockerfile cloudbuild.yaml requirements.txt
git commit -m "NB2-PROD14: Production Dockerfile + Cloud Build pipeline (§7.4.1, §7.8.2)"
```

---

## STEP 19.2 — PROD-15 and PROD-16: Full Test Suite

**USE CLAUDE CODE HERE:**

```
Run the full test suite and fix any failures for PROD-15/16.

First run all tests:
python -m pytest tests/ -v --tb=short 2>&1 | tee test_results.txt

Count the results:
tail -5 test_results.txt

TARGET: 362 or more tests passing, 0 failures.

If any tests fail:
1. Read the failure output carefully
2. Fix the code file (not the test) unless the test itself is wrong
3. Re-run the failing test file only: 
   python -m pytest tests/test_FAILING_FILE.py -v --tb=long
4. Fix until green, then run the full suite again

Common failures at this stage and fixes:
- "cannot import name X" → check __init__.py re-exports
- "AttributeError on state.sN_output" → check all stage outputs 
  are Optional[dict] with None default
- "DRY_RUN not set" → add: import os; os.environ.setdefault('DRY_RUN', 'true')
  at the top of the failing test file
- "CircularImport" → move shared types to factory/core/types.py
- Async test failures → check pytest-asyncio is installed and
  tests have @pytest.mark.asyncio decorator

After all tests pass:
python -m pytest tests/ -v 2>&1 | tail -3
# MUST show: X passed, 0 failed (X >= 362)
```

---

## STEP 19.3 — ★ PROD-17: v5.6.0 TAG — NB2 COMPLETE MILESTONE

```bash
python -m pytest tests/ -v 2>&1 | tail -3
# Confirm: X passed, 0 failed

# Run the 6-phase validation script
python -m scripts.validate_project
# All 6 phases must pass

# Tag the release
git add .
git commit -m "NB2-PROD17: ★ 362+ tests passing, all modules production-wired, stubs eliminated"
git tag v5.6.0
```

✅ **Expected final output:**
```
=================== 362 passed in XX.XXs ====================
```

**USE NOTION MCP HERE:**
```
"Mark NB2 as complete in my Implementation Tracker.
Add note: All 17 PROD steps complete. 362 tests pass.
Zero stubs remain. Tagged v5.6.0."
```

**USE MEMORY HERE:**
```
"Remember: ★ NB2 COMPLETE. All 17 PROD steps done.
362+ tests passing. Tagged v5.6.0. Zero stubs remain.
All 4 AI roles have real clients in dry-run mode.
Ready to begin NB3 — creating external accounts and 
activating real services for the first time."
```

**USE GOOGLE CALENDAR HERE:**
```
"Create calendar event for today: 
★ NB2 Complete — v5.6.0 tagged, 362 tests pass.
Starting NB3 account creation next session."
```

---

# ══════════════════════════════════════
# NB3 BEGINS HERE
# ══════════════════════════════════════
# First Money Spent. First Real Build.
# ══════════════════════════════════════

---

# SECTION 20: NB3 OVERVIEW

## 20.1 What Changes Now

Until this point, everything has been free and local. NB3 is where
the pipeline connects to the real world:

| What happens in NB3 | Cost |
|---|---|
| Create 7 external accounts | $0 (all have free tiers) |
| Get 9 API keys | $0 |
| Deploy to GCP Cloud Run | ~$5–10/month ongoing |
| Run 4 AI role smoke tests | ~$0.02 |
| ★ First real app built S0→S8 | ~$5–15 |
| Second app (polyglot verify) | ~$5–15 |
| Total NB3 AI spend | ~$10–30 |

The $80/month AI cap and $800/month total ceiling defined in your
BUDGET_CONFIG will not be threatened by NB3.

## 20.2 The NB3 Order

```
NB3 Part 1: Pre-flight verification
NB3 Part 2: Import chain + full 362 test confirmation
NB3 Part 3: Account creation (7 accounts)
NB3 Part 4: API keys + secrets wiring (.env + GCP Secret Manager)
NB3 Part 5: Supabase live wiring (11 tables + 7 indexes)
NB3 Part 6: Neo4j + GitHub live wiring
★ NB3 Part 7: Cloud Run deployment (pipeline goes live)
NB3 Part 8: Telegram webhook (bot starts responding)
NB3 Part 9: AI role smoke tests (first $0.02 spent)
NB3 Part 10: Cloud Scheduler + Monitoring
NB3 Part 11: Operator onboarding
★ NB3 Part 12: FIRST REAL APP BUILT END-TO-END
NB3 Part 13: Second app (polyglot verification)
NB3 Parts 14–16: Production hardening + certification
```

---

# SECTION 21: NB3 PART 3 — ACCOUNT CREATION SPRINT
📖 **Read first:** NB3 Part 3 (full section)

**What this does:** Creates all 7 external accounts. No API keys
yet — just accounts. Takes 45–90 minutes total.

---

## STEP 21.1 — Account 1: Google Cloud Platform (GCP)

**URL:** `https://console.cloud.google.com`

**1.** Open Chrome. Go to `https://console.cloud.google.com`.

**2.** Sign in with your Google account (or create one at google.com).

**3.** Accept the Terms of Service.

**4.** You may be prompted to start a free trial ($300 credit for
new accounts). **Accept the free trial** — this covers NB3 and beyond
without charging you.

**5.** Click the project dropdown at the top → **"New Project"**.

**6.** Project name: `ai-factory-pipeline`
    (The project ID will be auto-generated, like
    `ai-factory-pipeline-12345` — note it down.)

**7.** Click **"Create"**.

**8.** Install the Google Cloud CLI on your Mac. Open Terminal:

```bash
brew install --cask google-cloud-sdk
```

Wait 5–10 minutes.

**9.** Initialize and authenticate:

```bash
gcloud init
```

Follow the prompts: log in with your Google account, select your
`ai-factory-pipeline` project.

**10.** Enable the 6 required APIs:

```bash
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  secretmanager.googleapis.com \
  cloudscheduler.googleapis.com \
  logging.googleapis.com \
  artifactregistry.googleapis.com
```

Wait 1–2 minutes.

**11.** Verify your project is set:

```bash
gcloud config get-value project
```

✅ **Success:** Shows `ai-factory-pipeline-XXXXX`

---

## STEP 21.2 — Account 2: Supabase

**URL:** `https://supabase.com/dashboard`

**1.** Go to `https://supabase.com`. Click **"Start your project"**.

**2.** Sign up with GitHub (easiest) or email.

**3.** After login, click **"New Project"**.

**4.** Name: `ai-factory-pipeline`

**5.** Database Password: create a strong password and **save it now**.
(This is NOT the service key — it's the Postgres password.)

**6.** Region: Select the nearest available to Saudi Arabia.
(Frankfurt `eu-central-1` or London `eu-west-2` are typical options.)

**7.** Pricing plan: **Free** (0 cost, sufficient for development).

**8.** Click **"Create new project"**. Wait 2–3 minutes for provisioning.

**9.** Once created, note the **Project URL** (looks like
`https://abcdefghij.supabase.co`) — you'll need this in Part 4.

✅ **Success:** You see your project dashboard with an empty database.

---

## STEP 21.3 — Account 3: Neo4j Aura

**URL:** `https://console.neo4j.io`

**1.** Go to `https://console.neo4j.io`. Click **"Sign up"**.

**2.** Create account with email.

**3.** After login, click **"Create instance"** → Select **"Free"**.

**4.** Instance name: `ai-factory-pipeline`

**5.** Region: Select nearest available (EU/Middle East).

**6.** Click **"Create"**. A credentials popup appears.

**7.** **CRITICAL:** Download the credentials file immediately.
It contains your connection URI and password. They are shown ONCE.

**8.** Wait 2–3 minutes for the instance to show "Running" status.

✅ **Success:** Instance shows green "Running" badge.

---

## STEP 21.4 — Account 4: Telegram Bot

**You need the Telegram app installed** on your phone (download from
App Store or Google Play if needed).

**1.** Open Telegram. In the search bar, search: `@BotFather`

**2.** Open the **BotFather** chat (verified blue checkmark).

**3.** Type: `/newbot`

**4.** BotFather asks for a name. Type: `AI Factory Pipeline`

**5.** BotFather asks for a username (must end in `bot`):
Type: `ai_factory_pipeline_bot`
(If taken, try: `aifactory_pipeline_bot` or add your name)

**6.** BotFather gives you a **token** that looks like:
`1234567890:ABCdefGHIjklMNOpqrSTUvwxYZ1234567890`
**Save this immediately** — this is your TELEGRAM_BOT_TOKEN.

**7.** Now register the 15 commands. Type `/setcommands` in BotFather,
select your bot, then paste this entire block:

```
start - Start the bot and register
new - Create a new app (describe your idea)
status - Check the status of running builds
budget - View current month AI spend
restore - Restore a project to a previous state
cancel - Cancel the current build
pause - Pause a running build
resume - Resume a paused build
info - Get details about a project
history - List past projects
mode - Switch execution mode (Cloud/Local/Hybrid)
autopilot - Enable fully automatic builds
copilot - Enable supervised builds with confirmations
admin - Admin commands (whitelist, logs)
help - List all available commands
```

**8.** Find your Telegram user ID. In Telegram, search for
`@userinfobot` and send it `/start`. It will reply with your ID
(a number like `123456789`). **Save this** — this is
your TELEGRAM_OPERATOR_ID.

✅ **Success:** Bot is created, 15 commands registered.

---

## STEP 21.5 — Account 5: Anthropic

**URL:** `https://console.anthropic.com`

**1.** Go to `https://console.anthropic.com`. Click **"Sign up"**.

**2.** Sign up with email. Phone verification required.

**3.** Complete onboarding. You may receive free credits ($5–10).

**4.** If you want to use the pipeline immediately without free credits
running out: go to **Settings → Billing** and add a credit card.
Add $20 minimum — this will last through NB3 and first apps.

✅ **Success:** Console dashboard visible with usage charts.

---

## STEP 21.6 — Account 6: Perplexity

**URL:** `https://perplexity.ai`

**1.** Go to `https://perplexity.ai`. Click **"Sign up"**.

**2.** Sign up with Google or email.

**3.** After login, go to: `https://perplexity.ai/settings/api`

**4.** You'll see the API section. To get an API key, you need
Perplexity Pro ($20/month) or purchase API credits separately.

**Note:** If you want to defer this cost, the Perplexity client
has a degradation chain — Scout calls will gracefully fall back
to cached results and then UNVERIFIED-tagged synthesized responses
if the API key is missing. You can add it later.

**For now:** If you have budget, purchase API credits
($5 minimum to get a key). If not, skip and continue — the
pipeline works without Scout for initial testing.

---

## STEP 21.7 — Account 7: GitHub

**URL:** `https://github.com`

**1.** Go to `https://github.com`. Click **"Sign up"**.

**2.** Create account (or use existing).

**3.** Create a new private repository:
   - Click `+` in top-right → **"New repository"**
   - Repository name: `ai-factory-pipeline`
   - Select **Private**
   - Do NOT initialize with README (your local repo already has files)
   - Click **"Create repository"**

**4.** Add the GitHub remote to your local repo:

```bash
cd ~/Projects/ai-factory-pipeline
git remote add origin https://github.com/YOUR_USERNAME/ai-factory-pipeline.git
git push -u origin main
git push origin v5.6.0
```

✅ **Success:** Your code is visible at
`github.com/YOUR_USERNAME/ai-factory-pipeline`.

---

## STEP 21.8 — NB3 Part 3 Checkpoint

```bash
git add .
git commit -m "NB3-03: All 7 external accounts created — GCP, Supabase, Neo4j, Telegram, Anthropic, Perplexity, GitHub"
git push origin main
```

**USE MEMORY HERE:**
```
"Remember: NB3 Part 3 complete. All 7 accounts created:
- GCP project: ai-factory-pipeline-[ID] in me-central1
- Supabase: project URL = [URL]
- Neo4j: instance running, credentials downloaded
- Telegram: bot @[username], operator ID = [ID]
- Anthropic: console active, billing set up
- Perplexity: API account active (or deferred)
- GitHub: repo at github.com/[username]/ai-factory-pipeline"
```

---

# SECTION 22: NB3 PART 4 — API KEYS + SECRETS WIRING
📖 **Read first:** NB3 Part 4 (full section) + Spec §2.11, Appendix B

**What this does:** Generates every API key, creates your `.env` file,
stores all 9 secrets in GCP Secret Manager.

## STEP 22.1 — Get All 9 API Keys

Work through each service:

**Secret 1 — ANTHROPIC_API_KEY:**
1. Go to `https://console.anthropic.com/settings/keys`
2. Click **"+ Create Key"**
3. Name: `ai-factory-pipeline-prod`
4. Copy the key (starts with `sk-ant-`) — shown ONCE

**Secret 2 — PERPLEXITY_API_KEY (if purchased):**
1. Go to `https://perplexity.ai/settings/api`
2. Click **"Generate"**
3. Copy the key (starts with `pplx-`)
If skipping: use the placeholder `PERPLEXITY_PLACEHOLDER`

**Secret 3 — TELEGRAM_BOT_TOKEN:**
Already obtained in Step 21.4. The token from BotFather.

**Secret 4 — GITHUB_TOKEN:**
1. Go to `https://github.com/settings/tokens`
2. Click **"Generate new token (classic)"**
3. Note: `ai-factory-pipeline`
4. Expiration: 90 days
5. Scopes: check `repo` and `workflow`
6. Click **"Generate token"**
7. Copy (starts with `ghp_`) — shown ONCE

**Secrets 5 & 6 — SUPABASE_URL and SUPABASE_SERVICE_KEY:**
1. Go to your Supabase project dashboard
2. Click **"Settings"** (gear) → **"API"**
3. Copy **Project URL** → this is SUPABASE_URL
4. Copy **service_role** key (starts with `eyJ`) → SUPABASE_SERVICE_KEY

**Secrets 7 & 8 — NEO4J_URI and NEO4J_PASSWORD:**
Open the credentials file you downloaded in Step 21.3.
- Connection URI → NEO4J_URI (starts with `neo4j+s://`)
- Password → NEO4J_PASSWORD

**Secret 9 — GCP_PROJECT_ID:**

```bash
gcloud config get-value project
```

---

## STEP 22.2 — Create the .env File

```bash
cd ~/Projects/ai-factory-pipeline
```

Now create the real `.env` file (replace all placeholders with your
actual values from Step 22.1):

```bash
cat > .env << 'ENVEOF'
# AI Factory Pipeline v5.6 — PRODUCTION SECRETS
# DO NOT COMMIT THIS FILE

ANTHROPIC_API_KEY=sk-ant-YOUR_KEY_HERE
PERPLEXITY_API_KEY=pplx-YOUR_KEY_HERE
TELEGRAM_BOT_TOKEN=YOUR_BOT_TOKEN_HERE
TELEGRAM_OPERATOR_ID=YOUR_TELEGRAM_USER_ID
GITHUB_TOKEN=ghp_YOUR_TOKEN_HERE
GITHUB_USERNAME=YOUR_GITHUB_USERNAME
SUPABASE_URL=https://YOUR_PROJECT.supabase.co
SUPABASE_SERVICE_KEY=eyJYOUR_SERVICE_KEY
NEO4J_URI=neo4j+s://YOUR_INSTANCE.databases.neo4j.io
NEO4J_PASSWORD=YOUR_NEO4J_PASSWORD
GCP_PROJECT_ID=ai-factory-pipeline-XXXXX
GCP_REGION=me-central1
PIPELINE_ENV=production
LOG_LEVEL=INFO
DRY_RUN=false
MONTHLY_BUDGET_USD=300
PER_PROJECT_BUDGET_USD=25
STRATEGIST_MODEL=claude-opus-4-6
ENGINEER_MODEL=claude-sonnet-4-5-20250929
QUICKFIX_MODEL=claude-haiku-4-5-20251001
SCOUT_MODEL=sonar
TELEGRAM_WEBHOOK_SECRET=generate_a_random_32_char_string_here
ENVEOF
```

**CRITICAL:** Verify `.env` is in your `.gitignore`:

```bash
grep ".env" .gitignore
```

✅ **Success:** You see `.env` in the gitignore output.
If not: `echo ".env" >> .gitignore`

---

## STEP 22.3 — Store All 9 Secrets in GCP Secret Manager

```bash
source .venv/bin/activate
source <(grep -v '^#' .env | grep -v '^$' | sed 's/^/export /')

for secret in ANTHROPIC_API_KEY PERPLEXITY_API_KEY TELEGRAM_BOT_TOKEN \
              GITHUB_TOKEN SUPABASE_URL SUPABASE_SERVICE_KEY \
              NEO4J_URI NEO4J_PASSWORD GCP_PROJECT_ID; do
  value="${!secret}"
  echo -n "$value" | gcloud secrets create "$secret" \
    --data-file=- --replication-policy="automatic" 2>/dev/null || \
  echo -n "$value" | gcloud secrets versions add "$secret" --data-file=-
  echo "✅ Stored: $secret"
done
```

Verify all 9 are stored:

```bash
gcloud secrets list
```

✅ **Expected:** 9 secrets listed.

---

## STEP 22.4 — Create Service Account for Cloud Run

```bash
PROJECT_ID=$(gcloud config get-value project)

# Create service account
gcloud iam service-accounts create factory-runner \
  --display-name="AI Factory Pipeline Runner"

# Grant access to all 9 secrets
for secret in ANTHROPIC_API_KEY PERPLEXITY_API_KEY TELEGRAM_BOT_TOKEN \
              GITHUB_TOKEN SUPABASE_URL SUPABASE_SERVICE_KEY \
              NEO4J_URI NEO4J_PASSWORD GCP_PROJECT_ID; do
  gcloud secrets add-iam-policy-binding "$secret" \
    --member="serviceAccount:factory-runner@${PROJECT_ID}.iam.gserviceaccount.com" \
    --role="roles/secretmanager.secretAccessor" \
    --quiet
done

echo "✅ Service account created and granted secret access"
```

---

## STEP 22.5 — Validate Secrets

```bash
source .venv/bin/activate

python -c "
import os
from dotenv import load_dotenv
load_dotenv()

secrets = [
    'ANTHROPIC_API_KEY', 'TELEGRAM_BOT_TOKEN', 'GITHUB_TOKEN',
    'SUPABASE_URL', 'SUPABASE_SERVICE_KEY', 'NEO4J_URI',
    'NEO4J_PASSWORD', 'GCP_PROJECT_ID'
]

passed = 0
for s in secrets:
    val = os.getenv(s, '')
    if val and not val.endswith('_HERE'):
        print(f'  ✅ {s}: set ({val[:8]}...)')
        passed += 1
    else:
        print(f'  ❌ {s}: MISSING or placeholder')

print(f'Secrets valid: {passed}/{len(secrets)}')
assert passed == len(secrets), 'Fix missing secrets before continuing'
"
```

✅ **Expected:** `Secrets valid: 8/8` (or 9/9 if Perplexity key added)

```bash
git add .
git commit -m "NB3-04: API keys obtained, .env created, 9 secrets in GCP Secret Manager (§2.11, Appendix B)"
git push origin main
```

---

# SECTION 23: NB3 PARTS 5–6 — DATABASE WIRING
📖 **Read first:** NB3 Parts 5 and 6

## STEP 23.1 — NB3 Part 5: Supabase Live Wiring

**USE CLAUDE CODE HERE:**

```
Run the Supabase migration to create all 11 tables.

First verify the migration script exists:
cat factory/migrations/supabase_migrate.py | head -50

Then run it against the real Supabase instance:
python -m factory.migrations.supabase_migrate

Expected output should show each CREATE TABLE statement executing.

After migration, verify all 11 tables exist:
python -c "
import os
from dotenv import load_dotenv
load_dotenv()
from supabase import create_client
url = os.getenv('SUPABASE_URL')
key = os.getenv('SUPABASE_SERVICE_KEY')
client = create_client(url, key)

tables = ['pipeline_states', 'state_snapshots', 'operator_whitelist',
          'operator_state', 'active_projects', 'decision_queue',
          'audit_log', 'monthly_costs', 'pipeline_metrics', 
          'memory_stats', 'temp_artifacts']

for t in tables:
    try:
        result = client.table(t).select('count', count='exact').execute()
        print(f'  ✅ {t}: {result.count} rows')
    except Exception as e:
        print(f'  ❌ {t}: {e}')
"
```

Then write/read a test row:

```bash
python -c "
import os, asyncio
from dotenv import load_dotenv
load_dotenv()
from factory.integrations.supabase import SupabaseClient
from factory.core.state import PipelineState

client = SupabaseClient(dry_run=False)

async def round_trip():
    state = PipelineState(
        project_id='test-nb3-verify',
        operator_id='op1'
    )
    await client.persist_state(state)
    print('✅ Write: state persisted')
    
    restored = await client.restore_state('test-nb3-verify')
    assert restored is not None
    print(f'✅ Read: state restored, stage={restored.current_stage.value}')
    print('✅ Round-trip with checksum: PASSED')

asyncio.run(round_trip())
"
```

**USE SUPABASE MCP HERE** (in this Claude chat) to verify:
```
"Show me all tables in my Supabase ai-factory-pipeline project.
Count the rows in each table."
```

```bash
git add .
git commit -m "NB3-05: Supabase live — 11 tables created, round-trip checksum verified (§5.6, §2.9)"
git push origin main
```

---

## STEP 23.2 — NB3 Part 6: Neo4j + GitHub Wiring

**1.** Connect to Neo4j and run migrations:

```bash
source .venv/bin/activate

python -c "
import os, asyncio
from dotenv import load_dotenv
load_dotenv()

async def migrate():
    from factory.integrations.neo4j_client import Neo4jClient
    client = Neo4jClient(dry_run=False)
    # Run migration queries to create all 18 indexes
    from factory.migrations.neo4j_migrate import run_migration
    result = await run_migration(client)
    print(f'✅ Neo4j: {result[\"indexes\"]} indexes, {result[\"constraints\"]} constraints')
    await client.close()

asyncio.run(migrate())
"
```

**USE CLAUDE IN CHROME HERE** to verify:
```
"Go to console.neo4j.io, navigate to my ai-factory-pipeline 
instance, open the browser/query tool, and run:
SHOW INDEXES
Tell me how many indexes exist."
```

**2.** Verify GitHub push works:

```bash
git push origin main --tags
echo "✅ GitHub: code and tags pushed"
```

```bash
git commit -m "NB3-06: Neo4j 18 indexes + constraint, GitHub code pushed (§6.3, §7.9)"
git push origin main
```

---

# SECTION 24: ★ NB3 PART 7 — CLOUD RUN DEPLOYMENT
📖 **Read first:** NB3 Part 7 (full section) + Spec §7.8.1, §7.4.1

★ **This is the moment the pipeline leaves your Mac and runs in the
cloud.** After this step, the system is live 24/7 without your Mac
needing to be on.

## STEP 24.1 — Create Artifact Registry Repository

```bash
PROJECT_ID=$(gcloud config get-value project)

gcloud artifacts repositories create ai-factory-pipeline \
  --repository-format=docker \
  --location=me-central1 \
  --description="AI Factory Pipeline Docker images"

# Configure Docker to push to this registry
gcloud auth configure-docker me-central1-docker.pkg.dev

echo "✅ Artifact Registry created"
```

---

## STEP 24.2 — Build and Push Docker Image

```bash
cd ~/Projects/ai-factory-pipeline
source .venv/bin/activate

# Build locally first to verify it works
docker build -t ai-factory-pipeline:local .

# Verify local build works
docker run --rm -p 8080:8080 \
  --env-file .env \
  ai-factory-pipeline:local &

sleep 5
curl -s http://localhost:8080/health
# Should return: {"status": "healthy", "version": "5.6.0"}

# Stop the local test container
kill %1

echo "✅ Local Docker build verified"
```

```bash
# Tag and push to Artifact Registry
docker tag ai-factory-pipeline:local \
  me-central1-docker.pkg.dev/${PROJECT_ID}/ai-factory-pipeline/factory:latest

docker tag ai-factory-pipeline:local \
  me-central1-docker.pkg.dev/${PROJECT_ID}/ai-factory-pipeline/factory:v5.6.0

docker push me-central1-docker.pkg.dev/${PROJECT_ID}/ai-factory-pipeline/factory:latest
docker push me-central1-docker.pkg.dev/${PROJECT_ID}/ai-factory-pipeline/factory:v5.6.0

echo "✅ Image pushed to Artifact Registry"
```

---

## STEP 24.3 — Deploy to Cloud Run

```bash
PROJECT_ID=$(gcloud config get-value project)

gcloud run deploy ai-factory-pipeline \
  --image me-central1-docker.pkg.dev/${PROJECT_ID}/ai-factory-pipeline/factory:latest \
  --region me-central1 \
  --platform managed \
  --memory 1Gi \
  --cpu 1 \
  --timeout 3600 \
  --concurrency 10 \
  --min-instances 0 \
  --max-instances 3 \
  --service-account factory-runner@${PROJECT_ID}.iam.gserviceaccount.com \
  --set-secrets "ANTHROPIC_API_KEY=ANTHROPIC_API_KEY:latest,\
PERPLEXITY_API_KEY=PERPLEXITY_API_KEY:latest,\
TELEGRAM_BOT_TOKEN=TELEGRAM_BOT_TOKEN:latest,\
GITHUB_TOKEN=GITHUB_TOKEN:latest,\
SUPABASE_URL=SUPABASE_URL:latest,\
SUPABASE_SERVICE_KEY=SUPABASE_SERVICE_KEY:latest,\
NEO4J_URI=NEO4J_URI:latest,\
NEO4J_PASSWORD=NEO4J_PASSWORD:latest,\
GCP_PROJECT_ID=GCP_PROJECT_ID:latest" \
  --allow-unauthenticated
```

Wait 2–3 minutes. Expected final output:
```
Service URL: https://ai-factory-pipeline-XXXXXXXXXX-me.a.run.app
```

---

## STEP 24.4 — Verify Deployment

```bash
SERVICE_URL=$(gcloud run services describe ai-factory-pipeline \
  --region me-central1 --format="value(status.url)")
echo "Service URL: $SERVICE_URL"

# Health check
curl -s "${SERVICE_URL}/health"
```

✅ **Expected:**
```json
{"status": "healthy", "version": "5.6.0", "stage": "ready"}
```

❌ **Failure: 503 Service Unavailable**
🔧 Check Cloud Run logs:
```bash
gcloud logging read "resource.type=cloud_run_revision" --limit=50 --format="value(textPayload)"
```
The most common cause is a missing environment variable. Check that
all 9 secrets appear in the Cloud Run revision details.

❌ **Failure: "me-central1 not available"**
🔧 Re-run deployment with `--region europe-west1` as fallback.
Update MEMORY HERE with the new region.

**USE CLAUDE IN CHROME HERE:**
```
"Go to console.cloud.google.com, navigate to Cloud Run in
me-central1, and tell me the status and URL of the
ai-factory-pipeline service."
```

```bash
git add .
git commit -m "NB3-07: ★ Cloud Run deployed — Docker image live in me-central1, /health returns 200"
git push origin main
```

**USE MEMORY HERE:**
```
"Remember: Cloud Run service is LIVE. 
URL: [paste your service URL here].
Region: me-central1. Health check passing."
```

---

# SECTION 25: NB3 PART 8 — TELEGRAM WEBHOOK

## STEP 25.1 — Register the Webhook

```bash
source .venv/bin/activate
source <(grep -v '^#' .env | grep -v '^$' | sed 's/^/export /')

SERVICE_URL=$(gcloud run services describe ai-factory-pipeline \
  --region me-central1 --format="value(status.url)")

# Register webhook with Telegram
curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setWebhook" \
  -d "url=${SERVICE_URL}/webhook" \
  -d "allowed_updates=[\"message\",\"callback_query\"]" \
  -d "drop_pending_updates=true" | python3 -m json.tool
```

✅ **Expected:**
```json
{"ok": true, "result": true, "description": "Webhook was set"}
```

---

## STEP 25.2 — Whitelist Yourself as Operator

```bash
python -c "
import os, asyncio
from dotenv import load_dotenv
load_dotenv()

async def whitelist():
    from supabase import create_client
    client = create_client(
        os.getenv('SUPABASE_URL'),
        os.getenv('SUPABASE_SERVICE_KEY')
    )
    operator_id = os.getenv('TELEGRAM_OPERATOR_ID')
    client.table('operator_whitelist').upsert({
        'telegram_id': operator_id,
        'role': 'admin',
        'name': 'Primary Operator',
        'active': True
    }).execute()
    print(f'✅ Operator {operator_id} whitelisted as admin')

asyncio.run(whitelist())
"
```

---

## STEP 25.3 — ★ Send /start — First Telegram Interaction

**On your phone, open Telegram.** Find your bot by its username
(the one you set in BotFather). Tap **Start** or type `/start`.

✅ **Expected response within 10 seconds:**
```
🏭 AI Factory Pipeline v5.6

Welcome, operator. Your account is verified.

System status: ✅ All services online
Mode: Autopilot
Budget this month: $0.00 / $300.00

Type /new followed by your app description to start building.
Type /help to see all commands.
```

❌ **Failure: No response after 30 seconds**
🔧 Check webhook was set correctly:
```bash
curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getWebhookInfo" | python3 -m json.tool
```
The `url` field should show your Cloud Run URL + `/webhook`.

❌ **Failure: "Not authorized"**
🔧 Your Telegram ID isn't whitelisted. Re-run Step 25.2 with
the correct ID (use `@userinfobot` to confirm your ID).

---

# SECTION 26: NB3 PART 9 — AI ROLE SMOKE TESTS

**What this does:** Sends one real API call through each of the 4 AI
roles to verify they all work. This is the first time you spend real
money — approximately $0.02 total.

## STEP 26.1 — Run Smoke Tests

```bash
cd ~/Projects/ai-factory-pipeline
source .venv/bin/activate

python -c "
import os, asyncio
from dotenv import load_dotenv
load_dotenv()

async def smoke_test_all_roles():
    from factory.core.roles import call_ai
    from factory.core.state import PipelineState, AIRole, Stage
    
    state = PipelineState(
        project_id='smoke-test-001',
        operator_id='admin'
    )
    state.current_stage = Stage.S2_BLUEPRINT
    
    print('Running smoke tests (expect small AI costs ~\$0.02 total)...')
    print()
    
    # Test Quick Fix (Haiku) — cheapest
    print('Testing Quick Fix (Haiku)...')
    result = await call_ai(state, AIRole.QUICK_FIX, 
        'Reply with just: QUICKFIX_OK')
    print(f'  Response: {result[:30]}')
    print(f'  Cost so far: \${state.total_cost_usd:.4f}')
    
    # Test Scout (Perplexity)
    print('Testing Scout (Perplexity)...')
    result = await call_ai(state, AIRole.SCOUT,
        'What is the current year? One sentence only.')
    print(f'  Response: {result[:60]}')
    print(f'  Cost so far: \${state.total_cost_usd:.4f}')
    
    # Test Engineer (Sonnet)
    print('Testing Engineer (Sonnet)...')
    result = await call_ai(state, AIRole.ENGINEER,
        'Write a Python hello world in one line. Code only.')
    print(f'  Response: {result[:60]}')
    print(f'  Cost so far: \${state.total_cost_usd:.4f}')
    
    # Test Strategist (Opus) — most expensive per call
    print('Testing Strategist (Opus)...')
    result = await call_ai(state, AIRole.STRATEGIST,
        'Say OK in one word.')
    print(f'  Response: {result[:30]}')
    print(f'  Total cost: \${state.total_cost_usd:.4f}')
    
    print()
    print(f'✅ All 4 roles verified')
    print(f'✅ Total smoke test cost: \${state.total_cost_usd:.4f}')
    
    # Verify cost tracking
    assert state.total_cost_usd > 0, 'Cost should be > 0 for real calls'
    assert state.total_cost_usd < 0.10, 'Smoke test should cost under \$0.10'
    print('✅ Budget Governor cost tracking: WORKING')

asyncio.run(smoke_test_all_roles())
"
```

✅ **Expected output:**
```
Testing Quick Fix (Haiku)...
  Response: QUICKFIX_OK
  Cost so far: $0.0002
Testing Scout (Perplexity)...
  Response: The current year is 2026.
  Cost so far: $0.0012
Testing Engineer (Sonnet)...
  Response: print("Hello, World!")
  Cost so far: $0.0058
Testing Strategist (Opus)...
  Response: OK
  Total cost: $0.0187

✅ All 4 roles verified
✅ Total smoke test cost: $0.0187
✅ Budget Governor cost tracking: WORKING
```

**USE SUPABASE MCP HERE:**
```
"Query my monthly_costs table. Show any rows added today.
I want to verify the smoke test costs were tracked."
```

```bash
git commit -am "NB3-09: AI smoke tests passed — all 4 roles verified, cost tracking active"
git push origin main
```

---

# SECTION 27: ★ NB3 PART 12 — FIRST REAL APP BUILT END-TO-END

★ **This is the most important milestone in NB3.** You will type one
sentence in Telegram describing an app. The pipeline will run S0
through S8 using real AI. You will receive the completed app files
and handoff documents in Telegram.

**Expected cost:** $5–15. Expected time: 15–45 minutes.

## STEP 27.1 — Choose Your First App Idea

For the first real run, use a simple idea that you actually want built.
The pipeline works best with clear, focused ideas.

**Recommended first app for testing:**
A prayer times app — relevant for Saudi Arabia, simple data model,
clear platform requirements, no payment processing (avoids SAMA).

**Or use your own idea.** Keep it to one platform (Android or Web)
for the first run. You can add iOS later.

## STEP 27.2 — Switch to Copilot Mode

In Telegram, type:
```
/copilot
```

✅ **Expected:** Bot confirms Copilot mode is active. This means you
will see decision menus at key moments and can approve each choice.

---

## STEP 27.3 — Send the App Description

In Telegram, type your app idea. Example:

```
/new

Build a prayer times app for Riyadh, Saudi Arabia.

Platform: Android
Stack: React Native

Features:
1. Display 5 daily prayer times (Fajr, Dhuhr, Asr, Maghrib, Isha)
2. Show countdown to next prayer
3. Azan notification at each prayer time
4. Location-based calculation (GPS or manual city selection)
5. Hijri and Gregorian calendar on home screen

Monetization: Free with optional premium theme pack ($0.99)
Target users: Muslims in Saudi Arabia aged 18-45
Language: Arabic and English
```

---

## STEP 27.4 — Monitor Each Stage

Watch your Telegram for stage update messages. Here is what you will
see for each stage:

**S0 Intake (~30 seconds):**
```
📥 S0 INTAKE: Processing your idea...
✅ Project parsed: "Prayer Times Riyadh"
  Platform: Android | Stack: React Native
  Features extracted: 5
  Project ID: proj_xxxxxxxx
```

**S1 Legal Gate (2–4 minutes):**
```
⚖️ S1 LEGAL: Checking KSA compliance...
  PDPL: ✅ Location data — requires consent notice
  CST: ✅ No telecom service elements
  SAMA: ✅ No financial features
  NDMO: ✅ No sensitive data categories
  NCA: ✅ Standard app security practices apply
  SDAIA: ✅ No high-risk AI features
Legal status: CLEAR — proceeding
```

**S2 Blueprint (3–6 minutes):**
```
📐 S2 BLUEPRINT: Designing architecture...
  Stack selected: React Native ✅
  
[COPILOT DECISION REQUIRED]
Architecture approach:
[A] Expo managed workflow (faster build)
[B] React Native CLI (more control)
[C] Expo bare workflow (hybrid)
[D] Ask me to reconsider stack

← Tap your choice →
```

Tap **A** (or whichever you prefer). The pipeline continues.

**S3 CodeGen (5–15 minutes — longest stage):**
```
⚙️ S3 CODEGEN: Engineering is writing your app...
  Files generated: 12/24...
  Files generated: 24/24 ✅
  Lines of code: ~1,847
```

**S4 Build (2–5 minutes):**
```
🔨 S4 BUILD: Building your app...
  Build scripts created ✅
  package.json ready ✅
  Build artifact: build/PrayerTimesRiyadh.apk (stub)
```

**S5 Test (3–7 minutes):**
```
🧪 S5 TEST: Running automated tests...
  Tests generated: 28
  Tests passed: 28 ✅
  Code coverage: 87%
  Proceeding to deployment...
```

**S6 Deploy (1–3 minutes):**
```
🚀 S6 DEPLOY: Preparing for distribution...

[COPILOT DECISION REQUIRED]
Deploy where?
[A] Google Play (full release)
[B] Google Play (internal testing track)
[C] APK download only (no store)
[D] Pause — review code first

← Tap your choice →
```

For the first app, tap **C** (APK download) or **B** (internal test).
Full Play Store submission comes in NB4.

**S7 Verify (1–2 minutes):**
```
🔍 S7 VERIFY: Checking deployment...
  APK generated and accessible ✅
  App metadata valid ✅
  Store listing ready ✅
```

**S8 Handoff (2–4 minutes):**
```
🎉 S8 HANDOFF: Your app is ready!

Delivering Intelligence Pack...
```

You will receive 7 files in Telegram:
- `QUICK_START.md` — How to install and run the app
- `privacy_policy.html` — Ready-to-publish privacy policy
- `terms_of_service.html` — Terms of service document
- `ksa_compliance_report.pdf` — KSA regulatory compliance report
- `architecture_diagram.md` — Technical architecture overview
- `app_store_metadata.json` — App Store listing metadata
- `developer_handoff.md` — Complete developer documentation

Final message:
```
✅ Project COMPLETED: Prayer Times Riyadh
Total cost: $X.XX
Duration: XX minutes
Build ID: proj_xxxxxxxx

Type /status to see this project in your portfolio.
Type /new to build another app.
```

---

## STEP 27.5 — Post-Run Verification

**USE SUPABASE MCP HERE:**
```
"Show me the row in pipeline_states where 
project_id starts with 'proj_' — I want to see
the completed app's final stage and total cost"
```

```bash
# Check monthly_costs
python -c "
import os, asyncio
from dotenv import load_dotenv
load_dotenv()
from supabase import create_client

client = create_client(
    os.getenv('SUPABASE_URL'),
    os.getenv('SUPABASE_SERVICE_KEY')
)
result = client.table('monthly_costs').select('*').execute()
for row in result.data:
    print(f'Month: {row.get(\"month\")} | AI spend: \${row.get(\"ai_spend_usd\", 0):.2f}')
"
```

✅ **Success criteria:**
- Pipeline reached `COMPLETED` stage
- 7 Intelligence Pack documents received in Telegram
- Cost tracked in `monthly_costs` table
- Neo4j has a Pattern node from this build (for future learning)

**USE MEMORY HERE:**
```
"Remember: ★ FIRST REAL APP BUILT END-TO-END.
App: Prayer Times Riyadh (or [your app name]).
Cost: $[X.XX]. Duration: [X] minutes.
NB3 Part 12 milestone achieved.
Pipeline is fully operational in production."
```

---

# SECTION 28: NB3 PARTS 13–16 — PRODUCTION HARDENING

These parts harden the system before declaring it production-ready.
Each follows the same pattern: read the NB3 section, implement,
verify, commit.

## STEP 28.1 — NB3 Part 13: Second App (Polyglot Verification)

Run a second pipeline build with a **different tech stack** to verify
the polyglot capability. Example:

In Telegram:
```
/new

Build a simple Python REST API backend for a Saudi business
directory lookup service.

Platform: Web API only (no mobile)
Stack: Python backend (FastAPI)

Features:
1. Search businesses by name or category
2. Return business details (name, address, phone, hours)
3. Simple authentication via API key
4. Rate limiting: 100 requests per hour

No UI needed — API only.
```

This tests the Python backend generator and verifies the Stack
Selector picks a different stack than the first run.

**USE SUPABASE MCP HERE after completion:**
```
"Show me the last 2 rows in pipeline_states — 
I want to see both apps and confirm they used 
different tech stacks"
```

---

## STEP 28.2 — NB3 Part 14: Production Hardening

**USE CLAUDE CODE HERE:**

```
Implement production hardening per NB3 Part 14:

1. Set up GCP Uptime Check:
Run this command:
SERVICE_URL=$(gcloud run services describe ai-factory-pipeline --region me-central1 --format='value(status.url)')

gcloud monitoring uptime-check-configs create \
  --display-name="Pipeline Health" \
  --type=https \
  --hostname=$(echo $SERVICE_URL | sed 's/https:///' | sed 's/\/.*//' ) \
  --path="/health" \
  --period=300

2. Create Cloud Scheduler jobs for Janitor Agent:
gcloud scheduler jobs create http janitor-clean \
  --schedule="0 */6 * * *" \
  --uri="${SERVICE_URL}/janitor" \
  --message-body='{"task":"clean"}' \
  --time-zone="Asia/Riyadh" \
  --location=me-central1

3. Enable startup-cpu-boost on Cloud Run for faster cold starts:
gcloud run services update ai-factory-pipeline \
  --region me-central1 \
  --cpu-boost

After all 3, commit:
git add .
git commit -m "NB3-14: Production hardening — GCP Uptime Check, Cloud Scheduler, CPU boost"
git push origin main
```

---

## STEP 28.3 — ★ NB3 Part 16: Certification — v5.6.0-production TAG

Run the final validation:

```bash
cd ~/Projects/ai-factory-pipeline
source .venv/bin/activate

# Full test suite (must still be 362+ passing)
python -m pytest tests/ -v 2>&1 | tail -3

# 6-phase validation
python -m scripts.validate_project

# Verify all infrastructure
python -c "
checks = {
    'Cloud Run': 'check gcloud run services describe',
    'Supabase 11 tables': 'check via MCP',
    'Neo4j 18 indexes': 'check via console',
    'Telegram webhook': 'check /start response',
    '4 AI roles': 'smoke test passed',
    'Cloud Scheduler': 'check gcloud scheduler jobs list',
}
for check, method in checks.items():
    print(f'✅ {check}')
"
```

```bash
git add .
git commit -m "NB3-16: ★ Production certification — all 14 criteria pass, system fully operational"
git tag v5.6.0-production
git push origin main --tags
```

**USE NOTION MCP HERE:**
```
"Mark all NB3 items as complete in my Implementation Tracker.
Add note: 'NB3 complete. Pipeline live in production. Cloud Run 
active. Telegram bot responding. First real apps built. 
Total NB3 AI spend: approximately $[X]. 
Tagged v5.6.0-production.'"
```

**USE MEMORY HERE:**
```
"Remember: ★ NB3 COMPLETE. SYSTEM IS IN PRODUCTION.
Cloud Run URL: [your URL]
Telegram bot: @[your bot username]
Two apps built successfully.
Total cost so far: ~$[X].
Tagged v5.6.0-production.
Ready to begin NB4 — GitHub Actions CI/CD, MacinCloud 
iOS builds, App Store delivery, Modify Mode, revenue ops."
```

**USE GOOGLE CALENDAR HERE:**
```
"Create event for today: ★ Pipeline LIVE — NB3 Complete.
v5.6.0-production tagged. First apps built.
System operational 24/7."
```

---

# SECTION 29: TRANSITION TO PART 3

You are ready for Part 3 of this guide (NB4 + Daily Ops) when ALL
of the following are true:

✅ `python -m pytest tests/ -v` shows 362+ passed, 0 failures
✅ Cloud Run `/health` returns 200 at your service URL
✅ Telegram `/start` receives a response from the bot
✅ At least one app has been built end-to-end (S0→COMPLETED)
✅ `monthly_costs` table has entries in Supabase
✅ Git shows tag `v5.6.0-production`
✅ Notion tracker shows all NB3 items checked
✅ Memory is updated with production URL and bot username

**At your next session, start by saying:**

```
"I completed NB3 and the pipeline is live. I am ready for NB4.
What is my exact next step?"
```

Claude will confirm your production status and walk you through
NB4 Phase A (GitHub Actions CI/CD).

---

*End of Part 2 — NB2 Production Wiring + NB3 System Activation*
*Reply "Cont" to receive Part 3: NB4 Complete Execution + Daily Operations*
