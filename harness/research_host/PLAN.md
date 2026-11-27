# Research host setup plan: desktop-h0g6rel (WSL)

You are a Claude Code session running **inside WSL on desktop-h0g6rel**, in the repo checkout
`/home/seleis/autoQuant`. This plan turns this machine into autoQuant's **research host**.
It runs every Claude agent and trades nothing. The trading desk (the VPS) is already set up
for its side. Work through the steps in order. Each step says how to verify it before you
move on.

Read `harness/README.md` → "Two hosts: the desk and the research host" first. It describes
the split from the desk's side.

## Context

- **Until Oct 12 2026 this machine was the whole system.** It traded every strategy and ran
  every agent. On Oct 12 its daemons were stopped and everything moved to a VPS.
- **The move broke research.** On the VPS the agents run as root, and the Claude CLI refuses
  `--dangerously-skip-permissions` as root, so every nightly research session since Oct 22
  died within a second. The VPS also has a 30 GB disk and 3.8 GB RAM, too small for research.
  The tick store (~117 GB on `D:\WSL\autoquant-ticks.vhdx`) is only here.
- **The new split:**
  - **Desk (VPS, `AQ_ROLE=desk`):** always on. Trades, serves the dashboard at
    quant.a-maral.com, and starts the strategies this host merges. Runs no agents.
  - **Research host (this machine, `AQ_ROLE=research`):** on only some of the time. Runs the
    nightly research batch at most **once per local calendar day**, the deployment-review
    agent and the revision agent. Trades **nothing**.
  - **Approval stays fully automatic.** The deployment agent reviews, merges and labels
    `deployed` as before. The desk then launches the strategy.
- **Results reach the desk through GitHub, as before.** Logs, the session registry and
  transcripts reach it by **rsync over the tailnet**. The repo is public, so these never go
  into git.
- **The desk only ever receives connections from this host.** This host connects out to the
  desk. The desk never connects in.

The desk: tailnet IP `100.120.177.5`, MagicDNS name `server`. Use the IP: MagicDNS was
reporting DNS errors. You sync as user `aqsync`, whose key is pinned to
`rrsync -munge /var/lib/autoquant-remote`. It can read and write files under that directory
and nothing else. It has no shell, so `ssh aqsync@… id` is refused by design. Paths in rsync
commands are relative to that directory.

## What is already done on the desk

The commits that carry this have to be pushed before you start. Step 2 checks.

- **`AQ_ROLE` in `harness/session_lib.sh`.** `aq_role` resolves the role from the
  environment first, then `.env`, and defaults to `all`. `no_agents_on_desk` makes every
  launcher exit 5 on the desk.
- **`harness/poll_prs.sh`.**
  - `desk`: watchdog, `desk_launch.sh` and `remote_inbox.sh publish`, no agent queues.
  - `research`: the agent queues, **no watchdog**.
  - `all`: unchanged.
- **`harness/desk_launch.sh`, the desk's half of deploying.** It handles merged PRs labelled
  `deployed` and merged after `AQ_DESK_SINCE`. For each one it:
  1. pulls `main`,
  2. reserves `capital_usdt` in the `book` that `meta.json` names,
  3. enables and starts the strategy's unit,
  4. labels the PR `vps:launched`, or `vps:launch-failed` with a comment.
- **`.claude/commands/deploy-strategy.md`, Phase 7.** With `AQ_ROLE=research` the agent
  merges and labels `deployed` but does **not** enable or start anything.
- **`harness/install_autostart.sh` refuses to run on a research host (exit 5).** It installs
  the trading desk.
- **The desk's dashboard reads the synced files** under `/var/lib/autoquant-remote/desktop`.
  It shows the research host's status in the header. Its Launch and Resume buttons write
  requests to `outbox/requests/` instead of running anything locally.
- **The desk's nightly timer is off.** `AQ_ROLE=desk` and `AQ_DESK_SINCE` are in its `.env`.

### The file contract (paths relative to the rrsync root)

| Path | Writer | Content |
|---|---|---|
| `desktop/logs/<name>.log` | you | `harness/logs/*.log` as is. **Rename your `poller.log` to `desktop-poller.log`.** The desk has its own `poller.log`, and the dashboard prefers the local file when names match. |
| `desktop/sessions/<uuid>.json`, `<uuid>.result.json` | you | `harness/state/sessions/` as is |
| `desktop/transcripts/<uuid>.jsonl` | you | `~/.claude/projects/-home-seleis-autoQuant/<uuid>.jsonl`, flat, **only for uuids in the registry** |
| `desktop/heartbeat.json` | you, **pushed last** | `{"ts": ISO-UTC, "host": "desktop-h0g6rel", "role": "research", "running": [uuid…], "research_today": "YYYY-MM-DD" or null, "disk_free_gb": number}` |
| `outbox/allocations.json` | desk | the desk's capital book |
| `outbox/desk.json` | desk | `{"ts", "host", "head", "strategies": [{"name", "status"}]}` |
| `outbox/requests/<id>.json` | desk | `{"id", "action", "requested_at", …}`. Pull with `--remove-source-files`, which deletes them on the desk (tested). |

Details of the contract:
- **How the desk judges freshness.** It uses the heartbeat file's **mtime**, which `rsync -t`
  preserves from this machine. If the mtime is older than 10 min, the desk shows this host as
  off and its `running` sessions as `aborted · host_offline`.
- **What `running` must contain.** Only uuids whose registry status is `running` **and** whose
  pid is alive on this machine.
- **Push permissions.** Push with `--chmod=D0700,F0600`. Never use `--delete`: the desk keeps
  history even after you prune.
- **Dashboard validation.** The desk validates every basename it serves:
  - session files must match `<uuid>.json`,
  - logs must match `[\w.-]+\.log`,
  - transcripts must be `<uuid>.jsonl`.

  Anything else is ignored, so stick to those names.

### The requests you will receive

| `action` | Fields | Do |
|---|---|---|
| `launch_research` | `asset_class`, `seed` (≤ 500 chars), `model` | `harness/launch_research.sh "$asset_class" "$seed" --model "$model"` |
| `resume` | `session`: a uuid or `--all` | `harness/resume_aborted.sh "$session"` |
| `clear_attempts` | `pr` (int) | `rm -f harness/state/attempts-$pr` (the dashboard's requeue button already cleared the labels) |

**Re-validate every field before acting.** Anything that can write the outbox can write a
request: in practice only the desk, but treat requests as untrusted.
- `asset_class` must be one of: `spot-btc spot-eth crypto-perps crypto-alts us-large-cap
  sector-etf global-equity-etf fx-majors rates-bonds commodities vol-complex`, **and**
  `.claude/commands/<ac>-quant-research.md` must exist.
- `model` must be one of `opus sonnet fable`.
- `session` must match `^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$` or
  be exactly `--all`.
- `pr` must be all digits.
- Pass values as argv. Never interpolate them into a shell string.

Rejected requests go to `harness/logs/requests.log` with the reason and are dropped. Accepted
ones are logged there too, which makes them visible on the dashboard.

Manual requests do **not** count toward the once-a-day limit: the user asked for them
explicitly. If `launch_research.sh` exits 3 (no free agent slot), keep the request in a
local pending folder and retry it at the next sync rather than dropping it.

## Step 1: make sure this machine trades nothing (do this first)

This is the urgent one. The Windows task "autoQuant WSL" boots WSL at Windows startup "so
autoQuant's systemd units come up". Those units were *stopped* on Oct 12, but nobody checked
whether they were *disabled*. If they still start at boot, every boot of this PC runs a
second copy of every strategy against the same Binance testnet account.

1. Run `systemctl --user list-units 'autoquant*' --all` and `pgrep -af 'live/.*/runner.py'`.
2. Stop and disable everything trading-related:
   ```bash
   systemctl --user disable --now autoquant.target autoquant-dashboard.service \
     autoquant-poller.service autoquant-nightly.timer 'autoquant-strategy@*'
   ```
   The poller is disabled for now; Step 7 re-enables it in the research role.
   **Leave `autoquant-ticks.service` alone.** The tick disk is wanted.
3. Check whether any strategy ran here after Oct 12 2026 16:30 UTC. Look at the newest
   timestamps in `live/*/*/journal.jsonl` and `runner.log`. If one did, it may have placed
   duplicate testnet orders. **Report this to the user** with the strategy names and time
   ranges. Do not "fix" anything in the journals.
4. Do not delete `live/` here. Its old ledgers are dead weight, but they are the WSL-era
   record. They are never synced or used again.

Verify: no `autoquant-strategy@*` unit is enabled or active, and `pgrep` finds no runner.

## Step 2: update the checkout

1. Run `git status` and `git log -1`. This tree is from the WSL era.
2. If there are local changes, **show them to the user and ask** before stashing or
   discarding anything.
3. Then `git fetch && git checkout main && git pull --ff-only`.
4. Confirm the desk's changes are there. All of these must exist:
   - `harness/desk_launch.sh`
   - `harness/remote_inbox.sh`
   - `tests/test_two_hosts.py`
   - a `no_agents_on_desk` function in `harness/session_lib.sh`

   If they are missing, the desk side hasn't been pushed yet. **Stop and tell the user.**
5. Run `.venv/bin/python -m pytest -q tests` (Node tests: `node --test tests/test_dashboard_ui.mjs`).

## Step 3: role and environment

1. Add `AQ_ROLE=research` to `.env`. Keep the Binance testnet keys there: the deployment
   agent's `check_symbols.py --book venue` and `runner.py --check` read them.
2. Make sure `claude` is the user-owned native install at `~/.local/bin/claude`, is current
   (`claude update`) and is logged in to the subscription. Agents run as `seleis`, never root.
3. Make sure `gh auth status` is OK. The agents push branches, open, label and merge PRs.
4. Tick store: confirm `data/ticks` is mounted (`mountpoint "$(realpath data/ticks)"`). If it
   isn't, follow `code/shared/DATA.md` §4 and ensure `autoquant-ticks.service` is enabled.
5. Note the free space on the distro disk and on the tick disk for the heartbeat.

Verify: `bash -c '. harness/session_lib.sh; aq_role'` prints `research`, and
`harness/install_autostart.sh` refuses with exit 5.

## Step 4: reach the desk

1. Test `nc -zv 100.120.177.5 22` (or `timeout 5 bash -c '</dev/tcp/100.120.177.5/22'`)
   **from inside WSL**. The PC is on the tailnet, but WSL2's NAT may or may not route to it.
   If it can't, the fix is WSL mirrored networking (`networkingMode=mirrored` in
   `%UserProfile%\.wslconfig`, then `wsl --shutdown`; README mentions it) or Tailscale inside
   WSL. Ask the user before changing either.
2. Generate a dedicated key with no passphrase, since timers have to use it unattended:
   `ssh-keygen -t ed25519 -N '' -C autoquant-research-host -f ~/.ssh/autoquant_sync`.
3. Give the user the `.pub` line. On the **desk** they run, as root:
   `/root/autoQuant/harness/remote_inbox.sh add-key '<the line>'`.
   You cannot do this yourself: you have no access to the desk.
4. Pin the host key once with
   `ssh-keyscan -t ed25519 100.120.177.5 >> ~/.ssh/known_hosts`. Then ask the user to confirm
   the fingerprint against `ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub` on the desk.

Verify: `rsync -rt -e "ssh -i ~/.ssh/autoquant_sync -o BatchMode=yes -o IdentitiesOnly=yes" aqsync@100.120.177.5:outbox/desk.json /tmp/`
fetches a file listing the desk's strategies. `ssh … aqsync@100.120.177.5 id` must be refused.

## Step 5: `harness/research_host/sync.sh` plus a timer

Write the sync script. It must be idempotent, safe to run every 2 minutes, and exit 0 quietly
when the desk is unreachable (log a line and go). Use
`-e "ssh -i ~/.ssh/autoquant_sync -o BatchMode=yes -o ConnectTimeout=10 -o IdentitiesOnly=yes"`.
Take a `flock` so two runs never overlap.

Order of a pass:
1. **Reconcile the registry.** For every `harness/state/sessions/*.json` with status
   `running` whose pid is not alive on this machine, mark it the way the dashboard would:
   `status=aborted`, `reason=orphaned`, via `session_set` in `session_lib.sh` or the same
   JSON write. The PC was switched off mid-run, so this records the truth before syncing.
   Check first how `session_lib.sh` and `resume_aborted.sh` treat orphans, and reuse that
   logic rather than duplicating it.
2. **Pull** `outbox/allocations.json` into `harness/state/allocations.json` atomically
   (download to a temp file, then `mv`). This host's own copy is meaningless now, and the
   deployment agent must see the desk's. Pull `outbox/desk.json` into `harness/state/desk.json`.
3. **Pull requests** into a local pending folder with `--remove-source-files`, then process
   them as described under "The requests you will receive".
4. **Push** `harness/logs/*.log`, excluding `poller.log`, plus `poller.log` renamed to
   `desktop-poller.log`, to `desktop/logs/`. Then `harness/state/sessions/` to
   `desktop/sessions/`, then the registered uuids' transcripts to `desktop/transcripts/`
   (build the list with `--files-from`).
5. **Write** `heartbeat.json` locally and push it **last**.

Then add a user systemd unit and timer in `harness/research_host/`
(`autoquant-research-sync.service` and `.timer`, `OnBootSec=1min`, `OnUnitActiveSec=2min`)
and an install script `harness/research_host/install.sh`. The install script copies or
symlinks the units into `~/.config/systemd/user/` and enables them. It must refuse unless
`aq_role` is `research`.

Verify: within 2 minutes the desk's dashboard header shows "research host on" (the user can
check https://quant.a-maral.com). The WSL-era sessions show up in "Agent sessions" tagged
`desktop`, with working "convo" and "log" links.

## Step 6: once-a-day research, `harness/research_host/daily.sh` plus a timer

- **Triggers.** A user timer with `OnBootSec=10min`, for when the PC is turned on, and
  `OnCalendar=*-*-* 01:00` with `Persistent=false`, for when it is left on overnight. Both
  call `daily.sh`. WSL comes up at Windows startup via the "autoQuant WSL" task, so a boot
  timer inside WSL is enough. Check that the task still exists and is enabled.
- **The once-a-day rule.** `daily.sh` enforces **at most one nightly batch per local calendar
  day** (Europe/Paris) with a stamp file, `harness/state/research_host/last_batch` containing
  `YYYY-MM-DD`. Write the stamp **before** launching. A PC switched off ten minutes into the
  batch has used its day; the cut-off sessions are resumable from the dashboard. Report
  `research_today` in the heartbeat from this stamp.
- **Guards, each logging a line to a log the sync pushes, e.g. `harness/logs/daily.log`:**
  - skip if `harness/state/research_host/paused` exists, the user's off switch;
  - skip if `harness/state/research_host/skip-YYYY-MM-DD` exists for today;
  - skip if free space on the distro disk is below 20 GB;
  - skip if `claude` or `gh` is not authenticated.

  These come on top of the batch's own guards: max open PRs and the deadline.
- **Running it.** `daily.sh` runs `harness/nightly_research.sh`. It is unchanged: two asset
  classes in sequence, least recently researched first, judged by this host's
  `harness/logs/research-*.log`.
- **Ask the user about the deadline.** `NIGHTLY_DEADLINE_H` defaults to 10 h. Two research
  sessions can run up to ~8 h on a PC that may be turned off sooner. Ask whether they want a
  shorter `RESEARCH_AGENT_TIMEOUT` or a single class per day (`NIGHTLY_COUNT=1`). Don't
  change the defaults on your own.

Verify with `harness/nightly_research.sh --dry-run`, which shows tonight's classes and costs
nothing. Then run `daily.sh` with a fake date via an env override you add for testing, and
check that a second run the same day exits without launching. **Do not let a real batch
start during testing**: it spends the user's subscription. Ask first if you want an
end-to-end run.

## Step 7: the poller in the research role

Enable `autoquant-poller.service` only. It is already in `harness/systemd/`; link or copy it
the way `install_autostart.sh` does, without running that script. With `AQ_ROLE=research` it
drains the revision and review queues and skips the watchdog.

- **The deployment agent runs here now.** After it merges and labels `deployed`, the desk
  launches the strategy within one sweep (≤ 30 min) and labels `vps:launched` or
  `vps:launch-failed`.
- **The dashboard isn't needed here.** Leave `autoquant-dashboard.service` disabled.

Verify: `poll_prs.sh --once` logs a sweep with no `WATCHDOG` line. Its log reaches the desk
as `desktop-poller.log`.

## Step 8: end-to-end check (no paid agents)

1. Ask the user to click **Requeue** on any closed PR in the dashboard (it is harmless; it
   sends `clear_attempts`), or to tell you the time they pressed **Launch** if they want a
   real research run.
2. Watch `harness/logs/requests.log` pick the request up at the next sync.
3. Reboot test, if the user agrees: restart Windows, and confirm three things:
   - WSL comes up with sync running and no strategy unit active,
   - `daily.sh` runs once and only once that day,
   - the desk shows "research host on".

## Rules

- **Never start a strategy or run `install_autostart.sh` on this machine.** Never set
  `AQ_ROLE` to anything but `research` here.
- **Never put logs, transcripts or `.env` content in git.** The repo is public.
- **Don't edit the desk-side contract alone.** That means `desk_launch.sh`,
  `remote_inbox.sh`, the dashboard's remote readers and the file contract above. If you need
  a change there, write it up for the user; the desk has to deploy it too.
- **Commit your new files on a branch and open a PR**, a `harness/...` branch, not
  `research/...`: the poller only reviews `research/*` branches. Leave merging to the user.
  The desk pulls them whenever `desk_launch.sh` next pulls `main`, but they have no effect
  there.
- **When you're done, report to the user:**
  - what Step 1 found,
  - the WSL networking result,
  - the public key you need installed,
  - the deadline question from Step 6,
  - anything you could not verify.
