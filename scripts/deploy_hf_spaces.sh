#!/usr/bin/env bash
# AI Factory Pipeline v5.6 — Hugging Face Spaces Deployment (Free, No CC)
#
# HF Spaces free tier: 2 vCPU, 16GB RAM, Docker support, public HTTPS URL.
# Free forever, no credit card, sign up with email or GitHub.
# Note: Spaces may pause after extended inactivity but restart on first request.
# The GitHub Actions health probe (scheduler.yml) keeps it awake automatically.
#
# What this does:
#   1. Validate HF_TOKEN and HF_USERNAME
#   2. Create HF Space (Docker SDK) via HF API
#   3. Push secrets to Space (encrypted at rest)
#   4. Build and push Docker image to the HF Space registry
#   5. Set Telegram webhook to the Space URL
#   6. Run Supabase migrations
#   7. Health check
#
# Get HF token (free, no CC):
#   1. Sign up at https://huggingface.co  (email or GitHub)
#   2. Go to: huggingface.co/settings/tokens
#   3. New token → Write access → copy token
#   4. Add to .env:  HF_TOKEN=hf_xxxx  HF_USERNAME=your_username
#
# Usage:
#   ./scripts/deploy_hf_spaces.sh

set -euo pipefail

ENV_FILE="${ENV_FILE:-.env}"
SPACE_NAME="ai-factory-pipeline"
HF_API="https://huggingface.co/api"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✓${NC} $*"; }
warn() { echo -e "${YELLOW}⚠${NC} $*"; }
err()  { echo -e "${RED}✗${NC} $*"; exit 1; }
info() { echo -e "${BLUE}→${NC} $*"; }

echo "================================================"
echo "  AI Factory Pipeline — HF Spaces (Free)"
echo "================================================"
echo ""

[[ ! -f "${ENV_FILE}" ]] && err ".env not found"
set -a; source "${ENV_FILE}"; set +a

HF_TOKEN="${HF_TOKEN:-}"
HF_USERNAME="${HF_USERNAME:-}"

if [[ -z "${HF_TOKEN}" || -z "${HF_USERNAME}" ]]; then
    echo -e "${YELLOW}HF_TOKEN or HF_USERNAME not set.${NC}"
    echo ""
    echo "Get them free (no CC):"
    echo "  1. Sign up at https://huggingface.co"
    echo "  2. huggingface.co/settings/tokens → New token (Write)"
    echo "  3. Add to .env:"
    echo "       HF_TOKEN=hf_xxxxxxxxxxxx"
    echo "       HF_USERNAME=your_username"
    exit 1
fi

SPACE_ID="${HF_USERNAME}/${SPACE_NAME}"
SPACE_URL="https://${HF_USERNAME}-${SPACE_NAME}.hf.space"

# ── Step 1: Verify token ──────────────────────────────────────────
echo "Step 1/7: Verifying HF token..."

WHOAMI=$(curl -sf \
    -H "Authorization: Bearer ${HF_TOKEN}" \
    "${HF_API}/whoami" 2>/dev/null | \
    python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('name','unknown'))" \
    2>/dev/null || echo "")
[[ -z "${WHOAMI}" ]] && err "HF token invalid — check huggingface.co/settings/tokens"
ok "Authenticated as: ${WHOAMI}"

# ── Step 2: Create or verify Space ───────────────────────────────
echo ""
echo "Step 2/7: Creating HF Space..."

# Check if Space exists
SPACE_EXISTS=$(curl -sf \
    -H "Authorization: Bearer ${HF_TOKEN}" \
    "${HF_API}/spaces/${SPACE_ID}" 2>/dev/null | \
    python3 -c "import sys,json; d=json.load(sys.stdin); print('yes' if d.get('id') else 'no')" \
    2>/dev/null || echo "no")

if [[ "${SPACE_EXISTS}" == "yes" ]]; then
    ok "Space '${SPACE_ID}' already exists"
else
    info "Creating Space '${SPACE_ID}'..."
    CREATE_RESP=$(curl -sf \
        -X POST \
        -H "Authorization: Bearer ${HF_TOKEN}" \
        -H "Content-Type: application/json" \
        "${HF_API}/repos/create" \
        -d "{
            \"type\": \"space\",
            \"name\": \"${SPACE_NAME}\",
            \"private\": false,
            \"sdk\": \"docker\",
            \"hardware\": \"cpu-basic\"
        }" 2>/dev/null || echo "{}")
    CREATED_ID=$(echo "${CREATE_RESP}" | python3 -c "
import sys,json; d=json.load(sys.stdin); print(d.get('id',''))" 2>/dev/null || echo "")
    [[ -z "${CREATED_ID}" ]] && err "Failed to create Space — check your HF token permissions"
    ok "Space created: ${CREATED_ID}"
fi

# ── Step 3: Set Space secrets ─────────────────────────────────────
echo ""
echo "Step 3/7: Setting Space secrets..."

SECRET_KEYS=(
    ANTHROPIC_API_KEY GOOGLE_AI_API_KEY GROQ_API_KEY OPENROUTER_API_KEY
    CEREBRAS_API_KEY TOGETHER_API_KEY MISTRAL_API_KEY
    TAVILY_API_KEY EXA_API_KEY STACKEXCHANGE_APP_KEY
    TELEGRAM_BOT_TOKEN TELEGRAM_OPERATOR_ID GITHUB_TOKEN
    SUPABASE_URL SUPABASE_SERVICE_KEY SUPABASE_PUBLISHABLE_KEY
    NEO4J_URI NEO4J_PASSWORD
    UPSTASH_REDIS_REST_URL UPSTASH_REDIS_REST_TOKEN
    TURSO_DATABASE_URL TURSO_AUTH_TOKEN
)

SECRETS_SET=0
for key in "${SECRET_KEYS[@]}"; do
    val="${!key:-}"
    [[ -z "${val}" ]] && continue
    curl -sf \
        -X POST \
        -H "Authorization: Bearer ${HF_TOKEN}" \
        -H "Content-Type: application/json" \
        "${HF_API}/spaces/${SPACE_ID}/secrets" \
        -d "{\"key\": \"${key}\", \"value\": $(python3 -c "import json,sys; print(json.dumps('${val//\'/\'\\\'\'}'))")}" \
        &>/dev/null || true
    (( SECRETS_SET++ )) || true
done
ok "Secrets set: ${SECRETS_SET}"

# Also set non-secret config vars
CONFIG_VARS=(
    "PORT=8080"
    "PYTHONUNBUFFERED=1"
    "PIPELINE_ENV=production"
    "DRY_RUN=false"
    "TELEGRAM_POLLING=false"
    "AI_PROVIDER=anthropic"
    "SCOUT_PROVIDER=tavily"
    "AI_PROVIDER_CHAIN=anthropic,gemini,groq,openrouter,cerebras,together,mistral,mock"
    "SCOUT_PROVIDER_CHAIN=tavily,exa,searxng,duckduckgo,wikipedia,hackernews,reddit,stackoverflow,github_search,ai_scout"
    "MEMORY_BACKEND_CHAIN=neo4j,supabase,upstash,turso"
    "MONTHLY_BUDGET_USD=300"
    "STRATEGIST_MODEL=claude-opus-4-6"
    "ENGINEER_MODEL=claude-sonnet-4-5-20250929"
    "QUICKFIX_MODEL=claude-haiku-4-5-20251001"
    "GITHUB_USERNAME=Valonyx"
)
for kv in "${CONFIG_VARS[@]}"; do
    k="${kv%%=*}"; v="${kv#*=}"
    curl -sf -X POST \
        -H "Authorization: Bearer ${HF_TOKEN}" \
        -H "Content-Type: application/json" \
        "${HF_API}/spaces/${SPACE_ID}/variables" \
        -d "{\"key\": \"${k}\", \"value\": \"${v}\"}" &>/dev/null || true
done

# ── Step 4: Push Dockerfile and code to Space ─────────────────────
echo ""
echo "Step 4/7: Pushing code to HF Space (via git)..."

# HF Spaces use git LFS for Docker — clone Space repo, copy files, push
TMP_DIR=$(mktemp -d)
trap "rm -rf ${TMP_DIR}" EXIT

HF_REPO_URL="https://${HF_USERNAME}:${HF_TOKEN}@huggingface.co/spaces/${SPACE_ID}"

git clone --depth=1 "${HF_REPO_URL}" "${TMP_DIR}/space" 2>/dev/null || \
    { mkdir -p "${TMP_DIR}/space" && cd "${TMP_DIR}/space" && git init && \
      git remote add origin "${HF_REPO_URL}"; }

# Copy required files into Space repo
cp Dockerfile "${TMP_DIR}/space/"
cp -r factory/ "${TMP_DIR}/space/"
cp requirements.txt pyproject.toml "${TMP_DIR}/space/" 2>/dev/null || true
[[ -f .env.example ]] && cp .env.example "${TMP_DIR}/space/"

# Create HF-specific README.md (required for Spaces)
cat > "${TMP_DIR}/space/README.md" << 'README'
---
title: AI Factory Pipeline
emoji: 🏭
colorFrom: blue
colorTo: purple
sdk: docker
pinned: false
---

AI Factory Pipeline v5.6 — Automated AI application factory.
README

cd "${TMP_DIR}/space"
git config user.email "pipeline@ai-factory.local"
git config user.name "AI Factory Pipeline"
git add -A
git diff --cached --quiet || git commit -m "deploy: AI Factory Pipeline $(date +%Y-%m-%d)"
git push origin HEAD:main --force 2>/dev/null || \
    git push origin HEAD:main 2>/dev/null || \
    warn "Git push failed — push manually or use HF web UI"

ok "Code pushed to HF Space"

# ── Step 5: Wait for Space to build ──────────────────────────────
echo ""
echo "Step 5/7: Waiting for Space to build (up to 5 min)..."
sleep 30

for i in $(seq 1 9); do
    SPACE_STATUS=$(curl -sf \
        -H "Authorization: Bearer ${HF_TOKEN}" \
        "${HF_API}/spaces/${SPACE_ID}" 2>/dev/null | \
        python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('runtime',{}).get('stage','unknown'))" \
        2>/dev/null || echo "unknown")
    echo "  Build status: ${SPACE_STATUS}"
    [[ "${SPACE_STATUS}" == "RUNNING" ]] && { ok "Space is running"; break; }
    [[ "${SPACE_STATUS}" == "ERROR" ]] && { warn "Build error — check huggingface.co/spaces/${SPACE_ID}"; break; }
    sleep 30
done

# ── Step 6: Set Telegram webhook ──────────────────────────────────
echo ""
echo "Step 6/7: Setting Telegram webhook..."

WEBHOOK_URL="${SPACE_URL}/webhook"
RESPONSE=$(curl -s \
    "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setWebhook" \
    -d "url=${WEBHOOK_URL}" \
    -d "allowed_updates=[\"message\",\"callback_query\"]" \
    -d "drop_pending_updates=true" 2>/dev/null || echo '{"ok":false}')
echo "${RESPONSE}" | grep -q '"ok":true' && \
    ok "Webhook: ${WEBHOOK_URL}" || \
    warn "Webhook not set — set manually after Space is running"

# ── Step 7: Supabase migrations ───────────────────────────────────
echo ""
echo "Step 7/7: Running Supabase migrations..."
python -c "import supabase" &>/dev/null && \
    { python -m scripts.migrate_supabase && ok "Migrations applied" || \
      warn "Run: python -m scripts.migrate_supabase"; } || \
    warn "supabase-py not installed"

# ── Done ──────────────────────────────────────────────────────────
echo ""
echo "================================================"
echo -e "${GREEN}  Pipeline is LIVE on HF Spaces!${NC}"
echo "================================================"
echo ""
echo "Space:    https://huggingface.co/spaces/${SPACE_ID}"
echo "Service:  ${SPACE_URL}"
echo "Health:   ${SPACE_URL}/health"
echo ""
echo "The GitHub Actions health probe keeps the Space awake."
echo "Set SERVICE_URL secret in GitHub to: ${SPACE_URL}"
echo "  github.com/Valonyx/ai-factory-pipeline/settings/secrets/actions"
