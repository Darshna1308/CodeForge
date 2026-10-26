#!/usr/bin/env bash
# Reproducible headless load test. Usage: tests/load/run.sh [API_URL] [USERS] [SPAWN_RATE] [DURATION]
set -euo pipefail
API_URL=${1:-http://localhost:8000}
USERS=${2:-40}
RATE=${3:-10}
DURATION=${4:-90s}
HERE=$(cd "$(dirname "$0")" && pwd)
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
OUT="$HERE/results/$STAMP"
mkdir -p "$OUT"

{
  echo "timestamp_utc: $STAMP"
  echo "target: $API_URL"
  echo "users: $USERS  spawn_rate: $RATE/s  duration: $DURATION"
  echo "host: $(uname -srm)"
  echo "cpus: $(nproc 2>/dev/null || sysctl -n hw.ncpu)"
  echo "memory: $(free -h 2>/dev/null | awk '/Mem:/ {print $2}' || echo unknown)"
  echo "workers_online: $(curl -s "$API_URL/stats/overview" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("active_workers"))' 2>/dev/null || echo unknown)"
} > "$OUT/environment.txt"

locust -f "$HERE/locustfile.py" --host "$API_URL" --headless -u "$USERS" -r "$RATE" -t "$DURATION" \
  --csv "$OUT/locust" --only-summary 2>&1 | tee "$OUT/summary.txt"
curl -s "$API_URL/stats/system" > "$OUT/system_after.json" || true
echo "results written to $OUT"
