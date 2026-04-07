#!/usr/bin/env bash
# AI Factory Pipeline v5.6 — Cloud Scheduler Setup
#
# Creates Cloud Scheduler jobs for:
#   1. Janitor Agent    — every 6 hours (purge expired artifacts + Neo4j nodes)
#   2. Health probe     — every 5 minutes (uptime monitoring)
#
# Usage:
#   ./scripts/setup_cloud_scheduler.sh
#   SERVICE_URL=https://my-service.run.app ./scripts/setup_cloud_scheduler.sh
#
# Prerequisites:
#   - gcloud CLI installed and authenticated
#   - Cloud Run service already deployed
#   - GCP_PROJECT set or gcloud default project configured
#
# Spec Authority: v5.6 §2.10.2 (Janitor), §7.4.1 (Health)

set -euo pipefail

GCP_PROJECT="${GCP_PROJECT:-$(gcloud config get-value project 2>/dev/null)}"
REGION="${GCP_REGION:-me-central1}"
SERVICE_NAME="${CLOUD_RUN_SERVICE:-ai-factory-pipeline}"
SERVICE_URL="${SERVICE_URL:-}"

if [[ -z "${GCP_PROJECT}" ]]; then
    echo "ERROR: GCP_PROJECT not set."
    exit 1
fi

# Auto-detect service URL if not provided
if [[ -z "${SERVICE_URL}" ]]; then
    echo "Detecting Cloud Run service URL..."
    SERVICE_URL=$(gcloud run services describe "${SERVICE_NAME}" \
        --region="${REGION}" \
        --project="${GCP_PROJECT}" \
        --format="value(status.url)" 2>/dev/null || echo "")
fi

if [[ -z "${SERVICE_URL}" ]]; then
    echo "ERROR: Could not detect service URL."
    echo "Set SERVICE_URL=https://your-service.run.app and re-run."
    exit 1
fi

echo "=== AI Factory Pipeline — Cloud Scheduler Setup ==="
echo "Project:     ${GCP_PROJECT}"
echo "Region:      ${REGION}"
echo "Service URL: ${SERVICE_URL}"
echo ""

# ── Enable Cloud Scheduler API ────────────────────────────────────
echo "Enabling Cloud Scheduler API..."
gcloud services enable cloudscheduler.googleapis.com \
    --project="${GCP_PROJECT}" --quiet

# ── Get the Cloud Run service account ─────────────────────────────
SA_EMAIL=$(gcloud run services describe "${SERVICE_NAME}" \
    --region="${REGION}" \
    --project="${GCP_PROJECT}" \
    --format="value(spec.template.spec.serviceAccountName)" 2>/dev/null || echo "")

if [[ -z "${SA_EMAIL}" ]]; then
    SA_EMAIL="${GCP_PROJECT}@appspot.gserviceaccount.com"
    echo "Using default service account: ${SA_EMAIL}"
fi

# ── Job 1: Janitor Agent (every 6 hours) ──────────────────────────
echo ""
echo "Creating Janitor Agent job (every 6 hours)..."

gcloud scheduler jobs describe ai-factory-janitor \
    --location="${REGION}" \
    --project="${GCP_PROJECT}" &>/dev/null && \
    gcloud scheduler jobs delete ai-factory-janitor \
        --location="${REGION}" \
        --project="${GCP_PROJECT}" --quiet 2>/dev/null || true

gcloud scheduler jobs create http ai-factory-janitor \
    --location="${REGION}" \
    --project="${GCP_PROJECT}" \
    --schedule="0 */6 * * *" \
    --uri="${SERVICE_URL}/janitor" \
    --http-method=POST \
    --oidc-service-account-email="${SA_EMAIL}" \
    --oidc-token-audience="${SERVICE_URL}" \
    --time-zone="Asia/Riyadh" \
    --description="AI Factory Janitor Agent — purge expired artifacts every 6h" \
    --attempt-deadline="300s"

echo "✓ Janitor job created: 0 */6 * * * (every 6 hours, Riyadh time)"

# ── Job 2: Health Probe (every 5 minutes) ─────────────────────────
echo ""
echo "Creating health probe job (every 5 minutes)..."

gcloud scheduler jobs describe ai-factory-health \
    --location="${REGION}" \
    --project="${GCP_PROJECT}" &>/dev/null && \
    gcloud scheduler jobs delete ai-factory-health \
        --location="${REGION}" \
        --project="${GCP_PROJECT}" --quiet 2>/dev/null || true

gcloud scheduler jobs create http ai-factory-health \
    --location="${REGION}" \
    --project="${GCP_PROJECT}" \
    --schedule="*/5 * * * *" \
    --uri="${SERVICE_URL}/health" \
    --http-method=GET \
    --oidc-service-account-email="${SA_EMAIL}" \
    --oidc-token-audience="${SERVICE_URL}" \
    --time-zone="UTC" \
    --description="AI Factory health probe — every 5 minutes" \
    --attempt-deadline="30s"

echo "✓ Health probe created: */5 * * * * (every 5 minutes)"

# ── Summary ───────────────────────────────────────────────────────
echo ""
echo "=== Cloud Scheduler setup complete ==="
echo ""
echo "Active jobs:"
gcloud scheduler jobs list \
    --location="${REGION}" \
    --project="${GCP_PROJECT}" \
    --format="table(name,schedule,state)" 2>/dev/null || true

echo ""
echo "Test janitor manually:"
echo "  gcloud scheduler jobs run ai-factory-janitor --location=${REGION}"
