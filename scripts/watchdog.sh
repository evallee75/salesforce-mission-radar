#!/bin/bash
# Filet de sécurité des crons GitHub (souvent retardés, parfois sautés) : lancé par launchd
# toutes les 30 min sur le Mac, il déclenche un scan si aucun n'a démarré depuis 150 min,
# entre 6h et 22h (heure de Paris). Les republications (push) ne comptent pas comme scan.
set -euo pipefail
export PATH="/opt/homebrew/bin:/usr/bin:/bin"
REPO="evallee75/salesforce-mission-radar"
MAX_AGE_MIN=150

hour=$(TZ=Europe/Paris date +%H)
if [ "$hour" -lt 6 ] || [ "$hour" -ge 22 ]; then exit 0; fi

runs=$(gh run list -R "$REPO" -w radar.yml -L 20 --json createdAt,event,status) || { echo "$(date) gh indisponible"; exit 0; }
age_min=$(echo "$runs" | python3 -c '
import json, sys, datetime as dt
runs = [r for r in json.load(sys.stdin) if r["event"] != "push"]
if any(r["status"] in ("queued", "in_progress", "waiting", "pending") for r in runs):
    print(0); sys.exit()
if not runs:
    print(99999); sys.exit()
last = max(dt.datetime.fromisoformat(r["createdAt"].replace("Z", "+00:00")) for r in runs)
print(int((dt.datetime.now(dt.timezone.utc) - last).total_seconds() // 60))
')

if [ "$age_min" -ge "$MAX_AGE_MIN" ]; then
  gh workflow run radar.yml -R "$REPO" && echo "$(date) dernier scan il y a ${age_min} min : scan déclenché"
fi
