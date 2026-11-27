#!/usr/bin/env bash
# At most one nightly research batch per local calendar day (Europe/Paris), on a PC that
# is only on some of the time (see PLAN.md, Step 6).
#
#   harness/research_host/daily.sh             # the research timers: 10 min after boot, and 01:00
#   harness/research_host/daily.sh --dry-run   # every guard and the stamp check, then
#                                              # nightly_research.sh --dry-run; launches nothing
#
# The stamp (harness/state/research_host/last_batch, YYYY-MM-DD) is written BEFORE the
# batch starts: a PC switched off ten minutes in has used its day, and the cut-off session
# is resumable from the dashboard. A skipped day (any guard below) writes no stamp, so a
# later boot the same day tries again.
#
# Off switches, in harness/state/research_host/:
#   paused              no batch at all until the file is removed
#   skip-YYYY-MM-DD     no batch on that day
#
# Environment (for tests): AQ_DAILY_TODAY overrides the date, AQ_RH_STATE the state dir,
# AQ_DAILY_LOG the log file.
# NIGHTLY_COUNT defaults to 1 here -- one asset class per day was the user's choice.
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck source=/dev/null
. "$REPO/harness/session_lib.sh"

DRY=0
[ "${1:-}" = "--dry-run" ] && DRY=1
STATE="${AQ_RH_STATE:-$REPO/harness/state/research_host}"
LOGS="$REPO/harness/logs"
LOG="${AQ_DAILY_LOG:-$LOGS/daily.log}"
MIN_FREE_GB="${DAILY_MIN_FREE_GB:-20}"
mkdir -p "$STATE" "$LOGS"
export NIGHTLY_COUNT="${NIGHTLY_COUNT:-1}"

TAG=daily
[ "$DRY" = 1 ] && TAG="daily (dry-run)"
say() { echo "[$(date -u +%FT%TZ)] $TAG: $*" | tee -a "$LOG"; }

if [ "$(aq_role)" != research ]; then
  echo "REFUSED: daily.sh runs on the research host only (AQ_ROLE=$(aq_role))" >&2
  exit 5
fi

exec {lock}>"$STATE/daily.lock"
flock -n "$lock" || { say "another daily.sh is running"; exit 0; }

today="${AQ_DAILY_TODAY:-$(TZ=Europe/Paris date +%F)}"
[[ "$today" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] || { say "bad date '$today'"; exit 2; }

# ---- once a day ------------------------------------------------------------------
if [ "$(cat "$STATE/last_batch" 2>/dev/null)" = "$today" ]; then
  say "already ran today ($today), nothing launched"
  exit 0
fi

# ---- guards: each one skips the day without using it up --------------------------
if [ -e "$STATE/paused" ]; then
  say "paused (remove ${STATE#"$REPO"/}/paused to resume), nothing launched"; exit 0
fi
if [ -e "$STATE/skip-$today" ]; then
  say "skip-$today is set, nothing launched"; exit 0
fi
free_gb="$(df -BG --output=avail "$REPO" | tail -1 | tr -dc 0-9)"
if [ "${free_gb:-0}" -lt "$MIN_FREE_GB" ]; then
  say "only ${free_gb:-?} GB free on the distro disk (< $MIN_FREE_GB), nothing launched"; exit 0
fi
if ! timeout 60 "$CLAUDE_BIN" auth status 2>/dev/null | grep -q '"loggedIn": *true'; then
  say "claude is not logged in, nothing launched"; exit 0
fi
if ! timeout 60 gh auth status >/dev/null 2>&1; then
  say "gh is not authenticated, nothing launched"; exit 0
fi

if [ "$DRY" = 1 ]; then
  say "guards passed; would stamp $today and run nightly_research.sh (NIGHTLY_COUNT=$NIGHTLY_COUNT):"
  "$REPO/harness/nightly_research.sh" --dry-run | tee -a "$LOG"
  # A dry run stamps only a test state dir: stamping the real one would use up today.
  if [ -n "${AQ_RH_STATE:-}" ]; then
    echo "$today" > "$STATE/last_batch"
    say "stamped $today in $STATE (nothing launched)"
  fi
  exit 0
fi

# ---- the batch --------------------------------------------------------------------
echo "$today" > "$STATE/last_batch"
say "stamped $today; starting nightly_research.sh (NIGHTLY_COUNT=$NIGHTLY_COUNT, ${free_gb} GB free)"
"$REPO/harness/nightly_research.sh"
rc=$?
say "nightly_research.sh exited rc=$rc"
exit "$rc"
