"""autoQuant control dashboard -- stdlib HTTP server, no framework.

    ./harness/dashboard.sh start          # daemonised
    .venv/bin/python harness/dashboard.py --bind auto --port 8787

Serves `harness/web/index.html` plus a small JSON API. Every slow source (GitHub,
Binance, Claude transcripts) is refreshed on a background thread and served from
cache, so the page stays responsive and a GitHub outage degrades one panel instead
of hanging the request.

Binding
-------
`--bind auto` (default) binds loopback plus the Tailscale address if this host has
one, and nothing else. That is deliberate: the API can place orders, spend money on
agents and stop strategies, so it must never land on a coffee-shop Wi-Fi interface.
Under WSL's default NAT the tailnet address lives on the Windows side and is not
bindable from here -- see harness/README.md for the mirrored-networking fix.
"""
from __future__ import annotations

import argparse
import functools
import glob
import json
import os
import re
import subprocess
import sys
import threading
import time
import traceback
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import metrics  # noqa: E402
import transcript  # noqa: E402
from live_lib import (BASE_URL, LIVE_DIR, REPO_ROOT, PaperBroker,  # noqa: E402
                      allocations_summary, load_env)

HARNESS_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(HARNESS_DIR, "web")
STATE_DIR = os.path.join(HARNESS_DIR, "state")
RUN_DIR = os.path.join(STATE_DIR, "run")
LOGS_DIR = os.path.join(HARNESS_DIR, "logs")
LAUNCH = os.path.join(HARNESS_DIR, "launch_live.sh")
POLLER = os.path.join(HARNESS_DIR, "poll_prs.sh")
RESEARCH = os.path.join(HARNESS_DIR, "launch_research.sh")
RESUME = os.path.join(HARNESS_DIR, "resume_aborted.sh")
SESSIONS_DIR = os.path.join(STATE_DIR, "sessions")

# A deployment is always "<asset-class>/<short-name>": one slash, no traversal. Kept in
# one place because the HTTP layer and the action layer must agree on what is addressable.
STRATEGY_RE = r"[\w.-]+/[\w.-]+"
LOGFILE_RE = r"[\w.-]+\.log"
# Session ids are minted by uuidgen in session_lib.sh; nothing else may name a transcript.
SESSION_RE = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
MAX_BODY_BYTES = 1 << 20

ASSET_CLASSES = ["spot-btc", "spot-eth", "crypto-perps", "crypto-alts", "us-large-cap",
                 "sector-etf", "global-equity-etf", "fx-majors", "rates-bonds",
                 "commodities", "vol-complex"]

# Models a research agent may be launched on. The dashboard is the only caller that needs
# an allowlist -- it is reachable over the tailnet, and this value reaches a subprocess argv.
#
# Aliases, not pinned ids, so a new release is picked up without editing this file: the CLI
# maps `opus` to the newest Opus it knows. That makes the CLI version the thing that decides
# how current the models are -- a root-owned install that cannot self-update was still
# resolving `opus` to Opus 5 after Opus 5.5 shipped, and rejected `claude-opus-5-5` outright.
# CLAUDE_BIN therefore prefers the user-owned native install (see session_lib.sh), the
# nightly job runs `claude update` first, and the registry records the model the alias
# actually resolved to (read back from the result JSON), so a session still says exactly
# what produced it.
RESEARCH_MODELS = {
    "opus":   {"id": "opus",   "label": "Opus (latest)"},
    "sonnet": {"id": "sonnet", "label": "Sonnet (latest)"},
    # Fable is NOT covered by the Claude subscription the rest of this harness runs on --
    # it bills purchased usage credits, so a long research session on it costs real money
    # where an Opus or Sonnet one does not. Offered, flagged, and never the default.
    "fable":  {"id": "fable",  "label": "Fable (latest)", "min_cli": "2.1.251",
               "note": "bills usage credits, not the subscription"},
}
DEFAULT_RESEARCH_MODEL = "opus"

# Approximate Claude pricing, $/Mtok, for the local usage estimate only. A cache write is
# 1.25x input and a cache read 0.1x -- except Fable, where a read is a flat $0.25/Mtok.
# Priced per tier, so a transcript from a previous generation (Sonnet 4.6 at $3/$15) is
# costed at the current rate; the total is an estimate either way.
PRICING = {
    "fable":  {"in": 10.0, "out": 50.0, "cache_w": 12.50, "cache_r": 0.25},
    "opus":   {"in": 5.0,  "out": 25.0, "cache_w": 6.25,  "cache_r": 0.50},
    "sonnet": {"in": 2.0,  "out": 10.0, "cache_w": 2.50,  "cache_r": 0.20},
    "haiku":  {"in": 1.0,  "out": 5.0,  "cache_w": 1.25,  "cache_r": 0.10},
}


def _tier(model: str) -> str:
    m = (model or "").lower()
    for t in ("fable", "opus", "sonnet", "haiku"):
        if t in m:
            return t
    return "sonnet"


def claude_bin() -> str:
    """The binary agents run on -- the same rule as CLAUDE_BIN in session_lib.sh."""
    env = os.environ.get("CLAUDE_BIN")
    if env:
        return env
    native = os.path.expanduser("~/.local/bin/claude")
    return native if os.access(native, os.X_OK) else "claude"


@functools.lru_cache(maxsize=1)
def _cli_version() -> str:
    """Version of the `claude` the agents actually run on (CLAUDE_BIN selects it).

    Cached for the life of the process: `/api/state` is polled every 10 seconds and this
    costs a subprocess. A `claude update` is therefore picked up at the next dashboard
    restart, which is also when the agents would start using the new binary.
    """
    rc, out, _ = sh([claude_bin(), "--version"], 20)
    return out.split()[0] if rc == 0 and out else ""


def _version_below(have: str, want: str) -> bool:
    def parts(v):
        return [int(x) for x in re.findall(r"\d+", v)[:3]] or [0]
    return parts(have) < parts(want)


def research_model_options() -> list:
    """The picker's options, each marked with why it cannot be used, if it cannot.

    A model the installed CLI is too old for is offered but disabled, rather than hidden:
    silently dropping it looks like the feature is missing, and launching onto it would
    fail minutes later inside a detached agent with the reason buried in a log.
    """
    cli = _cli_version()
    out = []
    for key, m in RESEARCH_MODELS.items():
        row = {"key": key, "id": m["id"], "label": m["label"],
               "default": key == DEFAULT_RESEARCH_MODEL}
        if m.get("note"):
            row["note"] = m["note"]
        # What the alias last resolved to on this machine, so "latest" is checkable.
        seen = next((r["model_resolved"] for r in CACHE.get("sessions", [])
                     if r.get("model_resolved") and _tier(r["model_resolved"]) == key), None)
        if seen:
            row["resolved"] = seen
        need = m.get("min_cli")
        if need and cli and _version_below(cli, need):
            row["unavailable"] = (f"needs Claude Code >= {need}; this machine has {cli}. "
                                  "Run `claude update`.")
        out.append(row)
    return out


def sh(cmd, timeout=30, cwd=REPO_ROOT):
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                           timeout=timeout)
        return p.returncode, p.stdout.strip(), p.stderr.strip()
    except subprocess.TimeoutExpired:
        return 124, "", "timed out"
    except Exception as e:  # noqa: BLE001
        return 1, "", str(e)


# --------------------------------------------------------------------------- cache

class Cache:
    """Values refreshed on a background thread; readers never block on the network."""

    def __init__(self):
        self._d = {}
        self._lock = threading.Lock()

    def get(self, key, default=None):
        with self._lock:
            v = self._d.get(key)
        return default if v is None else v["value"]

    def age(self, key):
        with self._lock:
            v = self._d.get(key)
        return None if v is None else time.time() - v["at"]

    def set(self, key, value):
        with self._lock:
            self._d[key] = {"value": value, "at": time.time()}


CACHE = Cache()


# --------------------------------------------------------------------------- sources

def strategy_dirs() -> list:
    out = []
    for meta in sorted(glob.glob(os.path.join(LIVE_DIR, "*", "*", "meta.json"))):
        out.append(os.path.relpath(os.path.dirname(meta), LIVE_DIR))
    for runner in sorted(glob.glob(os.path.join(LIVE_DIR, "*", "*", "runner.py"))):
        n = os.path.relpath(os.path.dirname(runner), LIVE_DIR)
        if n not in out:
            out.append(n)
    return out


def _read_json(path, default=None):
    try:
        with open(path) as fh:
            return json.load(fh)
    except Exception:  # noqa: BLE001
        return default


@functools.lru_cache(maxsize=256)
def systemd_unit(name: str) -> str:
    """Escaping is a pure function of the name, but it costs a subprocess, and
    /api/state asked for it several times per strategy on a 10s poll."""
    rc, out, _ = sh(["systemd-escape", name], 10)
    return f"autoquant-strategy@{out}.service" if rc == 0 else ""


def pid_of(name: str):
    """Live pid, asking systemd first -- a supervised strategy has no pidfile of
    its own, so the pidfile alone would report everything as stopped."""
    unit = systemd_unit(name)
    if unit:
        rc, out, _ = sh(["systemctl", "--user", "show", unit, "-p", "MainPID",
                         "--value"], 10)
        if rc == 0 and out.isdigit() and out != "0":
            return int(out)
        rc, out, _ = sh(["systemctl", "--user", "is-enabled", unit], 10)
        if rc == 0:
            return None          # systemd owns it and says it is not up
    pf = os.path.join(RUN_DIR, name.replace("/", "_") + ".pid")
    if not os.path.exists(pf):
        return None
    try:
        pid = int(open(pf).read().strip())
        os.kill(pid, 0)
        return pid
    except Exception:  # noqa: BLE001
        return None


def proc_started(pid):
    """Wall-clock epoch seconds at which `pid` started, so callers can subtract it
    from now to get an age. It used to return the age itself, which the one caller
    then subtracted from time.time() again -- reporting every daemon as up since
    the epoch, "20705d 16h"."""
    try:
        with open(f"/proc/{pid}/stat") as fh:
            # comm can contain spaces and parens, so split after the LAST ")".
            starttime = int(fh.read().rsplit(")", 1)[1].split()[19])
        with open("/proc/uptime") as fh:
            up = float(fh.read().split()[0])
        hz = os.sysconf("SC_CLK_TCK")
        return (time.time() - up) + starttime / hz
    except Exception:  # noqa: BLE001
        return None


def build_strategies() -> list:
    out = []
    for name in strategy_dirs():
        d = os.path.join(LIVE_DIR, name)
        meta = _read_json(os.path.join(d, "meta.json"), {}) or {}
        state = _read_json(os.path.join(d, "state.json"), {}) or {}
        ledger = _read_json(os.path.join(d, "ledger.json"), {}) or {}
        sched = meta.get("schedule") or state.get("schedule") or "1h"
        pid = pid_of(name)

        # A hung process still reports RUNNING; staleness is what actually catches it.
        stale, last_run_age = False, None
        if state.get("last_run"):
            try:
                lr = datetime.fromisoformat(state["last_run"].replace("Z", "+00:00"))
                last_run_age = (datetime.now(timezone.utc) - lr).total_seconds()
                stale = last_run_age > 2.2 * metrics.SCHEDULE_SECONDS.get(sched, 3600)
            except Exception:  # noqa: BLE001
                pass

        status = "RUNNING" if pid else "STOPPED"
        if pid and stale:
            status = "STALE"

        started = proc_started(pid) if pid else None
        out.append({
            "name": name, "meta": meta, "state": state, "ledger": ledger,
            "schedule": sched, "symbol": meta.get("symbol") or state.get("symbol"),
            "pid": pid, "status": status, "stale": stale,
            "supervised": bool(systemd_unit(name)) and sh(
                ["systemctl", "--user", "is-enabled", systemd_unit(name)], 10)[0] == 0,
            "last_run_age_s": last_run_age,
            "uptime_s": (time.time() - started) if started else None,
            "shadow": state.get("shadow", ledger.get("shadow")),
            # `mode` separates a book that is simulated BY DESIGN from one that wanted
            # the venue and could not reach it. Both have shadow=True, and only the
            # second is a fault, so a UI reading `shadow` alone either cries wolf over
            # every sim strategy or stays silent when a venue strategy degrades.
            "mode": state.get("mode", ledger.get("mode")),
            "book": meta.get("book", "venue"),
            "symbols": meta.get("symbols"),
            "live": metrics.compute(name, sched),
        })
    return out


def refresh_prs():
    rc, out, _ = sh(["gh", "pr", "list", "--state", "open", "--limit", "50", "--json",
                     "number,title,isDraft,labels,headRefName,url,updatedAt,author"], 45)
    if rc != 0:
        return
    try:
        prs = json.loads(out or "[]")
    except json.JSONDecodeError:
        return
    for p in prs:
        p["labelNames"] = [l["name"] for l in p.get("labels", [])]
    CACHE.set("prs", prs)


def refresh_account():
    try:
        b = PaperBroker("BTCUSDT")
        bals = b.account_balances()
        px = b.mark_price()
        CACHE.set("account", {
            "venue": BASE_URL, "ok": True,
            "usdt_free": bals.get("USDT", {}).get("free", 0.0),
            "btc_total": bals.get("BTC", {}).get("free", 0.0) + bals.get("BTC", {}).get("locked", 0.0),
            "btc_price": px,
            "books": allocations_summary(),
        })
    except Exception as e:  # noqa: BLE001
        CACHE.set("account", {"venue": BASE_URL, "ok": False, "error": str(e),
                              "books": allocations_summary()})


def refresh_usage():
    """Rolling Claude usage from local transcripts.

    These token counts come straight from API responses, so they are exact for this
    machine -- but they are NOT your subscription quota. `/usage` is the only source
    for that and it is not available outside an interactive session. Usage from
    claude.ai, mobile or another machine is invisible here, and the weighting each
    token type gets against the 5h/weekly limits is not published.
    """
    now = datetime.now(timezone.utc)
    seen, buckets = set(), {"5h": {}, "7d": {}}
    for f in glob.glob(os.path.expanduser("~/.claude/projects/*/*.jsonl")):
        try:
            fh = open(f)
        except OSError:
            continue
        with fh:
            for line in fh:
                if '"usage"' not in line:
                    continue
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                msg = d.get("message") or {}
                u = msg.get("usage")
                mid = msg.get("id")
                if not u or not mid or mid in seen:
                    continue          # streaming repeats the same message many times
                seen.add(mid)
                try:
                    ts = datetime.fromisoformat(d["timestamp"].replace("Z", "+00:00"))
                except Exception:  # noqa: BLE001
                    continue
                age = (now - ts).total_seconds()
                for label, span in (("5h", 5 * 3600), ("7d", 7 * 86400)):
                    if age <= span:
                        t = _tier(msg.get("model"))
                        b = buckets[label].setdefault(
                            t, {"in": 0, "out": 0, "cache_w": 0, "cache_r": 0, "msgs": 0})
                        b["in"] += u.get("input_tokens", 0)
                        b["out"] += u.get("output_tokens", 0)
                        b["cache_w"] += u.get("cache_creation_input_tokens", 0)
                        b["cache_r"] += u.get("cache_read_input_tokens", 0)
                        b["msgs"] += 1
    res = {}
    for label, tiers in buckets.items():
        cost = sum(sum(v[k] / 1e6 * PRICING[t][k] for k in ("in", "out", "cache_w", "cache_r"))
                   for t, v in tiers.items())
        tot = {k: sum(v[k] for v in tiers.values())
               for k in ("in", "out", "cache_w", "cache_r", "msgs")}
        res[label] = {"tokens": tot, "cost_usd": cost, "by_tier": tiers}
    res["disclaimer"] = ("Exact token counts from local Claude Code transcripts. NOT your "
                         "subscription quota -- the 5h/weekly limits are server-side and "
                         "/usage is unavailable outside an interactive session.")
    CACHE.set("usage", res)


def refresh_data_freshness():
    out = []
    for p in sorted(glob.glob(os.path.join(REPO_ROOT, "data", "*.parquet"))):
        age = time.time() - os.path.getmtime(p)
        out.append({"file": os.path.basename(p), "age_h": age / 3600,
                    "mb": os.path.getsize(p) / 1e6})
    out.sort(key=lambda r: -r["age_h"])
    CACHE.set("data", out)


def refresh_git():
    _, branch, _ = sh(["git", "rev-parse", "--abbrev-ref", "HEAD"], 10)
    _, head, _ = sh(["git", "log", "-1", "--format=%h %s"], 10)
    _, remote, _ = sh(["git", "remote", "get-url", "origin"], 10)
    url = re.sub(r"^git@github\.com:", "https://github.com/", remote or "")
    url = re.sub(r"\.git$", "", url)
    CACHE.set("git", {"branch": branch, "head": head, "url": url})


def transcript_path(reg: dict) -> str:
    """Where Claude Code wrote this registry entry's conversation."""
    return transcript.path_for(reg.get("id") or "", reg.get("cwd") or REPO_ROOT)


def _sessions_by_log() -> dict:
    """Log basename -> session id, so a row in the agent-runs list can open the
    conversation behind it and not only the launcher's log."""
    out = {}
    for f in glob.glob(os.path.join(SESSIONS_DIR, "*.json")):
        if f.endswith(".result.json"):
            continue
        d = _read_json(f) or {}
        if d.get("log") and d.get("id"):
            out[os.path.basename(d["log"])] = d["id"]
    return out


def refresh_agents():
    by_log = _sessions_by_log()
    runs = []
    for f in sorted(glob.glob(os.path.join(LOGS_DIR, "*.log")), key=os.path.getmtime,
                    reverse=True)[:25]:
        base = os.path.basename(f)
        runs.append({"log": base, "mtime": os.path.getmtime(f),
                     "size": os.path.getsize(f), "session": by_log.get(base),
                     "kind": "deploy" if base.startswith("pr-") else
                             ("research" if base.startswith("research-") else "other")})
    CACHE.set("agents", runs)


def _repo_slug():
    rc, out, _ = sh(["gh", "repo", "view", "--json", "nameWithOwner",
                     "--jq", ".nameWithOwner"], 20)
    return out.strip() if rc == 0 else ""


def resolved_model(result_json: str):
    """The model an alias such as `opus` actually ran as, read off the run's result.

    `modelUsage` also lists the small model Claude Code uses for housekeeping, so the
    main model is the non-haiku key -- or haiku itself if that is all there is.
    """
    d = _read_json(result_json)
    if isinstance(d, list):
        d = d[-1] if d else None
    keys = [k.split("[")[0] for k in ((d or {}).get("modelUsage") or {})]
    main = [k for k in keys if "haiku" not in k] or keys
    return main[0] if main else None


def refresh_sessions():
    """The agent-session registry: what ran, how it ended, what can be resumed."""
    out = []
    for f in glob.glob(os.path.join(SESSIONS_DIR, "*.json")):
        if f.endswith(".result.json"):
            continue
        try:
            d = json.load(open(f))
        except Exception:  # noqa: BLE001
            continue
        pid = d.get("pid")
        if d.get("status") == "running" and pid:
            try:
                os.kill(int(pid), 0)
            except (OSError, ValueError):
                # The process is gone but nothing wrote a verdict -- the supervisor was
                # killed too (a reboot, a kill -9). Show it as parked rather than as a
                # run that is still going, which is what it would look like forever.
                d["status"], d["reason"] = "aborted", "orphaned"
        out.append({k: d.get(k) for k in
                    ("id", "kind", "target", "status", "reason", "launched_at",
                     "ended_at", "log", "model")}
                   | {"resumes": len(d.get("resumes") or []),
                      "model_resolved": resolved_model(f[:-5] + ".result.json"),
                      "has_transcript": os.path.exists(transcript_path(d))})
    out.sort(key=lambda r: r.get("launched_at") or "", reverse=True)
    CACHE.set("sessions", out[:40])


def poller_status():
    pf = os.path.join(STATE_DIR, "poller.pid")
    if os.path.exists(pf):
        try:
            pid = int(open(pf).read().strip())
            os.kill(pid, 0)
            return {"running": True, "pid": pid}
        except Exception:  # noqa: BLE001
            pass
    return {"running": False, "pid": None}


REFRESHERS = [(refresh_prs, 120), (refresh_account, 45), (refresh_usage, 120),
              (refresh_data_freshness, 300), (refresh_git, 120), (refresh_agents, 30),
              (refresh_sessions, 20)]


def refresher_loop(stop: threading.Event):
    last = {}
    while not stop.is_set():
        for fn, every in REFRESHERS:
            if time.time() - last.get(fn.__name__, 0) >= every:
                try:
                    fn()
                except Exception:  # noqa: BLE001
                    traceback.print_exc()
                last[fn.__name__] = time.time()
        stop.wait(5)


# --------------------------------------------------------------------------- actions

# Run out-of-process on purpose: flattening loads the broker, talks to the venue and can
# block, and none of that belongs on a dashboard request thread.
FLATTEN_SRC = """
import json, os, sys
sys.path.insert(0, 'harness')
from live_lib import broker_from_meta
d = os.path.join('live', sys.argv[1])
m = json.load(open(os.path.join(d, 'meta.json')))
b = broker_from_meta(m, state_file=os.path.join(d, 'ledger.json'))
b.preflight()
print(json.dumps(b.flatten(), default=str))
"""


def do_action(body: dict) -> dict:
    a = body.get("action")
    name = body.get("strategy", "")
    if name and (".." in name or not re.fullmatch(STRATEGY_RE, name)):
        return {"ok": False, "error": "bad strategy name"}

    if a in ("start", "stop", "restart"):
        # An empty name reaches launch_live.sh as an empty argument, where it resolves to
        # the live/ directory itself rather than to any strategy.
        if not name:
            return {"ok": False, "error": "no strategy given"}
        rc, out, err = sh([LAUNCH, a, name], 120)
        return {"ok": rc == 0, "output": out or err}
    if a == "flatten":
        if not name:
            return {"ok": False, "error": "no strategy given"}
        # The name goes in as argv, not spliced into the source text. The regex above
        # already bars quotes, but a validator and a code generator drifting apart is
        # exactly how that stops being true.
        rc, out, err = sh([os.path.join(REPO_ROOT, ".venv/bin/python"), "-c",
                           FLATTEN_SRC, name], 90)
        return {"ok": rc == 0, "output": out or err}
    if a == "kill_all":
        stopped, failed = [], []
        for s in strategy_dirs():
            rc, out, err = sh([LAUNCH, "stop", s], 60)
            (stopped if rc == 0 else failed).append(s if rc == 0 else f"{s}: {err or out}")
        # Report the failures. This used to answer ok:True unconditionally, so a kill
        # switch that had stopped nothing still showed a tick.
        msg = "stopped: " + (", ".join(stopped) or "none")
        if failed:
            msg += "\nFAILED: " + "; ".join(failed)
        return {"ok": not failed, "output": msg}
    if a == "flatten_all":
        outs, ok = [], True
        for s in strategy_dirs():
            r = do_action({"action": "flatten", "strategy": s})
            ok = ok and r.get("ok", False)
            outs.append(f"{s}: {r.get('output') or r.get('error', '')}")
        return {"ok": ok, "output": "\n".join(outs)}
    if a in ("poller_start", "poller_stop"):
        rc, out, err = sh([POLLER, "--start" if a == "poller_start" else "--stop"], 60)
        return {"ok": rc == 0, "output": out or err}
    if a == "poller_sweep":
        rc, out, err = sh([POLLER, "--once"], 600)
        return {"ok": rc == 0, "output": out or err}
    if a in ("resume_aborted", "resume_session"):
        arg = str(body.get("session", "")).strip() or "--all"
        if arg != "--all" and not re.fullmatch(r"[0-9a-fA-F-]{36}", arg):
            return {"ok": False, "error": "bad session id"}
        rc, out, err = sh([RESUME, arg], 120)
        refresh_sessions()
        return {"ok": rc == 0, "output": out or err}
    if a == "requeue_pr":
        num = str(body.get("pr", "")).strip()
        if not num.isdigit():
            return {"ok": False, "error": "bad pr number"}
        # `gh pr edit` is broken on this machine -- it resolves the PR through a GraphQL
        # query asking for projectCards, which GitHub now refuses outright, so every call
        # failed silently and this button did nothing at all. The issues API is fine.
        slug = _repo_slug()
        for lab in ("invalid", "needs-revision", "harness:failed",
                    "harness:processing", "harness:paused", "harness:exhausted"):
            sh(["gh", "api", "-X", "DELETE",
                f"repos/{slug}/issues/{num}/labels/{lab.replace(':', '%3A')}"], 30)
        try:
            os.remove(os.path.join(STATE_DIR, f"attempts-{num}"))
        except OSError:
            pass
        refresh_prs()
        return {"ok": True, "output": f"PR #{num} requeued"}
    if a == "launch_research":
        ac = body.get("asset_class", "")
        if ac not in ASSET_CLASSES:
            return {"ok": False, "error": "unknown asset class"}
        key = body.get("model") or DEFAULT_RESEARCH_MODEL
        if key not in RESEARCH_MODELS:
            return {"ok": False, "error": f"unknown model {key!r}"}
        opt = next(o for o in research_model_options() if o["key"] == key)
        if opt.get("unavailable"):
            # Caught here rather than at the venue: the agent is detached, so an
            # unsupported model would otherwise surface as a session that died silently.
            return {"ok": False, "error": f"{opt['label']} {opt['unavailable']}"}
        seed = (body.get("seed") or "")[:500]
        rc, out, err = sh([RESEARCH, ac, seed, "--model", opt["id"]], 60)
        return {"ok": rc == 0, "output": out or err}
    return {"ok": False, "error": f"unknown action {a!r}"}


# --------------------------------------------------------------------------- http

class Handler(BaseHTTPRequestHandler):
    server_version = "autoQuant"

    def log_message(self, fmt, *args):
        pass                      # the access log is noise here

    def _send(self, code, payload, ctype="application/json"):
        body = payload if isinstance(payload, bytes) else json.dumps(
            payload, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):
        # parse_qs, not a hand-rolled split: every strategy name contains a "/", so the
        # browser sends it percent-encoded and an undecoded value matches no name at all.
        # That single omission broke Log, Trades and every equity sparkline at once.
        split = urlsplit(self.path)
        path = split.path
        qs = {k: v[0] for k, v in parse_qs(split.query).items() if v}
        if path in ("/", "/index.html"):
            f = os.path.join(WEB_DIR, "index.html")
            if not os.path.exists(f):
                return self._send(404, b"index.html missing", "text/plain")
            return self._send(200, open(f, "rb").read(), "text/html; charset=utf-8")
        if path == "/api/state":
            strategies = build_strategies()
            return self._send(200, {
                "now": datetime.now(timezone.utc).isoformat(),
                "strategies": strategies,
                "correlation": metrics.correlation(
                    [s["name"] for s in strategies],
                    {s["name"]: s["schedule"] for s in strategies}),
                "poller": poller_status(),
                "prs": CACHE.get("prs", []),
                "account": CACHE.get("account", {}),
                "usage": CACHE.get("usage", {}),
                "data": CACHE.get("data", []),
                "git": CACHE.get("git", {}),
                "agents": CACHE.get("agents", []),
                "sessions": CACHE.get("sessions", []),
                "asset_classes": ASSET_CLASSES,
                "research_models": research_model_options(),
                "ages": {k: CACHE.age(k) for k in
                         ("prs", "account", "usage", "data", "git", "agents",
                          "sessions")},
            })
        if path == "/api/series":
            name = qs.get("strategy", "")
            if not re.fullmatch(STRATEGY_RE, name or ""):
                return self._send(400, {"error": "bad strategy"})
            return self._send(200, metrics.equity_series(name))
        if path == "/api/portfolio":
            # Capital comes from meta.json where the deploy agent recorded it, and from
            # the journal otherwise; a book with neither is left out rather than summed
            # at an assumed size.
            books = [{"name": s["name"],
                      "capital_usdt": (s["meta"].get("capital_usdt")
                                       or s["state"].get("capital_usdt"))}
                     for s in build_strategies()]
            return self._send(200, metrics.portfolio_series(books))
        if path == "/api/journal":
            name = qs.get("strategy", "")
            if not re.fullmatch(STRATEGY_RE, name or ""):
                return self._send(400, {"error": "bad strategy"})
            rows = [r for r in metrics.read_journal(name) if r.get("event") != "heartbeat"]
            return self._send(200, rows[-200:])
        if path == "/api/log":
            name = qs.get("strategy", "")
            try:
                n = min(max(int(qs.get("n") or 200), 1), 2000)
            except ValueError:
                return self._send(400, {"error": "bad line count"})
            fname = qs.get("file", "")
            if re.fullmatch(STRATEGY_RE, name or ""):
                f = os.path.join(LIVE_DIR, name, "runner.log")
            elif re.fullmatch(LOGFILE_RE, fname or ""):
                # A bare `*.log` basename: no separator can appear in the character
                # class, so this cannot escape LOGS_DIR.
                f = os.path.join(LOGS_DIR, fname)
            else:
                return self._send(400, {"error": "bad target"})
            if not os.path.exists(f):
                return self._send(404, {"error": "no log"})
            _, out, _ = sh(["tail", "-n", str(n), f], 20)
            return self._send(200, {"text": out})
        if path == "/api/transcript":
            sid = qs.get("session", "")
            if not re.fullmatch(SESSION_RE, sid or ""):
                return self._send(400, {"error": "bad session"})
            reg = _read_json(os.path.join(SESSIONS_DIR, sid + ".json")) or {"id": sid}
            f = transcript_path(reg)
            if not os.path.exists(f):
                return self._send(404, {"error": "no transcript for this session -- it may "
                                                 "predate the registry or have been cleaned up"})
            out = transcript.render(f)
            # `model` stays what the transcript says ran; the registry holds the alias.
            out.update({k: reg.get(k) for k in ("kind", "target", "status")})
            out["model_alias"] = reg.get("model")
            return self._send(200, out)
        return self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/api/action":
            return self._send(404, {"error": "not found"})
        try:
            n = int(self.headers.get("Content-Length") or 0)
            if n < 0 or n > MAX_BODY_BYTES:
                return self._send(413, {"ok": False, "error": "body too large"})
            body = json.loads(self.rfile.read(n) or b"{}")
            if not isinstance(body, dict):
                return self._send(400, {"ok": False, "error": "body must be an object"})
        except Exception:  # noqa: BLE001
            return self._send(400, {"ok": False, "error": "bad body"})
        try:
            return self._send(200, do_action(body))
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            return self._send(500, {"ok": False, "error": str(e)})


def tailscale_ip():
    """This host's tailnet address, if it is bindable from here."""
    try:
        out = subprocess.run(["ip", "-4", "-o", "addr"], capture_output=True,
                             text=True, timeout=10).stdout
    except Exception:  # noqa: BLE001
        return None
    for line in out.splitlines():
        m = re.search(r"inet (100\.\d+\.\d+\.\d+)/", line)
        if m:
            return m.group(1)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bind", default="auto",
                    help="'auto' (loopback + tailnet), or an explicit address")
    ap.add_argument("--port", type=int, default=8788)
    args = ap.parse_args()
    load_env()

    if args.bind == "auto":
        addrs = ["127.0.0.1"]
        ts = tailscale_ip()
        if ts:
            addrs.append(ts)
        else:
            print("NOTE: no tailnet address is bindable from this host, so the dashboard "
                  "is loopback-only.\n      Under WSL's default NAT the Tailscale address "
                  "lives on the Windows side; see\n      harness/README.md "
                  "(mirrored networking) to reach it from your phone.", flush=True)
    else:
        addrs = [args.bind]

    stop = threading.Event()
    threading.Thread(target=refresher_loop, args=(stop,), daemon=True).start()

    servers = []
    for a in addrs:
        try:
            srv = ThreadingHTTPServer((a, args.port), Handler)
        except OSError as e:
            print(f"WARNING: cannot bind {a}:{args.port}: {e}", flush=True)
            continue
        servers.append(srv)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        print(f"listening on http://{a}:{args.port}", flush=True)
    if not servers:
        print("ERROR: no address could be bound", file=sys.stderr)
        return 1
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        stop.set()
        for s in servers:
            s.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
