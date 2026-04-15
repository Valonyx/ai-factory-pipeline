#!/usr/bin/env bash
# AI Factory Pipeline v5.8 — GitHub Container Registry (GHCR) Activation
#
# What this does:
#   1. Verify GITHUB_TOKEN has packages scope
#   2. Authenticate Docker with ghcr.io
#   3. Build the Docker image
#   4. Push :latest and :sha-<git> tags to ghcr.io
#   5. Make the package public (so Koyeb / any platform can pull it)
#   6. Verify pull works
#
# Run ONCE to activate, then CI (docker-build.yml) keeps it updated.
#
# Prerequisites:
#   - Docker running
#   - GITHUB_TOKEN in .env (needs write:packages scope)
#     Classic PAT: check "write:packages" at github.com/settings/tokens
#     Fine-grained PAT: check "Read and Write" under Repository > Packages
#
# Usage:
#   ./scripts/setup_ghcr.sh

set -euo pipefail

ENV_FILE="${ENV_FILE:-.env}"
GHCR_USER="valonyx"
GHCR_REPO="ai-factory-pipeline"
GHCR_IMAGE="ghcr.io/${GHCR_USER}/${GHCR_REPO}"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✓${NC} $*"; }
warn() { echo -e "${YELLOW}⚠${NC} $*"; }
err()  { echo -e "${RED}✗${NC} $*"; exit 1; }
info() { echo -e "${BLUE}→${NC} $*"; }

echo "================================================"
echo "  GHCR Activation — GitHub Container Registry"
echo "================================================"
echo ""

# ── Load .env ─────────────────────────────────────────────────────
[[ -f "${ENV_FILE}" ]] && { set -a; source "${ENV_FILE}"; set +a; }
GITHUB_TOKEN="${GITHUB_TOKEN:-}"
[[ -z "${GITHUB_TOKEN}" ]] && err "GITHUB_TOKEN not set in .env"

# ── Step 1: Verify token has packages scope ───────────────────────
echo "Step 1: Verifying GITHUB_TOKEN packages scope..."

SCOPES=$(curl -s -I \
    -H "Authorization: Bearer ${GITHUB_TOKEN}" \
    "https://api.github.com/user" 2>/dev/null | \
    grep -i "x-oauth-scopes:" | tr -d '\r' | sed 's/x-oauth-scopes: //')

if [[ -z "${SCOPES}" ]]; then
    warn "Could not verify token scopes (token may be fine-grained PAT — continuing)"
elif echo "${SCOPES}" | grep -q "write:packages\|repo"; then
    ok "Token has packages scope: ${SCOPES}"
else
    echo ""
    echo -e "${RED}Token is missing write:packages scope.${NC}"
    echo ""
    echo "To fix — go to: https://github.com/settings/tokens"
    echo "  Classic PAT: check 'write:packages' and 'read:packages'"
    echo "  Fine-grained PAT: Repository > Packages > Read and Write"
    echo ""
    echo "Then update GITHUB_TOKEN= in your .env and re-run."
    exit 1
fi

# ── Step 2: Authenticate Docker with ghcr.io ──────────────────────
echo ""
echo "Step 2: Authenticating Docker with ghcr.io..."

echo "${GITHUB_TOKEN}" | docker login ghcr.io \
    -u "${GHCR_USER}" \
    --password-stdin 2>/dev/null
ok "Authenticated with ghcr.io as ${GHCR_USER}"

# ── Step 3: Build Docker image ────────────────────────────────────
echo ""
echo "Step 3: Building Docker image..."

GIT_SHA=$(git rev-parse --short HEAD 2>/dev/null || echo "init")
SHA_TAG="${GHCR_IMAGE}:sha-${GIT_SHA}"
LATEST_TAG="${GHCR_IMAGE}:latest"

docker build \
    -t "${SHA_TAG}" \
    -t "${LATEST_TAG}" \
    --label "org.opencontainers.image.source=https://github.com/${GHCR_USER}/${GHCR_REPO}" \
    --label "org.opencontainers.image.revision=${GIT_SHA}" \
    . 2>&1 | tail -5
ok "Image built: ${LATEST_TAG}"

# ── Step 4: Push to GHCR ──────────────────────────────────────────
echo ""
echo "Step 4: Pushing to ghcr.io..."

docker push "${SHA_TAG}" --quiet
docker push "${LATEST_TAG}" --quiet
ok "Pushed: ${LATEST_TAG}"
ok "Pushed: ${SHA_TAG}"

# ── Step 5: Make package public ───────────────────────────────────
echo ""
echo "Step 5: Setting package visibility to public..."

# GHCR packages are private by default. Making them public lets Koyeb
# and any other platform pull without authentication.
PATCH_RESP=$(curl -s -w "\n%{http_code}" \
    -X PATCH \
    -H "Authorization: Bearer ${GITHUB_TOKEN}" \
    -H "Accept: application/vnd.github+json" \
    -H "X-GitHub-Api-Version: 2022-11-28" \
    "https://api.github.com/user/packages/container/${GHCR_REPO}" \
    -d '{"visibility":"public"}' 2>/dev/null)

HTTP_CODE=$(echo "${PATCH_RESP}" | tail -1)
BODY=$(echo "${PATCH_RESP}" | head -1)

if [[ "${HTTP_CODE}" == "200" ]]; then
    ok "Package visibility set to public"
elif [[ "${HTTP_CODE}" == "404" ]]; then
    # Package may not exist yet as a user package (might be org package)
    # Try org endpoint
    ORG_RESP=$(curl -s -w "\n%{http_code}" \
        -X PATCH \
        -H "Authorization: Bearer ${GITHUB_TOKEN}" \
        -H "Accept: application/vnd.github+json" \
        "https://api.github.com/orgs/${GHCR_USER}/packages/container/${GHCR_REPO}" \
        -d '{"visibility":"public"}' 2>/dev/null)
    HTTP_CODE2=$(echo "${ORG_RESP}" | tail -1)
    if [[ "${HTTP_CODE2}" == "200" ]]; then
        ok "Package visibility set to public (org)"
    else
        warn "Could not set visibility via API (HTTP ${HTTP_CODE}/${HTTP_CODE2})"
        warn "Set manually: github.com/users/${GHCR_USER}/packages/container/${GHCR_REPO}"
        warn "  → Package settings → Change visibility → Public"
    fi
elif [[ "${HTTP_CODE}" == "401" || "${HTTP_CODE}" == "403" ]]; then
    warn "Token lacks permission to change package visibility (HTTP ${HTTP_CODE})"
    warn "Set manually: github.com/users/${GHCR_USER}/packages/container/${GHCR_REPO}"
    warn "  → Package settings → Change visibility → Public"
else
    warn "Unexpected response HTTP ${HTTP_CODE}: ${BODY}"
    warn "Set visibility manually if needed."
fi

# ── Step 6: Verify pull ───────────────────────────────────────────
echo ""
echo "Step 6: Verifying pull..."

docker pull "${LATEST_TAG}" --quiet 2>/dev/null && \
    ok "Pull verified: ${LATEST_TAG}" || \
    warn "Pull verification failed (may still be propagating — try again in 30s)"

# ── Done ──────────────────────────────────────────────────────────
echo ""
echo "================================================"
echo -e "${GREEN}  GHCR activated!${NC}"
echo "================================================"
echo ""
echo "Image: ${LATEST_TAG}"
echo ""
echo "CI keeps it updated automatically:"
echo "  Every push to main → docker-build.yml → push to GHCR"
echo ""
echo "To manually rebuild and push:"
echo "  ./scripts/setup_ghcr.sh"
echo ""
echo "Next step — deploy to Koyeb (free, no CC):"
echo "  ./scripts/deploy_koyeb.sh"
