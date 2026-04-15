# AI Factory Pipeline v5.8 — Safety & Rollback Runbook

**Spec authority:** §2.9 (Time-Travel), §2.14 (Budget Governor), §4.10 (Halt Handler)  
**Last updated:** 2026-04-12  
**Applies to:** All pipeline stages S0–S8, Telegram bot, infrastructure

---

## Quick Reference

| Situation | Command |
|---|---|
| Pipeline stuck / hung | `/cancel` → `/new <idea>` |
| Legal compliance halt | `/force_continue <reason>` or `/cancel` |
| Budget circuit breaker | `/admin budget_override <USD>` → `/continue` |
| Roll back to last snapshot | `/restore State_#N` (see `/snapshots`) |
| Stage produced bad output | `/restore State_#N` → `/continue` |
| War Room cannot fix | `/cancel` (preserves snapshots) |
| Bot unresponsive | Restart `python scripts/run_bot.py` |
| Code rollback (git) | `git checkout <tag>` (see tag table below) |

---

## 1. Git Tag Reference

Every stage wiring commit has a named tag for instant code rollback.

| Tag | Commit | What it includes |
|---|---|---|
| `pre-real-production-20260412` | `0c1f1ba` | Baseline before Phase 1 (safe restore point) |
| `S0-REAL` | `ab86ee5` | S0 Intake wired |
| `S1-REAL` | `4e1c1e6` | S1 Legal Gate + PDF generator |
| `S2-REAL` | `cc23e2f` | S2 Blueprint PDF + ADR + Design Package |
| `S3-REAL` | `8d14cb7` | S3 CodeGen + GitHub commit |
| `S4-REAL` | `8d14cb7` | S4 Build (verified real, no changes needed) |
| `S5-REAL` | `8d14cb7` | S5 Test (verified real, no changes needed) |
| `S6-REAL` | `8d14cb7` | S6 Deploy (verified real, no changes needed) |
| `S7-REAL` | `8d14cb7` | S7 Verify (verified real, no changes needed) |
| `S8-REAL` | `df526c6` | S8 Handoff + Neo4j sibling query |
| `PHASE2-REAL` | `60be9ab` | Telegram notifications + budget alerts |
| `PHASE3-REAL` | `deb9021` | +37 tests + S8 await fix |

### Roll back the entire codebase to pre-Phase 1

```bash
git stash                                    # save any local changes
git checkout pre-real-production-20260412   # detach HEAD at baseline
# OR to create a branch at that point:
git checkout -b rollback/pre-phase1 pre-real-production-20260412
```

### Roll back a single stage (surgical revert)

```bash
# Example: revert S1 PDF generator changes only
git revert 4e1c1e6 --no-commit   # stages the revert
git diff --cached                  # review what will change
git commit -m "revert: S1 PDF generation (rollback)"
```

### Roll back Phase 2 Telegram changes only

```bash
git revert 60be9ab --no-commit
git commit -m "revert: Phase 2 Telegram wiring (rollback)"
```

---

## 2. Operator Telegram Commands (Live Pipeline)

### 2.1 Pipeline Halts

**Legal halt** (`state.legal_halt = True`)

Triggered when: S1 detects high-severity compliance blockers with confidence > 0.7, or S1 Strategist returns `proceed: false`.

```
Operator receives:
⛔ Pipeline halted at S1_LEGAL
Reason: [FIX-06] Compliance blocker(s) at confidence 0.82: 2 issues
Options:
  /continue — Resume after resolving
  /force_continue — Override and proceed
  /cancel — Cancel this project

Recovery options:
  /force_continue I accept compliance risk for internal sandbox testing
  → Clears legal_halt, logs acceptance, resumes from current stage

  /cancel
  → Archives project, preserves all snapshots for audit
```

**Budget BLACK halt** (`BudgetExhaustedError`)

```
Operator receives:
⛔ Monthly budget EXHAUSTED (100%)
Pipeline HALTED. All activity stopped.
Resets on 2026-05-01

Recovery:
  /admin budget_override <new_USD_limit>
  → Raises ceiling, clears circuit breaker, resumes
  
  /cancel
  → Archives project. Snapshots preserved.
  Wait until monthly reset (first of next month).
```

**War Room exhaustion halt**

```
Recovery:
  /restore State_#N       → Roll back to before the failing stage
  /admin force_stage S3_CODEGEN  → Jump to any stage
  /cancel                 → Archive
```

### 2.2 Time-Travel Restore

Every stage completion saves a numbered snapshot to Supabase.

```
# List available snapshots
/snapshots
→ 📸 Snapshots for proj_abc123:
     State_#9 — S8_HANDOFF (2026-04-12 14:30)
     State_#8 — S7_VERIFY  (2026-04-12 14:28)
     State_#7 — S6_DEPLOY  (2026-04-12 14:20)
     ...
     State_#1 — S0_INTAKE  (2026-04-12 13:45)

# Restore to before S6 deploy
/restore State_#6
→ ✅ Restored to snapshot #6 — stage: S5_TEST
   Use /continue to resume or /status to check.

# Then resume
/continue
→ ▶️ Resuming from S5_TEST...
```

**Checksum validation:** Supabase snapshots are stored with SHA-256 checksums. If a snapshot is corrupted, `/restore` will fail with a checksum mismatch error — the operator will be notified and can try an earlier snapshot.

### 2.3 Budget Circuit Breaker

The Budget Governor operates in 4 tiers:

| Tier | Threshold | Behaviour | Recovery |
|---|---|---|---|
| GREEN | 0–79% | Normal operation | — |
| AMBER | 80–94% | Strategist downgraded, Engineer context capped | Auto-recovers |
| RED | 95–99% | New project intake blocked (in-flight continues) | `/admin budget_override` |
| BLACK | 100% | All activity stopped | Wait for monthly reset or raise ceiling |

```bash
# Check current budget status
/cost

# Override RED/BLACK tier to unblock intake
/admin budget_override 50.00

# The override lasts until the next monthly reset or manual deactivation
# In-flight projects at AMBER: Engineer output stays capped at 8192 tokens
```

**Budget alert messages** (sent automatically on tier transitions):
```
🟡 Budget at 81% — AMBER mode active
Remaining: $3.80
Strategist downgraded to opus-4.5
Engineer context capped at 100K
Scout preferring cached results

🔴 Budget at 96% — RED mode active
Remaining: $0.80
New projects BLOCKED. In-flight continues degraded.
Override: /admin budget_override
```

### 2.4 Resuming After Any Halt

```
/continue
→ Clears: legal_halt, circuit_breaker_triggered
→ Resumes from state.current_stage (or previous_stage if HALTED)

If pipeline does not advance after /continue:
  /status               → check current stage
  /warroom              → check War Room activation log
  /snapshots            → list restore points
  /restore State_#N     → restore to last clean state
```

---

## 3. Per-Stage Rollback Procedures

### S0 Intake — Roll Back

**When:** Requirements were parsed incorrectly, wrong app name, bad category.

```
Telegram:
  /restore State_#1      → restore to after S0 (before S1)
  /cancel                → abandon and start over with /new

Git (code-level):
  git revert ab86ee5    → removes S0 verification changes (rare)
```

**Artifacts created:**
- `state.s0_output` (in-memory / Supabase)
- Supabase snapshot #1

**Safe to re-run:** Yes. S0 is idempotent — re-running with the same input produces the same output.

---

### S1 Legal Gate — Roll Back

**When:** Legal PDF was corrupted, wrong regulatory classification, legal halt issued incorrectly.

```
Telegram:
  /restore State_#1      → restore to end of S0 (re-runs S1 fresh)
  /force_continue <reason>  → override legal halt if you accept the risk
  /legal                 → view compliance log before deciding

Git (code-level, S1 PDF only):
  git revert 4e1c1e6    → removes pdf_generator.py wiring from s1_legal.py
  # Legal dossier PDF generation becomes no-op; pipeline continues without PDF

Environment flag (disable PDF without code change):
  # Add to s1_legal.py try/except — already wrapped non-fatally
  # If PDF generation fails it logs warning and pipeline continues
```

**Artifacts created:**
- `artifacts/{project_id}/legal/legal_dossier.pdf`
- Supabase storage: `{project_id}/legal/legal_dossier.pdf`
- Supabase snapshot #2

**Safe to re-run:** Yes. `pdf_generator.py` is non-fatal — if it fails, the pipeline continues without a PDF.

---

### S2 Blueprint — Roll Back

**When:** Wrong stack selected, bad design system, ADR incorrect.

```
Telegram:
  /restore State_#2      → restore to end of S1 (re-runs S2 fresh)
  /admin force_stage S2_BLUEPRINT  → jump directly to S2

Git (code-level, Blueprint PDF only):
  git revert cc23e2f    → removes blueprint_pdf.py wiring from s2_blueprint.py
  # Master Blueprint PDF, Stack ADR, and Design Package generation removed
  # S2 reverts to brand assets + Vibe Check only

Manual artifact cleanup:
  rm -rf artifacts/{project_id}/blueprint/
  rm docs/adr/{id:04d}-stack-selection-*.md
```

**Artifacts created:**
- `artifacts/{project_id}/blueprint/master_blueprint.pdf`
- `docs/adr/{id:04d}-stack-selection-{stack}.md`
- Design package (brand colors, WCAG verification, screen mocks)
- Supabase snapshot #3

**Safe to re-run:** Yes. Blueprint PDF and ADR writes are idempotent (overwrite existing files).

---

### S3 CodeGen + GitHub — Roll Back

**When:** Generated code is wrong, GitHub repo was created with wrong name, files committed to wrong repo.

```
Telegram:
  /restore State_#3      → restore to end of S2 (re-runs S3 fresh)
  # New GitHub repo will be created (old one abandoned, not deleted)

Git (code-level, GitHub commit only):
  git revert 8d14cb7    → removes _commit_to_github() from s3_codegen.py
  # Generated files stay in state but are no longer committed to GitHub

GitHub cleanup (manual):
  gh repo delete {org}/{repo-name} --yes
  # Or archive the repo if you want to preserve it

Selective re-run:
  /admin force_stage S3_CODEGEN  → regenerates code from S2 blueprint
```

**Artifacts created:**
- `state.s3_output.generated_files` (in-memory / Supabase)
- GitHub repo: `{sanitised-app-name}` (private)
- Supabase snapshot #4

**Non-fatal:** If `GITHUB_TOKEN` is not set or GitHub is unreachable, the GitHub commit step is silently skipped. Code generation still completes.

---

### S4 Build — Roll Back

**When:** Build produced corrupt artifacts, wrong platform binaries.

```
Telegram:
  /restore State_#4      → restore to end of S3 (re-runs S4 fresh)
  /warroom               → check War Room L1/L2/L3 log for build errors

Manual workspace cleanup:
  rm -rf ~/factory-projects/{app-name}/
  # Workspace is recreated on next S4 run

Re-run from S3:
  /admin force_stage S3_CODEGEN  → regenerates code, rebuilds
```

**Artifacts created:**
- Build workspace: `~/factory-projects/{app-name}/`
- `state.s4_output.artifacts` (IPA / AAB / APK paths)
- Supabase snapshot #5

**Non-fatal failures:** If binary compilation fails (source-only mode), the pipeline continues. S4 sends a Telegram notification with the workspace path so you can inspect or manually build.

---

### S5 Test — Roll Back

**When:** Tests were wrong, false positive pass, want to retry with fixed code.

```
Telegram:
  /restore State_#4      → re-runs S4 + S5 fresh
  /restore State_#3      → re-runs S3 + S4 + S5 (full re-codegen)
  
  After restore, pipeline auto-routes:
    tests pass → continues to S6
    tests fail → War Room → retry S3 (up to 3 times) → halt

Manual test override (skip test failures):
  /admin force_stage S6_DEPLOY  → bypass S5 entirely (use with caution)
```

**Artifacts created:**
- `state.s5_output.test_results`
- Supabase snapshot #6

**Retry loop:** S5→S3 retry fires automatically up to 3 times (`state.retry_count`). After 3 failures the pipeline halts. Use `/admin reset_retries` to reset the counter and try again.

---

### S6 Deploy — Roll Back

**When:** Deployment went to wrong environment, store submission was premature.

```
Telegram:
  /deploy_cancel         → cancels pending deployment (before confirmation)
  /restore State_#5      → rolls pipeline back to end of S5 (before deploy gate)

External rollback (store submissions):
  Apple TestFlight: Log into App Store Connect → Builds → Remove build from TestFlight
  Google Play: Console → Internal Testing → Deactivate release
  Web (Vercel/Render): Dashboard → Deployments → Roll back to previous

Environment:
  DEPLOY_DRY_RUN=true   → makes S6 simulate deployment without submitting
```

**Artifacts created:**
- Submitted IPA / AAB to TestFlight / Play Console
- `state.s6_output.deployment_url`
- Supabase snapshot #7

**Pre-deploy gate:** In Copilot mode, S6 waits for `/deploy_confirm` before submitting. The gate times out after 15 minutes and auto-cancels if no confirmation is received.

---

### S7 Verify — Roll Back

**When:** Verification false-negative (endpoints are healthy but verify failed), or redeploy loop is spinning.

```
Telegram:
  /restore State_#6      → re-runs S6 + S7 (fresh deployment)
  /restore State_#5      → re-runs S5 + S6 + S7 (fresh tests + deploy)

Stop redeploy loop:
  /admin reset_retries   → resets retry_count (loop fires max 2 times)
  /admin force_stage S8_HANDOFF  → skip verify, proceed to handoff

Manual endpoint check:
  curl {deployment_url}/health
  → if healthy, use /admin force_stage S8_HANDOFF
```

**Artifacts created:**
- `state.s7_output.passed`
- `state.s7_output.health_check_url`
- Supabase snapshot #8

**Redeploy loop:** S7 failure triggers S6→S7 redeploy up to 2 times. Use `/admin reset_retries` to reset.

---

### S8 Handoff — Roll Back

**When:** Handoff docs were generated with wrong content, program docs triggered prematurely.

```
Telegram:
  /restore State_#8      → re-runs S8 fresh (regenerates all handoff docs)

Program docs deferred (expected behaviour):
  When not all sibling projects in a program are complete,
  _generate_program_docs() returns _PROGRAM_DOCS_DEFERRED — this is correct.
  Program docs are auto-generated when the last sibling reaches S8.

Manual doc cleanup:
  Handoff docs are sent as Telegram file attachments — no cleanup needed.
  Neo4j HandoffDoc nodes are permanent (janitor-exempt).

Git (code-level):
  git revert df526c6    → removes Neo4j sibling query + program doc generation
  # Handoff reverts to per-project docs only (no cross-project integration map)
```

**Artifacts created:**
- QUICK_START.md, EMERGENCY_RUNBOOK.md, SERVICE_MAP.md, UPDATE_GUIDE.md (Telegram attachments)
- Neo4j: HandoffDoc nodes (permanent=true)
- Program docs (when all siblings complete): CROSS_STACK_INTEGRATION_MAP.md, UNIFIED_DEPLOYMENT_GUIDE.md, PROGRAM_HEALTH_DASHBOARD.md
- Supabase snapshot #9

---

## 4. Infrastructure Rollback

### Telegram Bot

```bash
# Restart local polling bot
python scripts/run_bot.py

# Remove stale webhook (if bot went offline while webhook was set)
curl -s "https://api.telegram.org/bot{TOKEN}/deleteWebhook?drop_pending_updates=true"

# Switch from Render webhook to local polling
/local    (from Telegram, if bot is responsive)
# OR manually:
python -c "import urllib.request; urllib.request.urlopen('https://api.telegram.org/bot{TOKEN}/deleteWebhook', data=b'drop_pending_updates=true')"
```

### Supabase

```bash
# Check active projects table
# (from psql or Supabase dashboard)
SELECT project_id, current_stage, created_at FROM active_projects ORDER BY created_at DESC LIMIT 10;

# Manually archive a stuck project
DELETE FROM active_projects WHERE project_id = 'proj_abc123';
INSERT INTO archived_projects (project_id, ...) SELECT ... FROM active_projects WHERE ...;

# List snapshots for a project
SELECT snapshot_id, stage, created_at FROM state_snapshots WHERE project_id = 'proj_abc123' ORDER BY snapshot_id DESC;
```

### Neo4j

```bash
# Remove orphaned HandoffDoc nodes (non-permanent only)
# Neo4j Aura console or cypher-shell:
MATCH (n:HandoffDoc) WHERE n.permanent IS NULL OR n.permanent = false DELETE n;

# View program nodes
MATCH (n:ProjectNode) WHERE n.program_id IS NOT NULL RETURN n;

# Reset a project node status (if stuck)
MATCH (n:ProjectNode {project_id: 'proj_abc123'}) SET n.status = 'S5_TEST' RETURN n;
```

### Legal Dossier PDF (Supabase Storage)

```bash
# Remove a misgenerated PDF from Supabase storage
# Via dashboard: Storage → artifacts bucket → {project_id}/legal/
# Via API:
curl -X DELETE \
  "{SUPABASE_URL}/storage/v1/object/artifacts/{project_id}/legal/legal_dossier.pdf" \
  -H "Authorization: Bearer {SERVICE_ROLE_KEY}"
```

### GitHub Repos

```bash
# List repos created by the pipeline
gh repo list --limit 50 | grep "factory-"

# Delete a test/bad repo
gh repo delete {owner}/{repo-name} --yes

# Archive a repo (preserves history, disables new commits)
gh repo archive {owner}/{repo-name}
```

---

## 5. Disaster Recovery Scenarios

### DR-1: Bot is completely unresponsive

```bash
# 1. Kill any running bot processes
pkill -f "run_bot.py"

# 2. Clear stale webhook
curl "https://api.telegram.org/bot{TOKEN}/deleteWebhook?drop_pending_updates=true"

# 3. Restart
python scripts/run_bot.py

# 4. Check state of active project
/status
```

### DR-2: Pipeline hung mid-stage (no progress for 10+ minutes)

```bash
# 1. Check what stage it's at
/status

# 2. Check if it's in a retry loop
/warroom

# 3. Restore to last clean snapshot
/snapshots
/restore State_#N

# 4. Resume
/continue
```

### DR-3: Budget depleted unexpectedly

```bash
# 1. Immediately check tier
/cost

# 2. If BLACK tier:
/admin budget_override 100.00   # raise ceiling
/continue                        # resume in-flight project

# 3. Investigate root cause
/status → check phase_costs breakdown
# Likely: War Room L3 retry loop burning tokens
# Fix: /admin reset_retries → reduces retry burn
```

### DR-4: Legal PDF generation failing consistently

```bash
# Check if ReportLab is installed
pip show reportlab

# Install if missing
pip install "reportlab>=4.0"

# If Supabase upload is failing (non-fatal, PDF still saved locally):
# Check artifacts/{project_id}/legal/legal_dossier.pdf
ls -la artifacts/*/legal/

# Emergency: disable PDF generation (it's already wrapped non-fatally)
# No code change needed — if generate_legal_dossier_pdf raises, pipeline continues
```

### DR-5: GitHub commit loop / rate limit

```bash
# Check GitHub API rate limit
gh api rate_limit

# If rate limited, GitHub commits are non-fatal — pipeline continues
# To disable GitHub commits temporarily:
unset GITHUB_TOKEN   # or set to empty
# _commit_to_github() checks gh.is_connected() and skips if false

# When rate limit resets (1 hour):
export GITHUB_TOKEN={your_token}
/admin force_stage S3_CODEGEN  # re-runs codegen + commit
```

### DR-6: Neo4j connection lost mid-pipeline

```bash
# Neo4j is non-fatal for all operations:
# - Mother Memory write failures are logged, pipeline continues
# - S8 program doc query falls back to _PROGRAM_DOCS_DEFERRED
# - HandoffDoc storage skipped gracefully

# Check Neo4j Aura status: https://console.neo4j.io/

# Force reconnect:
# Neo4j client reconnects on next call — no restart needed

# If program docs were deferred due to Neo4j outage:
/admin force_stage S8_HANDOFF   # re-runs S8 when Neo4j is back
```

---

## 6. Post-Rollback Verification Checklist

After any rollback operation, run:

```bash
# 1. Tests must be green
python -m pytest tests/ -q
# Expected: 569 passed

# 2. Bot imports clean
python -c "from factory.telegram.bot import setup_bot; print('OK')"

# 3. Pipeline imports clean
python -c "from factory.orchestrator import run_pipeline; print('OK')"

# 4. Dry-run end-to-end
AI_PROVIDER=mock SCOUT_PROVIDER=mock DRY_RUN=true python -c "
import asyncio, os
from factory.orchestrator import run_pipeline_from_description
async def main():
    state = await run_pipeline_from_description('Test app', autonomy_mode='autopilot')
    assert state.current_stage.value == 'S8_HANDOFF', f'Unexpected stage: {state.current_stage}'
    print(f'✅ Pipeline OK — {len(state.stage_history)} stages, cost=\${state.total_cost_usd:.4f}')
asyncio.run(main())
"

# 5. Check Telegram bot responds
/status   (in Telegram)
```

---

## 7. Rollback Decision Tree

```
Pipeline problem detected
         │
         ▼
Is the pipeline still running?
├── YES → /status to identify stage
│          └── In War Room retry loop? → /admin reset_retries
│          └── Legal halt? → /force_continue <reason> or /cancel
│          └── Budget halt? → /admin budget_override → /continue
│          └── Hung/silent? → /restore State_#N → /continue
│
└── NO (completed with bad output)
           │
           ▼
           Is the output bad for one stage?
           ├── YES → /restore State_#(N-1) → /continue
           │         (re-runs from that stage)
           │
           └── NO (systemic / wrong from S0)
                      │
                      ▼
                      /cancel (preserves snapshots)
                      /new <corrected description>
```

---

## 8. Contact & Escalation

| Level | Action |
|---|---|
| L1 (self-service) | Telegram commands: `/restore`, `/continue`, `/force_continue`, `/admin` |
| L2 (code rollback) | `git revert <tag>` per stage, `pytest` to verify, re-deploy bot |
| L3 (data rollback) | Supabase dashboard, Neo4j console, Supabase storage |
| L4 (full reset) | `git checkout pre-real-production-20260412`, wipe Supabase `active_projects` |

---

*AI Factory Pipeline v5.8 — Safety & Rollback Runbook*  
*Generated: 2026-04-12 | Spec: §2.9, §2.14, §4.10*
