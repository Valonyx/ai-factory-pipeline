# RESPONSE PLAN for RB2: TROUBLESHOOTING & PROBLEM RESOLUTION

```
═══════════════════════════════════════════════════════════════════════════════
RB2 GENERATION PLAN - 6 PARTS
═══════════════════════════════════════════════════════════════════════════════

Part 1: Front Matter + Overview + Prerequisites + Section 1 (Systematic Diagnostic Process)
Part 2: Section 2 (Stage-by-Stage Failures - S0 through S3)
Part 3: Section 2 continued (Stage-by-Stage Failures - S4 through S7)
Part 4: Section 3 (Service-Specific Issues) + Section 4 (App-Level Issues)
Part 5: Section 5 (Quick Reference - Error Code Table) + Section 6 (Escalation Path)
Part 6: Troubleshooting Examples + Next Steps

Delivering Part 1 now. Reply "Cont" for Part 2.
```

---

# RB2: TROUBLESHOOTING & PROBLEM RESOLUTION

---

**PURPOSE:** Diagnose and resolve any pipeline, build, or app failure systematically.

**WHEN TO USE:** When something goes wrong - pipeline fails, build errors occur, app crashes, or services malfunction.

**ESTIMATED LENGTH:** 35-45 pages

**PREREQUISITE READING:**
- Pipeline is installed and has run successfully at least once (NB1-4)
- Familiar with daily operations (RB1 recommended)
- Understanding of basic pipeline concepts (stages S0-S7, execution modes)

**TIME COMMITMENT:**
- Quick fixes: 5-15 minutes
- Moderate issues: 30-60 minutes
- Complex problems: 1-3 hours
- Rare/severe issues: 2-6 hours (with escalation)

**WHAT YOU'LL MASTER:**
- ✅ Systematic problem diagnosis methodology
- ✅ Stage-by-stage build failure resolution (S0-S7)
- ✅ Service-specific troubleshooting (Anthropic, GitHub, Firebase, GCP)
- ✅ App-level debugging (crashes, performance, data issues)
- ✅ Error code interpretation and quick fixes
- ✅ When and how to escalate issues
- ✅ Prevention strategies for common problems

---

## 1. OVERVIEW

### 1.1 What This Runbook Covers

This is your comprehensive troubleshooting manual for the AI Factory Pipeline. Unlike RB1 (which covers normal operations), this runbook focuses exclusively on **what to do when things go wrong**.

**You'll learn:**

**Diagnostic Methodology:**
- How to identify what's actually wrong
- How to gather relevant information
- How to determine severity (critical vs minor)
- How to choose the right fix approach

**Stage-Specific Troubleshooting:**
- Every possible failure at each stage (S0-S7)
- Root causes explained in plain English
- Step-by-step resolution procedures
- When issues are fixable vs when to rebuild

**Service Troubleshooting:**
- Anthropic API connection issues
- GitHub authentication and repository problems
- Firebase deployment failures
- GCP infrastructure errors
- External service integration issues

**App Debugging:**
- Crash diagnosis and resolution
- Performance problems
- Data persistence issues
- Feature malfunctions
- User-reported bugs

**Quick Reference:**
- Error code lookup table
- Common symptoms → solutions
- Decision trees for complex problems
- Emergency procedures

**Escalation:**
- When to retry yourself
- When to seek help
- What information to provide
- Emergency support procedures

### 1.2 How Problems Are Organized

**By Location/Type:**

**Section 1: Systematic Diagnostic Process**
- Universal methodology for any problem
- Information gathering checklist
- Severity classification
- Solution selection framework

**Section 2: Stage-by-Stage Failures (S0-S7)**
- Organized by which stage fails
- Every known failure mode per stage
- Specific fixes for each failure type

**Section 3: Service-Specific Issues**
- Organized by external service
- Connection/authentication problems
- Configuration issues
- Service outages and workarounds

**Section 4: App-Level Issues**
- Organized by problem type
- Post-build problems (crashes, bugs)
- Performance and data issues
- User experience problems

**Section 5: Quick Reference**
- Error code → solution lookup table
- Symptom-based troubleshooting
- Decision trees

**Section 6: Escalation Path**
- Self-service troubleshooting limits
- When to get help
- How to report issues effectively

### 1.3 Important Philosophy

**Three core principles for troubleshooting:**

**Principle 1: Problems are normal**
- Every software system has issues
- Pipeline is complex (8 stages, 5+ services)
- Failures happen even with perfect specifications
- Most problems are solvable

**Don't feel:**
- ❌ Frustrated when builds fail
- ❌ Like you did something wrong
- ❌ That pipeline is "broken"

**Do understand:**
- ✅ Failures are expected and manageable
- ✅ Most issues have known solutions
- ✅ You can resolve 90%+ of problems yourself

---

**Principle 2: Accurate diagnosis > quick action**

**Wrong approach:**
```
Build fails at S4
→ Immediately retry
→ Fails again
→ Retry again
→ Fails again
→ Now frustrated and stuck
```

**Right approach:**
```
Build fails at S4
→ Read error message carefully
→ Understand what failed and why
→ Apply correct fix
→ Retry once
→ Succeeds
```

**Time investment:**
- Wrong approach: 3 retries × 30 min = 90 min wasted
- Right approach: 5 min diagnosis + 30 min build = 35 min total

**Saves:** 55 minutes + frustration

---

**Principle 3: Prevention > cure**

After fixing any problem, ask:
- **Why did this happen?**
- **Can I prevent it next time?**
- **What pattern caused this?**

**Examples:**

**Problem:** Build fails because API rate limit exceeded

**Cure:** Wait 60 seconds, retry

**Prevention:** 
- Don't queue 5 builds simultaneously
- Space builds 10 minutes apart
- Monitor API usage with `/cost`

---

**Problem:** App crashes because variable is undefined

**Cure:** Use `/modify` to add null check

**Prevention:**
- Always specify error handling in specifications
- Request defensive coding patterns
- Test edge cases immediately after build

---

### 1.4 How to Use This Runbook

**This is NOT a book to read cover-to-cover.**

**This IS a reference manual to consult when problems occur.**

**Recommended usage:**

**When problem occurs:**

1. **Start with Section 1 (Diagnostic Process)**
   - Follow systematic approach
   - Gather information
   - Classify severity

2. **Jump to relevant section based on diagnosis:**
   - Build failed at specific stage? → Section 2 (that stage)
   - Service connection issue? → Section 3 (that service)
   - App crashes/bugs? → Section 4 (app-level issues)

3. **Use Section 5 (Quick Reference) for fast lookup:**
   - Know the error code? → Look it up directly
   - Know the symptom? → Find in symptom table

4. **If solution doesn't work → Section 6 (Escalation)**

**Bookmark/save:**
- Section 5 (Quick Reference) - most frequently used
- Specific fixes you've used before
- Your personal "common problems" list

---

## 2. PREREQUISITES CHECKLIST

Before troubleshooting, verify these basics are in place:

### 2.1 Pipeline Foundation

□ **Pipeline was working previously**
- Have you successfully built at least one app before?
- Has pipeline ever run without errors?

**If NO:** This isn't troubleshooting, this is setup.
→ Go to NB1-4 (implementation notebooks) for initial configuration.

□ **You can access Telegram bot**
- Can you send messages to bot?
- Does bot respond to ANY command?

**If NO:** Bot connection issue.
→ See Section 3.1 (Telegram/Bot connectivity)

□ **You have admin access to pipeline**
- Can you access configuration files?
- Can you restart pipeline?
- Can you view logs?

**If NO:** Permission issue.
→ Contact system administrator or see NB2 for permissions setup.

### 2.2 Information Gathering Ability

□ **You can access logs**

Test:
```
/logs recent
```

Should show recent log entries.

**If command fails:**
→ See Section 3.5 (Logging system issues)

□ **You can check pipeline status**

Test:
```
/status
```

Should show current pipeline state.

**If command fails:**
→ Pipeline is completely down. See Section 2.1 (Pipeline won't start)

□ **You understand error messages (basic level)**
- Can you identify which stage failed (S0-S7)?
- Can you copy error text?
- Can you note timestamps?

**If NO:** This runbook will teach you. Continue reading.

### 2.3 Troubleshooting Mindset

□ **You have 15+ minutes to dedicate**
Rushed troubleshooting leads to:
- Skipping diagnostic steps
- Missing root cause
- Applying wrong fix
- Wasting more time

**If you have <15 minutes:**
- Note the problem
- Save error messages
- Return when you have time

□ **You're willing to follow systematic process**
Not:
- ❌ Random guessing
- ❌ Immediate retries without diagnosis
- ❌ Changing multiple things simultaneously

But:
- ✅ Reading error messages carefully
- ✅ Following diagnostic steps sequentially
- ✅ Testing one change at a time

□ **You have access to this runbook**
- Can reference sections as needed
- Can look up error codes
- Can follow step-by-step procedures

### 2.4 Emergency Quick Checks

**Before deep troubleshooting, verify these basics:**

**Check 1: Is internet working?**
```bash
ping google.com
```

If no response: Internet is down.
→ Fix internet connection first, then retry.

**Check 2: Is computer responding normally?**
- Is computer slow/frozen?
- CPU at 100%?
- Out of memory?

If yes: Restart computer, then retry.

**Check 3: Did anything change recently?**
- Updated pipeline?
- Changed configuration?
- Updated operating system?
- Installed new software?

If yes: Change may have broken something.
→ Note what changed for diagnosis.

**Check 4: Is problem reproducible?**
- Does it happen every time?
- Or just once?

If just once: Might be transient error.
→ Retry once before deep troubleshooting.

If every time: Systematic problem.
→ Proceed with full diagnosis.

---

## 3. SECTION 1: SYSTEMATIC DIAGNOSTIC PROCESS

**Use this process for ANY problem, regardless of type.**

### 3.1 Step 1: Identify What's Wrong

**Don't assume. Verify.**

**Action: State the problem precisely.**

**Vague (not helpful):**
- "It's broken"
- "Doesn't work"
- "Something's wrong"

**Precise (helpful):**
- "Build fails at S4 stage with 'out of memory' error"
- "Telegram bot doesn't respond to /status command"
- "App crashes immediately on launch after build completes"
- "GitHub deployment fails with authentication error"

**Framework for precision:**

**For build failures:**
```
[BUILD TYPE] fails at [STAGE] with error: "[EXACT ERROR TEXT]"

Example:
CREATE build fails at S4 with error: "Xcode signing failed - provisioning profile not found"
```

**For service issues:**
```
[SERVICE] [ACTION] fails with: "[EXACT ERROR TEXT]"

Example:
GitHub repository creation fails with: "Authentication failed - token expired"
```

**For app issues:**
```
App [BEHAVIOR] when [ACTION] on [PLATFORM]

Example:
App crashes when user taps "Start Timer" button on Android 13
```

---

### 3.2 Step 2: Gather Information

**Collect these details systematically:**

**Information Category A: Error Details**

□ **Exact error message**
- Copy complete text (don't paraphrase)
- Include error codes if shown
- Note any warnings before error

**How to get:**
```
/logs recent
```

Or check Telegram notification that reported error.

**Example:**
```
❌ S4 FAILED - Build

Error: Code signing failed
Code: ERRCODE_XCODE_SIGN_001
Details: No valid signing certificate found for bundle ID com.yourname.focusflow

Stack trace:
  at XcodeBuildService.sign (xcode.js:234)
  at BuildStage.execute (s4-build.js:156)
  at Pipeline.runStage (pipeline.js:89)
```

Copy ALL of this, not just "code signing failed."

---

**Information Category B: Context**

□ **What were you trying to do?**
- /create new app?
- /modify existing app?
- Just checking /status?

□ **What stage/step failed?**
- Which S0-S7 stage?
- Or pre-build (evaluation)?
- Or post-build (testing)?

□ **Execution mode:**
```
/status
```

Look for: `Mode: [CLOUD/LOCAL/HYBRID]`

□ **Platform:**
- Building for iOS, Android, Web, or All?

□ **Has this worked before?**
- First time trying this?
- Or worked yesterday, broken today?

---

**Information Category C: System State**

□ **Pipeline status:**
```
/status
```

Note:
- Status: RUNNING, STOPPED, ERROR?
- Service connections: All connected?
- Resource usage: CPU%, Memory%

□ **Recent changes:**
- Updated pipeline recently?
- Changed configuration?
- Updated OS or dependencies?

□ **Timing:**
- When did problem start?
- How long has it been failing?
- Does it fail immediately or after delay?

---

**Information Category D: Reproduction**

□ **Is it consistent?**
- Fails every time? (reproducible)
- Or random? (intermittent)

□ **What's the pattern?**
- Fails for ALL builds or specific apps?
- Fails in one mode but not another?
- Fails at specific time of day?

**Test reproducibility:**

If build failed:
```
/retry [build-id]
```

Does it fail at same place with same error?
- YES → Systematic problem (good, easier to fix)
- NO → Transient issue (harder to diagnose)

---

### 3.3 Step 3: Determine Severity

**Not all problems are equal. Classify to prioritize:**

**CRITICAL (fix immediately, <30 minutes):**
- ✅ Pipeline completely down (won't start)
- ✅ All builds failing (nothing works)
- ✅ Production app crashed for users
- ✅ Data loss occurring
- ✅ Security vulnerability exposed

**Action:** Drop everything, fix now.

---

**HIGH (fix within hours):**
- ✅ Current build failing (blocking active work)
- ✅ Service disconnected (affects all future builds)
- ✅ App crashes for some users
- ✅ Payment system broken

**Action:** Finish current task, then address.

---

**MEDIUM (fix within days):**
- ✅ Feature not working as expected
- ✅ Performance slower than normal
- ✅ Cosmetic issues in app
- ✅ Non-blocking warnings in builds

**Action:** Schedule time to fix, not urgent.

---

**LOW (fix when convenient):**
- ✅ Minor UI imperfections
- ✅ Rare edge case bugs
- ✅ Nice-to-have improvements
- ✅ Documentation typos

**Action:** Add to backlog, fix during maintenance.

---

**Severity assessment questions:**

**Q1: Does this block ALL work?**
- YES → CRITICAL
- NO → Continue

**Q2: Does this block CURRENT work?**
- YES → HIGH
- NO → Continue

**Q3: Does this affect USERS?**
- YES → HIGH or MEDIUM (depending on how many users)
- NO → Continue

**Q4: Does this affect QUALITY?**
- YES, significantly → MEDIUM
- NO, cosmetic only → LOW

---

### 3.4 Step 4: Choose Solution Approach

**Based on gathered information and severity, choose approach:**

---

**Approach A: RETRY (transient errors)**

**Use when:**
- ✅ Error mentions "timeout" or "network"
- ✅ Error says "temporary" or "try again"
- ✅ First occurrence (never happened before)
- ✅ Service status page shows issues

**Action:**
```
/retry [build-id]
```

Or for non-build issues:
- Wait 60 seconds
- Retry exact same action

**Expected outcome:**
- Success on retry (if truly transient)
- Same failure (if systematic problem)

**If fails again:** Move to Approach B or C.

---

**Approach B: QUICK FIX (known issues)**

**Use when:**
- ✅ Error code appears in Section 5 (Quick Reference)
- ✅ Exact error seen before
- ✅ Solution is documented

**Action:**
1. Look up error in Section 5
2. Follow fix procedure
3. Test immediately

**Expected outcome:**
- Problem resolved in <15 minutes

**If doesn't work:** Move to Approach C.

---

**Approach C: SYSTEMATIC DIAGNOSIS (unknown issues)**

**Use when:**
- ✅ Retry didn't work
- ✅ Error not in quick reference
- ✅ Never seen this before
- ✅ Complex/unclear problem

**Action:**
1. Identify which category:
   - Build failure (S0-S7) → Section 2
   - Service issue → Section 3
   - App issue → Section 4

2. Read relevant section completely

3. Follow diagnostic steps for that issue type

4. Apply solution

5. Test thoroughly

**Expected outcome:**
- Problem resolved in 30-90 minutes

**If doesn't work:** Move to Approach D.

---

**Approach D: WORKAROUND (can't fix immediately)**

**Use when:**
- ✅ Fix is complex (requires hours)
- ✅ Severity is LOW or MEDIUM
- ✅ You need to make progress

**Action:**
1. Find alternative approach
2. Document the problem
3. Schedule proper fix later

**Examples:**

**Problem:** iOS build fails in CLOUD mode with Xcode error

**Workaround:** Build for Android instead (LOCAL mode, free)
**Proper fix later:** Configure Xcode signing certificates

---

**Problem:** Payment integration broken

**Workaround:** Launch without payments, add in v1.1
**Proper fix later:** Debug RevenueCat configuration

---

**Approach E: ESCALATION (beyond self-service)**

**Use when:**
- ✅ Tried everything in this runbook
- ✅ Problem persists for >3 hours
- ✅ CRITICAL severity
- ✅ Suspected pipeline bug

**Action:**
→ See Section 6 (Escalation Path)

---

### 3.5 Step 5: Apply Fix

**Once you've chosen an approach and solution:**

**Rule 1: Change ONE thing at a time**

❌ **Wrong:**
```
Build failing, so:
1. Switch from CLOUD to LOCAL mode
2. Update pipeline version
3. Change API keys
4. Modify app specification
5. Retry build

[Build succeeds]

Which change fixed it? Unknown.
```

✅ **Right:**
```
Build failing, so:

Test 1: Retry without changes
Result: Failed

Test 2: Switch to LOCAL mode only
Result: Failed

Test 3: Update API key only (switch back to CLOUD)
Result: SUCCESS

Conclusion: API key was the issue.
```

**Why this matters:**
- Know what actually fixed it
- Can prevent in future
- Can document solution
- Faster next time

---

**Rule 2: Test immediately after fix**

**Don't assume fix worked. Verify.**

After applying fix:
```
1. Test the exact thing that failed
2. Verify it now works
3. Test related functionality
4. Confirm no new problems introduced
```

**Example:**

**Fixed:** GitHub authentication

**Test:**
```
1. Create test repository manually via GitHub API
2. Verify pipeline can push code
3. Try building simple app
4. Check deployment succeeds
5. Delete test repository
```

**Only THEN:** Mark as resolved.

---

**Rule 3: Document what you did**

**Create simple log entry:**

```
DATE: 2026-03-03
PROBLEM: Build failing at S6 with GitHub auth error
ERROR: "Authentication failed - token expired"
SEVERITY: HIGH (blocking current work)

DIAGNOSIS:
- GitHub token last updated: 90 days ago
- Tokens expire after 90 days
- Verified by checking GitHub settings

FIX:
1. Generated new token at github.com/settings/tokens
2. Updated pipeline: /config github_token ghp_xxxxx
3. Restarted pipeline: /restart
4. Tested with build retry

RESULT: ✅ Resolved in 12 minutes
PREVENTION: Set calendar reminder to renew token every 80 days
```

**Value:**
- Next time: Look at your log first
- Same error: Apply same fix immediately
- Save 12 minutes of diagnosis

---

**Rule 4: Verify prevention (if applicable)**

**After fix, ask:**
- Can this happen again?
- If yes, how do I prevent it?
- What's the preventive measure?

**Examples:**

**Problem:** Disk full, builds failing

**Fix:** Deleted old build artifacts

**Prevention:**
```
/config auto_cleanup true
/config cleanup_interval 7-days
```

Now pipeline auto-cleans weekly.

---

**Problem:** API rate limit exceeded

**Fix:** Waited 60 seconds

**Prevention:**
- Don't queue 5 builds simultaneously
- Space builds 10 minutes apart
- Monitor usage: `/cost` daily

---

**Problem:** App crashes due to undefined variable

**Fix:** Used /modify to add null check

**Prevention:**
Add to specification template:
```
IMPORTANT: Add comprehensive error handling:
- Check all variables before use (null/undefined checks)
- Handle all API failures gracefully
- Validate all user inputs
- Never crash - show error messages instead
```

Future apps won't have same issue.

---

### 3.6 Step 6: Document and Learn

**After EVERY problem resolution:**

**Create entry in personal troubleshooting log:**

**Simple format:**
```
[DATE] [SEVERITY] [PROBLEM] → [SOLUTION] [TIME]

2026-03-03 HIGH S4 build failure (memory) → Switch to HYBRID mode 15min
2026-03-05 MEDIUM App crash on launch → /modify add null checks 45min
2026-03-08 LOW Slow build times → Closed other apps, restart 5min
2026-03-10 HIGH GitHub auth failed → Renewed token 10min
```

**Over time, patterns emerge:**
```
Analysis after 30 days:

TOP 3 PROBLEMS:
1. GitHub auth (3 times) - set token renewal reminder
2. Memory errors (2 times) - default to HYBRID for complex apps
3. App crashes (2 times) - improve specification template

TOTAL TIME SPENT TROUBLESHOOTING: 3.5 hours (7 minutes/day average)
TOTAL BUILDS: 45
FAILURE RATE: 15% (7 failures / 45 builds)

GOAL FOR NEXT 30 DAYS:
- Reduce failure rate to <10%
- Implement all prevention measures
- Build better specifications
```

**This transforms troubleshooting from frustrating to educational.**

---

**✅ SECTION 1 COMPLETE**

You now have:
- ✅ Systematic 6-step diagnostic process
- ✅ Information gathering framework
- ✅ Severity classification system
- ✅ Solution approach selection criteria
- ✅ Fix application methodology
- ✅ Documentation and learning practices

**Next (Section 2): Stage-by-stage failure resolution (S0-S7)**

---

**[END OF PART 1]**














---

# RB2: TROUBLESHOOTING & PROBLEM RESOLUTION
## PART 2 of 6

---

## 4. SECTION 2: STAGE-BY-STAGE FAILURES (S0-S7)

**PURPOSE:** Resolve build failures at each specific stage.

**How to use this section:**
1. Identify which stage failed (S0, S1, S2, etc.)
2. Jump to that stage's subsection
3. Find your specific error
4. Follow resolution steps

---

### 4.1 S0: PLANNING STAGE FAILURES

**What S0 does:**
- Claude AI reads your app specification
- Creates technical architecture plan
- Decides file structure and dependencies
- Validates specification completeness

**Normal duration:** 1.5-3.5 minutes

**Common failure rate:** 5-8% (relatively rare)

---

#### 4.1.1 ERROR: "Specification parsing failed"

**Error message:**
```
❌ S0 FAILED - Planning

Error: Specification parsing failed
Details: Unable to extract app requirements from provided text

Specification appears incomplete or malformed:
- Missing platform declaration
- No features specified
- Description is too vague

Please review specification format and retry.
```

**What this means in plain English:**
Pipeline couldn't understand your app specification. It's either incomplete, too vague, or formatted incorrectly.

**Root causes:**
1. Missing required fields (platform, description, features)
2. Specification is too short (< 50 words)
3. Specification is just placeholder text
4. Wrong format (not following template)

**Diagnosis:**

Review your /create or /modify command. Check:

□ **Platform specified?**
```
/create
platform: android  ← This line present?
stack: react-native  ← This line present?
```

□ **Description provided?**
Should be 2-3 sentences minimum, not:
❌ "A productivity app"
✅ "A Pomodoro timer app for students that tracks study sessions by subject and provides weekly analytics"

□ **Features listed?**
Should have 3-5+ specific features, not:
❌ "Various productivity features"
✅ "
- 25-minute Pomodoro timer
- Subject tracking
- Weekly analytics
- Push notifications
"

**Solution:**

**Step 1: Use specification template**

```
/create
platform: [android/ios/web/all]
stack: [react-native/flutter/swift/kotlin/nextjs]

APP SPECIFICATION

App Name: [Clear, specific name]
Platform: [Same as above]
Description: [2-3 sentences describing what app does, who it's for, what problem it solves]

Target Users: [Specific audience - age, occupation, needs]

Core Features:
1. [Specific feature with details]
2. [Specific feature with details]
3. [Specific feature with details]
4. [Minimum 3-5 features]

[Additional sections: UI design, data storage, monetization, etc.]
```

**Step 2: Ensure minimum length**

Specification should be **at least 200 words** for simple apps, 400+ words for complex apps.

If yours is <100 words, it's too vague.

**Step 3: Be specific, not generic**

❌ Generic:
```
App Name: MyApp
Description: A social app
Features:
- Social features
- User profiles
- Messaging
```

✅ Specific:
```
App Name: StudyGroups
Description: A study group coordination app for college students that helps them find classmates taking the same courses, schedule group study sessions, and share notes. Unlike generic messaging apps, StudyGroups focuses specifically on academic collaboration with features like course-based matching and study session scheduling.

Target Users: College students (ages 18-24) looking to form study groups for their courses.

Core Features:
1. Course roster - Add courses by code (e.g., "CS101")
2. Find classmates - See other students in same courses
3. Schedule study sessions - Pick date/time/location
4. Study session chat - Group messaging for confirmed sessions
5. Share notes/resources - Upload and share files within study groups
```

**Step 4: Retry with improved specification**

```
/create
[paste your revised, detailed specification]
```

**Prevention:**
- Keep specification templates for common app types
- Reference NB5 or RB1 for specification examples
- Start detailed, cut back if needed (easier than expanding)

---

#### 4.1.2 ERROR: "Unsupported feature detected"

**Error message:**
```
❌ S0 FAILED - Planning

Error: Unsupported feature detected
Details: Specification requests "blockchain wallet integration"

This feature is not currently supported by the pipeline:
- Blockchain/cryptocurrency features
- Web3 wallet connections
- Smart contract interactions

Suggested alternatives:
- Use external wallet services (link to Coinbase, etc.)
- Build web interface to existing blockchain apps
- Simplify to standard payment processing

Please remove or replace unsupported features and retry.
```

**What this means:**
You requested a feature the pipeline cannot build. Claude AI recognized it during planning and stopped before wasting time.

**Root causes:**
1. Feature genuinely unsupported (AR, blockchain, complex ML)
2. Feature name unclear (pipeline misunderstood)
3. Too complex for automated generation
4. Requires specialized hardware/software pipeline doesn't have

**Diagnosis:**

Check error message for which feature was flagged.

**Commonly unsupported features:**
- ❌ Blockchain/cryptocurrency/Web3
- ❌ Augmented Reality (AR)
- ❌ Virtual Reality (VR)
- ❌ Real-time video streaming
- ❌ Custom ML model training
- ❌ Peer-to-peer networking
- ❌ Advanced 3D graphics/game engines
- ❌ Hardware integrations (Bluetooth devices, NFC, etc.)
- ❌ Direct access to phone system (call logs, SMS, etc.)

**Solution A: Remove unsupported feature**

Simplest approach. Remove from specification.

**Before:**
```
Core Features:
1. User authentication
2. Task list management
3. AI voice assistant with natural language processing
4. AR task visualization in 3D space
5. Data export
```

**After:**
```
Core Features:
1. User authentication
2. Task list management
3. Voice notes (record audio notes for tasks)
4. Visual task calendar (2D calendar view)
5. Data export
```

Removed: AI voice assistant (complex ML) and AR visualization (AR unsupported)
Replaced with: Simple alternatives that achieve similar goals

**Solution B: Use external service**

Keep feature concept but delegate to external service.

**Before:**
```
Feature: Real-time video calls between users
```

This requires complex WebRTC, video encoding, etc. (unsupported)

**After:**
```
Feature: Schedule video calls
- Users can set meeting time
- App generates Zoom/Google Meet link
- Calendar integration sends reminders
- Users click link to join (opens Zoom/Meet app)
```

Pipeline can build scheduling, linking, and calendar features. External service (Zoom/Meet) handles actual video.

**Solution C: Simplify to supportable version**

**Before:**
```
Feature: Custom ML model that predicts user behavior
```

**After:**
```
Feature: Smart recommendations based on usage patterns
- Track which features user uses most
- Show relevant suggestions
- Use simple rule-based logic (if user does X often, suggest Y)
```

No ML required, achieves similar outcome with simpler logic.

**Solution D: Clarify if pipeline misunderstood**

Sometimes feature IS supported but named unclearly.

**Error says:**
```
Unsupported feature: "Advanced AI analytics"
```

**But you meant:**
```
Feature: Analytics dashboard
- Show daily/weekly/monthly usage stats
- Bar charts and graphs
- Data aggregation and display
```

**Clarify in specification:**
```
Feature: Usage analytics dashboard (NOT machine learning)
- Calculate daily active users (simple count)
- Display statistics in charts (using standard charting library)
- Show trends over time (basic data aggregation)
- No AI/ML required - just data visualization
```

Pipeline will understand this IS supported.

**Prevention:**
- Check feature list against supported features: `/help features`
- Avoid buzzwords: "AI", "ML", "blockchain" unless specifically needed
- Be explicit about implementation approach
- When in doubt, use simpler alternatives

---

#### 4.1.3 ERROR: "Platform/Stack mismatch"

**Error message:**
```
❌ S0 FAILED - Planning

Error: Platform and stack combination not supported
Details: 
- Platform: iOS
- Stack: kotlin

Kotlin is for Android apps only. For iOS, use:
- swift (native iOS)
- react-native (iOS + Android)
- flutter (iOS + Android)

Please correct platform/stack combination and retry.
```

**What this means:**
You specified a technology stack that doesn't work for your chosen platform.

**Root causes:**
1. Confused platform and stack options
2. Copy-paste error in specification
3. Misunderstanding of what stacks work where

**Valid combinations:**

| Platform | Supported Stacks |
|----------|------------------|
| iOS | swift, react-native, flutter |
| Android | kotlin, react-native, flutter |
| Web | nextjs |
| All (iOS + Android) | react-native, flutter |

**Invalid combinations that cause this error:**
- ❌ iOS + kotlin (Kotlin is Android-only)
- ❌ Android + swift (Swift is iOS-only)
- ❌ Web + react-native (React Native is for mobile)
- ❌ Web + flutter (Flutter web support limited, not recommended)
- ❌ iOS + nextjs (Next.js is for web)

**Solution:**

**Step 1: Decide your target platform**

What do you actually want to build?
- Mobile app for iPhone users → iOS
- Mobile app for Android users → Android
- Both iPhone and Android → All
- Website/web app → Web

**Step 2: Choose compatible stack**

**For iOS only:**
```
platform: ios
stack: swift
```
OR
```
platform: ios
stack: react-native
```

**For Android only:**
```
platform: android
stack: kotlin
```
OR
```
platform: android
stack: react-native
```

**For both iOS and Android:**
```
platform: all
stack: react-native
```
OR
```
platform: all
stack: flutter
```

**For web only:**
```
platform: web
stack: nextjs
```

**Step 3: Retry with corrected combination**

```
/create
platform: android  ← Corrected
stack: react-native  ← Corrected (works for Android)

[rest of specification]
```

**Prevention:**
- Use platform/stack template for consistency
- Don't change both simultaneously
- When unsure: `react-native` works for most mobile scenarios

---

#### 4.1.4 ERROR: "Execution mode incompatible with platform"

**Error message:**
```
❌ S0 FAILED - Planning

Error: Execution mode not suitable for platform
Details:
- Platform: iOS
- Current mode: LOCAL

iOS apps require macOS build environment.
LOCAL mode only supports: Android, Web

For iOS, you must use:
- CLOUD mode ($1.20 per build)

Change mode: /config execution_mode CLOUD
Then retry build.
```

**What this means:**
You're trying to build an iOS app in LOCAL mode, but iOS apps MUST be built on macOS (which LOCAL mode on your Windows/Linux machine doesn't provide).

**Root causes:**
1. Forgot iOS requires CLOUD mode
2. Recently switched to LOCAL for cost savings
3. Trying to build multi-platform (including iOS) in LOCAL

**Valid mode combinations:**

| Platform | CLOUD | HYBRID | LOCAL |
|----------|-------|--------|-------|
| iOS | ✅ Required | ❌ | ❌ |
| Android | ✅ | ✅ | ✅ |
| Web | ✅ | ✅ | ✅ |

**Solution A: Switch to CLOUD mode (if building iOS)**

```
/config execution_mode CLOUD
/restart
```

Wait 30 seconds, then retry:
```
/create
platform: ios
stack: swift

[specification]
```

**Cost:** $1.20 per iOS build

**Solution B: Build for Android instead (if flexible)**

```
/create
platform: android  ← Changed from iOS
stack: react-native

[same specification otherwise]
```

**Benefits:**
- LOCAL mode works (free)
- Faster iteration (LOCAL is faster for you)
- Lower barrier (Google Play is $25 vs Apple $99/year)

**Can add iOS later** once Android version proven.

**Solution C: Use multi-platform with mixed modes**

If building for both iOS and Android:

```
# Cannot do this in one build with LOCAL mode
platform: all

# Instead, build separately:
```

**First: Android in LOCAL (free)**
```
/create
platform: android
stack: react-native
[specification]
```

**Then: iOS in CLOUD ($1.20)**
```
/config execution_mode CLOUD
/restart

/create
platform: ios
stack: react-native
[same specification]
```

**Cost:** $0 (Android) + $1.20 (iOS) = $1.20 total
**vs** $1.20 + $1.20 = $2.40 if built both in CLOUD

**Prevention:**
- Check platform before building
- Remember: iOS always needs CLOUD mode
- Consider Android-first strategy for cost savings
- Document in your build checklist

---

#### 4.1.5 TIMEOUT: "S0 taking >5 minutes"

**Symptom:**
```
📋 S0 STARTED - Planning

[5 minutes pass... no completion notification]

/status shows:
Current build: S0 (Planning) - 6m 30s elapsed
Status: ACTIVE
```

**What this means:**
S0 should complete in 1.5-3.5 minutes. If >5 minutes, something is stuck.

**Root causes:**
1. Anthropic API slow/unresponsive
2. Extremely complex specification (1000+ words)
3. Network issues causing retries
4. Pipeline process frozen

**Diagnosis:**

**Check 1: Is pipeline actually working?**
```
/status
```

Look for:
```
Status: ACTIVE  ← Pipeline is running
```

If shows `FROZEN` or doesn't respond → Pipeline crashed. See Section 4.2.1.

**Check 2: Is Anthropic API responding?**

Check status: https://status.anthropic.com

If showing outage → Service issue, not your fault.

**Check 3: Specification complexity**

Character count your specification:
- <500 words: Should be fast (2 min)
- 500-1000 words: Normal (3 min)
- 1000-2000 words: Slow (4-5 min)
- 2000+ words: Very slow (might timeout)

**Solutions:**

**If <10 minutes elapsed:**
**Wait.** Let it finish. Complex specs legitimately take longer.

**If 10-15 minutes:**
**Check logs:**
```
/logs recent
```

Look for:
```
[S0] Retrying Anthropic API call (attempt 2/3)
[S0] Network timeout, waiting...
```

This indicates transient issue. **Wait for automatic retry.**

**If >15 minutes:**
**Cancel and retry:**
```
/cancel

[Wait for cancellation confirmation]

/create
[paste specification again]
```

**If fails again at S0:**

**Simplify specification:**
- Remove detailed UI descriptions
- Cut feature list to top 5 only
- Remove optional sections
- Keep core concept only

**Example simplification:**

**Before (1,200 words):**
```
[Long detailed specification with 15 features, extensive UI mockups, detailed user flows, comprehensive data models, etc.]
```

**After (400 words):**
```
App Name: StudyTimer
Platform: Android
Stack: React Native

Description: Pomodoro timer for students that tracks study time by subject.

Core Features (MVP):
1. 25-minute timer
2. Track sessions by subject
3. View weekly total hours
4. Simple stats dashboard
5. Dark mode

Build this minimal version first. Will add advanced features in v1.1.
```

**Prevention:**
- Start with MVP specifications (minimal viable product)
- Add features incrementally via /modify
- Keep initial specs under 500 words
- Elaborate after first successful build

---

### 4.2 S1: DESIGN STAGE FAILURES

**What S1 does:**
- Claude AI creates UI/UX design
- Plans screen layouts and navigation
- Establishes design system (colors, fonts)
- Creates component hierarchy

**Normal duration:** 3-6 minutes

**Common failure rate:** 3-5% (rare)

---

#### 4.2.1 ERROR: "Design constraints conflicting"

**Error message:**
```
❌ S1 FAILED - Design

Error: Design constraints are conflicting
Details: Cannot satisfy all specified requirements simultaneously

Conflicts detected:
1. Specification requests "minimalist design" but also "10+ screens"
   Minimalist apps typically have 3-5 screens max

2. Requests "simple UI" but also "advanced data visualization with 5+ chart types"
   Complex visualizations contradict simplicity

3. Color scheme: Primary #FFFFFF (white) and background #FFFFFF (white)
   No contrast - text would be invisible

Suggestion: Simplify requirements or resolve contradictions
```

**What this means:**
Your specification contains contradictory design requirements that can't both be satisfied.

**Root causes:**
1. Conflicting adjectives ("simple" + "feature-rich")
2. Too many screens for stated simplicity
3. Impossible color combinations
4. Contradictory style requests

**Common contradictions:**

**Contradiction A: Scope vs. Simplicity**
```
❌ "Build a minimalist app with 15 screens and 30 features"
```
Minimalist = few features, few screens. Can't have both.

**Fix:**
```
✅ Option 1: "Build a minimalist app with 3-5 core screens"
✅ Option 2: "Build a feature-rich app with 15 screens" (drop "minimalist")
```

**Contradiction B: Design style conflict**
```
❌ "Modern minimalist design with lots of animations, gradients, and decorative elements"
```
Minimalist = few decorative elements. Animations/gradients are opposite.

**Fix:**
```
✅ "Modern minimalist design with subtle animations and solid colors"
OR
✅ "Modern colorful design with gradients, animations, and visual flair"
```

**Contradiction C: Color accessibility**
```
❌ Primary: #FFFF00 (bright yellow)
    Background: #FFFFFF (white)
    Text: #CCCCCC (light gray)
```
Yellow on white, light gray text = unreadable.

**Fix:**
```
✅ Primary: #2196F3 (blue)
    Background: #FFFFFF (white)
    Text: #212121 (dark gray/black)
```

**Solution:**

**Step 1: Identify contradictions**

Read error message carefully. It tells you exactly what conflicts.

**Step 2: Choose one direction**

You can't have both. Pick priority:
- Simple OR feature-rich?
- Minimalist OR decorative?
- Few screens OR comprehensive?

**Step 3: Revise specification**

Remove contradictory requirements.

**Before:**
```
Design: Minimalist and simple
Screens: 12 screens with complex navigation
Features: 20 features across all screens
UI Style: Lots of animations and gradients
```

**After:**
```
Design: Clean and modern (not strictly minimalist)
Screens: 8 main screens with tab navigation
Features: 12 core features (prioritized list below)
UI Style: Subtle animations on key interactions, simple color scheme
```

**Step 4: Retry**
```
/create
[revised specification without contradictions]
```

**Prevention:**
- Review specification for contradictions before submitting
- Use consistent terminology throughout
- If unsure, skip adjectives (let pipeline decide)
- Test colors for contrast: https://webaim.org/resources/contrastchecker/

---

#### 4.2.2 ERROR: "Screen count exceeds recommended limit"

**Error message:**
```
❌ S1 FAILED - Design

Error: Screen count exceeds recommended limit
Details: Specification describes 25+ unique screens

Pipeline recommendation: Maximum 15 screens for maintainability

Detected screens:
1. Login, 2. Signup, 3. Password Reset, 4. Email Verification,
5. Onboarding 1, 6. Onboarding 2, 7. Onboarding 3,
8. Main Dashboard, 9. Settings, 10. Profile, 11. Edit Profile,
[... 14 more screens ...]

Suggestions:
- Combine related screens (e.g., merge 3 onboarding screens into 1 scrollable)
- Remove optional screens
- Build MVP first (5-8 screens), add more in updates
```

**What this means:**
Your app design is too complex for initial build. 25 screens means:
- Longer build time (45-60 min vs 30 min)
- More bugs
- Harder to test
- Overwhelming for users

**Root causes:**
1. Over-planning initial version
2. Trying to match complex existing apps
3. Separate screen for every minor function
4. Not thinking about MVP (minimum viable product)

**Solution:**

**Step 1: Identify core screens (must-have)**

From your 25 screens, which are **absolutely essential** for app to function?

**Example: Social app with 20 screens**

Must-have (6 screens):
1. Login/Signup (can be 1 screen with tabs)
2. Main feed
3. Profile
4. Create post
5. Settings
6. Chat

Nice-to-have (can add later):
7-20. Everything else (detailed analytics, advanced filters, custom themes, etc.)

**Step 2: Combine screens where possible**

**Before (3 screens):**
```
1. Onboarding screen 1: "Welcome"
2. Onboarding screen 2: "How it works"
3. Onboarding screen 3: "Get started"
```

**After (1 screen):**
```
1. Onboarding: Swipeable carousel with 3 pages (Welcome, How it works, Get started)
```

**Before (2 screens):**
```
1. View profile
2. Edit profile (separate screen)
```

**After (1 screen):**
```
1. Profile (with "Edit" button that makes fields editable in-place)
```

**Step 3: Version planning**

**v1.0 (launch with 6-8 screens):**
- Core functionality only
- Proves concept
- Gets user feedback

**v1.1 (add 3-4 screens):**
- Most-requested features from feedback
- Improves on v1.0

**v1.2 (add 3-4 more):**
- Advanced features
- Polish

**Better than:**
- v1.0 with 20 screens (overwhelming, buggy, late)

**Step 4: Revise specification to 8-12 screens max**

```
/create
platform: android
stack: react-native

App Name: SocialConnect

SCREENS (MVP - v1.0):
1. Auth Screen (combined login/signup with tabs)
2. Main Feed (posts from connections)
3. Create Post Screen
4. Profile Screen (view + edit mode toggle)
5. Connections List
6. Direct Messages
7. Notifications
8. Settings

[v1.1 will add: Advanced search, Groups, Events]
[v1.2 will add: Stories, Analytics, Custom themes]
```

**Prevention:**
- Think MVP first, features later
- Combine screens when possible
- Plan versions: v1.0, v1.1, v1.2
- Aim for 5-10 screens initially

---

#### 4.2.3 TIMEOUT: "S1 taking >10 minutes"

**Symptom:**
```
🎨 S1 STARTED - Design

[10 minutes pass... no completion]

/status shows:
Current build: S1 (Design) - 12m 15s elapsed
```

**What this means:**
S1 should complete in 3-6 minutes. If >10 minutes, likely stuck.

**Root causes:**
1. Extremely complex UI specification
2. Anthropic API slow
3. Too many design iterations requested
4. Pipeline trying to resolve impossible design constraints

**Solution:**

**If <12 minutes: Wait**
Complex designs legitimately take up to 10 minutes.

**If >12 minutes: Check logs**
```
/logs recent
```

Look for repeated patterns:
```
[S1] Attempting design iteration 5...
[S1] Resolving layout constraints...
[S1] Attempting design iteration 6...
[S1] Resolving layout constraints...
```

This indicates pipeline is stuck in iteration loop.

**Action: Cancel and simplify**
```
/cancel

[Wait for confirmation]
```

Then create simpler specification:

**Remove:**
- Detailed UI mockups
- Specific pixel dimensions
- Complex layout constraints
- "Must look exactly like [existing app]"

**Keep:**
- General style (minimalist, modern, etc.)
- Color preferences
- Basic screen list
- Essential components

**Retry:**
```
/create
[simplified specification - let pipeline decide details]
```

**Example simplification:**

**Before (too detailed):**
```
UI Design:
Main screen must have:
- Header exactly 64px tall with logo left-aligned 16px from edge
- Search bar centered, width 80% of screen, height 44px, border radius 22px
- Grid layout below: 2 columns on mobile, 3 on tablet, 4 on desktop
- Each grid item: 150x150px with 12px padding
- Bottom navigation: 5 icons, each 24x24px, centered
- Use Roboto font size 14 for body, 16 for headers, 12 for captions
[etc... extremely specific]
```

**After (appropriate level):**
```
UI Design:
- Clean, modern design
- Header with logo and search bar
- Grid layout for content (responsive)
- Bottom tab navigation
- Use sans-serif font (Roboto or SF Pro)
- Primary color: Blue (#2196F3)
```

Let pipeline determine exact measurements and responsive breakpoints.

**Prevention:**
- Avoid pixel-perfect specifications
- Give design guidelines, not exact mockups
- Trust pipeline's design decisions
- Refine with /modify if needed after seeing result

---

### 4.3 S2: CODE GENERATION STAGE FAILURES

**What S2 does:**
- Claude AI writes ALL code for your app
- Creates files (JavaScript, config, assets)
- Implements features from specification
- Adds tests and documentation

**Normal duration:** 7-15 minutes

**Common failure rate:** 8-12% (most common failure stage)

---

#### 4.3.1 ERROR: "Feature implementation failed - [feature name]"

**Error message:**
```
❌ S2 FAILED - Code Generation

Error: Feature implementation failed - "Real-time collaborative editing"
Details: Unable to generate code for requested feature

Reason: Feature requires WebSocket server infrastructure
Current limitation: Pipeline generates client-side code only

This feature would require:
- Dedicated WebSocket server
- Database for conflict resolution
- Real-time synchronization logic
- Complex state management

Suggested alternatives:
1. Remove real-time collaboration (users edit offline, sync periodically)
2. Use external service (Firebase Realtime Database, Pusher, etc.)
3. Simplify to "share edits" (not simultaneous real-time)

Please update specification and retry.
```

**What this means:**
Pipeline can write client app code, but this feature requires server infrastructure pipeline doesn't provide.

**Root causes:**
1. Feature needs backend server
2. Feature too complex for automated generation
3. Feature requires third-party service integration beyond pipeline scope

**Features that commonly cause this:**

**Category A: Real-time features**
- ❌ Real-time collaborative editing (Google Docs style)
- ❌ Live multiplayer games
- ❌ Real-time video chat
- ❌ Live location tracking of multiple users

**Alternative approaches:**
- ✅ Periodic sync (every 30 seconds, not real-time)
- ✅ Turn-based games (not live simultaneous)
- ✅ Schedule video calls (link to Zoom/Meet)
- ✅ Share location on demand (not continuous)

**Category B: Complex backend logic**
- ❌ Custom recommendation algorithms
- ❌ Complex business logic requiring server processing
- ❌ Data processing that can't run on device

**Alternative approaches:**
- ✅ Simple client-side recommendations (rule-based)
- ✅ Use external API for complex processing
- ✅ Simplify logic to run on device

**Category C: Specialized integrations**
- ❌ Direct bank account access (Plaid integration)
- ❌ Direct social media API access (Twitter, Instagram)
- ❌ Payment provider beyond RevenueCat (Stripe custom)

**Alternative approaches:**
- ✅ RevenueCat for payments (supported)
- ✅ OAuth social login (Google, Apple, Facebook - supported)
- ✅ Simplified external service integration

**Solution:**

**Option 1: Simplify feature to client-side**

**Before:**
```
Feature: Real-time collaborative task list
- Multiple users edit simultaneously
- Changes appear instantly for all users
- Conflict resolution when editing same task
```

**After:**
```
Feature: Shared task list
- Users can share their task list via link
- Others can view and add tasks
- Changes sync when app refreshes (every 30 seconds automatically)
- Last-edit-wins for conflicts (no complex resolution)
```

**Option 2: Use supported external service**

**Before:**
```
Feature: Custom payment processing with Stripe Connect
```

**After:**
```
Feature: In-app purchases with RevenueCat
- RevenueCat handles payment processing
- Supports App Store and Google Play
- Pipeline has built-in RevenueCat integration
```

**Option 3: Make it optional for v1.0**

**Before:**
```
Core Features (v1.0):
1. User authentication
2. Task management
3. Real-time collaboration ← BLOCKING
4. Push notifications
```

**After:**
```
Core Features (v1.0):
1. User authentication
2. Task management
3. Push notifications
4. Basic sharing (view-only links)

Future (v2.0):
- Real-time collaboration (requires custom backend development)
```

Launch without complex feature, add later with custom development.

**Prevention:**
- Check `/help features` for supported features
- Avoid "real-time" unless truly necessary
- Use Firebase for backend features (supported)
- Start simple, add complexity later

---

#### 4.3.2 ERROR: "Code generation timeout"

**Error message:**
```
❌ S2 FAILED - Code Generation

Error: Code generation timeout
Details: Operation exceeded maximum time limit (20 minutes)

Generation stopped at:
- Files created: 23/47 (49% complete)
- Last file: src/components/TaskList.jsx

Possible causes:
- Specification too complex
- Anthropic API responding slowly
- Large number of features

Recommendation: Simplify specification or retry during off-peak hours
```

**What this means:**
S2 has 20-minute timeout. Your specification was so complex that Claude AI couldn't finish generating code in time.

**Root causes:**
1. Specification requests 20+ features
2. Extremely detailed/verbose specification
3. Complex features requiring extensive code
4. API slow during peak hours

**Diagnosis:**

**Check specification complexity:**

Count features in your specification:
- 5-10 features: Normal (10-12 min S2)
- 10-15 features: Complex (12-16 min S2)
- 15-20 features: Very complex (16-20 min S2)
- 20+ features: Too complex (will timeout)

Count words:
- <500 words: Simple
- 500-1000 words: Normal
- 1000-2000 words: Complex
- 2000+ words: Too complex

**Solution A: Reduce feature count**

**Before (18 features):**
```
Core Features:
1. User authentication
2. Profile management
3. Task lists
4. Task categories
5. Task priorities
6. Task due dates
7. Task reminders
8. Task attachments
9. Task comments
10. Task sharing
11. Team collaboration
12. Calendar view
13. Timeline view
14. Kanban board view
15. Analytics dashboard
16. Export to PDF
17. Export to CSV
18. Dark mode
```

**After (8 core features for v1.0):**
```
Core Features (v1.0):
1. User authentication
2. Create/edit/delete tasks
3. Task due dates
4. Task reminders (push notifications)
5. Simple categories
6. Calendar view
7. Dark mode
8. Data export (CSV)

[v1.1 will add: Sharing, attachments, comments]
[v1.2 will add: Team features, multiple views, analytics]
```

**Solution B: Split into multiple builds**

Build in phases:

**Phase 1 - Core (Build 1):**
```
/create
[Specification with 5 core features only]
```

Builds successfully → v1.0.0

**Phase 2 - Enhancements (Build 2):**
```
/modify [github-url]
Add features for v1.1:
- Task attachments
- Task comments
- Sharing
```

→ v1.1.0

**Phase 3 - Advanced (Build 3):**
```
/modify [github-url]
Add features for v1.2:
- Team collaboration
- Multiple view options
- Analytics
```

→ v1.2.0

**Benefit:** Each build succeeds, incremental progress, testable at each stage.

**Solution C: Retry during off-peak hours**

**Peak hours (slower API):**
- 9 AM - 5 PM US Eastern Time (weekdays)
- Anthropic API busiest
- S2 takes 15-20 min for complex specs

**Off-peak hours (faster API):**
- Evenings (6 PM - 11 PM ET)
- Weekends
- Early mornings (6 AM - 9 AM ET)
- S2 takes 10-14 min for same specs

**Action:**
```
[Note: Current time is 2 PM ET - peak]

Schedule build for 8 PM tonight:
- Set reminder
- Submit same specification then
- Higher success probability
```

**Prevention:**
- Start with MVP (5-8 features)
- Add features incrementally
- Keep specifications under 800 words
- Build during off-peak hours if complex

---

#### 4.3.3 ERROR: "Dependency conflict detected"

**Error message:**
```
❌ S2 FAILED - Code Generation

Error: Dependency conflict detected
Details: Incompatible package versions required

Conflicts:
1. react-native-maps@0.31.0 requires react-native@0.68+
   But specification also requests: react-native-video@5.2.0
   which requires react-native@0.64-0.67

2. firebase@9.0.0 conflicts with @react-native-firebase/app@14.0.0
   Cannot use both standard Firebase SDK and React Native Firebase

Resolution required before code generation can proceed.
```

**What this means:**
Your specification requests features that require incompatible libraries. They can't coexist in the same app.

**Root causes:**
1. Requesting too many third-party integrations
2. Specific version requirements that conflict
3. Mixing incompatible technologies

**Solution A: Remove conflicting feature**

Choose which feature is more important, remove the other.

**Before:**
```
Features:
- Interactive maps (requires react-native-maps)
- Video playback (requires specific older video library)
```

**After (keep maps, remove problematic video library):**
```
Features:
- Interactive maps (react-native-maps)
- Video playback (use newer compatible video library)
```

Or:

**After (keep video, remove maps):**
```
Features:
- Video playback (old video library)
- Location display (simple, without interactive maps)
```

**Solution B: Don't specify library versions**

Let pipeline choose compatible versions automatically.

**Before (too specific):**
```
Use:
- react-native-maps v0.31.0
- react-native-video v5.2.0
- firebase v9.0.0
```

**After (let pipeline decide):**
```
Features:
- Map integration
- Video playback
- Firebase authentication

Use latest compatible versions of all libraries.
```

**Solution C: Use alternative approach**

**Before:**
```
Feature: Firebase Cloud Messaging for push notifications
AND
Feature: OneSignal for advanced notification features
```

**These conflict** (both notification services).

**After:**
```
Feature: Push notifications via Firebase Cloud Messaging
(Provides sufficient notification features, no need for OneSignal)
```

**Prevention:**
- Don't specify exact library versions unless critical
- Avoid requesting multiple similar services
- Let pipeline manage dependencies
- Trust pipeline's library choices (well-tested combinations)

---

**[END OF PART 2]**













---

# RB2: TROUBLESHOOTING & PROBLEM RESOLUTION
## PART 3 of 6

---

### 4.4 S3: TESTING STAGE FAILURES

**What S3 does:**
- Runs automated unit tests on generated code
- Validates code quality (linting)
- Checks for security vulnerabilities
- Ensures all features implemented correctly

**Normal duration:** 2-5 minutes

**Common failure rate:** 6-10%

---

#### 4.4.1 ERROR: "Tests failed - [X/Y] passed"

**Error message:**
```
❌ S3 FAILED - Testing

Error: Tests failed
Results: 24/31 tests passed (77% pass rate)

Failed tests (7):
1. test_timer_countdown
   Expected: Timer counts down from 25:00 to 00:00
   Actual: Timer shows "NaN:NaN" after 5 seconds
   
2. test_data_persistence
   Expected: Tasks saved after app restart
   Actual: All tasks lost on restart
   
3. test_notification_trigger
   Expected: Notification appears at set time
   Actual: No notification received
   
4. test_dark_mode_toggle
   Expected: All screens switch to dark theme
   Actual: Settings screen remains light theme
   
5. test_payment_flow
   Expected: Payment sheet opens on upgrade
   Actual: Payment sheet doesn't appear
   
6. test_user_authentication
   Expected: User can login with credentials
   Actual: Login returns "invalid credentials" for valid user
   
7. test_export_data
   Expected: CSV file downloads
   Actual: Export button does nothing

Build stopped. Fix required before proceeding.
```

**What this means:**
Pipeline generated code, but automated tests found bugs. These must be fixed before build can continue.

**Root causes:**
1. Specification unclear or contradictory
2. Complex feature not implemented correctly
3. Edge cases not handled
4. Integration between features broken

**Diagnosis:**

**Step 1: Categorize failures**

Group failed tests by type:

**Data handling (3 failures):**
- test_data_persistence
- test_user_authentication  
- test_export_data

**UI/Display (2 failures):**
- test_timer_countdown
- test_dark_mode_toggle

**Integration (2 failures):**
- test_notification_trigger
- test_payment_flow

**Step 2: Identify pattern**

All data-related tests failing → Data storage configuration issue
All UI tests failing → Rendering problem
Random failures → Multiple unrelated issues

**Solution A: Review specification for clarity**

Often test failures indicate specification was unclear.

**Example:**

**Test failure:**
```
test_timer_countdown: Shows "NaN:NaN"
```

**Review specification:**
```
Feature: Timer
- User can set duration
- Timer counts down
```

**Problem:** Didn't specify:
- What happens if user doesn't set duration?
- Default duration?
- What if user enters invalid number?

**Fix specification and retry:**
```
/create
[updated specification]

Feature: Timer
- User can set duration in minutes (1-120)
- Default duration: 25 minutes if not set
- Timer counts down from set duration to 00:00
- If invalid input, show error and use default
- Timer persists if app goes to background
```

**Solution B: Simplify problematic features**

If test keeps failing, feature might be too complex.

**Example:**

**Test failure:**
```
test_notification_trigger: No notification received
```

**Original specification:**
```
Feature: Smart notifications
- AI predicts optimal reminder time
- Learns from user behavior
- Sends notification at predicted time
```

**This is complex** (AI prediction, learning).

**Simplified version:**
```
Feature: Scheduled notifications
- User sets specific time for reminder (e.g., 9:00 AM)
- Notification fires at that exact time daily
- User can change time in settings
```

Much simpler, more likely to pass tests.

**Solution C: Remove optional failing features**

If feature isn't critical, remove it for v1.0.

**Example:**

**Test failure:**
```
test_export_data: Export button does nothing
```

**Decision:** Is data export critical for launch?

**If NO:**
```
/create
[specification WITHOUT export feature]

Note: Export feature will be added in v1.1 after core features proven stable.
```

**If YES:**
Keep trying to fix it (Solution D).

**Solution D: Use /modify to fix specific issues**

If you understand the bug, can fix directly:

```
/create
[original specification]
```

Let it fail at S3 again, note specific failures.

Then immediately:
```
/modify [github-url]

Fix test failures:

1. Timer showing NaN:NaN
   Issue: Duration not initialized properly
   Fix: Set default duration of 25 minutes on component mount
   
2. Data not persisting
   Issue: AsyncStorage not configured
   Fix: Initialize AsyncStorage properly and save data on change
   
3. Notifications not triggering
   Issue: Permission not requested
   Fix: Request notification permission on first app launch
```

**Prevention:**
- Be extremely specific in specifications
- Include edge case handling
- Specify defaults for all user inputs
- Define error handling explicitly
- Start simple, add complexity after core works

---

#### 4.4.2 ERROR: "Security vulnerabilities detected"

**Error message:**
```
❌ S3 FAILED - Testing

Error: Security vulnerabilities detected
Severity: HIGH (build blocked)

Vulnerabilities found:
1. CRITICAL: Hardcoded API key in source code
   Location: src/config/api.js line 15
   Risk: API key exposure if code is leaked
   Fix: Move to environment variables
   
2. HIGH: SQL injection vulnerability
   Location: src/database/queries.js line 42
   Risk: User input not sanitized before database query
   Fix: Use parameterized queries
   
3. MEDIUM: Insecure HTTP connection
   Location: src/services/analytics.js line 28
   Risk: Data transmitted over unencrypted connection
   Fix: Change to HTTPS
   
Build cannot proceed with CRITICAL or HIGH severity vulnerabilities.
Fix and retry.
```

**What this means:**
Pipeline's security scanner found dangerous code patterns that could expose user data or allow attacks.

**Root causes:**
1. Specification included API keys directly
2. Complex data queries generated without sanitization
3. External services using HTTP instead of HTTPS

**Solution A: Remove hardcoded secrets**

**Problem:**
Specification said:
```
Use OpenAI API with key: sk-abc123xyz456...
```

Pipeline literally put this in code:
```javascript
const API_KEY = "sk-abc123xyz456..."; // HARDCODED - SECURITY RISK
```

**Fix specification:**
```
Integration: OpenAI API
Configuration: API key should be stored in environment variable (OPENAI_API_KEY)
Access via: process.env.OPENAI_API_KEY
Never hardcode keys in source files.
```

**Solution B: Specify secure coding practices**

Add to specification:
```
SECURITY REQUIREMENTS:
- No hardcoded API keys, passwords, or secrets
- All external API calls must use HTTPS
- All user inputs must be validated and sanitized
- Use parameterized database queries (no string concatenation)
- Implement proper authentication for all data access
- Follow OWASP security guidelines
```

**Solution C: Accept warnings, fix criticals**

Some vulnerabilities are acceptable for MVP:

**CRITICAL/HIGH:** Must fix before build proceeds
**MEDIUM:** Can fix in v1.1 (note for later)
**LOW:** Can ignore for now

**Example decision:**

```
Vulnerabilities:
1. CRITICAL: Hardcoded API key → FIX NOW (update spec)
2. HIGH: SQL injection → FIX NOW (specify sanitization)
3. MEDIUM: HTTP analytics → NOTE FOR v1.1 (not blocking users)
4. LOW: Outdated library version → IGNORE (works fine)
```

**Solution D: Retry with security-aware specification**

```
/create
platform: android
stack: react-native

[Original specification]

SECURITY ADDITIONS:
- Store all API keys in .env file (environment variables)
- Use HTTPS for all network requests
- Validate all user inputs before processing
- Use React Native's secure storage for sensitive data
- Implement proper error handling (don't expose system details)
- Follow secure coding practices throughout
```

**Prevention:**
- Never put API keys in specifications
- Always specify "use environment variables"
- Request HTTPS explicitly for all services
- Include security section in specification template
- Review security checklist before submitting

---

#### 4.4.3 ERROR: "Code quality below threshold"

**Error message:**
```
⚠️ S3 WARNING - Testing

Warning: Code quality below recommended threshold
Score: C (68/100)

Issues detected:
- Code complexity: High (20+ lines per function in 8 files)
- Code duplication: 15% of code is duplicated
- Unused variables: 12 instances
- Console.log statements: 23 instances (should be removed)
- Missing error handling: 7 functions lack try-catch

Build can proceed, but quality improvements recommended.

Continue? (yes/no)
Auto-continuing in 30 seconds...
```

**What this means:**
Code works but has quality issues (complex, messy, hard to maintain). Not blocking, but concerning.

**Root causes:**
1. Specification too complex
2. Too many features in one build
3. Features not well-defined

**Decision tree:**

**If quality score >60:** Let it continue
- Code works
- Can improve later with /modify
- Not worth rebuilding from scratch

**If quality score <60:** Consider rebuilding
- Very messy code
- Will be hard to maintain
- Better to simplify now

**Solution A: Let it proceed, fix in v1.1**

```
[Let timer expire, build continues]

Note to self: Clean up code in v1.1 update
- Remove console.log statements
- Add error handling
- Reduce code duplication
```

**Solution B: Cancel and simplify**

```
/cancel

[Simplify specification - fewer features, clearer requirements]

/create
[simplified specification]
```

**Prevention:**
- Keep initial specifications simple
- Well-defined features = cleaner code
- Add features incrementally
- Quality improves with simpler specs

---

### 4.5 S4: BUILD STAGE FAILURES

**What S4 does:**
- Compiles code into actual app file
- Creates APK (Android), IPA (iOS), or deploys web app
- Signs app with certificates
- Optimizes assets and code

**Normal duration:** 8-20 minutes (LONGEST STAGE)

**Common failure rate:** 12-18% (MOST COMMON FAILURE STAGE)

---

#### 4.5.1 ERROR: "Out of memory"

**Error message:**
```
❌ S4 FAILED - Build

Error: Build process out of memory
Details: Java heap space exceeded

Build process attempted to use: 4.2 GB RAM
System available: 4.0 GB RAM
Additional needed: 0.2 GB

Platform: Android
Build tool: Gradle

Recommendation:
1. Close other applications to free memory
2. Switch to HYBRID mode (offloads work to cloud)
3. Switch to CLOUD mode (builds on cloud servers)
```

**What this means:**
Your computer doesn't have enough RAM to compile the app. Android builds (especially with Gradle) are memory-intensive.

**Root causes:**
1. Computer has <8GB total RAM
2. Other applications using memory
3. LOCAL mode on underpowered system
4. Very large app (many assets/dependencies)

**Immediate diagnosis:**

**Check 1: How much RAM do you have?**

**macOS:**
```
Apple menu → About This Mac → Memory
```

**Windows:**
```
Task Manager → Performance → Memory
```

**Linux:**
```bash
free -h
```

**Check 2: What's using memory now?**

**macOS:** Activity Monitor → Memory tab
**Windows:** Task Manager → Processes (sort by Memory)
**Linux:** `top` command

**Solutions by RAM amount:**

---

**If you have <8GB RAM:**

**Best solution: Switch to HYBRID mode**

```
/config execution_mode HYBRID
/restart

[Wait 30 seconds]

/create
[your specification]
```

**Cost:** $0.20 per build
**Benefit:** Offloads memory-intensive work to cloud
**Success rate:** 95%+

**Alternative: Switch to CLOUD mode**
```
/config execution_mode CLOUD
/restart
```

**Cost:** $0.20 (Android/Web), $1.20 (iOS)
**Benefit:** Entire build on cloud servers
**Success rate:** 99%+

---

**If you have 8GB+ RAM but build still fails:**

**Solution A: Free up memory**

Close these memory-heavy applications:
- ❌ Chrome/Firefox (500MB - 2GB per instance)
- ❌ Slack (400MB - 800MB)
- ❌ Photoshop/Video editors (1GB+)
- ❌ Virtual machines (2GB+)
- ❌ Games
- ❌ Multiple code editors

Keep only:
- ✅ Terminal/Command Prompt
- ✅ Telegram
- ✅ Basic text editor (if needed)

**Then retry:**
```
/retry [build-id]
```

**Solution B: Restart computer**

Fresh start clears memory:
```
1. Save all work
2. Restart computer
3. Don't open other apps
4. Start pipeline
5. Retry build immediately
```

**Solution C: Increase Java heap size (advanced)**

Edit pipeline configuration:
```bash
# Linux/macOS
export GRADLE_OPTS="-Xmx6g -XX:MaxMetaspaceSize=512m"

# Windows
set GRADLE_OPTS=-Xmx6g -XX:MaxMetaspaceSize=512m
```

Allocates 6GB to Java (adjust based on your RAM).

Then:
```
/restart
/retry [build-id]
```

**Solution D: Switch to HYBRID/CLOUD mode**

Even with 8GB+, HYBRID mode is more reliable:
```
/config execution_mode HYBRID
/restart
```

---

**Prevention:**
- Use HYBRID mode by default for Android
- Close unnecessary apps before building
- Restart computer weekly
- Upgrade to 16GB RAM if building frequently
- Use CLOUD mode for critical builds

---

#### 4.5.2 ERROR: "Xcode signing failed" (iOS only)

**Error message:**
```
❌ S4 FAILED - Build

Error: Code signing failed
Platform: iOS
Details: No valid signing certificate found

Error from Xcode:
"No profiles for 'com.yourname.focusflow' were found"

Required:
- Apple Developer account ($99/year)
- iOS Distribution Certificate
- Provisioning Profile for bundle ID: com.yourname.focusflow

Current status:
- Apple Developer account: Not detected
- Certificate: Not found
- Provisioning profile: Not found

Action required: Complete iOS setup before building.
See: docs/apple-developer-setup.md
```

**What this means:**
iOS apps must be cryptographically signed by Apple-issued certificates. You haven't set this up yet.

**Root causes:**
1. No Apple Developer account ($99/year required)
2. Account exists but certificates not configured
3. Provisioning profile not created
4. Pipeline not configured with certificates

**This is NOT a quick fix. iOS setup requires 30-60 minutes first time.**

**Solution A: Complete iOS setup (if you need iOS)**

**Step 1: Apple Developer account**

1. Go to: https://developer.apple.com
2. Sign up ($99/year - unavoidable)
3. Wait for approval (24-48 hours usually)

**Step 2: Generate certificates**

Follow complete guide: docs/apple-developer-setup.md

Summary:
1. Create iOS Distribution Certificate
2. Create App ID for your app
3. Create Provisioning Profile
4. Download certificates to computer
5. Configure pipeline with certificates

**Time:** 30-60 minutes
**Complexity:** Medium-high
**Required:** Only once, then reusable

**Step 3: Retry build**
```
/retry [build-id]
```

---

**Solution B: Build for Android instead (if flexible)**

iOS setup is complex and costs $99/year.

**Android setup is:**
- ✅ $25 one-time (vs $99/year)
- ✅ 5 minutes (vs 60 minutes)
- ✅ Simple (vs complex)
- ✅ Review in 1-3 hours (vs 24-48 hours)

**If your goal is "launch an app quickly":**
```
/create
platform: android  ← Changed from iOS
stack: react-native

[same specification otherwise]
```

**Benefits:**
- Build succeeds immediately
- Faster iteration
- Lower cost
- Can add iOS later after Android proven

**Later, add iOS:**

After Android app successful:
1. Complete iOS setup (one time)
2. Build iOS version of same app
3. Submit to both stores

---

**Solution C: Use MacinCloud (if CLOUD mode)**

If using CLOUD mode, pipeline can use MacinCloud certificates:

```
/config macincloud_use_shared_cert true
/restart
```

**Cost:** No additional cost (included in CLOUD mode)
**Limitation:** Uses shared certificate (for testing only, not App Store submission)

**Good for:**
- Testing builds
- Development
- Prototyping

**NOT for:**
- App Store submission (needs your certificate)
- Production apps

---

**Prevention:**
- Do iOS setup before first iOS build
- Keep certificates valid (renew annually)
- Start with Android, add iOS later
- Budget $99/year for Apple Developer account
- Follow setup guide completely

---

#### 4.5.3 ERROR: "Build timeout"

**Error message:**
```
❌ S4 FAILED - Build

Error: Build timeout
Details: Build process exceeded maximum time (30 minutes)

Progress:
- Compilation: 100% complete
- Asset optimization: 85% complete ← STUCK HERE
- App signing: Not started

Last activity: 18 minutes ago

Likely causes:
- Network connectivity issues (cloud mode)
- Large assets being processed
- Build process hung/frozen

Recommendation: Cancel and retry
```

**What this means:**
S4 started but got stuck partway through. Usually at asset optimization or network transfer.

**Root causes:**
1. Network timeout (CLOUD/HYBRID mode)
2. Large image/video assets
3. Build process frozen
4. Service outage

**Solution A: Check what's stuck**

```
/logs recent
```

Look for last activity:
```
[S4] Compiling JavaScript: 100%
[S4] Optimizing assets: image1.png (2.3 MB)
[S4] Optimizing assets: image2.png (4.1 MB)
[S4] Optimizing assets: video1.mp4 (125 MB) ← LAST ENTRY 18 min ago
```

**Issue identified:** Trying to optimize 125 MB video file, taking too long.

---

**Solution B: Reduce asset sizes**

**If timeout on large assets:**

Update specification:
```
/create
[original specification]

ASSETS:
- Optimize all images before including (max 500 KB each)
- Videos: Link to external hosting (YouTube, Vimeo) instead of embedding
- Use compressed formats: WebP for images, not PNG
- Limit total asset size to <20 MB
```

**For existing assets in specification:**
- Remove large videos (link instead)
- Compress images before build
- Use placeholders, replace after build

---

**Solution C: Retry (if transient network issue)**

```
/cancel

[Wait for cancellation]

/retry [build-id]
```

**If CLOUD/HYBRID mode:**
- Network timeout might be temporary
- Retry often succeeds
- Try 2-3 times before other solutions

---

**Solution D: Switch modes**

**If in CLOUD/HYBRID and timing out:**
```
/config execution_mode LOCAL
/restart
/create [specification]
```

**If in LOCAL and timing out:**
```
/config execution_mode HYBRID
/restart  
/create [specification]
```

Sometimes different mode routes around issue.

---

**Solution E: Simplify build**

If complex app causing timeout:

**Before (complex):**
```
- 20 features
- 50+ screens  
- Large assets
- Many dependencies
```

**After (simplified):**
```
- 8 core features
- 10 screens
- Optimized assets
- Essential dependencies only
```

---

**Prevention:**
- Keep apps simple initially
- Optimize assets before build
- Use external hosting for large media
- Test network stability before long builds
- Use LOCAL mode for faster builds (Android/Web)

---

#### 4.5.4 ERROR: "Gradle build failed" (Android)

**Error message:**
```
❌ S4 FAILED - Build

Error: Gradle build failed
Platform: Android
Details: Compilation error in generated code

Gradle error:
> Task :app:compileDebugJavaWithJavac FAILED

/src/main/java/com/focusflow/MainActivity.java:45: 
error: cannot find symbol
  symbol:   method getSupportActionBar()
  location: class MainActivity

Build failed with 1 error
```

**What this means:**
Android build tool (Gradle) found an error in the generated Java/Kotlin code. Usually means pipeline generated code that doesn't compile.

**Root causes:**
1. Pipeline generated incorrect code (rare)
2. Dependency version mismatch
3. Android API level mismatch
4. Breaking change in library

**Solution A: Check specification for Android-specific issues**

**Common issues:**

**Issue 1: Requested Android API level too old/new**
```
Specification said: "Support Android 6.0 and above"
Android 6.0 = API 23 (very old, some features don't work)
```

**Fix:**
```
Support Android 8.0 (API 26) and above
This is modern enough for most features, old enough for broad compatibility.
```

**Issue 2: Conflicting libraries**
```
Specification requested both:
- react-native-vector-icons
- react-native-ico (different icon library)
```

**Fix:** Choose one, remove the other.

---

**Solution B: Retry (if transient)**

Sometimes Gradle has temporary issues:
```
/retry [build-id]
```

Success rate: ~30% (worth trying once)

---

**Solution C: Report as pipeline bug**

If you didn't request anything unusual and build fails:

```
/report-issue
Build ID: [from error message]
Stage: S4
Error: Gradle build failed - cannot find symbol
Platform: Android
Specification: [attach or paste]

This appears to be code generation issue.
Specification is straightforward, no unusual requests.
```

Pipeline maintainers will:
1. Investigate generated code
2. Fix code generation bug
3. Provide updated pipeline version
4. Or suggest specification workaround

---

**Solution D: Simplify specification**

If complex specification causing issues:

Remove:
- Complex Android-specific features
- Bleeding-edge library requests
- Specific version requirements

Let pipeline use defaults:
```
Platform: Android
Use stable, well-tested defaults for all libraries and build configurations.
```

---

**Prevention:**
- Don't specify exact Android API levels unless needed
- Avoid mixing conflicting libraries
- Let pipeline choose library versions
- Start simple, add complexity later
- Report code generation bugs to help improve pipeline

---

#### 4.5.5 ERROR: "Deployment failed" (Web apps)

**Error message:**
```
❌ S4 FAILED - Build

Error: Web deployment failed
Platform: Web (Next.js)
Details: Firebase deployment timeout

Deployment progress:
- Build completed: ✅
- Uploading to Firebase Hosting: 45% ← STUCK
- Time elapsed: 15 minutes

Error: Upload timeout - connection reset

Recommendation:
- Check internet connection
- Retry deployment
- Check Firebase quota
```

**What this means:**
Web app built successfully but uploading to Firebase Hosting failed.

**Root causes:**
1. Slow/unstable internet connection
2. Large build size
3. Firebase quota exceeded
4. Firebase service issues

**Solution A: Check internet speed**

Test: https://speedtest.net

**If <5 Mbps upload:**
- Too slow for large deployments
- Switch to CLOUD mode (cloud has faster upload)

**If >5 Mbps but unstable:**
- Wait for stable connection
- Use wired Ethernet (not WiFi)
- Retry during off-peak hours

---

**Solution B: Reduce build size**

**Check build size:**
```
/logs recent
```

Look for:
```
[S4] Build size: 145 MB
```

**If >50 MB:**

Reduce by:
- Removing large assets
- Using CDN for images/videos
- Enabling code splitting
- Optimizing dependencies

**Update specification:**
```
Build optimization:
- Enable code splitting (dynamic imports)
- Use image CDN for large images (don't bundle)
- Remove unused dependencies
- Minimize bundle size
```

---

**Solution C: Check Firebase quota**

1. Go to: https://console.firebase.google.com
2. Select your project
3. Click "Usage and billing"
4. Check Hosting quota

**Free tier limits:**
- Storage: 10 GB
- Bandwidth: 360 MB/day

**If exceeded:**
- Upgrade to Blaze plan (pay-as-you-go)
- Or wait until quota resets (next day)
- Or delete old deployments to free space

---

**Solution D: Switch to CLOUD mode**

```
/config execution_mode CLOUD
/restart

/create [specification]
```

Cloud servers have:
- Faster upload speeds
- More reliable connections
- Better Firebase connectivity

**Cost:** $0.20 (vs $0 for LOCAL web builds)
**Benefit:** Higher success rate

---

**Prevention:**
- Keep web builds under 50 MB
- Use CDN for large assets
- Monitor Firebase quota
- Use stable internet connection
- Consider CLOUD mode for production builds

---

**✅ S4 TROUBLESHOOTING COMPLETE**

S4 is the most complex and failure-prone stage. Common themes:
- **Memory issues** → Use HYBRID/CLOUD mode
- **iOS signing** → Complete Apple setup first
- **Timeouts** → Simplify, reduce assets, check network
- **Gradle errors** → Simplify specification, let pipeline choose defaults
- **Web deployment** → Check connection, reduce size, check quotas

---

**[END OF PART 3]**














---

# RB2: TROUBLESHOOTING & PROBLEM RESOLUTION
## PART 4 of 6

---

### 4.6 S5: QUALITY CHECK STAGE FAILURES

**What S5 does:**
- Scans built app for security vulnerabilities
- Validates app structure and integrity
- Checks code signing validity
- Verifies platform compliance

**Normal duration:** 1.5-3.5 minutes

**Common failure rate:** 2-4% (rare - most issues caught in S3)

---

#### 4.6.1 ERROR: "Critical security vulnerability"

**Error message:**
```
❌ S5 FAILED - Quality Check

Error: CRITICAL security vulnerability detected
Severity: BLOCKER (cannot proceed)

Vulnerability: Malicious code pattern detected
Details: eval() function usage found in application code

Locations:
- src/utils/dynamicLoader.js line 47
- src/helpers/stringParser.js line 89
- src/components/CustomScript.js line 123

Risk Level: CRITICAL
Impact: Arbitrary code execution vulnerability
Exploitability: HIGH

This pattern allows execution of arbitrary code and is prohibited.

Resolution: Remove eval() usage, use safe alternatives
Build cannot proceed with this vulnerability.
```

**What this means:**
The built app contains code patterns that create serious security risks. These patterns are blocked by policy.

**Root causes:**
1. Specification requested dynamic code execution
2. Feature requires unsafe code patterns
3. Specification was too vague, pipeline guessed wrong approach

**Prohibited patterns (always blocked):**
- `eval()` - executes arbitrary code
- `Function()` constructor - same as eval
- `innerHTML` with user input - XSS attacks
- `document.write()` - security risk
- Unvalidated deep links - injection attacks

**Solution A: Review what you requested**

**Check specification for:**

❌ **Features requiring dynamic code:**
```
"Feature: User can write custom JavaScript formulas"
"Feature: Dynamic plugin system"
"Feature: Execute user-provided code snippets"
```

These REQUIRE eval() or similar unsafe patterns.

**Pipeline tried to implement** but security scanner blocked it.

**Fix: Remove or simplify feature**
```
Before:
"User can write custom formulas"

After:
"User can select from predefined formula templates"
```

Safe alternative that doesn't need dynamic code execution.

---

**Solution B: Specify safe implementation approach**

If you know safe way to implement feature:

**Before (unsafe - pipeline used eval):**
```
Feature: Calculate custom expressions
User enters: "2 + 2 * 3"
App calculates: 8
```

**After (safe - use math parser library):**
```
Feature: Calculate mathematical expressions
Use safe math parser library (e.g., mathjs)
No eval() or Function() constructor
Parse and evaluate expressions safely
Limit to mathematical operations only
```

---

**Solution C: Accept limitation, plan custom development**

Some features genuinely need dynamic code:

```
Feature: User can create custom automation scripts
```

**This cannot be built safely** by automated pipeline.

**Options:**
1. Remove from v1.0, add never (too risky)
2. Build core app now, add this feature with custom development later
3. Use external service for scripting (Zapier integration, etc.)

**Recommendation:** Remove from automated build, handle separately.

---

**Prevention:**
- Avoid features requiring "dynamic", "custom code", "user scripts"
- Specify safe implementation methods
- Use approved libraries for complex parsing
- Accept that some features can't be automated safely

---

#### 4.6.2 WARNING: "Non-critical vulnerabilities detected"

**Warning message:**
```
⚠️ S5 WARNING - Quality Check

Warning: Non-critical vulnerabilities detected
Severity: MEDIUM (build can proceed)

Vulnerabilities (3):
1. MEDIUM: Weak hash algorithm
   Location: src/auth/passwordHash.js
   Issue: Using MD5 for password hashing
   Recommendation: Use bcrypt or Argon2
   
2. LOW: Information disclosure
   Location: src/api/errorHandler.js
   Issue: Detailed error messages in production
   Recommendation: Generic errors for users, log details server-side
   
3. LOW: Outdated dependency
   Issue: lodash@4.17.19 has known vulnerability
   Recommendation: Update to lodash@4.17.21

Build can proceed, but fix these in v1.1.

Continue build? (yes/no)
Auto-continuing in 60 seconds...
```

**What this means:**
Security issues found, but not critical enough to block build. Can launch but should fix soon.

**Decision tree:**

**For MEDIUM severity:**
- If MVP/testing → Let it proceed, fix in v1.1
- If production launch → Fix before launch

**For LOW severity:**
- Can safely proceed
- Add to backlog for future updates

**Solution A: Let it proceed (most common)**

```
[Let timer expire, build continues]

Document for v1.1:
- Update password hashing to bcrypt
- Improve error handling
- Update lodash dependency
```

**Solution B: Fix now (if critical launch)**

```
/cancel

/create
[updated specification]

SECURITY REQUIREMENTS:
- Password hashing: Use bcrypt (NOT MD5)
- Error handling: Generic messages to users, detailed logs server-side only
- Dependencies: Use latest stable versions
```

---

**Prevention:**
- Include security requirements in specification template
- Specify modern security practices
- Request latest dependencies
- Review warnings in test builds

---

### 4.7 S6: DEPLOYMENT STAGE FAILURES

**What S6 does:**
- Creates GitHub repository
- Pushes source code to GitHub
- Uploads app to Firebase App Distribution
- Generates documentation

**Normal duration:** 2-4 minutes

**Common failure rate:** 8-12%

---

#### 4.7.1 ERROR: "GitHub authentication failed"

**Error message:**
```
❌ S6 FAILED - Deployment

Error: GitHub authentication failed
Details: Personal access token invalid or expired

Attempted operation: Create repository "focusflow"
Authentication method: Personal Access Token
Token status: INVALID

Error from GitHub API:
"Bad credentials" (HTTP 401)

Possible causes:
1. Token expired (tokens expire after 90 days by default)
2. Token revoked
3. Insufficient permissions
4. Wrong token configured

Resolution: Generate new token and update configuration
```

**What this means:**
Pipeline can't access your GitHub account to create repository or push code.

**Root causes:**
1. Token expired (most common - 90 day default)
2. Token deleted/revoked
3. Token has wrong permissions
4. Token not configured at all

**Solution:**

**Step 1: Generate new GitHub token**

1. Go to: https://github.com/settings/tokens
2. Click "Generate new token (classic)"
3. Token name: "AI Factory Pipeline"
4. Expiration: 90 days (or "No expiration" if you trust security)
5. Select scopes:
   - ☑️ **repo** (full control of private repositories)
   - ☑️ **workflow** (update GitHub Actions workflows)
   - ☑️ **admin:repo_hook** (full control of repository hooks)
6. Scroll to bottom, click "Generate token"
7. **Copy token immediately** (shows only once): `ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`

**Step 2: Update pipeline configuration**

```
/config github_token ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

Response:
```
✅ GitHub token updated
Token: ghp_xxxxx...xxxxx (hidden for security)
Permissions verified: ✅ repo, ✅ workflow, ✅ admin:repo_hook
```

**Step 3: Restart pipeline**

```
/restart
```

Wait 30 seconds.

**Step 4: Retry build**

```
/retry [build-id]
```

Or if starting fresh:
```
/create
[specification]
```

---

**Prevention:**

**Option 1: Set token expiration reminder**

If using 90-day expiration:
- Set calendar reminder for day 80
- Renew before expiration
- Prevents build failures

**Option 2: Use no-expiration token (if security permits)**

- More convenient (never expires)
- Security risk if token leaked
- Only if you're solo developer
- Not recommended for teams

**Option 3: Use GitHub App authentication (advanced)**

More secure than personal tokens:
- See pipeline documentation
- Requires additional setup
- Better for production use

---

#### 4.7.2 ERROR: "Repository already exists"

**Error message:**
```
❌ S6 FAILED - Deployment

Error: Repository creation failed
Details: Repository name already exists

Attempted: Create repository "focusflow"
Error from GitHub: "Repository name already exists in your account"

Repository URL: https://github.com/yourusername/focusflow

Options:
1. Delete existing repository (if old/unused)
2. Choose different app name
3. Use /config github_repo_prefix to add prefix
```

**What this means:**
You already have a repository with this name. GitHub doesn't allow duplicates.

**Root causes:**
1. Previously built app with same name
2. Manually created repository with this name
3. Retry after partial failure left repository

**Solution A: Delete old repository (if not needed)**

**If old repository is:**
- Previous test/failed build
- Not being used
- Safe to delete

**Steps:**
1. Go to: https://github.com/yourusername/focusflow
2. Click "Settings" (tab at top right)
3. Scroll to bottom: "Danger Zone"
4. Click "Delete this repository"
5. Type repository name to confirm: `yourusername/focusflow`
6. Click "I understand, delete this repository"

**Then retry build:**
```
/retry [build-id]
```

---

**Solution B: Rename your app**

Change app name in specification:

**Before:**
```
App Name: FocusFlow
```

**After:**
```
App Name: FocusFlow2
OR
App Name: StudyTimer (completely different name)
```

Then:
```
/create
[updated specification with new name]
```

Creates repository: `github.com/yourusername/focusflow2`

---

**Solution C: Use repository prefix**

Keep app name, add automatic prefix:

```
/config github_repo_prefix "v2-"
```

Now when building "FocusFlow":
- Creates repository: `v2-focusflow`
- Original `focusflow` repository untouched

Then:
```
/retry [build-id]
```

---

**Solution D: Use existing repository (advanced)**

If you WANT to update existing repository:

```
/modify https://github.com/yourusername/focusflow

[Describe changes to make]
```

This updates existing repository instead of creating new one.

---

**Prevention:**
- Use unique app names
- Delete failed build repositories promptly
- Use repository prefix for new versions
- Check GitHub before building if unsure

---

#### 4.7.3 ERROR: "Firebase deployment failed"

**Error message:**
```
❌ S6 FAILED - Deployment

Error: Firebase App Distribution upload failed
Details: Upload timeout after 15 minutes

Upload progress:
- APK size: 28.5 MB
- Uploaded: 12.3 MB (43%)
- Time elapsed: 15 minutes
- Error: Connection timeout

Network diagnostics:
- Upload speed: 0.8 Mbps (SLOW)
- Recommended: 5+ Mbps for reliable uploads

Retry or switch to CLOUD mode for better connectivity.
```

**What this means:**
Built app successfully but couldn't upload to Firebase for testing/distribution.

**Root causes:**
1. Slow internet upload speed
2. Large app file size
3. Firebase service issues
4. Network instability

**Diagnosis:**

**Check 1: Upload speed**
- Test: https://speedtest.net
- Look at UPLOAD speed (not download)

**If <2 Mbps:** Too slow for reliable uploads
**If 2-5 Mbps:** Marginal, may timeout on large apps
**If 5+ Mbps:** Should work fine

**Check 2: App size**
```
/logs recent
```

Look for:
```
[S6] APK size: 28.5 MB
```

**If <20 MB:** Should upload quickly
**If 20-40 MB:** Needs decent connection
**If >40 MB:** Very large, needs good connection

**Check 3: Firebase status**
- Visit: https://status.firebase.google.com
- Check if App Distribution has issues

---

**Solution A: Wait for better internet**

If on WiFi or mobile:
- Wait for stable connection
- Try wired Ethernet
- Try different time of day (off-peak)

Then:
```
/retry [build-id]
```

---

**Solution B: Switch to CLOUD mode**

Cloud servers have faster, more stable upload:

```
/config execution_mode CLOUD
/restart

/retry [build-id]
```

Upload happens from cloud → Firebase (both in cloud = faster).

**Cost:** $0.20 (vs $0 for LOCAL retry)
**Benefit:** Usually succeeds

---

**Solution C: Reduce app size**

If app is large (>30 MB):

**Causes of large size:**
- Large images/assets
- Many dependencies
- Unoptimized build

**Fix in next build:**
```
/create
[specification]

BUILD OPTIMIZATION:
- Compress all images (use WebP format)
- Remove unused dependencies
- Enable ProGuard minification (Android)
- Use vector graphics where possible
- Limit total asset size to 10 MB
```

---

**Solution D: Manual upload (workaround)**

If automated upload keeps failing:

**Step 1: Get APK locally**
```
/logs recent
```

Find line:
```
[S4] APK saved to: /builds/focusflow-v1.0.0.apk
```

**Step 2: Copy APK to accessible location**
```bash
cp ~/ai-factory-pipeline/builds/focusflow-v1.0.0.apk ~/Downloads/
```

**Step 3: Manually upload to Firebase**
1. Go to: https://console.firebase.google.com
2. Select your project
3. Click "App Distribution"
4. Click "Release" → "Upload new release"
5. Select APK file from Downloads
6. Add release notes
7. Click "Upload"

**Step 4: Mark build as complete**
```
/complete [build-id] --manual-deploy
```

---

**Prevention:**
- Use stable, fast internet for builds
- Keep apps under 25 MB
- Use CLOUD mode for production builds
- Optimize assets before building
- Test uploads during off-peak hours

---

### 4.8 S7: MONITORING SETUP STAGE FAILURES

**What S7 does:**
- Configures Sentry error tracking
- Enables Firebase Analytics
- Sets up crash reporting
- Creates monitoring dashboards

**Normal duration:** 1-2 minutes

**Common failure rate:** 3-5% (rare, non-critical)

---

#### 4.8.1 ERROR: "Sentry configuration failed"

**Error message:**
```
⚠️ S7 WARNING - Monitoring Setup

Warning: Sentry configuration failed
Details: No Sentry DSN configured

Sentry error tracking will not be available for this app.

To enable Sentry:
1. Create account at sentry.io
2. Get DSN (Data Source Name)
3. Configure: /config sentry_dsn [your-dsn]
4. Rebuild or update app

Build can proceed without Sentry.
App will function normally, but errors won't be tracked.

Continue? (yes/no)
Auto-continuing in 30 seconds...
```

**What this means:**
Error tracking not configured. App works fine but won't automatically report crashes/errors.

**Impact:**
- ✅ App functions normally
- ❌ No automatic error tracking
- ❌ Have to find bugs manually
- ❌ No crash reports from users

**Decision:**

**For MVP/testing:** Proceed without Sentry
- Can add later
- Not critical for initial testing
- One less thing to configure

**For production:** Configure Sentry first
- Important for real users
- Catches bugs you didn't find in testing
- Essential for support

---

**Solution A: Proceed without Sentry (quick)**

```
[Let timer expire, build continues]
```

Note for later: Set up Sentry before production launch.

---

**Solution B: Configure Sentry now**

**Step 1: Create Sentry account**
1. Go to: https://sentry.io
2. Sign up (free tier available)
3. Verify email

**Step 2: Create project**
1. Click "Create Project"
2. Platform: React Native (for mobile) or Next.js (for web)
3. Project name: focusflow
4. Click "Create Project"

**Step 3: Get DSN**

Sentry shows:
```
Configure your SDK:

Sentry.init({
  dsn: "https://abc123@xyz789.ingest.sentry.io/456789",
});
```

**Copy the DSN:** `https://abc123@xyz789.ingest.sentry.io/456789`

**Step 4: Configure pipeline**
```
/config sentry_dsn "https://abc123@xyz789.ingest.sentry.io/456789"
/restart
```

**Step 5: Retry or rebuild**

If build still in progress:
```
[Wait for build to complete]
```

If build already completed:
```
/modify [github-url]

Add Sentry error tracking:
DSN: https://abc123@xyz789.ingest.sentry.io/456789
```

---

**Prevention:**
- Set up Sentry before first production build
- Add to pipeline setup checklist
- Use same Sentry account for all apps
- Free tier supports multiple projects

---

#### 4.8.2 WARNING: "Analytics configuration incomplete"

**Warning message:**
```
⚠️ S7 WARNING - Monitoring Setup

Warning: Firebase Analytics partially configured
Details: Analytics enabled but events not configured

Basic analytics: ✅ Active
Custom events: ❌ Not configured
User properties: ❌ Not configured

App will track basic metrics:
- Screen views
- Session duration
- User engagement

But won't track custom events like:
- Feature usage
- Button clicks
- Conversions

To add custom events, use /modify after launch.

Continue? (yes/no)
Auto-continuing in 30 seconds...
```

**What this means:**
Basic analytics work, but custom event tracking not set up. For MVP, basic analytics usually sufficient.

**Decision:**

**Proceed:** Basic analytics are enough for v1.0
- See how many users
- See which screens they visit
- See session duration

**Customize later:** Add specific tracking in v1.1
- Track specific features
- Measure conversion rates
- A/B test results

**Solution:**

```
[Let build continue]

Note for v1.1: Add custom analytics events
- Track "Timer Started" event
- Track "Premium Upgrade" conversion
- Track feature usage
```

Then in v1.1:
```
/modify [github-url]

Add custom analytics events:
1. "timer_started" - when user starts timer
2. "subject_added" - when user adds subject
3. "premium_viewed" - when user sees paywall
4. "premium_purchased" - when user subscribes
5. "data_exported" - when user exports CSV

Track these in Firebase Analytics.
```

---

**Prevention:**
- Basic analytics sufficient for MVP
- Add custom events based on what you want to measure
- Review analytics in v1.0, customize in v1.1

---

## 5. SECTION 3: SERVICE-SPECIFIC ISSUES

**PURPOSE:** Troubleshoot problems with external services (Anthropic, GitHub, Firebase, GCP).

---

### 5.1 ANTHROPIC API ISSUES

#### 5.1.1 ERROR: "Rate limit exceeded"

**Error message:**
```
❌ API Error: Rate limit exceeded

Service: Anthropic Claude API
Error: 429 Too Many Requests
Details: Rate limit: 5000 requests per hour
Current usage: 5000 requests (100%)
Resets in: 42 minutes

Affected operations:
- /evaluate (blocked)
- /create (blocked)
- /modify (blocked)

Action: Wait for reset or upgrade API tier
```

**What this means:**
You've used all your Claude API requests for this hour. Must wait or upgrade.

**Root causes:**
1. Queued too many builds simultaneously
2. Many evaluations in short time
3. Large/complex specifications use more tokens
4. Free tier limits (if applicable)

**Solution A: Wait for reset**

```
Rate limit resets in: 42 minutes

[Set timer for 45 minutes]
[Come back and retry]
```

**No cost, just wait.**

---

**Solution B: Space out operations**

Instead of:
```
[Queue 5 builds at once]
→ Hit rate limit in 20 minutes
```

Do:
```
[Build 1 → Wait 15 min → Build 2 → Wait 15 min → Build 3]
→ Never hit rate limit
```

---

**Solution C: Upgrade API tier**

1. Go to: https://console.anthropic.com
2. Click "Billing"
3. Upgrade to higher tier
4. Higher rate limits

**Cost:** Depends on tier
**Benefit:** Build without waiting

---

**Prevention:**
- Don't queue 5+ builds at once
- Space builds 10-15 minutes apart
- Monitor usage: `/cost` command
- Upgrade if hitting limits regularly

---

#### 5.1.2 ERROR: "API key invalid"

**Error message:**
```
❌ S0 FAILED - Planning

Error: Anthropic API authentication failed
Details: API key invalid or expired

Error from Anthropic:
"Invalid API key" (HTTP 401)

Configured key: sk-ant-api03-...xxxxx (last 5 chars)
Status: INVALID

Action: Verify API key or generate new one
```

**What this means:**
Pipeline can't authenticate with Anthropic's servers.

**Root causes:**
1. API key typed incorrectly
2. API key revoked
3. API key from wrong account
4. API key expired (rare)

**Solution:**

**Step 1: Get API key**

1. Go to: https://console.anthropic.com
2. Click "API Keys"
3. Click "Create Key" (or use existing)
4. Copy key: `sk-ant-api03-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`

**Step 2: Update pipeline**
```
/config anthropic_api_key sk-ant-api03-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

**Step 3: Verify**
```
/config verify anthropic_api_key
```

Should show:
```
✅ Anthropic API key valid
Account: your@email.com
Tier: [Your tier]
```

**Step 4: Restart and retry**
```
/restart
[Wait 30 seconds]
/retry [build-id]
```

---

**Prevention:**
- Store API key securely
- Don't share in specifications or code
- Rotate keys periodically
- Monitor for invalid key errors

---

### 5.2 GITHUB ISSUES

**Covered in Section 4.7.1 (GitHub authentication failed)**

Additional GitHub issues:

#### 5.2.1 ERROR: "Push rejected - branch protected"

**Solution:**
1. Go to repository Settings on GitHub
2. Click "Branches"
3. Remove branch protection from `main` branch
4. Retry build

---

#### 5.2.2 ERROR: "Repository too large"

**Solution:**
- GitHub has 100 MB file limit
- Remove large files from specification
- Use external storage for big assets
- Clean up repository if needed

---

### 5.3 FIREBASE ISSUES

#### 5.3.1 ERROR: "Firebase quota exceeded"

**Error message:**
```
❌ S6 FAILED - Deployment

Error: Firebase quota exceeded
Service: Firebase Hosting
Details: Daily bandwidth limit reached

Free tier limit: 360 MB/day
Used today: 360 MB
Remaining: 0 MB

Resets: Tomorrow at 00:00 UTC (in 8 hours)

Action: Wait or upgrade to Blaze plan
```

**What this means:**
Hit Firebase free tier limits. Common with frequent deploys.

**Solution A: Wait for reset**
```
Quota resets in: 8 hours
[Come back tomorrow]
```

**Solution B: Upgrade to Blaze plan**
1. Go to: https://console.firebase.google.com
2. Select project
3. Click "Upgrade"
4. Select "Blaze" (pay-as-you-go)
5. Enter billing info

**Cost:** Approximately $1-5/month for normal usage

---

**Prevention:**
- Monitor Firebase usage
- Don't rebuild unnecessarily
- Use CLOUD mode (uploads from cloud, not your quota)
- Upgrade to Blaze if deploying frequently

---

## 6. SECTION 4: APP-LEVEL ISSUES

**PURPOSE:** Troubleshoot problems with built apps (crashes, bugs, performance).

---

### 6.1 APP CRASHES ON LAUNCH

**Symptom:**
Build succeeds (all stages ✅) but app crashes immediately when opened.

**Solution process:**

**Step 1: Get crash logs**

Check Telegram for automatic crash report:
```
🔴 CRASH DETECTED - FocusFlow v1.0.0

Error: TypeError: Cannot read property 'duration' of undefined
Location: Timer.jsx:47
Stack trace: [detailed trace]
```

**Step 2: Understand error**

Read error carefully. Usually indicates:
- Undefined variable
- Missing data
- Permission denied
- Network failure

**Step 3: Fix with /modify**

```
/modify [github-url]

Fix crash on app launch:

Error: TypeError at Timer.jsx:47
Root cause: Accessing 'duration' property before initialization

Fix:
- Add null check before accessing timer.duration
- Initialize with default value if undefined
- Add try-catch for error handling
```

**See detailed crash troubleshooting in Section 4 of this runbook.**

---

### 6.2 FEATURE NOT WORKING

**Symptom:**
App doesn't crash but specific feature doesn't work as expected.

**Examples:**
- Button does nothing when tapped
- Data doesn't save
- Notifications don't appear
- Payment sheet doesn't open

**Solution:**

**Step 1: Verify specification**

Review what you requested:
- Was feature clearly described?
- Did you specify behavior precisely?
- Are there edge cases?

**Step 2: Test systematically**

Test the feature:
- Does button respond at all? (visual feedback?)
- Check logs for errors
- Try different scenarios
- Test on different devices

**Step 3: Fix with /modify**

```
/modify [github-url]

Fix [feature name]:

Current behavior: [what happens now]
Expected behavior: [what should happen]
Steps to reproduce: [exact steps]

Fix needed:
[Clear description of what to fix]
```

---

**✅ SECTION 4 COMPLETE**

Common app-level issues:
- **Crashes** → Get logs, identify error, fix with /modify
- **Features not working** → Test systematically, fix specific issue
- **Performance slow** → Optimize assets, reduce complexity
- **Data loss** → Fix storage implementation

**Full app debugging covered in Section 4.4 earlier in this runbook.**

---

**[END OF PART 4]**














---

# RB2: TROUBLESHOOTING & PROBLEM RESOLUTION
## PART 5 of 6

---

## 7. SECTION 5: QUICK REFERENCE - ERROR CODE TABLE

**PURPOSE:** Fast lookup for known errors. Find your error code, jump to solution.

**How to use:**
1. Get error code from notification or logs
2. Find code in table below
3. Follow solution steps
4. If code not listed, use systematic diagnosis (Section 1)

---

### 7.1 ERROR CODE FORMAT

**Pipeline error codes follow pattern:**
```
ERRCODE_[STAGE]_[CATEGORY]_[NUMBER]

Examples:
ERRCODE_S0_PARSE_001     → S0 stage, parsing error, variant 001
ERRCODE_S4_BUILD_023     → S4 stage, build error, variant 023
ERRCODE_API_AUTH_005     → API error, authentication, variant 005
```

---

### 7.2 COMPREHENSIVE ERROR CODE TABLE

**S0 - PLANNING STAGE ERRORS**

| Error Code | Error Message | Cause | Solution | Section |
|------------|---------------|-------|----------|---------|
| ERRCODE_S0_PARSE_001 | Specification parsing failed | Missing required fields | Add platform, description, features | 4.1.1 |
| ERRCODE_S0_PARSE_002 | Platform not specified | No platform declaration | Add `platform: android/ios/web` | 4.1.3 |
| ERRCODE_S0_UNSUPPORTED_001 | Unsupported feature detected | Requested blockchain/AR/VR | Remove unsupported feature | 4.1.2 |
| ERRCODE_S0_UNSUPPORTED_002 | Feature requires backend | Real-time/server features | Simplify or use external service | 4.1.2 |
| ERRCODE_S0_CONFLICT_001 | Platform/stack mismatch | iOS + kotlin (invalid) | Use compatible stack (swift/react-native) | 4.1.3 |
| ERRCODE_S0_CONFLICT_002 | Mode incompatible with platform | iOS + LOCAL mode | Switch to CLOUD mode | 4.1.4 |
| ERRCODE_S0_TIMEOUT_001 | Planning timeout | Complex spec or API slow | Simplify spec or wait | 4.1.5 |

---

**S1 - DESIGN STAGE ERRORS**

| Error Code | Error Message | Cause | Solution | Section |
|------------|---------------|-------|----------|---------|
| ERRCODE_S1_DESIGN_001 | Design constraints conflicting | "Simple" + "20 features" | Resolve contradictions | 4.2.1 |
| ERRCODE_S1_DESIGN_002 | Color accessibility failure | White text on white background | Fix color contrast | 4.2.1 |
| ERRCODE_S1_SCREEN_001 | Screen count exceeds limit | 25+ screens requested | Reduce to 8-12 screens | 4.2.2 |
| ERRCODE_S1_TIMEOUT_001 | Design timeout | Too detailed UI specs | Simplify, remove pixel-perfect specs | 4.2.3 |

---

**S2 - CODE GENERATION STAGE ERRORS**

| Error Code | Error Message | Cause | Solution | Section |
|------------|---------------|-------|----------|---------|
| ERRCODE_S2_IMPL_001 | Feature implementation failed | Real-time collaboration | Simplify to periodic sync | 4.3.1 |
| ERRCODE_S2_IMPL_002 | Server infrastructure required | Custom backend needed | Use Firebase or external API | 4.3.1 |
| ERRCODE_S2_TIMEOUT_001 | Code generation timeout | 20+ features, 2000+ words | Reduce features, simplify spec | 4.3.2 |
| ERRCODE_S2_DEPEND_001 | Dependency conflict | Incompatible library versions | Remove version requirements | 4.3.3 |
| ERRCODE_S2_DEPEND_002 | Multiple similar services | Firebase + OneSignal both requested | Choose one service | 4.3.3 |

---

**S3 - TESTING STAGE ERRORS**

| Error Code | Error Message | Cause | Solution | Section |
|------------|---------------|-------|----------|---------|
| ERRCODE_S3_TEST_001 | Tests failed - X/Y passed | Code bugs from unclear spec | Review failed tests, fix with /modify | 4.4.1 |
| ERRCODE_S3_TEST_002 | Data persistence test failed | AsyncStorage not configured | Add storage initialization | 4.4.1 |
| ERRCODE_S3_TEST_003 | Notification test failed | Permission not requested | Add permission request | 4.4.1 |
| ERRCODE_S3_SEC_001 | Critical security vulnerability | Hardcoded API key | Move to environment variables | 4.4.2 |
| ERRCODE_S3_SEC_002 | eval() usage detected | Dynamic code execution | Remove feature or use safe parser | 4.4.2 |
| ERRCODE_S3_SEC_003 | SQL injection vulnerability | Unsanitized user input | Use parameterized queries | 4.4.2 |
| ERRCODE_S3_QUAL_001 | Code quality below threshold | Complex, duplicated code | Let proceed, improve in v1.1 | 4.4.3 |

---

**S4 - BUILD STAGE ERRORS**

| Error Code | Error Message | Cause | Solution | Section |
|------------|---------------|-------|----------|---------|
| ERRCODE_S4_MEM_001 | Out of memory | <8GB RAM, LOCAL mode | Switch to HYBRID/CLOUD mode | 4.5.1 |
| ERRCODE_S4_MEM_002 | Java heap space exceeded | Gradle memory limit | Close apps or increase heap size | 4.5.1 |
| ERRCODE_S4_IOS_001 | Xcode signing failed | No Apple certificates | Complete iOS setup | 4.5.2 |
| ERRCODE_S4_IOS_002 | Provisioning profile not found | Profile not created | Create in Apple Developer portal | 4.5.2 |
| ERRCODE_S4_TIMEOUT_001 | Build timeout | Stuck on asset optimization | Reduce asset sizes, retry | 4.5.3 |
| ERRCODE_S4_GRADLE_001 | Gradle build failed | Code compilation error | Report bug or simplify spec | 4.5.4 |
| ERRCODE_S4_GRADLE_002 | Dependency resolution failed | Conflicting versions | Let pipeline choose versions | 4.5.4 |
| ERRCODE_S4_WEB_001 | Firebase deployment failed | Slow upload, large build | Switch to CLOUD, reduce size | 4.5.5 |

---

**S5 - QUALITY CHECK STAGE ERRORS**

| Error Code | Error Message | Cause | Solution | Section |
|------------|---------------|-------|----------|---------|
| ERRCODE_S5_SEC_001 | Critical vulnerability - eval() | Dynamic code execution | Remove feature, use safe alternative | 4.6.1 |
| ERRCODE_S5_SEC_002 | Weak hash algorithm | MD5 for passwords | Specify bcrypt/Argon2 | 4.6.2 |
| ERRCODE_S5_SEC_003 | Insecure HTTP connection | HTTP instead of HTTPS | Update to HTTPS URLs | 4.6.2 |

---

**S6 - DEPLOYMENT STAGE ERRORS**

| Error Code | Error Message | Cause | Solution | Section |
|------------|---------------|-------|----------|---------|
| ERRCODE_S6_GIT_001 | GitHub authentication failed | Token expired/invalid | Generate new token, update config | 4.7.1 |
| ERRCODE_S6_GIT_002 | Repository already exists | Duplicate repository name | Delete old repo or rename app | 4.7.2 |
| ERRCODE_S6_GIT_003 | Push rejected | Branch protected | Remove branch protection | 5.2.1 |
| ERRCODE_S6_FIREBASE_001 | Firebase upload timeout | Slow connection, large app | Use CLOUD mode, reduce size | 4.7.3 |
| ERRCODE_S6_FIREBASE_002 | Firebase quota exceeded | Daily limit reached | Wait or upgrade to Blaze | 5.3.1 |

---

**S7 - MONITORING STAGE ERRORS**

| Error Code | Error Message | Cause | Solution | Section |
|------------|---------------|-------|----------|---------|
| ERRCODE_S7_SENTRY_001 | Sentry configuration failed | No DSN configured | Create Sentry account, add DSN | 4.8.1 |
| ERRCODE_S7_ANALYTICS_001 | Analytics incomplete | Custom events not configured | Proceed, add custom events in v1.1 | 4.8.2 |

---

**API / SERVICE ERRORS**

| Error Code | Error Message | Cause | Solution | Section |
|------------|---------------|-------|----------|---------|
| ERRCODE_API_AUTH_001 | Anthropic API key invalid | Wrong/expired key | Get new key from console.anthropic.com | 5.1.2 |
| ERRCODE_API_RATE_001 | Rate limit exceeded | Too many requests | Wait for reset or upgrade tier | 5.1.1 |
| ERRCODE_API_TIMEOUT_001 | API timeout | Network or API slow | Retry, check status.anthropic.com | 5.1.1 |

---

### 7.3 SYMPTOM-BASED LOOKUP

**Don't have error code? Find by symptom:**

| Symptom | Likely Cause | Quick Check | Go To |
|---------|-------------|-------------|-------|
| Pipeline won't start | Config issue, port conflict | Check logs, try different port | Section 11.1 |
| All builds failing | Service disconnected | `/status` check services | Section 1 |
| Builds slow (>60 min) | LOW memory, wrong mode | Check RAM, switch to HYBRID | 4.5.1 |
| Builds fail at same stage | Systematic issue | Review error for that stage | Section 2 |
| iOS builds fail | Not set up | Apple Developer setup needed | 4.5.2 |
| App crashes on launch | Code bug | Get crash logs from Sentry/Telegram | 6.1 |
| Feature doesn't work | Unclear spec | Review spec, fix with /modify | 6.2 |
| GitHub errors | Token expired | Generate new token | 4.7.1 |
| Costs too high | Wrong mode | Switch to LOCAL/HYBRID | Section 11.4 |
| Can't install app | Signing issue | Check certificates | 4.5.2 |

---

### 7.4 DECISION TREES

**DECISION TREE A: Build Failed - What To Do?**

```
Build failed
│
├─ Which stage?
│  │
│  ├─ S0 (Planning)
│  │  └─ Specification issue → Fix spec, retry
│  │
│  ├─ S1 (Design)  
│  │  └─ Too complex → Simplify screens/features
│  │
│  ├─ S2 (Code Gen)
│  │  └─ Unsupported feature → Remove or simplify
│  │
│  ├─ S3 (Testing)
│  │  └─ Tests failed → Review failures, fix issues
│  │
│  ├─ S4 (Build) **MOST COMMON**
│  │  ├─ Out of memory? → Switch to HYBRID/CLOUD
│  │  ├─ iOS signing? → Complete Apple setup
│  │  ├─ Timeout? → Reduce assets, check network
│  │  └─ Gradle error? → Simplify spec, report bug
│  │
│  ├─ S5 (Quality)
│  │  └─ Security issue → Fix vulnerability, retry
│  │
│  ├─ S6 (Deployment)
│  │  ├─ GitHub? → Fix token/permissions
│  │  └─ Firebase? → Check connection/quota
│  │
│  └─ S7 (Monitoring)
│     └─ Can proceed → Continue, fix monitoring later
```

---

**DECISION TREE B: Should I Retry or Rebuild?**

```
Build failed
│
├─ Error says "retry"?
│  ├─ YES → Retry once
│  │   ├─ Succeeds? ✅ Done
│  │   └─ Fails again? → Investigate root cause
│  │
│  └─ NO → Check error type
│
├─ Transient error? (timeout, network)
│  ├─ YES → Retry 2-3 times
│  └─ NO → Continue
│
├─ Configuration error? (auth, permissions)
│  ├─ YES → Fix config, then retry
│  └─ NO → Continue
│
├─ Specification error? (unsupported feature)
│  ├─ YES → Fix spec, rebuild from scratch
│  └─ NO → Continue
│
└─ Unknown/unclear?
   └─ Try retry once
       ├─ Succeeds? ✅ Lucky!
       └─ Fails? → Systematic diagnosis
```

---

**DECISION TREE C: Is This Critical?**

```
Problem occurred
│
├─ Does it block ALL builds?
│  ├─ YES → CRITICAL - fix immediately
│  └─ NO → Continue
│
├─ Does it block CURRENT build?
│  ├─ YES → HIGH - fix within hours
│  └─ NO → Continue
│
├─ Does it affect production users?
│  ├─ YES → HIGH - fix within hours
│  └─ NO → Continue
│
├─ Is it just cosmetic/minor?
│  ├─ YES → LOW - fix when convenient
│  └─ NO → MEDIUM - fix within days
```

---

## 8. SECTION 6: ESCALATION PATH

**PURPOSE:** Know when to get help and how to ask effectively.

---

### 8.1 WHEN TO ESCALATE

**Try self-service troubleshooting FIRST if:**
- ✅ Error is in this runbook
- ✅ Solution is documented
- ✅ You have time to troubleshoot (30+ min)
- ✅ Issue is non-critical

**Escalate to support if:**
- ❌ Tried all documented solutions (spent 2+ hours)
- ❌ Error not in this runbook
- ❌ Pipeline appears to have bug
- ❌ CRITICAL issue affecting production
- ❌ Data loss or security incident
- ❌ Suspected service outage

---

### 8.2 SELF-SERVICE CHECKLIST

**Before escalating, complete this checklist:**

□ **Read error message completely**
- Not just first line
- Include details, stack traces
- Copy exact text

□ **Checked this runbook**
- Looked up error code in Section 5
- Read relevant stage section (Section 2)
- Tried documented solutions

□ **Verified basic configuration**
- `/status` shows RUNNING
- All services connected
- API keys valid

□ **Tried obvious fixes**
- Restarted pipeline
- Retried build
- Checked internet connection

□ **Gathered information**
- Error messages (exact text)
- Build ID
- Logs (`/logs recent`)
- Specification (if build-related)
- Timeline (when it started)

□ **Attempted workaround**
- If possible, found alternative approach
- Documented what doesn't work

**If all checked and still stuck → Escalate**

---

### 8.3 HOW TO REPORT ISSUES EFFECTIVELY

**Good bug reports get faster responses.**

**Template for issue reports:**

```
ISSUE REPORT

**Summary:**
[One-sentence description]

**Error Code:** ERRCODE_S4_MEM_001 (if applicable)

**Severity:** [CRITICAL/HIGH/MEDIUM/LOW]

**What I Was Trying To Do:**
[Describe the goal - e.g., "Build Android app for habit tracking"]

**What Happened:**
[Exact error, unexpected behavior]

**Expected Behavior:**
[What should have happened]

**Steps To Reproduce:**
1. [First step]
2. [Second step]
3. [Error occurs]

**Error Messages:**
```
[Paste exact error text]
```

**Environment:**
- Pipeline version: [Check with /version]
- Execution mode: [CLOUD/LOCAL/HYBRID]
- Platform: [iOS/Android/Web]
- Operating System: [macOS 13.0, Windows 11, Ubuntu 22.04]
- Build ID: [From error or /status]

**Logs:**
```
[Paste relevant logs from /logs recent]
```

**What I've Tried:**
1. [Solution 1] - Result: [didn't work / partial success]
2. [Solution 2] - Result: [didn't work / partial success]
3. [Checked runbook section X.Y]

**Specification (if build-related):**
[Paste specification or attach file]

**Additional Context:**
[Anything else relevant - timing, patterns, recent changes]
```

---

**Example GOOD bug report:**

```
ISSUE REPORT

**Summary:**
S4 build fails with out-of-memory error even after switching to CLOUD mode

**Error Code:** ERRCODE_S4_MEM_001

**Severity:** HIGH (blocking current work)

**What I Was Trying To Do:**
Build Android app (habit tracker) in CLOUD mode to avoid memory issues

**What Happened:**
Build fails at S4 with "Out of memory" error even though using CLOUD mode (which should have unlimited memory)

**Expected Behavior:**
CLOUD mode builds should not have memory constraints

**Steps To Reproduce:**
1. Set mode: /config execution_mode CLOUD
2. Restart: /restart
3. Build: /create [specification]
4. Build fails at S4 after 12 minutes with memory error

**Error Messages:**
```
❌ S4 FAILED - Build
Error: Build process out of memory
Java heap space exceeded
Build process attempted to use: 4.2 GB RAM
```

**Environment:**
- Pipeline version: 5.8.0
- Execution mode: CLOUD
- Platform: Android
- Operating System: macOS 13.2
- Build ID: build_20260303_142315

**Logs:**
```
[S4] Starting Android build (CLOUD mode)
[S4] Gradle compilation: 0%
[S4] Gradle compilation: 25%
[S4] Gradle compilation: 50%
[S4] ERROR: Java heap space exceeded
[S4] Build failed
```

**What I've Tried:**
1. Switched from LOCAL to CLOUD mode - still fails
2. Restarted pipeline - same error
3. Reduced app complexity (removed 5 features) - still fails
4. Checked Section 4.5.1 - says CLOUD mode should resolve this

**Specification:**
[Attached: focusflow-spec.txt - 450 words, 8 features, standard Android app]

**Additional Context:**
- This is my third attempt to build this app
- First two attempts were in LOCAL mode (expected memory errors)
- CLOUD mode was supposed to fix this but error message still mentions local memory
- Wondering if CLOUD mode isn't actually being used?
```

**This report will get fast, helpful response because:**
- ✅ Clear, specific summary
- ✅ All relevant information included
- ✅ Shows what was already tried
- ✅ Includes error messages and logs
- ✅ Specification attached
- ✅ Environment details complete

---

**Example BAD bug report:**

```
help! it doesn't work

tried to build an app and it failed. error at s4. 
please fix asap this is urgent!!!
```

**This report will get slow response because:**
- ❌ No details about what failed
- ❌ No error messages
- ❌ No information about environment
- ❌ No indication of what was tried
- ❌ No specification
- ❌ Just "doesn't work" - not actionable

---

### 8.4 WHERE TO GET HELP

**Option 1: GitHub Issues (recommended)**

**For:**
- Bug reports
- Feature requests
- General troubleshooting
- Non-urgent issues

**How:**
1. Go to: [pipeline-github-url]/issues
2. Search existing issues first
3. If not found, click "New Issue"
4. Choose template: "Bug Report" or "Help Needed"
5. Fill out template completely
6. Submit

**Response time:** 
- Critical bugs: 2-6 hours
- Normal issues: 24-48 hours
- Enhancements: When scheduled

---

**Option 2: Community Discord/Slack**

**For:**
- Quick questions
- General discussion
- Sharing solutions
- Learning from others

**How:**
1. Join community: [invite-link]
2. Post in #troubleshooting channel
3. Include key details (error, platform, what you tried)

**Response time:**
- Active hours: 15-60 minutes
- Off-hours: 2-6 hours

---

**Option 3: Direct Email Support (paid plans only)**

**For:**
- Critical production issues
- Security incidents
- Account/billing issues
- Private/confidential issues

**How:**
1. Email: support@[pipeline-domain]
2. Subject: [CRITICAL] or [HIGH] [Brief description]
3. Include bug report template info
4. Attach relevant files

**Response time:**
- CRITICAL: 1-2 hours (24/7)
- HIGH: 4-8 hours (business hours)
- MEDIUM: 24 hours

---

**Option 4: Emergency Escalation (CRITICAL only)**

**For CRITICAL issues ONLY:**
- Production down affecting users
- Security breach
- Data loss
- Complete pipeline failure

**How:**
1. Email: emergency@[pipeline-domain]
2. Subject: [EMERGENCY] [Description]
3. Include:
   - Phone number for callback
   - Account details
   - Impact assessment (# users affected)
   - What you've tried

**Response time:** 30 minutes (24/7)

**Note:** False emergencies may result in fees. Use only for genuine critical issues.

---

### 8.5 WHAT HAPPENS AFTER ESCALATION

**Typical escalation flow:**

**1. Issue Triaged (within hours)**
- Support reviews your report
- Assigns severity
- Routes to appropriate team
- May ask clarifying questions

**2. Investigation (hours to days)**
- Team reproduces issue
- Analyzes logs and code
- Identifies root cause
- Develops fix

**3. Resolution Provided**
- Bug fix in next pipeline update (days to weeks)
- Workaround provided immediately (if available)
- Configuration change (immediate)
- Documentation update (if needed)

**4. Follow-Up**
- Issue marked resolved
- Release notes mention fix
- You're notified
- Issue closed

---

### 8.6 HELPING YOURSELF WHILE WAITING

**While waiting for response:**

**Option A: Find workaround**
- Can you build for different platform?
- Can you simplify specification?
- Can you use different execution mode?
- Can you remove problematic feature?

**Option B: Continue with other work**
- Build different app
- Update existing apps
- Test apps you've already built
- Plan future apps

**Option C: Learn more**
- Read other runbooks
- Study specification examples
- Explore pipeline features
- Join community discussions

**Option D: Contribute**
- Document your issue for others
- Share workaround in community
- Help others with similar issues
- Improve documentation

---

**✅ SECTIONS 5 & 6 COMPLETE**

You now have:
- ✅ Comprehensive error code lookup table
- ✅ Symptom-based troubleshooting guide
- ✅ Decision trees for common scenarios
- ✅ Escalation criteria and procedures
- ✅ Effective bug reporting template
- ✅ Support channel navigation

**Next (Part 6 - FINAL):**
- Complete troubleshooting examples
- Prevention strategies
- Next steps

---

**[END OF PART 5]**














---

# RB2: TROUBLESHOOTING & PROBLEM RESOLUTION
## PART 6 of 6 (FINAL)

---

## 9. REAL-WORLD TROUBLESHOOTING EXAMPLES

**PURPOSE:** See complete troubleshooting processes from problem to solution.

**Learn from these examples:**
- How to apply systematic diagnosis
- Common mistake patterns
- Effective solution approaches
- Prevention insights

---

### 9.1 EXAMPLE 1: "My iOS Build Keeps Failing"

**Initial Problem Report:**

```
User: Alex
Date: March 3, 2026
Issue: "iOS build fails every time at S4, Android works fine"

Error message:
❌ S4 FAILED - Build
Error: Xcode signing failed
"No profiles for 'com.alex.habittracker' were found"
```

---

**Troubleshooting Process:**

**Step 1: Systematic diagnosis (Section 1)**

**What's wrong:** iOS build fails at S4 (build stage)
**Stage:** S4
**Platform:** iOS
**Mode:** CLOUD (required for iOS)
**Reproducible:** Yes, fails every time

---

**Step 2: Identify error type**

Error mentions: "Xcode signing failed" + "No profiles found"

**Look up in Section 5.2 (Error Code Table):**
```
ERRCODE_S4_IOS_001: Xcode signing failed
Cause: No Apple certificates
Solution: Complete iOS setup
Go to: Section 4.5.2
```

---

**Step 3: Read Section 4.5.2**

**Root cause identified:**
- iOS apps require Apple Developer account ($99/year)
- Need certificates and provisioning profiles
- Alex hasn't set this up yet

---

**Step 4: Solution choice**

**Option A:** Complete iOS setup (60 min, $99/year)
**Option B:** Build for Android instead (works now, proven)

**Alex's decision:** Start with Android (faster, cheaper, already working)

Later add iOS after Android version successful.

---

**Solution applied:**

```
Instead of:
/create
platform: ios
stack: swift

Changed to:
/create
platform: android
stack: react-native

[Same specification otherwise]
```

**Result:** ✅ Build succeeded in 28 minutes

---

**Prevention for future:**

Alex documented:
```
FOR iOS BUILDS:
1. Complete Apple Developer setup first (see Section 4.5.2)
2. Budget $99/year for account
3. Allow 60 min for initial setup
4. Or: Build Android first, add iOS later (my approach)

LESSON: iOS has prerequisites. Check before building.
```

**Later (Week 2):** Alex completed iOS setup, successfully built iOS version.

---

**Key Takeaways:**
- ✅ Used error code to find exact section
- ✅ Chose pragmatic workaround (Android first)
- ✅ Documented for future
- ✅ Came back to iOS when ready
- ✅ Total time lost: 15 min (vs hours if kept trying iOS blindly)

---

### 9.2 EXAMPLE 2: "Build Succeeds But App Crashes"

**Initial Problem Report:**

```
User: Jordan
Date: March 5, 2026
Issue: "Build completes successfully (all stages ✅) but app crashes immediately when opened"

Platform: Android
Error from Sentry:
TypeError: Cannot read property 'map' of undefined
Location: TaskList.jsx:34
```

---

**Troubleshooting Process:**

**Step 1: Understand the issue**

**What's wrong:** App built fine, crashes at runtime
**Stage:** Post-build (app-level issue)
**Error type:** JavaScript error - undefined variable

This is NOT a build failure - it's a code bug.

---

**Step 2: Get complete error context**

Jordan checked Sentry dashboard:
```
Error: Cannot read property 'map' of undefined
File: TaskList.jsx
Line: 34

Code context:
32: const TaskList = ({ tasks }) => {
33:   return (
34:     tasks.map(task => (
35:       <TaskItem key={task.id} task={task} />
36:     ))
37:   );
38: };

Stack trace:
  at TaskList (TaskList.jsx:34)
  at App.render (App.jsx:15)
```

---

**Step 3: Analyze the bug**

**Translation to plain English:**

Line 34 tries to use `tasks.map()` but `tasks` is undefined.

**Why is tasks undefined?**

Looking at specification:
```
Feature: Task list
- Display all user's tasks
- Fetch tasks from local storage on app launch
```

**Problem:** App tries to display tasks BEFORE fetching from storage.

On first launch, no tasks exist yet → `tasks` is undefined → crash.

---

**Step 4: Solution**

Use `/modify` to fix:

```
/modify https://github.com/jordan/tasktracker

Fix crash on app launch:

Error: TypeError at TaskList.jsx:34
Cannot read property 'map' of undefined

Root cause:
- App tries to display tasks before loading from storage
- On first launch, tasks is undefined
- Code doesn't check if tasks exists before mapping

Fix needed:
1. Initialize tasks as empty array (not undefined)
2. Add null check before mapping
3. Show "No tasks yet" message if array is empty
4. Load tasks from storage on component mount
5. Handle case where storage is empty (first launch)

Example safe code pattern:
```javascript
const TaskList = ({ tasks = [] }) => {  // Default to empty array
  if (!tasks || tasks.length === 0) {
    return <Text>No tasks yet. Add your first task!</Text>;
  }
  
  return tasks.map(task => (
    <TaskItem key={task.id} task={task} />
  ));
};
```
```

---

**Step 5: Test the fix**

Pipeline rebuilt app with fixes (v1.0.1).

Jordan tested:
1. ✅ Fresh install - app opens, shows "No tasks yet"
2. ✅ Add first task - displays correctly
3. ✅ Close app, reopen - task persists
4. ✅ Add 10 tasks - all display correctly

**Result:** ✅ Bug fixed

---

**Prevention for future:**

Jordan updated specification template:
```
DEFENSIVE CODING REQUIREMENTS:
- Initialize all arrays/objects with defaults
- Add null/undefined checks before using data
- Handle empty states gracefully (show helpful messages)
- Test app from fresh install (no existing data)
- Never assume data exists - check first

Example:
✅ const tasks = loadTasks() || [];
❌ const tasks = loadTasks(); // might be undefined
```

**Result:** Next app didn't have this crash pattern.

---

**Key Takeaways:**
- ✅ Crash logs showed exact problem location
- ✅ Analyzed code context to understand cause
- ✅ Fixed with defensive coding patterns
- ✅ Updated specification template to prevent recurrence
- ✅ Time to fix: 45 minutes (diagnosis + fix + test)

---

### 9.3 EXAMPLE 3: "Builds Are Extremely Slow"

**Initial Problem Report:**

```
User: Sam
Date: March 7, 2026
Issue: "Builds taking 60-90 minutes, documentation says 25-40 minutes"

Details:
- Building Android apps
- LOCAL mode
- Every build slow, not just one
- S4 stage takes 40-50 minutes alone
```

---

**Troubleshooting Process:**

**Step 1: Gather baseline information**

Sam checked:
```
/status

Pipeline Status: ✅ RUNNING
Mode: LOCAL
CPU: 85-95% (very high during builds)
Memory: 7.2GB / 8GB (90% - very high)
```

**Computer specs:**
- 8GB RAM
- Intel i5 (4 years old)
- Windows 10
- Multiple apps always running

---

**Step 2: Compare to expected performance**

**Expected S4 timing:**
- LOCAL mode Android: 8-12 minutes
- Sam's S4: 40-50 minutes (4x slower)

**Diagnosis:** System resource constraints.

---

**Step 3: Identify resource bottleneck**

**During build, Sam checked Task Manager:**
```
CPU: 100% constantly
Memory: 7.8GB / 8GB (97%)

Memory usage:
- Pipeline build: 2.5 GB
- Chrome (20 tabs): 1.8 GB
- Slack: 0.9 GB
- Docker Desktop: 1.2 GB
- Spotify: 0.3 GB
- VS Code: 0.6 GB
- Other: 0.5 GB
```

**Problem identified:** 
- Only 8GB RAM total
- 5.3GB used by other apps
- Leaves 2.7GB for build (needs 4GB+)
- System constantly swapping to disk (very slow)

---

**Step 4: Solution options**

**Option A: Close other apps (immediate, free)**

Sam tried:
```
Closed:
- Chrome (saved tabs)
- Slack  
- Docker
- Spotify
- VS Code

Memory after: 3.1GB / 8GB (39%)
Available for build: 4.9 GB
```

**Retry build:**
- S4 completed in 18 minutes (was 45 min)
- Total build: 35 minutes (was 75 min)

**Result:** ✅ Much better! Still slower than ideal but usable.

---

**Option B: Switch to HYBRID mode (costs $0.20)**

For even better performance:
```
/config execution_mode HYBRID
/restart

[Build again]
```

**Result:**
- S4 completed in 12 minutes
- Total build: 28 minutes
- Cost: $0.20 per build

**Sam's decision:** Use HYBRID for important builds, LOCAL with apps closed for testing.

---

**Option C: Upgrade RAM (long-term, ~$50)**

Sam researched:
- 16GB RAM upgrade: ~$50
- Would solve problem permanently
- Better for other work too

**Sam's plan:** Upgrade RAM next month, use HYBRID mode until then.

---

**Prevention:**

Sam created build checklist:
```
BEFORE BUILDING:

If using LOCAL mode:
□ Close Chrome (or limit to 5 tabs)
□ Close Slack
□ Close Docker if not needed
□ Close music/video apps
□ Close extra code editors

If need other apps open:
□ Use HYBRID mode ($0.20) instead

Future: Upgrade to 16GB RAM
```

---

**Key Takeaways:**
- ✅ Identified resource constraint as root cause
- ✅ Tried cheapest solution first (close apps)
- ✅ Used paid mode when needed (HYBRID)
- ✅ Planned long-term fix (RAM upgrade)
- ✅ Created prevention checklist
- ✅ Time to diagnose: 20 minutes

---

### 9.4 EXAMPLE 4: "Pipeline Won't Start After Update"

**Initial Problem Report:**

```
User: Casey
Date: March 10, 2026
Issue: "Updated pipeline from v5.5 to v5.8, now won't start"

Error:
$ python -m factory.cli start
ModuleNotFoundError: No module named 'anthropic'
```

---

**Troubleshooting Process:**

**Step 1: Understand what changed**

**Timeline:**
- Yesterday: Pipeline v5.5 working fine
- Today: Updated to v5.8
- Now: Won't start

**Error:** Missing Python module.

**Likely cause:** Update changed dependencies.

---

**Step 2: Check what update requires**

Casey checked changelog:
```
v5.8 Changelog:

NEW FEATURES:
- Improved S4 build performance
- Better error messages

BREAKING CHANGES:
- Requires Python 3.11+ (was 3.10+)
- Updated dependencies (see requirements.txt)

MIGRATION:
Run: pip install -r requirements.txt --upgrade --break-system-packages
```

**Problem identified:** Dependencies not updated after version upgrade.

---

**Step 3: Solution**

**Reinstall dependencies:**
```bash
cd ~/ai-factory-pipeline
pip install -r requirements.txt --upgrade --break-system-packages
```

**Output:**
```
Installing collected packages:
- anthropic (upgraded 0.21.0 -> 0.25.0)
- firebase-admin (upgraded 6.0.0 -> 6.2.0)
- github3.py (new dependency)
[... more packages ...]

Successfully installed 23 packages
```

---

**Step 4: Verify Python version**

```bash
python --version
```

**Output:** Python 3.10.8

**Problem:** v5.8 requires Python 3.11+

---

**Step 5: Update Python**

**macOS (using Homebrew):**
```bash
brew update
brew upgrade python
```

**Windows:**
1. Download Python 3.11+ from python.org
2. Run installer
3. Select "Add to PATH"

**Linux:**
```bash
sudo apt update
sudo apt install python3.11
```

---

**Step 6: Reinstall dependencies with new Python**

```bash
python3.11 -m pip install -r requirements.txt --break-system-packages
```

---

**Step 7: Start pipeline**

```bash
python3.11 -m factory.cli start
```

**Output:**
```
AI Factory Pipeline v5.8
Starting services...
✅ Core engine started
✅ Telegram bot connected
✅ External services verified
Pipeline is RUNNING
```

**Result:** ✅ Working!

---

**Step 8: Verify with Telegram**

```
/status

Pipeline Status: ✅ RUNNING
Version: 5.8.0 ✅ (was 5.5.0)
```

---

**Prevention:**

Casey documented update procedure:
```
PIPELINE UPDATE CHECKLIST:

1. Read changelog completely BEFORE updating
2. Check breaking changes
3. Note required Python/dependency versions
4. Update Python if needed
5. Run: pip install -r requirements.txt --upgrade
6. Test with /status before building
7. Keep old version backed up (just in case)

Lesson: Read changelog carefully!
Breaking changes = extra steps needed
```

---

**Key Takeaways:**
- ✅ Changelog provided exact solution
- ✅ Checked Python version (often overlooked)
- ✅ Updated dependencies properly
- ✅ Verified working before building
- ✅ Created update checklist for future
- ✅ Time to fix: 30 minutes

---

## 10. PREVENTION BEST PRACTICES

**PURPOSE:** Prevent problems before they happen.

**Philosophy:** "An ounce of prevention is worth a pound of cure."

---

### 10.1 SPECIFICATION QUALITY

**Problem prevented:** 60-70% of build failures stem from unclear specifications.

**Best practices:**

**1. Use specification templates**

Don't start from blank page:
```
✅ Use template from NB5 or RB1
✅ Fill in all sections
✅ Don't skip "optional" sections (they help)
```

**2. Be extremely specific**

```
❌ Vague:
"Feature: Timer functionality"

✅ Specific:
"Feature: Pomodoro timer
- Default duration: 25 minutes
- User can adjust: 1-120 minutes
- Counts down to 00:00
- Plays sound when complete
- Continues in background
- Shows notification with time remaining
- Pauses on phone call
- Saves state if app closed"
```

**3. Define error handling explicitly**

```
Include in every specification:

ERROR HANDLING:
- Validate all user inputs (show error messages for invalid)
- Handle network failures gracefully (retry, show offline mode)
- Never crash - show error message instead
- Log errors to Sentry for debugging
- Provide helpful error messages to users
```

**4. Specify defaults for everything**

```
❌ "User can set timer duration"

✅ "User can set timer duration
    - Default: 25 minutes if not set
    - Minimum: 1 minute
    - Maximum: 120 minutes
    - Step: 1 minute increments
    - If invalid: Use default, show error"
```

**5. Review before submitting**

Checklist:
□ All required fields completed?
□ Features clearly described?
□ Edge cases handled?
□ Error handling specified?
□ Defaults provided?
□ No contradictions?
□ Under 1000 words? (for initial version)

---

### 10.2 SYSTEM MAINTENANCE

**Problem prevented:** System degradation, resource exhaustion, certificate expiration.

**Best practices:**

**1. Weekly cleanup (10 min)**

```bash
# Run every Friday
/cleanup builds --older-than 30-days
/cleanup logs --older-than 60-days
```

Prevents:
- Disk full errors
- Slow builds
- Cannot find files

---

**2. Monthly dependency updates (20 min)**

```bash
# First Monday of month
cd ~/ai-factory-pipeline
pip install -r requirements.txt --upgrade --break-system-packages
npm update -g
```

Prevents:
- Security vulnerabilities
- Incompatibility issues
- Deprecated package warnings

---

**3. Quarterly certificate/token renewal (15 min)**

Set calendar reminders:
- Day 80 of GitHub token (renew before 90-day expiry)
- 30 days before Apple Developer renewal
- Check Sentry/Firebase quota usage

Prevents:
- Authentication failures mid-build
- Service disruptions
- Quota exceeded errors

---

**4. Monitor system resources**

```
Daily quick check:
/status

Look for:
- CPU > 80% when idle → Close apps
- Memory > 85% → Restart computer
- Disk < 20GB free → Clean up
```

Prevents:
- Out of memory errors
- Slow performance
- Build failures

---

### 10.3 BUILD PRACTICES

**Problem prevented:** Failed builds, wasted time, unnecessary costs.

**Best practices:**

**1. Start with MVP**

```
v1.0: 5-8 core features
✅ Fast to build (25-30 min)
✅ Easy to test
✅ Can launch quickly

Later: Add features via /modify
✅ Incremental complexity
✅ Each version tested
✅ Lower risk
```

Prevents:
- Overwhelming complexity
- Long build times
- Testing difficulties
- Bug proliferation

---

**2. Evaluate before building**

```
For EVERY new app:
/evaluate [specification]

Only build if score > 70
```

**Time saved:** 30 minutes per rejected idea
**Cost saved:** $0-1.20 per avoided bad build

Prevents:
- Building unmarketable apps
- Wasting resources on doomed ideas
- Specification problems caught early

---

**3. Test immediately after build**

```
Build completes → Test within 1 hour

Don't:
❌ Queue next build immediately
❌ Build 5 apps, test later
❌ Assume it works
```

**Why:** Find bugs while context fresh.

Prevents:
- Forgetting what you built
- Multiple apps with same bug
- Bugs reaching users

---

**4. Use appropriate execution mode**

```
Decision matrix:

iOS → CLOUD (no choice)
Android (testing) → LOCAL (free)
Android (production) → HYBRID (reliable, cheap)
Web (simple) → LOCAL (free)
Web (production) → CLOUD (reliable)
```

Prevents:
- Unnecessary costs
- Memory errors
- Slow builds

---

**5. Version management discipline**

```
Naming convention:
MAJOR.MINOR.PATCH

1.0.0 → Initial launch
1.0.1 → Bug fixes
1.1.0 → New features
2.0.0 → Major changes

Document in CHANGELOG.md
Tag in GitHub releases
```

Prevents:
- Version confusion
- Can't track what changed
- Difficult rollbacks

---

### 10.4 COST CONTROL

**Problem prevented:** Unexpected bills, budget overruns.

**Best practices:**

**1. Daily cost monitoring**

```
Every morning:
/cost today

Set alert if > daily budget
```

**2. Use FREE options first**

```
Development/testing:
✅ LOCAL mode (Android/Web)
✅ Multiple evaluations (free)
✅ Firebase free tier

Production:
✅ HYBRID mode (Android - $0.20)
✅ CLOUD only when needed (iOS - $1.20)
```

**3. Batch operations**

```
Instead of:
Build → Test → Fix → Build → Test → Fix
(4 builds = $0.80-4.80)

Do:
Plan → Build → Test thoroughly → Fix all → Build once
(2 builds = $0.40-2.40)

Saves: 50% on build costs
```

**4. Monitor API usage**

```
Weekly:
/cost week --detailed

Look for:
- Excessive evaluation requests
- Failed builds (still cost money)
- Unnecessary rebuilds
```

**5. Set monthly budget**

```
/config monthly_budget 30

Pipeline warns when approaching limit:
⚠️ Budget: $28/$30 (93%)
```

Prevents:
- Surprise bills
- Runaway costs
- Budget overruns

---

### 10.5 DOCUMENTATION HABITS

**Problem prevented:** Repeated mistakes, lost knowledge, inefficiency.

**Best practices:**

**1. Document every fix**

```
After EVERY problem resolution:

[DATE] [PROBLEM] → [SOLUTION] [TIME]

2026-03-10 S4 memory error → HYBRID mode 20min
```

**Benefit:** Next time, instant solution from your notes.

---

**2. Update specification templates**

```
After fixing same bug in 3 apps:

Update template to prevent in future:

TEMPLATE ADDITION:
"Always validate user input before processing"
```

**Benefit:** Future apps don't have same bugs.

---

**3. Create personal runbook**

```
MY COMMON ISSUES:

Issue: GitHub token expires
Fix: Renew at github.com/settings/tokens
Reminder: Day 80 of 90

Issue: Out of memory (LOCAL mode)
Fix: Close Chrome, Slack, Docker
Or: Use HYBRID mode ($0.20)

Issue: App crashes on fresh install
Fix: Always initialize with defaults
```

**Benefit:** Faster troubleshooting from your own experience.

---

**4. Share solutions**

```
Found solution not in runbook?

Post to:
- GitHub issues (helps others)
- Community Discord (quick sharing)
- Update documentation (contribute)
```

**Benefit:** 
- Helps community
- Improves documentation
- You get help when you need it

---

## 11. SUMMARY & NEXT STEPS

### 11.1 What You've Learned

**Core Troubleshooting Skills:**

✅ **Systematic diagnosis process**
- 6-step methodology for any problem
- Information gathering framework
- Severity classification
- Solution approach selection

✅ **Stage-by-stage expertise**
- S0-S7 failure patterns
- Root cause identification
- Specific fix procedures
- Prevention strategies

✅ **Service troubleshooting**
- Anthropic API issues
- GitHub authentication
- Firebase deployment
- GCP infrastructure

✅ **App-level debugging**
- Crash analysis
- Feature debugging
- Performance optimization
- User-reported issues

✅ **Quick reference skills**
- Error code lookup
- Symptom-based diagnosis
- Decision tree navigation
- Fast solution finding

✅ **Escalation judgment**
- When to troubleshoot yourself
- When to get help
- How to report effectively
- Support channel navigation

✅ **Prevention mindset**
- Specification quality
- System maintenance
- Build best practices
- Cost control
- Documentation habits

---

### 11.2 Troubleshooting Confidence Levels

**After completing this runbook, you should be able to:**

**LEVEL 1: Basic (80% of issues)**
- ✅ Understand error messages
- ✅ Look up error codes
- ✅ Follow documented solutions
- ✅ Retry appropriately
- ✅ Apply simple fixes

**LEVEL 2: Intermediate (15% of issues)**
- ✅ Diagnose unfamiliar errors
- ✅ Combine multiple solutions
- ✅ Create workarounds
- ✅ Modify specifications effectively
- ✅ Optimize for cost/performance

**LEVEL 3: Advanced (4% of issues)**
- ✅ Identify pipeline bugs
- ✅ Debug complex app issues
- ✅ Help other users
- ✅ Contribute documentation
- ✅ Prevent future issues

**LEVEL 4: Expert (1% of issues)**
- ✅ Report bugs effectively
- ✅ Suggest pipeline improvements
- ✅ Create custom solutions
- ✅ Escalate appropriately

**Most users will handle 95%+ of issues themselves.**

---

### 11.3 Your Troubleshooting Toolkit

**You now have:**

**1. This runbook (RB2)**
- 45 pages of solutions
- Error code table
- Decision trees
- Real examples

**2. Complementary runbooks**
- RB1: Daily operations (normal usage)
- RB3: Cost control (optimization)
- RB4: App store delivery (submissions)
- RB5: Pipeline updates (version management)
- RB6: Project updates (app maintenance)

**3. Quick references**
- Error code table (Section 5.2)
- Symptom lookup (Section 5.3)
- Decision trees (Section 5.4)

**4. Community resources**
- GitHub issues
- Discord/Slack
- Documentation
- Examples

**5. Personal documentation**
- Your troubleshooting log
- Solution notes
- Prevention checklists
- Custom templates

---

### 11.4 Next Steps By Experience Level

**If you're NEW to pipeline (0-5 builds):**

**Immediate:**
1. Bookmark this runbook (you'll need it)
2. Read RB1 (Daily Operations) for normal usage
3. Build your first app following NB5
4. Expect issues - use this runbook when they occur
5. Document what you fix

**First month:**
- Build 3-5 apps
- Experience different error types
- Practice troubleshooting
- Create personal notes
- Join community

**Goal:** Handle 80% of issues yourself by end of month.

---

**If you're EXPERIENCED (6-20 builds):**

**Immediate:**
1. Review Section 5 (Quick Reference) for fast lookups
2. Update your specification templates based on Section 10.1
3. Implement prevention practices from Section 10
4. Create personal runbook from your experiences

**Next month:**
- Achieve 95% self-service troubleshooting
- Help newer users in community
- Contribute documentation improvements
- Optimize workflows

**Goal:** Troubleshooting becomes routine, not stressful.

---

**If you're ADVANCED (20+ builds):**

**Immediate:**
1. Review rare issues (Sections 4.6-4.8) you may not have seen
2. Study escalation procedures (Section 6) for when needed
3. Share your solutions with community
4. Consider contributing to pipeline development

**Ongoing:**
- Help troubleshoot for others
- Report pipeline bugs effectively
- Improve documentation
- Share best practices

**Goal:** Become community resource, help improve pipeline.

---

### 11.5 What to Read Next

**Based on your current need:**

**If troubleshooting specific issue right now:**
→ Use Section 5 (Quick Reference) - find your error code
→ Or use systematic diagnosis (Section 1)

**If preventing future issues:**
→ Read Section 10 (Prevention Best Practices)
→ Implement checklists and templates

**If managing costs:**
→ Read RB3: Cost Control & System Maintenance
→ Optimize execution modes, monitor spending

**If submitting to app stores:**
→ Read RB4: App Store & Google Play Delivery
→ Handle rejections, optimize listings

**If updating apps:**
→ Read RB6: Updating & Patching Existing Projects
→ Version management, modification best practices

**If managing multiple apps:**
→ Read NB7: App Portfolio Management
→ Scale operations, prioritize projects

**If updating pipeline itself:**
→ Read RB5: Updating AI Factory Pipeline System
→ Safe upgrade procedures, migration guides

---

### 11.6 Remember These Key Principles

**1. Problems are normal**
- Every system has issues
- Failures are learning opportunities
- Most problems are solvable
- You're not doing anything wrong

**2. Diagnosis before action**
- Read error messages completely
- Gather information systematically
- Understand root cause
- Then apply correct fix

**3. Start simple**
- Try obvious solutions first
- One change at a time
- Test after each change
- Document what worked

**4. Prevention beats cure**
- Good specifications prevent 60% of issues
- Regular maintenance prevents 20% more
- Documentation prevents repetition
- You can prevent most problems

**5. Help yourself, help others**
- Document your solutions
- Share in community
- Contribute improvements
- Everyone benefits

**6. Know when to escalate**
- Don't spend 6 hours on 30-minute issue
- Use self-service first
- Escalate when truly stuck
- Provide good bug reports

**7. Continuous improvement**
- Track your issues
- Identify patterns
- Update templates
- Get better over time

---

### 11.7 Final Thoughts

**You now have a complete troubleshooting system.**

**From problem occurrence to resolution:**
1. ✅ Systematic diagnosis process
2. ✅ Comprehensive solution database
3. ✅ Quick reference tools
4. ✅ Real-world examples
5. ✅ Prevention strategies
6. ✅ Escalation procedures

**Most importantly:**

**You can handle this.**

Problems will occur. That's normal.

You have the tools. You have the knowledge. You have the support.

**Troubleshooting gets easier with practice.**

Your first few issues will take time. That's okay.

By issue #10, you'll be much faster.

By issue #20, you'll know patterns.

By issue #50, you'll prevent most problems before they happen.

**Keep this runbook handy. You'll reference it often at first, less over time.**

**Go build amazing things. When issues arise, you know what to do.**

---

**═══════════════════════════════════════════════════════════════**
**END OF RB2: TROUBLESHOOTING & PROBLEM RESOLUTION**
**═══════════════════════════════════════════════════════════════**
