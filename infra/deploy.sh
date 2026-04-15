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
  --memory 1Gi \
  --allow-unauthenticated \
  --set-env-vars "GCS_BUCKET=${GCS_BUCKET},FIREBASE_PROJECT_ID=${FIREBASE_PROJECT_ID},VERTEX_PROJECT_ID=${VERTEX_PROJECT_ID:-${GCP_PROJECT_ID}},VERTEX_LOCATION=${VERTEX_LOCATION:-us-central1},LLM_PRIMARY_PROVIDER=${LLM_PRIMARY_PROVIDER:-anthropic},LLM_FALLBACK_PROVIDER=${LLM_FALLBACK_PROVIDER:-vertex},VERTEX_CHAT_MODEL=${VERTEX_CHAT_MODEL:-gemini-2.5-pro},VERTEX_SUMMARY_MODEL=${VERTEX_SUMMARY_MODEL:-gemini-2.5-pro},VERTEX_REWRITE_MODEL=${VERTEX_REWRITE_MODEL:-gemini-2.5-pro},VERTEX_ENRICH_MODEL=${VERTEX_ENRICH_MODEL:-gemini-2.5-pro},VERTEX_RERANK_MODEL=${VERTEX_RERANK_MODEL:-gemini-2.5-pro},VERTEX_EMBEDDING_MODEL=${VERTEX_EMBEDDING_MODEL:-gemini-embedding-001},VERTEX_RANKING_MODEL=${VERTEX_RANKING_MODEL:-semantic-ranker-512@latest},VERTEX_RANKING_CONFIG=${VERTEX_RANKING_CONFIG:-},EMBEDDING_DIMENSIONS=${EMBEDDING_DIMENSIONS:-768},EMBEDDING_MODEL_PROFILE=${EMBEDDING_MODEL_PROFILE:-quality}" \
  --set-secrets "VOYAGE_API_KEY=voyage-api-key:latest,ANTHROPIC_API_KEY=anthropic-api-key:latest,DATABASE_URL=database-url:latest"

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
