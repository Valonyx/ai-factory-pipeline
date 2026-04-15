#!/usr/bin/env bash
# AI Factory Pipeline v5.8 — GCS Artifact Bucket Setup
#
# Creates a Google Cloud Storage bucket for storing build artifacts
# (APKs, AABs, IPAs, Docker images) produced by the pipeline.
#
# Usage:
#   ./scripts/create_artifact_bucket.sh
#   GCP_PROJECT=my-project ./scripts/create_artifact_bucket.sh
#
# Prerequisites:
#   - gcloud CLI installed and authenticated (gcloud auth login)
#   - GCP_PROJECT env var set, or a gcloud default project
#
# Spec Authority: v5.8 §4.5 Build Artifacts

set -euo pipefail

# ── Configuration ────────────────────────────────────────────────────
GCP_PROJECT="${GCP_PROJECT:-$(gcloud config get-value project 2>/dev/null || echo "")}"
REGION="${GCP_REGION:-me-central1}"
BUCKET_NAME="${ARTIFACT_BUCKET:-ai-factory-artifacts-${GCP_PROJECT}}"
LIFECYCLE_DAYS="${ARTIFACT_RETENTION_DAYS:-90}"

if [[ -z "${GCP_PROJECT}" ]]; then
    echo "ERROR: GCP_PROJECT not set and no gcloud default project configured."
    echo "Set it with: export GCP_PROJECT=your-project-id"
    exit 1
fi

echo "=== AI Factory Pipeline — Artifact Bucket Setup ==="
echo "Project:   ${GCP_PROJECT}"
echo "Region:    ${REGION}"
echo "Bucket:    gs://${BUCKET_NAME}"
echo "Retention: ${LIFECYCLE_DAYS} days"
echo ""

# ── Create bucket if it doesn't exist ────────────────────────────────
if gsutil ls "gs://${BUCKET_NAME}" &>/dev/null; then
    echo "✓ Bucket already exists: gs://${BUCKET_NAME}"
else
    echo "Creating bucket gs://${BUCKET_NAME} ..."
    gsutil mb -p "${GCP_PROJECT}" -l "${REGION}" -b on "gs://${BUCKET_NAME}"
    echo "✓ Bucket created"
fi

# ── Set uniform bucket-level access ─────────────────────────────────
echo "Enabling uniform bucket-level access..."
gsutil uniformbucketlevelaccess set on "gs://${BUCKET_NAME}" 2>/dev/null || true

# ── Set lifecycle (auto-delete after N days) ─────────────────────────
LIFECYCLE_JSON=$(cat <<EOF
{
  "rule": [
    {
      "action": {"type": "Delete"},
      "condition": {"age": ${LIFECYCLE_DAYS}}
    }
  ]
}
EOF
)
echo "${LIFECYCLE_JSON}" | gsutil lifecycle set /dev/stdin "gs://${BUCKET_NAME}"
echo "✓ Lifecycle set: delete after ${LIFECYCLE_DAYS} days"

# ── Create folder structure ───────────────────────────────────────────
for folder in android ios web docker; do
    echo -n "" | gsutil cp - "gs://${BUCKET_NAME}/${folder}/.keep" 2>/dev/null || true
done
echo "✓ Folder structure created: android/, ios/, web/, docker/"

# ── Update .env ───────────────────────────────────────────────────────
if [[ -f ".env" ]]; then
    if grep -q "^ARTIFACT_BUCKET=" .env; then
        sed -i.bak "s|^ARTIFACT_BUCKET=.*|ARTIFACT_BUCKET=${BUCKET_NAME}|" .env
    else
        echo "" >> .env
        echo "ARTIFACT_BUCKET=${BUCKET_NAME}" >> .env
    fi
    echo "✓ ARTIFACT_BUCKET set in .env"
fi

echo ""
echo "=== Setup complete ==="
echo "Artifact bucket: gs://${BUCKET_NAME}"
echo "Add to .env:"
echo "  ARTIFACT_BUCKET=${BUCKET_NAME}"
echo "  GCP_PROJECT=${GCP_PROJECT}"
