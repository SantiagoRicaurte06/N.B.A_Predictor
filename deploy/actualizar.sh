#!/usr/bin/env bash
# Actualiza el VPS a la última versión de main y reconstruye la imagen.
set -euo pipefail
cd "$(dirname "$0")/.."
git pull --ff-only origin main
docker compose up -d --build
docker image prune -f
