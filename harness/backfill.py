"""
Replay the bars a stopped SIMULATED book missed, so its track has no dead zone.

A daemon that is down simply does not trade: when it comes back it resumes its ledger and
acts on the current bar, and the journal -- which is the equity curve -- draws a straight
line over the outage. The positions it held were marked through the gap only as one jump
at restart, and every rebalance it would have made in between is lost. On a `sim` book
none of that is necessary: fills are modelled against a quote source, so the bars can be
replayed after the fact with the same fill model the daemon would have used.

How the weights are recovered without a point-in-time copy of every data source: each
runner computes its weight by calling the research's own causal signal function
(`target_weight(s)`, `blend_weights`, ...) over the full history and taking the last row.
This wraps that function, calls the runner's own `compute_weight(s)` once with today's
data, and keeps the whole series it returned -- whose row for a missed bar is the weight
the daemon would have computed then, provided the signal has no lookahead (the deployment
review checks exactly that: live weight == backtest weight, bar for bar). The live weight
returned by the same call is checked against the series' last row before anything is
written, so a runner whose post-processing this does not reproduce is refused, not
approximated.

What it is NOT: a recovery of venue fills. A `venue` book (Binance spot testnet) never
filled those orders and cannot have them invented after the fact, so it is refused.
Replayed rows carry `"backfill": true`; the inputs are today's vintage of the data
(a revised yfinance close or a late COT report is seen as it is now, not as it was).

    .venv/bin/python harness/backfill.py rates-bonds/treasury-flow-calendar --dry-run
    .venv/bin/python harness/backfill.py rates-bonds/treasury-flow-calendar

One strategy per process: every runner imports a module called `strategy`, so two in one
interpreter would share the first one's signal. Stop the daemon first -- this refuses a
strategy whose state says it is running.
"""
from __future__ import annotations

import argparse
import functools
import json
import os
import shutil
import sys
import types
from datetime import datetime, timezone
from typing import Optional

import pandas as pd

HARNESS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HARNESS_DIR)

import live_lib  # noqa: E402
from live_lib import (LIVE_DIR, REPO_ROOT, _INTERVAL_SECONDS, MarketData,  # noqa: E402
                      QuoteSource, StrategyRunner)
from portfolio import SimPortfolioBroker  # noqa: E402

BACKUP_DIR = os.path.join(HARNESS_DIR, "state", "backfill")
STRATEGY_FNS = ("target_weight", "target_weights", "blend_weights", "alt_bab_weights")
TOL = 1e-9

#: Module constants a runner sizes its fetch with that are too short to reach back over an
#: outage. Only for signals whose weight does not depend on the window length.
OVERRIDES = {
    # The weight is a pure function of the bar's timestamp; 200 bars is only an index.
    "spot-eth/options-expiry-drift": {"HOURLY_BARS": 1000},
}


# --------------------------------------------------------------------------- loading

def load_runner(name: str):
    """Execute live/<name>/runner.py as the daemon would, but keep the runner it builds.

    `StrategyRunner.cli` is the last thing every runner calls; swapping it for a capture
    gives back the exact broker (costs, shorting, universe) the daemon trades, with no
    second copy of each runner's constructor arguments to drift out of date.
    """
    path = os.path.join(LIVE_DIR, name, "runner.py")
    built = []
    cli = StrategyRunner.cli
    StrategyRunner.cli = lambda self, argv=None: built.append(self)
    argv, cwd = sys.argv, os.getcwd()
    sys.argv = [path]
    os.chdir(os.path.dirname(path))
    try:
        # Run as __main__ so the runner's own `if __name__ == "__main__"` block builds it,
        # but never registered in sys.modules: this process keeps its own __main__.
        mod = types.ModuleType("__main__")
        mod.__file__ = path
        with open(path) as fh:
            exec(compile(fh.read(), path, "exec"), mod.__dict__)
    finally:
        StrategyRunner.cli = cli
        sys.argv = argv
        os.chdir(cwd)
    if len(built) != 1:
        raise RuntimeError(f"{name}: runner.py built {len(built)} runners, expected 1")
    return mod, built[0]


class Capture:
    """Keeps what the outermost call of a wrapped signal function returned."""

    def __init__(self):
        self.value = None
        self.depth = 0

    def wrap(self, fn):
        if getattr(fn, "_backfill_capture", False):
            return fn

        @functools.wraps(fn)
        def inner(*a, **kw):
            self.depth += 1
            try:
                out = fn(*a, **kw)
            finally:
                self.depth -= 1
            if self.depth == 0:
                self.value = out
            return out

        inner._backfill_capture = True
        return inner

    def install(self, mod) -> list:
        """Wrap the signal functions the runner reaches, by name or through a module."""
        code_dir = os.path.join(REPO_ROOT, "code")
        hooked = []
        for k, v in list(vars(mod).items()):
            if k in STRATEGY_FNS and callable(v):
                setattr(mod, k, self.wrap(v))
                hooked.append(k)
            elif isinstance(v, types.ModuleType) and str(getattr(v, "__file__", "")).startswith(code_dir):
                for fn in STRATEGY_FNS:
                    if callable(getattr(v, fn, None)):
                        setattr(v, fn, self.wrap(getattr(v, fn)))
                        hooked.append(f"{k}.{fn}")
        return hooked


# --------------------------------------------------------------------------- prices

class AsOfQuotes(QuoteSource):
    """A daily quote source frozen at one past session: its close, from the shared cache."""

    def __init__(self, inner, day: pd.Timestamp):
        self.inner = inner
        self.day = pd.Timestamp(day)
        self.name = inner.name
        self.bars_per_year_daily = inner.bars_per_year_daily

    def price(self, symbol: str) -> float:
        df = self.inner.md.daily(symbol, cache_hours=1e9)       # no refetch: as cached now
        c = df["Close"].dropna()
        c = c[c.index <= self.day]
        if c.empty or not c.iloc[-1] > 0:
            raise RuntimeError(f"{symbol}: no positive close on or before {self.day.date()}")
        return float(c.iloc[-1])

    def bar_key(self, symbol: str) -> Optional[str]:
        return self.day.date().isoformat()

    def daily_bars_per_year(self, symbol: str) -> float:
        return self.inner.daily_bars_per_year(symbol)


class FixedQuote(QuoteSource):
    """A continuous market's price at one past boundary."""

    def __init__(self, inner, px: float):
        self.inner = inner
        self.name = inner.name
        self.bars_per_year_daily = inner.bars_per_year_daily
        self.px = float(px)

    def price(self, symbol: str) -> float:
        return self.px

    def daily_bars_per_year(self, symbol: str) -> float:
        return self.inner.daily_bars_per_year(symbol)


# --------------------------------------------------------------------------- weights

def is_basket(runner) -> bool:
    return isinstance(runner.broker, SimPortfolioBroker)


def weights_at(runner, W, key):
    """The weight the runner would have returned had its last row been `key`."""
    row = W.loc[key]
    if not is_basket(runner):
        if isinstance(row, pd.Series):
            raise RuntimeError(f"scalar runner but the signal returned a frame at {key}")
        w = float(row)
        if w != w:
            raise RuntimeError(f"NaN weight at {key}")
        return w
    if row.isna().any():
        raise RuntimeError(f"NaN weights at {key}: {row[row.isna()].index.tolist()[:10]}")
    out = {s: float(v) for s, v in row.items() if v != 0.0}
    b = runner.broker
    unknown = sorted(s for s in out if s not in b.symbols)
    if unknown and not b.open_universe:
        raise RuntimeError(f"weights at {key} name symbols the book does not hold: {unknown}")
    for s in b.symbols:
        out.setdefault(s, 0.0)
    return out


def same_weights(runner, live, replayed) -> bool:
    if not is_basket(runner):
        b = runner.broker
        return abs(b._clamp_weight(live) - b._clamp_weight(replayed)) < TOL
    keys = set(live) | set(replayed)
    return all(abs(live.get(k, 0.0) - replayed.get(k, 0.0)) < TOL for k in keys)


# --------------------------------------------------------------------------- the plan

def last_rebalance_ts(runner) -> Optional[pd.Timestamp]:
    last = None
    with open(runner.journal_path) as fh:
        for line in fh:
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("event") == "rebalance":
                last = r["ts"]
    return pd.Timestamp(last) if last else None


def plan(mod, runner, W, now: pd.Timestamp) -> list:
    """[(journal key or None, wake time, weight-row label, price setter)], oldest first."""
    b = runner.broker
    offset = pd.Timedelta(seconds=runner.offset_s)
    idx = pd.DatetimeIndex(W.index)
    steps = []

    current = b.bar_key()
    if current is not None:
        # A session market: the runner acts once per new bar key. A yfinance crypto series
        # publishes the forming UTC day, so its key runs one day ahead of the last closed
        # row the signal used -- read the lag off the live state rather than assume it.
        if runner._last_bar is None:
            raise RuntimeError("no last_bar in state.json -- nothing to replay from")
        lag = pd.Timestamp(current) - idx[-1].normalize()
        if lag not in (pd.Timedelta(0), pd.Timedelta(days=1)):
            raise RuntimeError(f"bar key {current} vs last signal row {idx[-1].date()}: "
                               "unexpected lag, refusing to guess the mapping")
        last = pd.Timestamp(runner._last_bar)
        own_prices = is_basket(runner) and type(b).prices is not SimPortfolioBroker.prices
        for d in idx:
            key = d.normalize() + lag
            if not (last < key <= pd.Timestamp(current)):
                continue
            wake = (d.normalize() + pd.Timedelta(days=1)).tz_localize("UTC") + offset
            if wake >= now:
                continue
            if own_prices:
                # The book marks itself off the module's clock (cef, large-cap).
                def setter(d=d):
                    mod._state["trade_bar"] = d.date().isoformat()
            else:
                def setter(d=d, inner=b.quotes):
                    b.quotes = AsOfQuotes(inner, d)
            steps.append((key.date().isoformat(), wake, d, setter))
        return steps

    # A continuous market: one rebalance per schedule boundary, priced at the boundary.
    step = pd.Timedelta(seconds=_INTERVAL_SECONDS[runner.schedule])
    since = last_rebalance_ts(runner)
    if since is None:
        raise RuntimeError("no rebalance in the journal -- nothing to replay from")
    first = (since - offset).floor(step) + step
    lastb = (now - offset).floor(step)
    if first > lastb:
        return []
    bars = pd.date_range(first, lastb, freq=step)
    # The close of the bar ending at the boundary is the price at the boundary, and it is a
    # closed bar -- the one opening there may still be forming.
    need = int((now - first) / step) + 5
    hist = MarketData(source="public").history(b.symbol, runner.schedule, bars=max(need, 50))
    close = hist["Close"]
    for B in bars:
        opened = B - step
        if opened not in close.index:
            raise RuntimeError(f"no {runner.schedule} {b.symbol} bar opening {opened}")
        px = float(close.loc[opened])
        label = opened.tz_localize(None)
        if label not in idx:
            raise RuntimeError(f"signal series has no row {label} (it starts {idx[0]}) -- "
                               "the runner's fetch window is shorter than the outage")

        def setter(px=px, inner=b.quotes):
            b.quotes = FixedQuote(inner, px)

        steps.append((None, B + offset, label, setter))
    return steps


# --------------------------------------------------------------------------- main

def backfill(name: str, dry_run: bool = False) -> dict:
    meta = json.load(open(os.path.join(LIVE_DIR, name, "meta.json")))
    if meta.get("book", live_lib.VENUE_BOOK) != live_lib.SIM_BOOK:
        raise SystemExit(f"{name} trades on the venue book -- its missed fills cannot be "
                         "replayed; restart it and leave the gap")
    st = json.load(open(os.path.join(LIVE_DIR, name, "state.json")))
    if st.get("status") == "running":
        raise SystemExit(f"{name}: state.json says running -- stop the daemon first")

    mod, runner = load_runner(name)
    for k, v in OVERRIDES.get(name, {}).items():
        setattr(mod, k, v)
    cap = Capture()
    hooked = cap.install(mod)
    if not hooked:
        raise SystemExit(f"{name}: found no signal function to capture ({STRATEGY_FNS})")
    b = runner.broker
    if dry_run:
        b.state_file = None                    # nothing reaches the ledger file

    now = pd.Timestamp.now(tz="UTC")
    fn = runner.compute_weights if is_basket(runner) else runner.compute_weight
    live = fn(now.to_pydatetime())
    W = cap.value
    if not isinstance(W, (pd.Series, pd.DataFrame)) or W.empty:
        raise SystemExit(f"{name}: captured {type(W).__name__} from {hooked}, not a series")
    W = W[~W.index.duplicated(keep="last")].sort_index()

    # The live call used the series' last row. Read it back through the same mapping the
    # replay uses: if that disagrees with what the runner returned, the replayed weights
    # would not be the runner's weights.
    if not same_weights(runner, live, weights_at(runner, W, W.index[-1])):
        raise SystemExit(f"{name}: last series row {W.index[-1]} does not reproduce the "
                         f"live weight -- the runner post-processes in a way this cannot")

    steps = plan(mod, runner, W, now)
    eq0 = b.equity() if not is_basket(runner) or type(b).prices is SimPortfolioBroker.prices \
        else None
    rows = []
    for key, wake, label, set_price in steps:
        set_price()
        w = weights_at(runner, W, label)
        rep = b.set_target_weights(w) if is_basket(runner) else b.set_target_weight(w)
        rows.append({"ts": wake.isoformat(), "strategy": runner.name, "event": "rebalance",
                     **runner._journal_context(key), **rep, "backfill": True})

    # `equity_if_held`: the book left as it was at the stop, marked now -- what the dead
    # zone would have shown as one jump at restart.
    out = {"strategy": name, "bars": len(rows), "hooked": hooked,
           "first": rows[0]["ts"] if rows else None, "last": rows[-1]["ts"] if rows else None,
           "equity_if_held": eq0, "equity_after": rows[-1]["equity"] if rows else eq0,
           "trades": sum(1 for r in rows if r.get("traded")), "dry_run": dry_run,
           "rows": [(r["ts"][:16], r.get("bar"), round(r["weight"], 4),
                     round(r["price"], 4) if r.get("price") else None,
                     round(r["equity"], 2), r.get("traded")) for r in rows]}
    if dry_run or not rows:
        return out

    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    bk = os.path.join(BACKUP_DIR, f"{name.replace('/', '_')}-{stamp}")
    os.makedirs(bk, exist_ok=True)
    for f in ("journal.jsonl", "ledger.json", "state.json"):
        src = os.path.join(runner.dir, f)
        if os.path.exists(src):
            shutil.copy2(src, bk)

    b._save_ledger()
    with open(runner.journal_path, "a") as fh:
        for r in rows:
            fh.write(json.dumps(r, default=str) + "\n")
        fh.write(json.dumps({"ts": datetime.now(timezone.utc).isoformat(),
                             "strategy": runner.name, "event": "backfill",
                             "bars": len(rows), "from": out["first"], "to": out["last"],
                             "backup": os.path.relpath(bk, REPO_ROOT)}) + "\n")
    last = rows[-1]
    if steps[-1][0] is not None:
        runner._last_bar = steps[-1][0]
    extra = ({"gross": last["gross"], "net": last["net"], "positions": last["positions"]}
             if is_basket(runner) else {"last_price": last.get("price")})
    runner._save_state(status="stopped", last_weight=last["weight"], equity=last["equity"],
                       position=b.position() if not is_basket(runner) else None,
                       capital_usdt=b.capital_usdt, last_run=last["ts"],
                       last_bar=runner._last_bar, waiting_for_new_bar=False,
                       backfilled_through=last["ts"], **extra)
    out["backup"] = bk
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("strategy", help="<asset>/<name> under live/")
    ap.add_argument("--dry-run", action="store_true", help="compute and report, write nothing")
    a = ap.parse_args(argv)
    res = backfill(a.strategy.strip("/"), dry_run=a.dry_run)
    rows = res.pop("rows")
    print("BACKFILL " + json.dumps(res, default=str))
    for r in rows:
        print("  ", *r)


if __name__ == "__main__":
    main()
