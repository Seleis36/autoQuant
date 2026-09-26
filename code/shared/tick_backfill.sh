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
# where they stopped. Once caught up, a rerun only fetches what is new. Logs:
# data/ticks/logs/<job>.log.
#
#   code/shared/tick_backfill.sh                   # start both, detached
#   code/shared/tick_backfill.sh binance           # just one
#   code/shared/tick_backfill.sh --foreground      # both, supervised; repeats every 6h (systemd)
#
# Normally nobody runs this by hand: autoquant-ticks.service runs it with --foreground
# every time WSL comes up (see harness/systemd/).
#
# If the disk is not mounted, this asks Windows to mount it by running the logon task
# that ticks_disk.ps1 registered -- elevated already, so no UAC prompt -- and waits.
set -euo pipefail
cd "$(dirname "$0")/../.."
PY=.venv/bin/python
TASK="autoQuant ticks disk"
SCHTASKS=/mnt/c/Windows/System32/schtasks.exe
MOUNT_WAIT_S="${TICKS_MOUNT_WAIT_S:-180}"
REFRESH_S="${TICKS_REFRESH_S:-21600}"      # --foreground: pause between passes once caught up

tick_root() {
    $PY -c 'import sys; sys.path.insert(0, "code/shared"); import ticks; print(ticks.ticks_root())' 2>/dev/null
}

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

if ! ROOT=$(tick_root); then
    echo "tick disk not mounted; asking Windows to mount it (task '$TASK')"
    "$SCHTASKS" /run /tn "$TASK" >/dev/null || { echo "could not run task '$TASK'" >&2; exit 1; }
    for _ in $(seq "$MOUNT_WAIT_S"); do
        ROOT=$(tick_root) && break
        sleep 1
    done
    [ -n "${ROOT:-}" ] || { echo "tick disk still not mounted after ${MOUNT_WAIT_S}s" >&2; exit 1; }
    echo "tick disk mounted at $ROOT"
fi
mkdir -p "$ROOT/logs"

FOREGROUND=0
if [ "${1:-}" = "--foreground" ]; then FOREGROUND=1; shift; fi
[ $# -eq 0 ] && set -- binance dukascopy
todo=()
for job in "$@"; do
    case "$job" in binance|dukascopy) ;; *) echo "unknown job $job" >&2; exit 2 ;; esac
    if pgrep -f "tick_backfill.sh __run $job" >/dev/null; then
        echo "$job: already running"
    else
        todo+=("$job")
    fi
done
[ ${#todo[@]} -gt 0 ] || exit 0

if [ "$FOREGROUND" = 1 ]; then
    # Children of this process, so the service's cgroup owns them: stopping the unit
    # stops the jobs. The first job to die non-zero fails the whole run -- systemd then
    # restarts both, which is safe because both resume -- rather than leaving it dead
    # until the other job finishes weeks later. When every job is done, sleep and go
    # again, so new months and days keep arriving without anyone rerunning this.
    while :; do
        pids=()
        for job in "${todo[@]}"; do
            "$0" __run "$job" >> "$ROOT/logs/$job.log" 2>&1 < /dev/null &
            pids+=($!)
            echo "$(date -u +%FT%TZ) $job: running, log $ROOT/logs/$job.log"
        done
        for _ in "${pids[@]}"; do
            wait -n || { echo "$(date -u +%FT%TZ) a job failed; exiting for a restart" >&2; exit 1; }
        done
        echo "$(date -u +%FT%TZ) all caught up; next pass in ${REFRESH_S}s"
        sleep "$REFRESH_S"
    done
fi

for job in "${todo[@]}"; do
    setsid nohup "$0" __run "$job" >> "$ROOT/logs/$job.log" 2>&1 < /dev/null &
    echo "$job: started, log $ROOT/logs/$job.log"
done
