#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f .env ] || { echo "ERROR: missing .env (copy real secrets here first)"; exit 1; }
echo "==> pull images"; docker compose pull
echo "==> up";          docker compose up -d
docker compose ps
