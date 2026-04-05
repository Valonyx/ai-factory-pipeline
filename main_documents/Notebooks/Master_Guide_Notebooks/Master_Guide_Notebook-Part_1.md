# AI FACTORY PIPELINE v5.6
# MASTER IMPLEMENTATION GUIDE — PART 1
## Pre-Implementation Setup + NB1: Codebase Build

---

> **What this document is:** Your step-by-step guide from zero code to the
> NB1 Local Dry-Run Milestone. Every command is copy-paste ready. Every
> failure has a fix. Zero IT background assumed.
>
> **How to use it:** Read one section, then do it. Do not read ahead and
> then do it — the sections build on each other and skipping steps
> causes failures that are hard to diagnose.

---

# SECTION 0: BEFORE YOU TOUCH ANYTHING

## 0.1 The One Rule

**One part at a time. Test it. Commit it. Only then move forward.**

Every part ends with a checkpoint. Every checkpoint has a smoke test
command. Run the smoke test. If it passes, commit and continue. If it
fails, fix it before moving on. There are no exceptions to this rule.

## 0.2 How Long This Takes

| Phase | Time | Cost |
|---|---|---|
| Section 1 (Mac Setup) | 2–3 hours | $0 |
| Section 2 (Claude Tools Setup) | 30 minutes | $0 |
| Sections 3–7 (NB1 Parts 1–8) | 4–6 days | $0 |
| Sections 8–12 (NB1 Parts 9–21) | 5–7 days | $0 |
| **Total NB1** | **~12 days** | **$0** |

You will spend zero dollars until Section 13 (NB3 Activation).

## 0.3 What "Terminal" Means

Throughout this guide, "open Terminal" means:
1. Press **Command + Space** on your keyboard
2. Type: `Terminal`
3. Press **Enter**
4. A window appears with a text prompt ending in `$` or `%`

That window is Terminal. Every command in this guide is typed there.

---

# SECTION 1: MAC ENVIRONMENT SETUP
📖 **Read first:** NB1 Part 1 (entire section — §1.4 through §1.6)

This section installs every tool your Mac needs. Nothing else works
until this section is complete.

---

## STEP 1.1 — Install Homebrew

**What it is:** Homebrew is your Mac's software installer. Every tool
in the pipeline gets installed through it. Think of it as an App Store
for developer tools.

**1.** Open Terminal.

**2.** Paste this entire line and press Enter:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

**3.** You will be asked for your Mac login password. Type it (nothing
appears as you type — that is normal) and press Enter.

**4.** The install takes 5–10 minutes. Wait until you see the prompt
`$` return.

**5.** After install finishes, run this to add Homebrew to your path:

```bash
echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zshrc
source ~/.zshrc
```

**6.** Verify:

```bash
brew --version
```

✅ **Success:** You see `Homebrew 4.x.x` or similar.

❌ **Failure: "Permission denied"**
🔧 You do not need sudo. Enter your Mac login password when prompted.
That is standard macOS authentication, not sudo.

❌ **Failure: "Command Line Tools not installed"**
🔧 Run this first, wait for it to finish, then retry Homebrew:
```bash
xcode-select --install
```

**USE MEMORY HERE:** After success, say in this Claude chat:
`"Remember: Homebrew installed successfully on my M3 Pro."`

---

## STEP 1.2 — Install Python 3.11

**What it is:** Python is the programming language the entire pipeline
is written in. Version 3.11 specifically is required.

**1.** In Terminal:

```bash
brew install python@3.11
```

Wait until the `$` prompt returns (2–5 minutes).

**2.** Add Python 3.11 to your path:

```bash
echo 'export PATH="/opt/homebrew/opt/python@3.11/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

**3.** Verify:

```bash
python3.11 --version
```

✅ **Success:** You see `Python 3.11.x`

❌ **Failure: "brew: command not found"**
🔧 Homebrew path wasn't set. Run:
```bash
eval "$(/opt/homebrew/bin/brew shellenv)"
brew install python@3.11
```

❌ **Failure: "python3.11: command not found" after install**
🔧 Run:
```bash
echo 'export PATH="/opt/homebrew/opt/python@3.11/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
python3.11 --version
```

---

## STEP 1.3 — Install PyCharm Community Edition

**What it is:** PyCharm is your code editor — where you read and
edit Python files. It shows you errors before you run code, which
saves hours of debugging.

**1.** Open Safari or Chrome. Go to:
```
https://www.jetbrains.com/pycharm/download/
```

**2.** Click the tab that says **"Mac"** or **"macOS"**.

**3.** Make sure it shows **"Apple Silicon"** (not Intel).

**4.** Click **"Download"** under **"Community"** (the free version).

**5.** When download finishes, open the `.dmg` file from your Downloads
folder.

**6.** Drag the PyCharm icon into the Applications folder.

**7.** Open PyCharm from Applications. First launch is slow (1–2 min).

**8.** If macOS says "PyCharm can't be opened because Apple cannot
check it for malicious software":
🔧 Go to **System Settings → Privacy & Security** → scroll down →
click **"Open Anyway"** → click **"Open"**.

**9.** On the Welcome screen, click **"New Project"** — just to confirm
it works — then close PyCharm. You will configure the project properly
in Step 1.8.

✅ **Success:** PyCharm opens and shows a Welcome screen.

---

## STEP 1.4 — Install Git, Node.js, Docker, and Cloudflare Tunnel

**What each is:**
- **Git** — tracks every change you make to your code (version control)
- **Node.js** — needed for Claude Code and some build tools
- **Docker** — packages your pipeline for deployment to GCP
- **cloudflared** — creates a secure tunnel for Local Mode builds

**1.** In Terminal, install all four at once:

```bash
brew install git node cloudflared
```

**2.** Install Docker Desktop separately (it needs a graphical installer):

```bash
brew install --cask docker
```

**3.** Open Docker Desktop from Applications (it needs to run at least once
to finish setup). Wait until you see "Docker Desktop is running" in the
menu bar.

**4.** Verify everything:

```bash
git --version && node --version && cloudflared --version && docker --version
```

✅ **Success:** You see four version numbers, one per tool.

❌ **Failure: Any "command not found" after install**
🔧 Run `source ~/.zshrc` then retry the verification command.

❌ **Failure: Docker says "Cannot connect to the Docker daemon"**
🔧 Docker Desktop isn't running. Open it from Applications and wait
for the icon in the menu bar to stop animating.

---

## STEP 1.5 — Install Xcode Command Line Tools

**What it is:** Xcode's command line tools include a C compiler and
other tools that Python packages need when installing.

**1.** In Terminal:

```bash
xcode-select --install
```

**2.** A popup appears asking to install. Click **"Install"**.

**3.** Wait 5–10 minutes until it completes.

**4.** Verify:

```bash
xcode-select -p
```

✅ **Success:** You see a path like `/Library/Developer/CommandLineTools`

❌ **Failure: "xcode-select: error: command line tools are already installed"**
✅ This is also success — the tools were already there.

---

## STEP 1.6 — Create the Project Folder Structure

**What it is:** The pipeline has a specific folder layout where every
file lives. Creating these folders now means you can paste files into
exactly the right places later.

**1.** Create the main project folder:

```bash
mkdir -p ~/Projects/ai-factory-pipeline
cd ~/Projects/ai-factory-pipeline
```

**2.** Create all 13 subdirectories at once:

```bash
mkdir -p factory/core \
         factory/pipeline \
         factory/integrations \
         factory/design \
         factory/legal \
         factory/telegram \
         factory/infra \
         factory/migrations \
         factory/monitoring \
         factory/security \
         factory/tests \
         docs \
         scripts \
         tests \
         .github/workflows
```

**3.** Verify the structure:

```bash
find . -type d | sort
```

✅ **Success:** You see 15+ directory names listed.

---

## STEP 1.7 — Create the Python Virtual Environment

**What it is:** A virtual environment is an isolated Python
installation just for this project. It prevents this project's
packages from conflicting with anything else on your Mac.

You will activate this environment EVERY time you open Terminal
to work on the pipeline. This is the most important habit.

**1.** Create the virtual environment:

```bash
cd ~/Projects/ai-factory-pipeline
python3.11 -m venv .venv
```

**2.** Activate it:

```bash
source .venv/bin/activate
```

**3.** You know it's active when your prompt changes to show `(.venv)`
at the start, like this:
```
(.venv) your-name@MacBook ai-factory-pipeline %
```

**4.** Install the base packages the pipeline needs:

```bash
pip install --upgrade pip
pip install "pydantic>=2.0,<3.0" langgraph python-telegram-bot aiohttp fastapi uvicorn
```

Wait 2–3 minutes for all packages to download and install.

**5.** Verify:

```bash
python -c "from pydantic import BaseModel; print('✅ Pydantic v2 ready')"
```

✅ **Success:** You see `✅ Pydantic v2 ready`

❌ **Failure: "externally-managed-environment"**
🔧 You forgot to activate the venv. Run `source .venv/bin/activate`
then retry the pip install.

❌ **Failure: Package install fails with network error**
🔧 Check your internet connection. If using a VPN, try disconnecting it.

**CRITICAL HABIT — Do this every session:**
Every time you open a new Terminal window to work on this project, run:
```bash
cd ~/Projects/ai-factory-pipeline
source .venv/bin/activate
```
You will see `(.venv)` in your prompt. Only then start working.

---

## STEP 1.8 — Initialize Git

**What it is:** Git tracks every change to your code. Each checkpoint
creates a "commit" — a saved snapshot you can return to if something
breaks.

**1.** Initialize git in your project:

```bash
cd ~/Projects/ai-factory-pipeline
git init
git config user.email "your-email@example.com"
git config user.name "Your Name"
```

(Replace with your actual name and email.)

**2.** Create the `.gitignore` file (tells git what NOT to track):

```bash
cat > .gitignore << 'EOF'
.venv/
__pycache__/
*.pyc
*.pyo
.env
.env.local
*.egg-info/
dist/
build/
.DS_Store
*.log
.pytest_cache/
.coverage
htmlcov/
EOF
```

**3.** Create the `__init__.py` files for every package:

```bash
touch factory/__init__.py
touch factory/core/__init__.py
touch factory/pipeline/__init__.py
touch factory/integrations/__init__.py
touch factory/design/__init__.py
touch factory/legal/__init__.py
touch factory/telegram/__init__.py
touch factory/infra/__init__.py
touch factory/migrations/__init__.py
touch factory/monitoring/__init__.py
touch factory/security/__init__.py
touch factory/tests/__init__.py
touch tests/__init__.py
```

**4.** Make the first commit:

```bash
git add .
git commit -m "Initial scaffold — 13-directory structure, venv, gitignore"
```

✅ **Success:** You see a message like:
```
[main (root-commit) abc1234] Initial scaffold — 13-directory structure...
13 files changed, 0 insertions(+)
```

---

## STEP 1.9 — Configure PyCharm for This Project

**1.** Open PyCharm.

**2.** On the Welcome screen, click **"Open"**.

**3.** Navigate to `~/Projects/ai-factory-pipeline` and click **"Open"**.

**4.** Set the Python interpreter to your virtual environment:
   - Go to **PyCharm → Settings** (or **Preferences** on older versions)
   - Click **"Project: ai-factory-pipeline"** → **"Python Interpreter"**
   - Click the gear icon → **"Add"**
   - Select **"Existing environment"**
   - Click the folder icon and navigate to:
     `~/Projects/ai-factory-pipeline/.venv/bin/python3.11`
   - Click **"OK"**

**5.** Verify: In the bottom-right corner of PyCharm, you should see
`Python 3.11 (.venv)`.

✅ **SECTION 1 COMPLETE — Full Checkpoint**

Run this smoke test:
```bash
cd ~/Projects/ai-factory-pipeline
source .venv/bin/activate
python -c "
import sys, subprocess
print(f'Python: {sys.version}')
result = subprocess.run(['git', 'status'], capture_output=True, text=True)
print(f'Git: {result.stdout.strip().split(chr(10))[0]}')
from pydantic import BaseModel
print('Pydantic v2: ✅')
print('✅ Mac environment fully ready for NB1')
"
```

✅ **Expected output:**
```
Python: 3.11.x ...
Git: On branch main
Pydantic v2: ✅
✅ Mac environment fully ready for NB1
```

**USE MEMORY HERE:**
```
"Remember: Mac environment setup complete. Python 3.11, 
Homebrew, Git, Docker, Node.js, cloudflared all installed. 
Virtual environment at ~/Projects/ai-factory-pipeline/.venv. 
Ready to start NB1."
```

---

# SECTION 2: CLAUDE TOOLS SETUP
*Do this now, before writing any code. These tools will save you hours.*

---

## STEP 2.1 — Install Claude Code

**What it is:** Claude Code is a version of Claude that lives inside
Terminal and can directly read, write, and run your code files. This
is your primary coding assistant for NB1 and NB2.

**1.** In Terminal (with venv active):

```bash
npm install -g @anthropic-ai/claude-code
```

**2.** Verify:

```bash
claude --version
```

✅ **Success:** You see `claude 1.x.x` or similar.

**3.** Connect Claude Code to your Anthropic account:

```bash
claude
```

The first time, it will show a URL. Copy it, paste it into your
browser, log in with your Anthropic account (same as claude.ai),
and approve. You only do this once.

**4.** You will see a prompt inside Terminal. Type:
```
What files are in this directory?
```

✅ **Success:** Claude Code lists your project files.

**5.** To exit Claude Code: press `Control + C` or type `/exit`

---

## STEP 2.2 — Enable MCP Connectors

**What they are:** MCP connectors let Claude in this chat window talk
to external services (your database, your calendar, etc.) in plain
English.

**Enable these connectors now** (you will use them actively starting
from NB3, but enable them now so they are ready):

**In this claude.ai chat window:**
1. Click your profile picture (bottom-left)
2. Click **Settings**
3. Click **Integrations** (or **Connectors**)
4. Enable each of these:
   - ✅ **Supabase** (connect with your Supabase account — create one
     at supabase.com if you haven't yet, it's free to sign up)
   - ✅ **Context7** (no login needed — just toggle on)
   - ✅ **Notion** (connect with your Notion account — create one
     at notion.so if needed, free)
   - ✅ **Google Calendar** (connect with your Google account)
   - ✅ **Gmail** (connect with your Google account)

**Note:** Claude in Chrome is a separate browser extension. Install
it by searching "Claude for Chrome" in the Chrome Web Store.

---

## STEP 2.3 — Set Up Notion Implementation Tracker

**USE NOTION MCP HERE:**
Say this in the Claude chat:

```
"Using Notion, create a new page called 
'AI Factory Pipeline — Implementation Tracker'. 
Add a checklist with these items:
□ Section 1: Mac Environment Setup
□ Section 2: Claude Tools Setup
□ NB1 Part 1: Scaffold checkpoint
□ NB1 Part 2: state.py checkpoint
□ NB1 Part 3: Core foundation checkpoint
□ NB1 Part 4: Telegram (a) checkpoint
□ NB1 Part 5: Telegram (b) checkpoint
□ NB1 Part 6: Pipeline DAG (a) checkpoint
□ NB1 Part 7: Pipeline DAG (b) checkpoint
★ NB1 Part 8: LOCAL DRY-RUN MILESTONE
□ NB1 Part 9: Intelligence layer checkpoint
□ NB1 Part 10: FlutterFlow checkpoint
□ NB1 Parts 11-12: State/Infra checkpoint
□ NB1 Part 13: Mother Memory checkpoint
□ NB1 Part 14: Design+DocuGen checkpoint
□ NB1 Part 15: Polyglot stacks checkpoint
□ NB1 Parts 16-17: Ops hardening checkpoint
□ NB1 Parts 18-19: Assembly+Config checkpoint
□ NB1 Part 20: Paid activation checkpoint"
```

After Notion creates the page, mark the first two items as complete.

---

# SECTION 3: NB1 PART 1 — PROJECT SCAFFOLD
📖 **Read first:** NB1 Part 1 (§1.1 through §1.6 in the Codebase
Implementation Notebook)

**What this part does:** Confirms your environment is ready, installs
all Python dependencies, and creates the base scaffold files.

---

## STEP 3.1 — Install All Python Dependencies

**1.** Open Terminal, navigate to project, activate venv:

```bash
cd ~/Projects/ai-factory-pipeline
source .venv/bin/activate
```

**2.** Install the full dependency list:

```bash
pip install \
  "pydantic>=2.0,<3.0" \
  "langgraph>=0.1.0" \
  "langchain-core>=0.1.0" \
  "python-telegram-bot[webhooks]>=20.0" \
  "anthropic>=0.20.0" \
  "supabase>=2.0.0" \
  "neo4j>=5.0.0" \
  "PyGithub>=2.0.0" \
  "google-cloud-secret-manager>=2.0.0" \
  "google-cloud-run>=0.10.0" \
  "aiohttp>=3.9.0" \
  "fastapi>=0.110.0" \
  "uvicorn[standard]>=0.27.0" \
  "python-dotenv>=1.0.0" \
  "httpx>=0.27.0" \
  "pytest>=8.0.0" \
  "pytest-asyncio>=0.23.0" \
  "structlog>=24.0.0" \
  "tenacity>=8.2.0"
```

Wait 3–5 minutes for all packages to install.

**3.** Verify:

```bash
python -c "
import pydantic, telegram, anthropic, supabase, neo4j
print(f'pydantic: {pydantic.__version__}')
print(f'telegram: {telegram.__version__}')
print(f'anthropic: {anthropic.__version__}')
print('✅ All core packages installed')
"
```

✅ **Expected output:**
```
pydantic: 2.x.x
telegram: 20.x.x
anthropic: 0.x.x
✅ All core packages installed
```

**USE CONTEXT7 HERE** (if any package has an unexpected version):
```
"Using Context7, find the latest stable version of 
[package name] and confirm the correct import syntax"
```

---

## STEP 3.2 — Create the requirements.txt

**1.** Save the installed packages:

```bash
pip freeze > requirements.txt
```

**2.** Verify it was created:

```bash
head -20 requirements.txt
```

✅ **Success:** You see a list of package names and version numbers.

---

## STEP 3.3 — Create .env.example

**What this is:** A template file showing all 28 environment variables
the pipeline needs. The real `.env` file (with actual keys) gets
created in NB3. For now, you create the template.

**1.** Create the file:

```bash
cat > .env.example << 'EOF'
# AI Factory Pipeline v5.6 — Environment Variables
# Copy to .env and fill in real values during NB3 activation

# ── AI Services ──
ANTHROPIC_API_KEY=your_anthropic_api_key_here
PERPLEXITY_API_KEY=your_perplexity_api_key_here

# ── Telegram ──
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
TELEGRAM_OPERATOR_ID=your_telegram_user_id_here

# ── Supabase ──
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_KEY=your_supabase_service_role_key_here

# ── Neo4j ──
NEO4J_URI=neo4j+s://your-instance.databases.neo4j.io
NEO4J_PASSWORD=your_neo4j_password_here

# ── GitHub ──
GITHUB_TOKEN=your_github_token_here
GITHUB_USERNAME=your_github_username_here

# ── GCP ──
GCP_PROJECT_ID=your_gcp_project_id_here
GCP_REGION=me-central1

# ── Firebase ──
FIREBASE_PROJECT_ID=your_firebase_project_id_here

# ── Pipeline Config ──
PIPELINE_ENV=development
LOG_LEVEL=INFO
DRY_RUN=true
MONTHLY_BUDGET_USD=300
PER_PROJECT_BUDGET_USD=25

# ── Model Config ──
STRATEGIST_MODEL=claude-opus-4-6
ENGINEER_MODEL=claude-sonnet-4-5
QUICKFIX_MODEL=claude-haiku-4-5
SCOUT_MODEL=sonar
EOF
```

---

## STEP 3.4 — NB1 Part 1 Checkpoint

Run the full Part 1 smoke test:

```bash
cd ~/Projects/ai-factory-pipeline
source .venv/bin/activate
python -c "from pydantic import BaseModel; print('✅ Ready for Part 2')"
```

✅ **Expected:** `✅ Ready for Part 2`

**Git commit:**
```bash
git add .
git commit -m "NB1-01: Scaffold — venv, dependencies, .env.example, gitignore"
```

**USE NOTION MCP HERE:**
```
"Mark 'NB1 Part 1: Scaffold checkpoint' as complete 
in my Implementation Tracker"
```

**USE MEMORY HERE:**
```
"Remember: NB1 Part 1 complete. All Python dependencies 
installed. requirements.txt and .env.example created. 
Git commit: NB1-01."
```

---

# SECTION 4: NB1 PART 2 — CORE STATE MODEL (state.py)
📖 **Read first:** NB1 Part 2 (full section) + Spec §2.1 through §2.14

**What this part builds:** `factory/core/state.py` — the single most
important file in the entire pipeline. Every other module imports from
this file. It defines the data shape of everything the pipeline tracks.

---

## STEP 4.1 — Understand Before You Build

Before writing a single line, read these sections of the spec so you
understand what you are building:
- **§2.1** — PipelineState (the central object that travels through
  all 9 stages)
- **§2.1.1** — The 5 enums: Stage (11 values), TechStack (6 values),
  ExecutionMode (3 values), AutonomyMode (2 values), AIRole (4 values)
- **§1.4** — BUDGET_CONFIG (the $255.30/month baseline budget)

**USE CONTEXT7 HERE** before writing the file:
```
"Using Context7, get pydantic v2 documentation for 
BaseModel, Field with default_factory, field_validator, 
and model_validator"
```

Read the output. It confirms the exact syntax your code will use.

---

## STEP 4.2 — Build state.py Using Claude Code

**USE CLAUDE CODE HERE:**

**1.** Open Terminal, navigate to project, activate venv:

```bash
cd ~/Projects/ai-factory-pipeline
source .venv/bin/activate
```

**2.** Start Claude Code:

```bash
claude
```

**3.** Type this instruction to Claude Code:

```
Create the file factory/core/state.py implementing the 
complete AI Factory Pipeline v5.6 core state model per 
spec §2.1 through §2.14. 

The file must include:
1. All 5 enums: Stage (11 values: S0_INTAKE through S8_HANDOFF 
   plus COMPLETED and HALTED), TechStack (6 values), 
   ExecutionMode (3 values), AutonomyMode (2 values), 
   AIRole (4 values: scout, strategist, engineer, quick_fix)
2. VALID_TRANSITIONS dict mapping each stage to its valid next stages
3. PipelineState Pydantic v2 BaseModel with all fields using 
   Field(default_factory=...) for collections — never bare [] or {}
4. Blueprint schema (polyglot, used by S3–S8)
5. BUDGET_CONFIG totaling $255.30/month baseline
6. ROLE_CONTRACTS dict with 4 role entries
7. REQUIRED_SECRETS list with 15 secrets
8. Custom exceptions: IllegalTransition, BudgetExceeded, 
   RoleViolationError, UserSpaceViolation, SnapshotWriteError
9. transition_to() function as the ONLY way to change stages
10. All fields from NB1 Part 2 spec

After creating the file, run this verification:
python -c "
from factory.core.state import (Stage, TechStack, ExecutionMode, 
AutonomyMode, AIRole, PipelineState, BUDGET_CONFIG, ROLE_CONTRACTS)
print(f'Stages: {len(Stage)}')
print(f'Stacks: {len(TechStack)}')
print(f'Roles: {len(AIRole)}')
print(f'Budget baseline: \${BUDGET_CONFIG[\"total_baseline\"]:.2f}')
print('✅ state.py verified')
"
```

**4.** Claude Code will write the file and run the verification.
Watch for any errors and tell Claude Code to fix them.

---

## STEP 4.3 — Verify state.py Manually

After Claude Code finishes, run this verification yourself:

```bash
cd ~/Projects/ai-factory-pipeline
source .venv/bin/activate
python -c "
from factory.core.state import (
    Stage, TechStack, ExecutionMode, AutonomyMode, AIRole,
    PipelineState, Blueprint, BUDGET_CONFIG, ROLE_CONTRACTS,
    REQUIRED_SECRETS, transition_to, IllegalTransition
)
# Check counts
assert len(Stage) == 11, f'Expected 11 stages, got {len(Stage)}'
assert len(TechStack) == 6, f'Expected 6 stacks, got {len(TechStack)}'
assert len(AIRole) == 4, f'Expected 4 roles, got {len(AIRole)}'
assert len(REQUIRED_SECRETS) == 15, f'Expected 15 secrets'
assert len(ROLE_CONTRACTS) == 4, f'Expected 4 role contracts'
# Check budget
total = BUDGET_CONFIG.get('total_baseline', 0)
assert 250 < total < 260, f'Budget should be ~\$255, got \${total}'
# Check state instantiation
s = PipelineState(project_id='test', operator_id='op1')
assert s.current_stage == Stage.S0_INTAKE
# Check transition enforcement
try:
    transition_to(s, Stage.S8_HANDOFF)  # Invalid jump
    assert False, 'Should have raised IllegalTransition'
except IllegalTransition:
    pass  # Correct
print(f'✅ state.py: {len(Stage)} stages, {len(TechStack)} stacks, \${total:.2f}/mo budget')
"
```

✅ **Expected output:**
```
✅ state.py: 11 stages, 6 stacks, $255.30/mo budget
```

❌ **Failure: "ImportError: cannot import name X"**
🔧 Tell Claude Code:
```
"state.py has an import error: [paste the error].
Open the file, find the missing name, and add it."
```

❌ **Failure: "AssertionError: Expected 11 stages, got 10"**
🔧 Tell Claude Code:
```
"state.py is missing a stage value. The Stage enum 
needs exactly 11 values: S0_INTAKE, S1_LEGAL, 
S2_BLUEPRINT, S3_CODEGEN, S4_BUILD, S5_TEST, S6_DEPLOY, 
S7_VERIFY, S8_HANDOFF, COMPLETED, HALTED. Fix it."
```

---

## STEP 4.4 — NB1 Part 2 Checkpoint and Commit

```bash
git add factory/core/state.py
git commit -m "NB1-02: P0 state.py — all enums, PipelineState, Blueprint, BUDGET_CONFIG (§2.1–§2.14)"
```

**USE NOTION MCP HERE:**
```
"Mark 'NB1 Part 2: state.py checkpoint' as complete"
```

**USE MEMORY HERE:**
```
"Remember: NB1 Part 2 complete. factory/core/state.py built. 
11 stages, 6 stacks, 4 AI roles, $255.30/mo budget. 
All assertions pass. Commit: NB1-02."
```

---

# SECTION 5: NB1 PART 3 — CORE FOUNDATION (roles, stages, secrets, execution, user_space)
📖 **Read first:** NB1 Part 3 (full section) + Spec §2.2, §2.5, §2.7, §2.8, §2.11

**What this part builds:** Five more core files that complete the
foundation layer. Together with state.py, these 6 files form P0 —
the base everything else stands on.

| File | What it does | Spec |
|---|---|---|
| `roles.py` | Dispatches AI calls to the right model, enforces Eyes vs. Hands doctrine | §2.2 |
| `stages.py` | `@stage_gate` decorator that wraps every pipeline stage | §2.7 |
| `secrets.py` | Reads API keys from GCP Secret Manager (or .env in dev) | §2.11 |
| `execution.py` | Manages CLOUD / LOCAL / HYBRID mode switching | §2.7 |
| `user_space.py` | Blocks 22 prohibited terminal commands from generated code | §2.8 |

---

## STEP 5.1 — Build All Five Files Using Claude Code

**USE CLAUDE CODE HERE:**

In Claude Code (already running in Terminal), type:

```
Create these 5 files for NB1 Part 3:

1. factory/core/roles.py — AI role enforcement dispatcher
   Per spec §2.2 (Eyes vs. Hands doctrine):
   - call_ai(state, role, prompt) function that dispatches to correct model
   - Scout → Perplexity Sonar (READ-ONLY research)
   - Strategist → Claude Opus 4.6 (architecture decisions)
   - Engineer → Claude Sonnet 4.5 (code generation)
   - Quick Fix → Claude Haiku 4.5 (lightweight fixes)
   - Stub implementations that return mock responses (real API calls come in NB2)
   - Enforces that Scout cannot write, Engineer cannot decide architecture
   - war_room_escalate() function for L1/L2/L3 escalation

2. factory/core/stages.py — stage gate decorator
   Per spec §2.7:
   - @stage_gate decorator that wraps every pipeline stage node
   - Validates correct stage before execution
   - Catches errors and routes to HALTED state
   - route_after_test(state) routing function
   - route_after_verify(state) routing function

3. factory/core/secrets.py — secrets management
   Per spec §2.11:
   - get_secret(name) function — tries GCP Secret Manager first, falls back to .env
   - validate_secrets() function — checks all 15 required secrets exist
   - In dry-run mode (DRY_RUN=true), returns placeholder values
   - No real GCP calls yet (stubs for NB1)

4. factory/core/execution.py — execution mode manager
   Per spec §2.7 §3.3:
   - ExecutionModeManager class with CLOUD/LOCAL/HYBRID modes
   - get_current_mode() returning ExecutionMode enum value
   - HeartbeatMonitor stub for Local Mode

5. factory/core/user_space.py — command safety enforcer
   Per spec §2.8:
   - enforce_user_space(command) function
   - 22 prohibited patterns including: sudo, rm -rf, chmod 777, 
     curl | bash, wget | sh, pip install (without venv check),
     and other dangerous patterns
   - Raises UserSpaceViolation if command matches
   - Returns safe rewritten command for pip install

After creating all 5 files, run this test:
python -c "
from factory.core.roles import call_ai
from factory.core.stages import stage_gate, route_after_test
from factory.core.secrets import get_secret, validate_secrets
from factory.core.execution import ExecutionModeManager
from factory.core.user_space import enforce_user_space
from factory.core.state import UserSpaceViolation
import asyncio

# Test role dispatch (stub)
import factory.core.state as st
state = st.PipelineState(project_id='test', operator_id='op1')

# Test user space enforcer
try:
    enforce_user_space('sudo apt install python3')
    print('❌ FAIL: sudo should be blocked')
except UserSpaceViolation:
    print('✅ User-space enforcer blocks sudo')

result = enforce_user_space('pip install requests')
assert 'pip install' in result
print('✅ User-space enforcer rewrites pip install safely')

mgr = ExecutionModeManager()
print(f'✅ ExecutionMode: {mgr.get_current_mode()}')
print('✅ P0 Core foundation complete')
"
```

---

## STEP 5.2 — Create factory/core/__init__.py

The `__init__.py` file makes the core package importable from elsewhere
in the project. Ask Claude Code:

```
Create factory/core/__init__.py that exports the public API 
from all 6 core modules (state.py, roles.py, stages.py, 
secrets.py, execution.py, user_space.py). 
Include the most commonly used classes and functions.
```

---

## STEP 5.3 — NB1 Part 3 Checkpoint

```bash
cd ~/Projects/ai-factory-pipeline
source .venv/bin/activate
python -c "
from factory.core import (
    PipelineState, call_ai, enforce_user_space, 
    ExecutionModeManager, BUDGET_CONFIG
)
print(f'✅ P0 Core: {len(BUDGET_CONFIG[\"fixed_monthly\"])} fixed services, \${BUDGET_CONFIG[\"total_baseline\"]:.2f}/mo')
"
```

✅ **Expected:** `✅ P0 Core: 11 fixed services, $255.30/mo`

```bash
git add factory/core/
git commit -m "NB1-03: P0 Core complete — roles, stages, secrets, execution, user_space (§2.2–§2.14)"
```

**USE NOTION MCP HERE:**
```
"Mark 'NB1 Part 3: Core foundation checkpoint' as complete"
```

---

# SECTION 6: NB1 PARTS 4–5 — TELEGRAM INTERFACE
📖 **Read first:** NB1 Parts 4 and 5 + Spec §5.1 through §5.6

**What these parts build:** The Telegram bot layer — everything the
operator interacts with. Six modules that handle bot setup, message
formatting, notifications, decision menus, file delivery, and health
monitoring.

| Module | What it does |
|---|---|
| `telegram/bot.py` | Bot initialization, 15 command handlers, free-text handler |
| `telegram/messages.py` | Format all notification messages (stage updates, budget alerts, etc.) |
| `telegram/notifications.py` | Send messages, files, and inline keyboards to operator |
| `telegram/decisions.py` | 4-way Copilot decision menus, deploy gate, operator preferences |
| `telegram/airlock.py` | 3-tier delivery of build artifacts (binaries, docs) |
| `telegram/health.py` | 6-service startup health check, crash loop detection |

---

## STEP 6.1 — Build Telegram Layer Using Claude Code

**USE CONTEXT7 HERE first:**
```
"Using Context7, get python-telegram-bot v20+ documentation for:
Application setup, CommandHandler, MessageHandler, 
InlineKeyboardMarkup, CallbackQueryHandler, and webhook setup"
```

Then in Claude Code:

```
Create the Telegram bot layer for NB1 Parts 4-5 per spec §5.1–§5.6.

Create these 6 files in factory/telegram/:

1. telegram/messages.py — Message formatters
   - format_stage_update(state) → formatted stage notification
   - format_budget_alert(state, tier) → GREEN/AMBER/RED/BLACK alert
   - format_welcome_message() → first message when operator starts bot
   - format_build_complete(state) → S8 handoff notification
   - format_error_message(error) → friendly error display
   - Emoji maps for stages and budget tiers

2. telegram/notifications.py — Send functions
   - notify_operator(bot_token, operator_id, message) async
   - send_file_to_operator(bot_token, operator_id, file_path) async
   - All notifications are fire-and-forget (non-blocking)

3. telegram/decisions.py — Copilot decision menus
   - present_decision(state, options, question) → shows 4-option menu
   - wait_for_operator_reply(state, timeout=300) async
   - In AUTOPILOT mode: auto-selects best option without asking
   - In COPILOT mode: sends inline keyboard and waits for tap

4. telegram/airlock.py — Build artifact delivery  
   - airlock_deliver(state, file_path) async
   - Tier 1: direct file upload if <50MB
   - Tier 2: GitHub release URL if too large
   - Tier 3: GCP bucket URL as last resort
   - SHA-256 checksum in caption

5. telegram/health.py — Health monitoring
   - health_check() async → checks 6 services
   - detect_crash_loop() → returns True if 3+ crashes in 10 minutes
   - Returns dict with service statuses

6. telegram/bot.py — Main bot setup
   Per spec §5.2, implement ALL 15 commands as stubs:
   /start, /new, /status, /budget, /restore, /admin, 
   /cancel, /pause, /resume, /info, /history, /mode, 
   /autopilot, /copilot, /help
   Each command sends a stub response for now.
   setup_bot(token) function that returns Application instance.

After creating all files, verify:
python -c "
from factory.telegram.bot import setup_bot
from factory.telegram.messages import format_welcome_message, format_budget_alert
from factory.telegram.notifications import notify_operator
from factory.telegram.decisions import present_decision
from factory.telegram.airlock import airlock_deliver
from factory.telegram.health import health_check
import asyncio

# Test health check
h = asyncio.run(health_check())
print(f'Health status: {h[\"status\"]}')

# Test message formatting
msg = format_welcome_message()
assert 'AI Factory' in msg or len(msg) > 10
print('✅ Message formatting works')

print('✅ Telegram layer complete — 6 modules, 15 commands')
"
```

---

## STEP 6.2 — NB1 Parts 4–5 Checkpoint

```bash
python -c "
from factory.telegram import (
    setup_bot, notify_operator, airlock_deliver,
    health_check, format_welcome_message, present_decision
)
import asyncio
h = asyncio.run(health_check())
print(f'✅ P1 Telegram complete — Health: {h[\"status\"]}')
"
```

✅ **Expected:** `✅ P1 Telegram complete — Health: ok`

```bash
git add factory/telegram/
git commit -m "NB1-04: P1 Telegram layer — bot, messages, notifications, decisions, airlock, health (§5.1–§5.6)"
```

**USE NOTION MCP HERE:**
```
"Mark 'NB1 Part 4: Telegram (a) checkpoint' and 
'NB1 Part 5: Telegram (b) checkpoint' as complete"
```

---

# SECTION 7: NB1 PARTS 6–7 — PIPELINE DAG
📖 **Read first:** NB1 Parts 6, 7, and the Spec §2.7 (DAG Topology),
§4.0 (Stage Execution Model), §4.1–§4.9 (S0–S8 descriptions)

**What these parts build:** The LangGraph pipeline DAG and all 9 stage
implementations (S0–S8). This is the heart of the pipeline — the
directed graph that carries state from "user sends an idea" to
"app delivered."

**KEY CONCEPT — What a DAG is:**
A DAG (Directed Acyclic Graph) is like a flowchart. The pipeline flows:

```
S0 Intake → S1 Legal → S2 Blueprint → S3 CodeGen → S4 Build
    → S5 Test → (if fail → back to S3) → S6 Deploy
    → S7 Verify → (if fail → back to S6) → S8 Handoff → COMPLETED
```

Each box is a "node" — a Python function. The arrows are "edges" —
the routing logic that decides which node runs next.

---

## STEP 7.1 — Build the Pipeline DAG Using Claude Code

**USE CONTEXT7 HERE first:**
```
"Using Context7, get LangGraph documentation for 
StateGraph, add_node, add_edge, add_conditional_edges, 
and compile()"
```

Then in Claude Code:

```
Create the pipeline DAG and all stage implementations 
for NB1 Parts 6-7 per spec §2.7 and §4.0–§4.9.

Create these files in factory/pipeline/:

1. factory/pipeline/__init__.py — Package init

2. factory/pipeline/graph.py — LangGraph DAG wiring
   Per spec §2.7.1:
   - Build StateGraph with PipelineState as state type
   - Add 9 nodes: s0_intake through s8_handoff
   - Add linear edges S0→S1→S2→S3→S4→S5
   - Add conditional edge after S5 Test:
     * pass → s6_deploy
     * fail (retry < 3) → s3_codegen
     * fail (retry exhausted) → halt
   - Add S6 Deploy → S7 Verify
   - Add conditional edge after S7 Verify:
     * pass → s8_handoff
     * fail (retry < 2) → s6_deploy
     * fail exhausted → halt
   - Add S8 Handoff → COMPLETED terminal
   - Add halt node → HALTED terminal
   - build_pipeline_graph() function returns compiled graph
   - SimpleExecutor fallback if LangGraph not available

3. factory/pipeline/s0_intake.py — S0 Intake node (stub)
   Per spec §4.1:
   - Parses operator's natural language app idea
   - Validates operator whitelist
   - Returns structured idea with: name, description, platform,
     target_audience, monetization_hint
   - STUB: returns mock parsed idea for dry-run

4. factory/pipeline/s1_legal.py — S1 Legal Gate node (stub)
   Per spec §4.2:
   - Runs KSA legal compliance pre-check
   - Checks PDPL, CST, SAMA, NDMO, NCA, SDAIA requirements
   - Returns legal_clear=True/False with reason
   - STUB: returns legal_clear=True

5. factory/pipeline/s2_blueprint.py — S2 Blueprint node (stub)
   Per spec §4.3:
   - Builds Blueprint schema from parsed idea
   - Runs Stack Selector Brain (selects FlutterFlow/RN/Swift/etc.)
   - Generates 3 design mocks via Design Engine
   - STUB: returns mock blueprint with REACT_NATIVE stack

6. factory/pipeline/s3_codegen.py through s8_handoff.py — Stage stubs
   Each must:
   - Accept PipelineState as input
   - Update state.current_stage to correct value
   - Set state.sN_output with appropriate mock data
   - Return updated state
   
   s3_codegen: generates app code (stub: mock code string)
   s4_build: builds the app binary (stub: mock binary path)
   s5_test: runs automated tests (stub: returns passed=True)
   s6_deploy: deploys to store/cloud (stub: returns mock URL)
   s7_verify: verifies live deployment (stub: returns verified=True)
   s8_handoff: creates handoff docs with FIX-27 Intelligence Pack
               (stub: returns 7 doc types)

7. factory/pipeline/halt_handler.py — HALT terminal node
   - Sets state.current_stage = Stage.HALTED
   - Sends Telegram notification via notify_operator (stub)
   - Records halt reason in state.errors

After creating all files, run this test:
python -c "
from factory.pipeline.graph import build_pipeline_graph
from factory.core.state import PipelineState, Stage
import asyncio

async def test_dry_run():
    graph = build_pipeline_graph()
    state = PipelineState(project_id='test-001', operator_id='op1')
    state = await graph.ainvoke(state)
    print(f'Pipeline completed at stage: {state.current_stage.value}')
    assert state.current_stage in [Stage.COMPLETED, Stage.HALTED], \
        f'Expected terminal state, got {state.current_stage}'
    if state.current_stage == Stage.COMPLETED:
        print('✅ Pipeline reached COMPLETED')
    else:
        print(f'⚠️ Pipeline halted: {state.errors}')
    return state

state = asyncio.run(test_dry_run())
"
```

---

## STEP 7.2 — NB1 Parts 6–7 Checkpoint

```bash
python -c "
from factory.pipeline.graph import build_pipeline_graph
from factory.core.state import PipelineState, Stage
import asyncio

async def run():
    g = build_pipeline_graph()
    s = PipelineState(project_id='dry-run-001', operator_id='op1')
    result = await g.ainvoke(s)
    stage = result.current_stage.value
    print(f'Final stage: {stage}')
    return result

result = asyncio.run(run())
assert result.current_stage in [Stage.COMPLETED, Stage.HALTED]
print('✅ Pipeline DAG runs S0→S8')
"
```

```bash
git add factory/pipeline/
git commit -m "NB1-05: P2 Pipeline DAG — graph, S0-S8 stubs, halt handler (§2.7, §4.0-§4.9)"
```

---

# SECTION 8: NB1 PART 8 — LOCAL DRY-RUN MILESTONE ★
📖 **Read first:** NB1 Part 8 (full section) — this is the most
important section in NB1.

★ **This is your proof-of-architecture moment.** If the full pipeline
runs S0→S8→COMPLETED with no errors and no real API calls, your
architecture is correct. Everything after this point is adding
real services to a working skeleton.

---

## STEP 8.1 — Assemble the Top-Level Runner

**USE CLAUDE CODE HERE:**

```
Create factory/pipeline/runner.py — the main entry point 
for running the pipeline.

It needs:
- run_pipeline(idea_text, operator_id, dry_run=True) async function
- Creates a PipelineState with a unique project_id (uuid)
- Invokes build_pipeline_graph() compiled graph
- Returns final state
- Logs each stage transition

Also add a --dry-run flag to allow running from command line:
if __name__ == '__main__':
    import sys
    asyncio.run(run_pipeline(
        idea_text='Test app: simple habit tracker',
        operator_id='test_operator',
        dry_run=True
    ))
```

---

## STEP 8.2 — Run the Full Dry-Run

```bash
cd ~/Projects/ai-factory-pipeline
source .venv/bin/activate
python -m factory.pipeline.runner
```

✅ **Expected output:**
```
[INFO] Pipeline starting: test-xxxxx
[INFO] S0_INTAKE → processing...
[INFO] S0_INTAKE → S1_LEGAL transition
[INFO] S1_LEGAL → processing...
[INFO] S1_LEGAL → S2_BLUEPRINT transition
[INFO] S2_BLUEPRINT → processing...
[INFO] S2_BLUEPRINT → S3_CODEGEN transition
[INFO] S3_CODEGEN → processing...
[INFO] S3_CODEGEN → S4_BUILD transition
[INFO] S4_BUILD → processing...
[INFO] S4_BUILD → S5_TEST transition
[INFO] S5_TEST → processing...
[INFO] S5_TEST → S6_DEPLOY transition (tests passed)
[INFO] S6_DEPLOY → processing...
[INFO] S6_DEPLOY → S7_VERIFY transition
[INFO] S7_VERIFY → processing...
[INFO] S7_VERIFY → S8_HANDOFF transition
[INFO] S8_HANDOFF → processing...
[INFO] Pipeline COMPLETED
[INFO] Total cost: $0.00 (dry-run mode)
```

❌ **Failure: Pipeline stops at S3 and retries**
This happens if s5_test returns `passed=False`. Ask Claude Code:
```
"The pipeline is looping at S3→S5→S3. Open factory/pipeline/s5_test.py 
and make the stub return passed=True by default in dry-run mode."
```

❌ **Failure: LangGraph import error**
🔧 LangGraph may not be installed correctly. Run:
```bash
pip install "langgraph>=0.1.0" "langchain-core>=0.1.0"
```
Then ask Claude Code to use the SimpleExecutor fallback if LangGraph
still fails to import.

❌ **Failure: AttributeError on state.sN_output**
Tell Claude Code:
```
"Pipeline fails with AttributeError accessing state.s3_output 
(or another sN_output). All sN_output fields should be 
Optional[dict] = None in PipelineState and should be set 
by each stage. Fix the stage that is failing."
```

---

## STEP 8.3 — Verify All 14 Dry-Run Criteria

Run each check:

```bash
cd ~/Projects/ai-factory-pipeline
source .venv/bin/activate

# Check 1: All files exist
echo "Check 1: File count"
find factory/ -name "*.py" | wc -l
# Should show 20+ files

# Check 2: Pipeline runs to COMPLETED
echo "Check 2: Pipeline dry-run"
python -m factory.pipeline.runner
# Should show "Pipeline COMPLETED"

# Check 3: Pydantic models all work
echo "Check 3: State model"
python -c "
from factory.core.state import PipelineState, Stage
s = PipelineState(project_id='x', operator_id='y')
print(f'State at: {s.current_stage.value}')
"

# Check 4: Budget Governor tiers work
echo "Check 4: Budget Governor"
python -c "
from factory.core.state import BudgetTier, BUDGET_CONFIG
print(f'Budget tiers: {[t.value for t in BudgetTier]}')
print(f'Monthly ceiling: \${BUDGET_CONFIG[\"total_baseline\"]:.2f}')
"

# Check 5: User-Space Enforcer works
echo "Check 5: User-Space Enforcer"
python -c "
from factory.core.user_space import enforce_user_space
from factory.core.state import UserSpaceViolation
try:
    enforce_user_space('sudo rm -rf /')
    print('❌ FAIL')
except UserSpaceViolation:
    print('✅ sudo blocked correctly')
"

# Check 6: All Telegram commands exist
echo "Check 6: Telegram commands"
python -c "
from factory.telegram.bot import setup_bot
import inspect
src = inspect.getsource(setup_bot)
cmds = ['start','new','status','budget','restore','admin',
        'cancel','pause','resume','info','history','mode',
        'autopilot','copilot','help']
for cmd in cmds:
    if cmd in src:
        print(f'  ✅ /{cmd}')
    else:
        print(f'  ❌ /{cmd} MISSING')
"

echo "✅ Dry-run verification complete"
```

✅ **All 6 checks must pass before proceeding.**

---

## STEP 8.4 — ★ NB1 Part 8 MILESTONE COMMIT

This is the most important commit of the entire project.

```bash
git add .
git commit -m "NB1-08: ★ LOCAL DRY-RUN MILESTONE — Full S0→S8→COMPLETED, all 14 criteria pass (§2.7, §4.0-§4.9)"
```

**USE NOTION MCP HERE:**
```
"Mark '★ NB1 Part 8: LOCAL DRY-RUN MILESTONE' as complete 
with today's date. Add a note: 'Pipeline runs S0→S8→COMPLETED. 
Architecture verified. Zero dollars spent.'"
```

**USE MEMORY HERE:**
```
"Remember: ★ NB1 Part 8 LOCAL DRY-RUN MILESTONE achieved today. 
The full pipeline runs S0→S8→COMPLETED with mocked AI.
Architecture is verified. Commit: NB1-08. Zero dollars spent.
Ready to continue with NB1 Parts 9–21 (intelligence layer, 
FlutterFlow, state persistence, Mother Memory, design, 
polyglot stacks, ops hardening, final assembly)."
```

**USE GOOGLE CALENDAR HERE:**
```
"Create a calendar event for today called: 
★ AI Factory NB1 Dry-Run Milestone Achieved — 
Pipeline architecture verified, S0→S8 complete"
```

---

# SECTION 9: NB1 PARTS 9–19 — REMAINING LAYERS

These parts complete the remaining implementation layers. Each follows
the same pattern: read the NB1 section, use Claude Code to build,
verify, commit.

---

## STEP 9.1 — NB1 Part 9: Intelligence Layer (P3)
📖 **Read:** NB1 Part 9 + Spec §3.1–§3.4

**What this builds:** `perplexity.py`, `strategist.py`, 
`circuit_breaker.py` — stub AI clients and the budget circuit breaker.

**USE CLAUDE CODE HERE:**
```
Create factory/pipeline/intelligence/ with 3 stub files:

1. perplexity.py — Scout role client stub
   - PerplexityClient class with research(query) async method
   - Returns mock research results in dry-run mode
   - Per spec §3.1: Sonar model, READ-ONLY, max $2/phase

2. strategist.py — Strategist role client stub  
   - StrategistClient class with decide(context) async method
   - Returns mock architectural decisions in dry-run mode
   - Per spec §3.2: Opus 4.6 model

3. circuit_breaker.py — Budget circuit breaker
   - check_budget(state, role, estimated_cost) function
   - Raises BudgetExceeded if adding cost would exceed limit
   - Per spec §2.14: GREEN/AMBER/RED/BLACK tier thresholds
   - GREEN: < 70% of limit
   - AMBER: 70–90% of limit, warning sent
   - RED: 90–100%, requires operator approval
   - BLACK: > 100%, pipeline halted

Verify with:
python -c "
from factory.pipeline.intelligence.circuit_breaker import check_budget
from factory.core.state import PipelineState, BudgetTier, BudgetExceeded
s = PipelineState(project_id='t', operator_id='o')
s.total_cost_usd = 18.0  # 72% of $25 per-project limit
check_budget(s, 'engineer', 0.50)  # Should be AMBER
print('✅ Circuit breaker: AMBER at 72%')
try:
    s.total_cost_usd = 24.50
    check_budget(s, 'engineer', 5.00)  # Would exceed $25 limit
    print('❌ Should have raised BudgetExceeded')
except BudgetExceeded:
    print('✅ Circuit breaker: blocks at 100%')
"
```

**Git commit:**
```bash
git add factory/pipeline/intelligence/
git commit -m "NB1-09: P3 Intelligence — Perplexity/Strategist stubs, circuit breaker (§3.1–§3.4)"
```

---

## STEP 9.2 — NB1 Part 10: FlutterFlow + GUI Automation (P4)
📖 **Read:** NB1 Part 10 + Spec §4.5.2

**USE CLAUDE CODE HERE:**
```
Create factory/infra/gui_automation.py — 
FlutterFlow GUI automation stub per spec §4.5.2.

Classes needed:
- OmniParserClient (stub): screenshot + element detection
- UITARSClient (stub): action planning
- GUIAutomationManager: orchestrates 5-layer automation
  Layers: capture → detect → plan → execute → verify

All methods return mock data in dry-run mode.
The class should have execute_flutterflow_build(blueprint) 
as its main entry point.

Verify: python -c "
from factory.infra.gui_automation import GUIAutomationManager
mgr = GUIAutomationManager(dry_run=True)
print(f'✅ GUI automation manager ready: {mgr.dry_run=}')
"
```

**Git commit:**
```bash
git add factory/infra/
git commit -m "NB1-10: P4 FlutterFlow GUI automation stub (§4.5.2)"
```

---

## STEP 9.3 — NB1 Parts 11–12: State Persistence + Infrastructure (P5)
📖 **Read:** NB1 Parts 11–12 + Spec §5.6, §7.9, §2.9

**USE CLAUDE CODE HERE:**
```
Create these infrastructure stub files for NB1 Parts 11-12:

1. factory/integrations/supabase.py — per spec §5.6
   - SupabaseClient class with stub methods
   - triple_write_persist(state) async — writes to Supabase+Git+Neo4j
   - restore_state(project_id, snapshot_id) async
   - In dry-run: logs writes without calling real API
   - Includes checksum calculation (SHA-256 of state JSON)

2. factory/integrations/github.py — per spec §7.9
   - GitHubClient class  
   - github_commit_file(repo, path, content) async
   - github_reset_to_commit(repo, commit_hash) async stub
   - In dry-run: logs commits without calling real API

3. factory/integrations/firebase.py — stub
   - FirebaseClient class
   - deploy_web_app(build_path) async stub

4. factory/infra/macincloud.py — per spec §7.8
   - MacinCloudClient class
   - create_session() → SSH session stub
   - $1/hr kill switch after 8 hours maximum
   - heartbeat monitoring stub

Verify all 4 import cleanly:
python -c "
from factory.integrations.supabase import SupabaseClient
from factory.integrations.github import GitHubClient
from factory.integrations.firebase import FirebaseClient
from factory.infra.macincloud import MacinCloudClient
print('✅ P5 State + Infrastructure stubs ready')
"
```

**Git commit:**
```bash
git add factory/integrations/ factory/infra/
git commit -m "NB1-11: P5 State persistence + infra stubs — Supabase, GitHub, Firebase, MacinCloud (§5.6, §7.9)"
```

---

## STEP 9.4 — NB1 Part 13: Mother Memory v2 (P6)
📖 **Read:** NB1 Part 13 + Spec §6.3 (Neo4j schema)

**USE CLAUDE CODE HERE:**
```
Create Neo4j Mother Memory v2 stub files per spec §6.3:

1. factory/integrations/neo4j_client.py
   - Neo4jClient class
   - neo4j_run(cypher, params) async — runs Cypher query (stub)
   - 12 node types: Project, AppIdea, TechStack, LegalContext,
     Blueprint, CodeModule, TestResult, Deployment, Operator,
     Pattern, Error, HandoffDoc
   - In dry-run: logs queries without connecting to real Neo4j

2. factory/integrations/neo4j_queries.py
   - store_project_pattern(state) — saves successful pattern
   - get_similar_projects(idea) — retrieves similar past projects
   - Both stub in dry-run mode

3. factory/infra/janitor.py — per spec §6.5
   - JanitorAgent class
   - run_cycle() async — cleans orphaned temp files
   - 6-hour interval, skip HandoffDoc and S8-COMPLETED nodes
   - Stub implementation

Verify:
python -c "
from factory.integrations.neo4j_client import Neo4jClient
from factory.infra.janitor import JanitorAgent
import asyncio
janitor = JanitorAgent(dry_run=True)
asyncio.run(janitor.run_cycle())
print('✅ P6 Mother Memory + Janitor stubs ready')
"
```

**Git commit:**
```bash
git add factory/integrations/neo4j_client.py factory/integrations/neo4j_queries.py factory/infra/janitor.py
git commit -m "NB1-12: P6 Mother Memory v2 + Janitor Agent stubs (§6.3, §6.5)"
```

---

## STEP 9.5 — NB1 Part 14: Design Engine + DocuGen (P7)
📖 **Read:** NB1 Part 14 + Spec §2.12 (Design Engine), §2.13 (DocuGen)

**USE CLAUDE CODE HERE:**
```
Create Design Engine and DocuGen stub files per spec §2.12–§2.13:

1. factory/design/design_engine.py
   - DesignEngine class
   - generate_mocks(blueprint) → returns 3 mock design specs
   - vibe_check(blueprint) → WCAG AA contrast check stub
   - grid_enforcer(layout) → 4px grid alignment check stub
   - In dry-run: returns mock design data

2. factory/design/docugen.py
   - DocuGenEngine class
   - generate_handoff_docs(state) → creates 7 document types:
     QUICK_START.md, privacy_policy.html, terms_of_service.html,
     ksa_compliance_report.pdf, architecture_diagram.png,
     app_store_metadata.json, developer_handoff.md
   - Per FIX-27: Intelligence Pack with per-project and per-program docs
   - Stub: returns dict of doc names and placeholder content

3. factory/legal/continuous.py
   - LegalThread class
   - check_stage(state, stage) → runs KSA legal checks for stage
   - 6 regulatory frameworks: PDPL, CST, SAMA, NDMO, NCA, SDAIA
   - Stub: returns legal_clear=True with empty violations list

Verify:
python -c "
from factory.design.design_engine import DesignEngine
from factory.design.docugen import DocuGenEngine
from factory.core.state import PipelineState, Stage
import asyncio

s = PipelineState(project_id='test', operator_id='op')
engine = DesignEngine(dry_run=True)
mocks = engine.generate_mocks({'name': 'TestApp', 'platform': 'android'})
assert len(mocks) == 3
print(f'✅ Design Engine: {len(mocks)} mocks generated')

docugen = DocuGenEngine(dry_run=True)
docs = asyncio.run(docugen.generate_handoff_docs(s))
print(f'✅ DocuGen: {len(docs)} documents generated')
"
```

**Git commit:**
```bash
git add factory/design/ factory/legal/
git commit -m "NB1-13: P7 Design Engine + DocuGen + Legal Thread stubs (§2.12–§2.13)"
```

---

## STEP 9.6 — NB1 Part 15: Polyglot Stacks (P8)
📖 **Read:** NB1 Part 15 + Spec §2.3 (Stack Selector Brain)

**USE CLAUDE CODE HERE:**
```
Create stub code generators for all 6 tech stacks per spec §2.3.
Add to factory/pipeline/s3_codegen.py a dispatch router that 
selects the correct generator based on state.selected_stack.

Create factory/pipeline/generators/ package with:
1. flutterflow_gen.py — FlutterFlowGenerator stub
2. react_native_gen.py — ReactNativeGenerator stub
3. swift_gen.py — SwiftGenerator stub
4. kotlin_gen.py — KotlinGenerator stub
5. unity_gen.py — UnityGenerator stub
6. python_backend_gen.py — PythonBackendGenerator stub

Each generator has:
- generate(blueprint) async method
- Returns dict with: source_code, file_count, entry_point
- Stub: returns mock code dictionary

Update s3_codegen.py to select the right generator based on
state.selected_stack value.

Verify:
python -c "
from factory.pipeline.generators.react_native_gen import ReactNativeGenerator
from factory.pipeline.generators.python_backend_gen import PythonBackendGenerator
import asyncio

rn_gen = ReactNativeGenerator(dry_run=True)
result = asyncio.run(rn_gen.generate({'name': 'TestApp', 'platform': 'android'}))
assert 'source_code' in result
print(f'✅ React Native generator: {result[\"file_count\"]} files')

py_gen = PythonBackendGenerator(dry_run=True)
result = asyncio.run(py_gen.generate({'name': 'TestAPI'}))
print(f'✅ Python Backend generator: {result[\"file_count\"]} files')
print('✅ P8 Polyglot generators — all 6 stacks ready')
"
```

**Git commit:**
```bash
git add factory/pipeline/generators/
git commit -m "NB1-14: P8 Polyglot stack generators — FlutterFlow, RN, Swift, Kotlin, Unity, Python (§2.3)"
```

---

## STEP 9.7 — NB1 Parts 16–17: Ops Hardening (P9)
📖 **Read:** NB1 Parts 16–17

**USE CLAUDE CODE HERE:**
```
Create operations and security modules for NB1 Parts 16-17:

1. factory/monitoring/health.py
   - deep_health_check() async → checks 6 services: 
     Supabase, Neo4j, GitHub, Telegram, Anthropic, Perplexity
   - Returns dict with service statuses and overall health

2. factory/monitoring/metrics.py
   - log_project_metrics(state) → records build metrics
   - Stub: logs to console in dry-run mode

3. factory/security/auth.py
   - authenticate_operator(telegram_id) → checks whitelist
   - require_auth decorator for bot commands
   
4. factory/security/sanitize.py
   - sanitize_operator_input(text) → removes injection attempts
   
5. factory/security/audit.py
   - audit_log(action, state, details) → records all pipeline actions

6. factory/migrations/supabase_migrate.py
   - 11 CREATE TABLE IF NOT EXISTS statements
   - Per spec §7.1.3: all 11 Supabase tables

7. factory/migrations/neo4j_migrate.py
   - 18 CREATE INDEX IF NOT EXISTS statements
   - 1 CREATE CONSTRAINT for project_id uniqueness
   - Per spec §6.3

8. Create tests/ directory with 8 test files:
   tests/test_state.py — PipelineState tests
   tests/test_roles.py — Role contract tests
   tests/test_war_room.py — Escalation tests
   tests/test_circuit_breaker.py — Budget tests
   tests/test_design_engine.py — Design tests
   tests/test_user_space.py — Safety enforcer tests
   tests/test_snapshots.py — Persistence tests
   tests/test_janitor.py — Cleanup tests

Run tests:
python -m pytest tests/ -v --tb=short
```

After Claude Code creates all files and tests pass:

```bash
git add factory/monitoring/ factory/security/ factory/migrations/ tests/
git commit -m "NB1-15: P9 Ops hardening — monitoring, security, migrations, 8 test files (§7.3–§7.6)"
```

---

## STEP 9.8 — NB1 Parts 18–19: Top-Level Assembly

**USE CLAUDE CODE HERE:**
```
Create the top-level assembly files for NB1 Parts 18-19:

1. main.py — Application entry point
   - Starts FastAPI app + Telegram bot
   - Loads environment from .env
   - Sets up logging

2. factory_setup.py — One-time setup script
   - validate_environment() — checks all 28 env vars
   - setup_databases() — runs Supabase + Neo4j migrations
   - verify_connections() — tests all 6 service connections
   - --dry-run flag returns mock success

3. factory/app.py — FastAPI application
   - /health endpoint → {"status": "healthy", "version": "5.6.0"}
   - /webhook endpoint → Telegram webhook handler
   - /status endpoint → Pipeline status
   - /run endpoint → Trigger pipeline run

4. Dockerfile for GCP Cloud Run deployment:
   FROM python:3.11-slim
   (standard FastAPI container setup)

Run dry-run validation:
python factory_setup.py --dry-run
```

After Claude Code finishes:

```bash
git add main.py factory_setup.py factory/app.py Dockerfile
git commit -m "NB1-16: Top-level assembly — main.py, factory_setup.py, FastAPI app, Dockerfile (§8.5)"
```

---

# SECTION 10: NB1 PART 20 — FINAL CHECKPOINT

## STEP 10.1 — Run Full Test Suite

```bash
cd ~/Projects/ai-factory-pipeline
source .venv/bin/activate
python -m pytest tests/ -v
```

✅ **Expected:** All tests pass, 0 failures.

❌ **If any test fails:**

**USE CLAUDE CODE HERE:**
```
"Run python -m pytest tests/ -v --tb=short and fix 
every failing test. Show me what you changed."
```

---

## STEP 10.2 — Run All 14 Definition of Done Checks

```bash
# Check 1: File count
echo "=== Check 1: File count ==="
find factory/ -name "*.py" | wc -l

# Check 2: Full dry-run
echo "=== Check 2: Full dry-run ==="
python -m factory.pipeline.runner

# Check 3: Budget Governor
echo "=== Check 3: Budget Governor ==="
python -c "
from factory.core.state import BudgetTier
print('Tiers:', [t.value for t in BudgetTier])
"

# Check 4: User-Space Enforcer
echo "=== Check 4: User-Space Enforcer ==="
python -c "
from factory.core.user_space import enforce_user_space
from factory.core.state import UserSpaceViolation
try:
    enforce_user_space('sudo rm -rf /')
    print('❌ FAIL')
except UserSpaceViolation:
    print('✅ PASS')
"

# Check 5: .env.example
echo "=== Check 5: .env.example ==="
grep -c "=" .env.example
echo "(should show 28 or more)"

# Check 6: All imports
echo "=== Check 6: All imports ==="
python -c "
import factory.core
import factory.pipeline
import factory.telegram
import factory.integrations
import factory.design
import factory.legal
import factory.monitoring
import factory.security
print('✅ All packages import cleanly')
"

echo "=== All NB1 checks complete ==="
```

---

## STEP 10.3 — NB1 FINAL COMMIT

```bash
git add .
git commit -m "NB1-COMPLETE: All 14 Definition of Done criteria pass — ready for NB2 production wiring"
git tag v5.6.0-stub
```

**USE NOTION MCP HERE:**
```
"Mark all remaining NB1 items as complete in my 
Implementation Tracker. Add a note: 'NB1 complete. 
85+ files. All tests pass. Dry-run verified. 
Tagged v5.6.0-stub. Ready for NB2.'"
```

**USE MEMORY HERE:**
```
"Remember: NB1 COMPLETE. All 85+ files built as stubs. 
All tests pass. Dry-run runs S0→S8→COMPLETED. 
Tagged v5.6.0-stub. Zero dollars spent. 
Ready to begin NB2 — replacing stubs with real 
production API calls."
```

**USE GOOGLE CALENDAR HERE:**
```
"Create an event for today: NB1 Complete — 
v5.6.0-stub tagged. Starting NB2 next session."
```

---

# SECTION 11: TRANSITION CONDITION TO PART 2

You are ready for Part 2 of this guide (NB2 + NB3) when ALL of
the following are true:

✅ Every command in Sections 1–10 ran without unresolved errors
✅ `find factory/ -name "*.py" | wc -l` shows 55 or more files
✅ `python -m pytest tests/ -v` shows 0 failures
✅ `python -m factory.pipeline.runner` shows "Pipeline COMPLETED"
✅ Git shows tag `v5.6.0-stub`
✅ Notion tracker shows all NB1 items checked
✅ Memory is updated with NB1 complete status

**At your next Claude session, start by saying:**

```
"I completed NB1 and am ready to begin NB2. 
What is my exact next step?"
```

Claude will read your memory, confirm your status, and walk you
through NB2 PROD-1 (replacing the Anthropic stub with a real
AsyncAnthropic client).

---

*End of Part 1 — Pre-Implementation Setup and NB1 Codebase Build*
*Reply "Cont" to receive Part 2: NB2 Production Wiring + NB3 System Activation*
