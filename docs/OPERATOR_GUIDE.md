# Operator Guide — AI Factory Pipeline v5.6

This guide is for non-technical operators who interact with the pipeline through Telegram.

---

## Getting Started

1. **Open Telegram** and find the AI Factory bot
2. **Send a message** describing the app you want to build
3. **The pipeline runs automatically** — you'll receive progress updates
4. **Answer any questions** the bot asks (stack choice, design preference, etc.)
5. **Receive your app** — binaries, source code, and documentation

Example first message:
> Build me an e-commerce app for selling handmade crafts in Saudi Arabia. It should support Arabic and English, have Mada payments, and work on iOS and Android.

---

## Bot Commands

| Command | What it does |
|---------|-------------|
| `/start` | Begin a new project |
| `/status` | Check current project progress |
| `/budget` | View remaining budget |
| `/cancel` | Cancel the current project |
| `/continue` | Resume a halted pipeline |
| `/force_continue` | Override a halt and proceed |
| `/snapshots` | List saved checkpoints |
| `/restore State_#N` | Go back to checkpoint N |
| `/warroom` | View error fix history |
| `/legal` | View legal compliance status |
| `/help` | Show all commands |

---

## How the Pipeline Works

Your app goes through 9 stages:

1. **Intake** — The bot reads your description and confirms what you want
2. **Legal Gate** — Checks Saudi regulations (PDPL, SAMA, CST) apply
3. **Blueprint** — Picks the best tech stack and designs the architecture
4. **Code Generation** — Writes all the code for your app
5. **Build** — Compiles everything into a working app
6. **Test** — Runs automated tests to find bugs
7. **Deploy** — Puts your app on the internet
8. **Verify** — Checks the deployed app actually works
9. **Handoff** — Delivers binaries, docs, and instructions to you

If something goes wrong at steps 4–6, the **War Room** activates automatically and tries to fix it (up to 3 attempts).

---

## Modes

**Autopilot** (default) — The pipeline makes all decisions automatically. Best for simple apps.

**Copilot** — The pipeline asks you to choose at key decision points:
- App scope (as described / simplified / enhanced)
- Tech stack (AI recommendation / Alternative A / Alternative B)
- Design (Mock 1 / Mock 2 / Mock 3)
- How to handle test failures

To switch modes, tell the bot: "Switch to copilot mode" or "Switch to autopilot."

---

## Budget

Your monthly budget is **$300 USD (~1,125 SAR)** by default.

The budget has 4 levels:
- 🟢 **Green** (0–80%) — Everything works normally
- 🟡 **Amber** (80–95%) — Research features limited, you'll get alerts
- 🔴 **Red** (95–100%) — No new projects, existing ones continue
- ⚫ **Black** (100%+) — Pipeline stops, contact admin

A typical app costs **$15–$35** to build. Check your budget anytime with `/budget`.

---

## Receiving Your App

When the pipeline finishes, you'll receive:

**Files delivered via Telegram:**
- App binary (.ipa for iOS, .aab for Android)
- Source code archive
- If files are too large (>50MB), you'll get a download link valid for 72 hours

**Documentation (Handoff Intelligence Pack):**
1. **Operations Manual** — How to start/stop, update, and maintain your app
2. **Technical Guide** — Architecture, APIs, database structure
3. **Troubleshooting Playbook** — Common errors and how to fix them
4. **Cost Summary** — How much each part of the build cost

**For app stores:**
- The pipeline tries to upload automatically
- If automatic upload fails, you'll receive step-by-step instructions for manual upload via Apple Transporter (iOS) or Google Play Console (Android)
- Important: Manual upload does not bypass Apple/Google review

---

## When Things Go Wrong

**Pipeline halted?**
- Check the message — it tells you why
- Common reasons: legal compliance issue, budget exceeded, repeated build failures
- Use `/continue` after resolving the issue
- Use `/force_continue` to override (use with caution)

**App not working after deploy?**
- The pipeline verifies automatically and will redeploy if needed (up to 2 times)
- If it still fails, you'll be notified with details

**Need to go back?**
- Use `/snapshots` to see all checkpoints
- Use `/restore State_#5` to go back to checkpoint 5
- This resets to that point and resumes from there

---

## Legal Compliance

The pipeline automatically handles Saudi regulatory requirements:

- **PDPL** (Personal Data Protection Law) — Data stays in KSA (Dammam data center)
- **SAMA** — Financial apps get sandbox-first payment mode
- **CST** — Telecom features checked against Communications regulations
- **NCA** — Cybersecurity controls applied when needed

Legal documents (Privacy Policy, Terms of Service) are generated as templates with TODO markers — you must review and customize them before publishing.

Use `/legal` to check compliance status at any time.

---

## Tips

- **Be specific** in your initial description — the more detail, the better the app
- **Include the audience** — "for Saudi youth" or "for restaurant owners in Riyadh"
- **Mention payments early** — payment features affect legal requirements
- **Use Copilot mode** for your first app to understand the process
- **Check `/budget` regularly** if you're building multiple apps per month
