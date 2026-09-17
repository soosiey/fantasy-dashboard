#!/bin/bash
set -euo pipefail

cd /home/suhaas/repos/fantasy-dashboard

PYTHON="/home/suhaas/repos/fantasy-dashboard/venv/bin/python"
LEAGUE_IDS=(
    "1389388987633782784"
    "1389347297095073792"
)
WEEK_FILE="snapshot_week.txt"

read -r COMPLETED_WEEK < "$WEEK_FILE"
UPCOMING_WEEK=$((COMPLETED_WEEK + 1))

if (( COMPLETED_WEEK > 18 )); then
    exit 0
fi

for LEAGUE_ID in "${LEAGUE_IDS[@]}"; do
    "$PYTHON" take_snapshot.py post-week \
        --league-id "$LEAGUE_ID" --week "$COMPLETED_WEEK"

    if (( UPCOMING_WEEK <= 18 )); then
        "$PYTHON" take_snapshot.py pre-kickoff \
            --league-id "$LEAGUE_ID" --week "$UPCOMING_WEEK"
    fi
done

printf '%s\n' "$UPCOMING_WEEK" > "${WEEK_FILE}.tmp"
mv "${WEEK_FILE}.tmp" "$WEEK_FILE"
