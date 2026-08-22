#!/usr/bin/env bash
# Deploy icbu-listing to https://icbu-listing.vercel.app (Vercel production).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [ -z "${VERCEL_TOKEN:-}" ]; then
  echo "VERCEL_TOKEN is required" >&2
  exit 1
fi

echo "Deploying from $(pwd) …"
npx vercel@59 deploy --prod --token "$VERCEL_TOKEN" --yes

echo "Waiting for health …"
for _ in $(seq 1 20); do
  if curl -fsS "https://icbu-listing.vercel.app/api/v1/health" >/dev/null; then
    curl -fsS "https://icbu-listing.vercel.app/api/v1/health"
    echo
    exit 0
  fi
  sleep 5
done

echo "Deploy finished but health check timed out" >&2
exit 1
