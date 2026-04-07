#!/usr/bin/env bash
# AI Factory Pipeline v5.6 — Activation Script (Auto-selects platform)
#
# Detects which hosting platform is available and routes accordingly:
#
#   GCP available  → Cloud Run  (activate_pipeline.sh full path)
#   Koyeb key set  → Koyeb      (free, no CC — ./scripts/deploy_koyeb.sh)
#   Neither        → Local      (polling mode — python scripts/run_bot.py)
#
# Usage:
#   ./scripts/activate_pipeline.sh          # auto-detect
#   DEPLOY_PLATFORM=koyeb ./scripts/activate_pipeline.sh  # force Koyeb
#   DEPLOY_PLATFORM=gcp   ./scripts/activate_pipeline.sh  # force GCP
#   DEPLOY_PLATFORM=local ./scripts/activate_pipeline.sh  # force local
#
# Spec Authority: v5.6 NB4 — Operational Activation

set -euo pipefail

ENV_FILE="${ENV_FILE:-.env}"
[[ -f "${ENV_FILE}" ]] && { set -a; source "${ENV_FILE}"; set +a; }

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✓${NC} $*"; }
warn() { echo -e "${YELLOW}⚠${NC} $*"; }
err()  { echo -e "${RED}✗${NC} $*"; exit 1; }
info() { echo -e "${BLUE}→${NC} $*"; }

echo "================================================"
echo "  AI Factory Pipeline v5.6 — Activation"
echo "================================================"
echo ""

# ── Platform auto-detection ───────────────────────────────────────
DEPLOY_PLATFORM="${DEPLOY_PLATFORM:-auto}"

if [[ "${DEPLOY_PLATFORM}" == "auto" ]]; then
    # Priority order: GCP (if billing active) → Render → Koyeb → local
    if command -v gcloud &>/dev/null && \
       gcloud beta billing projects describe "${GCP_PROJECT_ID:-ai-factory-pipeline}" \
           --format="value(billingEnabled)" 2>/dev/null | grep -q "True"; then
        DEPLOY_PLATFORM="gcp"
    elif [[ -n "${RENDER_API_KEY:-}" ]]; then
        DEPLOY_PLATFORM="render"
    elif [[ -n "${HF_TOKEN:-}" && -n "${HF_USERNAME:-}" ]]; then
        DEPLOY_PLATFORM="hf_spaces"
    elif [[ -n "${KOYEB_API_KEY:-}" ]]; then
        DEPLOY_PLATFORM="koyeb"
    else
        DEPLOY_PLATFORM="local"
    fi
    info "Auto-detected platform: ${DEPLOY_PLATFORM}"
fi

# ── Route to selected platform ────────────────────────────────────
case "${DEPLOY_PLATFORM}" in
    local)
        echo ""
        echo -e "${YELLOW}No hosted platform configured.${NC}"
        echo "Running in local polling mode (bot connects outbound to Telegram)."
        echo ""
        echo "To run the bot:"
        echo "  python scripts/run_bot.py"
        echo ""
        echo "To deploy free with no CC (recommended):"
        echo "  Render.com (easiest):"
        echo "    1. Sign up at https://render.com  (GitHub login)"
        echo "    2. Add RENDER_API_KEY= to .env"
        echo "    3. ./scripts/deploy_render.sh"
        echo ""
        echo "  Hugging Face Spaces (Docker):"
        echo "    1. Sign up at https://huggingface.co"
        echo "    2. ./scripts/deploy_hf_spaces.sh"
        echo ""
        # Still run migrations and start locally
        info "Running Supabase migrations..."
        python -m scripts.migrate_supabase 2>/dev/null && ok "Migrations applied" || \
            warn "Run manually: python -m scripts.migrate_supabase"
        echo ""
        echo "Starting bot in local polling mode..."
        exec python scripts/run_bot.py
        ;;

    render)
        info "Deploying to Render.com (free, no CC)..."
        echo ""
        exec ./scripts/deploy_render.sh
        ;;

    hf_spaces)
        info "Deploying to Hugging Face Spaces (free, no CC)..."
        echo ""
        exec ./scripts/deploy_hf_spaces.sh
        ;;

    koyeb)
        info "Deploying to Koyeb (free tier)..."
        echo ""
        if ! docker pull "ghcr.io/valonyx/ai-factory-pipeline:latest" --quiet 2>/dev/null; then
            info "GHCR image not found — building and pushing first..."
            ./scripts/setup_ghcr.sh
        fi
        exec ./scripts/deploy_koyeb.sh
        ;;

    gcp)
        # Continue with original GCP Cloud Run path below
        info "Deploying to GCP Cloud Run..."
        echo ""
        ;;

    *)
        err "Unknown DEPLOY_PLATFORM '${DEPLOY_PLATFORM}'. Use: auto|local|koyeb|gcp"
        ;;
esac

# ─────────────────────────────────────────────────────────────────
# GCP Cloud Run path (original implementation)
# ─────────────────────────────────────────────────────────────────

GCP_PROJECT="${GCP_PROJECT:-$(gcloud config get-value project 2>/dev/null)}"
REGION="${GCP_REGION:-me-central1}"
REPO="${ARTIFACT_REPO:-ai-factory}"
SERVICE="${CLOUD_RUN_SERVICE:-ai-factory-pipeline}"
IMAGE="${REGION}-docker.pkg.dev/${GCP_PROJECT}/${REPO}/${SERVICE}"

echo "================================================"
echo "  AI Factory Pipeline v5.6 — GCP Cloud Run"
echo "================================================"
echo "Project: ${GCP_PROJECT}  Region: ${REGION}"
echo ""

# ── Step 1: Validate .env ─────────────────────────────────────────
echo "Step 1/8: Validating .env..."

if [[ ! -f "${ENV_FILE}" ]]; then
    err ".env not found. Copy .env.example → .env and fill in secrets."
fi

REQUIRED_KEYS=(
    ANTHROPIC_API_KEY
    TELEGRAM_BOT_TOKEN
    TELEGRAM_OPERATOR_ID
    SUPABASE_URL
    SUPABASE_SERVICE_KEY
)

missing=()
while IFS= read -r line || [[ -n "${line}" ]]; do
    [[ "${line}" =~ ^#.*$ || -z "${line}" ]] && continue
    key="${line%%=*}"
    val="${line#*=}"
    val="${val%%#*}"  # strip inline comments
    val="${val// /}"  # strip spaces
    for req in "${REQUIRED_KEYS[@]}"; do
        if [[ "${key}" == "${req}" && -z "${val}" ]]; then
            missing+=("${req}")
        fi
    done
done < "${ENV_FILE}"

if [[ ${#missing[@]} -gt 0 ]]; then
    err "Missing required secrets in .env: ${missing[*]}"
fi
ok ".env validation passed (${#REQUIRED_KEYS[@]} required keys present)"

# Load .env into environment
set -a; source "${ENV_FILE}"; set +a

# ── Step 2: Push secrets to GCP Secret Manager ───────────────────
echo ""
echo "Step 2/8: Pushing secrets to GCP Secret Manager..."

gcloud services enable secretmanager.googleapis.com \
    --project="${GCP_PROJECT}" --quiet

while IFS= read -r line || [[ -n "${line}" ]]; do
    [[ "${line}" =~ ^#.*$ || -z "${line}" ]] && continue
    key="${line%%=*}"
    val="${line#*=}"
    val="${val%%#*}"
    val="$(echo "${val}" | sed 's/^ *//;s/ *$//')"
    [[ -z "${val}" ]] && continue

    secret_name="aif-${key,,}"  # lowercase with aif- prefix
    secret_name="${secret_name//_/-}"

    # Create or update secret
    if gcloud secrets describe "${secret_name}" --project="${GCP_PROJECT}" &>/dev/null; then
        echo -n "${val}" | gcloud secrets versions add "${secret_name}" \
            --project="${GCP_PROJECT}" --data-file=- --quiet
    else
        echo -n "${val}" | gcloud secrets create "${secret_name}" \
            --project="${GCP_PROJECT}" --data-file=- --quiet \
            --replication-policy=automatic
    fi
done < "${ENV_FILE}"
ok "Secrets pushed to Secret Manager"

# ── Step 3: Supabase migrations ───────────────────────────────────
echo ""
echo "Step 3/8: Running Supabase migrations..."

if python -c "import supabase" &>/dev/null; then
    python -m scripts.migrate_supabase && ok "Supabase migrations applied" || \
        warn "Supabase migration failed (check credentials)"
else
    warn "supabase-py not installed — run migrations manually via SQL editor"
fi

# ── Step 4: Build Docker image ────────────────────────────────────
echo ""
echo "Step 4/8: Building Docker image..."

gcloud services enable artifactregistry.googleapis.com \
    --project="${GCP_PROJECT}" --quiet

# Create Artifact Registry repo if needed
gcloud artifacts repositories describe "${REPO}" \
    --location="${REGION}" --project="${GCP_PROJECT}" &>/dev/null || \
    gcloud artifacts repositories create "${REPO}" \
        --repository-format=docker \
        --location="${REGION}" \
        --project="${GCP_PROJECT}" \
        --description="AI Factory Pipeline images" --quiet

gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet

docker build -t "${IMAGE}:latest" . --quiet
docker push "${IMAGE}:latest" --quiet
ok "Docker image built and pushed: ${IMAGE}:latest"

# ── Step 5: Deploy to Cloud Run ───────────────────────────────────
echo ""
echo "Step 5/8: Deploying to Cloud Run..."

gcloud services enable run.googleapis.com --project="${GCP_PROJECT}" --quiet

# Build --set-env-vars from .env
ENV_VARS=""
while IFS= read -r line || [[ -n "${line}" ]]; do
    [[ "${line}" =~ ^#.*$ || -z "${line}" ]] && continue
    key="${line%%=*}"
    val="${line#*=}"
    val="${val%%#*}"
    val="$(echo "${val}" | sed 's/^ *//;s/ *$//')"
    [[ -z "${val}" ]] && continue
    ENV_VARS="${ENV_VARS},${key}=${val}"
done < "${ENV_FILE}"
ENV_VARS="${ENV_VARS#,}"  # strip leading comma

gcloud run deploy "${SERVICE}" \
    --image="${IMAGE}:latest" \
    --region="${REGION}" \
    --project="${GCP_PROJECT}" \
    --platform=managed \
    --allow-unauthenticated \
    --memory=1Gi \
    --cpu=1 \
    --concurrency=80 \
    --max-instances=5 \
    --set-env-vars="${ENV_VARS}" \
    --quiet

SERVICE_URL=$(gcloud run services describe "${SERVICE}" \
    --region="${REGION}" \
    --project="${GCP_PROJECT}" \
    --format="value(status.url)")
ok "Deployed to Cloud Run: ${SERVICE_URL}"

# ── Step 6: Set Telegram webhook ──────────────────────────────────
echo ""
echo "Step 6/8: Setting Telegram webhook..."

WEBHOOK_URL="${SERVICE_URL}/webhook"
RESPONSE=$(curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setWebhook" \
    -d "url=${WEBHOOK_URL}" \
    -d "allowed_updates=[\"message\",\"callback_query\"]" \
    -d "drop_pending_updates=true")

if echo "${RESPONSE}" | grep -q '"ok":true'; then
    ok "Telegram webhook set: ${WEBHOOK_URL}"
else
    warn "Webhook setup failed. Set manually:"
    warn "  curl 'https://api.telegram.org/bot\${TELEGRAM_BOT_TOKEN}/setWebhook?url=${WEBHOOK_URL}'"
fi

# ── Step 7: Cloud Scheduler ───────────────────────────────────────
echo ""
echo "Step 7/8: Setting up Cloud Scheduler..."
SERVICE_URL="${SERVICE_URL}" ./scripts/setup_cloud_scheduler.sh && \
    ok "Cloud Scheduler configured" || \
    warn "Cloud Scheduler setup failed (run scripts/setup_cloud_scheduler.sh manually)"

# ── Step 8: Health check ──────────────────────────────────────────
echo ""
echo "Step 8/8: Running health check..."
sleep 3  # give Cloud Run a moment to settle

HEALTH=$(curl -s "${SERVICE_URL}/health" 2>/dev/null || echo '{"status":"unreachable"}')
if echo "${HEALTH}" | grep -q '"ok"'; then
    ok "Health check passed: ${HEALTH}"
elif echo "${HEALTH}" | grep -q '"status"'; then
    ok "Service responding: ${HEALTH}"
else
    warn "Health check inconclusive — check logs: gcloud run logs tail ${SERVICE}"
fi

# ── Done ──────────────────────────────────────────────────────────
echo ""
echo "================================================"
echo -e "${GREEN}  AI Factory Pipeline is LIVE!${NC}"
echo "================================================"
echo ""
echo "Bot URL:     https://t.me/${SERVICE}"
echo "Service:     ${SERVICE_URL}"
echo "Health:      ${SERVICE_URL}/health"
echo "Webhook:     ${SERVICE_URL}/webhook"
echo ""
echo "Send your first message to the bot:"
echo "  /start"
echo "  /new Build a food delivery app for Saudi Arabia"
echo ""
echo "Useful commands:"
echo "  gcloud run logs tail ${SERVICE} --region ${REGION}"
echo "  gcloud scheduler jobs list --location ${REGION}"
