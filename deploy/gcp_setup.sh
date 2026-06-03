#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${PROJECT_ID:-}" ]]; then
  echo "PROJECT_ID is required."
  exit 1
fi

REGION="${REGION:-asia-northeast1}"
SERVICE="${SERVICE:-tabelog-instagram}"
BUCKET="${BUCKET:-${PROJECT_ID}-tabelog-instagram-media}"
REVIEWER_URL="${REVIEWER_URL:-https://tabelog.com/rvwr/018712231/}"

gcloud config set project "${PROJECT_ID}"

gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  cloudscheduler.googleapis.com \
  iamcredentials.googleapis.com \
  secretmanager.googleapis.com \
  storage.googleapis.com

gcloud storage buckets create "gs://${BUCKET}" --location="${REGION}" || true
gcloud storage buckets add-iam-policy-binding "gs://${BUCKET}" \
  --member="allUsers" \
  --role="roles/storage.objectViewer"

IMAGE="gcr.io/${PROJECT_ID}/${SERVICE}:latest"
gcloud builds submit --tag "${IMAGE}"

gcloud run deploy "${SERVICE}" \
  --image "${IMAGE}" \
  --region "${REGION}" \
  --allow-unauthenticated \
  --set-env-vars "TABELOG_REVIEWER_URL=${REVIEWER_URL},STORAGE_BUCKET=${BUCKET},PUBLIC_BASE_URL=https://storage.googleapis.com/${BUCKET},AUTO_PUBLISH_FEED=${AUTO_PUBLISH_FEED:-false},AUTO_PUBLISH_STORY=${AUTO_PUBLISH_STORY:-false},AUTO_PUBLISH_REEL=${AUTO_PUBLISH_REEL:-false}" \
  --set-secrets "IG_USER_ID=ig-user-id:latest,IG_ACCESS_TOKEN=ig-access-token:latest,SYNC_TOKEN=sync-token:latest"

SERVICE_URL="$(gcloud run services describe "${SERVICE}" --region "${REGION}" --format='value(status.url)')"

if gcloud scheduler jobs describe "${SERVICE}-sync" --location "${REGION}" >/dev/null 2>&1; then
  gcloud scheduler jobs update http "${SERVICE}-sync" \
    --location "${REGION}" \
    --schedule "0 * * * *" \
    --uri "${SERVICE_URL}/sync" \
    --http-method POST \
    --headers "X-Sync-Token=${SYNC_TOKEN_VALUE:-CHANGE_ME_IN_CONSOLE}"
else
  gcloud scheduler jobs create http "${SERVICE}-sync" \
    --location "${REGION}" \
    --schedule "0 * * * *" \
    --uri "${SERVICE_URL}/sync" \
    --http-method POST \
    --headers "X-Sync-Token=${SYNC_TOKEN_VALUE:-CHANGE_ME_IN_CONSOLE}"
fi

echo "Service URL: ${SERVICE_URL}"
