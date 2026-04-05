# AI FACTORY PIPELINE v5.6
# MASTER IMPLEMENTATION GUIDE — PART 3
## NB4: Complete Execution + Daily Operations Reference

---

> **Where you are:** NB3 is complete. The pipeline is live in production.
> Cloud Run is running. Telegram responds. Two real apps have been built.
> The repo is tagged `v5.6.0-production`.
>
> **What this part covers:**
> - NB4 (15–20 days, ~$30–50 in AI spend): GitHub Actions CI/CD,
>   MacinCloud iOS builds, App Store delivery, Modify Mode, revenue ops,
>   final certification. Tag `v5.6.0-complete`.
> - Daily Operations Reference: Morning routine, all Telegram commands,
>   weekly/monthly maintenance, cost optimisation.
>
> **Starting condition check:**

```bash
cd ~/Projects/ai-factory-pipeline
source .venv/bin/activate
git tag | grep production       # Should show v5.6.0-production
python -m pytest tests/ -v 2>&1 | tail -3  # 362+ passed, 0 failed
curl -s $SERVICE_URL/health     # {"status":"healthy","version":"5.6.0"}
```

> All three must pass. If any fail, resolve them before continuing.

---

# SECTION 30: NB4 OVERVIEW

## 30.1 What NB4 Builds

NB4 is the final implementation notebook. It takes the pipeline from
"can build apps and deliver them to Telegram" to "can submit real
binaries to the App Store and Google Play, update existing apps, and
track revenue."

```
NB4 PHASE MAP
═══════════════════════════════════════════════════════

Phase A — Real Build Execution (Parts 1–4, ~3 days)
  GitHub Actions workflows for all 6 stacks
  First real binary: Python backend on Cloud Run

Phase B — MacinCloud + GUI Automation (Parts 5–8, ~3 days)
  SSH session management, $1/hr kill switch
  5-layer OmniParser + UI-TARS automation stack
  FlutterFlow and Unity GUI builds

Phase C — Real App Store Deployment (Parts 9–13, ~3 days)
  Apple Developer API (certificates, signing, Transporter)
  Google Play Console API (AAB upload, internal track)
  Firebase full-stack provisioning

Phase D — End-to-End Binary Delivery (Parts 14–16, ~2 days)
  First real APK delivered to operator
  First real IPA through TestFlight
  First real web app on Firebase Hosting

Phase E — Local + Hybrid Execution (Parts 17–19, ~2 days)
  Cloudflare Tunnel setup
  LOCAL mode: build on your Mac, save MacinCloud cost
  HYBRID mode: cloud AI + local build

Phase F — Modify Mode (Parts 20–23, ~2 days)
  PipelineMode enum: CREATE vs MODIFY
  Codebase ingestion for existing repos
  Diff-based code generation
  Semantic version management

Phase G — Revenue Operations (Parts 24–26, ~2 days)
  /evaluate command (idea viability scoring)
  /revenue /invoice /clients commands
  Customer and pricing tables

Phase H — Operational Completeness (Parts 27–28, ~1 day)
  4 complete operator runbooks
  Day-2+ procedures: billing, cleanup, key rotation

Phase I — Final Validation (Parts 29–30, ~1 day)
  84-criteria Production Readiness Scorecard
  v5.6.0-complete tag
═══════════════════════════════════════════════════════
```

**Cost estimate:** ~$30–50 AI spend across all 30 NB4 parts.
MacinCloud iOS builds cost $1/hr; budget approximately $8–15 for
test builds during Phases B–D.

---

# SECTION 31: NB4 PHASE A — REAL BUILD EXECUTION (PARTS 1–4)
📖 **Read first:** NB4 Parts 1–4 + Spec §4.5, §4.5.1, Appendix D

## STEP 31.1 — Part 1: GitHub Actions CI/CD Foundation

**What this builds:** Six workflow YAML templates — one per stack —
that GitHub Actions uses to build real binaries. Also updates
`factory/integrations/github.py` to dispatch workflows and download
the resulting artifacts.

**USE CLAUDE CODE HERE:**

```
Complete NB4 Part 1: GitHub Actions CI/CD Foundation.

Create factory/templates/github_actions/ with 6 workflow files:

1. react_native.yml
   - Node.js 18 setup
   - npm install
   - Android: ./gradlew assembleRelease → produces .apk artifact
   - iOS: xcodebuild archive → only on macos-latest runner
   - Upload artifact with 30-day retention

2. flutter_flow.yml
   - Flutter 3.x setup
   - flutter pub get
   - flutter build apk --release (Android)
   - flutter build ipa (iOS, macos-latest runner only)
   - Upload artifact

3. unity.yml
   - Unity 2022.3 LTS (via game-ci/unity-builder action)
   - Build Android and iOS targets
   - Upload artifact

4. python_backend.yml
   - Python 3.11 setup
   - pip install -r requirements.txt
   - docker build -t app:$COMMIT_SHA .
   - docker push to Artifact Registry
   - gcloud run deploy (auto-deploy on main branch)

5. swift_ios.yml
   - macos-latest runner
   - xcodebuild -scheme App -configuration Release
   - xcrun altool --upload-app (Transporter)

6. kotlin_android.yml
   - ./gradlew bundleRelease → .aab artifact
   - Sign with keystore (KEYSTORE_B64, KEYSTORE_PASS secrets)
   - Upload artifact

Also update factory/integrations/github.py:
- trigger_workflow(repo, workflow_file, ref, inputs) async
  → Uses GitHub REST API POST /repos/{owner}/{repo}/actions/workflows/{workflow_id}/dispatches
- wait_for_workflow_run(repo, run_id, timeout=3600) async
  → Polls GET /repos/{owner}/{repo}/actions/runs/{run_id} every 30s
  → Returns success/failure when complete
- download_artifact(repo, artifact_id, dest_path) async
  → GET /repos/{owner}/{repo}/actions/artifacts/{artifact_id}/zip

Run tests:
pip install PyGithub>=2.0.0
python -m pytest tests/test_github_actions.py -v
```

```bash
git add factory/templates/ factory/integrations/github.py tests/test_github_actions.py
git commit -m "NB4-01: GitHub Actions CI/CD — 6 workflow templates, workflow dispatch, artifact download (§4.5.1)"
git push origin main
```

---

## STEP 31.2 — Part 2: Pipeline Self-CI/CD

**USE CLAUDE CODE HERE:**

```
Complete NB4 Part 2: Pipeline Self-CI/CD.

Create .github/workflows/pipeline_ci.yml:
- Triggers on push to main and on PRs
- Steps:
  1. python -m pytest tests/ -v --tb=short (must pass)
  2. docker build -t ai-factory-pipeline:$COMMIT_SHA .
  3. Push to Artifact Registry (on main only)
  4. gcloud run deploy (on main only, via workload identity)
- Notification: if build fails, send Telegram message to operator
  using TELEGRAM_BOT_TOKEN and TELEGRAM_OPERATOR_ID secrets

This means every git push to main automatically deploys to Cloud Run.
No manual docker build + push + deploy required after initial setup.

Also update cloudbuild.yaml to use the same Artifact Registry path.

Test by pushing a small change:
echo "# CI/CD test" >> README.md
git add README.md
git commit -m "test: trigger CI/CD"
git push origin main
```

```bash
git add .github/workflows/pipeline_ci.yml cloudbuild.yaml
git commit -m "NB4-02: Pipeline self-CI/CD — auto-test + auto-deploy on push to main (§7.8.2)"
git push origin main
```

---

## STEP 31.3 — Parts 3–4: Real S4 Build + First Binary

**USE CLAUDE CODE HERE:**

```
Complete NB4 Parts 3 and 4.

PART 3 — Update factory/pipeline/s4_build.py:
Replace _build_gui_stub() with real execution:

async def _build_real(state: PipelineState) → dict:
    stack = state.selected_stack
    repo_name = state.s3_output["repo_name"]
    
    # Dispatch the correct GitHub Actions workflow
    workflow_map = {
        TechStack.REACT_NATIVE: "react_native.yml",
        TechStack.FLUTTER_FLOW: "flutter_flow.yml",
        TechStack.UNITY: "unity.yml",
        TechStack.PYTHON_BACKEND: "python_backend.yml",
        TechStack.SWIFT: "swift_ios.yml",
        TechStack.KOTLIN: "kotlin_android.yml",
    }
    workflow = workflow_map[stack]
    
    # Trigger build
    run_id = await github.trigger_workflow(repo_name, workflow, ref="main")
    
    # Wait for completion (up to 1 hour)
    result = await github.wait_for_workflow_run(repo_name, run_id, timeout=3600)
    
    if result["status"] != "success":
        raise BuildError(f"Build failed: {result['conclusion']}")
    
    # Download artifact
    artifact_path = await github.download_artifact(
        repo_name, 
        result["artifact_id"],
        dest_path=f"/tmp/{state.project_id}/build/"
    )
    
    state.s4_output = {
        "artifact_path": artifact_path,
        "artifact_size_mb": os.path.getsize(artifact_path) / 1_048_576,
        "workflow_run_id": run_id,
        "build_duration_seconds": result["duration"],
    }
    return state

PART 4 — Prove the first real binary:
Run an end-to-end Python backend build using the real GitHub Actions:
1. Create a simple FastAPI hello-world app specification
2. Run it through the pipeline to S4
3. Verify the Docker image was built and pushed
4. Verify it's running on Cloud Run at a real URL
5. curl the URL and get a 200 response
Record the Cloud Run URL in state.s4_output["deployed_url"]
```

```bash
git add factory/pipeline/s4_build.py
git commit -m "NB4-03/04: Real S4 build via GitHub Actions, first binary delivered (§4.5, §4.5.1)"
git push origin main
```

---

# SECTION 32: NB4 PHASE B — MACINCLOUD + GUI AUTOMATION (PARTS 5–8)
📖 **Read first:** NB4 Parts 5–8 + Spec §7.8

**Why this phase exists:** iOS builds require a physical Mac or
a Mac-based CI environment. MacinCloud provides pay-per-hour Mac
instances accessible via SSH. At $1/hr billed in 1-hour minimums,
a typical iOS build costs $1.

## STEP 32.1 — Part 5: MacinCloud SSH Integration

**Pre-requisite:** Create a MacinCloud account at macincloud.com.
Purchase a Pay-As-You-Go (PAYG) instance (macOS Ventura recommended).
Note the SSH hostname, username, and password from your dashboard.

**Add to .env:**
```bash
echo "MACINCLOUD_HOSTNAME=server-XXX.macincloud.com" >> .env
echo "MACINCLOUD_USERNAME=mcuser" >> .env
echo "MACINCLOUD_PASSWORD=YOUR_PASSWORD" >> .env
```

**Store in GCP Secret Manager:**
```bash
source <(grep -v '^#' .env | grep -v '^$' | sed 's/^/export /')
for secret in MACINCLOUD_HOSTNAME MACINCLOUD_USERNAME MACINCLOUD_PASSWORD; do
  echo -n "${!secret}" | gcloud secrets create "$secret" \
    --data-file=- --replication-policy="automatic" 2>/dev/null || \
  echo -n "${!secret}" | gcloud secrets versions add "$secret" --data-file=-
done
```

**USE CLAUDE CODE HERE:**

```
Complete NB4 Part 5: MacinCloud SSH session manager.

Replace factory/infra/macincloud.py stub with real implementation:

MacinCloudClient class:
  HOURLY_RATE = 1.0          # $1/hr per spec §1.4
  MAX_SESSION_HOURS = 8      # Kill switch at 8 hours = $8 max
  MAX_SESSION_COST = 8.0
  HEARTBEAT_INTERVAL = 60    # Ping every 60 seconds
  HEARTBEAT_TIMEOUT = 300    # 5 minutes = dead session

  create_session(session_id) async → MacinCloudSession
    - paramiko.SSHClient with set_missing_host_key_policy
    - client.connect(hostname, username, password, timeout=30)
    - client.get_transport().set_keepalive(60)
    - Start heartbeat monitor as asyncio background task
    - Return session with connected_at timestamp

  execute_command(session_id, command, timeout=600) async → str
    - stdin, stdout, stderr = ssh_client.exec_command(command)
    - Wait for exit status
    - Return stdout string
    - Raise on non-zero exit

  terminate_session(session_id) async
    - client.close()
    - Cancel heartbeat task
    - Log total duration and cost

  get_session_cost(session_id) → float
    - hours = ceil(duration_seconds / 3600)
    - return hours * HOURLY_RATE

  _heartbeat_loop(session_id) async (private background task)
    - Every 60s: execute_command("echo heartbeat")
    - If no response for 5 min: terminate_session + notify operator
    - If hours >= MAX_SESSION_HOURS: terminate_session + notify operator

pip install paramiko==3.4.0
Add to requirements.txt.
Run: python -m pytest tests/test_macincloud.py -v
All 7 tests should pass.
```

```bash
git add factory/infra/macincloud.py requirements.txt tests/test_macincloud.py
git commit -m "NB4-05: MacinCloud SSH — heartbeat monitoring, $8 kill switch, session lifecycle (§7.8)"
git push origin main
```

---

## STEP 32.2 — Parts 6–8: GUI Automation Stack

**What this builds:** A 5-layer automation system that can see and
control the MacinCloud Mac's screen. Required for FlutterFlow (GUI
app builder, no CLI), Unity builds, and any tool that has no command
line interface.

**USE CLAUDE CODE HERE:**

```
Complete NB4 Parts 6, 7, and 8: Full GUI automation stack.

The 5 layers per spec §4.5.2:

Layer 1 — Screen Capture (Part 6):
  factory/integrations/omniparser.py
  - OmniParserClient.capture_screen(session_id) async
    → SSH into MacinCloud, run screencapture command
    → Download PNG to local /tmp
    → Returns image bytes

Layer 2 — Element Detection (Part 6):
  OmniParserClient.detect_elements(image_bytes) async
  - POST image to OmniParser V2 API endpoint
  - Returns list of UI elements with bounding boxes and labels
  - [{label: "Build Button", bbox: [x1,y1,x2,y2], confidence: 0.95}]
  - OmniParser V2 API: https://api.omniparser.io/v2/parse
  - API key from OMNIPARSER_API_KEY secret

Layer 3 — Action Planning (Part 7):
  factory/integrations/uitars_client.py
  - UITARSClient.plan_action(screenshot, elements, goal) async
  - POST to UI-TARS API with screenshot + detected elements + goal text
  - Returns action: {type: "click"|"type"|"scroll", target_element, value}
  - UI-TARS API: https://api.ui-tars.com/v1/plan

Layer 4 — Action Execution (Part 8):
  factory/infra/action_executor.py
  - ActionExecutor.execute(session_id, action) async
  - click: SSH cliclick -c x,y (cliclick installed on MacinCloud)
  - type: SSH cliclick t:text
  - scroll: SSH cliclick -w x,y

Layer 5 — Verification (Part 8):
  ActionExecutor.verify(session_id, expected_state) async
  - Capture new screenshot after action
  - Detect elements again
  - Return True if expected_state element is visible

Main orchestrator: factory/infra/gui_automation.py
  GUIAutomationOrchestrator.execute_goal(session_id, goal) async
  → Loop: capture → detect → plan → execute → verify → repeat
  → Maximum 20 iterations before raising GUIAutomationError
  → Used by s4_build.py for FlutterFlow and Unity builds

Also add OMNIPARSER_API_KEY and UITARS_API_KEY to REQUIRED_SECRETS.

pip install requests pillow
Run: python -m pytest tests/test_gui_automation.py -v
```

```bash
git add factory/integrations/omniparser.py factory/integrations/uitars_client.py \
        factory/infra/action_executor.py factory/infra/gui_automation.py \
        tests/test_gui_automation.py
git commit -m "NB4-06/07/08: 5-layer GUI automation — OmniParser V2 + UI-TARS + ActionExecutor (§4.5.2)"
git push origin main
```

---

# SECTION 33: NB4 PHASE C — APP STORE DEPLOYMENT (PARTS 9–13)
📖 **Read first:** NB4 Parts 9–13 + Spec §4.7.1, §4.7.2, FIX-21, FIX-22

## STEP 33.1 — Pre-requisites: Apple Developer + Google Play Accounts

**Apple Developer ($99/year):**
1. Go to `developer.apple.com/programs/enroll/`
2. Sign in with your Apple ID
3. Choose "Enroll as Individual" (or "Organization" for a company)
4. Pay $99/year
5. Wait for approval (1–3 days for individuals)
6. After approval: go to `appstoreconnect.apple.com`
7. Create an API key: Users and Access → Integrations → App Store Connect API
8. Download the `.p8` key file, note the Key ID and Issuer ID

**Save to .env:**
```bash
echo "APP_STORE_CONNECT_KEY_ID=YOUR_KEY_ID" >> .env
echo "APP_STORE_CONNECT_ISSUER_ID=YOUR_ISSUER_ID" >> .env
# Key file: store as base64 string
echo "APP_STORE_CONNECT_KEY_B64=$(base64 < /path/to/key.p8)" >> .env
```

**Google Play Console ($25 one-time):**
1. Go to `play.google.com/console/`
2. Sign in with Google account
3. Pay $25 registration fee
4. Create your developer profile
5. Go to Setup → API access → Link to Google Cloud project
6. Create a service account with "Release Manager" role
7. Download the service account JSON key

```bash
echo "GOOGLE_PLAY_SERVICE_ACCOUNT_B64=$(base64 < /path/to/service_account.json)" >> .env
```

**Store all new secrets in GCP Secret Manager:**
```bash
source <(grep -v '^#' .env | grep -v '^$' | sed 's/^/export /')
for secret in APP_STORE_CONNECT_KEY_ID APP_STORE_CONNECT_ISSUER_ID \
              APP_STORE_CONNECT_KEY_B64 GOOGLE_PLAY_SERVICE_ACCOUNT_B64; do
  echo -n "${!secret}" | gcloud secrets create "$secret" \
    --data-file=- --replication-policy="automatic" 2>/dev/null || \
  echo -n "${!secret}" | gcloud secrets versions add "$secret" --data-file=-
done
```

---

## STEP 33.2 — Parts 9–10: Apple Developer + Google Play Clients

**USE CLAUDE CODE HERE:**

```
Complete NB4 Parts 9 and 10.

PART 9 — Apple Developer client (factory/integrations/apple_developer.py):
Per spec §4.7.2 + FIX-21 iOS 5-step submission protocol:

Step 1 (Certificate): Download distribution certificate from App Store
  Connect API using JWT auth (Key ID + Issuer ID + .p8 private key)
  
Step 2 (Provisioning): Download provisioning profile for the bundle ID

Step 3 (Sign): Call codesign via MacinCloud SSH:
  codesign --sign "iPhone Distribution: NAME" --entitlements ...

Step 4 (Package): xcrun -sdk iphoneos PackageApplication
  produces signed .ipa file

Step 5 (Upload): Transporter CLI on MacinCloud:
  xcrun altool --upload-app --file app.ipa
  --apiKey $KEY_ID --apiIssuer $ISSUER_ID

AppStoreConnectClient:
  get_bundle_ids() async → list of bundle IDs
  create_app(name, bundle_id, primary_locale) async → app_id
  submit_for_review(app_id, build_id) async

PART 10 — Google Play client (factory/integrations/google_play.py):
Per spec §4.7.1 + FIX-22 Android submission protocol:

GooglePlayClient:
  authenticate() → google.oauth2.service_account.Credentials
    from GOOGLE_PLAY_SERVICE_ACCOUNT_B64 (decode + load JSON)
  
  create_edit(package_name) → edit_id
    POST /androidpublisher/v3/applications/{pkg}/edits
  
  upload_aab(package_name, edit_id, aab_path) → version_code
    POST /androidpublisher/v3/applications/{pkg}/edits/{edit}/bundles
  
  assign_to_track(package_name, edit_id, version_code, track="internal")
    PUT /androidpublisher/v3/applications/{pkg}/edits/{edit}/tracks/internal
  
  commit_edit(package_name, edit_id)
    POST /androidpublisher/v3/applications/{pkg}/edits/{edit}:commit

pip install google-auth google-auth-httplib2 google-api-python-client
pip install PyJWT cryptography
Run: python -m pytest tests/test_apple_developer.py tests/test_google_play.py -v
```

```bash
git add factory/integrations/apple_developer.py factory/integrations/google_play.py \
        tests/test_apple_developer.py tests/test_google_play.py
git commit -m "NB4-09/10: Apple Developer API (5-step FIX-21), Google Play Console API (FIX-22) (§4.7.1, §4.7.2)"
git push origin main
```

---

## STEP 33.3 — Parts 11–13: Firebase + Real Submissions

**USE CLAUDE CODE HERE:**

```
Complete NB4 Parts 11–13.

PART 11 — Firebase full-stack (factory/integrations/firebase_client.py):
Per spec §4.7.3:

FirebaseClient.provision_full_stack(app_name, platform) async:
  1. firebase projects:create --display-name app_name
  2. firebase apps:create ANDROID/IOS --project project_id
  3. Enable Firebase Auth (Email+Password provider)
  4. Initialize Cloud Firestore (nam5 region)
  5. Enable Cloud Storage
  6. Deploy to Firebase Hosting (if Web platform)
  Returns: {project_id, app_id, web_config_json, hosting_url}

PART 12 — Update s6_deploy.py with real iOS submission:
_deploy_ios(state) async:
  1. Start MacinCloud session
  2. Transfer signed IPA to MacinCloud via SFTP
  3. Run Transporter CLI (FIX-21 Step 5)
  4. Poll App Store Connect API for build processing status
  5. Submit for TestFlight external testing
  6. Return state.s6_output["testflight_url"]
  
  Airlock fallback: if submission fails, send IPA file directly
  via airlock_deliver() so operator always gets the binary

PART 13 — Update s6_deploy.py with real Android submission:
_deploy_android(state) async (FIX-22):
  1. Generate signing keystore (or reuse existing for updates)
  2. Sign .aab: jarsigner -verbose -sigalg SHA256withRSA ...
  3. create_edit() → upload_aab() → assign_to_track("internal")
  4. commit_edit()
  5. Return state.s6_output["play_store_url"]
  
  Store keystore in GCP Secret Manager per project_id
  (never regenerate for the same bundle ID — breaks signatures)

Run: python -m pytest tests/test_firebase.py tests/integration/ -v
```

```bash
git add factory/integrations/firebase_client.py factory/pipeline/s6_deploy.py \
        tests/test_firebase.py
git commit -m "NB4-11/12/13: Firebase full-stack, iOS TestFlight (FIX-21), Android Play Store (FIX-22) (§4.7)"
git push origin main
```

---

# SECTION 34: NB4 PHASES D–E — BINARY PROOFS + LOCAL MODE
📖 **Read first:** NB4 Parts 14–19 + Spec §7.2, ADR-032

## STEP 34.1 — Phase D: End-to-End Binary Delivery Proofs

These three parts (14–16) prove that each platform's binary actually
reaches the operator. They are integration tests, not new code.

**USE CLAUDE CODE HERE:**

```
Create three end-to-end scenario tests for NB4 Parts 14–16.

tests/scenarios/test_apk_delivery.py (Part 14):
  Build "Hello Riyadh" React Native Android app end-to-end
  Verify: .apk or .aab file exists and > 1MB
  Verify: file delivered to operator via Telegram airlock
  Verify: file accessible via GitHub release URL
  Mark: @pytest.mark.e2e (skip in normal test runs)

tests/scenarios/test_ipa_delivery.py (Part 15):
  Build "Hello Riyadh" iOS Swift app end-to-end (uses MacinCloud)
  Verify: TestFlight build processing started
  Verify: operator received Telegram notification with TestFlight link
  Verify: build visible in App Store Connect API
  Mark: @pytest.mark.e2e (skip in normal test runs)

tests/scenarios/test_web_delivery.py (Part 16):
  Build "Hello Riyadh" Next.js web app end-to-end
  Verify: Firebase Hosting URL returns 200
  Verify: URL contains real content (not empty)
  Verify: Firebase console shows active deployment
  Mark: @pytest.mark.e2e (skip in normal test runs)

To run the proofs manually when you're ready:
  python -m pytest tests/scenarios/ -v -m e2e --no-header
```

```bash
git add tests/scenarios/
git commit -m "NB4-14/15/16: End-to-end binary delivery proofs — APK, IPA, Web (Appendix D No Magic Handoffs #7, #8)"
git push origin main
```

---

## STEP 34.2 — Phase E: Cloudflare Tunnel + Local + Hybrid Modes

**Install Cloudflare Tunnel on your Mac:**
```bash
brew install cloudflared
cloudflared login   # Opens browser to authenticate with Cloudflare
cloudflared tunnel create ai-factory-pipeline
cloudflared tunnel route dns ai-factory-pipeline pipeline.yourdomain.com
```

**Update .env with tunnel info:**
```bash
echo "CLOUDFLARE_TUNNEL_ID=$(cloudflared tunnel list | grep ai-factory-pipeline | awk '{print $1}')" >> .env
echo "CLOUDFLARE_TUNNEL_URL=https://pipeline.yourdomain.com" >> .env
```

**USE CLAUDE CODE HERE:**

```
Complete NB4 Parts 17–19: All three execution modes.

PART 17 — factory/infra/cloudflare_tunnel.py:
CloudflareTunnel class:
  start() async → starts cloudflared process locally
    subprocess.Popen(['cloudflared', 'tunnel', '--config', tunnel.yml, 'run'])
  stop() async → terminates the process
  is_running() → checks process status
  get_public_url() → returns CLOUDFLARE_TUNNEL_URL from env
  
  Also: register_with_cloud_run()
    Updates Cloud Run WEBHOOK_BASE_URL env var to tunnel URL
    So Telegram continues working in LOCAL mode

PART 18 — Update factory/core/execution.py LOCAL mode:
ExecutionModeManager.switch_to_local() async:
  1. Start Cloudflare tunnel
  2. Register tunnel URL with Cloud Run (or run pipeline locally)
  3. For builds: run GitHub Actions on local Mac via act (github.com/nektos/act)
     brew install act
     act --secret-file .env (runs workflow locally)
  4. iOS builds in LOCAL mode: still use MacinCloud (Mac-on-Mac)
  5. Save ~80% of build costs vs CLOUD mode

PART 19 — HYBRID mode (ADR-032):
factory/core/hybrid_orchestrator.py:
  AI calls (Scout/Strategist/Engineer): → Cloud Run (standard)
  Build tasks: → LOCAL via act or MacinCloud SSH directly
  Deploy tasks: → Cloud APIs (App Store Connect, Google Play)
  Benefit: cloud AI quality + local build cost savings
  Typical HYBRID cost: $0.20/build vs $1.20 CLOUD

Run: python -m pytest tests/integration/test_execution_modes.py -v
```

```bash
git add factory/infra/cloudflare_tunnel.py factory/core/execution.py \
        factory/core/hybrid_orchestrator.py tests/integration/test_execution_modes.py
git commit -m "NB4-17/18/19: Cloudflare Tunnel, LOCAL mode (act), HYBRID mode (§7.2, ADR-032)"
git push origin main
```

---

# SECTION 35: NB4 PHASE F — MODIFY MODE (PARTS 20–23)
📖 **Read first:** NB4 Parts 20–23 + Spec §6.1–§6.7, §3.4

**What Modify Mode is:** The pipeline can now take an *existing* deployed
app and update it with new features, rather than building from scratch.
You provide the GitHub URL of the existing app and describe the changes.

## STEP 35.1 — Parts 20–21: Foundation + Codebase Ingestion

**USE CLAUDE CODE HERE:**

```
Complete NB4 Parts 20 and 21.

PART 20 — Add PipelineMode to state.py:
class PipelineMode(str, Enum):
    CREATE = "CREATE"
    MODIFY = "MODIFY"

Add to PipelineState:
    pipeline_mode: PipelineMode = PipelineMode.CREATE
    existing_repo_url: Optional[str] = None
    existing_repo_local_path: Optional[str] = None
    existing_codebase_summary: Optional[str] = None
    modification_request: Optional[str] = None
    files_to_modify: List[str] = Field(default_factory=list)
    new_files_to_create: List[str] = Field(default_factory=list)

Update Telegram /new command handler to parse MODIFY requests:
If message contains a GitHub URL, set pipeline_mode = MODIFY
and existing_repo_url = the URL.
Otherwise set pipeline_mode = CREATE.

PART 21 — factory/pipeline/codebase_ingestor.py:
CodebaseIngestor class:
  clone_repository(github_url, dest_path) async
    git clone --depth=1 github_url dest_path (shallow clone for speed)
  
  analyze_file(file_path) → FileAnalysis
    Detect language from extension
    Count lines of code
    Extract imports (import X, from X import Y)
    Extract exports (module.exports, export default, etc.)
    Identify components (React components, SwiftUI views)
  
  analyze_codebase(repo_path) → CodebaseSummary
    Walk all files, skip node_modules and build dirs
    Return: {total_files, total_lines, tech_stack, key_files, dependencies}
  
  build_context_string(summary) → str
    Format summary for AI consumption (under 8000 tokens)
    Include: structure tree, key files, tech stack, dependencies
    This becomes the context for MODIFY mode AI prompts

Update s0_intake.py to route MODIFY requests:
  if state.pipeline_mode == PipelineMode.MODIFY:
    clone repo → analyze → set state.existing_codebase_summary
    parse modification_request from operator message
  else:
    existing CREATE mode flow

Run: python -m pytest tests/test_codebase_ingestor.py -v
```

```bash
git add factory/core/state.py factory/pipeline/codebase_ingestor.py \
        factory/pipeline/s0_intake.py tests/test_codebase_ingestor.py
git commit -m "NB4-20/21: MODIFY mode foundation — PipelineMode enum, codebase ingestion, analysis (§6.1, §6.2)"
git push origin main
```

---

## STEP 35.2 — Parts 22–23: Diff Generation + Version Management

**USE CLAUDE CODE HERE:**

```
Complete NB4 Parts 22 and 23.

PART 22 — Diff-based code generation:
factory/pipeline/diff_generator.py:
  generate_diff(original_file, modified_file) → str
    Uses Python difflib.unified_diff() to create unified diff
    Format: standard --- +++ @@ patch format (Git-compatible)

  apply_diff(original_file, diff_patch) → str
    Applies patch to file content
    Returns modified content or raises ConflictError

  detect_conflict(patch1, patch2) → bool
    Checks if two patches modify the same lines

  ConflictResolver class with 4 strategies:
    OURS: keep our version
    THEIRS: keep AI version
    MERGE: attempt auto-merge of non-overlapping changes
    MANUAL: mark conflict markers for operator review

Update s3_codegen.py MODIFY mode path:
  Instead of generating full files:
  1. call_ai(ENGINEER, modify_prompt) where prompt includes
     existing_codebase_summary + modification_request
  2. AI returns JSON: {"file_path": "...", "diff": "..."}[]
  3. For each diff: apply_diff() → write modified file
  4. Run existing tests against modified codebase
  5. If tests fail: try ConflictResolver.THEIRS strategy

PART 23 — Semantic version management:
factory/core/version_manager.py:
  VersionManager class:
  
  get_current_version(repo_path) → semver (reads from package.json/pubspec.yaml/Info.plist)
  
  bump_version(current, change_type) → str
    change_type: "patch" | "minor" | "major"
    "patch": 1.2.3 → 1.2.4 (bug fixes)
    "minor": 1.2.3 → 1.3.0 (new features, backward compatible)
    "major": 1.2.3 → 2.0.0 (breaking changes)
  
  write_version(repo_path, new_version)
    Updates package.json version field
    Updates Android versionName and increments versionCode
    Updates iOS CFBundleShortVersionString
  
  generate_changelog_entry(modification_request, new_version) → str
    Calls call_ai(QUICKFIX, changelog_prompt) to generate
    human-readable changelog for the app store

  The MODIFY pipeline always bumps the patch version automatically.
  Operator can override to minor/major via Telegram decision menu.

Run: python -m pytest tests/test_diff_generator.py tests/test_version_manager.py -v
```

```bash
git add factory/pipeline/diff_generator.py factory/core/version_manager.py \
        factory/pipeline/s3_codegen.py tests/test_diff_generator.py \
        tests/test_version_manager.py
git commit -m "NB4-22/23: Diff-based codegen, 4-strategy conflict resolution, semantic versioning (§6.3–§6.7)"
git push origin main
```

---

# SECTION 36: NB4 PHASE G — REVENUE OPERATIONS (PARTS 24–26)
📖 **Read first:** NB4 Parts 24–26 + Spec §8.1–§8.5

## STEP 36.1 — Part 24: /evaluate Command

The `/evaluate` command lets you pre-screen ideas before spending money
on a full build. It scores an idea 0–100 and returns a recommendation.

**USE CLAUDE CODE HERE:**

```
Complete NB4 Part 24: /evaluate command.

factory/evaluation/idea_evaluator.py:
EvaluationScore dataclass:
  technical_feasibility: int   # 0-100: can pipeline build this?
  market_potential:      int   # 0-100: is there a market?
  ksa_compliance:        int   # 0-100: KSA legal risk (PDPL, etc.)
  build_complexity:      int   # 0-100: how complex is the build?
  estimated_cost_usd:    float # estimated AI cost for this build
  estimated_duration_min: int  # estimated build time in minutes
  recommended_stack:     str   # best TechStack for this idea

  @property
  def composite_score(self) → int:
    return weighted average (technical 40%, market 30%, compliance 30%)
  
  @property
  def grade(self) → str:
    90-100: "🏆 EXCELLENT — Build immediately"
    75-89:  "✅ GOOD — Build with minor refinements"
    60-74:  "⚠️  FAIR — Review challenges before building"
    0-59:   "❌ RISKY — Resolve issues before building"

evaluate_idea(state, idea_text) async → EvaluationResult:
  1. call_ai(SCOUT, ksa_market_research_prompt + idea_text)
  2. call_ai(STRATEGIST, technical_feasibility_prompt + idea_text + scout_result)
  3. Parse structured JSON from Strategist response
  4. Return EvaluationResult with score + 3 strengths + 3 challenges + recommendations

Update Telegram bot to handle /evaluate:
  cmd_evaluate(update, context):
    idea_text = " ".join(context.args) or ask for it
    result = await evaluate_idea(state, idea_text)
    Format and send rich Telegram message with score, grade, 
    strengths, challenges, estimated cost

Typical /evaluate cost: ~$0.05 (Scout + Strategist, short prompts)
Much cheaper than a full build that turns out to be a bad idea.

Run: python -m pytest tests/test_idea_evaluator.py -v
```

```bash
git add factory/evaluation/ factory/telegram/bot.py tests/test_idea_evaluator.py
git commit -m "NB4-24: /evaluate command — idea scoring 0-100, feasibility + market + compliance (§8.1, §8.2)"
git push origin main
```

---

## STEP 36.2 — Parts 25–26: Revenue Tracking + Customer Management

**USE CLAUDE CODE HERE:**

```
Complete NB4 Parts 25 and 26.

PART 25 — Revenue tracking commands:
factory/revenue/tracker.py:
  RevenueTracker class backed by Supabase revenue_records table:
  
  record_revenue(project_id, amount_usd, source, notes) async
  get_monthly_revenue(year_month) async → float
  get_project_revenue(project_id) async → float
  generate_revenue_report(period) async → str (Markdown)

Add 3 new Supabase tables (run migration):
  revenue_records: id, project_id, amount_usd, source, recorded_at, notes
  clients: id, name, telegram_id, email, company, active, created_at  
  invoices: id, client_id, amount_usd, currency, status, due_date, items_json

New Telegram commands in bot.py:
  /revenue → show this month's revenue summary
    "💰 March 2026 Revenue
     App Store: $124.50
     Google Play: $87.30
     Direct clients: $200.00
     ─────────────────
     Total: $411.80
     Monthly AI cost: $34.20
     Net profit: $377.60 (91.7%)"

  /invoice [client_name] [amount] [description]
    → Creates invoice record in Supabase
    → Sends invoice summary to operator

  /clients
    → Lists active clients from clients table
    → Shows per-client revenue total

PART 26 — Pricing calculator + client intake:
factory/revenue/pricing.py:
  PricingCalculator:
  estimate_project_cost(idea_description, platform, complexity) → dict
    Returns: {
      ai_cost_usd: float,       # Estimated AI spend
      macincloud_cost_usd: float, # If iOS, $1/build
      total_cost_usd: float,
      suggested_price_usd: float, # 3x cost = 67% margin
      profit_margin_pct: float
    }
  
  calculate_saas_pricing(monthly_users, tier) → dict
    Returns recommended subscription pricing

Run: python -m pytest tests/test_revenue.py -v
```

```bash
git add factory/revenue/ factory/telegram/bot.py tests/test_revenue.py
git commit -m "NB4-25/26: /revenue /invoice /clients commands, pricing calculator, client management (§8.3–§8.5)"
git push origin main
```

---

# SECTION 37: NB4 PHASE H — OPERATIONAL COMPLETENESS (PARTS 27–28)
📖 **Read first:** NB4 Parts 27–28

## STEP 37.1 — Parts 27–28: Operator Runbooks

**USE CLAUDE CODE HERE:**

```
Create 4 comprehensive operator runbooks in docs/runbooks/.
These are plain-English guides for zero-IT-background operators.

docs/runbooks/01-setup-runbook.md (~700 lines):
Covers: Prerequisites → Account creation → Pipeline installation →
Configuration → First pipeline run → Verification checklist.
All steps in second-person ("Go to...", "Type...", "You should see...").

docs/runbooks/02-daily-operations-runbook.md (~800 lines):
Covers: Morning startup (2 min routine) → Evaluating ideas →
Building apps → Monitoring builds → End-of-day check.
Includes: ALL Telegram commands with examples + expected responses.
Mode selection decision tree (CLOUD vs LOCAL vs HYBRID).

docs/runbooks/03-troubleshooting-runbook.md (~1000 lines):
Covers: Every failure mode from RB2, diagnosed in plain English.
Format per error: "What you'll see" → "What it means" → "What to do."
Covers: Pipeline won't start, builds failing, Telegram not responding,
budget exhausted, Cloud Run crashed, database errors, App Store rejection.

docs/runbooks/04-budget-maintenance-runbook.md (~900 lines):
Covers: Reading the /budget command, weekly cost review,
GCP billing alerts setup, monthly reconciliation, 
API key rotation schedule (90-day / 180-day per Appendix B),
certificate renewal calendar (Apple Developer annual),
storage cleanup (temp_artifacts older than 72 hours),
snapshot pruning (keep last 50 per project).

After creating all 4, run:
wc -l docs/runbooks/*.md
# Each file should be 700+ lines
```

```bash
git add docs/runbooks/
git commit -m "NB4-27/28: 4 operator runbooks — setup, daily ops, troubleshooting, budget maintenance (§7.3, §7.4)"
git push origin main
```

---

# SECTION 38: ★ NB4 PHASE I — FINAL CERTIFICATION (PARTS 29–30)

## STEP 38.1 — Part 29: Extended Production Readiness Scorecard

**USE CLAUDE CODE HERE:**

```
Create the extended Production Readiness Scorecard for NB4 Part 29.

docs/scorecard-v5.6.md: comprehensive validation document.

It must verify these 84 criteria (trace each to a spec section):

PIPELINE STAGES (S0–S8): 9 criteria — each stage has real AI call,
  real output, real Telegram notification, test coverage

AI ROLES (4): Scout/Strategist/Engineer/QuickFix all route to
  real APIs with real cost tracking

EXECUTION MODES (3): CLOUD, LOCAL, HYBRID — each mode builds 
  an app end-to-end with documented cost

TECH STACKS (6): React Native, FlutterFlow, Unity, Python Backend,
  Swift, Kotlin — each stack has a workflow template and builds

APP STORE DELIVERY (2): iOS TestFlight + Android Google Play —
  each has a real submission completed (or e2e test)

STATE PERSISTENCE (3): Supabase write, GitHub write, Neo4j write —
  triple-write verified with checksum

TELEGRAM (15): All 15 commands have real handlers with real responses

BUDGET GOVERNOR (4 tiers): GREEN/AMBER/RED/BLACK — circuit breaker
  tested at each tier

LEGAL COMPLIANCE (6): PDPL, CST, SAMA, NDMO, NCA, SDAIA — each
  checked in S1 Legal with real Strategist call

MODIFY MODE (4): PipelineMode, codebase ingestion, diff generation,
  version bump — each has a test proving it works

OPERATOR SAFETY (22): All 22 prohibited commands blocked by
  UserSpace Enforcer

RUNBOOKS (4): All 4 runbooks exist and are 700+ lines each

INTELLIGENCE PACK (7): All 7 FIX-27 docs generated for a real project

Also create: docs/definition-of-done-verification.md
  37 Definition of Done items from the spec — mark each ✅ with evidence

Run a final check:
python -m pytest tests/ -v 2>&1 | tail -5
# Must show: 591+ passed, 0 failed
```

```bash
git add docs/scorecard-v5.6.md docs/definition-of-done-verification.md \
        tests/integration/ tests/performance/
git commit -m "NB4-29: 84-criteria scorecard, 7 integration tests, performance benchmarks (§8.1, §8.11)"
git push origin main
```

---

## STEP 38.2 — ★ Part 30: v5.6.0-complete — FINAL CERTIFICATION

```bash
cd ~/Projects/ai-factory-pipeline
source .venv/bin/activate

# ── Final test run ──
python -m pytest tests/ -v 2>&1 | tail -5
# MUST show: 591+ passed, 0 failed

# ── Scorecard completion check ──
grep -c "✅" docs/scorecard-v5.6.md
# MUST show 84 (or more)

# ── All runbooks present and substantial ──
for f in docs/runbooks/0{1,2,3,4}-*.md; do
  lines=$(wc -l < "$f")
  echo "$f: $lines lines"
  [ "$lines" -lt 700 ] && echo "⚠️  WARNING: file too short"
done

# ── Binary delivery proofs ──
echo "Checking binary delivery evidence..."
ls -la /tmp/*/build/*.apk 2>/dev/null && echo "✅ APK on disk" || echo "⚠️  APK not found locally"
grep -r "testflight_url" tests/scenarios/ | head -3

# ── MODIFY mode proof ──
python -c "
import os; os.environ['DRY_RUN']='true'
from factory.core.state import PipelineMode
from factory.pipeline.codebase_ingestor import CodebaseIngestor
print('✅ MODIFY mode code present')
"

# ── LOCAL mode proof ──
python -c "
from factory.infra.cloudflare_tunnel import CloudflareTunnel
from factory.core.execution import ExecutionModeManager, ExecutionMode
print('✅ LOCAL + HYBRID mode code present')
"

# ── Final commit and tag ──
git add -A
git commit -m "NB4-30: ★ FINAL CERTIFICATION — 84/84 scorecard, 591+ tests, all proofs complete"
git tag -a v5.6.0-complete -m "AI Factory Pipeline v5.6.0 — Production Complete

All 4 notebooks implemented:
- NB1: 85+ stub files, architecture verified (tag: v5.6.0-stub)
- NB2: 362 tests, all stubs replaced (tag: v5.6.0)
- NB3: System live in production, first real apps built (tag: v5.6.0-production)
- NB4: Full delivery pipeline, Modify Mode, Revenue Ops (tag: v5.6.0-complete)

84/84 Production Readiness Scorecard criteria met.
591+ tests passing.
System certified for production operation."

git push origin main
git push origin v5.6.0-complete
```

**USE NOTION MCP HERE:**
```
"Mark all NB4 items complete in my Implementation Tracker.
Add note: NB4 complete. All 30 parts done. 591 tests passing.
Tagged v5.6.0-complete. Full pipeline operational: CI/CD,
iOS TestFlight, Android Play, Modify Mode, Revenue Ops."
```

**USE MEMORY HERE:**
```
"Remember: ★ NB4 COMPLETE — FULL SYSTEM CERTIFIED.
All 4 notebooks done. 591 tests. Tag v5.6.0-complete.
System can: build 6 stacks, deploy to iOS + Android + Web,
update existing apps (Modify Mode), track revenue.
Cost per iOS app build: ~$1-2. Per Android: ~$0-0.20.
Begin daily operations using RB1 and NB5 Day 1 guide."
```

**USE GOOGLE CALENDAR HERE:**
```
"Create event: ★ AI Factory Pipeline v5.6.0-complete — 
Full system certified. All 4 notebooks done.
Daily operations begin from today."
```

---

# ══════════════════════════════════════
# SECTION 39: DAILY OPERATIONS REFERENCE
# For use every day after NB4 is complete
# ══════════════════════════════════════

---

# SECTION 39: DAILY OPERATIONS REFERENCE

## 39.1 Morning Routine (5 Minutes)

Do this every morning before building any app:

**Step 1 — Health check (30 seconds):**
In Telegram, type:
```
/status
```

✅ Healthy response:
```
🏭 AI Factory Pipeline v5.6.0
Status: ✅ RUNNING
Mode: Autopilot
Services: Supabase ✅ | Neo4j ✅ | GitHub ✅ | Anthropic ✅
Active builds: 0
Budget this month: $XX.XX / $300.00 (X%)
```

❌ If you see any ❌ next to a service, check RB2 for that service.

**Step 2 — Budget check (30 seconds):**
```
/budget
```

Check that you are still in GREEN tier (<70% of $300 = <$210).
If you see AMBER (70–90%) — reduce build frequency this month.
If you see RED (90–100%) — stop non-essential builds immediately.

**Step 3 — Review overnight notifications (1 minute):**
Scroll up in Telegram and look for any failed build messages.
If a build failed: note the project ID and check RB2.

**That's it.** If everything is green, you're ready to build.

---

## 39.2 All Telegram Commands — Complete Reference

### Build Commands

| Command | What it does | When to use |
|---------|-------------|-------------|
| `/evaluate [idea]` | Score idea 0–100, estimate cost | Before every new build |
| `/new [description]` | Start new app build (CREATE mode) | After evaluating |
| `/new [github-url] [changes]` | Update existing app (MODIFY mode) | For app updates |
| `/status` | Health check + active build list | Every morning, anytime |
| `/budget` | Monthly spend breakdown | Daily if heavy usage |
| `/history` | List past completed projects | Finding old project IDs |
| `/info [project-id]` | Details for one project | Checking specific project |

### Build Control Commands

| Command | What it does |
|---------|-------------|
| `/pause` | Pause a running build (resumes from same point) |
| `/resume` | Resume a paused build |
| `/cancel` | Cancel and discard current build |
| `/restore [project-id]` | Restore a project to a previous snapshot |

### Mode Commands

| Command | What it does | Cost implication |
|---------|-------------|-----------------|
| `/autopilot` | Pipeline makes all decisions | Faster, no interruptions |
| `/copilot` | You approve key decisions | Slower, more control |
| `/mode cloud` | All builds on GCP | iOS: $1.20/build |
| `/mode local` | All builds on your Mac | iOS: still MacinCloud, Android/Web: $0 |
| `/mode hybrid` | AI on cloud, builds local | Best value: ~$0.20/build |

### Revenue Commands

| Command | What it does |
|---------|-------------|
| `/revenue` | This month's revenue summary |
| `/invoice [client] [amount] [description]` | Create client invoice |
| `/clients` | List active clients and their totals |

### Admin Commands

| Command | What it does |
|---------|-------------|
| `/admin whitelist [telegram_id]` | Add new operator |
| `/admin logs [project-id]` | View raw logs |
| `/help` | Full command list |

---

## 39.3 Building a New App — Standard Workflow

**Best practice sequence:**

**1. Evaluate first (1 minute, ~$0.05):**
```
/evaluate

I want to build a Quran memorisation app for Saudi kids aged 8–14.
Android and iOS. Free with optional $2.99 in-app unlocks.
Key features: audio playback, progress tracking, parent dashboard.
```

Read the score. If below 60, address the issues before building.

**2. Choose your mode:**
- Android only → use `/mode hybrid` or `/mode local` (saves money)
- iOS included → use `/mode cloud` (MacinCloud needed for signing)
- Quick test → use `/mode local`

**3. Switch to Copilot for first few apps:**
```
/copilot
```
This lets you see each AI decision and learn the system.
Switch to `/autopilot` once you're comfortable.

**4. Send the full specification:**
```
/new

App name: Quran Memorise
Platforms: Android + iOS
Stack: React Native

Description:
A Quran memorisation app for Saudi children aged 8–14.

Core Features (MVP v1.0):
1. Audio playback of individual Ayahs (verses) with Arabic text
2. Repeat mode: loop a verse until memorised
3. Progress tracker: mark verses as memorised
4. Simple parent dashboard showing weekly progress
5. 30 Juz (chapters) with full text and audio

Monetisation:
- Free: Juz 30 only (last chapter, 37 verses — good for beginners)
- Premium: All 30 Juz ($2.99 one-time purchase or $0.99/month)
- No ads

Target users: Saudi Muslim families, children 8–14
Primary language: Arabic (with English option in settings)
Design style: Clean, modern, green and gold colours, large Arabic text
KSA legal: Handles audio only, no user data beyond progress sync
```

**5. Watch the Telegram notifications:**

You will see one message per stage (S0 through S8). In COPILOT mode,
you may see decision menus — tap your choice when they appear.

**Typical timeline:**
- Simple app (React Native, Android only): 25–35 minutes
- Medium app (React Native, Android + iOS): 40–60 minutes
- Complex app (Unity game): 45–90 minutes

**6. Receive your Intelligence Pack:**

At S8, you get 7 files in Telegram:
- `QUICK_START.md` — How to install, configure, launch
- `privacy_policy.html` — Ready for your website
- `terms_of_service.html` — Ready for your website
- `ksa_compliance_report.pdf` — For regulatory reference
- `architecture_diagram.md` — Technical overview
- `app_store_metadata.json` — Copy-paste into App Store Connect
- `developer_handoff.md` — Full technical documentation

---

## 39.4 Updating an Existing App — Modify Mode Workflow

**1. Get the GitHub URL of your existing app:**
```
/history
```
Find the project and note its GitHub URL (e.g.
`github.com/yourusername/quran-memorise`).

**2. Send the update request:**
```
/new github.com/yourusername/quran-memorise

Update request: Add a daily reminder notification feature.

Details:
- Let user set a daily reminder time (default 6 PM)
- Notification says "Time for your Quran practice! 📖"
- Tapping notification opens the app at the last memorised verse
- iOS and Android push notifications
- Settings screen should have a toggle to enable/disable reminders
  and a time picker

Keep all existing features exactly as they are.
Version bump: minor (1.0 → 1.1)
```

**3. The pipeline will:**
1. Clone your existing repo (read-only)
2. Analyse the existing codebase structure
3. Generate diffs (not full rewrites) for the affected files
4. Add new files for the notification feature
5. Run tests on the modified code
6. Bump version: `1.0.0` → `1.1.0`
7. Build and deliver updated binary
8. Generate updated store metadata for the new version

**Cost:** ~$0.20 (HYBRID mode) to ~$1.00 (CLOUD mode with iOS)

---

## 39.5 Execution Mode Decision Guide

Every time before you build, ask these two questions:

**Question 1: Does this build include iOS?**
- Yes → You need MacinCloud for code signing
  - But: Use `/mode hybrid` to save money (only MacinCloud for signing step)
  - Or: Use `/mode cloud` (simplest, fully automated, most expensive)
- No (Android or Web only) → Use `/mode local` or `/mode hybrid`

**Question 2: Is this a quick test/experiment?**
- Yes → Use `/mode local` (no cloud costs, your Mac does everything)
- No (production build) → Use `/mode hybrid` (cloud AI quality + local build)

**Cost reference per build:**

| Mode | Android/Web | iOS | When to use |
|------|------------|-----|-------------|
| `/mode local` | $0 | $1 (MacinCloud) | Testing, Android/Web builds |
| `/mode hybrid` | $0 | $0.20 (AI only) + $1 (Mac) | Most builds |
| `/mode cloud` | $0.20 | $1.20 | When you want fully automated |

---

## 39.6 Weekly Maintenance Checklist (30 Minutes)

Do this every Monday morning:

**Monday morning (15 minutes):**
```
/budget
```
Review the weekly AI spend breakdown. Identify any unexpectedly
expensive builds and note what made them expensive (long prompts?
many retries? complex codegen?).

**USE SUPABASE MCP HERE:**
```
"Show me rows from monthly_costs where the period is the current
month. Sum the ai_spend_usd column."
```

**Verify all services are green:**
```
/status
```
All 6 services should be ✅. If any is ❌, check RB2 immediately.

**Check GitHub Actions for build failures:**
```
"Using Claude in Chrome, go to github.com/YOUR_USERNAME/
ai-factory-pipeline/actions and tell me if any workflows
failed in the last 7 days."
```

**Friday afternoon (15 minutes):**
Review what you built this week. For any completed app:
- Is it live in the App Store / Google Play?
- Have you shared it for initial users?
- Do you need a v1.1 update based on feedback?

---

## 39.7 Monthly Maintenance Checklist (1 Hour)

**1st of each month — Cost Review (20 minutes):**

```
/budget
```

Then in your terminal:
```bash
# Check GCP billing
gcloud billing accounts list
gcloud billing projects describe $(gcloud config get-value project)

# Open GCP Billing in browser
open https://console.cloud.google.com/billing
```

The total monthly ceiling is ~$800 / ~3,000 SAR (§1.4).
Typical breakdown:
- GCP Cloud Run: $5–15/month (scale-to-zero saves cost)
- GCP Secret Manager: $0.06/month (9 secrets)
- GCP Cloud Scheduler: $0.10/month (4 jobs)
- Supabase Free tier: $0
- Neo4j Aura Free tier: $0
- AI calls (Anthropic + Perplexity): $20–80/month
- MacinCloud (iOS builds): $1/build × number of iOS builds
- Apple Developer: $99/year = $8.25/month
- GitHub: $0 (free tier)

**API Key Rotation Schedule (per Appendix B):**

| Key | Rotation | Next date |
|-----|----------|-----------|
| ANTHROPIC_API_KEY | 90 days | Check creation date |
| PERPLEXITY_API_KEY | 90 days | Check creation date |
| GITHUB_TOKEN | 90 days | Expires automatically |
| SUPABASE_SERVICE_KEY | 180 days | Check creation date |
| NEO4J_PASSWORD | 180 days | Check creation date |

To rotate a key:
1. Generate new key on the provider's console
2. Update in GCP Secret Manager:
```bash
echo -n "NEW_KEY_VALUE" | gcloud secrets versions add SECRET_NAME --data-file=-
```
3. Cloud Run picks up the new version automatically on next container start
4. Update your local `.env` file too

**Apple Developer Certificate Calendar:**
Your Apple Distribution certificate expires annually. 30 days before
expiry, Apple sends an email to your developer account email.
When it arrives: renew via `developer.apple.com/account/certificates`.

**USE GOOGLE CALENDAR MCP HERE** when you rotate any key:
```
"Create a reminder 85 days from today: Rotate ANTHROPIC_API_KEY
in GCP Secret Manager and update .env"
```

---

## 39.8 Troubleshooting Quick Reference

The full troubleshooting guide is in `docs/runbooks/03-troubleshooting-runbook.md`.
Here are the most common issues and immediate fixes:

**Problem: Telegram bot not responding**
```bash
# Check webhook is set
curl -s "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/getWebhookInfo" | python3 -m json.tool
```
If `url` field is empty: re-run the webhook registration from NB3 Part 8.
If `url` is set but bot still silent: check Cloud Run logs.

**Problem: Build stuck at a stage > 20 minutes**
```
/cancel
```
Then type `/new` again with the same specification.
If it keeps getting stuck at the same stage: check RB2 for that stage.

**Problem: "Budget cap exceeded"**
The per-project $25 cap has been hit. Options:
1. Type `/authorize` to approve a one-time extension (adds $5)
2. Type `/cancel` and rebuild with a simpler specification
3. Wait until next month if monthly cap is hit

**Problem: Cloud Run returns 503**
```bash
gcloud logging read "resource.type=cloud_run_revision severity>=ERROR" --limit=20
```
Most common causes:
- Container crashed on startup (check logs for Python exception)
- Memory exceeded (increase to 2GiB: `gcloud run services update ... --memory 2Gi`)
- Cold start timeout (enable CPU boost: `gcloud run services update ... --cpu-boost`)

**Problem: "Legal halt — PDPL violation"**
The Scout found a feature that violates Saudi Arabia's Personal Data
Protection Law. The pipeline has HALTED to protect you. Read the
`ksa_compliance_report.pdf` from the S1 output (check Telegram for
this file). Revise your specification to remove or anonymise the
data element that triggered the halt, then rebuild.

**Problem: Neo4j connection lost**
```bash
python -c "
import os; from dotenv import load_dotenv; load_dotenv()
from neo4j import GraphDatabase
driver = GraphDatabase.driver(os.getenv('NEO4J_URI'), 
    auth=('neo4j', os.getenv('NEO4J_PASSWORD')))
driver.verify_connectivity()
print('✅ Connected')
driver.close()
"
```
If this fails: log in at console.neo4j.io and check the instance
status. Free tier instances pause after 72 hours of inactivity.
Click "Resume" to restart it.

---

## 39.9 The Complete Implementation Journey — Final Summary

You have now completed the entire AI Factory Pipeline v5.6 implementation:

```
IMPLEMENTATION MILESTONES
══════════════════════════════════════════════════════════
★ NB1 Part 8   — LOCAL DRY-RUN MILESTONE
                 Architecture verified. $0 spent.
                 Tag: v5.6.0-stub

★ NB2 PROD-17  — ALL STUBS ELIMINATED
                 362 tests passing. Real AI clients.
                 Tag: v5.6.0

★ NB3 Part 7   — CLOUD RUN DEPLOYED
                 Pipeline live 24/7 in GCP me-central1.

★ NB3 Part 8   — TELEGRAM WEBHOOK ACTIVE
                 /start responds. Operator connected.

★ NB3 Part 12  — FIRST REAL APP BUILT
                 Full S0→S8 with real AI. ~$5–15 spent.
                 Tag: v5.6.0-production

★ NB4 Part 30  — FULL SYSTEM CERTIFIED
                 84/84 scorecard. 591 tests. Binary delivery.
                 Modify Mode. Revenue Ops.
                 Tag: v5.6.0-complete
══════════════════════════════════════════════════════════

CODEBASE METRICS AT COMPLETION
══════════════════════════════════════════════════════════
Python files:         85+
Lines of code:        ~23,000
Tests:                591+
Git commits:          50+ (NB1-01 through NB4-30)
Git tags:             4 (stub → verified → production → complete)
Documentation:        ~35,000 lines across 15 files
══════════════════════════════════════════════════════════

INFRASTRUCTURE AT COMPLETION
══════════════════════════════════════════════════════════
GCP Cloud Run:        1 service (me-central1)
GCP Artifact Registry: 1 Docker repo
GCP Secret Manager:   12+ secrets
GCP Cloud Scheduler:  4 Janitor cron jobs
GCP Uptime Check:     1 external monitor
Supabase:             11 tables, 7 indexes
Neo4j Aura:           18 indexes, 1 constraint
Telegram:             1 bot, 15 commands, webhook active
GitHub:               1 pipeline repo + app repos per build
Apple Developer:      Account + API key + certificates
Google Play Console:  Account + service account
Firebase:             Auto-provisioned per app
MacinCloud:           PAYG, $1/hr, 8hr kill switch
══════════════════════════════════════════════════════════

CAPABILITY SUMMARY
══════════════════════════════════════════════════════════
✅ 6 tech stacks: React Native, FlutterFlow, Unity,
   Python Backend, Swift, Kotlin
✅ 3 platforms: iOS (TestFlight → App Store),
   Android (Play Store), Web (Firebase Hosting)
✅ 3 execution modes: Cloud, Local, Hybrid
✅ 2 pipeline modes: CREATE (new app), MODIFY (update)
✅ 4 AI roles: Scout, Strategist, Engineer, Quick Fix
✅ KSA legal compliance: 6 regulatory bodies checked
✅ Budget Governor: 4-tier with circuit breaker
✅ Revenue tracking: /revenue /invoice /clients
✅ Idea scoring: /evaluate before every build
══════════════════════════════════════════════════════════
```

---

*End of Part 3 — NB4 Complete Execution + Daily Operations Reference*

*This is the final part of the Master Implementation Guide.*
*Total guide: Part 1 (NB1 stub build) + Part 2 (NB2 wiring + NB3 activation) + Part 3 (NB4 complete execution + daily ops)*

*Begin your first production app using Section 39.3.*
*Refer to docs/runbooks/ for detailed operational procedures.*
