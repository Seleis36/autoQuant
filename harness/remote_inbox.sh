#!/usr/bin/env bash
# The desk's end of the research host's rsync link.
#
#   sudo ./harness/remote_inbox.sh setup            # user + directories (idempotent)
#   sudo ./harness/remote_inbox.sh add-key '<ssh-ed25519 AAAA... comment>'
#   ./harness/remote_inbox.sh publish               # refresh the outbox (every desk sweep)
#   ./harness/remote_inbox.sh status
#
# The research host (AQ_ROLE=research) only ever connects OUT, to this machine over the
# tailnet, as the unprivileged user `aqsync`. Its key is pinned to rrsync rooted at
# $AQ_REMOTE_DIR, so the most a stolen key can do is read and write files in there: no
# shell, no forwarding, no root, nothing outside the directory (-munge defangs symlinks).
#
#   $AQ_REMOTE_DIR/desktop/      written by the research host, read by the dashboard
#     logs/<name>.log              harness/logs, as is
#     sessions/<uuid>.json         the session registry (+ <uuid>.result.json)
#     transcripts/<uuid>.jsonl     Claude Code conversations of registered sessions
#     heartbeat.json               {"ts", "host", "running": [uuid...], ...}
#   $AQ_REMOTE_DIR/outbox/       written here, read by the research host
#     allocations.json             the desk's capital book, for the deployment agent
#     desk.json                    what the desk is running, and when this was written
#     requests/<id>.json           dashboard asks (launch research, resume); the research
#                                  host deletes each one once it has acted on it
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIR="${AQ_REMOTE_DIR:-/var/lib/autoquant-remote}"
USER_NAME="${AQ_REMOTE_USER:-aqsync}"

say() { echo "[$(date -u +%FT%TZ)] inbox: $*"; }
need_root() { [ "$(id -u)" = 0 ] || { echo "ERROR: $1 needs root" >&2; exit 1; }; }

case "${1:-}" in
  setup)
    need_root setup
    command -v rrsync >/dev/null || { echo "ERROR: rrsync not installed (apt install rsync)" >&2; exit 1; }
    if ! id "$USER_NAME" >/dev/null 2>&1; then
      useradd --system --create-home --home-dir "/home/$USER_NAME" --shell /bin/sh "$USER_NAME"
      say "created user $USER_NAME"
    fi
    install -d -m 0755 -o "$USER_NAME" -g "$USER_NAME" "$DIR"
    install -d -m 0755 -o "$USER_NAME" -g "$USER_NAME" \
      "$DIR/desktop" "$DIR/desktop/logs" "$DIR/desktop/sessions" "$DIR/desktop/transcripts" \
      "$DIR/outbox" "$DIR/outbox/requests"
    install -d -m 0700 -o "$USER_NAME" -g "$USER_NAME" "/home/$USER_NAME/.ssh"
    touch "/home/$USER_NAME/.ssh/authorized_keys"
    chown "$USER_NAME:$USER_NAME" "/home/$USER_NAME/.ssh/authorized_keys"
    chmod 0600 "/home/$USER_NAME/.ssh/authorized_keys"
    say "ready: $DIR (user $USER_NAME); add the research host's key with: $0 add-key '<pubkey>'"
    ;;
  add-key)
    need_root add-key
    key="${2:?usage: $0 add-key '<ssh-ed25519 AAAA... comment>'}"
    [[ "$key" =~ ^ssh-(ed25519|rsa)\ [A-Za-z0-9+/=]+(\ [[:graph:]]+)?$ ]] \
      || { echo "ERROR: that does not look like one public key line" >&2; exit 2; }
    ak="/home/$USER_NAME/.ssh/authorized_keys"
    [ -f "$ak" ] || { echo "ERROR: run '$0 setup' first" >&2; exit 1; }
    blob="$(echo "$key" | awk '{print $2}')"
    if grep -qF "$blob" "$ak"; then say "key already present"; exit 0; fi
    echo "command=\"/usr/bin/rrsync -munge $DIR\",restrict $key" >> "$ak"
    say "key added for $USER_NAME, pinned to rrsync $DIR"
    ;;
  publish)
    [ -d "$DIR/outbox" ] || exit 0      # inbox not set up: nothing to publish to
    tmp="$(mktemp "$DIR/outbox/.allocations.XXXXXX")"
    if cp "$REPO/harness/state/allocations.json" "$tmp" 2>/dev/null; then
      chmod 0644 "$tmp"; mv -f "$tmp" "$DIR/outbox/allocations.json"
    else
      rm -f "$tmp"
    fi
    tmp="$(mktemp "$DIR/outbox/.desk.XXXXXX")"
    {
      printf '{"ts": "%s", "host": "%s", "head": "%s", "strategies": [' \
        "$(date -u +%FT%TZ)" "$(hostname)" "$(git -C "$REPO" rev-parse --short HEAD 2>/dev/null)"
      "$REPO/harness/launch_live.sh" status 2>/dev/null \
        | awk '{printf "%s{\"name\": \"%s\", \"status\": \"%s\"}", (NR>1?", ":""), $2, $1}'
      printf ']}\n'
    } > "$tmp"
    chmod 0644 "$tmp"; mv -f "$tmp" "$DIR/outbox/desk.json"
    ;;
  status)
    echo "remote dir: $DIR"
    if [ -f "$DIR/desktop/heartbeat.json" ]; then
      age=$(( $(date +%s) - $(stat -c %Y "$DIR/desktop/heartbeat.json") ))
      echo "research host last synced ${age}s ago: $(cat "$DIR/desktop/heartbeat.json")"
    else
      echo "research host has never synced"
    fi
    echo "pending requests: $(find "$DIR/outbox/requests" -name '*.json' 2>/dev/null | wc -l)"
    ;;
  *) echo "usage: $0 {setup|add-key <pubkey>|publish|status}" >&2; exit 2 ;;
esac
