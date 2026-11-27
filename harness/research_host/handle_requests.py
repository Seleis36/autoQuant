#!/usr/bin/env python3
"""Act on the dashboard requests the desk left in outbox/requests/ (see PLAN.md).

    handle_requests.py <pending-dir>

sync.sh pulls the desk's request files into <pending-dir> (deleting them on the desk) and
then runs this. Each file is one request: {"id", "action", "requested_at", ...}.

Anything that can write the desk's outbox can write a request, so every field is checked
against a fixed allow-list here, and values only ever reach a launcher as argv -- never
through a shell string. Every request, accepted or rejected, gets one line in
harness/logs/requests.log, which the sync pushes back so the dashboard shows it.

A request is deleted once handled, with one exception: a research launch refused for want
of a free agent slot (launch_research.sh exit 3) stays in <pending-dir> and is retried at
the next sync. Manual requests do not count toward daily.sh's once-a-day limit.
"""
import datetime
import json
import os
import re
import subprocess
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HARNESS = os.path.join(REPO, "harness")
LOG = os.environ.get("AQ_REQUESTS_LOG") or os.path.join(HARNESS, "logs", "requests.log")

ASSET_CLASSES = {"spot-btc", "spot-eth", "crypto-perps", "crypto-alts", "us-large-cap",
                 "sector-etf", "global-equity-etf", "fx-majors", "rates-bonds",
                 "commodities", "vol-complex"}
MODELS = {"opus", "sonnet", "fable"}
UUID_RE = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
FILE_RE = r"[0-9A-Za-z]+-[0-9a-f]+\.json"      # the dashboard's <YYYYmmddTHHMMSS>-<hex>
SEED_MAX = 500
LAUNCH_TIMEOUT_S = 120     # the launchers detach their agent and return within seconds
NO_SLOT = 3                # launch_research.sh: every research slot is busy


def log(rid, verdict, detail):
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    detail = " ".join(str(detail).split())[:600]
    with open(LOG, "a") as fh:
        fh.write(f"[{ts}] {verdict} {rid}: {detail}\n")


def validate(req):
    """(argv, None) for a request this host may act on, or (None, why) for one it may not."""
    if not isinstance(req, dict):
        return None, "not a JSON object"
    action = req.get("action")
    if action == "launch_research":
        ac, seed, model = req.get("asset_class"), req.get("seed", ""), req.get("model")
        if ac not in ASSET_CLASSES:
            return None, f"unknown asset_class {str(ac)[:40]!r}"
        if not os.path.isfile(os.path.join(REPO, ".claude", "commands",
                                           f"{ac}-quant-research.md")):
            return None, f"no research command for {ac}"
        if seed is None:
            seed = ""
        if not isinstance(seed, str) or len(seed) > SEED_MAX:
            return None, f"seed must be a string of at most {SEED_MAX} characters"
        if model not in MODELS:
            return None, f"model must be one of {sorted(MODELS)}"
        return [os.path.join(HARNESS, "launch_research.sh"), ac, seed, "--model", model], None
    if action == "resume":
        s = req.get("session")
        if not isinstance(s, str) or not (s == "--all" or re.fullmatch(UUID_RE, s)):
            return None, "session must be a session uuid or --all"
        return [os.path.join(HARNESS, "resume_aborted.sh"), s], None
    if action == "clear_attempts":
        pr = req.get("pr")
        if isinstance(pr, bool) or not re.fullmatch(r"[0-9]{1,6}", str(pr)):
            return None, "pr must be a PR number"
        return ["clear_attempts", str(int(str(pr)))], None
    return None, f"unknown action {str(action)[:40]!r}"


def act(argv):
    """Run one validated request. Returns (keep_for_retry, verdict, detail)."""
    if argv[0] == "clear_attempts":
        f = os.path.join(HARNESS, "state", f"attempts-{argv[1]}")
        existed = os.path.exists(f)
        if existed:
            os.remove(f)
        return False, "DONE", f"clear_attempts PR {argv[1]}" + ("" if existed else " (none recorded)")
    try:
        p = subprocess.run(argv, cwd=REPO, stdin=subprocess.DEVNULL, capture_output=True,
                           text=True, timeout=LAUNCH_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return False, "FAILED", f"{os.path.basename(argv[0])} did not return in {LAUNCH_TIMEOUT_S}s"
    out = (p.stdout + " " + p.stderr).strip()
    name = os.path.basename(argv[0])
    shown = [a if len(a) < 80 else a[:77] + "..." for a in argv[1:]]
    if name == "launch_research.sh" and p.returncode == NO_SLOT:
        return True, "WAITING", f"{name} {shown}: no free agent slot, retrying next sync"
    verdict = "DONE" if p.returncode == 0 else f"FAILED rc={p.returncode}"
    return False, verdict, f"{name} {shown}: {out[-400:]}"


def main(pending):
    for name in sorted(os.listdir(pending)):
        path = os.path.join(pending, name)
        if not os.path.isfile(path) or not name.endswith(".json"):
            continue
        rid = name[:-5]
        if not re.fullmatch(FILE_RE, name):
            log(rid[:60], "REJECTED", "bad request file name")
            os.remove(path)
            continue
        try:
            with open(path) as fh:
                req = json.load(fh)
        except (OSError, ValueError) as e:
            log(rid, "REJECTED", f"unreadable: {e}")
            os.remove(path)
            continue
        argv, why = validate(req)
        if argv is None:
            log(rid, "REJECTED", why)
            os.remove(path)
            continue
        keep, verdict, detail = act(argv)
        if verdict != "WAITING" or not os.path.exists(path + ".waiting"):
            log(rid, verdict, detail)          # a waiting request logs once, not every sync
        if keep:
            open(path + ".waiting", "w").close()
        else:
            os.remove(path)
            if os.path.exists(path + ".waiting"):
                os.remove(path + ".waiting")


if __name__ == "__main__":
    if len(sys.argv) != 2 or not os.path.isdir(sys.argv[1]):
        sys.exit("usage: handle_requests.py <pending-dir>")
    main(sys.argv[1])
