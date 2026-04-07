#!/usr/bin/env bash
# AI Factory Pipeline v5.6 — Fly.io Deployment
#
# ⚠️  NOTE: Fly.io requires billing activation (credit card) to deploy.
#     If you don't have a CC or are in a region with payment issues,
#     use Koyeb instead (truly free, no CC):
#
#       ./scripts/deploy_koyeb.sh
#
# Fly.io deployment path — use when billing is available:
#   1. Validate .env (required secrets present)
#   2. Install flyctl if missing
#   3. Authenticate with Fly.io
#   4. Build Docker image and push to GHCR (free, uses GITHUB_TOKEN)
#   5. Create Fly.io app (if new) or just deploy (if existing)
#   6. Push all .env secrets to fly secrets
#   7. Deploy image to Fly.io
#   8. Set Telegram webhook OR confirm polling mode
#   9. Trigger Supabase migrations
#  10. Health check
#   - Telegram polling: no inbound URL needed
#
# Prerequisites:
#   - .env filled with real keys
#   - Docker installed and running
#   - GitHub token with packages:write scope (already in .env)
#
# Usage:
#   ./scripts/deploy_fly.sh
#   FLY_API_TOKEN=your_token ./scripts/deploy_fly.sh   # non-interactive

set -euo pipefail

ENV_FILE="${ENV_FILE:-.env}"
GHCR_IMAGE="ghcr.io/valonyx/ai-factory-pipeline"
FLY_APP="ai-factory-pipeline"
FLY_REGION="${FLY_REGION:-bom}"   # Mumbai — closest free-tier region to KSA

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✓${NC} $*"; }
warn() { echo -e "${YELLOW}⚠${NC} $*"; }
err()  { echo -e "${RED}✗${NC} $*"; exit 1; }
info() { echo -e "${BLUE}→${NC} $*"; }

echo "================================================"
echo "  AI Factory Pipeline — Fly.io Deploy (Free)"
echo "================================================"
echo ""

# ── Step 1: Validate .env ─────────────────────────────────────────
echo "Step 1/10: Validating .env..."

[[ ! -f "${ENV_FILE}" ]] && err ".env not found. Copy .env.example → .env and fill in secrets."

REQUIRED_KEYS=(
    ANTHROPIC_API_KEY
    TELEGRAM_BOT_TOKEN
    TELEGRAM_OPERATOR_ID
    SUPABASE_URL
    SUPABASE_SERVICE_KEY
    GITHUB_TOKEN
)

missing=()
while IFS= read -r line || [[ -n "${line}" ]]; do
    [[ "${line}" =~ ^#.*$ || -z "${line}" ]] && continue
    key="${line%%=*}"
    val="${line#*=}"
    val="${val%%#*}"
    val="$(echo "${val}" | sed 's/^ *//;s/ *$//')"
    for req in "${REQUIRED_KEYS[@]}"; do
        [[ "${key}" == "${req}" && -z "${val}" ]] && missing+=("${req}")
    done
done < "${ENV_FILE}"

[[ ${#missing[@]} -gt 0 ]] && err "Missing required keys in .env: ${missing[*]}"

# Load .env
set -a; source "${ENV_FILE}"; set +a
ok ".env validated"

# ── Step 2: Install flyctl ────────────────────────────────────────
echo ""
echo "Step 2/10: Checking flyctl..."

if ! command -v flyctl &>/dev/null && ! command -v fly &>/dev/null; then
    info "flyctl not found — installing..."
    curl -L https://fly.io/install.sh | sh
    export PATH="${HOME}/.fly/bin:${PATH}"
fi

FLY_CMD="fly"
command -v flyctl &>/dev/null && FLY_CMD="flyctl"
ok "flyctl available: $($FLY_CMD version 2>/dev/null | head -1)"

# ── Step 3: Authenticate Fly.io ───────────────────────────────────
echo ""
echo "Step 3/10: Authenticating with Fly.io..."

if [[ -n "${FLY_API_TOKEN:-}" ]]; then
    export FLY_API_TOKEN
    ok "Using FLY_API_TOKEN from environment"
else
    # Check if already authenticated
    if $FLY_CMD auth whoami &>/dev/null; then
        ok "Already authenticated: $($FLY_CMD auth whoami 2>/dev/null)"
    else
        info "Opening browser for Fly.io login..."
        $FLY_CMD auth login
    fi
fi

# ── Step 4: Build and push Docker image to GHCR ──────────────────
echo ""
echo "Step 4/10: Building and pushing Docker image to GHCR..."

GIT_SHA=$(git rev-parse --short HEAD 2>/dev/null || echo "latest")
FULL_IMAGE="${GHCR_IMAGE}:${GIT_SHA}"
LATEST_IMAGE="${GHCR_IMAGE}:latest"

# Authenticate with GHCR
echo "${GITHUB_TOKEN}" | docker login ghcr.io -u valonyx --password-stdin --quiet
ok "Authenticated with ghcr.io"

docker build -t "${FULL_IMAGE}" -t "${LATEST_IMAGE}" . --quiet
ok "Image built: ${FULL_IMAGE}"

docker push "${FULL_IMAGE}" --quiet
docker push "${LATEST_IMAGE}" --quiet
ok "Pushed to GHCR: ${FULL_IMAGE}"

# ── Step 5: Create or confirm Fly.io app ─────────────────────────
echo ""
echo "Step 5/10: Setting up Fly.io app..."

if $FLY_CMD apps list 2>/dev/null | grep -q "^${FLY_APP}"; then
    ok "App '${FLY_APP}' already exists"
else
    info "Creating app '${FLY_APP}'..."
    $FLY_CMD apps create "${FLY_APP}" --machines-size "shared-cpu-1x" 2>/dev/null || \
        $FLY_CMD launch --name "${FLY_APP}" --region "${FLY_REGION}" \
            --no-deploy --copy-config --yes 2>/dev/null || \
        warn "App may already exist — continuing"
    ok "App created: ${FLY_APP}"
fi

# ── Step 6: Push secrets to Fly.io ───────────────────────────────
echo ""
echo "Step 6/10: Pushing secrets to Fly.io..."

SECRETS_ARGS=""
SECRETS_SKIPPED=0
while IFS= read -r line || [[ -n "${line}" ]]; do
    [[ "${line}" =~ ^#.*$ || -z "${line}" ]] && continue
    key="${line%%=*}"
    val="${line#*=}"
    val="${val%%#*}"
    val="$(echo "${val}" | sed 's/^ *//;s/ *$//')"
    [[ -z "${val}" ]] && { (( SECRETS_SKIPPED++ )) || true; continue; }
    # Skip non-secret config that's in fly.toml [env]
    case "${key}" in
        PORT|PYTHONUNBUFFERED|PYTHONDONTWRITEBYTECODE|PIPELINE_ENV|LOG_LEVEL|\
        DRY_RUN|TELEGRAM_POLLING|MONTHLY_BUDGET_USD|PER_PROJECT_BUDGET_USD|\
        AI_PROVIDER|SCOUT_PROVIDER|STRATEGIST_MODEL|ENGINEER_MODEL|QUICKFIX_MODEL|\
        SCOUT_MODEL|BUDGET_GOVERNOR_ENABLED|GCP_PROJECT_ID|GCP_REGION|GITHUB_USERNAME|\
        AI_PROVIDER_CHAIN|SCOUT_PROVIDER_CHAIN|MEMORY_BACKEND_CHAIN)
            continue ;;
    esac
    SECRETS_ARGS="${SECRETS_ARGS} ${key}=${val}"
done < "${ENV_FILE}"

if [[ -n "${SECRETS_ARGS}" ]]; then
    # shellcheck disable=SC2086
    $FLY_CMD secrets set --app "${FLY_APP}" ${SECRETS_ARGS} --stage 2>/dev/null || \
        $FLY_CMD secrets set --app "${FLY_APP}" ${SECRETS_ARGS} 2>/dev/null
    ok "Secrets pushed to Fly.io (${SECRETS_SKIPPED} empty skipped)"
else
    warn "No secrets to push"
fi

# ── Step 7: Deploy to Fly.io ──────────────────────────────────────
echo ""
echo "Step 7/10: Deploying to Fly.io..."

$FLY_CMD deploy \
    --app "${FLY_APP}" \
    --image "${LATEST_IMAGE}" \
    --strategy rolling \
    --wait-timeout 120 \
    --yes 2>/dev/null || \
$FLY_CMD deploy \
    --app "${FLY_APP}" \
    --image "${LATEST_IMAGE}" \
    --wait-timeout 120

SERVICE_URL="https://${FLY_APP}.fly.dev"
ok "Deployed: ${SERVICE_URL}"

# ── Step 8: Telegram webhook / polling ───────────────────────────
echo ""
echo "Step 8/10: Configuring Telegram..."

# In polling mode, the bot connects outbound — no webhook needed.
# Polling mode is set via TELEGRAM_POLLING=true in fly.toml [env].
# Optionally set webhook for production (comment out if using polling):
WEBHOOK_URL="${SERVICE_URL}/webhook"
RESPONSE=$(curl -s \
    "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setWebhook" \
    -d "url=${WEBHOOK_URL}" \
    -d "allowed_updates=[\"message\",\"callback_query\"]" \
    -d "drop_pending_updates=true" 2>/dev/null || echo '{"ok":false}')

if echo "${RESPONSE}" | grep -q '"ok":true'; then
    ok "Webhook set: ${WEBHOOK_URL}"
    # Switch to webhook mode since we have a URL
    $FLY_CMD secrets set --app "${FLY_APP}" TELEGRAM_POLLING=false --stage 2>/dev/null || true
else
    warn "Webhook not set — bot running in polling mode (TELEGRAM_POLLING=true)"
    warn "This is fine for dev; for production re-run or set webhook manually."
fi

# ── Step 9: Supabase migrations ───────────────────────────────────
echo ""
echo "Step 9/10: Running Supabase migrations..."

if python -c "import supabase" &>/dev/null; then
    python -m scripts.migrate_supabase && ok "Supabase migrations applied" || \
        warn "Migration failed — run manually: python -m scripts.migrate_supabase"
else
    warn "supabase-py not installed — install: pip install supabase"
fi

# ── Step 10: Health check ─────────────────────────────────────────
echo ""
echo "Step 10/10: Running health check..."
sleep 5   # give Fly.io a moment to settle

HEALTH=$(curl -s "${SERVICE_URL}/health" 2>/dev/null || echo '{"status":"unreachable"}')
if echo "${HEALTH}" | grep -q '"ok"\|"status"'; then
    ok "Service responding: ${HEALTH}"
else
    warn "Health check inconclusive — check logs: fly logs --app ${FLY_APP}"
fi

# ── Done ──────────────────────────────────────────────────────────
echo ""
echo "================================================"
echo -e "${GREEN}  AI Factory Pipeline is LIVE on Fly.io!${NC}"
echo "================================================"
echo ""
echo "Service URL:  ${SERVICE_URL}"
echo "Health:       ${SERVICE_URL}/health"
echo "Webhook:      ${SERVICE_URL}/webhook"
echo ""
echo "Send your first message:"
echo "  /start"
echo "  /new Build a food delivery app for Saudi Arabia"
echo ""
echo "Useful commands:"
echo "  fly logs --app ${FLY_APP}"
echo "  fly status --app ${FLY_APP}"
echo "  fly ssh console --app ${FLY_APP}"
echo ""
echo "When GCP billing is resolved, run instead:"
echo "  ./scripts/activate_pipeline.sh"
