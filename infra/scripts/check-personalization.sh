#!/usr/bin/env bash
# Diagnostica pipeline personalizzazione: dal POST /yf_track del browser fino
# alla riga su activity_log. Risponde a "i dati per la personalizzazione
# stanno entrando e venendo elaborati?".
#
# Catena tracciata:
#   browser → POST /yf_track   → Redis list `yf:activity:queue`
#                              → worker yf-activity-log
#                              → Postgres activity_log
#                              → UPDATE articles.read_count/open_count
#
# Uso:
#   ./infra/scripts/check-personalization.sh           # ultimi 24h
#   ./infra/scripts/check-personalization.sh 1h        # finestra custom (1h, 6h, 7d)

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

set -a
# shellcheck disable=SC1091
source .env
set +a

WINDOW="${1:-24h}"
REDIS_URL_USE="${REDIS_URL:-redis://localhost:6379/0}"
QUEUE_KEY="yf:activity:queue"

# Eventi attesi dal frontend (vedi frontend/src/lib/tracking.ts TrackEventType).
# Quelli marcati DROPPED non sono in routers/track.py ALLOWED_EVENT_TYPES e
# vengono silenziosamente scartati lato server — segnale rosso se trovate 0 righe.
FRONTEND_EVENTS=(
    impression preview_open dwell_5s dwell_15s dwell_60s
    original_open related_click bookmark share search
)

bold() { printf '\033[1m%s\033[0m\n' "$*"; }
dim()  { printf '\033[2m%s\033[0m\n' "$*"; }
ok()   { printf '\033[32m✓\033[0m %s\n' "$*"; }
warn() { printf '\033[33m⚠\033[0m %s\n' "$*"; }
err()  { printf '\033[31m✗\033[0m %s\n' "$*"; }

# ---------- 1. systemd unit ----------------------------------------------------
bold "== yf-activity-log.service =="
if command -v systemctl >/dev/null 2>&1; then
    if systemctl list-unit-files yf-activity-log.service >/dev/null 2>&1; then
        state="$(systemctl is-active yf-activity-log.service 2>/dev/null || true)"
        case "$state" in
            active) ok "active" ;;
            *)      err "stato: $state" ;;
        esac
        dim "  ultimi errori (10 righe):"
        journalctl -u yf-activity-log.service --since "-${WINDOW}" \
            --no-pager --priority=warning -n 10 2>/dev/null \
            | sed 's/^/    /' || true
    else
        warn "unit non installata (ok in dev locale)"
    fi
else
    warn "systemctl non disponibile"
fi
echo

# ---------- 2. Redis: profondità coda -----------------------------------------
bold "== Redis queue $QUEUE_KEY =="
if command -v redis-cli >/dev/null 2>&1; then
    qlen="$(redis-cli -u "$REDIS_URL_USE" LLEN "$QUEUE_KEY" 2>/dev/null || echo "ERR")"
    case "$qlen" in
        ERR)     err  "redis-cli fallito (controlla REDIS_URL=$REDIS_URL_USE)" ;;
        0)       ok   "coda vuota (worker sta drenando in tempo reale)" ;;
        [0-9]*)
            if [ "$qlen" -lt 100 ]; then
                ok   "len=$qlen (worker non in ritardo)"
            elif [ "$qlen" -lt 5000 ]; then
                warn "len=$qlen (worker in ritardo lieve)"
            else
                err  "len=$qlen (worker bloccato o lento — controlla journalctl)"
            fi
            ;;
    esac
    # Sneak peek dell'ultimo evento accodato (non distruttivo: LINDEX, non POP)
    last="$(redis-cli -u "$REDIS_URL_USE" LINDEX "$QUEUE_KEY" 0 2>/dev/null || true)"
    if [ -n "$last" ]; then
        dim "  ultimo evento accodato:"
        echo "    $last" | head -c 400
        echo
    fi
else
    warn "redis-cli non installato"
fi
echo

# ---------- 3. Postgres: activity_log -----------------------------------------
bold "== Postgres activity_log (finestra: $WINDOW) =="
if [ -z "${DATABASE_URL_SYNC:-}" ]; then
    err "DATABASE_URL_SYNC non impostato in .env"
    exit 1
fi

# psql --tuples-only --no-align: output pulito. Usiamo TO_CHAR per leggibilità.
psql_q() {
    psql "$DATABASE_URL_SYNC" --quiet --no-psqlrc -P pager=off "$@"
}

# 3a. Freshness: timestamp dell'ultima riga.
dim "Freshness:"
psql_q -c "
    SELECT
        MAX(ts)             AS ultimo_evento,
        NOW() - MAX(ts)     AS lag,
        COUNT(*)            AS totale_finestra
    FROM activity_log
    WHERE ts > NOW() - INTERVAL '$WINDOW';
" 2>&1 | sed 's/^/  /'

# 3b. Breakdown per event_type (tutti, anche quelli non attesi).
dim "Breakdown per event_type:"
psql_q -c "
    SELECT
        event_type,
        COUNT(*)                                   AS rows,
        COUNT(DISTINCT user_id) FILTER (WHERE user_id IS NOT NULL)
                                                   AS distinct_user,
        COUNT(DISTINCT fingerprint) FILTER (WHERE fingerprint IS NOT NULL)
                                                   AS distinct_fp,
        MAX(ts)                                    AS ultimo
    FROM activity_log
    WHERE ts > NOW() - INTERVAL '$WINDOW'
    GROUP BY event_type
    ORDER BY rows DESC;
" 2>&1 | sed 's/^/  /'

# 3c. Sanity check eventi attesi dal frontend (vedi commento sopra).
dim "Eventi attesi dal frontend nella finestra:"
for ev in "${FRONTEND_EVENTS[@]}"; do
    n=$(psql_q -tA -c "
        SELECT COUNT(*) FROM activity_log
        WHERE ts > NOW() - INTERVAL '$WINDOW' AND event_type = '$ev';
    " 2>/dev/null | tr -d '[:space:]')
    if [ "${n:-0}" -gt 0 ]; then
        printf '    %-16s %6d\n' "$ev" "$n"
    else
        printf '    %-16s %6d  (assente)\n' "$ev" "${n:-0}"
    fi
done

# 3d. Eventi che muovono i contatori articles (click/open).
dim "Top articoli con read_count > 0 (ultime 24h da last_read_at):"
psql_q -c "
    SELECT
        a.id,
        a.read_count,
        a.open_count,
        a.last_read_at,
        LEFT(a.title, 60) AS titolo
    FROM articles a
    WHERE a.last_read_at > NOW() - INTERVAL '24 hours'
    ORDER BY a.last_read_at DESC
    LIMIT 10;
" 2>&1 | sed 's/^/  /'

# 3e. Coverage signals personalizzazione: quanti utenti distinti hanno
# accumulato segnali utili (un proxy di "fase di apprendimento").
dim "Coverage personalizzazione (signal-bearing events per utente, finestra):"
psql_q -c "
    WITH per_user AS (
        SELECT
            COALESCE(user_id::text, 'fp:' || fingerprint) AS who,
            COUNT(*) FILTER (WHERE event_type IN ('preview_open','click'))    AS previews,
            COUNT(*) FILTER (WHERE event_type IN ('original_open','open'))    AS originals,
            COUNT(*) FILTER (WHERE event_type = 'related_click')              AS related,
            COUNT(*) FILTER (WHERE event_type = 'bookmark')                   AS bookmarks
        FROM activity_log
        WHERE ts > NOW() - INTERVAL '$WINDOW'
          AND (user_id IS NOT NULL OR fingerprint IS NOT NULL)
        GROUP BY 1
    )
    SELECT
        COUNT(*) FILTER (WHERE previews + originals + related + bookmarks > 0)
            AS utenti_con_segnali,
        COUNT(*) FILTER (WHERE previews + originals + related + bookmarks >= 5)
            AS utenti_5plus_segnali,
        SUM(previews)      AS tot_previews,
        SUM(originals)     AS tot_originals,
        SUM(related)       AS tot_related,
        SUM(bookmarks)     AS tot_bookmarks
    FROM per_user;
" 2>&1 | sed 's/^/  /'

# 3f. Errori del worker nella finestra.
dim "Errori worker (journalctl, max 5):"
if command -v journalctl >/dev/null 2>&1; then
    journalctl -u yf-activity-log.service --since "-${WINDOW}" \
        --no-pager --priority=err -n 5 2>/dev/null \
        | sed 's/^/  /' || true
fi

echo
bold "== Note =="
cat <<'EOF'
- Se "preview_open / original_open / related_click / bookmark / dwell_5s|15s|60s"
  restano sempre a 0 mentre "impression / share" salgono → backend sta scartando
  quegli event_type. Vedi backend/app/routers/track.py:28 (ALLOWED_EVENT_TYPES).
- Se la coda Redis cresce e non scende → worker fermo: controlla
  `sudo systemctl status yf-activity-log` e gli errori sopra.
- Se "freshness lag" supera 1-2 minuti con coda vuota → o non c'è traffico,
  o le richieste non passano dall'app FastAPI (es. cache Apache 200 da disk).
EOF
