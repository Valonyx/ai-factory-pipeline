# RESPONSE PLAN for NB0: MASTER NAVIGATION GUIDE

```
═══════════════════════════════════════════════════════════════════════════════
NB0 GENERATION PLAN - 4 PARTS
═══════════════════════════════════════════════════════════════════════════════

Part 1: Front Matter + Section 1 (How to Use This System)
         + Section 2 (Quick Start Paths by Situation)

Part 2: Section 3 (Complete Documentation Map)
         + Section 4 (Topic-Based Navigation)

Part 3: Section 5 (Reference Quick Links)
         + Section 6 (Learning Paths)

Part 4: Section 7 (When to Read What) + Quick Reference + Summary

Delivering Part 1 now. Reply "Cont" for Part 2.
```

---

# NB0: MASTER NAVIGATION GUIDE

---

**PURPOSE:** Help you find exactly what you need across the entire AI Factory Pipeline documentation system — in under 2 minutes, every time.

**WHEN TO USE:**
- You're new and don't know where to start
- You're stuck and don't know which document to open
- You want to understand how all the documents relate to each other
- You're looking for a specific topic and can't remember where it lives
- You've been reading for a while and feel lost

**ESTIMATED LENGTH:** 20-25 pages

**PREREQUISITE READING:** None. This is the first document to read if you feel overwhelmed.

**TIME TO FIND WHAT YOU NEED:** Under 2 minutes using the indexes in this notebook

**WHAT YOU'LL MASTER:**
- ✅ The complete documentation system laid out in one place
- ✅ Which document to open first based on your exact situation
- ✅ The difference between Notebooks (learning) and Runbooks (reference)
- ✅ Where every major topic lives — without searching
- ✅ A reading path that matches your current stage
- ✅ The single most important document for every common problem

---

## 1. HOW TO USE THIS DOCUMENTATION SYSTEM

### 1.1 The Documentation System at a Glance

The AI Factory Pipeline documentation consists of **14 documents** organized into three groups:

```
THE COMPLETE DOCUMENTATION SYSTEM
════════════════════════════════════════════════════════

GROUP 1 — IMPLEMENTATION NOTEBOOKS (NB1-4)
Technical setup guides. Read these once during installation.
After setup, archive them. You won't need them again unless
reinstalling from scratch.

  NB1: Installation Guide
  NB2: Configuration
  NB3: Integration Setup
  NB4: Testing & Verification

GROUP 2 — OPERATOR NOTEBOOKS (NB0, NB5, NB6, NB7)
Learning documents. Read sequentially when preparing for
a new stage of your journey. Each tells a story with context,
examples, and explanations.

  NB0: Master Navigation Guide  ← You are here
  NB5: First 30 Days — Setup to First Profit
  NB6: Real-World Scenarios & Solutions
  NB7: App Portfolio Management

GROUP 3 — RUNBOOKS (RB1-RB6)
Reference documents. Look up specific sections when you
need to perform a specific task or solve a specific problem.
Not meant to be read cover-to-cover.

  RB1: Daily Operations & Standard Workflows
  RB2: Troubleshooting & Problem Resolution
  RB3: Cost Control & System Maintenance
  RB4: App Store & Google Play Delivery
  RB5: Updating AI Factory Pipeline System
  RB6: Updating & Patching Existing Projects
```

### 1.2 Notebooks vs. Runbooks — The Critical Difference

Understanding this distinction prevents the most common source of documentation overwhelm.

**Notebooks (NB)** are written to be read. They have narrative flow, build on each other, include examples and context, and are designed to prepare you for a stage of the journey before you begin it. Think of them like a course or a book — you read them when you have time to learn.

**Runbooks (RB)** are written to be consulted. They are organized by task rather than by narrative. When you need to do a specific thing, you open the right runbook, find the right section, and follow the steps. Think of them like a cookbook — you don't read the whole thing; you look up the recipe you need right now.

```
THE READING MODEL
════════════════════════════════════════════════════════

Notebooks:   Read BEFORE you reach a new stage
             Example: Read NB5 before building your first app
             Example: Read NB7 before building your 3rd app

Runbooks:    Consult DURING a specific task or problem
             Example: Open RB4 when submitting to app stores
             Example: Open RB2 when something breaks
             Example: Open RB3 when your costs feel high

Never:       Try to read all Runbooks cover-to-cover before starting
             They're reference documents, not pre-reading
```

### 1.3 The Just-In-Time Philosophy

The most effective way to use this documentation: read what you need, when you need it — not everything upfront.

The just-in-time approach:
1. Identify your current stage (see Section 2 below)
2. Read the Notebook that prepares you for that stage
3. Start doing the work
4. When you hit a specific task or problem, open the right Runbook section
5. Complete the task, then close the Runbook
6. When you approach the next stage, read the next Notebook

You will naturally discover which documents are most useful through doing. Operators who try to read everything first often feel less prepared than those who dive in — because documentation without practice context doesn't stick.

### 1.4 How This Guide Is Organized

The rest of NB0 is divided into six sections you can jump to directly:

| Section | What It Gives You | When to Use It |
|---------|------------------|----------------|
| Section 2 | Quick start paths by your current situation | You're not sure where to begin |
| Section 3 | Visual map of the entire system | You want to understand how everything connects |
| Section 4 | Topic-based navigation index | You have a specific topic in mind |
| Section 5 | Quick links to most-used content | You need something fast |
| Section 6 | Learning paths for each stage | You want a structured reading plan |
| Section 7 | "When to read what" master table | You want a complete reference |

---

## 2. QUICK START PATHS BY SITUATION

*Find your situation below. Follow the path exactly. Each path tells you what to read, in what order, and what to do.*

---

### PATH A: "I just got the pipeline. What do I do first?"

**Your situation:** Pipeline has been set up (or is being set up). You haven't built any apps yet.

```
PATH A — NEW OPERATOR
════════════════════════════════════════════════════════

Step 1: Verify setup is complete
  Read: NB1-4 (Implementation Notebooks, in order)
  Time: 1-2 days of setup work
  Goal: Pipeline running, responds to /status command

Step 2: Understand what you're about to do
  Read: NB5 Sections 1-2 (Overview + Prerequisites)
  Time: 45 minutes
  Goal: Clear picture of the 30-day journey ahead

Step 3: Validate your first app idea
  Action: Send /evaluate command (NB5 Section 2 walks you through this)
  Read: NB6 Scenario 1 if unsure how to evaluate
  Time: 1-2 hours

Step 4: Build your first app
  Read: NB5 Section 3 (Build Day) the morning of your build
  Time: 25-40 minutes pipeline + 2-3 hours preparation

Step 5: After the build — continue with NB5
  Read: NB5 Sections 4-6 as each week arrives
  Reference: RB4 when submitting to app stores
  Reference: RB2 if anything breaks

Total reading before first build: ~2 hours
Total time to first app live: 10-30 days (mostly app store review wait)
```

---

### PATH B: "Pipeline is running. I want to build my first app now."

**Your situation:** Setup is complete. Pipeline responds to commands. Ready to build.

```
PATH B — FIRST BUILD READY
════════════════════════════════════════════════════════

Tonight (30 minutes):
  Read: NB5 Sections 1-2
  Action: Validate your idea with /evaluate
  Goal: Confirmed idea ready to build tomorrow

Build day (morning, 20 minutes):
  Read: NB5 Section 3
  Action: Send /create command
  Monitor: Telegram notifications for S0-S7 stages
  If build fails: Open NB6 Scenario 2 immediately

Build day (while pipeline runs, 30-40 min):
  Read: NB5 Sections 4-5 (store submission prep)
  Action: Write your app description draft
  Action: Plan your 5 screenshots

Days 2-7:
  Reference: RB4 for step-by-step store submission
  Reference: RB1 Section 2 for Telegram commands reference

Day 14+:
  Read: NB5 Section 6 (getting first users)
  Reference: NB6 Scenario 8 if downloads aren't coming

Total active reading: 2-3 hours spread over first 2 weeks
```

---

### PATH C: "I have one app live. It's working. What now?"

**Your situation:** First app is in the stores with downloads and some revenue. Wondering what to focus on next.

```
PATH C — FIRST APP LIVE
════════════════════════════════════════════════════════

First: Optimize what you have (Week 1-2)
  Check: Is rating ≥ 4.0? If not → NB6 Scenarios 9 then 4
  Check: Are downloads growing? If not → NB6 Scenario 8
  Check: Are users staying? → NB6 Scenario 11
  Read: RB3 Section 1-2 to understand your costs

Then: Build operational habits (Week 3-4)
  Read: RB1 Sections 1-3 (daily operations, Telegram commands,
        execution modes)
  Action: Set up the 5-day weekly operations rhythm from RB1

Then: Prepare for App 2 (Month 2)
  Read: NB7 Sections 1-2 (portfolio strategy + when to scale)
  Action: Complete the App 2 Readiness Checklist (NB7 Section 2.1)

When App 2 readiness confirmed:
  Read: NB7 Sections 3-4 (operations + tiering)
  Build: App 2 following NB5 process
```

---

### PATH D: "Something broke / Something isn't working."

**Your situation:** An error occurred, build failed, app crashed, or something is behaving unexpectedly.

```
PATH D — TROUBLESHOOTING
════════════════════════════════════════════════════════

Step 1: Identify what type of problem (2 minutes)

  Build failed?
  → NB6 Scenario 2 (first) or RB2 Section 2

  App crashes after launch?
  → NB6 Scenario 4

  App store rejected my submission?
  → NB6 Scenario 7 or RB4 Section 6-7

  Pipeline not responding / slow / degraded?
  → RB2 Section 1 (pipeline health) then Section 3

  Cost is higher than expected?
  → NB6 Scenario 5 or RB3 Section 2-3

  Downloads stopped / very low?
  → NB6 Scenario 8 or 10

  Bad reviews accumulating?
  → NB6 Scenario 9

  Can't find the specific problem here?
  → Open RB2 and use its Section 1 diagnostic flowchart

Step 2: Apply the solution from the referenced section
Step 3: If unresolved after first fix attempt → RB2 Section 4
        (escalation procedures)
```

---

### PATH E: "I have multiple apps and feel overwhelmed."

**Your situation:** Managing 3+ apps. Feeling pulled in too many directions. Not sure what to prioritize.

```
PATH E — PORTFOLIO OVERWHELM
════════════════════════════════════════════════════════

Today (30 minutes):
  Read: NB6 Scenario 13 (Managing too many apps)
  Action: Complete the Portfolio Snapshot Table
  Action: Assign every app to a tier (Tier 1-4)

This week:
  Read: NB7 Section 3 (Weekly Operations Rhythm)
  Action: Block your calendar with the 5-day schedule
  Read: NB7 Section 4 (Tiering System complete)

This month:
  Read: NB7 Sections 5-6 (Cross-promotion + Resource optimization)
  Action: First Monthly Portfolio Review (NB7 Section 7.2)

Going forward:
  Reference: NB7 as your primary management guide
  Reference: NB6 Scenarios when specific apps need attention
```

---

### PATH F: "I want to understand my costs / reduce spending."

**Your situation:** Monthly pipeline costs feel high, or you want to optimize before they become a problem.

```
PATH F — COST OPTIMIZATION
════════════════════════════════════════════════════════

Step 1: Understand what you're spending (20 minutes)
  Command: /status costs --month [YYYY-MM]
  Read: RB3 Section 1 (understanding pipeline costs)

Step 2: Find the biggest waste sources (30 minutes)
  Read: NB6 Scenario 5 (builds too slow/expensive)
  Read: RB3 Section 2-3 (optimization strategies + mode selection)

Step 3: Apply specific optimizations
  Wrong execution mode: RB3 Section 3 + NB6 Scenario 5 Step 2
  Too many build cycles: NB6 Scenario 5 Step 3-4
  Infrastructure waste: RB3 Section 4-5

Step 4: Set up ongoing monitoring
  Read: RB3 Section 6 (budget planning + tracking)
  Action: Enable GCP billing alerts (RB3 Section 6.3)
```

---

### PATH G: "I'm ready to scale / treat this as a business."

**Your situation:** 1-3 apps generating consistent revenue. Ready to build a portfolio systematically.

```
PATH G — SCALING UP
════════════════════════════════════════════════════════

Foundation reading (3-4 hours, spread over a week):
  Read: NB7 in full (all 5 parts)
  Read: NB6 Scenarios 13-15 (if not already read)

Implementation (week 2):
  Action: Choose portfolio archetype (NB7 Section 1.3)
  Action: Build Specification Template Library (NB7 Section 6.2)
  Action: Set up Monthly Portfolio Review (NB7 Section 7.2)
  Action: Tier all existing apps (NB7 Section 4.3)

Ongoing references:
  RB1: Daily operations as portfolio grows
  RB3: Cost management at scale
  NB6: Scenario-specific fixes for individual apps
  NB0: Return here whenever you feel lost
```

---

### PATH H: "I want to update or improve a live app."

**Your situation:** App is live. You want to add a feature, fix a bug, or make improvements.

```
PATH H — UPDATING A LIVE APP
════════════════════════════════════════════════════════

For any update:
  Reference: RB6 Section 1-3 (update workflow)
  Key command: /modify [specification]
  Rule: Batch related changes into one /modify cycle

For bug fixes specifically:
  Diagnose: NB6 Scenario 4 (crashes) or RB2 Section 2-3
  Fix: /modify with specific bug fix specification

For feature additions:
  Validate the feature: /capability
  Reference: RB6 Section 4 (adding new features safely)
  Rule: Test on device before submitting to stores

For store listing updates only (no new build):
  Reference: RB4 Section 4 (ASO) and RB4 Section 6.1
  No /modify needed — update directly in App Store Connect
  or Play Console

For pipeline system updates (not your app — the pipeline itself):
  Reference: RB5 (complete)
```

---

*Part 1 Complete ✅ — Front Matter + How to Use + 8 Quick Start Paths*















---

# NB0: MASTER NAVIGATION GUIDE
## Part 2 of 4 — Complete Documentation Map + Topic-Based Navigation

---

## SECTION 3: COMPLETE DOCUMENTATION MAP

### 3.1 Document Profiles — What Each One Contains

Read this section once to build a mental model of the entire system. After this, you'll know immediately which document to open for any task.

---

**NB0 — MASTER NAVIGATION GUIDE** *(this document)*
```
Type:        Operator Notebook
Read when:   Feeling lost, new to the system, or looking for a topic
Length:      20-25 pages
Contents:    - Complete documentation system map
             - 8 quick-start paths by situation
             - Topic-based navigation index (where everything lives)
             - Learning paths for each stage
             - "When to read what" master table
Cross-refs:  Points to every other document — the hub of the system
```

---

**NB5 — FIRST 30 DAYS: SETUP TO FIRST PROFIT**
```
Type:        Operator Notebook
Read when:   Building your first app; before beginning the 30-day journey
Length:      ~60 pages (longest notebook)
Contents:    - Prerequisites checklist
             - Idea validation with /evaluate
             - Build day walkthrough (S0-S7 stages)
             - Store submission process
             - Getting first users
             - Iterating after launch
             - First revenue setup (RevenueCat)
Key terms:   Execution modes (LOCAL/HYBRID/CLOUD), build stages,
             TestFlight, App Store Connect, Play Console
Cross-refs:  → RB4 for detailed store submission steps
             → RB1 for daily operations after launch
             → NB6 Scenario 2 if build fails
             → NB6 Scenario 7 if store rejects app
```

---

**NB6 — REAL-WORLD SCENARIOS & SOLUTIONS**
```
Type:        Operator Notebook (scenario-based reference)
Read when:   Facing a specific problem; proactively before common issues
Length:      ~40 pages (15 scenarios)
Contents:
  Scenarios 1-3   Getting Started Issues
    1. Idea validation uncertainty
    2. First build failed
    3. Documentation overwhelm
  Scenarios 4-6   Building & Technical Issues
    4. App crashes after launch
    5. Builds too slow or expensive
    6. Pipeline can't build requested feature
  Scenarios 7-9   App Store & Launch Issues
    7. App store rejection
    8. Zero downloads after launch
    9. Negative reviews accumulating
  Scenarios 10-12 Growth & Optimization Issues
    10. Downloads stalled after early momentum
    11. Users not returning (poor retention)
    12. Competitor threat response
  Scenarios 13-15 Advanced Challenges
    13. Managing too many apps at once
    14. Pivot or persist decision
    15. Scaling to a real business
Structure:   Each scenario: SITUATION → SYMPTOMS → ROOT CAUSE
             → SOLUTION → PREVENTION → TIME TO FIX → CASE STUDY
Cross-refs:  → RB2 for systematic troubleshooting
             → RB1 for operational context
             → NB7 Scenarios 13-15 lead into portfolio management
```

---

**NB7 — APP PORTFOLIO MANAGEMENT**
```
Type:        Operator Notebook
Read when:   Before building your 3rd app; feeling overwhelmed at 5+
Length:      ~33 pages
Contents:
  Section 1: Overview and who this is for
  Section 2: Portfolio strategy — 3 archetypes
             (Niche Specialist / Category Diversifier / Feature Expander)
  Section 3: When to scale — readiness checklist, timelines
  Section 4: Multi-app operations — weekly rhythm, batch operations
  Section 5: App tiering system (Tier 1-4 with full criteria)
  Section 6: Cross-promotion and synergies (4 methods)
  Section 7: Resource optimization — template library, asset library
  Section 8: Portfolio analytics — monthly review, KPIs, ROI
  Section 9: Case studies — Maria (Niche Specialist 1→10 apps)
             and Jordan (Category Diversifier)
  Section 10: Sustainable growth paths — 3 phases, milestones
Cross-refs:  → NB6 Scenarios 13-15 (introduced here, detailed there)
             → RB1 for daily operational context
             → RB3 for cost management at scale
```

---

**RB1 — DAILY OPERATIONS & STANDARD WORKFLOWS**
```
Type:        Runbook
Read when:   Setting up your daily routine; looking up a specific command
Length:      Reference document
Contents:    - Morning and evening operations checklists
             - Complete Telegram command reference
             - Standard workflows (build, update, monitor)
             - Execution mode selection guide
             - Build stage reference (S0-S7 explanations)
             - Weekly and monthly operations schedules
Key sections for common needs:
  "What command do I use for X?"     → Section 2 (command reference)
  "What mode should I use?"          → Section 3 (execution modes)
  "What does this stage mean?"       → Section 4 (build stages)
  "How do I check status?"           → Section 1 or Section 2
  "What should I do each day?"       → Section 5 (daily schedule)
Cross-refs:  → NB5 for context behind operations
             → RB2 when operations reveal a problem
             → RB3 for cost context behind mode selection
```

---

**RB2 — TROUBLESHOOTING & PROBLEM RESOLUTION**
```
Type:        Runbook
Read when:   Something is broken, not working, or behaving unexpectedly
Length:      Reference document
Contents:    - Pipeline health diagnostic flowchart
             - Build failure diagnosis (by stage: S0-S7)
             - App-side problem diagnosis
             - Store and account issues
             - Escalation procedures
             - Recovery checklists
Key sections for common needs:
  "Pipeline not responding"          → Section 1 (health check)
  "Build failed at stage X"          → Section 2 (by stage)
  "App crashes on device"            → Section 3
  "Store rejected / account issue"   → Section 4
  "Nothing in RB2 fixes it"          → Section 5 (escalation)
Cross-refs:  → NB6 Scenarios 2, 4, 7 for operator-friendly versions
             → RB1 for operational context
             → RB5 if pipeline system itself needs updating
```

---

**RB3 — COST CONTROL & SYSTEM MAINTENANCE**
```
Type:        Runbook
Read when:   Costs feel high; planning a budget; setting up monitoring
Length:      Reference document
Contents:    - Cost structure explanation (per build, per service)
             - Execution mode cost table
             - Optimization strategies (batching, mode selection)
             - Infrastructure cost management (GCP, APIs)
             - Budget planning templates
             - Billing alert setup
             - Monthly cost review process
Key sections for common needs:
  "What does each build cost?"       → Section 1
  "How to reduce costs now"          → Section 3
  "Set up budget alerts"             → Section 6
  "Why is this month expensive?"     → Section 2 (waste patterns)
Cross-refs:  → NB6 Scenario 5 for operator-friendly optimization
             → RB1 for execution mode context
```

---

**RB4 — APP STORE & GOOGLE PLAY DELIVERY**
```
Type:        Runbook
Read when:   Submitting an app; handling rejection; updating store listings
Length:      Reference document
Contents:    - App Store Connect setup and navigation
             - Google Play Console setup and navigation
             - Build upload process (iOS and Android)
             - Metadata requirements (screenshots, descriptions)
             - ASO (App Store Optimization) fundamentals
             - Rejection handling by rejection type
             - Review waiting period guidance
             - In-app purchase setup
Key sections for common needs:
  "How to submit to Apple"           → Section 2-3
  "How to submit to Google"          → Section 4-5
  "What screenshots do I need?"      → Section 6 (metadata)
  "How to write a good description"  → Section 6 (ASO)
  "My app was rejected"              → Section 7 (rejections)
  "Set up subscriptions/IAP"         → Section 8
Cross-refs:  → NB5 Sections 4-5 for first-time context
             → NB6 Scenario 7 for rejection decision trees
             → RB6 for updating an existing listing
```

---

**RB5 — UPDATING AI FACTORY PIPELINE SYSTEM**
```
Type:        Runbook
Read when:   Pipeline itself needs updating (not your apps — the pipeline)
Length:      Reference document
Contents:    - Pipeline version checking
             - Update procedures (minor and major)
             - Pre-update backup process
             - Post-update verification
             - Rollback procedures if update fails
Key sections for common needs:
  "How to check pipeline version"    → Section 1
  "How to update the pipeline"       → Section 2-3
  "Update broke something"           → Section 5 (rollback)
Note:        This runbook is rarely needed. Most operators use it 
             once every few months. If you're reading it frequently,
             something else is wrong — check RB2 first.
Cross-refs:  → RB2 if update reveals underlying problems
```

---

**RB6 — UPDATING & PATCHING EXISTING PROJECTS**
```
Type:        Runbook
Read when:   Updating a live app (new features, bug fixes, content changes)
Length:      Reference document
Contents:    - /modify command reference and best practices
             - Safe update workflow (test → build → review → submit)
             - Batching multiple changes into one /modify cycle
             - Version numbering conventions
             - Testing on device before store submission
             - What requires a new build vs. metadata-only update
             - Rollback procedures for live app updates
Key sections for common needs:
  "How to add a feature"             → Section 3-4
  "How to fix a specific bug"        → Section 2 (bug fix workflow)
  "Can I update just the description?"→ Section 6 (metadata-only)
  "How to batch multiple fixes"      → Section 3 (batching guide)
  "Update broke the app"             → Section 7 (rollback)
Cross-refs:  → NB6 Scenario 4 for crash diagnosis before fixing
             → RB4 for re-submitting after update
             → RB2 if update process itself fails
```

---

### 3.2 Document Relationship Map

This diagram shows how the documents relate to and reference each other:

```
DOCUMENT RELATIONSHIP MAP
════════════════════════════════════════════════════════

                    ┌─────────┐
                    │   NB0   │ ← You are here
                    │  (This) │   Points to everything
                    └────┬────┘
                         │
           ┌─────────────┼─────────────┐
           │             │             │
    ┌──────▼──────┐ ┌───▼───┐  ┌──────▼──────┐
    │ SETUP PATH  │ │OPERATE│  │  GROW PATH  │
    │  NB1→NB4   │ │  PATH │  │  NB6→NB7   │
    │(Install)    │ │       │  │(Scale)      │
    └─────────────┘ │  NB5  │  └──────┬──────┘
                    │(Build)│         │
                    └───┬───┘         │
                        │             │
             ┌──────────┴─────────────┘
             │
    ┌─────────▼──────────────────────────────────┐
    │            RUNBOOKS (reference layer)       │
    │                                             │
    │  RB1         RB2         RB3                │
    │  Daily       Trouble-    Cost               │
    │  Operations  shooting    Control            │
    │                                             │
    │  RB4         RB5         RB6                │
    │  App Store   Pipeline    Update             │
    │  Delivery    Updates     Projects           │
    └─────────────────────────────────────────────┘

Reading flow for new operators:
  NB1-4 → NB5 → (build first app) → RB1 for daily ops
  → NB6 when problems arise → NB7 when scaling

Reading flow for experienced operators:
  NB7 → NB6 (scenario-specific) → RBs (task-specific)
  → NB0 when lost
```

### 3.3 Content Volume at a Glance

```
DOCUMENT SIZE REFERENCE
════════════════════════════════════════════════════════

Document        Est. Pages    Reading Time
──────────────────────────────────────────────────────
NB0 (this)      20-25 pages   1.5-2 hours (read once)
NB5             ~60 pages     3-4 hours (read in stages)
NB6             ~40 pages     2-3 hours (reference by scenario)
NB7             ~33 pages     2-3 hours (read before App 3)

RB1             Reference     Look up as needed
RB2             Reference     Look up when troubleshooting
RB3             Reference     Look up for costs
RB4             Reference     Look up for store submissions
RB5             Reference     Rarely needed
RB6             Reference     Look up when updating apps

Total readable content: ~155 pages
Time to read relevant content at any given stage: 3-5 hours
Time to read everything: 10-15 hours (not recommended all at once)
```

---

## SECTION 4: TOPIC-BASED NAVIGATION INDEX

*Find your topic alphabetically. Each entry tells you exactly where to go.*

---

### A

**Account setup — Apple Developer**
→ NB5 Section 2.2 (prerequisites) | RB4 Section 1 (detailed setup)

**Account setup — Google Play**
→ NB5 Section 2.2 | RB4 Section 4 (detailed setup)

**Analytics — checking app metrics**
→ RB1 Section 5 (daily analytics check) | Command: `/status analytics`

**Analytics — portfolio-level**
→ NB7 Section 7 (full portfolio analytics + KPI dashboard)

**App crashes — diagnosing**
→ NB6 Scenario 4 | RB2 Section 3

**App crashes — fixing**
→ NB6 Scenario 4 Solution Steps 1-4 | RB6 Section 2 (bug fix workflow)

**App idea validation**
→ NB6 Scenario 1 | NB5 Section 3 | Command: `/evaluate`

**App icon — requirements**
→ RB4 Section 6 (metadata requirements)

**App retirement — when and how**
→ NB7 Section 4.5 | NB6 Scenario 13 Step 4

**App store rejection — handling**
→ NB6 Scenario 7 | RB4 Section 7

**App Store Connect — navigation**
→ RB4 Section 2-3

**ASO (App Store Optimization)**
→ NB6 Scenario 8 (keywords + descriptions) | RB4 Section 6

**Archetype — choosing portfolio type**
→ NB7 Section 1.2-1.3

### B

**Bad reviews — responding to**
→ NB6 Scenario 9

**Billing alerts — setting up**
→ RB3 Section 6.3

**Build costs — understanding**
→ RB3 Section 1 | NB6 Scenario 5

**Build failure — diagnosing**
→ NB6 Scenario 2 | RB2 Section 2

**Build modes — choosing**
→ RB1 Section 3 | NB6 Scenario 5 Step 2 | NB5 Section 2.1

**Build stages (S0-S7) — reference**
→ RB1 Section 4 | NB5 Section 3

**Builds — batching changes**
→ RB6 Section 3 | NB6 Scenario 5 Step 4

### C

**Capability check — can pipeline build X?**
→ Command: `/capability` | NB6 Scenario 6

**Competitor threat — responding**
→ NB6 Scenario 12

**Conversion rate — improving (store listing)**
→ NB6 Scenario 8 Steps 3-4 | RB4 Section 6

**Cost control — general**
→ NB6 Scenario 5 | RB3 (full runbook)

**Cost per build — reference**
→ RB3 Section 1 | NB7 Section 10.4

**Crash reporting — setting up**
→ NB6 Scenario 4 Step 3 (Sentry setup)

**Cross-promotion — setting up**
→ NB7 Section 5 (all 4 methods)

### D

**Daily operations schedule**
→ RB1 Section 5 | NB7 Section 3.2 (portfolio weekly rhythm)

**Description — writing for app store**
→ NB6 Scenario 8 Step 3 | RB4 Section 6

**Developer profile — managing**
→ RB4 Section 1 | NB7 Section 5.3 Method 1

**Downloads — increasing**
→ NB6 Scenarios 8, 10 | NB5 Section 6

**Downloads — stalled after early growth**
→ NB6 Scenario 10

### E

**Evaluation — app idea**
→ Command: `/evaluate` | NB6 Scenario 1 | NB5 Section 3

**Execution modes — choosing**
→ RB1 Section 3 | NB6 Scenario 5 | NB7 Section 10.4

### F

**Feature additions — to live apps**
→ RB6 Section 3-4 | Command: `/modify`

**Feature parity with competitor**
→ NB6 Scenario 12

**First app — building**
→ NB5 (full notebook) | Path B in NB0 Section 2

**First win — designing for new users**
→ NB6 Scenario 11 Step 1-2

### G

**GCP — cost management**
→ RB3 Section 4-5

**Google Play Console — navigation**
→ RB4 Section 4-5

**Growth — stalled downloads**
→ NB6 Scenario 10

**Growth phases — portfolio**
→ NB7 Section 9.2

### H

**Health check — pipeline**
→ Command: `/status` | RB2 Section 1

**HYBRID mode — when to use**
→ RB1 Section 3 | NB6 Scenario 5

### I

**IAP (In-App Purchase) — setting up**
→ RB4 Section 8 | NB5 Section 5

**Icon — app icon requirements**
→ RB4 Section 6

**Idea validation**
→ Command: `/evaluate` | NB6 Scenario 1 | NB5 Section 3

**Income milestones — roadmap**
→ NB7 Section 9.3

### K

**Keywords — research and optimization**
→ NB6 Scenario 8 Step 2 | NB6 Scenario 10 Step 1-2 | RB4 Section 6

**KPIs — portfolio-level**
→ NB7 Section 7.3

### L

**Launch — first app**
→ NB5 Sections 4-6 | RB4 (store submission)

**LOCAL mode — when to use**
→ RB1 Section 3 | NB6 Scenario 5

**Logs — reading crash logs**
→ NB6 Scenario 4 Step 2

### M

**Maintenance schedule — apps**
→ NB7 Section 3 (weekly rhythm) | RB1 Section 5

**Monetization — setting up**
→ NB5 Section 5 | RB4 Section 8

**Monetization — choosing model**
→ NB7 Section 1.4 Principle 2

**Monthly portfolio review**
→ NB7 Section 7.2 (complete template)

**/modify command — usage**
→ RB6 Section 1-3 | RB1 Section 2

### N

**New app — deciding whether to build**
→ NB6 Scenario 1 | NB7 Section 7.5

**Notifications — in-app setup**
→ NB6 Scenario 11 Step 3

**Notifications — push, re-engagement**
→ NB6 Scenario 11 Step 3

### O

**Onboarding — improving for new users**
→ NB6 Scenario 11 Step 2

**Operations — daily**
→ RB1 | NB7 Section 3 (portfolio level)

### P

**Paywall — placement and conversion**
→ NB6 Scenario 11 Step 4

**Pipeline — checking health**
→ Command: `/status` | RB2 Section 1

**Pipeline — updating the system**
→ RB5 (full runbook)

**Pivot or persist — decision**
→ NB6 Scenario 14

**Platform selection — iOS vs Android**
→ NB7 Section 1.4 Principle 1 | NB5 Section 2.1

**Portfolio archetype — choosing**
→ NB7 Section 1.2-1.3

**Portfolio analytics**
→ NB7 Section 7

**Portfolio management — overview**
→ NB7 (full notebook) | NB6 Scenario 13

**Privacy policy — setup**
→ NB5 Section 4 | RB4 Section 6

**Premium conversion — improving**
→ NB6 Scenario 11 Step 4

### R

**Rating — improving**
→ NB6 Scenario 9 Steps 1-5

**Rejection — app store**
→ NB6 Scenario 7 | RB4 Section 7

**Retention — improving**
→ NB6 Scenario 11

**Revenue — first**
→ NB5 Sections 5-6

**Revenue — stalled**
→ NB6 Scenarios 10-11 | NB7 Section 7.5

**Review responses — writing**
→ NB6 Scenario 9 Step 2

**Review velocity — improving**
→ NB6 Scenario 9 Step 3 | NB6 Scenario 10 Step 3

**RevenueCat — setup**
→ NB5 Section 5

**ROI per app — calculating**
→ NB7 Section 7.4

**Rollback — app update**
→ RB6 Section 7

**Rollback — pipeline update**
→ RB5 Section 5

### S

**Scaling — from single app to portfolio**
→ NB7 Sections 2-3 | NB6 Scenario 15

**Screenshots — creating**
→ NB6 Scenario 8 Step 3 | RB4 Section 6

**Sentry — crash reporting setup**
→ NB6 Scenario 4 Step 3

**Specification — writing**
→ NB5 Section 3 | NB7 Section 6.2 (templates)

**Stage failures (S0-S7)**
→ NB6 Scenario 2 | RB2 Section 2

**/status command**
→ RB1 Section 2 | Command reference

**Store listing — writing**
→ NB6 Scenario 8 | RB4 Section 6

**Subscription setup**
→ NB5 Section 5 | RB4 Section 8

**Sunset — retiring an app**
→ NB7 Section 4.5

### T

**Telegram commands — complete reference**
→ RB1 Section 2

**Template library — specification**
→ NB7 Section 6.2

**TestFlight — using**
→ NB5 Section 3 | RB4 Section 3

**Tiering — assigning apps to tiers**
→ NB7 Section 4 | NB6 Scenario 13 Step 2

**Troubleshooting — general**
→ RB2 (full runbook) | NB6 (scenario-specific)

### U

**Update — pipeline system**
→ RB5

**Update — live app**
→ RB6 | Command: `/modify`

**User acquisition — first users**
→ NB5 Section 6 | NB6 Scenario 8

### V

**Validation — app idea**
→ Command: `/evaluate` | NB6 Scenario 1

**Version numbering**
→ RB6 Section 5

### W

**Weekly operations schedule**
→ NB7 Section 3.2 | RB1 Section 5

---

*Part 2 Complete ✅ — Complete Documentation Map + Topic-Based Navigation Index*















---

# NB0: MASTER NAVIGATION GUIDE
## Part 3 of 4 — Reference Quick Links + Learning Paths by Stage

---

## SECTION 5: REFERENCE QUICK LINKS

*The most frequently needed sections across the entire documentation system. Bookmark or memorize these — they cover 80% of daily lookups.*

---

### 5.1 Commands — Fast Reference

```
COMPLETE PIPELINE COMMAND REFERENCE
════════════════════════════════════════════════════════

EVALUATION & PLANNING:
  /evaluate                     Validate app idea before building
  /capability                   Check if pipeline can build a feature
  /status                       Check pipeline health (overall)
  /status --all-projects        Check all apps at once

BUILD COMMANDS:
  /create [spec]                Build a new app from specification
  /modify [changes]             Update or fix an existing app

MONITORING:
  /status builds --last 30 days    Recent build history
  /status costs --month YYYY-MM    Monthly pipeline costs
  /status analytics --project [name] --metric [type]
    Metric options: retention, downloads, revenue, screen-flow

CONFIGURATION:
  /configure service            Set up external service credentials

FULL REFERENCE: RB1 Section 2
```

---

### 5.2 Build Costs — Fast Reference

```
COST PER BUILD (quick lookup)
════════════════════════════════════════════════════════

LOCAL mode:   $0.00  — Android, Web (all scenarios)
HYBRID mode:  $0.20  — Android, Web, iOS updates
CLOUD mode:   $1.20  — iOS new app first build

When to use each:
  Experimenting / testing: LOCAL always
  Android new app:         LOCAL or HYBRID
  Android update:          LOCAL or HYBRID
  iOS new app (v1):        CLOUD
  iOS update / fix:        HYBRID

Annual fixed costs:
  Apple Developer account: $99/year ($8.25/month)
  Google Play account:     $25 one-time

Revenue share:
  Apple:  15% (under $1M/year)
  Google: 15% (first $1M/year)

FULL REFERENCE: RB3 Section 1 | NB6 Scenario 5 | NB7 Section 10.4
```

---

### 5.3 Build Stages — Fast Reference

```
BUILD STAGES S0-S7 (what the pipeline is doing)
════════════════════════════════════════════════════════

S0: Planning       Reading spec, creating build plan
S1: Design         UI/UX layout generation
S2: Code Gen       Writing application code
S3: Testing        Automated test suite
S4: Build          Compiling the app file (.ipa or .apk/.aab)
S5: QA             Quality checks and linting
S6: Deployment     Packaging for distribution
S7: Monitoring     Setting up crash reporting and analytics

Normal build time: 25-40 minutes (S0 through S7)
If stuck at a stage for > 15 minutes: Check RB2 Section 2

FULL REFERENCE: RB1 Section 4 | NB6 Scenario 2
```

---

### 5.4 Rejection Types — Fast Reference

```
APP STORE REJECTION QUICK RESPONSE
════════════════════════════════════════════════════════

Metadata rejection (screenshots, description, privacy URL):
  Fix directly in App Store Connect / Play Console
  No new build needed
  Re-review: 1-3 days
  → RB4 Section 6

Build/technical rejection (crashes, broken features):
  Run /modify with specific fix
  Submit new build
  Re-review: 1-3 days
  → NB6 Scenario 7 Tier 2 | RB6 Section 2

Policy rejection (payment, data, permissions):
  Implement required system via /modify
  May require 1-2 build cycles
  Re-review: 2-7 days
  → NB6 Scenario 7 Tier 3 | RB4 Section 7

Fundamental rejection (guideline violation, insufficient function):
  Read guidelines carefully, appeal or redesign
  Timeline: 1-4 weeks
  → NB6 Scenario 7 Tier 4

Apple review times: 1-3 days (median ~24 hours)
Google review times: 1-7 days (new apps), 1-3 days (updates)

FULL REFERENCE: NB6 Scenario 7 | RB4 Section 7
```

---

### 5.5 Tiering — Fast Reference

```
APP TIER ASSIGNMENT (quick lookup)
════════════════════════════════════════════════════════

TIER 1 (Star Performers):
  Revenue > $150/month + rating ≥ 4.2 + growing
  Time: 40-50% of your total pipeline time
  Updates: Every 4-6 weeks with new features

TIER 2 (Stable Earners):
  Revenue $30-150/month, stable
  Time: 30-35% of total pipeline time
  Updates: Every 6-8 weeks, fixes + small improvements

TIER 3 (Recovery Candidates):
  Revenue < $30/month, app < 4 months old or rating ≥ 4.0
  Time: 15% of total, one intervention, 60-day window
  Updates: One strategic intervention only

TIER 4 (Sunset Candidates):
  Revenue < $15/month for 3+ months OR rating < 3.0
  Time: 5-10%, critical fixes only
  Updates: None; evaluate for retirement monthly

Re-tier: Monthly (check) + Quarterly (full re-tier)

FULL REFERENCE: NB7 Section 4 | NB6 Scenario 13
```

---

### 5.6 Weekly Operations Schedule — Fast Reference

```
WEEKLY PORTFOLIO RHYTHM (quick lookup)
════════════════════════════════════════════════════════

Monday (45-60 min):
  /status --all-projects + metrics check + all negative reviews

Tuesday (1.5-2 hrs):
  Tier 1 app work — new features, improvements

Wednesday (1.5-2 hrs):
  New app build OR Tier 1 deep work

Thursday (1 hr):
  Tier 2 batch maintenance + Tier 3/4 decisions

Friday (30-45 min):
  Costs + planning + positive review responses

Total: 5-7 hours/week for 6-10 apps

FULL REFERENCE: NB7 Section 3.2 | RB1 Section 5
```

---

### 5.7 Execution Mode Decision — Fast Reference

```
WHICH MODE SHOULD I USE? (quick lookup)
════════════════════════════════════════════════════════

Question 1: What platform?
  Android or Web → LOCAL ($0) or HYBRID ($0.20)
  iOS → Go to Question 2

Question 2: Is this a new iOS app (first build)?
  Yes → CLOUD ($1.20)
  No (update/fix to existing iOS app) → HYBRID ($0.20)

Question 3: Am I just experimenting?
  Yes → LOCAL always, regardless of platform

One-line rule:
  LOCAL for Android/Web, CLOUD for iOS first build,
  HYBRID for iOS updates, LOCAL for experiments.

FULL REFERENCE: RB1 Section 3 | NB6 Scenario 5 Step 2
```

---

### 5.8 Retention Benchmarks — Fast Reference

```
RETENTION THRESHOLDS (quick lookup)
════════════════════════════════════════════════════════

Day 1 retention (users who return day 2):
  Below 20%: Critical — fix first win experience
  20-40%:    Acceptable — improve in parallel with growth
  Above 40%: Strong — invest in growth confidently

Day 7 retention (return within 7 days):
  Below 10%: Retention is priority before any marketing
  10-20%:    Average — improve while growing
  Above 20%: Good — growth investment will compound

Day 30 retention:
  Below 8%:  Review monetization and core value loop
  8-15%:     Average
  Above 15%: Strong

Where to check:
  Apple: App Store Connect → Analytics → Retention
  Google: Play Console → Android Vitals → User Retention
  Pipeline: /status analytics --project [name] --metric retention

FULL REFERENCE: NB6 Scenario 11
```

---

### 5.9 Most-Used Cross-References

*The links operators look up most often — what document covers what adjacent topic.*

```
MOST-USED CROSS-REFERENCES
════════════════════════════════════════════════════════

"Build failed" covered in:
  First-time operator context:  NB6 Scenario 2
  Technical diagnosis:          RB2 Section 2
  By stage (S0-S7):            RB2 Section 2.1-2.8

"App store submission" covered in:
  First-time walkthrough:       NB5 Sections 4-5
  Step-by-step Apple:          RB4 Section 2-3
  Step-by-step Google:         RB4 Section 4-5
  Rejection handling:          NB6 Scenario 7 + RB4 Section 7

"Downloads are low" covered in:
  From zero:                   NB6 Scenario 8
  After early stall:           NB6 Scenario 10
  Keyword optimization:        NB6 Scenario 8 Step 2 + RB4 Section 6

"Portfolio overwhelmed" covered in:
  Quick triage:                NB6 Scenario 13
  Full management system:      NB7 Sections 3-4
  Weekly rhythm:               NB7 Section 3.2

"Costs too high" covered in:
  Operator context:            NB6 Scenario 5
  Technical optimization:      RB3 Sections 2-5
  Mode selection:              RB1 Section 3

"Update a live app" covered in:
  Feature additions:           RB6 Sections 3-4
  Bug fixes:                   RB6 Section 2 + NB6 Scenario 4
  Listing-only updates:        RB6 Section 6 + RB4 Section 4
```

---

## SECTION 6: LEARNING PATHS BY STAGE

*A structured reading plan matched to where you are. Follow your path. Skip what doesn't apply yet.*

---

### 6.1 Path: New Operator (Zero Apps)

**Goal:** Get from no apps to first app live, with confidence.

**Total reading time:** ~5-7 hours (spread over 2-4 weeks)
**Total calendar time:** 2-6 weeks (including app store review wait)

```
NEW OPERATOR READING PATH
════════════════════════════════════════════════════════

WEEK 0 — BEFORE YOU BUILD:
Required reading:
  □ NB0 Sections 1-2 (this document, the first two sections)
     Time: 45 minutes
     Why: Understand how the system works so you're oriented

  □ NB5 Sections 1-2 (prerequisites + overview)
     Time: 45 minutes
     Why: Know what the 30-day journey looks like

  □ NB6 Scenario 1 (idea validation)
     Time: 20 minutes
     Why: Validate your idea before spending pipeline time

Action: Run /evaluate on your idea. Score must be ≥ 6 to proceed.

WEEK 1 — BUILD WEEK:
Read the morning of your build:
  □ NB5 Section 3 (build day walkthrough)
     Time: 30 minutes
     Why: Walk beside the build as it happens

During the build (pipeline runs 25-40 min):
  □ NB5 Section 4 (store submission prep)
     Time: 30 minutes
     Why: Prepare while waiting

If build fails:
  □ NB6 Scenario 2 immediately
     Time: 20 minutes
     Why: Diagnosis + fix

After successful build:
  □ RB4 Sections 2-5 (store submission walkthrough)
     Time: Reference as needed during submission

WEEK 2 — SUBMISSION AND WAITING:
While in review (1-7 days):
  □ NB5 Section 5 (getting first users)
     Time: 30 minutes
     Why: Plan your launch before the app goes live

  □ NB6 Scenario 8 Sections 1-3 (ASO basics)
     Time: 30 minutes
     Why: Optimize your listing while waiting

WEEK 3-4 — POST-LAUNCH:
After app goes live:
  □ RB1 Sections 1-3 (daily operations basics)
     Time: 45 minutes (read once, reference after)
     Why: Establish healthy habits from day one

  □ NB6 Scenario 9 (handling reviews) proactively
     Time: 20 minutes
     Why: Be prepared for feedback before it arrives

If downloads are low after 2 weeks:
  □ NB6 Scenario 8 (full scenario)
  
If app has crashes or bad reviews:
  □ NB6 Scenarios 4 and 9

TOTAL FOR NEW OPERATOR PATH:
  Required reading: ~3.5 hours
  Situational reading: ~1-2 hours additional
  Reference lookups: As needed (RB documents)
```

---

### 6.2 Path: Active Builder (1-2 Apps, Growing)

**Goal:** Optimize existing apps, prepare for portfolio growth, build efficient habits.

**Total reading time:** ~4-5 hours
**Focus:** Improvement + preparation for scaling

```
ACTIVE BUILDER READING PATH
════════════════════════════════════════════════════════

IMMEDIATELY (if not already read):
  □ RB1 Sections 1-5 (daily operations complete)
     Time: 1 hour
     Why: Operational foundation for everything that follows

  □ NB6 Scenarios 8-11 (growth fundamentals)
     Time: 1.5 hours
     Why: These four scenarios cover the core post-launch
          optimization work: downloads, store presence,
          reviews, and retention

WHEN YOUR FIRST APP IS STABLE (rating ≥ 4.0, downloads consistent):
  □ NB7 Sections 1-3 (portfolio strategy + when to scale)
     Time: 1 hour
     Why: Plan before you build App 2

  □ NB7 Section 4 (tiering system)
     Time: 45 minutes
     Why: Set up tiering from App 2, not App 5

ONGOING REFERENCES (look up as needed):
  □ NB6 remaining scenarios (reference when the situation arises)
  □ RB3 Sections 1-3 (cost optimization when costs feel high)
  □ RB4 when submitting updates or new apps
  □ RB6 when updating live apps

WHEN BUILDING APP 2:
  Repeat the New Operator build-week process (NB5 Section 3)
  Use your specification template (NB7 Section 6.2)
  Apply 30-60-90 Transition Schedule (NB7 Section 2.3)
```

---

### 6.3 Path: Portfolio Operator (3-8 Apps)

**Goal:** Operate efficiently, grow systematically, avoid burnout.

**Total reading time:** ~4-5 hours (mostly NB7)
**Focus:** Systems + scale

```
PORTFOLIO OPERATOR READING PATH
════════════════════════════════════════════════════════

FOUNDATION (read before anything else if not done):
  □ NB6 Scenario 13 (portfolio overwhelm triage)
     Time: 30 minutes
     Action: Complete Portfolio Snapshot Table immediately after

  □ NB7 Sections 3-5 (operations + tiering + cross-promotion)
     Time: 2 hours
     Action: Implement weekly rhythm + tier all apps

OPTIMIZATION:
  □ NB7 Sections 6-7 (resource optimization + analytics)
     Time: 1.5 hours
     Action: Build spec template library + start monthly review

  □ NB6 Scenarios applicable to your current apps
     (Use Section 2 Scenario Index to find relevant ones)

STRATEGIC:
  □ NB7 Sections 8-9 (case studies + growth paths)
     Time: 1 hour
     Why: See the full arc; calibrate expectations

ONGOING:
  □ Monthly: NB7 Section 7.2 (portfolio review template)
  □ Quarterly: NB7 Section 4.4 (re-tier all apps)
  □ As needed: NB6 scenarios for individual app issues
  □ As needed: RB documents for specific tasks
```

---

### 6.4 Path: Experienced Operator (8+ Apps, Scaling)

**Goal:** Maximize portfolio efficiency, scale revenue, potentially professionalize.

**Total reading time:** ~2-3 hours (most foundational reading already done)
**Focus:** Optimization + strategic decision-making

```
EXPERIENCED OPERATOR READING PATH
════════════════════════════════════════════════════════

STRATEGIC REVIEW:
  □ NB7 Section 9 (sustainable growth paths + milestones)
     Time: 45 minutes
     Why: Calibrate your phase and set appropriate goals

  □ NB7 Section 7 (portfolio analytics — in depth)
     Time: 45 minutes
     Action: Calculate ROI per app; identify where time is 
             over- or under-invested

OPTIMIZATION:
  □ NB7 Section 6.4-6.6 (efficiency benchmarks + 80/20 rule)
     Time: 30 minutes
     Action: Compare your time-per-app to benchmarks

  □ NB6 Scenario 15 (treating this as a business)
     Time: 30 minutes
     Action: Build Business Baseline Snapshot

ONGOING SYSTEM MAINTENANCE:
  □ Monthly: NB7 Section 7.2 (portfolio review)
  □ Quarterly: NB7 Section 7.6 (portfolio rebalancing)
  □ Quarterly: NB7 Section 4.4 (tier re-assignment)
  □ As needed: NB6 (scenario-specific app issues)
  □ Annually: NB7 Section 1.4 (revisit composition principles)

NEW CAPABILITIES AT THIS STAGE:
  □ Consider VA for review responses (NB7 Section 9.2 Phase 3)
  □ Consider small paid promotion for proven Tier 1 apps
  □ Consider public developer brand (Indie Hackers, YouTube)
```

---

### 6.5 Path: Troubleshooter (Something is Wrong)

**Goal:** Diagnose and fix the specific problem as quickly as possible.

**Total reading time:** 10-30 minutes (targeted, not broad)

```
TROUBLESHOOTER READING PATH
════════════════════════════════════════════════════════

STEP 1: Identify the problem type (2 minutes)
  Pipeline issue:     → RB2 Section 1 (health diagnostic)
  Build issue:        → NB6 Scenario 2 or RB2 Section 2
  App crash:          → NB6 Scenario 4
  Store rejection:    → NB6 Scenario 7 or RB4 Section 7
  Downloads problem:  → NB6 Scenario 8 or 10
  Reviews problem:    → NB6 Scenario 9
  Cost issue:         → NB6 Scenario 5 or RB3 Section 2
  Portfolio problem:  → NB6 Scenario 13 or NB7 Section 3-4
  Competitor:         → NB6 Scenario 12
  Pivot decision:     → NB6 Scenario 14

STEP 2: Read only the relevant section (10-20 minutes)
  Each scenario has: SYMPTOMS → ROOT CAUSE → SOLUTION
  Start at SYMPTOMS to confirm you have the right scenario
  Jump to SOLUTION if you're sure of the problem
  Read ROOT CAUSE if the solution isn't working as expected

STEP 3: If not resolved (5 minutes)
  All pipeline issues:     → RB2 Section 4 (escalation)
  All app-side issues:     → RB2 Section 3 (general diagnosis)
  All store issues:        → RB4 Section 7 + Apple/Google support
  All cost issues:         → RB3 Section 5 (infrastructure review)

RULE: Read only what you need. Don't read surrounding
sections "just in case" — it slows you down and
the answer is in the specific section.
```

---

### 6.6 Situational Reading — By Month of Your Journey

For operators who like a calendar-based view:

```
WHAT TO READ WHEN (timeline view)
════════════════════════════════════════════════════════

Month 0 (Setup):
  NB1-4 (implementation)
  NB0 Sections 1-2 (orientation)

Month 1 (First Build):
  NB5 (complete, section by section as each week arrives)
  RB4 (reference during store submissions)
  NB6 Scenario 7 if rejected
  NB6 Scenario 2 if build fails

Month 2 (Optimizing App 1):
  RB1 (set up daily operations)
  NB6 Scenarios 8-9 (downloads + reviews)
  NB6 Scenario 11 (retention)
  RB3 Sections 1-3 (understand and optimize costs)

Month 3 (Preparing for App 2):
  NB7 Sections 1-3 (portfolio strategy + readiness)
  NB6 Scenario 13 (get ahead of portfolio management)

Month 4-6 (App 2 and 3):
  NB7 Sections 3-5 (operations + tiering + cross-promotion)
  NB7 Section 6.2 (build specification template library)
  NB6 Scenarios as needed for each app

Month 7-12 (Active portfolio building):
  NB7 Sections 6-8 (resource optimization + analytics + case studies)
  Monthly: NB7 Section 7.2 (portfolio review)
  NB6 Scenarios as individual app issues arise

Year 2+ (Optimizing and scaling):
  NB7 Section 9 (sustainable growth paths)
  NB6 Scenario 15 (scaling to a business)
  NB7 Section 7.6 (quarterly portfolio rebalancing)
  Quarterly: Full portfolio re-tier (NB7 Section 4.4)
```

---

*Part 3 Complete ✅ — Reference Quick Links + Learning Paths by Stage*















---

# NB0: MASTER NAVIGATION GUIDE
## Part 4 of 4 — When to Read What + Quick Reference + Summary

---

## SECTION 7: WHEN TO READ WHAT — MASTER TABLE

*The complete reference. Every document, every situation, every trigger. Use this when you're not sure which path from Section 2 applies.*

---

### 7.1 Trigger-Based Reading Guide

Find your trigger in the left column. The right column tells you exactly what to open.

```
TRIGGER → DOCUMENT (Master Table)
════════════════════════════════════════════════════════

SETUP & FIRST BUILD
──────────────────────────────────────────────────────
"I just got the pipeline"                   → NB0 Sections 1-2, then NB1-4
"About to build my first app"              → NB5 Sections 1-3
"Not sure if my idea is good"              → NB6 Scenario 1
"Pipeline isn't responding to /status"     → RB2 Section 1
"Build failed at S[0-7]"                   → NB6 Scenario 2 | RB2 Section 2
"Build succeeded, need to submit"          → NB5 Sections 4-5 | RB4
"Don't know what execution mode to use"   → RB1 Section 3 | Section 5.7 (this doc)

APP STORE & LAUNCH
──────────────────────────────────────────────────────
"Submitting to Apple App Store"            → RB4 Sections 2-3
"Submitting to Google Play"               → RB4 Sections 4-5
"App was rejected by Apple"               → NB6 Scenario 7 | RB4 Section 7
"App was rejected by Google"              → NB6 Scenario 7 | RB4 Section 7
"Don't know what screenshots to create"   → NB6 Scenario 8 Step 3 | RB4 Section 6
"Don't know how to write a description"   → NB6 Scenario 8 Step 3 | RB4 Section 6
"Setting up in-app purchases"             → NB5 Section 5 | RB4 Section 8
"App is live — what now?"                 → NB5 Section 6 | RB1 Sections 1-3
"App isn't appearing in search"           → NB6 Scenario 8 | RB4 Section 6 (ASO)

GROWTH & DOWNLOADS
──────────────────────────────────────────────────────
"Zero or very low downloads"              → NB6 Scenario 8
"Downloads started then stopped"          → NB6 Scenario 10
"Users don't return after first visit"    → NB6 Scenario 11
"Bad reviews appearing"                   → NB6 Scenario 9
"Good reviews but no downloads"           → NB6 Scenario 8 Step 2 (keywords)
"Competitor launched similar app"         → NB6 Scenario 12
"Don't know if app is succeeding"         → NB7 Section 7 | RB1 Section 5

TECHNICAL PROBLEMS
──────────────────────────────────────────────────────
"App crashes on open"                     → NB6 Scenario 4
"App crashes in specific situation"       → NB6 Scenario 4 Step 2 (log reading)
"Pipeline says DEGRADED"                  → RB2 Section 1
"Build costs more than expected"          → NB6 Scenario 5 | RB3 Section 2
"Want a feature pipeline can't build"     → NB6 Scenario 6
"Pipeline is running slow"               → RB2 Section 1-2

UPDATING APPS
──────────────────────────────────────────────────────
"Want to add a feature"                   → RB6 Sections 3-4
"Want to fix a bug"                       → RB6 Section 2 | NB6 Scenario 4
"Want to change description/screenshots" → RB6 Section 6 | RB4 Section 4
"Update broke the app"                   → RB6 Section 7 (rollback)
"Pipeline itself needs updating"          → RB5

PORTFOLIO MANAGEMENT
──────────────────────────────────────────────────────
"Managing 3+ apps, feel overwhelmed"      → NB6 Scenario 13 | NB7 Sections 3-4
"Not sure which app deserves more time"   → NB7 Section 4 (tiering)
"Want to build App 2 — ready?"            → NB7 Section 2.1 (readiness checklist)
"Should I pivot or keep going?"           → NB6 Scenario 14
"Want to cross-promote between apps"      → NB7 Section 5
"Want to retire/remove an app"           → NB7 Section 4.5
"Portfolio revenue is stalled"            → NB7 Section 7.5 | NB6 Scenarios 10-11
"Want to treat this as a business"        → NB6 Scenario 15 | NB7 Section 9

COSTS
──────────────────────────────────────────────────────
"Costs feel too high"                     → NB6 Scenario 5 | RB3 Section 2-3
"Want to set up billing alerts"           → RB3 Section 6.3
"Not sure what I'm being charged for"     → RB3 Section 1
"Want a budget plan"                      → RB3 Section 6

OPERATIONS
──────────────────────────────────────────────────────
"Want a daily routine for managing apps" → RB1 Section 5
"Don't know which command to use"        → RB1 Section 2 | Section 5.1 (this doc)
"Want a weekly management schedule"      → NB7 Section 3.2 | RB1 Section 5
"Want to do a monthly portfolio review"  → NB7 Section 7.2

GENERAL ORIENTATION
──────────────────────────────────────────────────────
"Feel lost / don't know where to start"  → NB0 Section 2 (Quick Start Paths)
"Looking for a specific topic"           → NB0 Section 4 (Topic Index)
"Want to understand cost structure"      → Section 5.2 (this doc) | RB3 Section 1
"What is [build stage / term / concept]" → NB5 Section 1.3 (glossary)
"Which document covers [topic]"          → NB0 Section 4 (Topic Index)
"Just want to know what I'm doing well"  → NB7 Section 9.5 (health indicators)
```

---

### 7.2 By Frequency of Use

Not all documents are used equally. Here's an honest picture of how often you'll use each one:

```
DOCUMENT USAGE FREQUENCY
════════════════════════════════════════════════════════

DAILY or MULTIPLE TIMES PER WEEK:
  RB1 — Daily Operations       (command lookup, routine reference)
  RB6 — Updating Projects      (every time you run /modify)

WEEKLY:
  NB6 — Scenarios              (at least one scenario per week
                                 during active building phase)
  NB7 — Portfolio Management   (weekly review section)

MONTHLY:
  RB3 — Cost Control           (monthly cost review)
  RB4 — App Store Delivery     (new submissions or updates)
  NB7 Section 7.2              (monthly portfolio review)

PER-STAGE (when you reach that stage):
  NB5 — First 30 Days         (once, thoroughly)
  NB7 — Portfolio Management  (once before App 3, then reference)
  NB0 — Navigation            (once to orient, then as needed)

RARELY (specific circumstances):
  RB2 — Troubleshooting       (when something breaks)
  RB5 — Pipeline Updates      (every few months at most)
  NB1-4 — Implementation      (during initial setup only)
```

---

### 7.3 Five Rules for Using This Documentation System

**Rule 1: Match the document type to your need.**
Learning something new → Notebook. Doing a specific task → Runbook. Never read a Runbook as pre-reading before you understand the context it's written for.

**Rule 2: Start with the scenario, not the runbook.**
If something has gone wrong, NB6 Scenarios give you context, diagnosis, and a human-readable fix. The Runbooks give you technical depth. Start in NB6, go to the Runbook if you need more detail. Never start in a Runbook when you're not sure what's wrong.

**Rule 3: Read what's relevant, skip what isn't.**
At any given stage, 60-70% of this documentation is either pre-reading for a future stage you haven't reached or reference for a situation you're not in. You don't need all of it now. Use NB0 to find only what you need.

**Rule 4: NB0 is the answer to "I'm confused."**
Anytime you don't know where to go, return here first. Section 2 covers 8 common situations. Section 4 covers 80+ topics. Between them, you'll find your answer in under 2 minutes.

**Rule 5: The specification document is the ultimate authority.**
All documentation in this system is derived from and consistent with the v5.8 AI Factory Pipeline Specification. If any notebook or runbook appears to conflict with the specification, the specification takes precedence. The specification also covers architectural and technical decisions that these operator-facing documents intentionally simplify.

---

## SECTION 8: QUICK REFERENCE

### 8.1 All Documents at a Glance

| Document | Type | Read When | Frequency |
|----------|------|-----------|-----------|
| NB0 | Notebook | Orientation / lost | Per stage + as needed |
| NB5 | Notebook | Before first app | Once (section by section) |
| NB6 | Notebook | Problem arises | Weekly during active phase |
| NB7 | Notebook | Before App 3 | Once + monthly reference |
| RB1 | Runbook | Any operations task | Daily |
| RB2 | Runbook | Something broke | As needed |
| RB3 | Runbook | Cost review | Monthly |
| RB4 | Runbook | Store submission | Per submission |
| RB5 | Runbook | Pipeline update | Rarely |
| RB6 | Runbook | Updating live app | Per update |

### 8.2 One-Line Document Descriptions

```
NB0: Where everything is — the guide to the guides
NB5: How to build and launch your first app in 30 days
NB6: 15 real problems with diagnosed solutions and case studies
NB7: How to build and run a portfolio of 5-20 apps
RB1: How to operate the pipeline day-to-day
RB2: How to diagnose and fix anything that breaks
RB3: How to control and minimize pipeline costs
RB4: How to submit apps to Apple and Google stores
RB5: How to update the pipeline system itself
RB6: How to safely update and patch live apps
```

### 8.3 The 10 Most Important Pages in the System

If you read only 10 pages from the entire documentation system, read these (in this order):

```
TOP 10 PAGES TO READ
════════════════════════════════════════════════════════

1. NB0 Section 2 (Quick Start Paths — pick yours)
   Why: Tells you exactly where to go based on your situation

2. NB5 Section 1.3 (Glossary — key terms)
   Why: Builds shared vocabulary for every other document

3. NB5 Section 3 (Build day walkthrough)
   Why: Core workflow you'll use for every new app

4. NB6 Scenario 1 (Idea validation)
   Why: The most preventable mistake — building the wrong thing

5. NB6 Scenario 8 (Getting downloads)
   Why: The most common post-launch problem

6. RB1 Section 2 (Telegram command reference)
   Why: The commands you'll use every single day

7. RB1 Section 3 (Execution mode selection)
   Why: Choosing the wrong mode costs money unnecessarily

8. NB7 Section 4.2 (The four tiers)
   Why: The system that makes portfolio management manageable

9. NB7 Section 3.2 (Weekly operations rhythm)
   Why: The weekly habit that prevents everything accumulating

10. NB7 Section 7.2 (Monthly portfolio review template)
    Why: 45 minutes/month that prevents 80% of portfolio problems
```

### 8.4 Emergency Lookup Table

*When something just broke and you need an answer in under 60 seconds.*

```
EMERGENCY QUICK LOOKUP
════════════════════════════════════════════════════════

Pipeline silent (no response to /status):    → RB2 Section 1.1
Build stuck at stage > 20 minutes:          → RB2 Section 2
Build failed — error message on screen:     → NB6 Scenario 2
App just crashed for a user:                → NB6 Scenario 4 Step 1
Store sent rejection email:                 → NB6 Scenario 7 Step 1
Store sent policy violation notice:         → RB4 Section 7.4
Rating just dropped below 3.0:              → NB6 Scenario 9 + Scenario 4
Something broke after last /modify:         → RB6 Section 7 (rollback)
Cost alert triggered unexpectedly:          → /status costs --month [YYYY-MM]
                                              then RB3 Section 2
```

---

## SUMMARY & NEXT STEPS

### What You've Learned

You've completed NB0 — the master map of the entire AI Factory Pipeline documentation system.

You now know:
- **The 14-document system** and exactly what each document contains
- **Notebooks vs. Runbooks** — when to read vs. when to reference
- **Your personal path** — which documents to read based on where you are
- **Any topic** — where it lives across all 14 documents, alphabetically indexed
- **Fast lookups** — the 9 reference tables that answer 80% of daily questions
- **What to read when** — the master trigger table for every situation

### The Single Most Important Habit

Of everything in this documentation system, one habit generates more value than all others combined:

**Return to NB0 before reading anything else.**

Whenever you feel lost, overwhelmed, or unsure what to do next — open NB0 Section 2 first. Find your situation. Follow the path. It will always tell you exactly where to go, in what order, and why.

The operators who struggle with documentation don't struggle because the system is too complex. They struggle because they try to read everything rather than the right thing. NB0 is the answer to that problem.

### The Documentation Hierarchy

When in doubt about what takes precedence:

```
AUTHORITY HIERARCHY
════════════════════════════════════════════════════════

1. v5.8 AI Factory Pipeline Specification
   (technical authority — all else is derived from it)

2. Implementation Notebooks (NB1-4)
   (how to correctly set up the system)

3. Operator Notebooks (NB5, NB6, NB7, NB0)
   (how to operate and grow successfully)

4. Runbooks (RB1-6)
   (how to perform specific tasks day-to-day)

Conflicts between documents are rare. When they occur:
higher authority always wins.
```

### Common Mistakes to Avoid

1. **Reading everything before doing anything** — documentation is for doing, not pre-learning
2. **Opening a Runbook when you need a Notebook** — Runbooks assume context Notebooks provide
3. **Skipping NB0 when lost** — it always has the answer to "what do I read now"
4. **Searching for a topic instead of using the index** — Section 4 covers 80+ topics alphabetically
5. **Ignoring cross-references** — every document tells you where to go next; follow those pointers
6. **Treating all 14 documents as equally urgent** — most operators only actively use 5-6 at any given stage

### What to Read Next

```
FROM NB0, WHERE TO GO
════════════════════════════════════════════════════════

Haven't built first app yet:
  → NB5 (First 30 Days) right now

Have first app, want to grow:
  → NB6 (Scenarios 8-11 specifically)

Have first app, want to build App 2:
  → NB7 Sections 1-2 (strategy + readiness)

Managing 3+ apps, feeling stretched:
  → NB6 Scenario 13 + NB7 Sections 3-4

Something is broken:
  → NB6 (the right scenario) or RB2

Want your daily routine sorted:
  → RB1 Sections 1-5

Want to reduce costs:
  → NB6 Scenario 5 + RB3

Need to submit an app:
  → RB4 (right now, as you submit)
```

### Final Thoughts

The AI Factory Pipeline documentation system was built on one core principle: an operator with zero technical background should be able to answer any question about building, launching, and growing apps — without asking for help.

NB0 is the key that unlocks the rest of the system. Every section, every scenario, every reference table in these 14 documents is one search away — as long as you know where to look.

You now know where to look.

---

*✅ NB0: MASTER NAVIGATION GUIDE — COMPLETE*

*All 4 parts delivered:*
*- Part 1: How to Use the System + 8 Quick Start Paths*
*- Part 2: Complete Documentation Map + Topic Navigation Index*
*- Part 3: Reference Quick Links + Learning Paths by Stage*
*- Part 4: When to Read What + Quick Reference + Summary*

*Estimated total: ~22 pages*

---

*✅ ✅ ✅ COMPLETE DOCUMENTATION SYSTEM DELIVERED ✅ ✅ ✅*

*All 14 documents in the AI Factory Pipeline v5.8 Operator Manual are now complete:*

*Operator Notebooks:*
*  NB0: Master Navigation Guide (this session)*
*  NB5: First 30 Days — Setup to First Profit*
*  NB6: Real-World Scenarios & Solutions (this session)*
*  NB7: App Portfolio Management (this session)*

*Runbooks (previously delivered):*
*  RB1: Daily Operations & Standard Workflows*
*  RB2: Troubleshooting & Problem Resolution*
*  RB3: Cost Control & System Maintenance*
*  RB4: App Store & Google Play Delivery*
*  RB5: Updating AI Factory Pipeline System*
*  RB6: Updating & Patching Existing Projects*
