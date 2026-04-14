#!/usr/bin/env bash
# One-click deploy to Google Cloud Run
set -euo pipefail

PROJECT_ID="${GCP_PROJECT_ID:?Set GCP_PROJECT_ID}"
REGION="${GCP_REGION:-us-central1}"
BACKEND_IMAGE="gcr.io/${PROJECT_ID}/rag-backend:latest"
FRONTEND_IMAGE="gcr.io/${PROJECT_ID}/rag-frontend:latest"

echo "==> Building and pushing backend..."
docker build -t "${BACKEND_IMAGE}" ./backend
docker push "${BACKEND_IMAGE}"

echo "==> Deploying backend to Cloud Run..."
gcloud run deploy rag-backend \
  --image "${BACKEND_IMAGE}" \
  --region "${REGION}" \
  --platform managed \
  --min-instances 1 \
  --allow-unauthenticated \
  --set-env-vars "GCS_BUCKET=${GCS_BUCKET},FIREBASE_PROJECT_ID=${FIREBASE_PROJECT_ID}" \
  --set-secrets "VOYAGE_API_KEY=voyage-api-key:latest,COHERE_API_KEY=cohere-api-key:latest,ANTHROPIC_API_KEY=anthropic-api-key:latest,DATABASE_URL=database-url:latest"

echo "==> Building and pushing frontend..."
docker build -t "${FRONTEND_IMAGE}" ./frontend
docker push "${FRONTEND_IMAGE}"

echo "==> Deploying frontend to Cloud Run..."
gcloud run deploy rag-frontend \
  --image "${FRONTEND_IMAGE}" \
  --region "${REGION}" \
  --platform managed \
  --min-instances 1 \
  --allow-unauthenticated \
  --set-env-vars "NEXT_PUBLIC_API_URL=${BACKEND_URL},NEXT_PUBLIC_FIREBASE_PROJECT_ID=${FIREBASE_PROJECT_ID}"

echo "==> Deploy complete."
