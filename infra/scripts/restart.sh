#!/usr/bin/env bash
# Riavvia i servizi backend YOUFEED. Da lanciare come utente abilitato a sudo.
#
# Uso:
#   ./infra/scripts/restart.sh            # riavvia API + scheduler + activity-log + tutti i worker
#   ./infra/scripts/restart.sh api        # solo l'API HTTP (cambi a template/router/admin)
#   ./infra/scripts/restart.sh workers    # solo i worker RQ (cambi alla pipeline ingestion)

set -euo pipefail

API_UNITS=(yf-api.service)
SCHED_UNITS=(yf-scheduler.service yf-activity-log.service)

# Worker template: prendiamo solo le istanze realmente attive nel sistema.
mapfile -t WORKER_UNITS < <(
    systemctl list-units --type=service --no-legend --no-pager 'yf-worker@*.service' \
        | awk '{print $1}'
)

target="${1:-all}"

units=()
case "$target" in
    api)
        units=("${API_UNITS[@]}")
        ;;
    workers)
        units=("${SCHED_UNITS[@]}" "${WORKER_UNITS[@]}")
        ;;
    all|"")
        units=("${API_UNITS[@]}" "${SCHED_UNITS[@]}" "${WORKER_UNITS[@]}")
        ;;
    *)
        echo "Uso: $0 [api|workers|all]" >&2
        exit 2
        ;;
esac

if [ ${#units[@]} -eq 0 ]; then
    echo "Nessuna unit da riavviare." >&2
    exit 0
fi

echo "Riavvio: ${units[*]}"
sudo systemctl restart "${units[@]}"

echo
echo "Stato:"
sudo systemctl --no-pager --lines=0 status "${units[@]}" \
    | grep -E '^(●|\s*Active:|\s*Loaded:)' || true
