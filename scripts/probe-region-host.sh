#!/usr/bin/env bash
# Per-minute connection probe for the HomGar cloud host.
#
# Measures DNS / TCP / TLS / total separately so a degradation can be
# attributed to a layer instead of guessed at. Uses the same budget the
# integration itself uses (20s connect, 30s total) so a "timeout" here means
# exactly what a timeout in the integration would have meant.
#
# Samples are aligned to the top of each minute, which makes logs from
# different vantage points directly comparable line by line.
#
# Usage: probe-region-host.sh [-h host] [-o logfile] [-i interval_seconds]

set -uo pipefail

HOST="region3.homgarus.com"
LOG=""
INTERVAL=60

while getopts "h:o:i:" opt; do
  case "$opt" in
    h) HOST="$OPTARG" ;;
    o) LOG="$OPTARG" ;;
    i) INTERVAL="$OPTARG" ;;
    *) echo "usage: $0 [-h host] [-o logfile] [-i seconds]" >&2; exit 2 ;;
  esac
done

[ -n "$LOG" ] || LOG="probe-${HOST}-$(date +%Y%m%d-%H%M).log"

# Match custom_components/homgar/api/client.py:_REQUEST_TIMEOUT
CONNECT_TIMEOUT=20
TOTAL_TIMEOUT=30

FMT='dns=%{time_namelookup}s tcp=%{time_connect}s tls=%{time_appconnect}s total=%{time_total}s code=%{http_code} ip=%{remote_ip}'

echo "# probe start $(date +%Y-%m-%dT%H:%M:%S%z) host=$HOST connect_timeout=${CONNECT_TIMEOUT}s total_timeout=${TOTAL_TIMEOUT}s" >> "$LOG"

while true; do
  # Align to the next boundary so samples land on predictable wall-clock times.
  now_sec=$(date +%s)
  sleep_for=$(( INTERVAL - (now_sec % INTERVAL) ))
  sleep "$sleep_for"

  stamp=$(date +%Y-%m-%dT%H:%M:%S%z)
  out=$(curl -sS -o /dev/null \
          --connect-timeout "$CONNECT_TIMEOUT" \
          --max-time "$TOTAL_TIMEOUT" \
          -w "$FMT" \
          "https://${HOST}/" 2>&1)
  rc=$?

  if [ $rc -eq 0 ]; then
    echo "$stamp $out" >> "$LOG"
  else
    # Keep the curl exit code: 28 is a timeout, 6/7 are resolve/connect failures.
    echo "$stamp FAILED rc=$rc ${out//$'\n'/ }" >> "$LOG"
  fi
done
