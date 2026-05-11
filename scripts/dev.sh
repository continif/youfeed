#!/usr/bin/env bash
# Avvia tutti i processi di sviluppo YOUFEED:
#   - backend FastAPI (uvicorn :8000, --reload)
#   - frontend Vite (:5173)
#   - scheduler ingestion (tick loop)
#   - activity_log drainer
#   - worker RQ (uno per coda)
#
# Servizi di sistema (Postgres/Redis/Manticore) NON sono gestiti qui:
# devono già essere attivi via systemd. Lo script verifica che lo siano.
#
# Log: logs/dev/<componente>.log
# Stop: CTRL+C → trap → killa tutti i figli + cleanup PID file.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$REPO_ROOT/.venv"
LOG_DIR="$REPO_ROOT/logs/dev"
PID_DIR="$REPO_ROOT/logs/dev/pids"

mkdir -p "$LOG_DIR" "$PID_DIR"

# Code RQ da avviare in dev. Commenta quelle che non ti servono.
QUEUES=(
    discover
    fetch_rss
    fetch_wp
    process_article
    image_processor
    email
)

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

c_red()    { printf "\033[31m%s\033[0m" "$*"; }
c_green()  { printf "\033[32m%s\033[0m" "$*"; }
c_yellow() { printf "\033[33m%s\033[0m" "$*"; }
c_dim()    { printf "\033[2m%s\033[0m" "$*"; }

PIDS=()

start() {
    # start <name> <workdir> <cmd...>
    local name="$1"; shift
    local workdir="$1"; shift
    local logfile="$LOG_DIR/$name.log"
    local pidfile="$PID_DIR/$name.pid"
    (
        cd "$workdir"
        exec "$@"
    ) >"$logfile" 2>&1 &
    local pid=$!
    echo "$pid" > "$pidfile"
    PIDS+=("$pid:$name")
    printf "  %s  pid=%s  log=%s\n" "$(c_green "✓ $name")" "$pid" "$(c_dim "$logfile")"
}

cleanup() {
    echo
    echo "$(c_yellow '↩ stop:')  invio SIGTERM ai processi…"
    for entry in "${PIDS[@]}"; do
        local pid="${entry%%:*}"
        local name="${entry##*:}"
        if kill -0 "$pid" 2>/dev/null; then
            kill -TERM "$pid" 2>/dev/null || true
            printf "  %s  pid=%s\n" "$(c_dim "→ $name")" "$pid"
        fi
    done
    sleep 1
    # SIGKILL ai sopravvissuti
    for entry in "${PIDS[@]}"; do
        local pid="${entry%%:*}"
        if kill -0 "$pid" 2>/dev/null; then
            kill -KILL "$pid" 2>/dev/null || true
        fi
    done
    rm -f "$PID_DIR"/*.pid
    echo "$(c_green '✓ stop completato.')"
    exit 0
}
trap cleanup INT TERM

# ---------------------------------------------------------------------------
# Pre-flight
# ---------------------------------------------------------------------------

echo "$(c_yellow '▸ pre-flight checks')"

if [[ ! -d "$VENV" ]]; then
    echo "$(c_red '✗ venv non trovato:') $VENV"
    echo "  crea con: python3 -m venv .venv && .venv/bin/pip install -e backend"
    exit 1
fi

# attiva venv (per rq + uvicorn nel PATH)
# shellcheck disable=SC1091
source "$VENV/bin/activate"

for svc in postgresql@16-main redis-server manticore; do
    if systemctl is-active --quiet "$svc"; then
        printf "  %s  %s\n" "$(c_green '✓')" "$svc"
    else
        printf "  %s  %s  (avvialo con: sudo systemctl start %s)\n" \
            "$(c_red '✗')" "$svc" "$svc"
        exit 1
    fi
done

if [[ ! -d "$REPO_ROOT/frontend/node_modules" ]]; then
    echo "$(c_yellow '⚠ frontend/node_modules mancante: lancio npm install')"
    (cd "$REPO_ROOT/frontend" && npm install)
fi

# Alembic migrations: applica head se ci sono migrazioni pendenti.
echo "$(c_yellow '▸ alembic upgrade head')"
(cd "$REPO_ROOT/backend" && alembic upgrade head) | sed 's/^/  /'

# ---------------------------------------------------------------------------
# Avvio
# ---------------------------------------------------------------------------

echo
echo "$(c_yellow '▸ start processi')"

# Backend FastAPI
start "uvicorn" "$REPO_ROOT/backend" \
    uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Frontend Vite
start "vite" "$REPO_ROOT/frontend" \
    npm run dev

# Scheduler ingestion
start "scheduler" "$REPO_ROOT/backend" \
    python -m app.workers.scheduler --tick 60 --batch 50

# Activity log drainer
start "activity_log" "$REPO_ROOT/backend" \
    python -m app.workers.activity_log

# RQ workers (uno per coda)
RQ_REDIS_URL="${RQ_REDIS_URL:-redis://localhost:6379/1}"
for q in "${QUEUES[@]}"; do
    start "rq-$q" "$REPO_ROOT/backend" \
        rq worker --url "$RQ_REDIS_URL" "$q"
done

# ---------------------------------------------------------------------------
# Pronto
# ---------------------------------------------------------------------------

cat <<EOF

$(c_green '▸ tutto avviato')
  backend   →  http://localhost:8000   (admin: /yf_admin)
  frontend  →  http://localhost:5173

  log:      tail -f $LOG_DIR/<name>.log
  multi:    tail -f $LOG_DIR/*.log

$(c_dim 'CTRL+C per terminare tutti i processi.')
EOF

# Aspetta i processi figli; il trap su INT fa il cleanup.
wait
