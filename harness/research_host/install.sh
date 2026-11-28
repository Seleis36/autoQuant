#!/usr/bin/env bash
# Install the research host's user units (see PLAN.md). Refuses unless AQ_ROLE=research.
#
#   harness/research_host/install.sh              # install + enable + start
#   harness/research_host/install.sh --uninstall  # stop, disable, remove the links
#
# What it sets up, all started at boot through default.target / timers.target -- NOT
# through autoquant.target, which is the old single host's "trade everything" target and
# stays disabled here:
#   autoquant-research-sync.timer    sync.sh every 2 min (logs, registry, requests)
#   autoquant-research-daily.timer   daily.sh at 01:00
#   autoquant-research-boot.timer    daily.sh 10 min after boot -- enabled, NOT started:
#                                    started mid-session its elapsed OnBootSec fires at once
#                                    and launches a real batch (that happened on install)
#   autoquant-poller.service         review and revision queues (no watchdog in this role)
#   autoquant-ticks.service          the D: tick disk and its backfill
#
# The research units are symlinked from the repo, so a `git pull` changes them after a
# `systemctl --user daemon-reload`. The poller and tick units are copied, the way
# install_autostart.sh does it.
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck source=/dev/null
. "$REPO/harness/session_lib.sh"
SRC="$REPO/harness/research_host"
DST="$HOME/.config/systemd/user"
RESEARCH_UNITS=(autoquant-research-sync.service autoquant-research-sync.timer
                autoquant-research-daily.service autoquant-research-daily.timer
                autoquant-research-boot.timer)
TIMERS=(autoquant-research-sync.timer autoquant-research-daily.timer)
BOOT_TIMER=autoquant-research-boot.timer
SERVICES=(autoquant-poller.service autoquant-ticks.service)

say() { echo "[research-host install] $*"; }

if [ "$(aq_role)" != research ]; then
  echo "REFUSED: this installs the research host; AQ_ROLE is '$(aq_role)' (set AQ_ROLE=research in .env)" >&2
  exit 5
fi

if [ "${1:-}" = "--uninstall" ]; then
  systemctl --user disable --now "${TIMERS[@]}" "$BOOT_TIMER" 2>/dev/null
  systemctl --user stop autoquant-research-sync.service autoquant-research-daily.service 2>/dev/null
  systemctl --user remove-wants default.target "${SERVICES[@]}" 2>/dev/null
  systemctl --user stop "${SERVICES[@]}" 2>/dev/null
  for u in "${RESEARCH_UNITS[@]}"; do [ -L "$DST/$u" ] && rm -f "$DST/$u"; done
  systemctl --user daemon-reload
  say "research units removed; poller and tick store stopped and no longer started at boot"
  exit 0
fi

# Never alongside the trading side: a strategy unit enabled here would trade the same
# testnet account as the desk.
mkdir -p "$DST"
enabled="$(find "$DST" -path '*.wants/autoquant-strategy@*' -o -path '*.wants/autoquant.target' 2>/dev/null)"
if [ -n "$enabled" ]; then
  echo "REFUSED: trading units are still enabled on this host:" >&2
  echo "$enabled" | sed 's/^/  /' >&2
  echo "Disable them first (PLAN.md, Step 1)." >&2
  exit 1
fi

for u in "${RESEARCH_UNITS[@]}"; do ln -sfn "$SRC/$u" "$DST/$u"; done
for u in "${SERVICES[@]}"; do cp "$REPO/harness/systemd/$u" "$DST/$u"; done
systemctl --user daemon-reload

systemctl --user enable --now "${TIMERS[@]}"
systemctl --user enable "$BOOT_TIMER"        # no --now: see the header
# Their [Install] says WantedBy=autoquant.target; on this host they hang off default.target.
systemctl --user add-wants default.target "${SERVICES[@]}"
systemctl --user start "${SERVICES[@]}"

loginctl show-user "$USER" -p Linger 2>/dev/null | grep -q yes \
  || say "WARNING: linger is off -- the units start only while you are logged in (sudo loginctl enable-linger $USER)"
say "installed:"
systemctl --user list-timers "${TIMERS[@]}" --no-pager | sed 's/^/  /'
say "  $BOOT_TIMER: $(systemctl --user is-enabled "$BOOT_TIMER") (runs from the next boot)"
systemctl --user is-active "${SERVICES[@]}" | paste - - | sed "s/^/  poller, ticks: /"
