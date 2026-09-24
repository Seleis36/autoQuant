#!/usr/bin/env bash
# Make autoQuant survive a reboot: systemd inside WSL, and a Windows logon hook
# that boots WSL in the first place.
#
#   ./harness/install_autostart.sh            # install + enable + start
#   ./harness/install_autostart.sh --uninstall
#
# Two halves, because neither is sufficient alone:
#
#   1. systemd USER units supervise the dashboard, the poller and every strategy
#      (Restart=always), and `loginctl enable-linger` lets them run without an open
#      login session. This also replaces the poller's watchdog as the primary
#      supervisor -- systemd notices a crash in seconds, the watchdog in <=30 min.
#   2. WSL does not start when Windows boots. A .vbs in the Startup folder boots the
#      distro at logon, silently, which is what triggers (1).
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UNIT_SRC="$REPO/harness/systemd"
UNIT_DST="$HOME/.config/systemd/user"
WIN_USER="$(cmd.exe /c 'echo %USERNAME%' 2>/dev/null | tr -d '\r\n')"
STARTUP="/mnt/c/Users/$WIN_USER/AppData/Roaming/Microsoft/Windows/Start Menu/Programs/Startup"
VBS="$STARTUP/autoQuant.vbs"
DISTRO="$(wsl.exe -l -q --running 2>/dev/null | tr -d '\r\0' | head -1)"
DISTRO="${DISTRO:-Ubuntu}"

say() { echo "  $*"; }

strategies() {
  find "$REPO/live" -mindepth 3 -maxdepth 3 -name runner.py -printf '%h\n' 2>/dev/null \
    | sed "s|^$REPO/live/||"
}

if [ "${1:-}" = "--uninstall" ]; then
  echo "Removing autostart..."
  systemctl --user disable --now autoquant.target >/dev/null 2>&1
  for s in $(strategies); do
    systemctl --user disable --now "autoquant-strategy@$(systemd-escape "$s").service" >/dev/null 2>&1
  done
  systemctl --user disable --now autoquant-dashboard.service autoquant-poller.service \
    autoquant-nightly.timer >/dev/null 2>&1
  rm -f "$UNIT_DST"/autoquant-*.service "$UNIT_DST"/autoquant-*.timer "$UNIT_DST"/autoquant.target
  systemctl --user daemon-reload
  rm -f "$VBS"
  say "units and Startup entry removed (linger left enabled)"
  exit 0
fi

echo "Installing autoQuant autostart"
echo

# ---- 1. systemd user units -------------------------------------------------
if ! systemctl --user is-system-running >/dev/null 2>&1; then
  echo "ERROR: no systemd user instance. Check that /etc/wsl.conf has [boot] systemd=true" >&2
  exit 1
fi

mkdir -p "$UNIT_DST" "$REPO/harness/logs"
cp "$UNIT_SRC"/autoquant-*.service "$UNIT_SRC"/autoquant-*.timer "$UNIT_SRC"/autoquant.target "$UNIT_DST"/
systemctl --user daemon-reload
say "units installed in ${UNIT_DST/#$HOME/\~}"

# Linger keeps the user manager alive with no login session -- without it every
# unit dies the moment the last terminal closes.
if [ "$(loginctl show-user "$USER" -p Linger --value 2>/dev/null)" != "yes" ]; then
  if loginctl enable-linger "$USER" 2>/dev/null; then
    say "linger enabled for $USER"
  else
    say "WARNING: could not enable linger (needs sudo). Run: sudo loginctl enable-linger $USER"
  fi
else
  say "linger already enabled"
fi

# Hand supervision over cleanly: stop anything started by launch_live.sh first, so
# systemd does not find the port or the ledger already taken.
"$REPO/harness/dashboard.sh" stop >/dev/null 2>&1
"$REPO/harness/poll_prs.sh" --stop >/dev/null 2>&1
for s in $(strategies); do "$REPO/harness/launch_live.sh" stop "$s" >/dev/null 2>&1; done

systemctl --user enable autoquant.target >/dev/null 2>&1
systemctl --user enable autoquant-dashboard.service autoquant-poller.service >/dev/null 2>&1
for s in $(strategies); do
  unit="autoquant-strategy@$(systemd-escape "$s").service"
  systemctl --user enable "$unit" >/dev/null 2>&1
  say "enabled $unit  ($s)"
done
systemctl --user start autoquant.target
sleep 4
say "started autoquant.target"

# The nightly research batch. Only the timer is enabled; the service it triggers has no
# [Install] on purpose -- enabling it would also run a research batch at every boot.
systemctl --user enable --now autoquant-nightly.timer >/dev/null 2>&1 \
  && say "nightly research timer: $(systemctl --user list-timers autoquant-nightly.timer --no-legend --no-pager | awk '{print $1, $2, $3}')"

# ---- 2. Windows logon hook -------------------------------------------------
if [ -d "$STARTUP" ]; then
  cat > "$VBS" <<VBSEOF
' autoQuant - boot WSL at logon so its systemd units come up.
' Written by harness/install_autostart.sh. Runs hidden (0) and does not wait.
' The trailing sleep is load-bearing: WSL tears the distro down ~15s after the
' last wsl.exe client exits, which would kill the units linger keeps alive.
CreateObject("WScript.Shell").Run _
  "wsl.exe -d $DISTRO -u $USER --exec /bin/bash -lc ""systemctl --user start autoquant.target; exec /bin/sleep infinity""", 0, False
VBSEOF
  say "Startup entry written: ${VBS#/mnt/c/}"
  say "  boots distro '$DISTRO' at Windows logon"
else
  say "WARNING: Startup folder not found at $STARTUP -- Windows hook not installed"
fi

echo
echo "Status:"
systemctl --user list-units 'autoquant*' --no-pager --no-legend | sed 's/^/  /'
echo
echo "Notes:"
echo "  * This starts at LOGON, not at boot. A true pre-login start needs an elevated"
echo "    Task Scheduler entry -- see harness/windows_autostart_task.ps1 (run as admin)."
echo "  * systemd now supervises the strategies. Use launch_live.sh as before; it"
echo "    delegates to systemctl for anything under a unit."
echo "  * Logs are unchanged: live/<name>/runner.log, harness/logs/."
