#!/usr/bin/env bash
# Aggiorna i database MMDB di MaxMind (GeoLite2 ASN + Country).
# Da eseguire mensile via cron come utente "youfeed".
#
# Richiede MAXMIND_LICENSE_KEY in .env.
# Crea account gratuito su https://www.maxmind.com/en/geolite2/signup

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

# Carica .env
if [[ ! -f .env ]]; then
    echo "Errore: .env non trovato in $ROOT_DIR" >&2
    exit 1
fi
set -a
# shellcheck disable=SC1091
source .env
set +a

if [[ -z "${MAXMIND_LICENSE_KEY:-}" ]]; then
    echo "Errore: MAXMIND_LICENSE_KEY non valorizzata in .env" >&2
    exit 1
fi

DB_DIR="${MAXMIND_DB_DIR:-/var/lib/youfeed/maxmind}"
mkdir -p "$DB_DIR"
TMPDIR="$(mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT

download() {
    local edition="$1"
    local url="https://download.maxmind.com/app/geoip_download?edition_id=${edition}&license_key=${MAXMIND_LICENSE_KEY}&suffix=tar.gz"
    echo "Scaricando $edition..."
    curl -sSL "$url" -o "${TMPDIR}/${edition}.tar.gz"
    tar -xzf "${TMPDIR}/${edition}.tar.gz" -C "$TMPDIR"
    # Il tar contiene una directory con timestamp; troviamo il .mmdb dentro
    find "$TMPDIR" -name "${edition}.mmdb" -exec mv {} "${DB_DIR}/${edition}.mmdb" \;
}

download "GeoLite2-Country"
download "GeoLite2-ASN"

echo "MMDB aggiornati in $DB_DIR"
ls -la "$DB_DIR"/*.mmdb
