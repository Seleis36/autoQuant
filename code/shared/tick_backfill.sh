#!/usr/bin/env bash
# Tier-1 tick backfill into the D: tick disk (see ticks.py, ticks_disk.ps1).
#
#   binance    aggTrades: spot BTC/ETH + USD-M perps for BTC/ETH and 22 alts, then 1m flow
#              bars for the perps into the bar store as <SYM>_PERP/1m.
#              ~330 GB to download, ~110 GB kept. Hours to a day, bandwidth-bound.
#   dukascopy  every tick for the 7 FX majors since 2012, plus 1m bid/ask bars.
#              ~7 GB kept, but ~700k throttled requests: weeks. Runs alongside.
#
# Both jobs are resumable -- rerun this script after any interruption and they pick up
# where they stopped. Logs: data/ticks/logs/<job>.log.
#
#   code/shared/tick_backfill.sh              # start both, detached
#   code/shared/tick_backfill.sh binance      # just one
set -euo pipefail
cd "$(dirname "$0")/../.."
PY=.venv/bin/python

ROOT=$($PY -c 'import sys; sys.path.insert(0, "code/shared"); import ticks; print(ticks.ticks_root())') || exit 1
mkdir -p "$ROOT/logs"

ALTS=SOLUSDT,BNBUSDT,XRPUSDT,ADAUSDT,DOGEUSDT,LINKUSDT,AVAXUSDT,DOTUSDT,LTCUSDT,TRXUSDT,ATOMUSDT,NEARUSDT,UNIUSDT,BCHUSDT,ETCUSDT,FILUSDT,AAVEUSDT,XLMUSDT,ALGOUSDT,APTUSDT,ARBUSDT,SUIUSDT
PERPS=BTCUSDT,ETHUSDT,$ALTS

binance() {
    $PY code/shared/fetch_binance_vision.py aggtrades --market spot --symbol BTCUSDT,ETHUSDT
    $PY code/shared/fetch_binance_vision.py aggtrades --market um --symbol "$PERPS"
    $PY code/shared/fetch_binance_vision.py flowbars --market um --freq 1m --symbol "$PERPS"
    echo "binance backfill done $(date -u +%FT%TZ)"
}

dukascopy() {
    $PY code/shared/fetch_dukascopy.py ticks --start 2012-01-01 --workers 1
    echo "dukascopy backfill done $(date -u +%FT%TZ)"
}

if [ "${1:-}" = "__run" ]; then
    echo "== $2 start $(date -u +%FT%TZ)"
    "$2"
    exit
fi

[ $# -eq 0 ] && set -- binance dukascopy
for job in "$@"; do
    case "$job" in binance|dukascopy) ;; *) echo "unknown job $job" >&2; exit 2 ;; esac
    if pgrep -f "tick_backfill.sh __run $job" >/dev/null; then
        echo "$job: already running"; continue
    fi
    setsid nohup "$0" __run "$job" >> "$ROOT/logs/$job.log" 2>&1 < /dev/null &
    echo "$job: started, log $ROOT/logs/$job.log"
done
