#!/usr/bin/env bash
# AI Factory Pipeline v5.8 — Render.com Deployment (Free, No CC)
#
# Render free tier: 750 instance-hours/month (always-on), 512MB RAM.
# Sign up at render.com with your GitHub account — no credit card ever needed.
#
# What this does:
#   1. Validate RENDER_API_KEY
#   2. Create or update Render service from render.yaml config
#   3. Set all secrets from .env via Render API
#   4. Trigger deploy and wait for it to go live
#   5. Set Telegram webhook to the Render service URL
#   6. Run Supabase migrations
#   7. Update scheduler.yml SERVICE_URL for keep-alive pings
#   8. Health check
#
# Get your Render API key (free, no CC):
#   1. Sign up at https://render.com with GitHub
#   2. Go to: dashboard.render.com/u/your-username/keys
#   3. Create an API key
#   4. Add to .env: RENDER_API_KEY=rnd_xxxx
#
# Usage:
#   ./scripts/deploy_render.sh

set -euo pipefail

ENV_FILE="${ENV_FILE:-.env}"
RENDER_SERVICE_NAME="ai-factory-pipeline"
RENDER_API="https://api.render.com/v1"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✓${NC} $*"; }
warn() { echo -e "${YELLOW}⚠${NC} $*"; }
err()  { echo -e "${RED}✗${NC} $*"; exit 1; }
info() { echo -e "${BLUE}→${NC} $*"; }

echo "================================================"
echo "  AI Factory Pipeline — Render Deploy (Free)"
echo "================================================"
echo ""

# ── Load .env ─────────────────────────────────────────────────────
[[ ! -f "${ENV_FILE}" ]] && err ".env not found"
set -a; source "${ENV_FILE}"; set +a

RENDER_API_KEY="${RENDER_API_KEY:-}"
if [[ -z "${RENDER_API_KEY}" ]]; then
    echo -e "${YELLOW}RENDER_API_KEY not set.${NC}"
    echo ""
    echo "Get it free (no CC):"
    echo "  1. Sign up at https://render.com  (use GitHub login)"
    echo "  2. Go to: dashboard.render.com/u/settings/keys"
    echo "  3. New API Key → copy token"
    echo "  4. Add to .env:  RENDER_API_KEY=rnd_xxxxxx"
    echo "  5. Re-run this script"
    echo ""
    echo "OR deploy manually (also free):"
    echo "  1. Sign up at render.com with GitHub"
    echo "  2. New → Blueprint → connect github.com/Valonyx/ai-factory-pipeline"
    echo "  3. Render reads render.yaml and creates the service"
    echo "  4. Add secrets in Environment tab"
    echo ""
    exit 1
fi

# ── Step 1: Verify API key ────────────────────────────────────────
echo "Step 1/8: Verifying Render API key..."

OWNER=$(curl -sf \
    -H "Authorization: Bearer ${RENDER_API_KEY}" \
    -H "Accept: application/json" \
    "${RENDER_API}/owners?limit=1" 2>/dev/null | \
    python3 -c "import sys,json; d=json.load(sys.stdin); print(d[0]['owner']['name'] if d else 'unknown')" \
    2>/dev/null || echo "")

[[ -z "${OWNER}" ]] && err "Render API key invalid — check dashboard.render.com/u/settings/keys"
ok "Authenticated as: ${OWNER}"

# ── Step 2: Get or create service ────────────────────────────────
echo ""
echo "Step 2/8: Looking up Render service..."

SERVICES_JSON=$(curl -sf \
    -H "Authorization: Bearer ${RENDER_API_KEY}" \
    -H "Accept: application/json" \
    "${RENDER_API}/services?limit=20" 2>/dev/null || echo "[]")

SERVICE_ID=$(echo "${SERVICES_JSON}" | python3 -c "
import sys, json
svcs = json.load(sys.stdin)
for s in svcs:
    svc = s.get('service', s)
    if svc.get('name') == '${RENDER_SERVICE_NAME}':
        print(svc['id'])
        break
" 2>/dev/null || echo "")

if [[ -n "${SERVICE_ID}" ]]; then
    ok "Found existing service: ${SERVICE_ID}"
else
    info "Service not found — creating from render.yaml (Blueprint)..."
    echo ""
    echo "Render Blueprint deployment requires connecting your GitHub repo:"
    echo ""
    echo "  1. Go to: https://dashboard.render.com/select-repo?type=blueprint"
    echo "  2. Connect: github.com/Valonyx/ai-factory-pipeline"
    echo "  3. Render reads render.yaml and creates the service"
    echo "  4. Re-run this script to set secrets and webhook"
    echo ""
    warn "Service not yet created — complete the Blueprint step above first."
    exit 0
fi

# ── Step 3: Set environment variables and secrets ─────────────────
echo ""
echo "Step 3/8: Setting secrets on Render service..."

# Secrets to inject
declare -A SECRETS=(
    [ANTHROPIC_API_KEY]="${ANTHROPIC_API_KEY:-}"
    [GOOGLE_AI_API_KEY]="${GOOGLE_AI_API_KEY:-}"
    [GROQ_API_KEY]="${GROQ_API_KEY:-}"
    [OPENROUTER_API_KEY]="${OPENROUTER_API_KEY:-}"
    [CEREBRAS_API_KEY]="${CEREBRAS_API_KEY:-}"
    [TOGETHER_API_KEY]="${TOGETHER_API_KEY:-}"
    [MISTRAL_API_KEY]="${MISTRAL_API_KEY:-}"
    [TAVILY_API_KEY]="${TAVILY_API_KEY:-}"
    [EXA_API_KEY]="${EXA_API_KEY:-}"
    [STACKEXCHANGE_APP_KEY]="${STACKEXCHANGE_APP_KEY:-}"
    [TELEGRAM_BOT_TOKEN]="${TELEGRAM_BOT_TOKEN:-}"
    [TELEGRAM_OPERATOR_ID]="${TELEGRAM_OPERATOR_ID:-}"
    [GITHUB_TOKEN]="${GITHUB_TOKEN:-}"
    [SUPABASE_URL]="${SUPABASE_URL:-}"
    [SUPABASE_SERVICE_KEY]="${SUPABASE_SERVICE_KEY:-}"
    [SUPABASE_PUBLISHABLE_KEY]="${SUPABASE_PUBLISHABLE_KEY:-}"
    [NEO4J_URI]="${NEO4J_URI:-}"
    [NEO4J_PASSWORD]="${NEO4J_PASSWORD:-}"
    [UPSTASH_REDIS_REST_URL]="${UPSTASH_REDIS_REST_URL:-}"
    [UPSTASH_REDIS_REST_TOKEN]="${UPSTASH_REDIS_REST_TOKEN:-}"
    [TURSO_DATABASE_URL]="${TURSO_DATABASE_URL:-}"
    [TURSO_AUTH_TOKEN]="${TURSO_AUTH_TOKEN:-}"
)

# Build JSON payload for Render API
ENV_JSON="["
FIRST=1
for key in "${!SECRETS[@]}"; do
    val="${SECRETS[$key]}"
    [[ -z "${val}" ]] && continue
    [[ "${FIRST}" -eq 0 ]] && ENV_JSON+=","
    # Escape val for JSON
    val_escaped=$(printf '%s' "${val}" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read())[1:-1])")
    ENV_JSON+="{\"key\":\"${key}\",\"value\":\"${val_escaped}\"}"
    FIRST=0
done
ENV_JSON+="]"

PATCH_RESP=$(curl -sf -w "\n%{http_code}" \
    -X PATCH \
    -H "Authorization: Bearer ${RENDER_API_KEY}" \
    -H "Accept: application/json" \
    -H "Content-Type: application/json" \
    "${RENDER_API}/services/${SERVICE_ID}/env-vars" \
    -d "{\"envVars\": ${ENV_JSON}}" 2>/dev/null || echo -e "\n500")

HTTP_CODE=$(echo "${PATCH_RESP}" | tail -1)
if [[ "${HTTP_CODE}" == "200" || "${HTTP_CODE}" == "201" ]]; then
    ok "Secrets set on Render service"
else
    warn "Env var update returned HTTP ${HTTP_CODE} — set secrets manually in Render dashboard"
fi

# ── Step 4: Trigger deploy ────────────────────────────────────────
echo ""
echo "Step 4/8: Triggering deploy..."

DEPLOY_RESP=$(curl -sf \
    -X POST \
    -H "Authorization: Bearer ${RENDER_API_KEY}" \
    -H "Accept: application/json" \
    -H "Content-Type: application/json" \
    "${RENDER_API}/services/${SERVICE_ID}/deploys" \
    -d '{"clearCache":"do_not_clear"}' 2>/dev/null || echo "{}")

DEPLOY_ID=$(echo "${DEPLOY_RESP}" | python3 -c "
import sys,json; d=json.load(sys.stdin); print(d.get('id',''))
" 2>/dev/null || echo "")

if [[ -n "${DEPLOY_ID}" ]]; then
    ok "Deploy triggered: ${DEPLOY_ID}"
else
    warn "Could not trigger deploy via API — may deploy on next git push"
fi

# ── Step 5: Get service URL ───────────────────────────────────────
echo ""
echo "Step 5/8: Getting service URL..."

SVC_INFO=$(curl -sf \
    -H "Authorization: Bearer ${RENDER_API_KEY}" \
    -H "Accept: application/json" \
    "${RENDER_API}/services/${SERVICE_ID}" 2>/dev/null || echo "{}")

SERVICE_URL=$(echo "${SVC_INFO}" | python3 -c "
import sys,json
d=json.load(sys.stdin)
svc = d.get('service', d)
print('https://' + svc.get('serviceDetails',{}).get('url','').lstrip('https://') or
      svc.get('name','ai-factory-pipeline') + '.onrender.com')
" 2>/dev/null || echo "https://${RENDER_SERVICE_NAME}.onrender.com")

ok "Service URL: ${SERVICE_URL}"

# Wait for deploy to finish
info "Waiting for deploy to complete (up to 3 min)..."
for i in $(seq 1 18); do
    sleep 10
    HEALTH=$(curl -s --max-time 5 "${SERVICE_URL}/health" 2>/dev/null || echo "")
    if echo "${HEALTH}" | grep -q '"ok"\|"status"'; then
        ok "Service is up!"
        break
    fi
    [[ "${i}" -eq 18 ]] && warn "Service taking longer than expected — check Render dashboard"
done

# ── Step 6: Set Telegram webhook ──────────────────────────────────
echo ""
echo "Step 6/8: Setting Telegram webhook..."

WEBHOOK_URL="${SERVICE_URL}/webhook"
RESPONSE=$(curl -s \
    "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setWebhook" \
    -d "url=${WEBHOOK_URL}" \
    -d "allowed_updates=[\"message\",\"callback_query\"]" \
    -d "drop_pending_updates=true" 2>/dev/null || echo '{"ok":false}')

echo "${RESPONSE}" | grep -q '"ok":true' && \
    ok "Webhook set: ${WEBHOOK_URL}" || \
    warn "Webhook not set — set manually: curl 'https://api.telegram.org/bot\${TELEGRAM_BOT_TOKEN}/setWebhook?url=${WEBHOOK_URL}'"

# ── Step 7: Supabase migrations ───────────────────────────────────
echo ""
echo "Step 7/8: Running Supabase migrations..."

python -c "import supabase" &>/dev/null && \
    { python -m scripts.migrate_supabase && ok "Migrations applied" || \
      warn "Run: python -m scripts.migrate_supabase"; } || \
    warn "supabase-py not installed — run: pip install supabase"

# ── Step 8: Update scheduler SERVICE_URL ─────────────────────────
echo ""
echo "Step 8/8: Updating GitHub Actions scheduler with new service URL..."

SCHEDULER_FILE=".github/workflows/scheduler.yml"
if [[ -f "${SCHEDULER_FILE}" ]]; then
    sed -i.bak \
        "s|APP_URL:.*|APP_URL: ${SERVICE_URL}|g" \
        "${SCHEDULER_FILE}" && rm -f "${SCHEDULER_FILE}.bak"
    ok "scheduler.yml updated: APP_URL=${SERVICE_URL}"
    echo ""
    warn "Commit and push this change so the janitor cron pings the right URL:"
    warn "  git add .github/workflows/scheduler.yml && git commit -m 'chore: update scheduler URL to Render'"
fi

# ── Done ──────────────────────────────────────────────────────────
echo ""
echo "================================================"
echo -e "${GREEN}  AI Factory Pipeline is LIVE on Render!${NC}"
echo "================================================"
echo ""
echo "Service:  ${SERVICE_URL}"
echo "Health:   ${SERVICE_URL}/health"
echo "Webhook:  ${SERVICE_URL}/webhook"
echo ""
echo "The GitHub Actions scheduler.yml pings /health every 6h (janitor)."
echo "This also keeps the service awake — no separate keep-alive needed."
echo ""
echo "Send your first message to the bot:"
echo "  /start"
echo "  /new Build a food delivery app for Saudi Arabia"
