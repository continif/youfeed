#!/usr/bin/env bash
# Backup notturno: pg_dump + Manticore BACKUP + tar delle immagini delta.
# Da schedulare via cron. Destinazione: TBD (rsync offsite, S3, ...).

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

set -a
# shellcheck disable=SC1091
source .env
set +a

BACKUP_DIR="${BACKUP_DIR:-/var/backups/youfeed}"
TS="$(date +'%Y%m%d-%H%M%S')"
DEST="${BACKUP_DIR}/${TS}"
mkdir -p "$DEST"

echo "[+] Backup Postgres..."
pg_dump --format=custom --no-owner --no-privileges \
    --file="${DEST}/postgres.dump" \
    "${DATABASE_URL_SYNC}"

echo "[+] Backup Manticore..."
mysql -h "${MANTICORE_HOST:-127.0.0.1}" -P "${MANTICORE_PORT:-9306}" \
    -e "BACKUP TABLE articles_rt TO '${DEST}/manticore'"

echo "[+] Backup immagini (rsync incrementale)..."
rsync -a --link-dest="${BACKUP_DIR}/latest/images" \
    "${IMAGES_DIR:-/var/lib/youfeed/images}/" "${DEST}/images/"

# Aggiorna symlink "latest"
ln -sfn "$DEST" "${BACKUP_DIR}/latest"

# Retention locale: drop > 14 giorni
find "$BACKUP_DIR" -mindepth 1 -maxdepth 1 -type d -mtime +14 -exec rm -rf {} +

echo "[+] Backup completato in $DEST"
echo "[+] TODO: configurare upload offsite (rsync ssh, rclone, ecc.)"
