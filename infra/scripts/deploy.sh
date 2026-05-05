#!/usr/bin/env bash
# Deploy YOUFEED via git pull. Da eseguire come utente "youfeed" sul server.
# Niente CI/CD: questo è il flusso completo.
#
# Uso: cd /opt/youfeed && ./infra/scripts/deploy.sh

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

log() {
    echo "[$(date +'%Y-%m-%dT%H:%M:%S%z')] $*"
}

# 1. Pull
log "Pulling latest from main..."
git fetch origin main
git checkout main
git reset --hard origin/main

# 2. Backend deps
log "Installing backend deps..."
.venv/bin/pip install -e backend --upgrade

# 3. Migrazioni DB
log "Running Alembic migrations..."
.venv/bin/alembic -c backend/alembic.ini upgrade head

# 4. Frontend build
log "Building frontend..."
cd frontend
npm ci --no-audit --no-fund
npm run build
cd ..

# 5. Restart servizi
log "Restarting systemd services..."
sudo systemctl restart yf-api yf-scheduler
# I worker RQ sono safe da restartare in qualsiasi momento (job idempotenti)
sudo systemctl restart 'yf-worker@*'

log "Deploy completato."
