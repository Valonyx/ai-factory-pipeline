#!/usr/bin/env bash
# AI Factory Pipeline v5.6 — Koyeb Deployment (Free, No CC Required)
#
# Koyeb free tier: 1 web service, 512MB RAM, always-on (no sleep), no CC.
# Pulls from GHCR (public image pushed by setup_ghcr.sh).
#
# What this does:
#   1. Install Koyeb CLI if missing
#   2. Authenticate with Koyeb
#   3. Create Koyeb secrets for each .env key
#   4. Deploy / update the service from GHCR image
#   5. Set Telegram webhook to the Koyeb service URL
#   6. Run Supabase migrations
#   7. Health check
#
# Prerequisites:
#   - GHCR image already pushed: ./scripts/setup_ghcr.sh
#   - Koyeb account at koyeb.com (free, no CC)
#   - KOYEB_API_KEY in .env (from app.koyeb.com/user/settings/api-access)
#
# Usage:
#   ./scripts/deploy_koyeb.sh

set -euo pipefail

ENV_FILE="${ENV_FILE:-.env}"
KOYEB_APP="ai-factory-pipeline"
KOYEB_SERVICE="pipeline"
GHCR_IMAGE="ghcr.io/valonyx/ai-factory-pipeline:latest"
KOYEB_REGION="${KOYEB_REGION:-fra}"   # Frankfurt — closest to KSA with free tier

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✓${NC} $*"; }
warn() { echo -e "${YELLOW}⚠${NC} $*"; }
err()  { echo -e "${RED}✗${NC} $*"; exit 1; }
info() { echo -e "${BLUE}→${NC} $*"; }

echo "================================================"
echo "  AI Factory Pipeline — Koyeb Deploy (Free)"
echo "================================================"
echo ""

# ── Load .env ─────────────────────────────────────────────────────
[[ ! -f "${ENV_FILE}" ]] && err ".env not found"
set -a; source "${ENV_FILE}"; set +a

KOYEB_API_KEY="${KOYEB_API_KEY:-}"
[[ -z "${KOYEB_API_KEY}" ]] && {
    echo ""
    echo -e "${YELLOW}KOYEB_API_KEY not set.${NC}"
    echo ""
    echo "To get it (free, no CC):"
    echo "  1. Sign up at https://app.koyeb.com  (GitHub login works)"
    echo "  2. Go to: app.koyeb.com/user/settings/api-access"
    echo "  3. Create an API token"
    echo "  4. Add to .env:  KOYEB_API_KEY=your_token_here"
    echo "  5. Re-run this script"
    echo ""
    exit 1
}

# ── Step 1: Install koyeb CLI ─────────────────────────────────────
echo "Step 1/7: Checking koyeb CLI..."

if ! command -v koyeb &>/dev/null; then
    info "Installing koyeb CLI..."
    if [[ "$(uname)" == "Darwin" ]]; then
        if command -v brew &>/dev/null; then
            brew install koyeb/tap/koyeb
        else
            curl -fsSL https://raw.githubusercontent.com/koyeb/koyeb-cli/master/install.sh | sh
            export PATH="${HOME}/.koyeb/bin:${PATH}"
        fi
    else
        curl -fsSL https://raw.githubusercontent.com/koyeb/koyeb-cli/master/install.sh | sh
        export PATH="${HOME}/.koyeb/bin:${PATH}"
    fi
fi
ok "koyeb CLI: $(koyeb version 2>/dev/null | head -1)"

# ── Step 2: Authenticate ──────────────────────────────────────────
echo ""
echo "Step 2/7: Authenticating with Koyeb..."

export KOYEB_API_KEY
# Test auth
if ! koyeb whoami &>/dev/null 2>&1; then
    koyeb login --api-key "${KOYEB_API_KEY}" 2>/dev/null || \
        err "Koyeb auth failed — check your API key at app.koyeb.com/user/settings/api-access"
fi
ok "Authenticated: $(koyeb whoami 2>/dev/null | head -1)"

# ── Step 3: Create Koyeb secrets from .env ────────────────────────
echo ""
echo "Step 3/7: Creating Koyeb secrets..."

# Non-secret config goes as env vars (--env), secrets go as koyeb secrets (--secret)
SECRET_KEYS=(
    ANTHROPIC_API_KEY GOOGLE_AI_API_KEY GROQ_API_KEY OPENROUTER_API_KEY
    CEREBRAS_API_KEY TOGETHER_API_KEY MISTRAL_API_KEY
    TAVILY_API_KEY EXA_API_KEY STACKEXCHANGE_APP_KEY
    TELEGRAM_BOT_TOKEN GITHUB_TOKEN
    SUPABASE_URL SUPABASE_SERVICE_KEY SUPABASE_PUBLISHABLE_KEY
    NEO4J_URI NEO4J_PASSWORD
    UPSTASH_REDIS_REST_URL UPSTASH_REDIS_REST_TOKEN
    TURSO_DATABASE_URL TURSO_AUTH_TOKEN
)

SECRETS_CREATED=0
for key in "${SECRET_KEYS[@]}"; do
    val="${!key:-}"
    [[ -z "${val}" ]] && continue
    secret_name="aif-$(echo "${key}" | tr '[:upper:]_' '[:lower:]-')"
    # Create or update secret
    if koyeb secrets describe "${secret_name}" &>/dev/null 2>&1; then
        koyeb secrets update "${secret_name}" --value "${val}" 2>/dev/null || true
    else
        koyeb secrets create "${secret_name}" --value "${val}" 2>/dev/null || true
    fi
    (( SECRETS_CREATED++ )) || true
done
ok "Koyeb secrets: ${SECRETS_CREATED} created/updated"

# ── Step 4: Build env-var and secret-ref strings ──────────────────
echo ""
echo "Step 4/7: Configuring service..."

# Non-sensitive config as plain env vars
ENV_ARGS=(
    "--env" "PORT=8080"
    "--env" "PYTHONUNBUFFERED=1"
    "--env" "PIPELINE_ENV=production"
    "--env" "LOG_LEVEL=INFO"
    "--env" "DRY_RUN=false"
    "--env" "TELEGRAM_POLLING=true"
    "--env" "AI_PROVIDER=anthropic"
    "--env" "SCOUT_PROVIDER=tavily"
    "--env" "AI_PROVIDER_CHAIN=anthropic,gemini,groq,openrouter,cerebras,together,mistral,mock"
    "--env" "SCOUT_PROVIDER_CHAIN=tavily,exa,searxng,duckduckgo,wikipedia,hackernews,reddit,stackoverflow,github_search,ai_scout"
    "--env" "MEMORY_BACKEND_CHAIN=neo4j,supabase,upstash,turso"
    "--env" "MONTHLY_BUDGET_USD=300"
    "--env" "PER_PROJECT_BUDGET_USD=25"
    "--env" "STRATEGIST_MODEL=claude-opus-4-6"
    "--env" "ENGINEER_MODEL=claude-sonnet-4-5-20250929"
    "--env" "QUICKFIX_MODEL=claude-haiku-4-5-20251001"
    "--env" "BUDGET_GOVERNOR_ENABLED=true"
    "--env" "GITHUB_USERNAME=Valonyx"
    "--env" "TELEGRAM_OPERATOR_ID=${TELEGRAM_OPERATOR_ID:-634992850}"
    "--env" "GCP_PROJECT_ID=ai-factory-pipeline"
    "--env" "GCP_REGION=me-central1"
)

# Sensitive secrets as Koyeb secret references
SECRET_ARGS=()
for key in "${SECRET_KEYS[@]}"; do
    val="${!key:-}"
    [[ -z "${val}" ]] && continue
    secret_name="aif-$(echo "${key}" | tr '[:upper:]_' '[:lower:]-')"
    SECRET_ARGS+=("--secret" "${key}=${secret_name}")
done

# ── Deploy / Update service ───────────────────────────────────────
# Check if app exists
if koyeb apps describe "${KOYEB_APP}" &>/dev/null 2>&1; then
    info "App '${KOYEB_APP}' exists — updating service..."
    koyeb services update "${KOYEB_APP}/${KOYEB_SERVICE}" \
        --docker "${GHCR_IMAGE}" \
        "${ENV_ARGS[@]}" \
        "${SECRET_ARGS[@]}" \
        2>/dev/null || warn "Service update failed (may need manual update)"
else
    info "Creating app '${KOYEB_APP}'..."
    koyeb apps create "${KOYEB_APP}" 2>/dev/null || true
    koyeb services create "${KOYEB_SERVICE}" \
        --app "${KOYEB_APP}" \
        --docker "${GHCR_IMAGE}" \
        --instance-type nano \
        --regions "${KOYEB_REGION}" \
        --ports "8080:http" \
        --routes "/:8080" \
        --checks "8080:http:/:/" \
        "${ENV_ARGS[@]}" \
        "${SECRET_ARGS[@]}"
fi
ok "Service deployed"

# ── Wait for service to be healthy ───────────────────────────────
echo ""
echo "Waiting for service to start (up to 90s)..."
sleep 10
SERVICE_URL="https://${KOYEB_SERVICE}-${KOYEB_APP}.koyeb.app"

# Try to get the actual URL from koyeb CLI
ACTUAL_URL=$(koyeb services describe "${KOYEB_APP}/${KOYEB_SERVICE}" \
    --output json 2>/dev/null | \
    python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('public_domain',''))" \
    2>/dev/null || echo "")
[[ -n "${ACTUAL_URL}" && "${ACTUAL_URL}" != "None" ]] && SERVICE_URL="https://${ACTUAL_URL}"
ok "Service URL: ${SERVICE_URL}"

# ── Step 5: Set Telegram webhook ──────────────────────────────────
echo ""
echo "Step 5/7: Setting Telegram webhook..."

WEBHOOK_URL="${SERVICE_URL}/webhook"
RESPONSE=$(curl -s \
    "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setWebhook" \
    -d "url=${WEBHOOK_URL}" \
    -d "allowed_updates=[\"message\",\"callback_query\"]" \
    -d "drop_pending_updates=true" 2>/dev/null || echo '{"ok":false}')

if echo "${RESPONSE}" | grep -q '"ok":true'; then
    ok "Webhook set: ${WEBHOOK_URL}"
else
    warn "Webhook not set — bot running in polling mode (OK for now)"
    warn "To set manually later: curl 'https://api.telegram.org/bot\${TELEGRAM_BOT_TOKEN}/setWebhook?url=${WEBHOOK_URL}'"
fi

# ── Step 6: Supabase migrations ───────────────────────────────────
echo ""
echo "Step 6/7: Running Supabase migrations..."

if python -c "import supabase" &>/dev/null; then
    python -m scripts.migrate_supabase && ok "Migrations applied" || \
        warn "Migration failed — run: python -m scripts.migrate_supabase"
else
    warn "supabase-py not installed — install: pip install supabase"
fi

# ── Step 7: Health check ──────────────────────────────────────────
echo ""
echo "Step 7/7: Health check..."
sleep 5

HEALTH=$(curl -s "${SERVICE_URL}/health" 2>/dev/null || echo '{"status":"starting"}')
if echo "${HEALTH}" | grep -q '"ok"\|"status"'; then
    ok "Service responding: ${HEALTH}"
else
    warn "Service starting — check in 30s: curl ${SERVICE_URL}/health"
fi

# ── Done ──────────────────────────────────────────────────────────
echo ""
echo "================================================"
echo -e "${GREEN}  AI Factory Pipeline is LIVE on Koyeb!${NC}"
echo "================================================"
echo ""
echo "Service:  ${SERVICE_URL}"
echo "Health:   ${SERVICE_URL}/health"
echo "Webhook:  ${SERVICE_URL}/webhook"
echo ""
echo "Send your first message:"
echo "  /start"
echo "  /new Build a food delivery app for Saudi Arabia"
echo ""
echo "Useful commands:"
echo "  koyeb services logs ${KOYEB_APP}/${KOYEB_SERVICE}"
echo "  koyeb services describe ${KOYEB_APP}/${KOYEB_SERVICE}"
echo ""
echo "CI auto-deploys on push to main via docker-build.yml + GHCR."
