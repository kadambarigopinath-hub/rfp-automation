#!/usr/bin/env bash
# Phase 1 scaffold: local infra for RFP Automation platform
# Run from the project root: ./scripts/setup.sh

set -e

echo "== 1. Checking prerequisites =="
command -v docker >/dev/null 2>&1 || { echo "Docker is required. Install it first."; exit 1; }
command -v docker compose >/dev/null 2>&1 || { echo "Docker Compose plugin is required."; exit 1; }

echo "== 2. Creating project folder structure =="
mkdir -p backend/app/{api,models,skills,rag,agents}
mkdir -p backend/alembic
mkdir -p frontend
mkdir -p scripts

echo "== 3. Copying .env template (edit before production use) =="
if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from .env.example — edit secrets before real use."
fi

echo "== 4. Starting Postgres (with pgvector), MinIO, Redis =="
docker compose up -d postgres minio redis

echo "== 5. Waiting for Postgres to be ready =="
until docker exec rfp_postgres pg_isready -U rfp_admin >/dev/null 2>&1; do
  sleep 1
done
echo "Postgres is up. Schema (db/schema.sql) is auto-applied on first container init."

echo "== 6. Creating MinIO buckets =="
if command -v mc >/dev/null 2>&1; then
  mc alias set local http://localhost:9000 rfp_admin change_me_locally
  mc mb -p local/kb-permanent
  mc mb -p local/staging
  mc mb -p local/rfp-permanent
  mc mb -p local/rfp-tmp
  echo "Buckets created: kb-permanent, staging, rfp-permanent, rfp-tmp"
else
  echo "mc (MinIO client) not found — install it, then run:"
  echo "  mc alias set local http://localhost:9000 rfp_admin change_me_locally"
  echo "  mc mb local/kb-permanent local/staging local/rfp-permanent local/rfp-tmp"
fi

echo "== Done =="
echo "Postgres:   localhost:5432 (db: rfp_automation)"
echo "MinIO API:  localhost:9000  (console: localhost:9001)"
echo "Redis:      localhost:6379"
echo ""
echo "Next: scaffold the FastAPI backend in backend/ with Claude Code, wiring it to"
echo "DATABASE_URL / S3_* / REDIS_URL / ANTHROPIC_API_KEY from .env"
