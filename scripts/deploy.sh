#!/bin/bash
#
# Deploy catchup-ai to Google Cloud Run with Tailscale
#
# Usage:
#   ./scripts/deploy.sh
#
# Environment variables:
#   PROJECT_ID: GCP project ID (default: catchup-ai-prod)
#   TAILSCALE_IP: RPi5's Tailscale IP (required)
#

set -euo pipefail

# Configuration
PROJECT_ID="${PROJECT_ID:-catchup-ai-prod}"
REGION="asia-northeast1"
SERVICE_NAME="catchup-ai"

# Check required environment variable
if [[ -z "${TAILSCALE_IP:-}" ]]; then
    echo "Error: TAILSCALE_IP environment variable is required"
    echo ""
    echo "Usage: TAILSCALE_IP=100.x.x.x ./scripts/deploy.sh"
    exit 1
fi

echo "=========================================="
echo "  Deploying catchup-ai to Cloud Run"
echo "  with Tailscale sidecar"
echo "=========================================="
echo ""
echo "Project:      ${PROJECT_ID}"
echo "Region:       ${REGION}"
echo "Service:      ${SERVICE_NAME}"
echo "Tailscale IP: ${TAILSCALE_IP}"
echo ""

# Confirm
read -p "Continue? (y/N): " confirm
if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
    echo "Aborted."
    exit 1
fi

echo ""
echo "[1/5] Setting project..."
gcloud config set project "${PROJECT_ID}"

echo ""
echo "[2/5] Creating Artifact Registry (if not exists)..."
gcloud artifacts repositories describe catchup-ai \
    --location="${REGION}" 2>/dev/null || \
gcloud artifacts repositories create catchup-ai \
    --repository-format=docker \
    --location="${REGION}" \
    --description="catchup-ai container images"

echo ""
echo "[3/5] Building and deploying..."
gcloud builds submit \
    --config=cloudbuild.yaml \
    --substitutions="_TAILSCALE_IP=${TAILSCALE_IP}"

echo ""
echo "[4/5] Waiting for service to be ready..."
sleep 10

echo ""
echo "[5/5] Getting service URL..."
SERVICE_URL=$(gcloud run services describe "${SERVICE_NAME}" \
    --region="${REGION}" \
    --format='value(status.url)')

echo ""
echo "=========================================="
echo "  Deployment Complete!"
echo "=========================================="
echo ""
echo "Service URL: ${SERVICE_URL}"
echo ""
echo "Test commands:"
echo ""
echo "  # Health check"
echo "  grpcurl ${SERVICE_URL#https://}:443 grpc.health.v1.Health/Check"
echo ""
echo "  # List services"
echo "  grpcurl ${SERVICE_URL#https://}:443 list"
echo ""
echo "  # EmbedArticle"
echo "  grpcurl -d '{\"article_id\": 1, \"title\": \"test\", \"content\": \"test\"}' \\"
echo "    ${SERVICE_URL#https://}:443 catchup.ai.v1.ArticleAI/EmbedArticle"
echo ""
