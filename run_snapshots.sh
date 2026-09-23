#!/bin/bash
set -euo pipefail

cd /home/suhaas/repos/fantasy-dashboard

PYTHON="/home/suhaas/repos/fantasy-dashboard/venv/bin/python"
DATA_DIR="${FANTASY_DASHBOARD_DATA_DIR:-/home/suhaas/repos/fantasy-dashboard/data}"
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

CACHE_STATUS=0
CACHE_ARGUMENTS=()
for LEAGUE_ID in "${LEAGUE_IDS[@]}"; do
    CACHE_ARGUMENTS+=(--league-id "$LEAGUE_ID")
done

"$PYTHON" warm_regression_cache.py "${CACHE_ARGUMENTS[@]}" || CACHE_STATUS=$?
if (( CACHE_STATUS != 0 )); then
    exit "$CACHE_STATUS"
fi

S3_BUCKET="${FANTASY_DASHBOARD_S3_BUCKET:-}"
if [[ -n "$S3_BUCKET" ]]; then
    AWS_CLI="${FANTASY_DASHBOARD_AWS_CLI:-aws}"
    S3_PREFIX="${FANTASY_DASHBOARD_S3_PREFIX:-data}"
    S3_PREFIX="${S3_PREFIX#/}"
    S3_PREFIX="${S3_PREFIX%/}"
    AWS_ARGUMENTS=()
    if [[ -n "${FANTASY_DASHBOARD_AWS_PROFILE:-}" ]]; then
        AWS_ARGUMENTS+=(--profile "$FANTASY_DASHBOARD_AWS_PROFILE")
    fi
    "$AWS_CLI" s3 sync \
        "$DATA_DIR/" "s3://$S3_BUCKET/$S3_PREFIX/" \
        --only-show-errors "${AWS_ARGUMENTS[@]}"
fi
