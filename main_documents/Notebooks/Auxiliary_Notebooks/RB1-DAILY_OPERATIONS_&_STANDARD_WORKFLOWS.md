# RESPONSE PLAN for RB1: DAILY OPERATIONS & STANDARD WORKFLOWS

```
═══════════════════════════════════════════════════════════════════════════════
RB1 GENERATION PLAN - 5 PARTS
═══════════════════════════════════════════════════════════════════════════════

Part 1: Front Matter + Overview + Prerequisites + Section 1 (Starting Your Day)
Part 2: Section 2 (Standard Workflows - Evaluate, Create, Modify, Status)
Part 3: Section 3 (Interpreting Telegram Notifications) + Section 4 (Execution Mode Selection)
Part 4: Section 5-7 (Daily/Weekly/Monthly Tasks) + Quick Reference
Part 5: Troubleshooting + Next Steps

Delivering Part 1 now. Reply "Cont" for Part 2.
```

---

# RB1: DAILY OPERATIONS & STANDARD WORKFLOWS

---

**PURPOSE:** Master routine pipeline operations for building, updating, and monitoring your apps efficiently.

**WHEN TO USE:** Every day when operating the AI Factory Pipeline to build or manage apps.

**ESTIMATED LENGTH:** 30-40 pages

**PREREQUISITE READING:** 
- Pipeline setup complete (NB1-4 implementation notebooks)
- Pipeline is running and responding to Telegram commands
- Have built at least one app (NB5 recommended but not required)

**TIME COMMITMENT:** 
- Daily routine: 5-10 minutes
- Build/update operations: 30-60 minutes (mostly automated, passive monitoring)
- Weekly maintenance: 15-30 minutes
- Monthly review: 30-60 minutes

**WHAT YOU'LL MASTER:**
- ✅ Starting and stopping pipeline correctly
- ✅ All Telegram commands and their proper usage
- ✅ Building new apps with /create
- ✅ Updating existing apps with /modify
- ✅ Understanding pipeline notifications and status messages
- ✅ Choosing correct execution modes (CLOUD/LOCAL/HYBRID)
- ✅ Daily, weekly, and monthly operational tasks
- ✅ Monitoring builds and identifying issues early

---

## 1. OVERVIEW

### 1.1 What This Runbook Covers

This is your operational manual for day-to-day pipeline usage. Unlike NB5 (which covers your first 30 days building a specific app), this runbook focuses on **how to operate the pipeline itself** as a daily tool.

**You'll learn:**

**Core Operations:**
- How to properly start/stop the pipeline
- How to check pipeline health and status
- How to queue and manage multiple builds
- How to monitor build progress without constant checking

**Standard Workflows:**
- Evaluating app ideas before building (/evaluate)
- Creating new apps from specifications (/create)
- Modifying existing apps with updates (/modify)
- Checking status and getting information (/status, /info)

**Understanding Feedback:**
- What Telegram notifications mean
- How to interpret stage completion messages (S0-S7)
- When to worry vs when to wait
- How to read error messages and logs

**Mode Management:**
- When to use CLOUD mode (iOS builds, $1.20)
- When to use LOCAL mode (Android/Web, free)
- When to use HYBRID mode (best of both, $0.20)
- How to switch between modes safely

**Routine Maintenance:**
- Daily health checks (5 minutes)
- Weekly maintenance tasks (30 minutes)
- Monthly optimization and cost review (1 hour)

### 1.2 Who Needs This Runbook

**You need this runbook if:**
- ✅ Pipeline is installed and running
- ✅ You've completed setup (NB1-4)
- ✅ You plan to use pipeline regularly (weekly or more)
- ✅ You want to build multiple apps efficiently
- ✅ You want to understand what's happening during builds

**You might not need this yet if:**
- ❌ Pipeline isn't installed (do NB1-4 first)
- ❌ You've never built an app (do NB5 first for guided experience)
- ❌ You only plan to build one app ever (NB5 alone is enough)
- ❌ Someone else operates pipeline for you (give them this runbook)

**This runbook is perfect for:**
- Solo developers building portfolio of apps
- Non-technical operators managing pipeline
- Teams with dedicated pipeline operator role
- Anyone using pipeline as daily production tool

### 1.3 How This Runbook Is Organized

**Section 1: Starting Your Day**
- How to start pipeline (if not always-on)
- Morning health check routine
- What to verify before queueing builds

**Section 2: Standard Workflows**
- /evaluate: Validate app ideas
- /create: Build new apps
- /modify: Update existing apps
- /status, /info, /logs: Get information

**Section 3: Interpreting Notifications**
- Stage-by-stage breakdown (S0-S7)
- What each message means in plain English
- Normal vs concerning timing
- Error notification handling

**Section 4: Execution Mode Selection**
- CLOUD vs LOCAL vs HYBRID decision tree
- Cost implications of each mode
- Performance tradeoffs
- When to switch modes

**Section 5: Daily Tasks**
- Morning routine (5-10 min)
- During builds (passive monitoring)
- Evening review (10-15 min)

**Section 6: Weekly Tasks**
- Monday planning
- Wednesday mid-week check
- Friday week review and cost analysis

**Section 7: Monthly Tasks**
- Cost review and optimization
- Metrics reporting
- Backup verification
- Update planning

**Quick Reference**
- All commands with syntax
- Common error codes
- Decision trees
- Timing expectations

**Troubleshooting**
- Pipeline won't start
- Builds failing consistently
- Slow performance
- Cost higher than expected

### 1.4 Important Terminology (Plain English)

**Pipeline** = The AI Factory Pipeline software running on your computer. Think of it as a factory that builds apps automatically when you give it instructions via Telegram.

**Telegram Bot** = Your communication channel with the pipeline. You send commands (text messages) to the bot, and the bot sends you updates about what the pipeline is doing.

**Build** = The process of creating an app. When you send `/create` command, the pipeline starts a "build" that goes through 8 stages (S0-S7) and produces a working app at the end.

**Stage (S0-S7)** = One step in the build process:
- S0 = Planning (pipeline reads your specification)
- S1 = Design (pipeline creates UI mockups)
- S2 = Code Generation (pipeline writes all the code)
- S3 = Testing (pipeline runs automated tests)
- S4 = Build (pipeline compiles code into actual app file)
- S5 = Quality Check (pipeline scans for security issues)
- S6 = Deployment (pipeline uploads to GitHub and Firebase)
- S7 = Monitoring Setup (pipeline configures error tracking)

**Execution Mode** = Where the pipeline does its work:
- CLOUD = Pipeline rents cloud computers to do the work
- LOCAL = Pipeline uses your own computer to do the work
- HYBRID = Pipeline uses mix of your computer and cloud

**Queue** = List of builds waiting to be processed. Pipeline handles one build at a time, others wait in queue.

**Artifact** = Output file from a build. For apps, this is the APK (Android), IPA (iOS), or deployed website (Web).

**Repository (Repo)** = Storage location for your app's source code on GitHub. Every app gets its own repository.

**Metadata** = Information about your app stored by pipeline (name, platform, version, build history, etc.).

**Telegram Command** = Message you send to bot that starts with `/` (slash). Examples: `/status`, `/create`, `/modify`.

**Notification** = Automatic message bot sends you when something happens (stage completes, error occurs, build finishes).

---

## 2. PREREQUISITES CHECKLIST

Before using pipeline daily, verify these are complete:

### 2.1 Installation Prerequisites

□ **Pipeline is installed**
- Software is on your computer
- Installation completed successfully
- No error messages during install

□ **All dependencies installed**
- Python 3.11+ installed
- Node.js 18+ installed
- Git installed
- Platform-specific tools (Xcode for iOS, Android Studio for Android)

□ **Configuration file complete**
- `.env` file exists in pipeline directory
- Contains all required API keys
- No placeholder values remaining

□ **API keys are valid**
- Anthropic API key (for Claude AI)
- GitHub personal access token
- Firebase project credentials
- GCP service account (if using CLOUD mode)

### 2.2 Account Prerequisites

□ **Telegram bot created and connected**
- Bot exists and is active
- You can send messages to it
- Bot responds to `/help` command

□ **GitHub account configured**
- Account exists and is accessible
- Pipeline can create repositories
- SSH key or token configured

□ **Firebase project set up**
- Project created in Firebase console
- Pipeline connected to project
- Hosting and App Distribution enabled

□ **Cloud accounts (if using CLOUD mode)**
- GCP account with billing enabled (for Cloud Run, Secret Manager)
- MacinCloud account (only if building iOS apps in CLOUD mode)

### 2.3 Operational Prerequisites

□ **Pipeline runs successfully**
- Can start pipeline without errors
- Stays running (doesn't crash immediately)
- Responds to `/status` command

□ **Network connectivity works**
- Internet connection is stable
- Pipeline can reach external services
- No firewall blocking connections

□ **Disk space available**
- At least 10GB free space (for builds)
- More space needed for multiple concurrent projects
- Build artifacts stored temporarily

□ **Know your execution mode**
- Understand which mode you're using
- Know why you chose that mode
- Can switch modes if needed

### 2.4 Knowledge Prerequisites

You should understand (at basic level):
- ✅ How to use Telegram messaging app
- ✅ What your pipeline does (builds apps from text descriptions)
- ✅ Basic concept of builds taking time (25-40 minutes)
- ✅ Apps go through stages S0-S7 during build
- ✅ Telegram bot will notify you of progress

You do NOT need to know:
- ❌ How to code
- ❌ How the pipeline works internally
- ❌ Technical details of build process
- ❌ Command line beyond basic navigation

### 2.5 Verification Test

**Before proceeding, do this final test:**

**Test 1: Pipeline Health Check**
```
Open Telegram → Find your pipeline bot → Send: /status
```

Expected response:
```
Pipeline Status: ✅ RUNNING
Mode: [CLOUD/LOCAL/HYBRID]
Version: 5.6

Services:
✅ Anthropic API: Connected
✅ GitHub: Connected
✅ Firebase: Connected
✅ [GCP: Connected] (if CLOUD mode)

Current builds: 0 active, 0 queued
Last build: [timestamp or "None"]
Uptime: [hours/days]
```

**If you see errors or "STOPPED":**
- Stop here
- Do not proceed to daily operations
- Go back to NB1-4 (setup notebooks)
- Fix configuration issues first

**Test 2: Simple Command Response**
```
Send to bot: /help
```

Expected response:
```
AI FACTORY PIPELINE v5.8
Available Commands:

BASIC:
/status - Check pipeline health
/help - Show this message
/evaluate - Score an app idea
/create - Build new app
/modify - Update existing app
/info - Get app information

[... rest of help text ...]
```

**If bot doesn't respond within 30 seconds:**
- Pipeline is not running properly
- Restart pipeline: `/restart` (if bot responds at all)
- Or manually restart (see troubleshooting section)

**Test 3: Mode Verification**
```
Send to bot: /config show
```

Expected response:
```
Current Configuration:

EXECUTION_MODE: [CLOUD/LOCAL/HYBRID]
ANTHROPIC_MODEL: claude-sonnet-4-20250514
AUTO_DEPLOY: true
COST_TRACKING: true

[... more config settings ...]
```

**Verify execution mode matches your intention:**
- Building iOS apps? Should be CLOUD
- Building Android/Web on your computer? Should be LOCAL
- Building Android/Web with cloud help? Should be HYBRID

**If mode is wrong:**
```
/config execution_mode [CLOUD/LOCAL/HYBRID]
/restart
```

Wait 30 seconds, then verify with `/status` again.

---

## 3. SECTION 1: STARTING YOUR DAY

### 3.1 If Pipeline Runs 24/7 (Recommended)

**Most users run pipeline continuously** (always on, always ready).

**Advantages:**
- No startup delay
- Can queue builds anytime
- Monitors for issues continuously
- Simpler operation

**Morning routine (2 minutes):**

**Step 1: Quick health check**
```
Open Telegram → Send: /status
```

Look for:
- ✅ Status: RUNNING
- ✅ All services: Connected
- ✅ No error messages

**Step 2: Check overnight builds (if any)**
```
Scroll up in Telegram to see notifications from last 12 hours
```

Look for:
- ✅ BUILD COMPLETE messages
- ⚠️ BUILD FAILED messages (read why)
- ℹ️ Warning messages (non-critical)

**Step 3: Done**
If status is healthy and no failed builds, you're ready for the day.

---

### 3.2 If Pipeline Runs On-Demand (When Needed)

**Some users start/stop pipeline manually** to save computer resources.

**When to use this approach:**
- Limited computer resources (low RAM, slow CPU)
- Only build apps occasionally (few times per week)
- Want to completely shut down pipeline when not in use
- Running on laptop that you move/transport

**How to start pipeline:**

**Method 1: Via Telegram (if configured)**
```
Send to bot: /start
```

Expected response:
```
Starting pipeline...
[Wait 30-60 seconds]
✅ Pipeline started successfully
Mode: [your mode]
Ready to receive commands
```

**Method 2: Via command line**

**On macOS/Linux:**
```bash
cd ~/ai-factory-pipeline
python -m factory.cli start
```

Expected output:
```
AI Factory Pipeline v5.8
Starting services...
✅ Core engine started
✅ Telegram bot connected
✅ External services verified
Pipeline is RUNNING
```

**On Windows:**
```cmd
cd C:\ai-factory-pipeline
python -m factory.cli start
```

**Method 3: Via startup script (if configured)**

**macOS/Linux:**
```bash
~/ai-factory-pipeline/start.sh
```

**Windows:**
```cmd
C:\ai-factory-pipeline\start.bat
```

**Verification after startup:**

Wait 60 seconds, then:
```
Telegram: /status
```

Should show `Status: ✅ RUNNING`

If shows `Status: STOPPED` or `Status: ERROR`:
- Check terminal/command window for error messages
- Common issues:
  - Port already in use (another instance running)
  - Missing API keys
  - Network connectivity problems
- See troubleshooting section

**Expected startup time:**
- First start of day: 45-90 seconds
- Restart (after stop): 30-60 seconds
- After crash/error: 60-120 seconds (recovery mode)

---

### 3.3 Morning Health Check Routine (5 minutes)

**Do this every morning before queueing builds:**

**Check 1: Pipeline Status**
```
/status
```

Verify:
□ Status: RUNNING (not STOPPED or ERROR)
□ Mode: Correct for today's work
□ All services: Connected
□ Current builds: Expected number (0 if nothing running)

**Check 2: Disk Space**

**Why it matters:**
Builds create temporary files (500MB - 2GB per build). If disk is full, builds fail.

**How to check:**

**macOS:**
- Click Apple menu → About This Mac → Storage
- Need: 10GB+ free

**Windows:**
- Open File Explorer → This PC
- Check C: drive
- Need: 10GB+ free

**Linux:**
```bash
df -h ~
```
- Look at "Available" column
- Need: 10GB+ free

**If less than 10GB free:**
```
/cleanup old-builds
```

This removes build artifacts older than 30 days.

Or manually delete from: `~/ai-factory-pipeline/builds/archive/`

**Check 3: Recent Errors (if any)**

```
/logs recent
```

This shows last 50 log entries. Look for:
- ❌ ERROR messages (red, need attention)
- ⚠️ WARNING messages (yellow, informational)
- ✅ INFO messages (normal operation)

**If you see ERROR messages:**
- Note what they say
- Check if builds failed overnight
- See troubleshooting section for common errors
- Consider running `/diagnose` for automated check

**Check 4: Cost Check (if CLOUD mode)**

```
/cost today
```

Shows spending since midnight (your timezone):
```
Cost Summary - Today (March 3, 2026)

Builds: 2 completed
- iOS build (CLOUD): $1.20
- Web build (HYBRID): $0.20

External Services:
- Anthropic API: $0.15
- GCP (Cloud Run): $0.03

TOTAL TODAY: $1.58
```

**If cost is unexpectedly high:**
- Check for failed builds (they still cost money)
- Verify execution mode (CLOUD is expensive)
- Review `/logs` for repeated operations
- Consider switching to LOCAL/HYBRID if possible

**Check 5: Queued Builds**

```
/queue
```

Shows builds waiting to be processed:
```
Build Queue: 0 active, 0 waiting

No builds in queue
```

Or:
```
Build Queue: 1 active, 2 waiting

ACTIVE:
- HabitFlow v1.2.0 (S4 - Build) - 8m 30s elapsed

WAITING:
- RecipeBox v1.0.0 (queued 2m ago)
- ExpenseTracker v1.1.0 (queued 5m ago)
```

**If queue is backed up:**
- This is normal if you queued multiple builds
- Pipeline processes one at a time
- Typical: 25-40 min per build
- Can cancel builds if needed: `/cancel [build-id]`

---

### 3.4 What to Do If Health Check Fails

**Problem: Status shows STOPPED**

```
Pipeline Status: ⚠️ STOPPED
```

**Solution:**
```
/start
```

Wait 60 seconds, check again:
```
/status
```

Should now show RUNNING.

**If still STOPPED after /start:**
- Check terminal/console for errors
- Manually restart from command line (see Section 3.2)
- Check troubleshooting section

---

**Problem: Service not connected**

```
Services:
✅ Anthropic API: Connected
❌ GitHub: Not connected
✅ Firebase: Connected
```

**Solution:**

Identify which service is disconnected, then:

**For Anthropic API:**
```
/config verify anthropic_api_key
```

If invalid:
1. Get new key from: https://console.anthropic.com
2. Update: `/config anthropic_api_key sk-ant-...`
3. Restart: `/restart`

**For GitHub:**
```
/config verify github_token
```

If invalid:
1. Create new token: https://github.com/settings/tokens
2. Update: `/config github_token ghp_...`
3. Restart: `/restart`

**For Firebase:**
- More complex, see NB2 (Service Integrations) for reconfiguration
- Or check `.env` file for Firebase credentials

**For GCP (CLOUD mode only):**
- Verify GCP credentials in `.env`
- Check GCP console for service issues
- See NB2 for GCP setup

---

**Problem: High error count in logs**

```
/logs recent
```

Shows many ERROR messages in last hour.

**Solution:**

Read the errors carefully. Common patterns:

**Rate limit errors:**
```
ERROR: Anthropic API rate limit exceeded
```
**Fix:** Wait 60 seconds, errors will stop. Consider reducing build frequency.

**Network errors:**
```
ERROR: Failed to connect to external service
```
**Fix:** Check your internet connection. If stable, service might be down temporarily.

**Permission errors:**
```
ERROR: GitHub permission denied
```
**Fix:** Token expired or lacks permissions. Generate new token with correct scopes.

**If errors are unclear or numerous:**
```
/diagnose
```

Pipeline runs automated diagnostics and suggests fixes.

---

### 3.5 Planning Your Day's Builds

**Before queueing builds, plan your work:**

**Question 1: What are you building today?**

Options:
- New app (use `/create`)
- Update to existing app (use `/modify`)
- Just evaluating ideas (use `/evaluate`)
- Multiple builds (queue them strategically)

**Question 2: What execution mode do you need?**

Decision tree:
```
Are you building iOS app?
├─ YES → Must use CLOUD mode
│   └─ Cost: $1.20 per build
└─ NO → Are you building Android or Web?
    └─ YES → Can use LOCAL (free) or HYBRID ($0.20)
        └─ Decision: Use LOCAL if your computer is powerful enough
```

**Question 3: How many builds will you queue?**

Considerations:
- Pipeline processes 1 build at a time
- Each build: 25-40 minutes
- 3 builds = 75-120 minutes total
- Queue morning builds before lunch for afternoon completion

**Question 4: Do you need results immediately?**

If YES:
- Queue one build at a time
- Monitor actively
- Don't start other intensive tasks on computer

If NO:
- Queue multiple builds
- Let them run in background
- Check back periodically

**Example daily plan:**

```
MORNING (9:00 AM):
- Health check: 5 min
- Queue Build 1 (new app): /create → 30 min
- Queue Build 2 (update app): /modify → 20 min
- Start work on something else while builds run

MIDDAY (11:00 AM):
- Check build results
- Test builds if successful
- Fix issues if failed

AFTERNOON (2:00 PM):
- Queue Build 3 (another update): /modify → 25 min
- Work on other tasks

EVENING (5:00 PM):
- Review day's builds
- Check costs
- Plan tomorrow's work
```

---

**✅ SECTION 1 COMPLETE**

You now know:
- ✅ How to start pipeline (24/7 or on-demand)
- ✅ Morning health check routine (5 min)
- ✅ What to verify before builds
- ✅ How to identify and fix common startup issues
- ✅ How to plan your daily build work

**Next (Section 2): Standard Workflows (Evaluate, Create, Modify, Status commands)**

---

**[END OF PART 1]**














---

# RB1: DAILY OPERATIONS & STANDARD WORKFLOWS
## PART 2 of 5

---

## 4. SECTION 2: STANDARD WORKFLOWS

### 4.1 Overview of Core Commands

The pipeline has four primary workflows you'll use daily:

**1. /evaluate** - Score app ideas before building (0-100 scale)
**2. /create** - Build new apps from specifications
**3. /modify** - Update existing apps with changes
**4. /status, /info, /logs** - Get information and monitor

Each workflow has specific syntax, timing, and best practices.

---

### 4.2 WORKFLOW: Evaluating App Ideas (/evaluate)

**When to use:**
- Before building any new app
- When choosing between multiple ideas
- When validating market demand
- Before investing time/money in build

**Time needed:** 2-3 minutes per evaluation

**Cost:** FREE (uses minimal AI tokens)

---

#### 4.2.1 Basic /evaluate Syntax

**Template:**
```
/evaluate

App Name: [Memorable name]
Platform: [iOS, Android, Web, or "All"]
Description: [2-3 sentences describing the app]
Target Users: [Who will use this - be specific]
Key Features: [3-5 main features]
Monetization: [How you'll make money]
```

**Example:**
```
/evaluate

App Name: StudyBuddy
Platform: iOS and Android
Description: A focused study timer app for students using the Pomodoro technique. Unlike generic timers, StudyBuddy tracks which subjects you study, shows productivity analytics, and syncs across devices. Perfect for high school and college students.
Target Users: High school and college students (ages 15-25) who struggle with focus and time management during studying.
Key Features:
- 25-minute Pomodoro timer with breaks
- Track study sessions by subject
- Weekly productivity reports
- Cross-device sync via cloud
- Distraction blocking suggestions
Monetization: Freemium - Free for 3 subjects, $1.99/month for unlimited subjects and advanced analytics
```

---

#### 4.2.2 What Happens During Evaluation

**Step-by-step process:**

**Step 1: Pipeline receives your specification (instant)**
```
✅ Evaluation request received

App: StudyBuddy
Analyzing...
```

**Step 2: Claude AI analyzes (60-120 seconds)**

Pipeline sends your specification to Claude AI, which evaluates:
- Market demand (search volume, competition, trends)
- Technical feasibility (can pipeline build this?)
- Monetization potential (will people pay?)
- Competitive landscape (how crowded is market?)
- Complexity (how hard to build?)

**Step 3: Results returned (instant)**

You receive detailed breakdown:

```
📊 IDEA EVALUATION RESULTS

App: StudyBuddy
Overall Score: 82/100 ⭐ EXCELLENT

BREAKDOWN:

✅ Market Demand: 88/100
Analysis:
- High search volume for "study timer" and "pomodoro app"
- Year-round relevance (students always need this)
- Search volume: 50k+ monthly searches globally
- Strong correlation with "productivity" and "focus" keywords
Evidence: Google Trends shows steady interest in study apps

✅ Technical Feasibility: 95/100
Analysis:
- All features within pipeline capabilities
- Standard React Native components
- Cloud sync requires Firebase (pipeline supports)
- No complex hardware integration
- Estimated build time: 25-30 minutes
Note: Distraction blocking may have OS limitations (research needed)

⚠️ Competitive Landscape: 68/100
Analysis:
- 100+ existing Pomodoro timer apps in stores
- Top apps: Forest (10M+ downloads), Focus To-Do (5M+)
- Market is crowded but not saturated
- Differentiation: Subject tracking + analytics is unique angle
Opportunity: Most existing apps are generic timers, yours is study-focused

✅ Monetization Potential: 85/100
Analysis:
- Freemium model proven in productivity category
- $1.99/month competitive pricing (vs $2.99-4.99 competitors)
- Clear free→paid upgrade path (3 subjects → unlimited)
- Students are price-sensitive but will pay for quality
Expected conversion: 5-8% (typical for student apps)

✅ Complexity: 88/100
Analysis:
- Simple feature set (focused, not bloated)
- Standard CRUD operations (Create, Read, Update, Delete)
- Cloud sync adds complexity but manageable
- No AI/ML, blockchain, or advanced features
Build time: 25-30 minutes (average)

RECOMMENDATION: ✅ BUILD THIS

Strengths:
- Clear target audience (students)
- Proven monetization model (freemium)
- Unique differentiation (subject tracking)
- Technical simplicity (fast to build)

Suggested Improvements:
1. Add study goal setting (increases engagement)
2. Consider group study rooms (social feature for v2.0)
3. Add study streaks (gamification element)
4. Integrate with calendar apps (homework/exam tracking)

Risks to Consider:
- Crowded market (need strong ASO strategy)
- Students expect free apps (conversion may be lower)
- Seasonal usage (drops in summer)

Estimated Costs:
- Build: $0 (LOCAL mode for Android) or $1.20 (CLOUD for iOS)
- Monthly operation: $0-5 (Firebase free tier sufficient)
- Revenue potential: $100-500/month (500 downloads, 5% conversion)

Next Steps:
1. Research top 5 competitors (App Annie, Sensor Tower)
2. Validate with 10-20 target users (student forums, r/StudyTips)
3. Build MVP with core features only (timer, subject tracking)
4. Launch on Android first (lower cost, faster iteration)
```

---

#### 4.2.3 Interpreting Scores

**Score Ranges:**

**90-100: EXCEPTIONAL**
- Rare, almost guaranteed success
- Build immediately
- Strong market demand + easy to build + clear monetization
- Example: Unique productivity tool with no competition

**80-89: EXCELLENT**
- Strong idea, high probability of success
- Build with confidence
- May have one minor weakness (competition, complexity, etc.)
- Example: StudyBuddy (82/100)

**70-79: GOOD**
- Solid idea, worth building with adjustments
- Address suggestions before building
- Usually fixable issues (pricing, features, positioning)
- Example: Generic habit tracker (would score ~75)

**60-69: NEEDS WORK**
- Viable but has significant problems
- Requires major changes before building
- Consider simplifying or pivoting
- Example: "Social network for cat owners" (too niche + complex)

**50-59: RISKY**
- Not recommended without major rework
- Multiple significant problems
- High failure probability
- Example: "Blockchain-based recipe app" (unnecessary complexity)

**Below 50: DON'T BUILD**
- Fundamental problems with idea
- Pick different idea from your list
- Learn from feedback, apply to next idea
- Example: "App that requires AR hardware most users don't have"

---

#### 4.2.4 Individual Component Scores

**Market Demand (weight: 25%)**

What it measures:
- Do people actually want this?
- How many people search for it?
- Is it a growing or declining trend?

**90-100:** Massive demand, proven market (e.g., "meditation app")
**70-89:** Strong demand, active searches (e.g., "study timer")
**50-69:** Moderate demand, niche market (e.g., "knitting pattern tracker")
**Below 50:** Very low demand, minimal searches (e.g., "left-handed scissors finder")

**Technical Feasibility (weight: 20%)**

What it measures:
- Can the pipeline actually build this?
- How complex is implementation?
- Any unsupported features?

**90-100:** Simple, standard features (e.g., "task list with reminders")
**70-89:** Mostly standard, minor complexity (e.g., "cloud sync across devices")
**50-69:** Some complex features (e.g., "real-time collaboration")
**Below 50:** Has unsupported features (e.g., "AR furniture preview")

**Competitive Landscape (weight: 20%)**

What it measures:
- How many similar apps exist?
- How dominant are top competitors?
- Can you differentiate?

**90-100:** Blue ocean, few competitors (rare)
**70-89:** Competitive but room for differentiation
**50-69:** Very crowded, hard to stand out
**Below 50:** Completely saturated, dominated by big players

Low score ≠ don't build. Even crowded markets work if you have unique angle.

**Monetization Potential (weight: 20%)**

What it measures:
- Will people pay for this?
- How much can you charge?
- What's conversion rate likely to be?

**90-100:** High-value B2B or proven paid model
**70-89:** Strong freemium or subscription model
**50-69:** Ads-only or low-price one-time purchase
**Below 50:** Hard to monetize (e.g., "free utility everyone expects")

**Complexity (weight: 15%)**

What it measures:
- How many features?
- How long to build?
- How hard to maintain?

**90-100:** Very simple (3-5 features, 20-25 min build)
**70-89:** Moderate (6-10 features, 30-40 min build)
**50-69:** Complex (10+ features, 45-60 min build)
**Below 50:** Very complex (15+ features, multiple integrations)

Higher complexity = longer build, more bugs, harder to iterate.

---

#### 4.2.5 Using Evaluation Results

**Scenario 1: High score (80+) → Build it**

Action plan:
1. Note the suggested improvements
2. Incorporate improvements into /create specification
3. Build immediately
4. Expected success probability: 70-90%

**Scenario 2: Good score (70-79) → Adjust then build**

Action plan:
1. Read "Suggested Improvements" section carefully
2. Implement at least 2-3 suggestions
3. Simplify if complexity is issue
4. Re-evaluate with improvements
5. If new score is 80+, build

**Scenario 3: Needs work (60-69) → Major changes needed**

Action plan:
1. Identify lowest-scoring component
2. Address that weakness specifically:
   - Low market demand? → Validate with real users first
   - Low feasibility? → Remove unsupported features
   - Low monetization? → Rethink pricing model
   - High complexity? → Cut features to core MVP
3. Re-evaluate after changes
4. Only build if score improves to 75+

**Scenario 4: Risky or poor (below 60) → Don't build**

Action plan:
1. Learn from feedback
2. Pick different idea from your list
3. Apply lessons to new idea
4. Don't waste time trying to fix fundamentally flawed idea

---

#### 4.2.6 Evaluating Multiple Ideas

**Best practice: Evaluate 5 ideas, build the winner**

**Process:**

**Day 1 Morning: Brainstorm (30 min)**
- Write down 5 app ideas you're considering
- Don't filter yet, just capture ideas

**Day 1 Afternoon: Evaluate all 5 (50 min)**
- Format each idea using /evaluate template
- Send all 5 evaluations (10 min each)
- Wait for results (2-3 min each)

**Day 1 Evening: Compare scores (15 min)**

Create simple comparison table:

| App Idea | Overall | Market | Feasibility | Competition | Monetization | Complexity |
|----------|---------|--------|-------------|-------------|--------------|------------|
| StudyBuddy | 82 | 88 | 95 | 68 | 85 | 88 |
| RecipeBox | 76 | 80 | 90 | 65 | 75 | 82 |
| ExpenseTracker | 71 | 85 | 92 | 58 | 68 | 85 |
| WaterReminder | 68 | 70 | 95 | 55 | 60 | 92 |
| SocialPets | 55 | 60 | 65 | 40 | 45 | 50 |

**Day 2: Build the winner (StudyBuddy - 82/100)**

Apply improvements suggested in evaluation:
- Add study goal setting ✅
- Add study streaks ✅
- Calendar integration (save for v2.0)

**Benefits of this approach:**
- Reduces risk (chose best of 5 instead of first idea)
- Faster than building all 5 to test market
- Costs $0 (evaluation is free)
- Learn from all 5 evaluations
- Can return to ideas #2-4 later

---

#### 4.2.7 Common Evaluation Mistakes

**Mistake 1: Vague descriptions**

❌ Bad:
```
/evaluate

App Name: MyApp
Platform: iOS
Description: It's a productivity app
Target Users: Everyone
Key Features: Various productivity features
Monetization: Will figure out later
```

This gives Claude AI nothing to work with. Score will be low (~40-50) because evaluation can't assess vague ideas.

✅ Good:
```
/evaluate

App Name: FocusBlocks
Platform: iOS
Description: Time-blocking calendar app that combines your tasks with your schedule. Unlike traditional calendars, FocusBlocks automatically allocates time blocks for your to-dos based on priority and deadlines.
Target Users: Busy professionals (ages 25-45) who struggle with time management and have 20+ tasks/week to juggle.
Key Features:
- Import calendar from Google/Apple Calendar
- Add tasks with deadlines and time estimates
- AI auto-schedules tasks into available calendar slots
- Reschedules automatically when meetings change
- Focus mode blocks distractions during time blocks
Monetization: Subscription $4.99/month (includes cloud sync + AI scheduling)
```

**Mistake 2: Too many features**

❌ Bad:
```
Key Features:
- Video calling
- Screen sharing
- File storage (5GB)
- Team chat
- Project management
- Time tracking
- Invoice generation
- Client portal
- Payment processing
- Analytics dashboard
- Mobile app
- Desktop app
- Web app
- API access
- Webhooks
```

This is not an app, it's a full platform. Complexity score will be ~20-30.

✅ Good: Start with 3-5 core features
```
Key Features:
- 25-minute focus timer (Pomodoro)
- Track time per project
- Simple time reports (weekly/monthly)
- Export to CSV
```

Build v1.0 with core features. Add more in v1.1, v1.2, etc.

**Mistake 3: Unrealistic monetization**

❌ Bad:
```
Monetization: $19.99/month subscription for a simple habit tracker
```

Users won't pay $20/month for a habit tracker when competitors are $2.99/month or free.

✅ Good: Research competitive pricing
```
Monetization: Freemium - Free for 3 habits, $2.99/month for unlimited (competitive with market leaders at $2.99-4.99/month)
```

**Mistake 4: Ignoring target audience**

❌ Bad:
```
Target Users: Everyone who wants to be productive
```

"Everyone" is not a target audience. Too broad to evaluate.

✅ Good:
```
Target Users: College students (ages 18-24) preparing for exams who struggle with procrastination and time management
```

Specific audience = better evaluation of market demand and monetization.

**Mistake 5: Not incorporating suggestions**

Pipeline evaluates your idea and suggests improvements:
```
Suggested Improvements:
1. Add dark mode (users expect this)
2. Add data export (builds trust)
3. Consider weekly email summaries (increases engagement)
```

❌ Bad: Ignore suggestions, build original idea as-is

✅ Good: Add at least 2-3 suggestions to your /create spec

Suggestions are based on successful apps in that category. Following them improves success rate.

---

### 4.3 WORKFLOW: Building New Apps (/create)

**When to use:**
- Building completely new app
- Evaluated idea scored 70+
- Ready to invest 30-60 minutes of time
- Have complete specification written

**Time needed:** 
- Specification writing: 15-30 minutes
- Build process: 25-40 minutes (automated)
- Your active time: ~5 minutes (send command, monitor notifications)

**Cost:**
- CLOUD mode (iOS): $1.20
- HYBRID mode: $0.20
- LOCAL mode: $0

---

#### 4.3.1 Basic /create Syntax

**Template:**
```
/create
platform: [android/ios/web/all]
stack: [react-native/flutter/swift/kotlin/nextjs]

[COMPLETE APP SPECIFICATION]
```

**Example:**
```
/create
platform: android
stack: react-native

APP SPECIFICATION

App Name: FocusFlow
Platform: Android
Description: A Pomodoro timer app designed specifically for students. FocusFlow tracks study sessions by subject, shows productivity analytics, and uses gentle notifications to maintain focus without being disruptive. The app emphasizes simplicity and beautiful design over feature bloat.

Target Users: High school and college students (ages 15-25) who want to improve study habits and track their productivity across different subjects.

Core Features:
1. Customizable Pomodoro timer (default 25 min work, 5 min break)
2. Track study sessions by subject/course
3. Visual calendar showing completed sessions
4. Weekly productivity statistics (total hours, by subject)
5. Gentle notification sounds (non-intrusive)
6. Dark mode support
7. Data export as CSV
8. Offline-first (works without internet)

User Interface:
- Design style: Minimalist and calming
- Primary color: Soft blue (#4A90E2)
- Secondary color: Warm orange (#FF9F43) for active timer
- Typography: Clean sans-serif (SF Pro/Roboto)
- Dark mode: Deep navy background (#1A1A2E), white text
- Emphasis on large, readable timer display

Navigation:
- Tab bar with 3 sections:
  * Timer (main screen)
  * Statistics (analytics dashboard)
  * Settings (preferences)

Data Storage:
- Local storage using AsyncStorage
- Store: Timer sessions (timestamp, subject, duration, completed)
- Store: User preferences (timer durations, notification settings, dark mode)
- No cloud sync in v1.0 (add in v1.1)

Notifications:
- Request permission on first launch
- Notify when work session complete (gentle chime)
- Notify when break complete (different chime)
- User can customize sounds in Settings
- Respect system Do Not Disturb mode

Monetization:
- Model: Freemium
- Free tier: Track 3 subjects, basic stats, ads
- Premium tier: $1.99/month or $14.99/year
  * Unlimited subjects
  * Advanced analytics (trends, insights)
  * No ads
  * CSV export
  * Cloud backup (future)

Technical Requirements:
- Minimum Android version: 8.0 (API 26)
- Portrait orientation only
- No special permissions except notifications
- SQLite database for session storage
- React Native version: Latest stable

Screens to Build:
1. Timer Screen (main)
   - Large circular timer display
   - Start/Pause/Reset buttons
   - Subject selector dropdown
   - Session count for today

2. Statistics Screen
   - Weekly bar chart (hours per day)
   - Pie chart (time by subject)
   - Totals (this week, this month, all time)
   - Best streak counter

3. Settings Screen
   - Timer duration settings (work/break)
   - Notification preferences
   - Dark mode toggle
   - Premium upgrade button
   - Data export button
   - About/Help section

4. Subject Management Screen
   - Add/edit/delete subjects
   - Assign colors to subjects
   - View total time per subject

5. Upgrade Paywall (for premium)
   - Show premium benefits
   - Pricing options (monthly/yearly)
   - Subscribe buttons
   - Restore purchase button

Additional Notes:
- Timer should continue in background
- Show notification with remaining time when app in background
- Pause timer automatically on phone call
- Simple onboarding (3 screens max) on first launch
- No login/account required for free tier
```

---

#### 4.3.2 Platform Selection

**platform: android**
- Builds Android APK file
- Can use LOCAL mode (free) or CLOUD/HYBRID
- Faster iteration (Google Play review is 1-3 hours)
- Lower barrier to entry ($25 one-time vs $99/year)
- **Best for:** First app, testing ideas, budget-conscious

**platform: ios**
- Builds iOS IPA file
- **Must use CLOUD mode** ($1.20 per build)
- Slower iteration (Apple review is 24-48 hours)
- Higher quality bar (stricter review)
- **Best for:** Targeting premium users, proven concepts

**platform: web**
- Builds Next.js website (deployed to Firebase)
- Can use LOCAL mode (free) or HYBRID
- No app store submission needed
- Instant deployment
- **Best for:** MVPs, web-first concepts, avoiding app store fees

**platform: all**
- Builds iOS + Android + Web simultaneously
- Same codebase for all platforms (React Native + Next.js)
- Takes longer (40-60 min vs 25-40 min)
- Higher initial cost (iOS requires CLOUD mode)
- **Best for:** Proven ideas ready for wide distribution

**Recommendation for first app:** Start with `platform: android` in LOCAL mode (free, fast iteration).

---

#### 4.3.3 Stack Selection

**stack: react-native** (Recommended for most apps)
- **Best for:** iOS and Android apps
- Largest community (easy to find help)
- Most pipeline experience (fewer bugs)
- Rich ecosystem of libraries
- **Choose this if:** Building mobile app for first time

**stack: flutter**
- **Best for:** iOS and Android apps
- Very fast performance
- Beautiful default UI components
- Growing community
- **Choose this if:** Want modern framework, prioritize performance

**stack: swift**
- **Best for:** iOS-only apps
- Native iOS, best performance
- Access to all iOS features immediately
- **Choose this if:** Building iOS-exclusive app, want native feel

**stack: kotlin**
- **Best for:** Android-only apps
- Native Android, best performance
- Modern language features
- **Choose this if:** Building Android-exclusive app, want native feel

**stack: nextjs**
- **Best for:** Web apps only
- React-based framework
- Server-side rendering (fast loading)
- SEO-friendly
- **Choose this if:** Building web app, not mobile

**Decision tree:**
```
Q: Mobile or Web?
├─ MOBILE → Q: iOS, Android, or both?
│  ├─ BOTH → react-native (easier) or flutter (newer)
│  ├─ iOS ONLY → swift (native) or react-native (portable)
│  └─ ANDROID ONLY → kotlin (native) or react-native (portable)
└─ WEB → nextjs (only option)

RECOMMENDATION: react-native for mobile, nextjs for web
```

---

#### 4.3.4 What Happens During Build (Stage by Stage)

Once you send `/create` command, pipeline begins 8-stage process:

**STAGE S0: PLANNING (2-3 minutes)**

What pipeline does:
- Claude AI reads your entire specification
- Creates technical architecture plan
- Decides file structure (which files to create)
- Plans code organization
- Identifies dependencies needed
- Estimates complexity

Telegram notification:
```
📋 S0 COMPLETE - Planning (2m 18s)

✅ Specification parsed
✅ Technical plan created
✅ Architecture: React Native (Android)
✅ Files planned: 43 files
✅ Dependencies: 22 packages
✅ Estimated build time: 28-35 minutes

Next: S1 (Design) starting now...
```

**What you do:** Nothing. Wait for next notification.

---

**STAGE S1: DESIGN (4-5 minutes)**

What pipeline does:
- Claude AI creates UI mockups (text descriptions)
- Defines screen layouts
- Plans component hierarchy
- Establishes design system (colors, fonts, spacing)
- Creates navigation flow
- Plans user interaction patterns

Telegram notification:
```
🎨 S1 COMPLETE - Design (4m 32s)

✅ Screens designed: 5 screens
   - Timer Screen (main)
   - Statistics Screen
   - Settings Screen
   - Subject Management
   - Upgrade Paywall

✅ Navigation defined: Bottom tab navigation

✅ Design system:
   - Primary color: #4A90E2 (soft blue)
   - Secondary color: #FF9F43 (warm orange)
   - Typography: Roboto
   - Dark mode: Supported

✅ Components planned: 18 reusable components

Next: S2 (Code Generation) starting now...
```

**What you do:** Nothing. Design is automated.

---

**STAGE S2: CODE GENERATION (9-12 minutes)**

What pipeline does:
- Claude AI writes ALL the code
- Creates all 43 files (JavaScript, JSON, config files)
- Implements all features you specified
- Adds error handling
- Writes comments and documentation
- Creates basic unit tests
- Configures build system

Telegram notification:
```
💻 S2 COMPLETE - Code Generation (10m 45s)

✅ Files created: 43 files
✅ Code written: 4,127 lines
✅ Features implemented:
   - Pomodoro timer with customization
   - Subject tracking (unlimited)
   - Visual calendar
   - Weekly statistics
   - Dark mode
   - Notifications
   - Data export
   - Freemium paywall

✅ Components: 18 React components
✅ Tests: 31 unit tests written
✅ Documentation: README, inline comments

Next: S3 (Testing) starting now...
```

**What you do:** Nothing. All code is generated automatically.

---

**STAGE S3: TESTING (3-4 minutes)**

What pipeline does:
- Runs all 31 unit tests
- Checks for syntax errors
- Validates code quality (linting)
- Checks for security issues
- Validates dependencies
- Ensures all features are implemented

Telegram notification:
```
🧪 S3 COMPLETE - Testing (3m 21s)

✅ Unit tests: 31/31 passed (100%)
✅ Code quality: A (92/100)
✅ Security scan: No issues found
✅ Dependencies: All valid

⚠️ Warnings (non-blocking):
   - 2 unused variables (cleaned up)
   - 1 console.log in debug mode (expected)

✅ Build ready to proceed

Next: S4 (Build) starting now...
```

**What you do:** Review warnings (usually safe to ignore). If test failures, build stops here.

---

**STAGE S4: BUILD (8-15 minutes) ⏰ LONGEST STAGE**

What pipeline does:
- Compiles JavaScript into native code
- Creates Android APK file (or iOS IPA)
- Signs the app with digital certificate
- Optimizes images and assets
- Minifies code for smaller size
- Generates source maps (for debugging)

This stage takes longest because actual compilation happens here.

Telegram notification:
```
🏗️ S4 COMPLETE - Build (11m 52s)

✅ Platform: Android
✅ APK created: focusflow-v1.0.0.apk
✅ App size: 22.8 MB
✅ Signing: Successful (debug certificate)
✅ Optimization: Complete

Build artifacts:
📦 APK: /builds/focusflow-v1.0.0.apk
📊 Source maps: /builds/focusflow-sourcemaps.zip
📄 Build logs: /builds/focusflow-build.log

Next: S5 (Quality Check) starting now...
```

**What you do:** Nothing. This is the "heavy lifting" stage. Be patient.

**If stuck here >20 minutes:** See troubleshooting section.

---

**STAGE S5: QUALITY CHECK (2-3 minutes)**

What pipeline does:
- Scans APK/IPA for security vulnerabilities
- Validates app structure
- Checks for malware/suspicious code
- Verifies code signing
- Validates Android/iOS requirements
- Scans for privacy violations

Telegram notification:
```
🔍 S5 COMPLETE - Quality Check (2m 38s)

✅ Security scan: PASSED
✅ Vulnerability check: No issues found
✅ App structure: Valid
✅ Code signing: Verified
✅ Privacy compliance: OK

✅ Ready for deployment

Next: S6 (Deployment) starting now...
```

**What you do:** Nothing. Quality check is automated.

---

**STAGE S6: DEPLOYMENT (2-3 minutes)**

What pipeline does:
- Creates GitHub repository
- Pushes all source code to GitHub
- Creates initial commit
- Uploads APK to Firebase App Distribution (for testing)
- Generates README.md with documentation
- Creates CHANGELOG.md
- Sets up GitHub releases

Telegram notification:
```
🚀 S6 COMPLETE - Deployment (2m 47s)

✅ GitHub repository created:
   https://github.com/yourusername/focusflow

✅ Source code pushed:
   - 43 files committed
   - Initial release tagged: v1.0.0

✅ APK uploaded to Firebase App Distribution:
   Install link: https://appdistribution.firebase.dev/i/abc123xyz
   Valid for: 180 days

✅ Documentation generated:
   - README.md (setup instructions)
   - CHANGELOG.md (version history)
   - CONTRIBUTING.md (development guide)

Next: S7 (Monitoring Setup) starting now...
```

**What you do:** Save the Firebase App Distribution link (for testing your app).

---

**STAGE S7: MONITORING SETUP (1-2 minutes)**

What pipeline does:
- Configures Sentry (error tracking)
- Sets up Firebase Analytics
- Creates monitoring dashboard
- Configures crash reporting
- Sets up performance monitoring
- Final validation

Telegram notification:
```
📊 S7 COMPLETE - Monitoring Setup (1m 29s)

✅ Error tracking: Sentry configured
   Dashboard: https://sentry.io/yourorg/focusflow

✅ Analytics: Firebase Analytics enabled
   Dashboard: Firebase Console > Analytics

✅ Crash reporting: Active
✅ Performance monitoring: Active

═══════════════════════════════════════════════════════
✅ BUILD COMPLETE - FocusFlow v1.0.0
═══════════════════════════════════════════════════════

Build Summary:
Total time: 36m 42s
Total cost: $0.00 (LOCAL mode)
Platform: Android
Stack: React Native
App size: 22.8 MB

📱 INSTALL YOUR APP:
Option 1 (Recommended): Firebase App Distribution
https://appdistribution.firebase.dev/i/abc123xyz

Option 2: Direct APK Download
https://github.com/yourusername/focusflow/releases/tag/v1.0.0

📂 SOURCE CODE:
https://github.com/yourusername/focusflow

📊 MONITORING:
Sentry: https://sentry.io/yourorg/focusflow
Firebase: https://console.firebase.google.com

📋 DOCUMENTATION:
README: https://github.com/yourusername/focusflow/blob/main/README.md
CHANGELOG: https://github.com/yourusername/focusflow/blob/main/CHANGELOG.md

Next Steps:
1. Install app using Firebase link above
2. Test all features thoroughly
3. Report any bugs with /modify command
4. Submit to Google Play when ready (see RB4 for guide)

═══════════════════════════════════════════════════════
```

**What you do:** 
1. ✅ Save all URLs (GitHub, Firebase, Sentry)
2. ✅ Install app and test (see NB5 for testing guide)
3. ✅ Celebrate! You built an app in 37 minutes! 🎉

---

**[END OF PART 2]**














---

# RB1: DAILY OPERATIONS & STANDARD WORKFLOWS
## PART 3 of 5

---

### 4.4 WORKFLOW: Updating Existing Apps (/modify)

**When to use:**
- Fixing bugs in deployed app
- Adding new features to existing app
- Changing UI/colors/text
- Updating dependencies
- Any change to app you've already built

**Time needed:**
- Specification writing: 5-15 minutes
- Build process: 15-30 minutes (faster than /create)
- Your active time: ~3 minutes

**Cost:**
- Same as /create (CLOUD $1.20, HYBRID $0.20, LOCAL $0)

---

#### 4.4.1 Basic /modify Syntax

**Template:**
```
/modify [github-repository-url]

[DESCRIPTION OF CHANGES]
```

**Example:**
```
/modify https://github.com/yourusername/focusflow

Fix critical bug and add dark mode improvements:

BUG FIXES:
1. Fix crash when user sets timer for exactly 60 minutes
   - Current behavior: App crashes when timer reaches 60:00
   - Expected behavior: Timer should work for any duration 1-120 minutes
   - Add validation and error handling

2. Fix notification sound not playing on some devices
   - Issue: Samsung devices not playing notification sound
   - Root cause: Audio file format incompatibility
   - Solution: Use multiple audio formats with fallback

IMPROVEMENTS:
3. Improve dark mode contrast
   - Current: Some text hard to read in dark mode
   - Change: Increase contrast ratio to meet WCAG AA standards
   - Update: Timer text, button labels, stats screen text

4. Add haptic feedback when timer starts/stops
   - Provide tactile confirmation when user taps start/stop
   - Use light haptic pulse (not vibration)
   - Respect system haptic settings

Version: 1.0.0 → 1.0.1 (bug fixes = patch version bump)
```

---

#### 4.4.2 How /modify Differs from /create

**Key differences:**

**1. Faster execution (15-30 min vs 25-40 min)**
- Pipeline doesn't rebuild everything from scratch
- Only modifies affected files
- Reuses existing architecture

**2. Incremental changes**
- You describe WHAT to change, not entire app
- Pipeline preserves everything you don't mention
- More targeted, less comprehensive

**3. Version management**
- Pipeline auto-increments version number
- Follows semantic versioning (MAJOR.MINOR.PATCH)
- Maintains CHANGELOG.md automatically

**4. Conflict handling**
- If you manually edited code AND pipeline modifies same file, pipeline handles merge
- Auto-merge in 90%+ cases
- Manual intervention needed <10% of time

**5. Testing focus**
- Only tests affected functionality
- Regression tests ensure nothing else broke
- Faster test cycle

---

#### 4.4.3 Types of Modifications

**Type 1: Bug Fixes (PATCH version bump 1.0.0 → 1.0.1)**

Examples:
```
/modify https://github.com/yourusername/focusflow

Fix timer display bug:
- Timer shows "NaN:NaN" when app returns from background
- Should show correct remaining time
- Add proper state restoration when app resumes
```

```
/modify https://github.com/yourusername/focusflow

Fix data loss issue:
- User's study sessions disappear after app update
- Caused by database migration error
- Add proper migration script to preserve existing data
```

**Type 2: New Features (MINOR version bump 1.0.0 → 1.1.0)**

Examples:
```
/modify https://github.com/yourusername/focusflow

Add widget support for iOS:

FEATURE: Home Screen Widget
- Small widget (2x2): Current timer countdown
- Medium widget (4x2): Today's completed sessions
- Large widget (4x4): Weekly statistics chart
- Widget updates every 1 minute during active timer
- Tapping widget opens app to timer screen
- Use WidgetKit (iOS 14+)

Version: 1.0.0 → 1.1.0
```

```
/modify https://github.com/yourusername/focusflow

Add study goals feature:

NEW FEATURE: Weekly Study Goals
- User can set weekly goal (e.g., "Study 10 hours this week")
- Progress bar shows completion percentage
- Motivational message when goal reached
- Goal persists week-to-week
- Displayed on Statistics screen

Version: 1.0.0 → 1.1.0
```

**Type 3: UI/UX Improvements (MINOR or PATCH)**

Examples:
```
/modify https://github.com/yourusername/focusflow

UI improvements based on user feedback:

CHANGES:
- Make timer display 50% larger (more prominent)
- Change primary color from #4A90E2 to #2196F3 (brighter blue)
- Add subtle animation when timer starts (pulsing circle)
- Improve button spacing on timer screen (8px → 16px)
- Update app icon to new design (attach new icon file)

Version: 1.0.1 → 1.0.2 (cosmetic = patch)
```

**Type 4: Performance Optimizations (PATCH)**

Examples:
```
/modify https://github.com/yourusername/focusflow

Performance improvements:

OPTIMIZATIONS:
- Reduce app launch time from 3s to <1s
  * Lazy-load statistics screen components
  * Cache subject list in memory
  * Defer non-critical initializations

- Reduce memory usage
  * Clear unused timers from memory
  * Optimize image assets (compress)
  * Remove unnecessary re-renders

Version: 1.0.5 → 1.0.6
```

**Type 5: Dependency Updates (PATCH)**

Examples:
```
/modify https://github.com/yourusername/focusflow

Update dependencies for security:

UPDATES:
- React Native: 0.72.0 → 0.73.0 (latest stable)
- React Navigation: 6.0.0 → 6.1.0 (bug fixes)
- AsyncStorage: Update to latest (security patch)

Ensure all features still work after updates.
Run full test suite.

Version: 1.0.8 → 1.0.9
```

**Type 6: Content Changes (PATCH)**

Examples:
```
/modify https://github.com/yourusername/focusflow

Update in-app text and copy:

CHANGES:
- Onboarding screen 1: Change "Welcome to FocusFlow" to "Study Smarter, Not Harder"
- Settings screen: Fix typo "Notifcations" → "Notifications"
- Stats screen: Change "Sessions Completed" to "Study Sessions"
- Paywall: Update premium description to emphasize new features

No functionality changes, text only.

Version: 1.1.2 → 1.1.3
```

---

#### 4.4.4 Level of Detail to Provide

**TOO VAGUE (pipeline will ask for clarification):**

```
/modify https://github.com/yourusername/focusflow

Make the app better
Add some new features
Fix the bugs
```

Pipeline response:
```
❌ Modification request too vague

Please specify:
1. Which bugs need fixing? (exact reproduction steps)
2. Which features to add? (detailed description)
3. What should be "better"? (specific improvements)

Resubmit with clear, specific changes.
```

---

**TOO DETAILED (pipeline doesn't need this much):**

```
/modify https://github.com/yourusername/focusflow

Fix timer bug:

In file src/components/Timer.jsx, line 47, change:
const [timeRemaining, setTimeRemaining] = useState(duration * 60);

to:
const [timeRemaining, setTimeRemaining] = useState(() => {
  const stored = AsyncStorage.getItem('timer_remaining');
  return stored ? parseInt(stored) : duration * 60;
});

And in line 89, add:
AsyncStorage.setItem('timer_remaining', timeRemaining.toString());

And update useEffect on line 102 to...
```

This is TOO specific - you're writing the code yourself. Pipeline needs problem description, not implementation.

---

**JUST RIGHT (clear problem, let pipeline solve it):**

```
/modify https://github.com/yourusername/focusflow

Fix timer persistence bug:

PROBLEM:
When user starts 25-minute timer, minimizes app, and returns 10 minutes later, timer shows "25:00" instead of "15:00" (remaining time).

EXPECTED BEHAVIOR:
Timer should remember state when app goes to background and restore correct remaining time when app returns to foreground.

SOLUTION NEEDED:
- Save timer state to persistent storage when app backgrounds
- Restore timer state when app foregrounds
- Calculate elapsed time while app was backgrounded
- Update display with correct remaining time

Test on both Android and iOS.
```

This gives pipeline:
- ✅ Clear problem description
- ✅ Expected behavior
- ✅ Solution approach (but not code)
- ✅ Testing requirements

Pipeline will implement the actual code.

---

#### 4.4.5 What Happens During /modify (Stages)

**MODIFIED STAGE FLOW (faster than /create):**

**S0: Analysis (1-2 min)** - Pipeline reads current code + your changes
**S1: Planning (2-3 min)** - Plans which files to modify
**S2: Code Modification (5-10 min)** - Applies changes to code
**S3: Testing (2-3 min)** - Tests affected functionality
**S4: Build (6-12 min)** - Recompiles app
**S5: Quality Check (1-2 min)** - Security scan
**S6: Deployment (2-3 min)** - Updates GitHub, creates new release
**S7: Monitoring (1 min)** - Updates monitoring config

**Total: 15-30 minutes** (vs 25-40 for /create)

**Example notification flow:**

```
📝 S0 COMPLETE - Analysis (1m 42s)

✅ Repository analyzed: focusflow
✅ Current version: 1.0.0
✅ Changes requested: 2 bug fixes, 2 improvements
✅ Files affected: 4 files
✅ Impact: Low (isolated changes)

Next: S1 (Planning)...
```

```
📋 S1 COMPLETE - Planning (2m 15s)

✅ Modification plan created
Files to modify:
- src/components/Timer.jsx (timer persistence fix)
- src/utils/notifications.js (sound fix)
- src/styles/darkMode.js (contrast improvements)
- src/components/Button.jsx (haptic feedback)

✅ Version increment: 1.0.0 → 1.0.1 (patch)
✅ Estimated time: 18-24 minutes

Next: S2 (Code Modification)...
```

```
💻 S2 COMPLETE - Code Modification (8m 32s)

✅ Changes applied to 4 files
✅ Lines changed: 127 lines modified, 43 added, 18 removed

Changes:
✅ Timer.jsx: Added background state persistence
✅ notifications.js: Multiple audio format support
✅ darkMode.js: Improved contrast ratios (WCAG AA compliant)
✅ Button.jsx: Haptic feedback on press

✅ Tests updated: 6 new tests added
✅ CHANGELOG updated

Next: S3 (Testing)...
```

```
🧪 S3 COMPLETE - Testing (2m 18s)

✅ Unit tests: 37/37 passed (100%)
   - 31 existing tests: PASSED
   - 6 new tests: PASSED

✅ Regression tests: PASSED
   - No existing functionality broken
   - All features still work

✅ Manual test checklist generated:
   □ Test timer with 60-minute duration
   □ Test background/foreground transition
   □ Test notification sound on Samsung device
   □ Verify dark mode text readability
   □ Test haptic feedback

Next: S4 (Build)...
```

```
🏗️ S4 COMPLETE - Build (9m 47s)

✅ APK rebuilt: focusflow-v1.0.1.apk
✅ App size: 22.9 MB (0.1 MB increase, expected)
✅ Build successful

Next: S5 (Quality Check)...
```

```
🔍 S5 COMPLETE - Quality Check (1m 28s)

✅ Security scan: PASSED
✅ No new vulnerabilities introduced
✅ Code quality: A (92/100, maintained)

Next: S6 (Deployment)...
```

```
🚀 S6 COMPLETE - Deployment (2m 31s)

✅ Changes committed to GitHub
   Commit: "v1.0.1 - Bug fixes and dark mode improvements"
   Files changed: 4

✅ New release created: v1.0.1
   Download: https://github.com/yourusername/focusflow/releases/tag/v1.0.1

✅ APK uploaded to Firebase App Distribution
   Install link: https://appdistribution.firebase.dev/i/xyz789abc

✅ CHANGELOG updated:
   ## [1.0.1] - 2026-03-03
   ### Fixed
   - Timer crash at 60 minutes
   - Notification sound on Samsung devices
   ### Improved
   - Dark mode text contrast (WCAG AA)
   - Added haptic feedback

Next: S7 (Monitoring)...
```

```
📊 S7 COMPLETE - Monitoring Setup (0m 58s)

✅ Monitoring updated for v1.0.1

═══════════════════════════════════════════════════════
✅ MODIFICATION COMPLETE - FocusFlow v1.0.1
═══════════════════════════════════════════════════════

Build Summary:
Total time: 28m 31s
Total cost: $0.00 (LOCAL mode)
Version: 1.0.0 → 1.0.1

Changes Applied:
✅ Fixed timer 60-minute crash
✅ Fixed notification sound compatibility
✅ Improved dark mode contrast
✅ Added haptic feedback

📱 INSTALL UPDATED APP:
https://appdistribution.firebase.dev/i/xyz789abc

📂 RELEASE NOTES:
https://github.com/yourusername/focusflow/releases/tag/v1.0.1

📋 MANUAL TESTING CHECKLIST:
1. Set timer for 60 minutes, verify no crash
2. Test background→foreground transition
3. Test notifications on Samsung device (if available)
4. Check dark mode text readability
5. Feel haptic feedback when tapping start/stop

Next Steps:
1. Install v1.0.1 and run manual tests
2. If tests pass: Submit to Google Play as update
3. If issues found: Report with /modify for hotfix

═══════════════════════════════════════════════════════
```

---

#### 4.4.6 Handling Merge Conflicts

**What is a merge conflict?**

A conflict happens when:
1. You manually edited file X in GitHub
2. Pipeline also needs to modify file X
3. Both changed the same lines

**Example scenario:**

You manually changed this in `Timer.jsx`:
```javascript
const DEFAULT_DURATION = 25; // You changed from 20 to 25
```

Pipeline wants to change same line:
```javascript
const DEFAULT_DURATION = 30; // Pipeline changing to 30 per your /modify request
```

**How pipeline handles conflicts:**

**90% of time: AUTO-MERGE**

Pipeline intelligently merges:
```
Your version: 25
Pipeline version: 30
Conflict resolution: Uses pipeline version (30) because that's what you requested in /modify
```

Notification:
```
✅ S2: Conflicts auto-resolved
- 1 merge conflict in Timer.jsx
- Resolution: Used requested value (30) over existing value (25)
```

**10% of time: MANUAL INTERVENTION**

If pipeline can't auto-resolve:

```
⚠️ S2: Manual merge required

Conflict in Timer.jsx, line 15:

<<<<<<< CURRENT (your manual edit)
const DEFAULT_DURATION = 25;
const BREAK_DURATION = 5;
=======
const DEFAULT_DURATION = 30;
const BREAK_DURATION = 10;
>>>>>>> PROPOSED (pipeline modification)

Actions:
1. Accept PROPOSED (pipeline version)
2. Accept CURRENT (your version)
3. Manually merge both

Reply with: /resolve [build-id] [action]
```

**How to resolve:**

**Option 1: Accept pipeline version (most common)**
```
/resolve abc123 accept-proposed
```

Use this if: Your /modify request is what you want, discard manual edits.

**Option 2: Accept your version**
```
/resolve abc123 accept-current
```

Use this if: Your manual edit is important, discard pipeline changes.

**Option 3: Manual merge**
```
/resolve abc123 manual-merge

Keep both values:
const DEFAULT_DURATION = 30; // From pipeline (your request)
const BREAK_DURATION = 5; // From your manual edit
```

---

**Best practice to avoid conflicts:**

1. **Don't manually edit code if you plan to use /modify**
   - Either manually edit OR use /modify, not both
   - If you must manually edit, document changes

2. **If you manually edited, mention in /modify request:**
   ```
   /modify https://github.com/yourusername/focusflow
   
   Add new feature X
   
   NOTE: I manually changed DEFAULT_DURATION to 25 in Timer.jsx - please preserve this value.
   ```

3. **Use /modify for all changes when possible**
   - More reliable than manual editing
   - Automatically tested
   - Version controlled properly

---

#### 4.4.7 Version Number Management

**Pipeline auto-increments versions following Semantic Versioning:**

**Format: MAJOR.MINOR.PATCH**

**PATCH (1.0.0 → 1.0.1)**
Auto-applied when:
- Bug fixes only
- Performance improvements
- Dependency updates
- Content/text changes
- No new features, no breaking changes

**MINOR (1.0.0 → 1.1.0)**
Auto-applied when:
- New features added
- New screens/functionality
- Enhancements to existing features
- Backward compatible

**MAJOR (1.0.0 → 2.0.0)**
Requires explicit instruction:
- Breaking changes
- Complete redesign
- Changed data format (old versions can't read)
- Removed features

**Overriding auto-increment:**

If pipeline chooses wrong version:
```
/modify https://github.com/yourusername/focusflow

[your changes]

Force version: 2.0.0
Reason: This is major redesign, not minor update
```

**Checking current version:**
```
/info focusflow
```

Returns:
```
App Information: FocusFlow

Current version: 1.0.1
Platform: Android
Stack: React Native
Last updated: 2026-03-03 14:22:00
Repository: https://github.com/yourusername/focusflow
```

---

### 4.5 WORKFLOW: Information & Status Commands

**Quick reference commands for daily use:**

---

#### 4.5.1 /status - Pipeline Health

**Usage:**
```
/status
```

**Returns:**
```
Pipeline Status: ✅ RUNNING
Mode: LOCAL
Version: 5.8.0
Uptime: 3 days, 14 hours

Services:
✅ Anthropic API: Connected (95 requests today)
✅ GitHub: Connected (last push: 2 hours ago)
✅ Firebase: Connected (3 deployments today)

Current Activity:
📱 Active build: FocusFlow v1.1.0 (S4 - Build, 8m elapsed)
⏳ Queued: 1 build waiting

System Resources:
CPU: 45% (normal during build)
Memory: 3.2GB / 8GB (40%)
Disk: 124GB free

Last 24 hours:
✅ Builds completed: 3
❌ Builds failed: 0
💰 Cost: $0.00 (LOCAL mode)
```

**When to use:**
- Morning health check
- Before queueing new builds
- When build seems slow
- Troubleshooting issues

---

#### 4.5.2 /info - App Information

**Usage:**
```
/info [app-name]
```

**Example:**
```
/info focusflow
```

**Returns:**
```
App Information: FocusFlow

Basic Details:
Name: FocusFlow
Platform: Android
Stack: React Native
Version: 1.0.1 (latest)

Repository:
GitHub: https://github.com/yourusername/focusflow
Last commit: 2 hours ago
Branches: main, dev

Deployment:
Firebase: https://appdistribution.firebase.dev/i/xyz789
Last deployed: 2026-03-03 14:22:00
Environment: Production

Metadata:
Created: 2026-03-01 09:15:00
Total builds: 4
Bundle ID: com.yourusername.focusflow
App ID: 1234567890

Build History:
v1.0.1 - 2 hours ago (Bug fixes)
v1.0.0 - 2 days ago (Initial release)

Monitoring:
Sentry: https://sentry.io/yourorg/focusflow
Firebase Analytics: Active
Crash-free rate: 99.2% (last 7 days)
```

**When to use:**
- Getting app URLs quickly
- Checking current version
- Finding repository/deployment links
- Reviewing build history

---

#### 4.5.3 /logs - View Recent Logs

**Usage:**
```
/logs
/logs recent
/logs [app-name]
/logs error
```

**Example:**
```
/logs recent
```

**Returns:**
```
Recent Logs (last 50 entries):

[2026-03-03 14:22:15] INFO: Build completed - FocusFlow v1.0.1
[2026-03-03 14:21:30] INFO: S7 complete - Monitoring setup
[2026-03-03 14:19:02] INFO: S6 complete - Deployment
[2026-03-03 14:16:31] INFO: S5 complete - Quality check
[2026-03-03 14:14:44] INFO: S4 complete - Build
[2026-03-03 14:05:12] INFO: S3 complete - Testing
[2026-03-03 14:02:38] INFO: S2 complete - Code modification
[2026-03-03 14:00:23] INFO: S1 complete - Planning
[2026-03-03 13:58:41] INFO: S0 complete - Analysis
[2026-03-03 13:56:50] INFO: Build started - FocusFlow v1.0.1

[2026-03-03 13:45:00] INFO: Health check passed
[2026-03-03 13:30:00] INFO: Cost tracking updated - $0.00 today

[Show more? Reply: /logs more]
```

**Error logs only:**
```
/logs error
```

Returns:
```
Error Logs (last 24 hours):

[2026-03-03 10:15:22] ERROR: GitHub API rate limit exceeded
Details: 5000 requests/hour limit reached
Resolution: Waiting 15 minutes for reset
Status: Resolved (auto-retry successful)

[2026-03-02 16:30:45] ERROR: Firebase deployment failed
Details: Network timeout during upload
Resolution: Retried, succeeded on attempt 2
Status: Resolved

No unresolved errors in last 24 hours ✅
```

**When to use:**
- Troubleshooting failed builds
- Checking for recent errors
- Auditing system activity
- Understanding what happened during build

---

#### 4.5.4 /queue - View Build Queue

**Usage:**
```
/queue
```

**Returns:**
```
Build Queue Status

ACTIVE (1):
🔄 FocusFlow v1.1.0
   Stage: S4 (Build)
   Elapsed: 8m 32s
   Estimated remaining: 3-7 minutes

WAITING (2):
⏳ StudyBuddy v1.0.0
   Type: CREATE
   Queued: 5m ago
   Position: #1
   Estimated start: 3-7 minutes

⏳ RecipeBox v1.2.0
   Type: MODIFY
   Queued: 2m ago
   Position: #2
   Estimated start: 20-35 minutes

Total estimated time: 45-65 minutes for all builds
```

**When to use:**
- Checking build progress
- Planning when to queue next build
- Estimating completion time
- Deciding whether to cancel queued build

---

#### 4.5.5 /cost - Track Spending

**Usage:**
```
/cost
/cost today
/cost week
/cost month
/cost [app-name]
```

**Example:**
```
/cost today
```

**Returns:**
```
Cost Summary - Today (March 3, 2026)

Builds:
FocusFlow v1.0.1 (MODIFY, LOCAL): $0.00
StudyBuddy v1.0.0 (CREATE, LOCAL): $0.00

External Services:
Anthropic API (142 requests): $0.21
GCP Cloud Run: $0.00 (free tier)
Firebase: $0.00 (free tier)

TOTAL TODAY: $0.21

Month to date (March 1-3): $0.87
This month budget: $30.00
Remaining: $29.13 (97%)
```

**By app:**
```
/cost focusflow
```

Returns:
```
Cost Breakdown - FocusFlow

Total lifetime cost: $1.43

By version:
v1.0.0 (initial build, CLOUD): $1.20
v1.0.1 (bug fix, LOCAL): $0.00

API costs: $0.23
- Anthropic (build): $0.18
- Anthropic (monitoring): $0.05

Infrastructure: $0.00 (within free tiers)

Revenue: $0.00 (no monetization active yet)
Profit: -$1.43 (pre-revenue)
```

**When to use:**
- Daily cost monitoring
- Monthly budget tracking
- Deciding execution mode
- ROI calculations

---

**[END OF PART 3]**














---

# RB1: DAILY OPERATIONS & STANDARD WORKFLOWS
## PART 4 of 5

---

## 5. SECTION 3: INTERPRETING TELEGRAM NOTIFICATIONS

### 5.1 Overview of Notification Types

Pipeline sends three categories of notifications:

**1. Stage Completion Notifications** (S0-S7)
- Sent when each build stage completes
- Shows what was accomplished
- Indicates next stage starting
- Most common notifications you'll see

**2. Status Change Notifications**
- Pipeline started/stopped
- Mode changed
- Service connected/disconnected
- Configuration updated

**3. Error/Warning Notifications**
- Build failures
- Service issues
- Resource warnings
- Action required alerts

---

### 5.2 Stage-by-Stage Notification Guide

**For each stage, you'll learn:**
- What the notification means in plain English
- Normal timing ranges
- What to do (usually: nothing, wait)
- When to worry

---

#### 5.2.1 S0: Planning Stage

**Example notification:**
```
📋 S0 COMPLETE - Planning (2m 18s)

✅ Specification parsed
✅ Technical plan created
✅ Architecture: React Native (Android)
✅ Files planned: 43 files
✅ Dependencies: 22 packages
✅ Estimated build time: 28-35 minutes

Next: S1 (Design) starting now...
```

**What this means in plain English:**
Claude AI finished reading your app specification and created a detailed technical plan. It knows what files to create, what libraries to use, and how to structure the code.

**Normal timing:** 1.5-3.5 minutes
- Simple apps (5 features): 1.5-2 minutes
- Medium apps (10 features): 2-3 minutes
- Complex apps (15+ features): 2.5-3.5 minutes

**What you do:** Nothing. Wait for S1 notification.

**When to worry:**
- ⚠️ If >5 minutes: Pipeline might be stuck or slow
- ⚠️ If error about "unsupported feature": Your spec has feature pipeline can't build

**Red flags in this notification:**
```
⚠️ Warning: Feature "blockchain wallet" not fully supported
⚠️ Warning: 200+ files planned (very complex, may be slow)
❌ Error: Platform "iOS" requires CLOUD mode, currently in LOCAL
```

If you see warnings/errors:
- Read carefully
- Decide whether to continue or cancel (`/cancel`)
- Adjust specification and retry if needed

---

#### 5.2.2 S1: Design Stage

**Example notification:**
```
🎨 S1 COMPLETE - Design (4m 32s)

✅ Screens designed: 5 screens
   - Timer Screen (main)
   - Statistics Screen
   - Settings Screen
   - Subject Management
   - Upgrade Paywall

✅ Navigation defined: Bottom tab navigation

✅ Design system:
   - Primary color: #4A90E2 (soft blue)
   - Secondary color: #FF9F43 (warm orange)
   - Typography: Roboto
   - Dark mode: Supported

✅ Components planned: 18 reusable components

Next: S2 (Code Generation) starting now...
```

**What this means:**
Claude AI created the visual design for your app - screen layouts, navigation flow, colors, fonts. It decided how everything will look before writing any code.

**Normal timing:** 3-6 minutes
- Simple UI (3-4 screens): 3-4 minutes
- Medium UI (5-8 screens): 4-5 minutes
- Complex UI (10+ screens): 5-6 minutes

**What you do:** Nothing. Design is automated.

**What to look for:**
- ✅ Screen count matches your specification
- ✅ Design system includes colors you requested
- ✅ Navigation type makes sense (tabs, stack, drawer)

**When to worry:**
- ⚠️ If >8 minutes: Unusually slow, but not necessarily stuck
- ⚠️ Screen count is way off (you requested 5, shows 15): Over-complicating

**If design doesn't match your vision:**
- Let it finish building
- Test the app
- Use `/modify` to adjust design later
- Don't cancel mid-build unless truly wrong

---

#### 5.2.3 S2: Code Generation Stage

**Example notification:**
```
💻 S2 COMPLETE - Code Generation (10m 45s)

✅ Files created: 43 files
✅ Code written: 4,127 lines
✅ Features implemented:
   - Pomodoro timer with customization
   - Subject tracking (unlimited)
   - Visual calendar
   - Weekly statistics
   - Dark mode
   - Notifications
   - Data export
   - Freemium paywall

✅ Components: 18 React components
✅ Tests: 31 unit tests written
✅ Documentation: README, inline comments

Next: S3 (Testing) starting now...
```

**What this means:**
Claude AI wrote ALL the code for your app. Every file, every function, every component. 4,000+ lines of working code in ~10 minutes.

**Normal timing:** 7-15 minutes
- Simple apps (<2,000 lines): 7-9 minutes
- Medium apps (2,000-5,000 lines): 9-12 minutes
- Complex apps (5,000+ lines): 12-15 minutes

**What you do:** Nothing. Code generation is fully automated.

**What to look for:**
- ✅ All features you requested are listed as "implemented"
- ✅ Line count seems reasonable (more features = more code)
- ✅ Tests were created (shows quality control)

**When to worry:**
- ⚠️ If >20 minutes: Very slow, might be stuck
- ⚠️ Missing feature in "implemented" list
- ❌ Error: "Feature X cannot be implemented"

**Common warnings (usually safe):**
```
⚠️ Warning: 2 TODO comments added for manual review
   (These mark places where you might want to customize later)

⚠️ Warning: External API integration requires API key
   (You'll need to add API key in .env file)
```

These are informational, not blocking.

---

#### 5.2.4 S3: Testing Stage

**Example notification:**
```
🧪 S3 COMPLETE - Testing (3m 21s)

✅ Unit tests: 31/31 passed (100%)
✅ Code quality: A (92/100)
✅ Security scan: No issues found
✅ Dependencies: All valid

⚠️ Warnings (non-blocking):
   - 2 unused variables (cleaned up)
   - 1 console.log in debug mode (expected)

✅ Build ready to proceed

Next: S4 (Build) starting now...
```

**What this means:**
Pipeline ran automated tests on the generated code. All 31 tests passed, code quality is high, no security issues found.

**Normal timing:** 2-5 minutes
- Few tests (10-20): 2-3 minutes
- Medium tests (20-40): 3-4 minutes
- Many tests (40+): 4-5 minutes

**What you do:** Nothing if all tests pass.

**What to look for:**
- ✅ All tests passed (X/X = 100%)
- ✅ Code quality grade (A or B is good)
- ✅ No security issues

**When to worry:**
```
❌ Tests failed: 5/31 passed (16% failure rate)

Failed tests:
- test_timer_countdown: Expected 60, got NaN
- test_data_persistence: Data not saved
- test_notification_trigger: Notification not fired
- test_dark_mode_toggle: Colors not changing
- test_payment_flow: Payment sheet not opening

Build STOPPED. Issues must be fixed before proceeding.

Recommended action:
1. Review failed test details
2. Use /modify to fix issues
3. Or simplify specification and retry /create
```

**If tests fail:**
- Read failure details carefully
- Usually means specification was unclear or contradictory
- Pipeline will NOT proceed to S4 (build)
- Options:
  1. `/modify` to fix issues (if app already partially exists)
  2. Cancel and refine specification
  3. `/retry` if transient issue

**Non-blocking warnings are OK:**
```
⚠️ Warning: Unused import in Timer.jsx
   (Cleaned up automatically, no action needed)

⚠️ Warning: console.log found in 3 files
   (Debug logging, removed in production build)
```

These don't stop the build.

---

#### 5.2.5 S4: Build Stage ⏰ LONGEST STAGE

**Example notification:**
```
🏗️ S4 COMPLETE - Build (11m 52s)

✅ Platform: Android
✅ APK created: focusflow-v1.0.0.apk
✅ App size: 22.8 MB
✅ Signing: Successful (debug certificate)
✅ Optimization: Complete

Build artifacts:
📦 APK: /builds/focusflow-v1.0.0.apk
📊 Source maps: /builds/focusflow-sourcemaps.zip
📄 Build logs: /builds/focusflow-build.log

Next: S5 (Quality Check) starting now...
```

**What this means:**
Pipeline compiled all that code into an actual app file (APK for Android, IPA for iOS). This is the "heavy lifting" stage where code becomes a working app.

**Normal timing:** 8-20 minutes (LONGEST STAGE)
- Android (LOCAL): 8-12 minutes
- Android (CLOUD/HYBRID): 10-15 minutes
- iOS (CLOUD - required): 15-20 minutes
- Web (LOCAL/HYBRID): 6-10 minutes

**What you do:** 
- Nothing
- Be patient
- This is the slowest stage
- Don't worry if it takes 15-18 minutes

**What to look for:**
- ✅ APK/IPA file created
- ✅ File size reasonable (20-40 MB typical for mobile apps)
- ✅ Signing successful

**When to worry:**
- ⚠️ If >25 minutes: Very slow, possibly stuck
- ⚠️ If >30 minutes: Likely stuck, consider canceling
- ❌ "Build failed" errors

**Common S4 issues:**

**Issue: "Xcode signing error" (iOS only)**
```
❌ S4 FAILED - Build

Error: Code signing failed
Details: Provisioning profile not found for bundle ID com.yourname.focusflow

Resolution:
1. Ensure Apple Developer account is active
2. Create provisioning profile in Apple Developer portal
3. Update pipeline configuration with profile
4. Retry build

See docs/ios-setup.md for detailed instructions
```

**Issue: "Out of memory"**
```
❌ S4 FAILED - Build

Error: Build process ran out of memory
Details: Java heap space exceeded during Android build

Resolution:
1. Close other applications to free RAM
2. Switch to HYBRID mode (offloads some work to cloud)
3. Or switch to CLOUD mode (builds on cloud servers)

Current mode: LOCAL
Your system RAM: 4GB (minimum 8GB recommended for LOCAL builds)
```

**Issue: "Network timeout" (CLOUD mode)**
```
❌ S4 FAILED - Build

Error: Connection timeout to MacinCloud
Details: Could not establish SSH connection after 3 retries

Resolution:
1. Check internet connection
2. Verify MacinCloud service status: status.macincloud.com
3. Retry build: /retry [build-id]
4. If persistent, switch to LOCAL mode (Android only)
```

**If S4 fails, you'll always get:**
1. Clear error message
2. Explanation of what went wrong
3. Recommended resolution steps
4. Whether to retry or change approach

---

#### 5.2.6 S5: Quality Check Stage

**Example notification:**
```
🔍 S5 COMPLETE - Quality Check (2m 38s)

✅ Security scan: PASSED
✅ Vulnerability check: No issues found
✅ App structure: Valid
✅ Code signing: Verified
✅ Privacy compliance: OK

✅ Ready for deployment

Next: S6 (Deployment) starting now...
```

**What this means:**
Pipeline scanned the built app for security vulnerabilities, malware, suspicious code, and structural issues. Everything passed.

**Normal timing:** 1.5-3.5 minutes

**What you do:** Nothing.

**What to look for:**
- ✅ All checks passed
- ✅ No security vulnerabilities
- ✅ No privacy compliance issues

**When to worry:**
```
⚠️ S5 WARNING - Quality Check (2m 15s)

Security scan: PASSED with warnings

Warnings detected:
1. Hardcoded API key found in source code
   Location: src/config/api.js line 12
   Risk: Medium (API key exposure)
   Recommendation: Move to environment variables

2. Insecure HTTP connection detected
   Location: src/services/analytics.js
   Risk: Low (should use HTTPS)
   Recommendation: Update URL to https://

These are warnings, not errors. Build continues.

✅ Build proceeding to deployment

Next: S6 (Deployment) starting now...
```

**If you see warnings:**
- Build continues (warnings don't block)
- Note the issues
- Fix with `/modify` in next version
- High/Critical warnings should be fixed before production

**Critical errors (rare, blocks build):**
```
❌ S5 FAILED - Quality Check

CRITICAL: Malicious code pattern detected
Details: eval() usage found in 3 files (security risk)

Location:
- src/utils/parser.js line 45
- src/components/DynamicLoader.js line 89
- src/helpers/validator.js line 120

Resolution:
This appears to be generated code attempting dynamic execution.
Please review specification for unsafe requirements.

Build STOPPED for security reasons.

Action: Review and simplify specification, remove dynamic code requirements
```

This is VERY rare (happens <1% of builds) and indicates serious issue with spec.

---

#### 5.2.7 S6: Deployment Stage

**Example notification:**
```
🚀 S6 COMPLETE - Deployment (2m 47s)

✅ GitHub repository created:
   https://github.com/yourusername/focusflow

✅ Source code pushed:
   - 43 files committed
   - Initial release tagged: v1.0.0

✅ APK uploaded to Firebase App Distribution:
   Install link: https://appdistribution.firebase.dev/i/abc123xyz
   Valid for: 180 days

✅ Documentation generated:
   - README.md (setup instructions)
   - CHANGELOG.md (version history)
   - CONTRIBUTING.md (development guide)

Next: S7 (Monitoring Setup) starting now...
```

**What this means:**
Pipeline uploaded your code to GitHub, deployed the app to Firebase for testing, and created documentation.

**Normal timing:** 2-4 minutes

**What you do:** 
- ✅ Save the Firebase App Distribution link (you'll need this to install app)
- ✅ Save the GitHub repository link

**What to look for:**
- ✅ GitHub repo created
- ✅ Firebase deployment successful
- ✅ Install link provided

**When to worry:**
```
❌ S6 FAILED - Deployment

Error: GitHub repository creation failed
Details: Repository name 'focusflow' already exists in your account

Resolution:
1. Choose different app name, OR
2. Delete existing repository at github.com/yourusername/focusflow, OR
3. Use /config github_repo_prefix "v2-" to add prefix (creates "v2-focusflow")

Build artifacts are saved locally but not deployed.
```

**Common S6 issues:**

**Repository name conflict:**
- You already have app with that name
- Solution: Choose different name or delete old repo

**Firebase permission error:**
- Firebase project not properly configured
- Solution: See NB2 (Service Integrations) for Firebase setup

**GitHub token expired:**
- Personal access token no longer valid
- Solution: Generate new token, update configuration

**All S6 failures are non-critical:**
- App file (APK/IPA) is still built
- Saved locally on your computer
- Just not deployed to cloud
- Can manually upload to GitHub/Firebase later

---

#### 5.2.8 S7: Monitoring Setup Stage

**Example notification:**
```
📊 S7 COMPLETE - Monitoring Setup (1m 29s)

✅ Error tracking: Sentry configured
   Dashboard: https://sentry.io/yourorg/focusflow

✅ Analytics: Firebase Analytics enabled
   Dashboard: Firebase Console > Analytics

✅ Crash reporting: Active
✅ Performance monitoring: Active

═══════════════════════════════════════════════════════
✅ BUILD COMPLETE - FocusFlow v1.0.0
═══════════════════════════════════════════════════════

[Full completion summary shown in Section 4.3.4]
```

**What this means:**
Pipeline set up monitoring tools so you can track errors, crashes, and analytics when users use your app.

**Normal timing:** 1-2 minutes

**What you do:**
- ✅ Note the Sentry dashboard URL (check errors later)
- ✅ Note Firebase Analytics URL (check usage stats later)

**What to look for:**
- ✅ All monitoring services active

**When to worry:**
Not critical if this fails:
```
⚠️ S7 WARNING - Monitoring Setup

Sentry configuration skipped: No Sentry API key configured
Firebase Analytics: ✅ Active

Build is COMPLETE but error tracking not available.

To enable Sentry:
1. Create account at sentry.io
2. Add Sentry DSN to configuration: /config sentry_dsn [your-dsn]
3. Monitoring will activate on next build
```

App still works, just won't track errors automatically.

---

### 5.3 Understanding Build Timing

**Total build time breakdown:**

**CREATE (new app): 25-40 minutes**
```
S0: Planning         2-3 min   (7%)
S1: Design           4-5 min   (12%)
S2: Code Generation  9-12 min  (30%)
S3: Testing          2-4 min   (9%)
S4: Build           8-15 min  (40%) ← LONGEST
S5: Quality Check    2-3 min   (7%)
S6: Deployment       2-3 min   (7%)
S7: Monitoring       1-2 min   (4%)
───────────────────────────────
TOTAL:              25-40 min
```

**MODIFY (update app): 15-30 minutes**
```
S0: Analysis         1-2 min   (7%)
S1: Planning         2-3 min   (10%)
S2: Modification     5-10 min  (33%)
S3: Testing          2-3 min   (10%)
S4: Build           6-12 min  (40%) ← LONGEST
S5: Quality Check    1-2 min   (7%)
S6: Deployment       2-3 min   (10%)
S7: Monitoring       1 min     (3%)
───────────────────────────────
TOTAL:              15-30 min
```

**When builds are faster:**
- LOCAL mode (Android/Web)
- Simple apps (few features)
- Powerful computer
- Weekday mornings (less cloud load)

**When builds are slower:**
- CLOUD mode (iOS, or cloud services)
- Complex apps (many features)
- Slow computer/internet
- Peak hours (afternoons US time)

---

### 5.4 Error Notification Patterns

**Pattern 1: Transient Errors (retry automatically)**

```
⚠️ TRANSIENT ERROR - S4 Build

Error: Network timeout connecting to Firebase
Attempt: 1 of 3

Automatic retry in 60 seconds...

[Wait 60 seconds]

✅ Retry successful - Build continuing from S4
```

**What to do:** Nothing. Pipeline retries automatically.

---

**Pattern 2: Recoverable Errors (action required)**

```
❌ BUILD PAUSED - Action Required

Error: GitHub authentication failed
Details: Personal access token expired

Resolution:
1. Generate new token: github.com/settings/tokens
2. Update configuration: /config github_token [new-token]
3. Resume build: /resume [build-id]

Build ID: abc123
Paused at: S6 (Deployment)
```

**What to do:**
1. Follow resolution steps
2. Resume build when fixed
3. Don't restart from beginning

---

**Pattern 3: Fatal Errors (rebuild required)**

```
❌ BUILD FAILED - Cannot Continue

Error: Unsupported feature detected
Details: Specification requires "AR camera" which is not supported

Failed at: S2 (Code Generation)

Resolution:
1. Remove AR camera requirement from specification
2. Simplify to standard camera usage
3. Restart build with updated specification: /create

Build cannot be resumed. Changes required.
```

**What to do:**
1. Fix specification
2. Start new build with `/create`
3. Previous build artifacts discarded

---

## 6. SECTION 4: EXECUTION MODE SELECTION

### 6.1 Three Modes Explained

**CLOUD Mode:**
- Pipeline rents cloud computers to build your app
- Required for iOS apps (needs macOS)
- Optional for Android/Web (can use LOCAL instead)
- Cost: $1.20 per iOS build, $0.20 per Android/Web build
- Speed: Fast (cloud servers are powerful)

**LOCAL Mode:**
- Pipeline uses YOUR computer to build
- Works for Android and Web only (NOT iOS)
- Cost: $0 (free, just your electricity)
- Speed: Depends on your computer power
- Requires: 8GB+ RAM, modern CPU

**HYBRID Mode:**
- Mix of both: some steps local, some steps cloud
- Works for Android and Web only (NOT iOS)
- Cost: $0.20 per build
- Speed: Faster than LOCAL, cheaper than CLOUD
- Best balance for most users

---

### 6.2 Decision Tree

**Question 1: Are you building iOS app?**

```
YES → MUST use CLOUD mode
      └─ Cost: $1.20 per build
      └─ No other option (iOS requires macOS)
```

**NO → Question 2: Is your computer powerful?**

```
8GB+ RAM, modern CPU → Use LOCAL mode
                       └─ Cost: $0 (free)
                       └─ Speed: Good

4-7GB RAM, older CPU → Use HYBRID mode
                       └─ Cost: $0.20
                       └─ Speed: Better than LOCAL

<4GB RAM → Use CLOUD mode
           └─ Cost: $0.20 (Android/Web)
           └─ Speed: Fastest
```

---

### 6.3 Checking Current Mode

```
/status
```

Look for:
```
Mode: LOCAL
```

or

```
Mode: CLOUD
```

or

```
Mode: HYBRID
```

---

### 6.4 Switching Modes

**To change mode:**

```
/config execution_mode [CLOUD/LOCAL/HYBRID]
```

**Examples:**

**Switch to LOCAL (free):**
```
/config execution_mode LOCAL
```

**Switch to CLOUD (iOS or fastest):**
```
/config execution_mode CLOUD
```

**Switch to HYBRID (balanced):**
```
/config execution_mode HYBRID
```

**After changing mode:**
```
Pipeline will respond:
✅ Execution mode changed to LOCAL

Configuration updated. Restart pipeline for changes to take effect.

Command: /restart
```

**Then restart:**
```
/restart
```

**Wait 30-60 seconds, verify:**
```
/status
```

Should show new mode:
```
Mode: LOCAL ✅
```

---

### 6.5 Cost Comparison Table

**Per-build costs:**

| Platform | CLOUD | HYBRID | LOCAL |
|----------|-------|--------|-------|
| iOS | $1.20 | N/A* | N/A* |
| Android | $0.20 | $0.20 | $0 |
| Web | $0.20 | $0.20 | $0 |

*iOS requires macOS, only available in CLOUD mode

**10 builds comparison:**

| Scenario | CLOUD | HYBRID | LOCAL |
|----------|-------|--------|-------|
| 10 iOS builds | $12.00 | N/A | N/A |
| 10 Android builds | $2.00 | $2.00 | $0 |
| 5 iOS + 5 Android | $9.00 | $1.00† | $0† |

†Android builds only (iOS still requires CLOUD)

**Monthly comparison (active development):**

Assuming: 2 apps, 3 updates/week each app = 24 builds/month

| Platform Mix | CLOUD | HYBRID | LOCAL |
|--------------|-------|--------|-------|
| Android only | $4.80 | $4.80 | $0 |
| iOS only | $28.80 | N/A | N/A |
| Both (12 each) | $33.60 | $2.40* | $0* |

*iOS builds still $1.20 each in any mode

**Recommendation:**
- **For iOS:** CLOUD mode (no choice)
- **For Android first app:** LOCAL mode (free learning)
- **For production Android apps:** HYBRID mode (reliable, low cost)
- **For budget-conscious:** LOCAL mode (free but slower)

---

## 7. SECTION 5: DAILY TASKS

### 7.1 Morning Routine (5-10 minutes)

**Every morning before starting work:**

**Step 1: Health check (2 min)**
```
/status
```

Verify:
- ✅ Status: RUNNING
- ✅ All services: Connected
- ✅ No errors in logs

**Step 2: Review overnight activity (3 min)**

Scroll up in Telegram to see:
- Any builds completed overnight?
- Any errors occurred?
- Any notifications missed?

**Step 3: Check disk space (1 min)**

If running LOCAL mode:
- Check available disk space
- Need 10GB+ free for builds
- Clean old builds if needed: `/cleanup`

**Step 4: Plan today's builds (2 min)**

Decide:
- What apps to build/update today?
- What execution mode to use?
- How many builds to queue?

**Step 5: Queue first build (2 min)**

Send first `/create` or `/modify` command to start day's work.

**Total: 5-10 minutes**

---

### 7.2 During Builds (Passive Monitoring)

**While build is running:**

**You don't need to watch constantly.**

Pipeline sends notifications automatically at each stage completion. Just:

**Option A: Work on other tasks**
- Do other work
- Check Telegram when you hear notification
- Read update, continue working

**Option B: Check periodically**
- Check every 10-15 minutes
- Look for latest stage completion
- Verify it's progressing

**Option C: Active monitoring (optional)**
- Watch each stage notification
- Useful for first few builds (learning)
- Not necessary once you understand flow

**What NOT to do:**
- ❌ Stare at Telegram waiting for updates
- ❌ Send `/status` every 2 minutes
- ❌ Worry if stage takes a bit longer than expected
- ❌ Interrupt build unless it's truly stuck (>30 min one stage)

**When to check actively:**
- First time building a specific type of app
- If previous builds failed
- If building complex/expensive app
- If on tight deadline

---

### 7.3 Evening Review (10-15 minutes)

**End of each day:**

**Step 1: Review completed builds (5 min)**

```
/queue
```

Check what completed today.

For each completed build:
- ✅ Did it succeed?
- ✅ Did you test it?
- ✅ Any issues to fix tomorrow?

**Step 2: Check daily costs (2 min)**

```
/cost today
```

Review spending:
- Within budget?
- Any unexpected costs?
- Mode selection optimal?

**Step 3: Plan tomorrow (3 min)**

Based on today's results:
- What to build tomorrow?
- What issues to fix?
- Any configuration changes needed?

**Step 4: Clean up (2 min, if needed)**

If disk space low:
```
/cleanup old-builds
```

**Step 5: Optional: Stop pipeline (if not 24/7)**

If running on-demand:
```
/stop
```

Gracefully stops pipeline overnight.

**Total: 10-15 minutes**

---

## 8. SECTION 6: WEEKLY TASKS

### 8.1 Monday: Week Planning (15-20 minutes)

**Start of each week:**

**Review last week's metrics:**
```
/cost week
```

Shows last 7 days spending.

**Plan this week's builds:**

Create simple plan:
```
WEEK OF MARCH 3-9, 2026

GOALS:
- Build 2 new apps
- Update 3 existing apps
- Total budget: $10

SCHEDULE:
Monday: Evaluate 5 ideas, choose 2
Tuesday: Build App 1 (StudyTimer)
Wednesday: Build App 2 (RecipeBox)
Thursday: Update FocusFlow v1.1
Friday: Update HabitFlow v1.2, test all
```

**Check for pipeline updates:**
```
/version
```

Shows current pipeline version.

If updates available:
```
Pipeline v5.8.0 installed
Update available: v5.8.1

New in v5.8.1:
- Faster S4 builds (10% improvement)
- Better error messages
- Bug fixes

Update now: /update
Or: Schedule for weekend
```

Consider updating (see RB5 for update process).

---

### 8.2 Wednesday: Mid-Week Check (10 minutes)

**Halfway through week:**

**Progress check:**
- How many builds completed?
- On track with weekly goals?
- Any blockers?

**Cost check:**
```
/cost week
```

Are you:
- ✅ Under budget: Great, continue
- ⚠️ At budget: Be conservative rest of week
- ❌ Over budget: Pause builds, analyze why

**Adjust plan if needed:**
- Behind schedule? Simplify remaining builds
- Ahead of schedule? Add stretch goals
- Issues encountered? Allocate time for fixes

---

### 8.3 Friday: Week Review (20-30 minutes)

**End of week:**

**Metrics summary:**

```
WEEK OF MARCH 3-9 RESULTS:

BUILDS:
✅ Completed: 7
❌ Failed: 1 (fixed and retried)
⏱️ Avg time: 32 minutes
💰 Total cost: $8.40 (under $10 budget ✅)

APPS:
🆕 New: 2 (StudyTimer, RecipeBox)
🔄 Updated: 3 (FocusFlow, HabitFlow, MealPlanner)
🧪 Tested: 5/5 (100%)

ISSUES:
- 1 build failed (S4 timeout, resolved by retry)
- 2 bugs found in testing (fixed with /modify)

LEARNINGS:
- HYBRID mode saved $1.80 vs CLOUD
- Complex builds take 35+ minutes, plan accordingly
- Testing immediately after build catches issues early
```

**Cost analysis:**
```
/cost week
```

Detailed breakdown:
- How much per app?
- Which mode was cheapest?
- Any waste (failed builds)?

**Plan next week:**
Based on this week's results.

---

## 9. SECTION 7: MONTHLY TASKS

### 9.1 First of Month: Cost Review (30-45 minutes)

**Monthly financial analysis:**

```
/cost month
```

Full month breakdown.

**Create summary:**
```
FEBRUARY 2026 PIPELINE COSTS

TOTAL: $47.23

BY CATEGORY:
Builds: $38.40
- iOS builds (12): $14.40
- Android builds (120): $24.00
- Web builds (0): $0

API costs: $6.83
- Anthropic: $6.83

Infrastructure: $2.00
- GCP: $2.00 (exceeded free tier)
- Firebase: $0 (within free tier)

BY APP:
- FocusFlow: $12.20 (4 builds)
- StudyTimer: $9.40 (3 builds)
- HabitFlow: $8.60 (3 builds)
- RecipeBox: $7.20 (2 builds)
- Others: $9.83 (various)

REVENUE (if monetized):
- FocusFlow: $127.50
- HabitFlow: $89.20
TOTAL REVENUE: $216.70

PROFIT: $169.47 (78% margin)
```

**Optimization opportunities:**
- Can any iOS builds switch to Android? (Save $1.00 each)
- Using LOCAL when HYBRID would be better?
- Any unnecessary rebuilds?

---

### 9.2 Monthly Maintenance (1-2 hours)

**Log rotation:**
```
/logs cleanup
```

Removes logs older than 90 days.

**Build artifact cleanup:**
```
/cleanup builds --older-than 60-days
```

Removes old APK/IPA files (keep 60 days).

**Dependency check:**
```
/check updates
```

Shows outdated dependencies:
```
Dependency Updates Available:

CRITICAL (security):
- react-native: 0.72.0 → 0.73.2 (security fix)
  Update: /update dependency react-native

RECOMMENDED:
- firebase: 10.1.0 → 10.3.0 (features + fixes)
- sentry: 4.2.0 → 4.5.0 (performance improvements)

OPTIONAL:
- 12 other minor updates
```

Update critical dependencies.

**Backup verification:**
```
/backup verify
```

Ensures backups are working:
```
Backup Status:

Last backup: 2026-03-01 02:00:00 (2 days ago)
Backup size: 1.2 GB
Location: GCS bucket: pipeline-backups-xyz
Retention: 90 days

✅ Backups are healthy

Test restore: /backup test-restore
```

Consider testing restore quarterly.

---

### 9.3 Monthly Metrics Report (30 minutes)

**Generate comprehensive report:**

```
PIPELINE METRICS - FEBRUARY 2026

PRODUCTIVITY:
- Apps built: 5 new
- Apps updated: 12 updates across 8 apps
- Total builds: 32
- Success rate: 96.9% (31/32 succeeded)

PERFORMANCE:
- Avg build time: 31 minutes
- Fastest build: 22 minutes (simple app, LOCAL)
- Slowest build: 47 minutes (complex app, CLOUD)

EFFICIENCY:
- Cost per build: $1.48 average
- Most cost-effective mode: LOCAL ($0)
- Most expensive mode: CLOUD iOS ($1.20)

QUALITY:
- Builds tested: 100%
- Bugs found in testing: 8
- Bugs found post-launch: 2
- User-reported issues: 5

FINANCIALS:
- Total costs: $47.23
- Total revenue (from apps): $216.70
- Net profit: $169.47
- ROI: 359%

GOALS:
- February goal: 5 new apps ✅ (achieved)
- Budget goal: <$50 ✅ (under by $2.77)
- Revenue goal: >$200 ✅ (exceeded by $16.70)
```

Use this to:
- Track improvement month-over-month
- Identify trends
- Set next month's goals
- Justify pipeline investment

---

## 10. QUICK REFERENCE

### 10.1 Command Cheat Sheet

```
ESSENTIAL COMMANDS:

/status              → Check pipeline health
/help                → List all commands
/evaluate [spec]     → Score app idea (0-100)
/create [spec]       → Build new app
/modify [url] [changes] → Update existing app
/info [app-name]     → Get app information
/logs                → View recent logs
/queue               → View build queue
/cost                → View costs
/cancel [build-id]   → Cancel active/queued build

CONFIGURATION:

/config show         → View current config
/config execution_mode [mode] → Change mode
/config [key] [value] → Update config value
/restart             → Restart pipeline
/stop                → Stop pipeline
/start               → Start pipeline

MAINTENANCE:

/cleanup             → Clean old builds
/update              → Update pipeline
/backup              → Manage backups
/diagnose            → Run diagnostics

INFORMATION:

/version             → Pipeline version
/stats               → Usage statistics
/help [command]      → Help for specific command
```

---

### 10.2 Normal Build Timings

**CREATE (new app):**
- Total: 25-40 minutes
- S4 is longest (8-15 min)
- S2 is second longest (9-12 min)

**MODIFY (update):**
- Total: 15-30 minutes
- Faster than CREATE
- Same stages but optimized

**By mode:**
- LOCAL: Slowest (free)
- HYBRID: Medium speed ($0.20)
- CLOUD: Fastest ($1.20 iOS, $0.20 Android/Web)

---

### 10.3 When to Worry

**Times to worry:**

❌ **S0-S3 taking >10 minutes each**
→ Something stuck, check /logs

❌ **S4 taking >30 minutes**
→ Likely stuck, consider canceling

❌ **Total build >60 minutes**
→ Definitely stuck, cancel and retry

❌ **Build fails at same stage repeatedly**
→ Systematic issue, review specification

---

**[END OF PART 4]**














---

# RB1: DAILY OPERATIONS & STANDARD WORKFLOWS
## PART 5 of 5 (FINAL)

---

## 11. TROUBLESHOOTING

**PURPOSE:** Quick solutions to common operational problems encountered during daily pipeline use.

---

### 11.1 PIPELINE WON'T START

**Symptom:**
```
/start

❌ Failed to start pipeline
Error: Pipeline is already running on port 8080
```

**Diagnosis:**

**Check 1: Is it actually running?**
```
/status
```

If responds with status, it IS running. You don't need to start it.

**Check 2: Port conflict**

Another process using port 8080.

**Solution A: Find and stop the conflicting process**

**macOS/Linux:**
```bash
lsof -i :8080
```

Shows what's using port 8080:
```
COMMAND   PID   USER
python    1234  yourname
```

Kill it:
```bash
kill 1234
```

**Windows:**
```cmd
netstat -ano | findstr :8080
```

Shows PID, then:
```cmd
taskkill /PID 1234 /F
```

**Solution B: Change pipeline port**

```
/config port 8081
/start
```

---

**Symptom:**
```
/start

❌ Failed to start pipeline
Error: Missing required API key: ANTHROPIC_API_KEY
```

**Diagnosis:**
Configuration incomplete.

**Solution:**

Check .env file:
```bash
cd ~/ai-factory-pipeline
cat .env | grep ANTHROPIC
```

If empty or invalid:
```
/config anthropic_api_key sk-ant-api03-...
```

Then:
```
/start
```

---

**Symptom:**
```
/start

Pipeline starting...
[30 seconds pass]
[No response]
```

**Diagnosis:**
Pipeline crashed during startup.

**Solution:**

Check startup logs:
```bash
cd ~/ai-factory-pipeline
tail -n 50 logs/startup.log
```

Look for error messages at end of file.

**Common startup errors:**

**"ModuleNotFoundError: No module named 'anthropic'"**
```
Missing dependency.

Fix:
pip install anthropic --break-system-packages
/start
```

**"Permission denied: /var/log/pipeline"**
```
Insufficient permissions.

Fix:
sudo chown -R $USER ~/ai-factory-pipeline
/start
```

**"Cannot connect to database"**
```
Database service not running.

Fix:
/config db_start_on_boot true
/start
```

---

### 11.2 BUILDS CONSISTENTLY FAILING

**Symptom:**
Every build fails at same stage (e.g., S4 always fails).

---

**Pattern A: Always fails at S2 (Code Generation)**

```
❌ S2 FAILED - Code Generation

Error: Feature "X" is not supported
```

**Diagnosis:**
Your specifications consistently request unsupported features.

**Solution:**

Review what features pipeline supports:
```
/help features
```

Returns:
```
SUPPORTED FEATURES:

✅ Standard mobile UI components
✅ Local data storage
✅ Push notifications
✅ Camera/photo access
✅ Location services
✅ Payment integration (RevenueCat)
✅ Social login (Google, Apple, Facebook)
✅ Cloud sync (Firebase)
✅ External API calls
✅ Dark mode
✅ Internationalization

❌ NOT SUPPORTED:
❌ Blockchain/cryptocurrency
❌ Augmented reality (AR)
❌ Virtual reality (VR)
❌ Real-time video streaming
❌ Custom ML models
❌ Peer-to-peer networking
❌ Advanced 3D graphics
```

**Action:**
- Remove unsupported features from spec
- Simplify to supported features
- Or use external services for complex features

---

**Pattern B: Always fails at S4 (Build)**

```
❌ S4 FAILED - Build

Error: Out of memory
Java heap space exceeded
```

**Diagnosis:**
Your computer doesn't have enough RAM for builds.

**Solution:**

**Option 1: Free up memory**
- Close all other applications
- Close browser tabs
- Restart computer
- Try build again

**Option 2: Switch to HYBRID mode**
```
/config execution_mode HYBRID
/restart
```

Offloads heavy work to cloud ($0.20 per build).

**Option 3: Switch to CLOUD mode**
```
/config execution_mode CLOUD
/restart
```

Builds entirely on cloud servers ($0.20-1.20 per build).

**Option 4: Upgrade computer RAM**
- Minimum: 8GB RAM
- Recommended: 16GB RAM
- LOCAL mode works best with 16GB+

---

**Pattern C: Always fails at S6 (Deployment)**

```
❌ S6 FAILED - Deployment

Error: GitHub authentication failed
```

**Diagnosis:**
GitHub credentials expired or invalid.

**Solution:**

**Step 1: Generate new GitHub token**

1. Go to: https://github.com/settings/tokens
2. Click "Generate new token (classic)"
3. Name: "AI Factory Pipeline"
4. Scopes:
   - ☑️ repo (full control)
   - ☑️ workflow
   - ☑️ admin:repo_hook
5. Click "Generate token"
6. Copy token (starts with `ghp_`)

**Step 2: Update pipeline configuration**
```
/config github_token ghp_xxxxxxxxxxxxxxxxxxxx
/restart
```

**Step 3: Retry failed build**
```
/retry [build-id]
```

Or start fresh:
```
/create
[your specification]
```

---

### 11.3 SLOW PERFORMANCE

**Symptom:**
Builds that normally take 30 minutes now take 50-60 minutes.

---

**Cause A: Computer performance**

**Diagnosis:**

Check system resources while build running:

**macOS:**
- Open Activity Monitor
- Check CPU % and Memory pressure

**Windows:**
- Open Task Manager
- Check CPU % and Memory usage

**Linux:**
```bash
top
```

**If CPU at 100% or Memory >90%:**
- Other apps using resources
- Close unnecessary applications
- Restart computer
- Consider switching to HYBRID/CLOUD mode

---

**Cause B: Network slowness (CLOUD/HYBRID mode)**

**Diagnosis:**

Test internet speed:
- Go to speedtest.net
- Run test

**If download <10 Mbps or upload <5 Mbps:**
- Network too slow for efficient cloud operations
- Causes timeouts and retries
- Switch to LOCAL mode (if Android/Web)

**If network is normally fast but slow right now:**
- Wait and retry later
- Peak internet hours (evenings) are slower
- Build during off-peak (mornings)

---

**Cause C: Pipeline version outdated**

**Diagnosis:**
```
/version
```

If shows:
```
Pipeline: v5.4.0
Latest: v5.8.0

You are 2 versions behind.
Update recommended.
```

**Solution:**
```
/update
```

Newer versions are often faster.

See RB5 (Updating AI Factory Pipeline) for full update process.

---

**Cause D: Disk space low**

**Diagnosis:**

Check disk space:

**macOS:**
```bash
df -h ~
```

**Windows:**
- File Explorer → This PC → Check C: drive

**Linux:**
```bash
df -h /home
```

**If <10GB free:**

Pipeline slows down when disk space low.

**Solution:**
```
/cleanup builds --older-than 30-days
/cleanup logs --older-than 60-days
```

Or manually delete old files:
```bash
cd ~/ai-factory-pipeline/builds
rm -rf archive/*
```

Frees up space immediately.

---

### 11.4 COSTS HIGHER THAN EXPECTED

**Symptom:**
```
/cost today

TOTAL TODAY: $8.40

Expected: ~$2.00
```

Much higher than expected.

---

**Investigation steps:**

**Step 1: Breakdown by category**
```
/cost today --detailed
```

Shows:
```
Cost Breakdown - March 3, 2026

BUILDS:
✅ FocusFlow v1.0.0 (CREATE, CLOUD): $1.20
✅ FocusFlow v1.0.1 (MODIFY, CLOUD): $1.20
❌ FocusFlow v1.0.2 (MODIFY, CLOUD): $1.20 FAILED
❌ FocusFlow v1.0.3 (MODIFY, CLOUD): $1.20 FAILED
✅ FocusFlow v1.0.4 (MODIFY, CLOUD): $1.20

API COSTS:
Anthropic Claude API: $2.40
- Build requests: $2.10
- Monitoring: $0.30

INFRASTRUCTURE:
GCP Cloud Run: $0.00
Firebase: $0.00
MacinCloud: $0.00 (within plan)

TOTAL: $8.40
```

**Cause identified:** 3 builds for same app, 2 failed but still charged.

---

**Common causes of high costs:**

**Cause A: Using CLOUD mode when LOCAL would work**

**Issue:**
Building Android apps in CLOUD mode ($1.20) when LOCAL mode ($0) would work.

**Fix:**
```
/config execution_mode LOCAL
/restart
```

**Savings:** $1.20 per Android/Web build

---

**Cause B: Failed builds still cost money**

**Issue:**
Failed builds consume API credits and cloud resources even though they didn't produce working app.

**Prevention:**
- Test specifications with `/evaluate` first (free)
- Start with simple spec, add features incrementally
- Don't retry immediately if build fails - understand why first
- Fix specification before retrying

**Fix for future:**
Be more careful with specifications to avoid failed builds.

---

**Cause C: Building same app repeatedly**

**Issue:**
Making many small changes, building each time:
- Change color → Build ($1.20)
- Fix typo → Build ($1.20)
- Adjust spacing → Build ($1.20)
= $3.60 for minor changes

**Better approach:**
Batch changes into one build:
```
/modify [url]

Changes for v1.1:
- Change primary color to #2196F3
- Fix typo in Settings screen ("Notifcations" → "Notifications")
- Adjust button spacing on main screen
```

= $1.20 for all changes

**Fix:**
Plan changes, batch them, build once.

---

**Cause D: Accidentally using expensive execution mode**

**Issue:**
Meant to use HYBRID ($0.20) but configuration was CLOUD ($1.20).

**Prevention:**
Check mode before building:
```
/status
```

Verify mode is what you expect.

**Fix:**
```
/config execution_mode HYBRID
/restart
```

---

### 11.5 APP CRASHES AFTER BUILD

**Symptom:**
Build succeeds (all stages ✅) but app crashes immediately when opened.

---

**Diagnosis Step 1: Get crash logs**

**For Android:**

1. Install app via Firebase App Distribution
2. Open app (it crashes)
3. Check Telegram for automatic crash report:

```
🔴 CRASH DETECTED - FocusFlow v1.0.0

Platform: Android 13 (Samsung Galaxy S21)
Time: 2026-03-03 15:23:45

Error: TypeError: Cannot read property 'duration' of undefined
Location: Timer.jsx:47

Stack trace:
  at Timer.componentDidMount (Timer.jsx:47)
  at App.render (App.jsx:23)
  at ReactNative.render (index.js:12)

Crash report: https://sentry.io/crash/abc123

Action: Review Timer.jsx line 47 for undefined property access
```

**For iOS:**

1. Install via TestFlight
2. Open app (it crashes)
3. Check Sentry dashboard: https://sentry.io/[your-org]/[app-name]
4. Or check Telegram for crash notification

---

**Diagnosis Step 2: Understand the crash**

Read error message carefully.

**Example:**
```
Error: TypeError: Cannot read property 'duration' of undefined
Location: Timer.jsx:47
```

**Translation to plain English:**
Code is trying to access `something.duration` but `something` is undefined (doesn't exist).

At line 47 of Timer.jsx file.

---

**Solution: Fix with /modify**

```
/modify https://github.com/yourusername/focusflow

Fix crash on app launch:

ERROR: TypeError: Cannot read property 'duration' of undefined at Timer.jsx:47

ROOT CAUSE:
Code assumes timer settings exist on first launch, but they're undefined until user sets them.

FIX NEEDED:
Add null check before accessing timer.duration:
- Check if timer settings exist
- If not, use default values
- Prevent accessing properties of undefined objects

Also add error handling to prevent future crashes from similar issues.
```

Pipeline will:
1. Analyze the crash
2. Fix the code
3. Add defensive checks
4. Rebuild app
5. Deploy fixed version

Test new version to verify crash is fixed.

---

**Common crash causes:**

**1. Undefined variables**
Most common cause. Code assumes something exists but it doesn't.

**2. Network errors not handled**
App tries to fetch data from API, fails, crashes.

**3. Incorrect data types**
Code expects number, gets string (or vice versa).

**4. Missing permissions**
App tries to access camera/location without requesting permission first.

**5. Memory issues**
App tries to load too much data at once.

---

**Prevention:**

When writing specifications:
```
IMPORTANT: Add error handling for all:
- API calls (handle failures gracefully)
- Data access (check if data exists before using)
- User inputs (validate before processing)
- Permissions (request before using features)

App should never crash - show error messages instead.
```

Pipeline will generate more defensive code.

---

### 11.6 TELEGRAM BOT NOT RESPONDING

**Symptom:**
You send `/status` or any command, bot doesn't respond for 30+ seconds.

---

**Diagnosis:**

**Check 1: Is pipeline running?**

Open terminal/command prompt:

**macOS/Linux:**
```bash
ps aux | grep pipeline
```

**Windows:**
```cmd
tasklist | findstr python
```

If you see pipeline process: It's running.
If you don't: It's stopped.

---

**Check 2: Is Telegram bot token valid?**

```bash
cd ~/ai-factory-pipeline
cat .env | grep TELEGRAM_BOT_TOKEN
```

If empty or looks wrong:

**Solution:**

1. Create new bot (or use existing):
   - Message @BotFather on Telegram
   - Send: `/newbot` (or `/mybots` to list existing)
   - Get token

2. Update configuration:
   ```
   /config telegram_bot_token 1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
   ```

3. Restart:
   ```
   /restart
   ```

---

**Check 3: Network connectivity**

Test internet connection:
```bash
ping google.com
```

If no response: Network is down.

**Solution:**
- Fix internet connection
- Restart router
- Try mobile hotspot temporarily

---

**Check 4: Telegram service issues**

Check Telegram status:
- Go to: https://downdetector.com/status/telegram/
- Or: Try messaging other bots

If Telegram is down globally:
- Wait for Telegram to recover (rare)
- Usually resolves within minutes

If Telegram works for other bots but not yours:
- Your bot might be suspended
- Check @BotFather for messages
- May need to create new bot

---

**Last resort: Restart everything**

```bash
# Stop pipeline
/stop

# Wait 10 seconds

# Start pipeline
/start

# Wait 30 seconds

# Test
/status
```

If still not responding:
- Check logs: `tail -f ~/ai-factory-pipeline/logs/telegram.log`
- Look for error messages
- See NB1-4 for reconfiguration

---

### 11.7 UNEXPECTED BEHAVIOR AFTER UPDATE

**Symptom:**
Updated pipeline to new version, now things work differently or break.

---

**Example issues:**

**Issue A: New version changes command syntax**

Old:
```
/create platform:android [spec]
```

New (v5.8):
```
/create
platform: android

[spec]
```

**Solution:**
Update your command format to match new syntax.

Check changelog:
```
/changelog
```

Shows breaking changes in new version.

---

**Issue B: New version has bugs**

New version introduces regression (new bug).

**Solution:**

Rollback to previous version:
```
/rollback v5.5.0
```

Wait for bug fix release:
```
/check-updates
```

When v5.8.1 available with fix:
```
/update
```

---

**Issue C: Configuration incompatible**

New version expects different configuration format.

**Solution:**

Run migration:
```
/migrate-config
```

Pipeline automatically updates configuration to new format.

Or manually update as indicated in changelog.

---

**Prevention:**

Before updating:
1. Read changelog
2. Backup configuration
3. Note breaking changes
4. Test in non-critical time
5. Be ready to rollback

See RB5 (Updating Pipeline) for full update procedures.

---

## 12. NEXT STEPS

### 12.1 You've Mastered Daily Operations!

**What you now know:**

✅ **Starting & stopping pipeline**
- Health checks
- Daily routines
- System monitoring

✅ **Core workflows**
- /evaluate: Validate ideas
- /create: Build apps
- /modify: Update apps
- /status, /info, /logs: Monitor operations

✅ **Understanding pipeline feedback**
- Stage-by-stage notifications (S0-S7)
- Error messages and warnings
- Build timing expectations
- When to worry vs when to wait

✅ **Execution mode management**
- CLOUD vs LOCAL vs HYBRID
- Cost implications
- Performance tradeoffs
- When to switch modes

✅ **Maintenance routines**
- Daily tasks (5-10 min)
- Weekly tasks (15-30 min)
- Monthly tasks (1-2 hours)
- Cost tracking and optimization

✅ **Troubleshooting**
- Pipeline startup issues
- Build failures
- Performance problems
- Cost management
- App crashes

---

### 12.2 What to Read Next

**Depending on your situation:**

---

**If you haven't built your first app yet:**

**→ Read NB5: First 30 Days - Setup to First Profit**

Why:
- Guided journey building first app
- Covers idea validation → deployment → monetization
- Step-by-step for 30 days
- Gets you from zero to profitable app

**After NB5, return to:**
- RB2 (Troubleshooting - deeper problem-solving)
- RB3 (Cost Control - optimization strategies)

---

**If you've built 1-2 apps successfully:**

**→ Read NB6: Real-World Scenarios & Solutions**

Why:
- Specific problems you'll encounter
- Proven solutions to common situations
- Scenario-based (not sequential)
- Reference when specific issue arises

**Then read:**
- RB4 (App Store Delivery - submission strategies)
- RB6 (Project Updates - maintaining apps long-term)

---

**If you're building 3+ apps:**

**→ Read NB7: App Portfolio Management**

Why:
- Managing multiple apps efficiently
- Portfolio strategy (build/grow/maintain/kill)
- Cross-promotion between apps
- Scaling operations

**Also read:**
- RB3 (Cost Control - critical at scale)
- RB6 (Project Updates - systematic update strategies)

---

**If you're encountering technical issues:**

**→ Read RB2: Troubleshooting & Problem Resolution**

Why:
- Comprehensive problem diagnosis
- Stage-by-stage failure handling
- Service-specific issues
- App-level debugging
- Escalation paths

**Also read:**
- RB5 (Pipeline Updates - may fix issues)
- NB6 (Real-World Scenarios - similar problems)

---

**If you want to optimize costs:**

**→ Read RB3: Cost Control & System Maintenance**

Why:
- Detailed cost breakdowns
- Optimization strategies
- Budget tracking
- Mode selection guidance
- Revenue tracking integration

**Also read:**
- RB1 Section 4.4 (Execution modes - this document)
- NB5 Week 2 (Monetization - revenue side)

---

**If you need to submit apps to stores:**

**→ Read RB4: App Store & Google Play Delivery**

Why:
- Complete submission guide
- Store listing optimization
- Rejection handling
- Review response strategies
- Update management

**Also read:**
- NB5 Days 8-10 (First submission walkthrough)
- RB6 (Updates after initial launch)

---

**If you need to update existing apps:**

**→ Read RB6: Updating & Patching Existing Projects**

Why:
- Modification best practices
- Version management
- Conflict resolution
- Testing strategies
- Update frequency planning

**Also read:**
- RB1 Section 4.4 (/modify workflow - this document)
- RB4 (Submitting updates to stores)

---

**If you need to update pipeline itself:**

**→ Read RB5: Updating AI Factory Pipeline System**

Why:
- Safe update procedures
- Version compatibility
- Rollback strategies
- Configuration migration
- Dependency management

**Also read:**
- RB3 (System maintenance)
- RB2 (Post-update troubleshooting)

---

### 12.3 Building Your Operating Rhythm

**After mastering daily operations, establish your personal rhythm:**

---

**Solo Operator Rhythm (2-4 hours/day):**

**Daily (30-60 min):**
- Morning: Health check + queue 1-2 builds
- Afternoon: Test completed builds
- Evening: Review costs + plan tomorrow

**Weekly (2-3 hours):**
- Monday: Week planning + evaluate ideas
- Wednesday: Mid-week progress check
- Friday: Week review + cost analysis

**Monthly (3-4 hours):**
- Cost optimization
- Metrics reporting
- System maintenance
- Goal setting for next month

**Result:** Sustainable, efficient pipeline usage without burnout.

---

**Team Operator Rhythm (multiple people):**

**Dedicated Operator:**
- Full-time pipeline monitoring
- Handles all /create and /modify commands
- Manages queue optimization
- Troubleshoots issues
- Reports to team daily

**Developers:**
- Write specifications
- Test completed builds
- Report bugs for /modify
- Review code if needed

**Product/Business:**
- Evaluate ideas
- Prioritize features
- Monitor costs vs revenue
- Make build/no-build decisions

**Result:** Professional software factory operation.

---

**Casual User Rhythm (few hours/week):**

**Weekly (1-2 hours):**
- Build or update 1 app
- Test it
- Submit to stores if ready

**Monthly (2-3 hours):**
- Review all apps
- Update high-priority apps
- Cost check
- Plan next month

**Result:** Side project pace, sustainable long-term.

---

### 12.4 Efficiency Tips from Experience

**Tip 1: Batch similar tasks**

Instead of:
```
Day 1: Evaluate idea A
Day 2: Evaluate idea B
Day 3: Build idea A
Day 4: Build idea B
```

Do:
```
Day 1: Evaluate ideas A, B, C, D, E (50 min)
Day 2: Build top 2 ideas (queue both, 60 min total)
Day 3: Test both builds
```

**Saves:** Context switching time, more efficient workflow.

---

**Tip 2: Use queue strategically**

Build during times when you don't need computer:
- Queue before lunch (builds while you eat)
- Queue before meetings (builds while you meet)
- Queue end of day (builds overnight if 24/7 mode)

**Saves:** Productive time, parallel processing.

---

**Tip 3: Template common specifications**

Save specification templates for common app types:

**Template: Simple Utility App**
```
App Name: [NAME]
Platform: [iOS/Android/Web]
Description: [2-3 sentences]
Target Users: [specific audience]

Core Features:
- [Feature 1: CRUD operation]
- [Feature 2: Display/visualization]
- [Feature 3: Settings/preferences]
- Dark mode
- Data export

Monetization: Freemium
- Free: Basic features
- Premium: $2.99/month - Advanced features
```

**Saves:** 15-20 minutes per app specification.

---

**Tip 4: Test immediately after build**

Don't wait. Test same day as build completes.

**Why:**
- Feedback fresh in mind
- Faster iteration cycles
- Catch issues before forgetting details
- Maintain momentum

**Saves:** Mental overhead of context switching.

---

**Tip 5: Document patterns**

When you solve a problem, document it:

```
PATTERN: "Build fails at S4 with memory error"
SOLUTION: Switch to HYBRID mode
WHEN: Computer has <8GB RAM
COST: +$0.20 per build
RESULT: Builds succeed
```

**Saves:** Solving same problem repeatedly.

---

### 12.5 Advanced Operations (Beyond This Runbook)

**Once comfortable with daily operations, explore:**

**Advanced Features:**
- Custom tech stacks beyond defaults
- Multi-platform simultaneous builds
- Automated testing pipelines
- Custom deployment targets
- Advanced monitoring configurations

**Integration:**
- CI/CD pipeline integration
- Webhook automation
- External tool connections
- Custom build triggers
- Automated version management

**Scaling:**
- Multiple pipeline instances
- Load balancing builds
- Team collaboration workflows
- Enterprise configurations
- High-throughput optimization

**These topics covered in:**
- Advanced operator documentation (when available)
- Technical specification (v5.8 document)
- GitHub issues and discussions
- Community knowledge base

---

### 12.6 Getting Help

**When you encounter issues not covered here:**

**1. Check other runbooks first:**
- RB2: Troubleshooting (comprehensive problem-solving)
- NB6: Real-World Scenarios (specific situations)
- Technical specification v5.8 (deep technical details)

**2. Use built-in diagnostics:**
```
/diagnose
```

Automated troubleshooting tool.

**3. Check pipeline logs:**
```
/logs error
```

Recent error messages often explain issues.

**4. Search GitHub issues:**
- Repository: [pipeline-github-url]
- Search existing issues
- Likely someone encountered similar problem

**5. Ask in community:**
- Create GitHub issue with details
- Include: error messages, logs, what you tried
- Pipeline version, execution mode
- Specification (if relevant)

**6. Emergency support:**
- Critical production issues
- Contact information in technical specification
- Include build ID, error details, urgency

---

## 13. FINAL SUMMARY

### 13.1 What You've Learned

**Core Competencies:**

✅ **Pipeline Operation**
- Start/stop procedures
- Health monitoring
- Resource management
- Configuration control

✅ **Build Management**
- Evaluating ideas effectively
- Creating new apps efficiently
- Modifying existing apps correctly
- Understanding build lifecycle

✅ **Communication**
- Reading Telegram notifications accurately
- Interpreting stage completions
- Understanding error messages
- Knowing when to take action

✅ **Mode Selection**
- CLOUD vs LOCAL vs HYBRID
- Cost-performance tradeoffs
- Strategic mode switching
- Budget optimization

✅ **Maintenance**
- Daily operational tasks
- Weekly review processes
- Monthly optimization
- Long-term sustainability

✅ **Problem Resolution**
- Common issue diagnosis
- Quick fix application
- Escalation decision-making
- Prevention strategies

---

### 13.2 Operating Principles to Remember

**1. Patience during builds**
- S4 takes 8-15 minutes (normal)
- Total builds: 25-40 minutes
- Don't interrupt unless stuck (>30 min one stage)

**2. Verification before action**
- Check `/status` before building
- Review mode before queuing
- Verify costs before month-end

**3. Batch operations**
- Evaluate multiple ideas together
- Queue multiple builds strategically
- Combine changes in single /modify

**4. Test immediately**
- Install app same day as build
- Test thoroughly before next version
- Document issues for /modify

**5. Monitor costs**
- Daily check if using CLOUD mode
- Weekly analysis for patterns
- Monthly optimization review

**6. Proactive maintenance**
- Don't wait for problems
- Regular cleanup (logs, builds)
- Stay updated (pipeline versions)

**7. Documentation**
- Keep track of your apps
- Note common patterns
- Document solutions
- Build personal knowledge base

---

### 13.3 Success Metrics

**You're operating pipeline successfully when:**

✅ **95%+ build success rate**
- Most builds complete without errors
- Failures are understood and resolved
- Specifications are refined over time

✅ **Builds complete in expected timeframes**
- CREATE: 25-40 minutes
- MODIFY: 15-30 minutes
- No chronic slowness

✅ **Costs match expectations**
- Within monthly budget
- No surprise expenses
- Optimal mode selection for each build

✅ **Apps work on first test**
- Few critical bugs
- Features implemented correctly
- Specifications are clear and complete

✅ **Efficient workflow**
- <10 min daily maintenance
- Strategic build scheduling
- Minimal context switching

✅ **Sustainable pace**
- Not overwhelming
- Consistent productivity
- Long-term maintainable

---

### 13.4 Continuous Improvement

**Track your metrics monthly:**

```
MONTH: MARCH 2026

BUILDS:
Total: 32
Success rate: 96.9% (31/32)
Avg time: 31 min
Cost: $47.23

EFFICIENCY:
Specifications refined: 5
Mode switches: 3 (optimization)
Failed builds: 1
Time saved: ~4 hours (vs manual coding)

APPS:
New: 5
Updated: 12 updates across 8 apps
Deployed: 100%

LEARNINGS:
- HYBRID mode optimal for Android
- Batching evals saves time
- Test immediately = fewer bugs
- Specification templates = faster

GOALS FOR APRIL:
- Achieve 98% success rate
- Reduce avg build time to <30 min
- Build 3 new apps
- Keep costs under $45
```

**Review monthly, refine processes, improve continuously.**

---

### 13.5 You're Ready

You now have everything needed for daily pipeline operations:

- ✅ How to start/stop/monitor pipeline
- ✅ How to use all core commands
- ✅ How to interpret feedback
- ✅ How to choose execution modes
- ✅ How to maintain system health
- ✅ How to troubleshoot problems
- ✅ How to optimize costs
- ✅ How to build sustainable workflows

**Go build amazing things.**

---

**═══════════════════════════════════════════════════════════════**
**END OF RB1: DAILY OPERATIONS & STANDARD WORKFLOWS**
**═══════════════════════════════════════════════════════════════**
