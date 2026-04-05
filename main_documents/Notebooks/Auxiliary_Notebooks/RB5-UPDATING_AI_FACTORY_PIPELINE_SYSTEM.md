# RESPONSE PLAN for RB5: UPDATING AI FACTORY PIPELINE SYSTEM

```
═══════════════════════════════════════════════════════════════════════════════
RB5 GENERATION PLAN - 5 PARTS
═══════════════════════════════════════════════════════════════════════════════

Part 1: Front Matter + Overview + Prerequisites + Section 1 (Update Strategy & Planning)
Part 2: Section 2 (Pre-Update Preparation) + Section 3 (Update Execution)
Part 3: Section 4 (Post-Update Verification) + Section 5 (Rollback Procedures)
Part 4: Section 6 (Version-Specific Migration Guides) + Section 7 (Dependency Management)
Part 5: Section 8 (Troubleshooting Update Issues) + Quick Reference + Next Steps

Delivering Part 1 now. Reply "Cont" for Part 2.
```

---

# RB5: UPDATING AI FACTORY PIPELINE SYSTEM

---

**PURPOSE:** Safely update the AI Factory Pipeline to newer versions without breaking existing functionality.

**WHEN TO USE:** When a new pipeline version is released and you want to update your installation.

**ESTIMATED LENGTH:** 30-35 pages

**PREREQUISITE READING:**
- Pipeline is installed and working (NB1-4)
- Familiar with daily operations (RB1 recommended)
- Have built at least one app successfully

**TIME COMMITMENT:**
- Planning & preparation: 30-60 minutes
- Update execution: 15-45 minutes (depending on version jump)
- Post-update verification: 15-30 minutes
- Total: 1-2 hours for safe update

**WHAT YOU'LL MASTER:**
- ✅ When to update vs when to stay on current version
- ✅ Safe update procedures with zero downtime
- ✅ Backup strategies before updating
- ✅ Configuration migration between versions
- ✅ Breaking change identification and handling
- ✅ Rollback procedures if update fails
- ✅ Version-specific migration guides
- ✅ Dependency compatibility management

---

## 1. OVERVIEW

### 1.1 What This Runbook Covers

This is your complete guide to updating the AI Factory Pipeline software itself (not your apps - see RB6 for app updates).

**You'll learn:**

**Update Strategy:**
- When to update immediately vs when to wait
- How to evaluate update necessity
- Understanding semantic versioning
- Release channel selection (stable vs beta)

**Safe Update Process:**
- Pre-update backup procedures
- Configuration preservation
- Step-by-step update execution
- Post-update verification testing
- Rollback if needed

**Migration Handling:**
- Breaking changes identification
- Configuration file migration
- Database schema updates
- API compatibility adjustments
- Custom integration updates

**Version Management:**
- Understanding version numbers (5.6.0 explained)
- Reading changelogs effectively
- Tracking which version you're on
- Planning multi-version upgrades

**Troubleshooting:**
- Update failures and recovery
- Dependency conflicts
- Configuration incompatibilities
- Service integration issues

### 1.2 Why Updates Matter

**Benefits of staying updated:**

**Security:**
- ✅ Security patches for vulnerabilities
- ✅ Updated dependencies with fixes
- ✅ Protection against exploits
- ✅ Compliance with security standards

**Features:**
- ✅ New capabilities (faster builds, new platforms)
- ✅ Improved user experience
- ✅ Better error messages
- ✅ Enhanced tooling

**Performance:**
- ✅ Faster build times
- ✅ Reduced memory usage
- ✅ More efficient API usage
- ✅ Optimized processes

**Reliability:**
- ✅ Bug fixes
- ✅ Stability improvements
- ✅ Reduced failures
- ✅ Better error recovery

**Compatibility:**
- ✅ Support for new OS versions
- ✅ Latest service API versions
- ✅ Modern dependency versions
- ✅ Future-proofing

---

**Risks of NOT updating:**

**Security risks:**
- ❌ Known vulnerabilities remain
- ❌ No security patches
- ❌ Incompatible with security requirements
- ❌ Potential data exposure

**Functionality risks:**
- ❌ Missing new features
- ❌ Can't use latest services
- ❌ Incompatible with new OS/tools
- ❌ Limited support

**Support risks:**
- ❌ Old versions not supported
- ❌ Community moves on
- ❌ Documentation outdated
- ❌ Bug fixes not backported

**Technical debt:**
- ❌ Harder to update later (multi-version jumps)
- ❌ Incompatible with modern practices
- ❌ Dependency version conflicts
- ❌ Integration issues

---

**BUT - don't update blindly:**

**When NOT to update immediately:**
- ⚠️ Major version (e.g., 5.x → 6.x) - wait for stability
- ⚠️ Critical production work in progress
- ⚠️ Just before important deadline
- ⚠️ No time to test properly
- ⚠️ Beta/pre-release versions (unless testing)

**Philosophy:** Stay reasonably current, but prioritize stability over bleeding edge.

### 1.3 Understanding Version Numbers

**AI Factory Pipeline uses Semantic Versioning:**

```
MAJOR.MINOR.PATCH

Example: 5.6.2
         │ │ │
         │ │ └─ PATCH version (bug fixes)
         │ └─── MINOR version (new features)
         └───── MAJOR version (breaking changes)
```

---

**PATCH updates (5.6.0 → 5.6.1)**

**What changes:**
- Bug fixes only
- Security patches
- Documentation corrections
- No new features
- No breaking changes

**Example changelog:**
```
v5.6.1 - March 15, 2026

FIXES:
- Fixed S4 timeout on large builds
- Corrected memory calculation in status display
- Fixed GitHub token validation edge case

SECURITY:
- Updated requests library (CVE-2026-1234)
```

**Update recommendation:** ✅ Update soon (within 1-2 weeks)
**Risk level:** Very low
**Breaking changes:** None
**Testing needed:** Minimal (verify /status works)

---

**MINOR updates (5.6.0 → 5.7.0)**

**What changes:**
- New features added
- Improvements to existing features
- Bug fixes included
- Backward compatible (mostly)
- No breaking changes to core functionality

**Example changelog:**
```
v5.7.0 - April 1, 2026

NEW FEATURES:
- Support for Flutter web apps
- Parallel builds (queue 3 builds simultaneously)
- Enhanced analytics dashboard

IMPROVEMENTS:
- 15% faster S4 builds
- Better error messages for S2 failures
- Improved /status output

FIXES:
- 12 bug fixes (see detailed changelog)

COMPATIBILITY:
- All v5.6.x configurations work unchanged
- New features opt-in, don't affect existing workflows
```

**Update recommendation:** ✅ Update when convenient (within 1 month)
**Risk level:** Low
**Breaking changes:** Rare, well-documented
**Testing needed:** Moderate (test primary workflows)

---

**MAJOR updates (5.x → 6.0)**

**What changes:**
- Significant architecture changes
- Breaking changes expected
- Configuration format changes
- API changes possible
- May require code updates
- Deprecated features removed

**Example changelog:**
```
v6.0.0 - July 1, 2026

BREAKING CHANGES:
- Minimum Python version: 3.11 (was 3.10)
- Configuration file format changed (YAML → TOML)
- Execution modes renamed: LOCAL→DEVICE, CLOUD→REMOTE
- Several deprecated commands removed
- API endpoint structure changed

NEW FEATURES:
- Complete UI redesign
- Multi-user support
- Advanced caching system
- Real-time collaboration

MIGRATION GUIDE:
See docs/migration-5-to-6.md for detailed steps
Migration tool: python -m factory.migrate
```

**Update recommendation:** ⚠️ Wait 2-4 weeks after release (let others find issues)
**Risk level:** Medium-High
**Breaking changes:** Many, documented
**Testing needed:** Extensive (test everything)

---

**Pre-release versions (5.7.0-beta.1, 5.7.0-rc.2)**

**Naming:**
```
5.7.0-beta.1   → Beta version 1 (early testing)
5.7.0-beta.2   → Beta version 2 (more stable)
5.7.0-rc.1     → Release Candidate 1 (nearly ready)
5.7.0-rc.2     → Release Candidate 2 (final testing)
5.7.0          → Stable release
```

**Update recommendation:** ❌ Don't use in production
**Risk level:** High (bugs expected)
**Purpose:** Testing, feedback, early access
**Who should use:** Developers, testers, enthusiasts only

---

### 1.4 Release Channels

**Pipeline offers multiple release channels:**

**STABLE (recommended for most users)**
- Production-ready releases only
- Thoroughly tested
- Breaking changes rare and documented
- Updates every 4-8 weeks

**How to use:**
```
/config release_channel stable
```

**Who should use:** Everyone using pipeline for real work.

---

**BETA (for early adopters)**
- New features before stable release
- Generally stable but may have bugs
- Early access to improvements
- Updates every 1-2 weeks

**How to use:**
```
/config release_channel beta
```

**Who should use:** 
- Advanced users who want latest features
- Those willing to report bugs
- Non-critical development work

---

**NIGHTLY (bleeding edge, unstable)**
- Latest commits from development
- May be broken
- No guarantees
- Updates daily

**How to use:**
```
/config release_channel nightly
```

**Who should use:**
- Pipeline developers
- Testing specific features
- NOT for any production use

---

**Recommendation:**
```
Production use: STABLE
Testing new features: BETA
Development/contributing: NIGHTLY
```

---

### 1.5 How to Check Your Current Version

**Method 1: Telegram command**
```
/version
```

**Response:**
```
AI Factory Pipeline

Installed: v5.6.0
Released: March 1, 2026
Channel: stable

Latest available: v5.6.2
Update available: Yes

New in v5.6.2:
- Security patch for API authentication
- Fixed S4 timeout issue
- Improved error messages

To update: /update
Or: See RB5 for manual update procedures
```

---

**Method 2: Command line**
```bash
cd ~/ai-factory-pipeline
python -m factory.cli version
```

**Response:**
```
AI Factory Pipeline v5.6.0
Python: 3.11.2
Platform: macOS 13.2

Release channel: stable
Update available: v5.6.2
```

---

**Method 3: Check version file**
```bash
cat ~/ai-factory-pipeline/VERSION
```

**Response:**
```
5.6.0
```

---

## 2. PREREQUISITES CHECKLIST

Before updating, verify these requirements:

### 2.1 System Prerequisites

□ **Pipeline currently working**
- Can start pipeline successfully
- Can execute builds
- `/status` shows healthy

**If NOT working:** Fix issues before updating (see RB2).

□ **Admin/root access**
- Can install software
- Can modify system files
- Can restart services

**If NOT:** Request access or work with system administrator.

□ **Sufficient disk space**
- At least 5GB free (for update + backup)
- Check: `df -h ~`

**If NOT:** Clean up old builds: `/cleanup`

□ **Stable internet connection**
- Will download update packages (100-500 MB)
- Needs sustained connection (15-30 min)

**If NOT:** Wait for stable connection or use wired Ethernet.

□ **Time available**
- 1-2 hours for safe update
- Not rushed or under deadline
- Can test after update

**If NOT:** Schedule update for later.

---

### 2.2 Knowledge Prerequisites

□ **Know current version**
```
/version
```

□ **Have read changelog**
- Understand what's changing
- Identified breaking changes
- Know new features

**Get changelog:**
- https://github.com/[pipeline-repo]/releases
- Or: `/changelog v5.6.2`

□ **Understand impact**
- Will this affect current projects?
- Are there breaking changes?
- Need configuration changes?

□ **Have this runbook available**
- Can reference during update
- Know rollback procedures
- Emergency contacts accessible

---

### 2.3 Backup Prerequisites

□ **Recent backup exists**
- Full pipeline backup
- Configuration files saved
- Build history preserved

**Create backup:** See Section 2.2

□ **Know how to restore**
- Tested restore procedure
- Confident in rollback

**Test restore:** See Section 5.2

□ **Current projects documented**
- List of all apps built
- GitHub repositories noted
- Critical data identified

---

### 2.4 Timing Prerequisites

□ **No active builds**
```
/queue

Should show: No builds in queue
```

**If active builds:** Wait for completion or cancel.

□ **No critical deadlines**
- Not updating night before launch
- No urgent builds needed immediately
- Time to fix if issues arise

□ **Update window available**
- 2-3 hours of availability
- Can troubleshoot if needed
- Not end of day/week

**Best times to update:**
- ✅ Monday morning (week to fix issues)
- ✅ After completing project (clean break)
- ❌ Friday evening (no support over weekend)
- ❌ Before important demo/deadline

---

## 3. SECTION 1: UPDATE STRATEGY & PLANNING

### 3.1 Should You Update? Decision Framework

**Use this decision tree for every update:**

```
New version available
│
├─ Is it PATCH update? (x.x.0 → x.x.1)
│  ├─ Contains security fix? 
│  │  └─ YES → Update within 48 hours
│  └─ Just bug fixes?
│     └─ Update within 1-2 weeks
│
├─ Is it MINOR update? (x.0.x → x.1.x)
│  ├─ Want new features?
│  │  └─ YES → Update within 2-4 weeks
│  ├─ Any breaking changes listed?
│  │  └─ YES → Read carefully, plan migration
│  └─ Just staying current?
│     └─ Update within 1 month
│
├─ Is it MAJOR update? (5.x → 6.x)
│  ├─ Critical new features you need?
│  │  └─ YES → Wait 2 weeks post-release, then update
│  ├─ Current version working fine?
│  │  └─ YES → Wait 1 month, let others test
│  └─ Forced (old version EOL)?
│     └─ Plan carefully, schedule proper time
│
└─ Is it pre-release? (beta, rc)
   └─ Testing/development only
      └─ Don't use for production
```

---

### 3.2 Reading Changelogs Effectively

**Every release has changelog. Read it completely before updating.**

**What to look for:**

**SECTION 1: Breaking Changes**
```
BREAKING CHANGES:
- Minimum Python version: 3.11
- Configuration format changed
- API endpoint restructured
```

**Action:** 
- Note each breaking change
- Plan how to handle
- Allocate time for adjustments

---

**SECTION 2: New Features**
```
NEW FEATURES:
- Parallel builds
- Flutter web support
- Enhanced analytics
```

**Action:**
- Identify features you want
- Note if opt-in or automatic
- Plan to try new features after update

---

**SECTION 3: Improvements**
```
IMPROVEMENTS:
- 15% faster S4 builds
- Better error messages
- Reduced memory usage
```

**Action:**
- Note expected improvements
- Can verify after update
- May improve your workflows

---

**SECTION 4: Bug Fixes**
```
FIXES:
- Fixed S4 timeout on large builds
- Corrected memory leak in monitoring
- Fixed GitHub token validation
```

**Action:**
- Check if any fixes affect you
- Note problems that will be solved
- May fix issues you've worked around

---

**SECTION 5: Deprecations**
```
DEPRECATED:
- /build command (use /create instead) - removed in v6.0
- OLD_CONFIG_FORMAT (migrate to new format) - removed in v6.0
```

**Action:**
- Check if you use deprecated features
- Plan migration before they're removed
- Update workflows now

---

**SECTION 6: Migration Notes**
```
MIGRATION:
- Run: python -m factory.migrate
- Update config file format (see docs/migration.md)
- Review breaking changes checklist
```

**Action:**
- Read migration guide completely
- Follow steps exactly
- Test after each migration step

---

**Example changelog analysis:**

**Changelog:**
```
v5.7.0 - April 1, 2026

BREAKING CHANGES:
- Minimum Python 3.11 required

NEW FEATURES:
- Parallel builds (queue up to 3 simultaneously)
- Flutter web support

IMPROVEMENTS:
- 15% faster S4 builds
- Better S2 error messages

FIXES:
- Fixed S4 timeout issue (#234)
- Corrected memory calculation (#245)

DEPRECATED:
- /build command (use /create)

MIGRATION:
- Upgrade Python to 3.11+
- No config changes needed
```

**Analysis:**
```
MUST DO:
✓ Check Python version (might need update)
✓ Stop using /build command

NICE TO HAVE:
✓ Try parallel builds (new feature)
✓ Test Flutter web (if interested)

BENEFITS:
✓ Faster builds (15% improvement)
✓ S4 timeout issue fixed (I had this!)

RISK LEVEL: LOW
- Only breaking change is Python version
- Easy to update Python
- No config migration needed

DECISION: Update next week
TIME NEEDED: 45 minutes (Python update + pipeline update + testing)
```

---

### 3.3 Update Timing Strategy

**Frequency recommendations:**

**PATCH updates (x.x.N):**
```
Schedule: Every 2-4 weeks
Effort: 15-30 minutes
Risk: Very low

Strategy:
- Group 2-3 patch updates together
- Update during routine maintenance
- Quick verification testing
```

**MINOR updates (x.N.x):**
```
Schedule: Every 2-3 months
Effort: 1-2 hours
Risk: Low

Strategy:
- Wait 1-2 weeks after release
- Read changelog thoroughly
- Plan testing of new features
- Update during maintenance window
```

**MAJOR updates (N.x.x):**
```
Schedule: 1-2 per year
Effort: 2-4 hours
Risk: Medium

Strategy:
- Wait 3-4 weeks after release
- Read migration guide completely
- Schedule dedicated time
- Full backup and testing
- Plan rollback if needed
```

---

**Update calendar example:**

```
QUARTERLY UPDATE PLAN

Q1 (Jan-Mar):
- Week 2: Patch updates (5.6.1 → 5.6.3)
- Week 8: Minor update if available (5.6.x → 5.7.0)
- Week 12: Patch updates (5.7.0 → 5.7.2)

Q2 (Apr-Jun):
- Week 2: Patch updates
- Week 8: Minor update if available
- Week 12: Evaluate major update if released

Strategy:
- Stay within 1 minor version of latest
- Never more than 3 patches behind
- Major updates only when stable (4+ weeks old)
```

---

### 3.4 Version Jump Planning

**Jumping multiple versions requires more planning.**

**Single version jump (5.6 → 5.7):**
```
Complexity: Low
Time: 1 hour
Approach: Direct update
```

**Two version jump (5.6 → 5.8):**
```
Complexity: Medium
Time: 1.5 hours
Approach: Review both changelogs, direct update usually works
```

**Three+ version jump (5.6 → 5.9):**
```
Complexity: High
Time: 2-3 hours
Approach: Step-by-step update or read cumulative changelog
```

**Major version jump (5.x → 6.x):**
```
Complexity: Very high
Time: 3-4 hours
Approach: Treat as fresh install, migrate data
```

---

**Example: 5.5 → 5.8 (3 versions)**

**Option A: Direct update (faster but riskier)**
```
1. Read all three changelogs (5.6, 5.7, 5.8)
2. Note cumulative breaking changes
3. Create backup
4. Update directly: 5.5 → 5.8
5. Handle all migrations at once
6. Extensive testing
```

**Time:** 2 hours
**Risk:** Medium (may encounter unexpected issues)

---

**Option B: Step-by-step (slower but safer)**
```
1. Update 5.5 → 5.6
2. Test thoroughly
3. Update 5.6 → 5.7  
4. Test thoroughly
5. Update 5.7 → 5.8
6. Test thoroughly
```

**Time:** 3 hours
**Risk:** Low (issues isolated to specific version)

**Recommendation:** Step-by-step if >3 versions behind.

---

### 3.5 Creating an Update Plan

**For each update, create written plan:**

**Template:**

```
UPDATE PLAN

FROM: v5.6.0
TO: v5.7.0
DATE: April 10, 2026

BREAKING CHANGES:
1. Python 3.11 required (currently have 3.10)
2. None others

PREPARATION NEEDED:
☐ Update Python to 3.11
☐ Backup current installation
☐ Export configuration
☐ Stop pipeline
☐ Cancel queued builds

MIGRATION STEPS:
1. Update Python (30 min)
2. Update pipeline (15 min)
3. Verify configuration (10 min)
4. Test basic operations (15 min)

TESTING CHECKLIST:
☐ /status works
☐ Can evaluate app idea
☐ Can create test build
☐ Services connect properly
☐ New features accessible

ROLLBACK PLAN:
If issues occur:
1. Restore from backup (15 min)
2. Downgrade Python if needed
3. Verify old version works

TIME BUDGET:
Preparation: 45 min
Execution: 30 min
Testing: 30 min
Buffer: 15 min
TOTAL: 2 hours

SCHEDULED WINDOW:
Monday April 10, 9:00 AM - 11:00 AM
No critical builds planned
No deadlines this week
```

---

**✅ SECTION 1 COMPLETE**

You now understand:
- ✅ When to update vs when to wait
- ✅ How to read version numbers
- ✅ How to analyze changelogs
- ✅ Update timing strategies
- ✅ How to plan updates systematically

**Next (Section 2): Pre-Update Preparation (backups, configuration export)**

---

**[END OF PART 1]**














---

# RB5: UPDATING AI FACTORY PIPELINE SYSTEM
## PART 2 of 5

---

## 4. SECTION 2: PRE-UPDATE PREPARATION

**PURPOSE:** Protect yourself before updating - create safety nets.

**Philosophy:** Hope for the best, prepare for the worst.

---

### 4.1 Pre-Update Checklist

**Complete ALL items before starting update:**

□ **Read changelog completely**
- Understand what's changing
- Note breaking changes
- Identify required actions

□ **Verify prerequisites**
- Sufficient disk space (5GB+)
- Admin access available
- Stable internet connection
- Time allocated (2+ hours)

□ **Document current state**
- Current version noted
- Active projects listed
- Configuration documented

□ **Create full backup**
- Pipeline installation backed up
- Configuration files saved
- Build history preserved
- Database exported (if applicable)

□ **Export configuration**
- All settings saved
- API keys recorded (separately, securely)
- Custom settings documented

□ **Stop all activity**
- No builds running
- No builds queued
- Pipeline can be stopped safely

□ **Notify stakeholders (if applicable)**
- Team knows update is happening
- Downtime communicated
- Support available if needed

□ **Have rollback plan ready**
- Know how to restore backup
- Tested restore procedure
- Documented steps available

---

### 4.2 Creating Full Backup

**CRITICAL: Always backup before updating.**

**What to backup:**
1. ✅ Pipeline installation directory
2. ✅ Configuration files (.env, config.json, etc.)
3. ✅ Build history and artifacts
4. ✅ Database files
5. ✅ Custom modifications
6. ✅ Logs (optional but helpful)

---

#### 4.2.1 Automated Backup (Recommended)

**Pipeline has built-in backup command:**

```
/backup create pre-update-5.7.0
```

**What happens:**
```
🔄 Creating backup: pre-update-5.7.0

Backing up:
✅ Pipeline code (543 MB)
✅ Configuration (2 MB)
✅ Build artifacts (last 30 days) (1.2 GB)
✅ Database (15 MB)
✅ Logs (45 MB)

Total: 1.8 GB
Compression: Enabled
Encryption: Enabled (AES-256)

Backup location: ~/ai-factory-pipeline/backups/pre-update-5.7.0.tar.gz.enc
Created: 2026-04-10 09:15:00
Size: 892 MB (compressed)

✅ Backup complete

To restore: /backup restore pre-update-5.7.0
```

**Verify backup:**
```
/backup list
```

**Response:**
```
Available backups:

1. pre-update-5.7.0
   Date: 2026-04-10 09:15:00
   Size: 892 MB
   Version: 5.6.0
   Status: ✅ Valid

2. pre-update-5.6.0
   Date: 2026-03-01 10:30:00
   Size: 845 MB
   Version: 5.5.0
   Status: ✅ Valid

3. weekly-auto-2026-04-07
   Date: 2026-04-07 02:00:00
   Size: 901 MB
   Version: 5.6.0
   Status: ✅ Valid
```

---

#### 4.2.2 Manual Backup (Alternative)

**If automated backup fails or you prefer manual control:**

**Step 1: Stop pipeline**
```
/stop
```

Wait for confirmation:
```
✅ Pipeline stopped gracefully
All builds completed
Services disconnected
Safe to backup
```

---

**Step 2: Create backup directory**
```bash
# Create dated backup folder
BACKUP_DIR=~/pipeline-backups/backup-$(date +%Y%m%d-%H%M%S)
mkdir -p $BACKUP_DIR
```

---

**Step 3: Backup pipeline installation**

**macOS/Linux:**
```bash
# Copy entire installation
cp -r ~/ai-factory-pipeline $BACKUP_DIR/pipeline

# Or create compressed archive (saves space)
tar -czf $BACKUP_DIR/pipeline.tar.gz -C ~ ai-factory-pipeline
```

**Windows (PowerShell):**
```powershell
# Create backup
$BackupDir = "$env:USERPROFILE\pipeline-backups\backup-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
New-Item -ItemType Directory -Path $BackupDir
Copy-Item -Recurse "$env:USERPROFILE\ai-factory-pipeline" "$BackupDir\pipeline"
```

---

**Step 4: Backup configuration separately**
```bash
# Extra safety - configuration files separately
cp ~/ai-factory-pipeline/.env $BACKUP_DIR/env-backup.txt
cp ~/ai-factory-pipeline/config.json $BACKUP_DIR/config-backup.json

# Document current version
echo "5.6.0" > $BACKUP_DIR/VERSION.txt
```

---

**Step 5: Backup database (if exists)**
```bash
# SQLite database (common)
cp ~/ai-factory-pipeline/data/pipeline.db $BACKUP_DIR/database-backup.db

# Or if PostgreSQL/MySQL
# Export using database-specific tools
```

---

**Step 6: Create backup manifest**
```bash
# Document what's in backup
cat > $BACKUP_DIR/MANIFEST.txt << EOF
AI Factory Pipeline Backup
Created: $(date)
Version: 5.6.0
Purpose: Pre-update backup before upgrading to 5.7.0

Contents:
- Full pipeline installation
- Configuration files (.env, config.json)
- Database snapshot
- Build history (last 30 days)

To restore:
1. Stop current pipeline
2. Remove ~/ai-factory-pipeline
3. Extract: tar -xzf pipeline.tar.gz -C ~
4. Restore config files
5. Start pipeline
EOF
```

---

**Step 7: Verify backup integrity**
```bash
# Check backup exists and is readable
ls -lh $BACKUP_DIR

# Verify archive if compressed
tar -tzf $BACKUP_DIR/pipeline.tar.gz | head -20

# Document backup location
echo "Backup created at: $BACKUP_DIR"
```

---

**Step 8: Test backup (optional but recommended)**

**Quick test:**
```bash
# Extract to temporary location (don't overwrite current)
mkdir /tmp/backup-test
tar -xzf $BACKUP_DIR/pipeline.tar.gz -C /tmp/backup-test

# Check key files exist
ls /tmp/backup-test/ai-factory-pipeline/.env
ls /tmp/backup-test/ai-factory-pipeline/config.json

# Clean up test
rm -rf /tmp/backup-test
```

**If extraction succeeds:** ✅ Backup is good

---

### 4.3 Exporting Configuration

**Separate from backup, export configuration in readable format:**

**Why:** 
- Easy to compare before/after update
- Can manually restore settings if needed
- Documents your setup

---

**Method 1: Using pipeline command**
```
/config export
```

**Creates file:**
```
~/ai-factory-pipeline/exports/config-export-2026-04-10.json
```

**Contains:**
```json
{
  "version": "5.6.0",
  "exported": "2026-04-10T09:20:00Z",
  "configuration": {
    "execution_mode": "HYBRID",
    "release_channel": "stable",
    "anthropic_api_key": "sk-ant-***...***",
    "github_token": "ghp_***...***",
    "firebase_project_id": "my-pipeline-project",
    "sentry_dsn": "https://***@***.ingest.sentry.io/***",
    "telegram_bot_token": "***:***",
    "monthly_budget": 50,
    "auto_cleanup": true,
    "cleanup_interval": "7-days",
    "notification_preferences": {
      "build_complete": true,
      "build_failed": true,
      "warnings": false
    },
    "default_platform": "android",
    "default_stack": "react-native"
  },
  "statistics": {
    "total_builds": 47,
    "successful_builds": 45,
    "total_cost": 23.40
  }
}
```

**Save this file somewhere safe** (not just in pipeline directory).

---

**Method 2: Manual documentation**

Create a text file documenting your settings:

```bash
cat > ~/Desktop/pipeline-config-backup.txt << EOF
AI FACTORY PIPELINE CONFIGURATION
Date: $(date)
Version: 5.6.0

EXECUTION:
- Mode: HYBRID
- Release channel: stable

API KEYS (reference only - stored securely):
- Anthropic: Configured ✅
- GitHub: Configured ✅
- Firebase: Configured ✅
- Sentry: Configured ✅

SETTINGS:
- Monthly budget: $50
- Auto cleanup: Enabled (7 days)
- Notifications: Build complete/failed only

DEFAULTS:
- Platform: Android
- Stack: React Native

CUSTOM CONFIGURATIONS:
- (none)

NOTES:
- Using shared Firebase project with team
- GitHub token expires: 2026-06-01 (set reminder)
EOF
```

---

### 4.4 Documenting Current State

**Before updating, document what's currently working:**

```bash
cat > ~/Desktop/pre-update-state.txt << EOF
PRE-UPDATE STATE DOCUMENTATION
Date: 2026-04-10
Current Version: 5.6.0
Target Version: 5.7.0

CURRENT STATUS:
Pipeline status: ✅ Running
All services: ✅ Connected
Recent builds: ✅ 5/5 successful
Last build: 2026-04-09 (HabitFlow v1.2.0)

ACTIVE PROJECTS:
1. HabitFlow - v1.2.0 (Android, published)
2. StudyTimer - v1.0.1 (Android, published)
3. RecipeBox - v0.9.0 (Android, in testing)

PENDING WORK:
- RecipeBox v1.0.0 launch (next week)
- StudyTimer v1.1.0 update (planned)

KNOWN ISSUES (before update):
- None currently

CUSTOM MODIFICATIONS:
- None

INTEGRATION STATUS:
- GitHub: ✅ Working
- Firebase: ✅ Working
- Sentry: ✅ Working
- Telegram: ✅ Working

SYSTEM INFO:
- OS: macOS 13.2
- Python: 3.11.2
- Node.js: 18.16.0
- Disk space: 145 GB free

NOTES:
- Update planned for Monday morning
- No critical deadlines this week
- Team notified of brief downtime
EOF
```

**Keep this file.** Compare after update to verify everything still works.

---

### 4.5 Stopping Pipeline Safely

**Before updating, stop pipeline properly:**

**Step 1: Check for active builds**
```
/queue
```

**If builds active:**
```
Current builds: 1 active

ACTIVE:
- RecipeBox v1.0.0 (S3 - Testing, 5m elapsed)
```

**Options:**
1. **Wait for completion** (recommended if <10 min remaining)
2. **Cancel build** (if safe to cancel)
   ```
   /cancel [build-id]
   ```

---

**Step 2: Graceful shutdown**
```
/stop
```

**Pipeline responds:**
```
🔄 Initiating graceful shutdown...

Stopping services:
✅ Telegram bot disconnected
✅ Active connections closed
✅ Background tasks completed
✅ Configuration saved
✅ Logs flushed

Pipeline stopped successfully.
Safe to update.
```

**Verify stopped:**
```
/status
```

**Should show:**
```
❌ Pipeline is not running

To start: /start
Or: python -m factory.cli start
```

---

**Step 3: Verify no processes running**

**macOS/Linux:**
```bash
ps aux | grep factory
```

**Should show:** Only the grep command itself, no pipeline processes.

**If pipeline processes still running:**
```bash
# Find process ID
ps aux | grep "factory.cli"

# Kill gracefully
kill [PID]

# Wait 10 seconds, check again
# If still running, force kill
kill -9 [PID]
```

---

### 4.6 Pre-Update Testing

**Before updating, test current version one last time:**

**Purpose:** Establish baseline for post-update comparison.

**Quick test:**
```
1. Start pipeline: /start
2. Check status: /status (all services connected?)
3. Test evaluation: /evaluate [simple idea]
4. Check cost tracking: /cost today
5. Verify logs: /logs recent
6. Stop pipeline: /stop
```

**Document results:**
```
PRE-UPDATE TEST RESULTS
Date: 2026-04-10 09:45:00
Version: 5.6.0

✅ Pipeline starts in 25 seconds
✅ All services connect (Anthropic, GitHub, Firebase)
✅ Evaluation works (scored test idea: 78/100)
✅ Cost tracking accurate ($23.40 this month)
✅ Logs accessible and readable
✅ Graceful shutdown works

Baseline established.
All systems operational before update.
```

**Keep this.** After update, run same tests and compare.

---

## 5. SECTION 3: UPDATE EXECUTION

**PURPOSE:** Step-by-step update procedures.

**Prerequisites:** All Section 2 steps completed (backup, export, documentation).

---

### 5.1 Update Methods

**Pipeline offers three update methods:**

**Method 1: Automatic update (recommended)**
- Built-in update command
- Handles dependencies automatically
- Safest for most users

**Method 2: Manual update**
- Download new version manually
- Install via package manager
- More control, more complex

**Method 3: Fresh install**
- Complete reinstall
- Migrate data manually
- Only for major version jumps or corrupted installations

---

### 5.2 Method 1: Automatic Update (Recommended)

**Use this method for:**
- ✅ Patch updates (5.6.0 → 5.6.1)
- ✅ Minor updates (5.6.0 → 5.7.0)
- ✅ When staying on same major version

**Don't use for:**
- ❌ Major version jumps (5.x → 6.x) - use Method 3
- ❌ Corrupted installations
- ❌ Custom-modified installations

---

**Step 1: Verify prerequisites**

```
# Check current version
/version

# Check if update available
/check-updates
```

**Response:**
```
Current: v5.6.0
Latest: v5.7.0

Update available: YES

Changes in v5.7.0:
- BREAKING: Requires Python 3.11
- NEW: Parallel builds
- IMPROVED: 15% faster S4 builds
- FIXED: S4 timeout issue

Prerequisites:
✅ Backup created
✅ Python 3.11+ installed
✅ Disk space: 5.2 GB free (need 3 GB)
✅ Internet: Connected

Ready to update: YES
```

---

**Step 2: Handle prerequisites**

**If Python version too old:**
```
Current Python: 3.10.8
Required: 3.11+

Please update Python first:
- macOS: brew upgrade python
- Ubuntu: sudo apt install python3.11
- Windows: Download from python.org

After updating Python, run /check-updates again.
```

**Update Python, then continue.**

---

**Step 3: Start automatic update**

```
/update
```

**Or with confirmation skip:**
```
/update --yes
```

---

**Step 4: Monitor update process**

**Pipeline shows progress:**
```
🔄 Starting update: 5.6.0 → 5.7.0

Phase 1: Pre-update checks
✅ Backup verified
✅ Configuration exported
✅ Dependencies checked
✅ Disk space sufficient

Phase 2: Download
Downloading v5.7.0... [################] 100% (234 MB)
✅ Download complete
✅ Checksum verified

Phase 3: Dependency update
Installing dependencies...
- anthropic 0.25.0 → 0.28.0 ✅
- firebase-admin 6.2.0 → 6.3.0 ✅
- github3.py (new) ✅
- 12 other packages ✅
✅ Dependencies updated

Phase 4: Code update
Extracting files... ✅
Updating code... ✅
Preserving configuration... ✅
✅ Code updated

Phase 5: Configuration migration
Checking configuration compatibility... ✅
No migration needed ✅

Phase 6: Post-update tasks
Clearing caches... ✅
Updating database schema... ✅
Verifying installation... ✅

✅ UPDATE COMPLETE

Updated: 5.6.0 → 5.7.0
Time: 3m 42s
Backup preserved: ~/ai-factory-pipeline/backups/pre-update-5.7.0.tar.gz.enc

Next steps:
1. Start pipeline: /start
2. Verify: /status
3. Test: Run a simple build
4. If issues: /rollback or restore backup

See changelog: /changelog 5.7.0
```

---

**Step 5: Handle update warnings/errors**

**If warnings appear:**
```
⚠️ WARNING during update:

Deprecated configuration detected:
- OLD_CONFIG_FORMAT will be removed in v6.0
- Please migrate to NEW_CONFIG_FORMAT

Update completed successfully but action required.
See: /config migrate-deprecated
```

**Action:** Note warning, handle after verifying update works.

---

**If errors occur:**
```
❌ UPDATE FAILED

Phase 3: Dependency update
Error: Could not install anthropic 0.28.0
Conflict: requests>=2.31.0 required, but 2.28.0 installed

Update aborted. System unchanged.

Resolution:
1. Update requests: pip install requests --upgrade
2. Retry update: /update

Or: See RB5 Section 8 for troubleshooting
```

**Action:** Follow resolution steps, retry.

---

### 5.3 Method 2: Manual Update

**Use when:**
- Automatic update fails
- Want more control
- Customized installation
- Offline update needed

---

**Step 1: Download new version**

**Option A: From GitHub releases**
```bash
cd ~/Downloads
curl -L -O https://github.com/[pipeline-repo]/releases/download/v5.7.0/ai-factory-pipeline-5.7.0.tar.gz
```

**Option B: Clone repository**
```bash
cd ~/Downloads
git clone --branch v5.7.0 https://github.com/[pipeline-repo].git pipeline-5.7.0
```

---

**Step 2: Verify download**
```bash
# Check checksum (from release page)
shasum -a 256 ai-factory-pipeline-5.7.0.tar.gz

# Should match published checksum:
# abc123...xyz789 ai-factory-pipeline-5.7.0.tar.gz
```

---

**Step 3: Stop current pipeline**
```
/stop
```

---

**Step 4: Backup current installation** (if not already done)
```bash
mv ~/ai-factory-pipeline ~/ai-factory-pipeline-5.6.0-backup
```

---

**Step 5: Extract new version**
```bash
tar -xzf ~/Downloads/ai-factory-pipeline-5.7.0.tar.gz -C ~
```

**Or if cloned:**
```bash
mv ~/Downloads/pipeline-5.7.0 ~/ai-factory-pipeline
```

---

**Step 6: Restore configuration**
```bash
# Copy configuration from backup
cp ~/ai-factory-pipeline-5.6.0-backup/.env ~/ai-factory-pipeline/.env
cp ~/ai-factory-pipeline-5.6.0-backup/config.json ~/ai-factory-pipeline/config.json

# Copy any custom modifications
# (if you made any to the code)
```

---

**Step 7: Install dependencies**
```bash
cd ~/ai-factory-pipeline
pip install -r requirements.txt --upgrade --break-system-packages
```

**Response:**
```
Collecting anthropic>=0.28.0
Installing collected packages: ...
Successfully installed 23 packages
```

---

**Step 8: Run migration script (if exists)**
```bash
# Check if migration needed
python -m factory.migrate --check

# If migration required:
python -m factory.migrate
```

---

**Step 9: Verify installation**
```bash
python -m factory.cli version
```

**Should show:**
```
AI Factory Pipeline v5.7.0
```

---

### 5.4 Method 3: Fresh Install with Migration

**Use for:**
- Major version jumps (5.x → 6.x)
- Corrupted installations
- Complete cleanup desired

**This is essentially reinstalling pipeline while preserving data.**

---

**Step 1: Export all data**

```
# Export configuration
/config export

# Export build history
/export builds --all

# Export statistics
/export stats

# Document active projects
/projects list > ~/projects-list.txt
```

**All exports saved to:**
```
~/ai-factory-pipeline/exports/
```

**Copy exports to safe location:**
```bash
mkdir ~/pipeline-migration-data
cp -r ~/ai-factory-pipeline/exports/* ~/pipeline-migration-data/
```

---

**Step 2: Note all GitHub repositories**

```
/projects list --format=urls
```

**Response:**
```
Active projects (3):

1. HabitFlow
   GitHub: https://github.com/yourusername/habitflow
   
2. StudyTimer
   GitHub: https://github.com/yourusername/studytimer
   
3. RecipeBox
   GitHub: https://github.com/yourusername/recipebox
```

**Save this list.** You'll need these URLs.

---

**Step 3: Completely remove old installation**

```bash
# Stop pipeline
/stop

# Remove installation
rm -rf ~/ai-factory-pipeline

# Remove old backups (optional, keep if you want)
# rm -rf ~/pipeline-backups

# Clean Python cache (optional)
pip cache purge
```

---

**Step 4: Fresh install of new version**

Follow installation guide (NB1) for new version.

```bash
# Download new version
curl -L -O https://github.com/[pipeline-repo]/releases/download/v6.0.0/ai-factory-pipeline-6.0.0.tar.gz

# Extract
tar -xzf ai-factory-pipeline-6.0.0.tar.gz -C ~

# Install
cd ~/ai-factory-pipeline
pip install -r requirements.txt --break-system-packages

# Initialize
python -m factory.cli init
```

---

**Step 5: Import configuration**

```bash
# Import from v5.x format
python -m factory.migrate import ~/pipeline-migration-data/config-export-*.json

# Or manually configure
python -m factory.cli configure
```

---

**Step 6: Verify services**

```
/start
/status
```

**All services should connect.**

---

**Step 7: Reconnect to projects**

For each GitHub repository:
```
/projects import https://github.com/yourusername/habitflow
```

**Pipeline reconnects to existing repositories.**

---

**Step 8: Import build history (optional)**

```bash
python -m factory.migrate import-history ~/pipeline-migration-data/build-history-*.json
```

---

### 5.5 Post-Update First Start

**After ANY update method, first start is critical:**

**Step 1: Start pipeline**
```
/start
```

**Or:**
```bash
cd ~/ai-factory-pipeline
python -m factory.cli start
```

---

**Step 2: Watch startup logs**

```
AI Factory Pipeline v5.7.0
Starting services...

Loading configuration... ✅
Connecting to services...
  - Anthropic API... ✅
  - GitHub... ✅
  - Firebase... ✅
  - Sentry... ✅
  
Initializing features...
  - Parallel builds... ✅ (NEW)
  - Flutter web support... ✅ (NEW)
  
Pipeline is RUNNING

New features available. See: /help new-features
```

**Look for:**
- ✅ All services connect
- ✅ No error messages
- ✅ New features initialized (if any)

---

**If errors during startup:**

```
❌ ERROR during startup

Service connection failed: GitHub
Error: Invalid token format

This may be due to configuration changes in v5.7.0.

Resolution:
1. Check GitHub token format
2. Regenerate if needed
3. Update: /config github_token [new-token]
4. Restart: /restart
```

**Action:** Follow error instructions.

---

**✅ SECTIONS 2 & 3 COMPLETE**

You now know:
- ✅ How to prepare for updates (backups, exports)
- ✅ How to execute updates (3 methods)
- ✅ How to handle prerequisites
- ✅ How to migrate configurations
- ✅ How to start after update

**Next (Part 3):**
- Section 4: Post-Update Verification
- Section 5: Rollback Procedures

---

**[END OF PART 2]**














---

# RB5: UPDATING AI FACTORY PIPELINE SYSTEM
## PART 3 of 5

---

## 6. SECTION 4: POST-UPDATE VERIFICATION

**PURPOSE:** Confirm update succeeded and everything works correctly.

**Philosophy:** Trust but verify. Update may complete without errors but still have issues.

---

### 6.1 Verification Testing Levels

**Three levels of testing after update:**

**LEVEL 1: Basic (required, 5-10 min)**
- Pipeline starts and runs
- Services connect
- Basic commands work
- No critical errors

**LEVEL 2: Standard (recommended, 15-20 min)**
- All core features functional
- Build process works
- Configuration preserved
- New features accessible

**LEVEL 3: Comprehensive (major updates, 30-45 min)**
- Full build cycle test
- All integrations verified
- Performance benchmarked
- Edge cases tested

---

### 6.2 Level 1: Basic Verification (Required)

**Perform immediately after update:**

---

**Test 1: Pipeline Status**

```
/status
```

**Expected result:**
```
Pipeline Status: ✅ RUNNING
Version: 5.7.0 ✅ (updated from 5.6.0)
Mode: HYBRID
Uptime: 2 minutes

Services:
✅ Anthropic API: Connected
✅ GitHub: Connected
✅ Firebase: Connected
✅ Sentry: Connected (optional)

System Resources:
CPU: 12%
Memory: 2.1GB / 8GB (26%)
Disk: 140GB free

Last 24 hours:
✅ Builds completed: 0 (just updated)
❌ Builds failed: 0
💰 Cost: $0.00
```

**What to verify:**
- ✅ Version shows new number (5.7.0)
- ✅ Status is RUNNING (not ERROR)
- ✅ All required services show Connected
- ✅ No error messages

**If FAIL:**
- Service not connected → Check that service's credentials
- Status ERROR → Check logs: `/logs error`
- Wrong version → Update didn't complete, retry

---

**Test 2: Help Command**

```
/help
```

**Expected result:**
```
AI FACTORY PIPELINE v5.7.0
Available Commands:

BASIC:
/status - Check pipeline health
/help - Show this message
/version - Show version info
/evaluate - Score an app idea
/create - Build new app
/modify - Update existing app

[... rest of help text ...]

NEW IN 5.7.0:
/parallel - Queue multiple builds
/flutter-web - Create Flutter web app
```

**What to verify:**
- ✅ Help displays correctly
- ✅ Version shows in header
- ✅ New commands listed (if any)
- ✅ No error messages

---

**Test 3: Version Check**

```
/version
```

**Expected result:**
```
AI Factory Pipeline

Installed: v5.7.0 ✅
Released: April 1, 2026
Channel: stable

Latest available: v5.7.0 (up to date)
Python: 3.11.2
Platform: macOS 13.2

Update history:
- 2026-04-10: 5.6.0 → 5.7.0 (SUCCESS)
- 2026-03-01: 5.5.0 → 5.6.0 (SUCCESS)
```

**What to verify:**
- ✅ Installed version matches target (5.7.0)
- ✅ Shows "up to date"
- ✅ Update history logged
- ✅ Python version correct

---

**Test 4: Configuration Check**

```
/config show
```

**Expected result:**
```
Current Configuration:

EXECUTION:
execution_mode: HYBRID
release_channel: stable

SERVICES:
anthropic_api_key: sk-ant-***...*** ✅ Valid
github_token: ghp_***...*** ✅ Valid
firebase_project_id: my-pipeline-project ✅
sentry_dsn: https://***...*** ✅

SETTINGS:
monthly_budget: 50
auto_cleanup: true
cleanup_interval: 7-days

DEFAULTS:
default_platform: android
default_stack: react-native

NEW FEATURES (v5.7.0):
parallel_builds: enabled
max_parallel: 3
flutter_web: enabled
```

**What to verify:**
- ✅ All settings preserved from before update
- ✅ API keys still valid (shows ✅)
- ✅ New features configured (if applicable)
- ✅ No "MISSING" or "INVALID" entries

**If settings lost:**
```
/config import ~/pipeline-migration-data/config-export-[date].json
```

---

**Test 5: Logs Accessibility**

```
/logs recent
```

**Expected result:**
```
Recent Logs (last 50 entries):

[2026-04-10 10:05:23] INFO: Pipeline started - v5.7.0
[2026-04-10 10:05:22] INFO: Services connected successfully
[2026-04-10 10:05:21] INFO: Configuration loaded
[2026-04-10 10:05:20] INFO: Update completed: 5.6.0 → 5.7.0
[2026-04-10 10:02:15] INFO: Update started
[2026-04-10 10:01:30] INFO: Pre-update backup created
...
```

**What to verify:**
- ✅ Logs readable
- ✅ Shows update sequence
- ✅ No ERROR entries
- ✅ Timestamps correct

---

**LEVEL 1 PASS CRITERIA:**

□ All 5 tests pass
□ No errors in any response
□ Version number correct
□ Services connected
□ Configuration preserved

**If ALL pass:** ✅ Proceed to Level 2

**If ANY fail:** ⚠️ Investigate issue before continuing. See Section 8 (Troubleshooting).

---

### 6.3 Level 2: Standard Verification (Recommended)

**Perform after Level 1 passes:**

---

**Test 6: Idea Evaluation**

```
/evaluate

App Name: TestApp
Platform: Android
Description: A simple test app to verify evaluation works after update. This is just for testing the pipeline functionality.
Target Users: Pipeline operators testing updates
Core Features:
- Basic UI
- Simple data storage
- Test functionality
Monetization: Free (test only)
```

**Expected result:**
```
📊 IDEA EVALUATION RESULTS

App: TestApp
Overall Score: 72/100 ⭐ GOOD

BREAKDOWN:
✅ Market Demand: 65/100
✅ Technical Feasibility: 95/100
✅ Competitive Landscape: 70/100
✅ Monetization Potential: 55/100
✅ Complexity: 90/100

RECOMMENDATION: ✅ BUILD THIS
[... detailed analysis ...]
```

**What to verify:**
- ✅ Evaluation completes (doesn't timeout)
- ✅ Returns structured results
- ✅ Score breakdown provided
- ✅ Analysis makes sense
- ✅ Time taken reasonable (2-3 min)

**Benchmark comparison:**
- Pre-update eval time: ~2m 15s
- Post-update eval time: ~2m 10s
- Within normal range ✅

---

**Test 7: Cost Tracking**

```
/cost today
```

**Expected result:**
```
Cost Summary - Today (April 10, 2026)

Builds: 0 completed
External Services:
- Anthropic API: $0.02 (evaluation test)

TOTAL TODAY: $0.02

Month to date: $23.42
Monthly budget: $50.00
Remaining: $26.58 (53%)
```

**What to verify:**
- ✅ Cost tracking works
- ✅ Historical costs preserved
- ✅ New costs tracked
- ✅ Budget calculations correct

---

**Test 8: Queue Management**

```
/queue
```

**Expected result:**
```
Build Queue: 0 active, 0 waiting

No builds in queue

NEW IN 5.7.0:
Parallel builds enabled (max 3 simultaneous)
Use: /parallel enable/disable
```

**What to verify:**
- ✅ Queue display works
- ✅ Shows new features (if applicable)
- ✅ No stuck builds from pre-update

---

**Test 9: New Features (if applicable)**

**For v5.7.0 example - test new parallel builds feature:**

```
/parallel status
```

**Expected result:**
```
Parallel Builds: ✅ ENABLED

Configuration:
- Max simultaneous: 3 builds
- Queue management: Automatic
- Priority: FIFO (first in, first out)

Current usage: 0/3 slots

This feature is NEW in v5.7.0
Allows queuing multiple builds that run simultaneously
Faster throughput for multiple apps
```

**What to verify:**
- ✅ New feature accessible
- ✅ Configuration shown
- ✅ Help text available

---

**Test 10: Project List**

```
/projects list
```

**Expected result:**
```
Active Projects (3):

1. HabitFlow
   Version: v1.2.0
   Platform: Android
   Repository: https://github.com/yourusername/habitflow
   Last build: 2026-04-09
   Status: ✅ Published

2. StudyTimer
   Version: v1.0.1
   Platform: Android
   Repository: https://github.com/yourusername/studytimer
   Last build: 2026-04-08
   Status: ✅ Published

3. RecipeBox
   Version: v0.9.0
   Platform: Android
   Repository: https://github.com/yourusername/recipebox
   Last build: 2026-04-09
   Status: 🧪 Testing

All projects preserved after update ✅
```

**What to verify:**
- ✅ All projects still listed
- ✅ Project data intact
- ✅ Repository links work
- ✅ Statuses preserved

---

**LEVEL 2 PASS CRITERIA:**

□ All Level 1 tests still pass
□ Evaluation works correctly
□ Cost tracking functional
□ Queue management operational
□ New features accessible (if any)
□ Project list preserved

**If ALL pass:** ✅ Proceed to Level 3 or conclude testing

**If ANY fail:** ⚠️ Non-critical issue but should investigate

---

### 6.4 Level 3: Comprehensive Verification (Major Updates)

**Perform for major version updates or when thorough validation needed:**

---

**Test 11: Full Build Cycle**

**Create a simple test app to verify entire build pipeline:**

```
/create
platform: android
stack: react-native

App Name: UpdateTestApp
Platform: Android
Description: Minimal test app to verify build pipeline after update. Single screen with text display.

Core Features:
- Single screen showing "Build Test Successful"
- App version display
- Built date display

No complex features, no integrations.
Purpose: Verify build pipeline works post-update.
```

**Monitor build stages:**
```
📋 S0 STARTED - Planning
[Wait for completion...]
📋 S0 COMPLETE - Planning (2m 18s) ✅

🎨 S1 STARTED - Design
[Wait for completion...]
🎨 S1 COMPLETE - Design (4m 12s) ✅

💻 S2 STARTED - Code Generation
[Wait for completion...]
💻 S2 COMPLETE - Code Generation (9m 35s) ✅

🧪 S3 STARTED - Testing
[Wait for completion...]
🧪 S3 COMPLETE - Testing (2m 47s) ✅

🏗️ S4 STARTED - Build
[Wait for completion...]
🏗️ S4 COMPLETE - Build (11m 22s) ✅

🔍 S5 STARTED - Quality Check
[Wait for completion...]
🔍 S5 COMPLETE - Quality Check (2m 08s) ✅

🚀 S6 STARTED - Deployment
[Wait for completion...]
🚀 S6 COMPLETE - Deployment (2m 41s) ✅

📊 S7 STARTED - Monitoring Setup
[Wait for completion...]
📊 S7 COMPLETE - Monitoring Setup (1m 23s) ✅

✅ BUILD COMPLETE - UpdateTestApp v1.0.0

Total time: 36m 26s
```

**What to verify:**
- ✅ All stages complete (S0-S7)
- ✅ No errors or warnings
- ✅ Build time reasonable (compare to pre-update)
- ✅ APK/IPA created successfully
- ✅ GitHub repository created
- ✅ Firebase deployment worked

**Performance comparison:**
```
Pre-update (v5.6.0): Avg 38m 15s
Post-update (v5.7.0): 36m 26s
Improvement: 1m 49s (4.8% faster) ✅

Note: v5.7.0 promised 15% faster S4 builds
S4 actual: 11m 22s vs 13m 10s pre-update = 13.6% faster ✅
```

---

**Test 12: App Installation & Testing**

**Install the test app:**

1. Download APK from Firebase App Distribution link
2. Install on test device
3. Open app
4. Verify displays correctly

**Expected result:**
- ✅ App installs without errors
- ✅ App opens successfully
- ✅ Displays "Build Test Successful"
- ✅ No crashes

**This confirms:**
- Build process works correctly
- Generated code is valid
- Deployment successful

---

**Test 13: Modify Existing Project**

**Test that /modify works with existing projects:**

```
/modify https://github.com/yourusername/habitflow

Add simple feature:
- On main screen, add "Version: 1.2.1" text at bottom
- Update version number 1.2.0 → 1.2.1
```

**Monitor modification:**
```
📝 S0 COMPLETE - Analysis (1m 42s) ✅
📋 S1 COMPLETE - Planning (2m 15s) ✅
💻 S2 COMPLETE - Code Modification (6m 32s) ✅
🧪 S3 COMPLETE - Testing (2m 18s) ✅
🏗️ S4 COMPLETE - Build (9m 47s) ✅
🔍 S5 COMPLETE - Quality Check (1m 28s) ✅
🚀 S6 COMPLETE - Deployment (2m 31s) ✅
📊 S7 COMPLETE - Monitoring Setup (0m 58s) ✅

✅ MODIFICATION COMPLETE - HabitFlow v1.2.1
```

**What to verify:**
- ✅ Modify process works on existing apps
- ✅ Version incremented correctly
- ✅ Changes applied
- ✅ Faster than /create (expected)

---

**Test 14: Service Integrations**

**Verify all external service integrations work:**

**GitHub integration:**
```
# Check if can create repository
/projects list

# Verify repository exists
Open browser: https://github.com/yourusername/updatetestapp
```

**Expected:** Repository exists with code ✅

---

**Firebase integration:**
```
# Check Firebase project
Open: https://console.firebase.google.com
Select project: [your project]
Check: App Distribution
```

**Expected:** APK uploaded, available for download ✅

---

**Anthropic API:**
```
/cost today
```

**Expected:** Shows API usage costs ✅

---

**Sentry (if configured):**
```
# Open Sentry dashboard
Open: https://sentry.io/[your-org]/updatetestapp

# Check if configured
Look for: Project created, SDK initialized
```

**Expected:** Project exists, no errors ✅

---

**Test 15: Cleanup & Maintenance**

**Verify maintenance commands work:**

```
/cleanup builds --dry-run
```

**Expected result:**
```
Cleanup Analysis (Dry Run - No Changes)

Old builds identified:
- Builds older than 30 days: 12 builds
- Total size: 2.4 GB

Files to be removed:
- /builds/archive/habitflow-v1.0.0.apk (45 MB)
- /builds/archive/studytimer-v0.9.0.apk (38 MB)
[... more files ...]

To execute cleanup: /cleanup builds --execute

This is a dry run - no files deleted ✅
```

**What to verify:**
- ✅ Cleanup command works
- ✅ Correctly identifies old builds
- ✅ Shows what would be deleted
- ✅ Dry run doesn't delete anything

---

**LEVEL 3 PASS CRITERIA:**

□ All Level 1 & 2 tests still pass
□ Full build cycle successful
□ Test app installs and runs
□ Modify works on existing projects
□ All service integrations functional
□ Maintenance commands operational
□ Performance meets or exceeds pre-update

**If ALL pass:** ✅ Update verified completely successful

**If ANY fail:** ⚠️ Investigate specific issue

---

### 6.5 Performance Benchmarking

**Compare performance before and after update:**

**Create benchmark report:**

```
PERFORMANCE COMPARISON
Update: v5.6.0 → v5.7.0
Date: 2026-04-10

BUILD PERFORMANCE:
                          v5.6.0      v5.7.0      Change
────────────────────────────────────────────────────────
Create (simple app):      38m 15s     36m 26s     -4.8% ✅
Modify (small change):    18m 40s     17m 23s     -6.8% ✅
Evaluation:               2m 15s      2m 10s      -3.7% ✅

STAGE BREAKDOWN:
S0 (Planning):            2m 30s      2m 18s      -8.0% ✅
S1 (Design):              4m 20s      4m 12s      -3.1% ✅
S2 (Code Gen):            10m 15s     9m 35s      -6.5% ✅
S3 (Testing):             2m 50s      2m 47s      -1.8% ✅
S4 (Build):               13m 10s     11m 22s     -13.6% ✅ (15% promised)
S5 (Quality):             2m 15s      2m 08s      -5.2% ✅
S6 (Deploy):              2m 35s      2m 41s      +3.9% (within variance)
S7 (Monitor):             1m 20s      1m 23s      +3.8% (within variance)

MEMORY USAGE:
Idle:                     2.3 GB      2.1 GB      -8.7% ✅
During build:             4.8 GB      4.5 GB      -6.3% ✅

API COSTS:
Create build:             $0.18       $0.16       -11.1% ✅
Modify build:             $0.12       $0.11       -8.3% ✅
Evaluation:               $0.02       $0.02       0%

ASSESSMENT: ✅ Performance improved across all metrics
Most significant: S4 build speed (13.6% faster as promised)
```

**Document this benchmark** for future reference.

---

### 6.6 Verification Checklist

**Complete this checklist before declaring update successful:**

**BASIC (Required):**
□ Pipeline starts without errors
□ Current version shows correctly (5.7.0)
□ All services connect (Anthropic, GitHub, Firebase)
□ Configuration preserved from pre-update
□ Logs accessible and readable
□ No critical errors in logs

**STANDARD (Recommended):**
□ Evaluation command works
□ Cost tracking functional
□ Queue management operational
□ New features accessible
□ Project list intact
□ All existing projects preserved

**COMPREHENSIVE (Major updates):**
□ Full build cycle successful
□ Test app created and runs
□ Modify works on existing projects
□ Service integrations verified
□ Cleanup commands work
□ Performance benchmarked
□ Performance meets expectations

**DOCUMENTATION:**
□ Post-update state documented
□ Benchmark results recorded
□ Any issues noted
□ Verification timestamp logged

**FINAL DECISION:**

If ALL required items checked:
✅ **UPDATE VERIFIED SUCCESSFUL**
- Can delete pre-update backup (after 1 week)
- Resume normal operations
- Document lessons learned

If ANY critical item fails:
⚠️ **ROLLBACK REQUIRED**
- Proceed to Section 5 (Rollback)
- Restore pre-update backup
- Investigate issue before retrying

---

## 7. SECTION 5: ROLLBACK PROCEDURES

**PURPOSE:** Restore previous version if update fails or causes problems.

**When to rollback:**
- ❌ Update fails completely
- ❌ Critical features broken
- ❌ Services won't connect
- ❌ Performance severely degraded
- ❌ Data loss detected

**When NOT to rollback:**
- ⚠️ Minor issues (fix forward instead)
- ⚠️ Cosmetic problems
- ⚠️ New features not working (but old features work)
- ⚠️ Just need configuration adjustment

---

### 7.1 Rollback Decision Tree

```
Issue detected after update
│
├─ Is pipeline completely broken?
│  ├─ YES → ROLLBACK IMMEDIATELY
│  └─ NO → Continue
│
├─ Are critical features broken?
│  ├─ YES → Can you fix quickly (<30 min)?
│  │   ├─ YES → Try fix first
│  │   └─ NO → ROLLBACK
│  └─ NO → Continue
│
├─ Is this just a minor issue?
│  ├─ YES → Fix forward (don't rollback)
│  └─ NO → Continue
│
├─ Can you work around it?
│  ├─ YES → Use workaround, fix later
│  └─ NO → ROLLBACK
│
└─ How urgent is fix?
   ├─ Critical (production down) → ROLLBACK
   ├─ High (blocking work) → ROLLBACK
   ├─ Medium (annoying) → Fix forward
   └─ Low (cosmetic) → Fix forward
```

---

### 7.2 Automatic Rollback (Fastest)

**If you used automatic update method:**

```
/rollback
```

**Pipeline asks for confirmation:**
```
⚠️ ROLLBACK REQUESTED

Current version: 5.7.0
Will rollback to: 5.6.0 (from backup: pre-update-5.7.0)

This will:
1. Stop pipeline
2. Restore code from backup
3. Restore configuration
4. Restart pipeline

⚠️ Any changes made after update will be lost

Backup details:
- Created: 2026-04-10 09:15:00
- Size: 892 MB
- Version: 5.6.0
- Status: ✅ Valid

Continue with rollback? (yes/no)
```

**Type:** `yes`

---

**Rollback process:**
```
🔄 Starting rollback: 5.7.0 → 5.6.0

Phase 1: Preparation
✅ Stopping pipeline
✅ Verifying backup integrity
✅ Preparing restore location

Phase 2: Code restoration
✅ Removing v5.7.0 installation
✅ Extracting v5.6.0 from backup
✅ Restoring files (543 MB)

Phase 3: Configuration restoration
✅ Restoring .env file
✅ Restoring config.json
✅ Restoring database

Phase 4: Verification
✅ Checking file integrity
✅ Verifying configuration
✅ Running post-restore checks

Phase 5: Restart
✅ Starting pipeline v5.6.0
✅ Connecting services
✅ Verifying functionality

✅ ROLLBACK COMPLETE

Restored to: v5.6.0
Time: 2m 45s
Previous state fully restored

Backup of v5.7.0 saved at:
~/ai-factory-pipeline/backups/failed-update-5.7.0.tar.gz
(In case you want to investigate the issue)

Next steps:
1. Verify: /status
2. Test: Basic operations
3. Document: What went wrong
4. Report: If pipeline bug (see RB2 Section 6)
```

---

**Verify rollback success:**
```
/version
```

**Should show:**
```
AI Factory Pipeline

Installed: v5.6.0 ✅
Released: March 1, 2026

Rollback successful
Previous version: 5.7.0 (rolled back due to issues)
```

---

### 7.3 Manual Rollback (If Automatic Fails)

**If automatic rollback doesn't work or pipeline won't start:**

---

**Step 1: Stop current (broken) installation**

```bash
# Force stop if needed
pkill -9 -f "factory.cli"

# Or on Windows
taskkill /F /IM python.exe
```

---

**Step 2: Locate backup**

```bash
ls -lh ~/ai-factory-pipeline/backups/

# Should see:
# pre-update-5.7.0.tar.gz.enc
```

**Or if manual backup:**
```bash
ls -lh ~/pipeline-backups/backup-20260410-*/
```

---

**Step 3: Remove broken installation**

```bash
# Rename (don't delete yet, in case needed)
mv ~/ai-factory-pipeline ~/ai-factory-pipeline-5.7.0-BROKEN
```

---

**Step 4: Restore from backup**

**If encrypted backup:**
```bash
# Decrypt and extract
cd ~/ai-factory-pipeline/backups
/path/to/pipeline-backup-tool decrypt pre-update-5.7.0.tar.gz.enc

# Extract
tar -xzf pre-update-5.7.0.tar.gz -C ~
```

**If unencrypted backup:**
```bash
tar -xzf ~/pipeline-backups/backup-20260410-*/pipeline.tar.gz -C ~
```

---

**Step 5: Restore configuration**

```bash
# Should be in backup, but verify
ls ~/ai-factory-pipeline/.env
ls ~/ai-factory-pipeline/config.json

# If missing, restore from manual backup
cp ~/pipeline-backups/backup-20260410-*/env-backup.txt ~/ai-factory-pipeline/.env
cp ~/pipeline-backups/backup-20260410-*/config-backup.json ~/ai-factory-pipeline/config.json
```

---

**Step 6: Restore dependencies**

**The old version might need old dependencies:**

```bash
cd ~/ai-factory-pipeline
pip install -r requirements.txt --break-system-packages
```

---

**Step 7: Start restored pipeline**

```bash
python -m factory.cli start
```

**Monitor startup:**
```
AI Factory Pipeline v5.6.0
Starting services...
✅ Core engine started
✅ Telegram bot connected
✅ External services verified
Pipeline is RUNNING
```

---

**Step 8: Verify restoration**

```
/status
/version
/projects list
```

**All should show v5.6.0 and pre-update state.**

---

### 7.4 Emergency Rollback (Complete Failure)

**If even manual rollback fails (very rare):**

**This means both current and backup are unusable.**

---

**Option 1: Restore from older backup**

```bash
# List all backups
ls -lht ~/ai-factory-pipeline/backups/

# Find earlier backup
# pre-update-5.6.0.tar.gz.enc (from previous update)

# Restore from that
[Follow manual rollback steps with older backup]
```

**Note:** May lose recent projects/data.

---

**Option 2: Fresh install + data migration**

**Last resort if no working backups:**

1. Download fresh v5.6.0 (or latest stable)
2. Install from scratch
3. Manually configure (API keys, etc.)
4. Reconnect to GitHub repositories
5. Rebuild history from GitHub

**See Section 5.4 (Fresh Install) from earlier.**

---

### 7.5 Post-Rollback Actions

**After successful rollback:**

**1. Document what happened**

```bash
cat > ~/Desktop/rollback-report-5.7.0.txt << EOF
ROLLBACK REPORT

Date: 2026-04-10 11:30:00
From: v5.7.0 (failed)
To: v5.6.0 (restored)

REASON FOR ROLLBACK:
[Describe issue that caused rollback]

SYMPTOMS:
- [What didn't work]
- [Error messages]
- [Impact on operations]

ROLLBACK PROCESS:
Method: Automatic
Time: 2m 45s
Status: Successful

CURRENT STATE:
✅ Pipeline running v5.6.0
✅ All services connected
✅ Projects intact
✅ Normal operations resumed

LESSONS LEARNED:
- [What to check before next update]
- [What went wrong]
- [How to prevent]

NEXT STEPS:
- Report bug if pipeline issue
- Wait for v5.7.1 fix
- Or stay on v5.6.0 until v5.8.0
EOF
```

---

**2. Report issue (if pipeline bug)**

**If update failed due to pipeline bug (not configuration issue):**

See RB2 Section 6 (Escalation) for bug reporting.

**Include:**
- Version attempted (5.7.0)
- Error messages
- Rollback logs
- Configuration (sanitized - no API keys)

---

**3. Clean up**

```bash
# After 1 week on stable v5.6.0:

# Remove broken v5.7.0
rm -rf ~/ai-factory-pipeline-5.7.0-BROKEN

# Remove failed update backup (if confident)
rm ~/ai-factory-pipeline/backups/failed-update-5.7.0.tar.gz

# Keep pre-update-5.7.0 backup for 1 month
# (In case need to reference)
```

---

**4. Decide next steps**

**Options:**

**A. Wait for fix release (5.7.1)**
- Issue reported
- Fix expected in patch release
- Update when available

**B. Stay on 5.6.0 indefinitely**
- 5.6.0 works fine
- Don't need 5.7.0 features
- Will update to 5.8.0 when available

**C. Try update again after investigation**
- Issue was configuration problem
- Now know how to fix
- Retry with adjustments

---

**5. Update documentation**

**Add to your update strategy document:**
```
UPDATE HISTORY

v5.7.0 - FAILED - 2026-04-10
Issue: [describe]
Rollback: Successful
Lesson: [what learned]
Status: Waiting for 5.7.1 or staying on 5.6.0

v5.6.0 - SUCCESS - 2026-03-01
Issue: None
Status: ✅ Current, stable
```

---

**✅ SECTIONS 4 & 5 COMPLETE**

You now know:
- ✅ How to verify updates (3 levels of testing)
- ✅ Performance benchmarking
- ✅ When to rollback vs fix forward
- ✅ Automatic rollback procedures
- ✅ Manual rollback procedures
- ✅ Emergency recovery options
- ✅ Post-rollback documentation

**Next (Part 4):**
- Section 6: Version-Specific Migration Guides
- Section 7: Dependency Management

---

**[END OF PART 3]**














---

# RB5: UPDATING AI FACTORY PIPELINE SYSTEM
## PART 4 of 5

---

## 8. SECTION 6: VERSION-SPECIFIC MIGRATION GUIDES

**PURPOSE:** Handle breaking changes and migrations for specific version updates.

**When to use:** When changelog shows "BREAKING CHANGES" or "MIGRATION REQUIRED".

---

### 8.1 Understanding Migration Requirements

**Not all updates require migration:**

**No migration needed:**
- ✅ Patch updates (5.6.0 → 5.6.1)
- ✅ Most minor updates (5.6.0 → 5.7.0)
- ✅ Backward-compatible changes

**Migration usually needed:**
- ⚠️ Major version updates (5.x → 6.x)
- ⚠️ Configuration format changes
- ⚠️ Database schema changes
- ⚠️ API structure changes

---

### 8.2 Reading Migration Guides

**Every release with breaking changes includes migration guide.**

**Where to find:**
```
# View from pipeline
/changelog v6.0.0 --migration

# Or online
https://github.com/[pipeline-repo]/blob/main/docs/migrations/5-to-6.md

# Or in installation
~/ai-factory-pipeline/docs/MIGRATION-6.0.0.md
```

---

**Standard migration guide format:**

```markdown
# Migration Guide: v5.x → v6.0.0

## Overview
This is a MAJOR version update with breaking changes.
Estimated migration time: 30-60 minutes

## Breaking Changes Summary
1. Python 3.11+ required (was 3.10+)
2. Configuration format: YAML → TOML
3. Execution modes renamed: LOCAL→DEVICE, CLOUD→REMOTE
4. Several commands removed
5. API endpoint structure changed

## Prerequisites
- [ ] Python 3.11 or higher installed
- [ ] Full backup created
- [ ] 1 hour available for migration
- [ ] Read this guide completely

## Migration Steps

### Step 1: Update Python
[Detailed instructions...]

### Step 2: Backup Current Installation
[Instructions...]

### Step 3: Run Migration Tool
python -m factory.migrate --from=5.x --to=6.0

### Step 4: Manual Configuration Updates
[Specific changes needed...]

### Step 5: Verify Migration
[Testing procedures...]

## Rollback Procedure
If migration fails:
1. Restore backup
2. Report issue with logs

## FAQ
Q: Do I have to migrate immediately?
A: No, v5.x supported until Dec 2026

Q: Will my apps still work?
A: Yes, built apps are unaffected
```

---

### 8.3 Common Migration Patterns

**Pattern A: Python Version Update**

**Symptom:**
```
BREAKING CHANGE: Requires Python 3.11+
Current: Python 3.10.8
```

**Migration:**

**Step 1: Check current version**
```bash
python --version
# Python 3.10.8
```

---

**Step 2: Install Python 3.11**

**macOS (Homebrew):**
```bash
brew update
brew install python@3.11

# Verify
python3.11 --version
# Python 3.11.7
```

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install python3.11 python3.11-venv python3.11-dev

# Verify
python3.11 --version
```

**Windows:**
1. Download Python 3.11 from python.org
2. Run installer
3. Check "Add to PATH"
4. Install

---

**Step 3: Create virtual environment (recommended)**
```bash
cd ~/ai-factory-pipeline
python3.11 -m venv venv-3.11

# Activate
source venv-3.11/bin/activate  # macOS/Linux
# Or
venv-3.11\Scripts\activate  # Windows

# Verify
python --version
# Python 3.11.7 (in virtual environment)
```

---

**Step 4: Reinstall dependencies**
```bash
pip install -r requirements.txt --break-system-packages
```

---

**Step 5: Update pipeline startup**

**Edit startup script to use Python 3.11:**
```bash
# Before:
python -m factory.cli start

# After:
python3.11 -m factory.cli start

# Or if using venv:
~/ai-factory-pipeline/venv-3.11/bin/python -m factory.cli start
```

---

**Pattern B: Configuration Format Change**

**Symptom:**
```
BREAKING CHANGE: Configuration format changed
Old: JSON (.env + config.json)
New: TOML (config.toml)
```

**Migration:**

**Step 1: Export old configuration**
```
/config export --format=json
```

**Saves to:**
```
~/ai-factory-pipeline/exports/config-export-v5.json
```

---

**Step 2: Run migration tool**
```bash
cd ~/ai-factory-pipeline
python -m factory.migrate config --from=json --to=toml
```

**Output:**
```
🔄 Migrating configuration: JSON → TOML

Reading old format:
✅ .env file parsed
✅ config.json parsed
✅ 47 settings found

Converting to TOML:
✅ Structure validated
✅ Types converted
✅ Comments preserved
✅ New format: config.toml

Backup created:
~/ai-factory-pipeline/config-backups/config-v5.json

✅ Migration complete

Old files preserved (renamed):
- .env → .env.v5.backup
- config.json → config.json.v5.backup

New file created:
- config.toml

Next: Verify configuration: /config show
```

---

**Step 3: Verify new format**

```
/config show
```

**Should display settings correctly from config.toml**

---

**Step 4: Test with new format**

```
/start
/status
```

**If services connect:** ✅ Migration successful

**If errors:** Check config.toml for issues, compare with backup

---

**Pattern C: Command Renamed/Removed**

**Symptom:**
```
BREAKING CHANGE: Commands changed
Removed: /build
Replaced with: /create

Removed: /deploy
Now automatic in /create
```

**Migration:**

**Step 1: Identify affected workflows**

**Review your documentation/scripts:**
```bash
# Check for old commands
grep -r "/build" ~/my-pipeline-scripts/
grep -r "/deploy" ~/my-pipeline-scripts/
```

---

**Step 2: Update scripts/documentation**

**Before (v5.x):**
```bash
# my-build-script.sh
/build --platform=android --spec=app-spec.txt
/deploy --target=firebase
```

**After (v6.x):**
```bash
# my-build-script.sh
/create platform:android < app-spec.txt
# (deploy now automatic, no separate command needed)
```

---

**Step 3: Update team documentation**

```markdown
# UPDATE NOTICE: Pipeline v6.0

## Command Changes

OLD COMMAND          | NEW COMMAND           | Notes
---------------------|----------------------|------------------------
/build               | /create              | Same functionality
/deploy              | (automatic)          | No longer needed
/queue show          | /queue               | Simplified
/project info [name] | /info [name]         | Renamed for clarity
```

---

**Pattern D: Execution Mode Rename**

**Symptom:**
```
BREAKING CHANGE: Execution modes renamed
LOCAL → DEVICE
CLOUD → REMOTE
HYBRID → ADAPTIVE
```

**Migration:**

**Automatic migration tool handles this:**
```bash
python -m factory.migrate modes
```

**Output:**
```
🔄 Migrating execution modes

Current configuration:
- Mode: LOCAL

Converting:
✅ LOCAL → DEVICE
✅ Configuration updated
✅ Historical data updated

New configuration:
- Mode: DEVICE

Note: Functionality unchanged, name only
```

**Manual migration (if automatic fails):**
```
# Update configuration
/config execution_mode DEVICE  # was LOCAL
```

---

**Pattern E: API Endpoint Structure Change**

**Symptom:**
```
BREAKING CHANGE: API structure changed
Old: /api/v1/builds
New: /api/v2/builds

Migration required for custom integrations
```

**This affects:**
- ❌ Most users (no custom integrations)
- ✅ Advanced users with custom tools
- ✅ Users with webhooks configured
- ✅ Users with external monitoring

**Migration:**

**If you have custom integrations:**

**Step 1: Identify integrations**
```bash
# Check for API usage
grep -r "api/v1" ~/my-tools/
```

---

**Step 2: Update API calls**

**Before (v5.x API):**
```python
# custom-monitor.py
import requests

response = requests.get(
    "http://localhost:8080/api/v1/builds/status"
)
```

**After (v6.x API):**
```python
# custom-monitor.py
import requests

response = requests.get(
    "http://localhost:8080/api/v2/builds/status"
)
```

---

**Step 3: Test integrations**
```bash
python custom-monitor.py --test
```

---

**If you DON'T have custom integrations:**

No action needed. Pipeline's internal API usage updates automatically.

---

### 8.4 Example Migration: v5.6 → v6.0

**Complete walkthrough of major version migration:**

**Starting point:**
- Current: v5.6.0
- Target: v6.0.0
- Time allocated: 2 hours

---

**Phase 1: Preparation (30 min)**

**Step 1: Read migration guide**
```
/changelog v6.0.0 --migration
```

**Note breaking changes:**
```
BREAKING CHANGES IN v6.0.0:
1. Python 3.11+ required ✓ (already have 3.11.2)
2. Config: JSON → TOML ✓ (will migrate)
3. Modes: LOCAL→DEVICE, CLOUD→REMOTE, HYBRID→ADAPTIVE ✓ (automatic)
4. Commands: /build removed (use /create) ✓ (already using /create)
5. API: v1 → v2 ✗ (no custom integrations, N/A)

Assessment: 2 items need action (config format, modes)
```

---

**Step 2: Create backup**
```
/backup create pre-update-6.0.0
```

**Step 3: Export configuration**
```
/config export
```

**Step 4: Document current state**
```
/status > ~/pre-6.0-status.txt
/projects list > ~/pre-6.0-projects.txt
/version > ~/pre-6.0-version.txt
```

---

**Phase 2: Migration Execution (45 min)**

**Step 5: Stop pipeline**
```
/stop
```

---

**Step 6: Download v6.0.0**
```bash
cd ~/Downloads
curl -L -O https://github.com/[pipeline-repo]/releases/download/v6.0.0/ai-factory-pipeline-6.0.0.tar.gz

# Verify checksum
shasum -a 256 ai-factory-pipeline-6.0.0.tar.gz
# Should match published checksum
```

---

**Step 7: Extract to temporary location**
```bash
mkdir ~/pipeline-6.0-temp
tar -xzf ai-factory-pipeline-6.0.0.tar.gz -C ~/pipeline-6.0-temp
```

---

**Step 8: Run migration tool**
```bash
cd ~/pipeline-6.0-temp/ai-factory-pipeline
python -m factory.migrate --from=~/ai-factory-pipeline --to=.
```

**Tool prompts:**
```
🔄 AI Factory Pipeline Migration Tool
From: v5.6.0 (~/ai-factory-pipeline)
To: v6.0.0 (current directory)

This will:
1. Migrate configuration (JSON → TOML)
2. Update execution modes (LOCAL→DEVICE, etc.)
3. Migrate database schema
4. Preserve all project data
5. Update historical data format

Backup verified: ✅ pre-update-6.0.0

Continue? (yes/no): yes

Phase 1: Configuration migration
Reading v5 config... ✅
Converting to TOML... ✅
Validating... ✅
Writing config.toml... ✅

Phase 2: Execution mode migration
Current mode: HYBRID
New mode: ADAPTIVE (equivalent)
Updated... ✅

Phase 3: Database migration
Schema v5 → v6... ✅
Data migration... ✅
Integrity check... ✅

Phase 4: Project data
Preserving project metadata... ✅
Updating build history format... ✅

Phase 5: Verification
Configuration valid... ✅
Database valid... ✅
All services compatible... ✅

✅ Migration complete

Summary:
- Configuration: Migrated to TOML
- Execution mode: HYBRID → ADAPTIVE
- Database: Updated to v6 schema
- Projects: 3 projects preserved
- Build history: 47 builds migrated

Ready to replace v5 installation.
```

---

**Step 9: Replace old installation**
```bash
# Backup old installation (extra safety)
mv ~/ai-factory-pipeline ~/ai-factory-pipeline-5.6.0-backup

# Move new installation
mv ~/pipeline-6.0-temp/ai-factory-pipeline ~/ai-factory-pipeline
```

---

**Step 10: Install dependencies**
```bash
cd ~/ai-factory-pipeline
pip install -r requirements.txt --upgrade --break-system-packages
```

---

**Phase 3: Verification (30 min)**

**Step 11: Start v6.0.0**
```bash
python -m factory.cli start
```

**Watch startup:**
```
AI Factory Pipeline v6.0.0
Starting services...

Configuration: config.toml ✅
Execution mode: ADAPTIVE ✅
Python: 3.11.2 ✅

Services:
✅ Anthropic API: Connected
✅ GitHub: Connected
✅ Firebase: Connected

✅ Pipeline is RUNNING

What's new in v6.0.0:
- New UI (try /dashboard)
- Multi-user support
- Advanced caching
- Real-time build monitoring

See: /help new-features
```

---

**Step 12: Verify configuration**
```
/config show
```

**Check:**
- ✅ All settings preserved
- ✅ API keys still valid
- ✅ Mode shows ADAPTIVE (was HYBRID)
- ✅ Using config.toml

---

**Step 13: Verify projects**
```
/projects list
```

**Check:**
- ✅ All 3 projects listed
- ✅ Repository links intact
- ✅ Versions preserved
- ✅ Build history accessible

---

**Step 14: Test basic operations**
```
# Test evaluation
/evaluate [simple test idea]

# Test cost tracking
/cost today

# Test logs
/logs recent
```

**All should work normally.**

---

**Step 15: Test build (optional but recommended)**

Create simple test app to verify full pipeline works:
```
/create
platform: android
stack: react-native

[Simple test spec]
```

**If build succeeds:** ✅ Migration fully successful

---

**Phase 4: Cleanup (15 min)**

**Step 16: Document migration**
```bash
cat > ~/migration-6.0-report.txt << EOF
MIGRATION COMPLETED SUCCESSFULLY

Date: 2026-04-10
From: v5.6.0
To: v6.0.0

Duration:
- Preparation: 30 min
- Execution: 45 min
- Verification: 30 min
- Total: 1h 45min

Issues encountered: None
Rollback needed: No

Post-migration state:
✅ All services operational
✅ All projects preserved
✅ Build pipeline functional
✅ Configuration migrated successfully

Backups preserved:
- ~/ai-factory-pipeline-5.6.0-backup
- Backup file: pre-update-6.0.0.tar.gz.enc

Notes:
- Execution mode HYBRID → ADAPTIVE (automatic)
- Config format JSON → TOML (automatic)
- No manual intervention needed
EOF
```

---

**Step 17: Clean up (after 1 week on stable v6.0.0)**
```bash
# Remove old backup installation
rm -rf ~/ai-factory-pipeline-5.6.0-backup

# Keep backup file for 1 month
# (Don't delete pre-update-6.0.0.tar.gz.enc yet)
```

---

## 9. SECTION 7: DEPENDENCY MANAGEMENT

**PURPOSE:** Manage Python packages, Node.js modules, and system dependencies during updates.

---

### 9.1 Understanding Pipeline Dependencies

**Pipeline requires three types of dependencies:**

**1. Python packages** (managed by pip)
- anthropic (Claude AI API)
- firebase-admin (Firebase services)
- github3.py (GitHub integration)
- requests (HTTP calls)
- 20+ other packages

**2. Node.js packages** (managed by npm)
- Required for build processes
- React Native CLI
- Metro bundler
- Various build tools

**3. System dependencies** (OS-level)
- Python 3.11+
- Node.js 18+
- Git
- Platform-specific tools (Xcode, Android SDK)

---

### 9.2 Python Dependency Management

**Checking current Python packages:**
```bash
pip list | grep -E "anthropic|firebase|github"
```

**Output:**
```
anthropic          0.25.0
firebase-admin     6.2.0
github3.py         3.2.0
```

---

**Updating Python dependencies:**

**Method 1: Update all (during pipeline update)**
```bash
cd ~/ai-factory-pipeline
pip install -r requirements.txt --upgrade --break-system-packages
```

**Method 2: Update specific package**
```bash
pip install anthropic --upgrade --break-system-packages
```

**Method 3: Install exact versions (for stability)**
```bash
pip install anthropic==0.28.0 --break-system-packages
```

---

**Handling dependency conflicts:**

**Symptom:**
```
ERROR: Cannot install anthropic 0.28.0
Requires: requests>=2.31.0
Installed: requests 2.28.0
```

**Solution A: Update conflicting package**
```bash
pip install requests --upgrade --break-system-packages
pip install anthropic==0.28.0 --break-system-packages
```

**Solution B: Use requirements.txt (recommended)**
```bash
# Pipeline's requirements.txt has compatible versions
pip install -r requirements.txt --upgrade --break-system-packages
```

---

**Using virtual environments (recommended for isolation):**

**Create virtual environment:**
```bash
cd ~/ai-factory-pipeline
python3.11 -m venv venv

# Activate
source venv/bin/activate  # macOS/Linux
# Or
venv\Scripts\activate  # Windows
```

**Install dependencies in venv:**
```bash
pip install -r requirements.txt
```

**Benefits:**
- ✅ Isolated from system Python
- ✅ No conflicts with other projects
- ✅ Easy to recreate if corrupted
- ✅ No need for --break-system-packages

**Activate venv before using pipeline:**
```bash
source ~/ai-factory-pipeline/venv/bin/activate
python -m factory.cli start
```

---

### 9.3 Node.js Dependency Management

**Checking Node.js version:**
```bash
node --version
# v18.16.0

npm --version
# 9.5.0
```

---

**Updating Node.js (if needed):**

**macOS (using nvm - recommended):**
```bash
# Install nvm if not already
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.0/install.sh | bash

# Install Node.js 18
nvm install 18
nvm use 18
nvm alias default 18

# Verify
node --version
```

**Ubuntu:**
```bash
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt-get install -y nodejs

# Verify
node --version
```

**Windows:**
Download from nodejs.org and run installer.

---

**Updating Node.js packages:**

**Update npm itself:**
```bash
npm install -g npm@latest
```

**Update global packages:**
```bash
# List outdated
npm outdated -g

# Update specific package
npm update -g react-native-cli

# Update all global packages
npm update -g
```

**Pipeline-specific Node packages:**

Most managed automatically by pipeline, but if needed:
```bash
cd ~/ai-factory-pipeline
npm install  # Install/update packages
npm audit fix  # Fix security vulnerabilities
```

---

### 9.4 System Dependency Updates

**Updating Git:**

**macOS:**
```bash
brew upgrade git
```

**Ubuntu:**
```bash
sudo apt update
sudo apt upgrade git
```

**Windows:**
Download latest from git-scm.com

---

**Platform-specific tools:**

**For iOS builds (macOS only):**
```bash
# Update Xcode from App Store
# Then update command line tools:
xcode-select --install
```

**For Android builds:**
```bash
# Update Android SDK via Android Studio
# Tools → SDK Manager → SDK Tools → Update
```

---

### 9.5 Dependency Verification

**Before updating pipeline, verify all dependencies:**

```
/check-dependencies
```

**Output:**
```
Dependency Check

PYTHON:
✅ Version: 3.11.2 (required: 3.11+)
✅ pip: 23.0.1

PYTHON PACKAGES:
✅ anthropic: 0.25.0 (required: 0.25.0+)
✅ firebase-admin: 6.2.0 (required: 6.0.0+)
✅ github3.py: 3.2.0 (required: 3.0.0+)
⚠️ requests: 2.28.0 (recommended: 2.31.0+)

NODE.JS:
✅ Version: 18.16.0 (required: 18.0.0+)
✅ npm: 9.5.0

SYSTEM:
✅ Git: 2.40.0 (required: 2.30.0+)
✅ Xcode: 14.3 (required: 14.0+) [macOS only]
✅ Android SDK: 33.0.0 (required: 30.0.0+)

WARNINGS:
⚠️ requests package outdated (not critical)

RECOMMENDATION:
Update requests: pip install requests --upgrade
Then proceed with pipeline update.
```

---

### 9.6 Dependency Troubleshooting

**Issue: "ModuleNotFoundError: No module named 'anthropic'"**

**Cause:** Python package not installed or wrong Python version

**Solution:**
```bash
# Verify Python version
python --version

# Install missing package
pip install anthropic --break-system-packages

# Or reinstall all
pip install -r ~/ai-factory-pipeline/requirements.txt --break-system-packages
```

---

**Issue: "npm ERR! code EACCES"**

**Cause:** Permission issue with global npm packages

**Solution:**
```bash
# Fix npm permissions (macOS/Linux)
mkdir ~/.npm-global
npm config set prefix '~/.npm-global'

# Add to PATH (add to ~/.bashrc or ~/.zshrc)
export PATH=~/.npm-global/bin:$PATH

# Reload shell
source ~/.bashrc  # or source ~/.zshrc

# Retry npm install
npm install -g [package]
```

---

**Issue: "Python version mismatch"**

**Cause:** Multiple Python versions, using wrong one

**Solution:**
```bash
# Find all Python installations
which -a python python3 python3.11

# Use specific version
python3.11 -m factory.cli start

# Or set up alias
alias python=python3.11
```

---

**Issue: "Dependency conflict cannot be resolved"**

**Cause:** Two packages require incompatible versions of same dependency

**Solution:**
```bash
# Create fresh virtual environment
cd ~/ai-factory-pipeline
rm -rf venv  # Remove old venv
python3.11 -m venv venv
source venv/bin/activate

# Install fresh
pip install -r requirements.txt

# This usually resolves conflicts
```

---

### 9.7 Dependency Update Schedule

**Recommended update frequency:**

**Python packages:**
- Security updates: Immediately
- Minor updates: Monthly
- Major updates: With pipeline updates

**Node.js:**
- LTS versions: Every 6 months
- Security patches: As released

**System tools:**
- Git: Every 3 months
- Xcode: Every iOS release (annually)
- Android SDK: Every Android release (annually)

---

**Monthly dependency maintenance:**

```bash
# First Monday of month
cd ~/ai-factory-pipeline

# Activate venv
source venv/bin/activate

# Update Python packages
pip list --outdated
pip install -r requirements.txt --upgrade

# Update Node.js
npm outdated -g
npm update -g

# Update system tools
brew upgrade  # macOS
# or
sudo apt update && sudo apt upgrade  # Ubuntu

# Test pipeline
python -m factory.cli start
/status
```

**Document:**
```
Dependency Update Log

Date: 2026-04-10
Updated:
- anthropic: 0.25.0 → 0.28.0
- firebase-admin: 6.2.0 → 6.3.0
- npm: 9.5.0 → 9.8.0

Test results: All passing
Issues: None
```

---

**✅ SECTIONS 6 & 7 COMPLETE**

You now know:
- ✅ How to read migration guides
- ✅ Common migration patterns
- ✅ Complete example migration (v5→v6)
- ✅ Breaking change handling
- ✅ Python dependency management
- ✅ Node.js dependency management
- ✅ System dependency updates
- ✅ Dependency troubleshooting

**Next (Part 5 - FINAL):**
- Section 8: Troubleshooting Update Issues
- Quick Reference
- Summary & Next Steps

---

**[END OF PART 4]**















---

# RB5: UPDATING AI FACTORY PIPELINE SYSTEM
## PART 5 of 5 (FINAL)

---

## 10. SECTION 8: TROUBLESHOOTING UPDATE ISSUES

**PURPOSE:** Diagnose and resolve problems that occur during or after updates.

**Common update failure scenarios:**
1. Update fails to start
2. Update hangs/freezes mid-process
3. Update completes but pipeline won't start
4. Update succeeds but features broken
5. Performance degraded after update
6. Services won't connect after update

---

### 10.1 Issue: Update Won't Start

**Symptom:**
```
/update

❌ Cannot start update
Error: Prerequisites not met
```

---

**Diagnosis & Solutions:**

**Check 1: Disk space**
```bash
df -h ~
```

**If <3GB free:**
```bash
# Clean up old builds
/cleanup builds --execute

# Remove old logs
/cleanup logs --older-than 30-days

# Check again
df -h ~
```

---

**Check 2: Running builds**
```
/queue
```

**If builds active:**
```
# Cancel builds
/cancel [build-id]

# Or wait for completion
[Wait...]

# Retry update
/update
```

---

**Check 3: Pipeline not stopped**
```
/status
```

**If RUNNING:**
```
# Stop pipeline
/stop

# Verify stopped
/status  # Should show NOT RUNNING

# Retry update
/update
```

---

**Check 4: Internet connection**
```bash
ping -c 4 google.com
```

**If no connection:**
- Fix internet connection
- Or download update manually (see Section 5.3)

---

**Check 5: Permission issues**
```bash
# Check if you have write access
touch ~/ai-factory-pipeline/test.txt
rm ~/ai-factory-pipeline/test.txt
```

**If permission denied:**
```bash
# Fix ownership (macOS/Linux)
sudo chown -R $USER ~/ai-factory-pipeline

# Or run with appropriate permissions
```

---

### 10.2 Issue: Update Hangs/Freezes

**Symptom:**
```
🔄 Starting update: 5.6.0 → 5.7.0

Phase 2: Download
Downloading v5.7.0... [########--------] 45%

[Stuck at 45% for 10+ minutes]
```

---

**Diagnosis:**

**Check 1: Network issues**
```bash
# Test download speed
curl -o /tmp/test.zip http://speedtest.tele2.net/10MB.zip

# If very slow or timing out → network problem
```

**Solution:**
- Wait for better connection
- Try different time (off-peak hours)
- Use wired connection instead of WiFi

---

**Check 2: Process frozen**

```bash
# Check if process still running
ps aux | grep factory

# Check CPU usage
top  # Look for factory processes
```

**If process consuming 0% CPU for >5 minutes:**

Process likely frozen.

**Solution:**
```bash
# Cancel frozen process
pkill -9 -f "factory"

# Clean up partial download
rm -rf ~/ai-factory-pipeline/.update-temp

# Retry update
python -m factory.cli update
```

---

**Check 3: Disk full during download**

```bash
df -h ~
```

**If disk full:**
```bash
# Free up space
/cleanup builds --aggressive
/cleanup logs --all

# Retry update
/update
```

---

### 10.3 Issue: Update Completes But Pipeline Won't Start

**Symptom:**
```
✅ UPDATE COMPLETE

Updated: 5.6.0 → 5.7.0

[Try to start]
python -m factory.cli start

❌ Error: Module not found
ModuleNotFoundError: No module named 'anthropic'
```

---

**Diagnosis & Solutions:**

**Issue A: Dependencies not installed**

**Solution:**
```bash
cd ~/ai-factory-pipeline
pip install -r requirements.txt --upgrade --break-system-packages

# Then start
python -m factory.cli start
```

---

**Issue B: Python version mismatch**

**Check Python version:**
```bash
python --version
# Python 3.10.8

# But update requires 3.11+
```

**Solution:**
```bash
# Install Python 3.11
[Follow Python update procedure from Section 6.3]

# Use correct Python
python3.11 -m factory.cli start
```

---

**Issue C: Configuration corrupted**

**Symptom:**
```
❌ Error: Configuration file invalid
Cannot parse config.toml
```

**Solution:**
```bash
# Restore configuration from backup
cp ~/ai-factory-pipeline/config-backups/config-v5.json.backup \
   ~/ai-factory-pipeline/config-backup.json

# Re-run migration
python -m factory.migrate config --from=json --to=toml

# Start pipeline
python -m factory.cli start
```

---

**Issue D: Port conflict**

**Symptom:**
```
❌ Error: Cannot bind to port 8080
Port already in use
```

**Solution:**
```bash
# Find what's using port
lsof -i :8080  # macOS/Linux

# Or
netstat -ano | findstr :8080  # Windows

# Kill process or change pipeline port
/config port 8081
/start
```

---

### 10.4 Issue: Services Won't Connect After Update

**Symptom:**
```
/status

Pipeline Status: ✅ RUNNING
Version: 5.7.0

Services:
❌ Anthropic API: Connection failed
❌ GitHub: Authentication failed
✅ Firebase: Connected
❌ Sentry: Connection failed
```

---

**Diagnosis & Solutions:**

**Issue A: API keys invalid/expired**

**Check 1: Anthropic API key**
```
/config verify anthropic_api_key
```

**If invalid:**
```
# Get new key from console.anthropic.com
# Update configuration
/config anthropic_api_key sk-ant-api03-[new-key]
/restart
```

---

**Check 2: GitHub token**
```
/config verify github_token
```

**If invalid:**
```
# Generate new token at github.com/settings/tokens
# Update configuration
/config github_token ghp_[new-token]
/restart
```

---

**Issue B: Service URLs changed in update**

**For v6.0.0 example - API endpoints changed**

**Solution:**
```bash
# Run endpoint migration
python -m factory.migrate endpoints

# Restart
/restart
```

---

**Issue C: Firewall blocking new connections**

**Test connectivity:**
```bash
# Test Anthropic API
curl https://api.anthropic.com/v1/messages

# Test GitHub API
curl https://api.github.com

# If timeout → firewall issue
```

**Solution:**
- Configure firewall to allow pipeline
- Or temporarily disable firewall to test
- Update firewall rules if needed

---

### 10.5 Issue: Performance Degraded After Update

**Symptom:**
Builds taking significantly longer after update.

**Before update:** 35 minutes average
**After update:** 60 minutes average (70% slower)

---

**Diagnosis:**

**Check 1: Resource usage**
```
/status
```

Look at CPU/Memory during build.

**If very high:**
- May be background processes
- System resource constraints
- Memory leak in new version

---

**Check 2: Execution mode changed**

```
/config show execution_mode
```

**If mode changed:**
```
# Before: HYBRID
# After: LOCAL (slower on low-spec machine)

# Change back
/config execution_mode HYBRID
/restart
```

---

**Check 3: Caching disabled**

**Some updates reset cache settings:**
```
/config show cache_enabled
```

**If false:**
```
/config cache_enabled true
/restart
```

---

**Check 4: New version overhead**

**First few builds after update may be slower:**
- Rebuilding caches
- Optimizing new code paths
- Normal after major update

**Wait for 3-5 builds to see if performance normalizes.**

---

**If performance still poor after 5 builds:**

**Benchmark and report:**
```bash
# Create performance report
cat > ~/performance-report.txt << EOF
Performance Issue After Update

Version: 5.7.0 (updated from 5.6.0)
Date: 2026-04-10

Build times comparison:
- Pre-update average: 35 minutes
- Post-update average: 60 minutes
- Degradation: 71% slower

System:
- OS: macOS 13.2
- RAM: 8 GB
- CPU: Intel i5
- Mode: HYBRID

Affected stages:
- S2: 10 min → 18 min (+80%)
- S4: 12 min → 22 min (+83%)

Request investigation.
EOF

# Report issue
/report-issue
[Attach performance-report.txt]
```

---

### 10.6 Issue: Features Broken After Update

**Symptom:**
Update succeeds, pipeline runs, but specific features don't work.

---

**Example A: Evaluation fails**

```
/evaluate [test idea]

❌ Error: Evaluation failed
API call timeout
```

**Solution:**
```bash
# Check Anthropic API status
curl https://status.anthropic.com

# If service operational, check API key
/config verify anthropic_api_key

# Regenerate if needed
/config anthropic_api_key [new-key]
/restart
```

---

**Example B: Builds fail at specific stage**

```
All builds fail at S4 with:
❌ S4 FAILED - Build
Error: Command not found: gradle
```

**Likely cause:** Build tools not configured

**Solution:**
```bash
# Reinstall build dependencies
cd ~/ai-factory-pipeline
python -m factory.setup install-build-tools

# Restart
/restart

# Retry build
/retry [build-id]
```

---

**Example C: New features not accessible**

```
Changelog says: "NEW: Parallel builds"

But:
/parallel

❌ Error: Command not found
```

**Likely cause:** Feature not enabled or misconfigured

**Solution:**
```
# Check feature flags
/config show features

# Enable if disabled
/config features.parallel_builds true
/restart

# Try again
/parallel status
```

---

### 10.7 Common Error Messages & Solutions

**Quick reference table:**

| Error Message | Cause | Solution |
|---------------|-------|----------|
| "Python version too old" | Python <3.11 | Update Python to 3.11+ |
| "ModuleNotFoundError" | Missing package | `pip install -r requirements.txt` |
| "Port already in use" | Port conflict | Change port or kill process |
| "Authentication failed" | Invalid API key | Regenerate and update key |
| "Configuration invalid" | Config corrupted | Restore from backup |
| "Disk space insufficient" | <3GB free | Clean up old builds/logs |
| "Cannot download update" | Network issue | Check connection, retry |
| "Migration failed" | Incompatible data | Rollback, report issue |
| "Service timeout" | API slow/down | Check status page, retry |
| "Permission denied" | Lacking permissions | Fix ownership/permissions |

---

## 11. QUICK REFERENCE

### 11.1 Pre-Update Checklist

```
BEFORE EVERY UPDATE:

□ Read changelog completely
□ Identify breaking changes
□ Check prerequisites (Python, disk space, etc.)
□ Create full backup: /backup create pre-update-X.Y.Z
□ Export configuration: /config export
□ Document current state
□ Stop all builds: /cancel [all]
□ Stop pipeline: /stop
□ Allocate 1-2 hours
□ Have rollback plan ready
```

---

### 11.2 Update Commands Quick Reference

```bash
# Check current version
/version

# Check for updates
/check-updates

# Automatic update (recommended)
/update

# Manual update
cd ~/Downloads
curl -L -O [update-url]
tar -xzf ai-factory-pipeline-X.Y.Z.tar.gz -C ~
mv ~/ai-factory-pipeline ~/ai-factory-pipeline-backup
mv ~/ai-factory-pipeline-X.Y.Z ~/ai-factory-pipeline
pip install -r requirements.txt --upgrade

# Migration (if required)
python -m factory.migrate

# Rollback (if needed)
/rollback

# Verify after update
/status
/version
/projects list
```

---

### 11.3 Post-Update Verification Checklist

```
AFTER EVERY UPDATE:

Level 1 (Required - 5-10 min):
□ Pipeline starts: /start
□ Version correct: /version
□ Services connect: /status
□ Configuration preserved: /config show
□ No errors in logs: /logs recent

Level 2 (Recommended - 15-20 min):
□ Evaluation works: /evaluate [test]
□ Cost tracking works: /cost today
□ Queue functional: /queue
□ Projects preserved: /projects list
□ New features accessible

Level 3 (Major updates - 30-45 min):
□ Full build successful
□ Test app installs and runs
□ Modify existing project works
□ All integrations functional
□ Performance benchmarked
```

---

### 11.4 Troubleshooting Decision Tree

```
Update issue occurred
│
├─ When did it happen?
│  ├─ Before update starts → Check prerequisites
│  ├─ During update → Check network, disk space
│  ├─ After update → Check logs, verify config
│  └─ Days after update → Likely unrelated
│
├─ Can pipeline start?
│  ├─ NO → Check dependencies, Python version
│  └─ YES → Continue
│
├─ Do services connect?
│  ├─ NO → Verify API keys, check service status
│  └─ YES → Continue
│
├─ Does basic functionality work?
│  ├─ NO → Consider rollback
│  └─ YES → Fix specific issues
│
└─ Is performance acceptable?
   ├─ NO → Check mode, resources, report if persistent
   └─ YES → Update successful ✅
```

---

### 11.5 When to Rollback vs Fix Forward

**ROLLBACK if:**
- ❌ Pipeline completely broken
- ❌ Critical features non-functional
- ❌ Can't fix within 1 hour
- ❌ Blocking production work
- ❌ Data corruption detected

**FIX FORWARD if:**
- ✅ Minor issues only
- ✅ Easy configuration fix
- ✅ Non-critical features affected
- ✅ Workaround available
- ✅ Official fix coming soon

---

### 11.6 Update Frequency Recommendations

```
TYPE           FREQUENCY        URGENCY
─────────────────────────────────────────────
Security       Immediate        Within 48h
Patch (X.X.N)  Every 2-4 weeks  Low priority
Minor (X.N.X)  Every 2-3 months Medium priority
Major (N.X.X)  1-2 per year     High planning needed

STRATEGY:
- Stay within 1 minor version of latest
- Never skip security updates
- Test major updates before deploying
- Update during low-activity periods
```

---

## 12. SUMMARY & NEXT STEPS

### 12.1 What You've Learned

**Update Strategy & Planning:**
✅ Understanding version numbers (MAJOR.MINOR.PATCH)
✅ Reading changelogs effectively
✅ When to update vs when to wait
✅ Release channels (stable/beta/nightly)
✅ Creating update plans

**Pre-Update Preparation:**
✅ Comprehensive backup procedures
✅ Configuration export and documentation
✅ System state documentation
✅ Stopping pipeline safely

**Update Execution:**
✅ Three update methods (automatic/manual/fresh install)
✅ Handling prerequisites
✅ Monitoring update progress
✅ Dealing with update failures

**Post-Update Verification:**
✅ Three-level testing approach
✅ Performance benchmarking
✅ Service verification
✅ Feature testing

**Rollback Procedures:**
✅ When to rollback vs fix forward
✅ Automatic rollback process
✅ Manual rollback procedures
✅ Emergency recovery

**Migration Handling:**
✅ Reading migration guides
✅ Common migration patterns
✅ Breaking change handling
✅ Configuration migrations

**Dependency Management:**
✅ Python package updates
✅ Node.js updates
✅ System dependency management
✅ Virtual environments

**Troubleshooting:**
✅ Common update issues
✅ Service connection problems
✅ Performance degradation
✅ Feature breakage

---

### 12.2 Update Mastery Levels

**After completing this runbook, you should achieve:**

**LEVEL 1: Basic Updates (Patches)**
- ✅ Update patch versions safely
- ✅ Verify updates successful
- ✅ Rollback if needed
- ✅ Handle common issues

**LEVEL 2: Standard Updates (Minors)**
- ✅ Plan and execute minor updates
- ✅ Handle configuration changes
- ✅ Manage dependencies
- ✅ Test comprehensively

**LEVEL 3: Advanced Updates (Majors)**
- ✅ Execute major version migrations
- ✅ Handle breaking changes
- ✅ Multi-version jumps
- ✅ Fresh install with data migration

**LEVEL 4: Expert Operations**
- ✅ Optimize update processes
- ✅ Automate routine updates
- ✅ Contribute to documentation
- ✅ Help others with updates

---

### 12.3 Your Update Toolkit

**You now have:**

**1. This runbook (RB5)** - 35 pages
- Complete update procedures
- Troubleshooting guides
- Migration examples
- Quick references

**2. Update templates**
- Pre-update checklist
- Update plan template
- Verification checklist
- Rollback decision tree

**3. Backup strategies**
- Automatic backup procedures
- Manual backup methods
- Configuration export
- State documentation

**4. Testing frameworks**
- Level 1: Basic verification
- Level 2: Standard testing
- Level 3: Comprehensive validation
- Performance benchmarking

**5. Recovery procedures**
- Automatic rollback
- Manual rollback
- Emergency recovery
- Data restoration

---

### 12.4 Best Practices Summary

**BEFORE UPDATES:**
1. Always read changelog completely
2. Create full backup (verify backup works)
3. Export and document configuration
4. Plan sufficient time (don't rush)
5. Update during low-activity periods

**DURING UPDATES:**
1. Monitor progress actively
2. Watch for errors/warnings
3. Don't interrupt update process
4. Keep backup accessible
5. Document any issues

**AFTER UPDATES:**
1. Verify all services connect
2. Test basic functionality
3. Run at least one build
4. Benchmark performance
5. Document results

**ALWAYS:**
1. Stay reasonably current (within 1-2 minor versions)
2. Never skip security updates
3. Test before deploying to production
4. Keep backups for 1 month minimum
5. Document lessons learned

---

### 12.5 Maintenance Schedule

**Create recurring calendar reminders:**

**WEEKLY (Every Monday):**
```
□ Check for security updates
□ Review pipeline status
□ Monitor for issues
```

**MONTHLY (First Monday):**
```
□ Check for new releases
□ Update dependencies (Python, Node)
□ Review update notes
□ Plan updates if needed
```

**QUARTERLY (First Monday of Jan/Apr/Jul/Oct):**
```
□ Execute planned updates
□ Full system verification
□ Backup verification
□ Documentation review
```

**ANNUALLY (January):**
```
□ Review update strategy
□ Evaluate release channels
□ Plan major version updates
□ Update workflows/documentation
```

---

### 12.6 What to Read Next

**Based on your situation:**

**If you just completed an update:**
→ Continue normal operations (see RB1)
→ Monitor for issues next few days
→ Document lessons learned

**If planning first update:**
→ Review this runbook completely
→ Create update plan (Section 3.5)
→ Schedule update window
→ Execute when ready

**If update failed:**
→ Review Section 8 (Troubleshooting)
→ Check rollback procedures (Section 5)
→ Report issue if pipeline bug

**If managing multiple installations:**
→ Create standardized update procedure
→ Test on development instance first
→ Roll out to production
→ Document organization-specific steps

**If contributing to pipeline:**
→ Review migration guide templates
→ Understand version strategy
→ Follow semantic versioning
→ Help improve update process

---

### 12.7 Advanced Topics

**Beyond this runbook:**

**Automated Updates (Advanced):**
- Scripting update procedures
- Continuous integration
- Automated testing
- Scheduled updates

**Multi-Environment Management:**
- Development/staging/production
- Phased rollouts
- Canary deployments
- Blue-green updates

**Team Coordination:**
- Update communication
- Shared update schedules
- Coordination procedures
- Rollback coordination

**Custom Modifications:**
- Preserving customizations
- Custom migration scripts
- Integration updates
- Plugin compatibility

These topics covered in advanced documentation (if you need them).

---

### 12.8 Getting Help

**If you encounter update issues:**

**Self-Service Resources:**
1. This runbook (RB5) - comprehensive guide
2. RB2 (Troubleshooting) - general problem-solving
3. Pipeline changelog - version-specific notes
4. Migration guides - breaking change details

**Community Support:**
1. GitHub Issues - bug reports, questions
2. Discord/Slack - quick help from community
3. Documentation - official guides

**Direct Support (if available):**
1. Email support - detailed assistance
2. Emergency escalation - critical issues
3. Custom migration help - complex scenarios

**When asking for help, provide:**
- Current version
- Target version
- Update method used
- Error messages (complete)
- Logs (recent)
- What you've tried

---

### 12.9 Contributing Back

**Help improve the update experience:**

**Share your experience:**
- Document your successful migrations
- Report issues you encountered
- Suggest documentation improvements
- Help others in community

**Contribute to pipeline:**
- Submit bug reports
- Suggest features
- Improve migration tools
- Update documentation

**Build community knowledge:**
- Write blog posts about updates
- Create video tutorials
- Share automation scripts
- Document edge cases

---

### 12.10 Final Thoughts

**You now have complete knowledge of pipeline updates.**

**Key principles to remember:**

**1. Updates are normal and healthy**
- Stay reasonably current
- Security updates are critical
- Plan updates, don't rush

**2. Preparation prevents problems**
- Always backup first
- Read changelogs completely
- Test before deploying

**3. Verification ensures success**
- Don't assume updates worked
- Test systematically
- Benchmark performance

**4. Rollback is a valid option**
- Not every update will work
- Having backup = confidence
- Fix forward when possible, rollback when necessary

**5. Documentation enables learning**
- Write down what you do
- Note what works/doesn't work
- Build your own knowledge base

**6. Community makes everyone better**
- Share your experiences
- Help others
- Report issues
- Contribute improvements

---

**You're ready to update confidently.**

Updates will become routine with practice.

First few updates: Follow checklist carefully
After 5 updates: Process becomes familiar
After 10 updates: Can do with minimal reference

**Keep this runbook handy. Reference as needed.**

**Go forth and update safely!**

---

**═══════════════════════════════════════════════════════════════**
**END OF RB5: UPDATING AI FACTORY PIPELINE SYSTEM**
**═══════════════════════════════════════════════════════════════**
