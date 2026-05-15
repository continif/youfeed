#!/usr/bin/env bash
# Pulizia retention dei log Apache vhost YOUFEED.
#
# Il vhost (vedi infra/apache/001.youfeed.it.conf) usa `rotatelogs` di
# Apache per creare un file al giorno con nome `access.YYYY-MM-DD.log` e
# `error.YYYY-MM-DD.log`. `rotatelogs` però NON ha retention né
# compressione: senza intervento i file si accumulano per sempre.
#
# Policy:
#   - file più vecchi di KEEP_PLAIN_DAYS (7gg) → gzip in place
#   - .gz più vecchi di KEEP_GZ_DAYS (30gg) → cancellati
#
# Lanciato dal systemd timer yf-log-cleanup.timer (daily 03:15 UTC).
# Manuale:  ./infra/scripts/log-cleanup.sh
# Override: LOG_DIR=/altra/cartella ./infra/scripts/log-cleanup.sh

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LOG_DIR="${LOG_DIR:-$ROOT_DIR/logs}"

KEEP_PLAIN_DAYS="${KEEP_PLAIN_DAYS:-7}"
KEEP_GZ_DAYS="${KEEP_GZ_DAYS:-30}"

if [[ ! -d "$LOG_DIR" ]]; then
    echo "log-cleanup: $LOG_DIR non esiste — niente da fare." >&2
    exit 0
fi

# Compressione: file in chiaro più vecchi di KEEP_PLAIN_DAYS, NON ancora .gz.
# `-not -newer` su un file di riferimento sarebbe più preciso, ma -mtime +N
# (giorni interi) basta per la cadenza quotidiana del job.
gzipped=$(find "$LOG_DIR" -maxdepth 1 -type f \
    \( -name 'access.*.log' -o -name 'error.*.log' \) \
    -mtime +"$KEEP_PLAIN_DAYS" -print -exec gzip -- {} \; | wc -l)

# Cancellazione .gz oltre KEEP_GZ_DAYS
deleted=$(find "$LOG_DIR" -maxdepth 1 -type f \
    \( -name 'access.*.log.gz' -o -name 'error.*.log.gz' \) \
    -mtime +"$KEEP_GZ_DAYS" -print -delete | wc -l)

echo "[$(date -Iseconds)] log-cleanup dir=$LOG_DIR gzipped=$gzipped deleted=$deleted (plain ${KEEP_PLAIN_DAYS}gg / gz ${KEEP_GZ_DAYS}gg)"
