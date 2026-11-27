"""Turn a deployed strategy's journal into live performance metrics.

The journal (`live/<name>/journal.jsonl`) records one `rebalance` event per bar with
the strategy's own mark-to-market equity, so the equity curve is already there --
this module reads it, segments it, and computes the same statistics the research
reports quote, so live and backtest can be put side by side honestly.

Two things it deliberately refuses to do:

  * **Chart across a mode switch.** A shadow book and a funded account are different
    books; splicing them produces a curve that never existed. Segments are split on
    `shadow` and only the current one is reported.
  * **Quote a Sharpe from a handful of bars.** Live Sharpe over days is noise --
    BULT's own bootstrap CI is [0.90, 2.13] over nine years. Every result carries
    `sufficient`, false until `MIN_DAYS_FOR_SHARPE` of history exists, and callers
    are expected to show "too early to judge" rather than the number.
"""
from __future__ import annotations

import json
import math
import os
from datetime import datetime, timezone
from typing import Optional

HARNESS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HARNESS_DIR)
LIVE_DIR = os.path.join(REPO_ROOT, "live")

BARS_PER_YEAR = {"1m": 525_600, "5m": 105_120, "15m": 35_040, "30m": 17_520,
                 "1h": 8_760, "2h": 4_380, "4h": 2_190, "6h": 1_460,
                 "12h": 730, "1d": 365}
SCHEDULE_SECONDS = {"1m": 60, "5m": 300, "15m": 900, "30m": 1800, "1h": 3600,
                    "2h": 7200, "4h": 14400, "6h": 21600, "12h": 43200, "1d": 86400}
MIN_DAYS_FOR_SHARPE = 30.0


def read_journal(name: str, limit: Optional[int] = None) -> list:
    path = os.path.join(LIVE_DIR, name, "journal.jsonl")
    if not os.path.exists(path):
        return []
    rows = []
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue          # a torn last line during a write is expected
    return rows[-limit:] if limit else rows


def _ts(row) -> datetime:
    return datetime.fromisoformat(row["ts"].replace("Z", "+00:00"))


def current_segment(rows: list) -> list:
    """Rebalance events since the last shadow/live mode change."""
    rb = [r for r in rows if r.get("event") == "rebalance" and r.get("equity") is not None]
    if not rb:
        return []
    mode = rb[-1].get("shadow", False)
    seg = []
    for r in reversed(rb):
        if r.get("shadow", False) != mode:
            break
        seg.append(r)
    return list(reversed(seg))


def segment_truncated_by_mode_switch(rows: list) -> bool:
    """True when a shadow<->live switch is what makes the current segment short.

    Worth distinguishing: a strategy that has run for days but dropped into shadow mode
    and back shows an empty chart and "not enough history", which reads like the daemon
    is broken rather than like the book was restarted.
    """
    rb = [r for r in rows if r.get("event") == "rebalance" and r.get("equity") is not None]
    if not rb:
        return False
    return any(r.get("shadow", False) != rb[-1].get("shadow", False) for r in rb)


def bars_per_year(seg: list, schedule: str) -> float:
    """Annualisation factor, preferring what the journal itself recorded.

    A "1d" bar happens 365 times a year on a crypto venue and about 252 times on an
    equity one, and only the strategy that wrote the row knows which market it traded.
    Reading it off the schedule alone overstated every equity Sharpe by ~20%.
    """
    for r in reversed(seg):
        v = r.get("bars_per_year")
        if v:
            return float(v)
    return BARS_PER_YEAR.get(schedule, 8_760)


def _row_turnover(r: dict) -> float:
    """Notional traded on one rebalance.

    A basket journals `turnover_usdt` outright: it has many legs and so no single
    `delta_qty`/`price` pair to multiply, and deriving it the single-instrument way
    would report exactly zero turnover for every cross-sectional strategy.
    """
    if r.get("turnover_usdt") is not None:
        return abs(float(r["turnover_usdt"]))
    return abs(float(r.get("delta_qty") or 0)) * float(r.get("price") or 0)


def _per_bar(seg: list, schedule: str) -> list:
    """The first row of each schedule bar, in order -- the mark taken at its boundary.

    A daemon that restarts mid-bar rebalances at once, so a continuous market's journal
    can hold several rows inside one bar -- spot-btc/perp-crowding had six on one day.
    Treating each row as a bar split that day's return into slices and annualised every
    slice as a full day, which understated the Sharpe by the square root of the
    duplication. Statistics are taken per bar; the chart still draws every row.
    """
    step = SCHEDULE_SECONDS.get(schedule)
    if not step:
        return list(seg)
    out, last_key = [], None
    for r in seg:
        key = _bucket(_ts(r), step)
        if key != last_key:
            out.append(r)
        last_key = key
    return out


def _is_basket(seg: list) -> bool:
    return any(r.get("gross") is not None for r in seg)


def _gross(r: dict) -> float:
    """Gross exposure of a row: a basket journals it, a single instrument is |weight|."""
    if r.get("gross") is not None:
        return abs(float(r["gross"]))
    return abs(float(r.get("weight") or 0))


def _drawdown(equity: list) -> float:
    peak, mdd = equity[0], 0.0
    for v in equity:
        peak = max(peak, v)
        if peak > 0:
            mdd = min(mdd, v / peak - 1.0)
    return mdd


def compute(name: str, schedule: str = "1h") -> dict:
    """Live statistics for one strategy, plus a buy-&-hold benchmark on the same bars."""
    rows = read_journal(name)
    seg = current_segment(rows)
    switched = segment_truncated_by_mode_switch(rows)
    out = {"strategy": name, "bars": len(seg), "sufficient": False,
           "mode_switched": switched,
           "shadow": seg[-1].get("shadow", False) if seg else None}
    if len(seg) < 2:
        out["reason"] = ("the book switched between shadow and live, so the curve starts "
                         "again from that point" if switched else "not enough history yet")
        return out

    t0, t1 = _ts(seg[0]), _ts(seg[-1])
    days = (t1 - t0).total_seconds() / 86400.0
    eq = [float(r["equity"]) for r in seg]
    px = [float(r["price"]) for r in seg if r.get("price")]
    ann = bars_per_year(seg, schedule)

    bars = _per_bar(seg, schedule)
    beq = [float(r["equity"]) for r in bars]
    rets = [beq[i] / beq[i - 1] - 1.0 for i in range(1, len(beq)) if beq[i - 1] > 0]
    out.update({
        "start": t0.isoformat(), "end": t1.isoformat(), "days": round(days, 2),
        "equity_start": eq[0], "equity_now": eq[-1],
        "total_return_pct": (eq[-1] / eq[0] - 1.0) * 100 if eq[0] else None,
        "maxdd_pct": _drawdown(eq) * 100,
        "avg_exposure": sum(float(r.get("weight") or 0) for r in bars) / len(bars),
        # A basket's `weight` is its NET exposure, which for a long/short book sits near
        # zero however much it holds: cef-discount-reversion read 0.000 fully invested.
        # Gross is what the backtests quote as exposure for a basket, so it travels too.
        "basket": _is_basket(seg),
        "avg_gross": sum(_gross(r) for r in bars) / len(bars),
        "current_weight": float(seg[-1].get("weight") or 0),
        "current_gross": _gross(seg[-1]),
        "fees_paid": sum(float(r.get("fee") or 0) for r in seg),
        "trades": sum(1 for r in seg if r.get("traded")),
        "errors": sum(1 for r in rows if r.get("event") == "error"),
    })

    turnover_usdt = sum(_row_turnover(r) for r in seg if r.get("traded"))
    out["turnover_usdt"] = turnover_usdt
    # Annualising a sub-day span produces theatre, not information.
    if eq[0] and days >= 1.0:
        out["round_trips_per_year"] = turnover_usdt / eq[0] / 2 * (365.0 / days)

    if len(rets) >= 2:
        mean = sum(rets) / len(rets)
        var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
        sd = math.sqrt(var)
        out["vol_pct"] = sd * math.sqrt(ann) * 100
        if sd > 0:
            out["sharpe"] = mean / sd * math.sqrt(ann)
        if days >= 1.0 and eq[0] > 0 and eq[-1] > 0:
            out["cagr_pct"] = ((eq[-1] / eq[0]) ** (365.0 / days) - 1.0) * 100

    # Buy & hold on the same bars, so the comparison is apples to apples.
    if len(px) >= 2 and px[0] > 0:
        bh = [p / px[0] for p in px]
        bh_rets = [bh[i] / bh[i - 1] - 1.0 for i in range(1, len(bh))]
        bench = {"total_return_pct": (bh[-1] - 1.0) * 100, "maxdd_pct": _drawdown(bh) * 100}
        if len(bh_rets) >= 2:
            m = sum(bh_rets) / len(bh_rets)
            v = math.sqrt(sum((r - m) ** 2 for r in bh_rets) / (len(bh_rets) - 1))
            if v > 0:
                bench["sharpe"] = m / v * math.sqrt(ann)
        out["benchmark"] = bench

    out["sufficient"] = days >= MIN_DAYS_FOR_SHARPE
    if not out["sufficient"]:
        out["reason"] = (f"only {days:.1f} days live; a live Sharpe needs at least "
                         f"{MIN_DAYS_FOR_SHARPE:.0f} days before it means anything")
        if switched:
            out["reason"] += (" -- the clock restarted at the last shadow/live switch, "
                              "the two books cannot be spliced")
    return out


def _empty_series() -> dict:
    return {"t": [], "ts": [], "equity": [], "benchmark": [], "weight": [], "gross": [],
            "trades": [],
            "points_total": 0, "capital_usdt": None, "equity_usdt": None,
            "start": None, "end": None, "mode": None}


def equity_series(name: str, max_points: int = 600) -> dict:
    """Downsampled equity + benchmark series for charting.

    Both curves are indexed to 100 at the segment's first bar, so a book risking $2,500
    and one risking $25,000 can share an axis.
    """
    seg = current_segment(read_journal(name))
    if len(seg) < 2:
        out = _empty_series()
        out["points_total"] = len(seg)
        return out
    step = max(1, len(seg) // max_points)
    pts = seg[::step]
    if pts[-1] is not seg[-1]:
        pts.append(seg[-1])
    p0 = float(pts[0].get("price") or 0) or None
    e0 = float(pts[0]["equity"])

    # Fills are read off the FULL segment, never off `pts`.  Downsampling keeps every
    # `step`-th bar whether or not it traded, so markers taken from the thinned series
    # would drop most fills and date the survivors to a bar they did not happen on.
    trades = []
    for r in seg:
        if not r.get("traded"):
            continue
        trades.append({
            "ts": int(_ts(r).timestamp()),
            # A basket rebalances many legs at once and has no single side, so it is
            # marked neutral rather than guessing a direction from one leg.
            "side": r.get("side") or ("REBAL" if r.get("legs") else None),
            "price": r.get("fill_price") or r.get("price"),
            "qty": r.get("filled_qty") or r.get("delta_qty"),
            "turnover_usdt": _row_turnover(r),
            "equity": round(float(r["equity"]) / e0 * 100, 4),
        })

    # Forward-fill the benchmark rather than substituting the first price: a bar that
    # journalled no price is a gap in the quote, and falling back to p0 drew the
    # benchmark snapping back to its starting value for the length of the outage.
    bench, last_px = [], p0
    if p0:
        for r in pts:
            px = float(r.get("price") or 0) or last_px
            last_px = px
            bench.append(round(px / p0 * 100, 4))

    return {
        "t": [_ts(r).isoformat() for r in pts],
        # Epoch seconds as well: a chart's x-scale wants a number, and re-parsing 600
        # ISO strings in the browser on every 10s refresh repeats work done here.
        "ts": [int(_ts(r).timestamp()) for r in pts],
        "equity": [round(float(r["equity"]) / e0 * 100, 4) for r in pts],
        "benchmark": bench,
        "weight": [round(float(r.get("weight") or 0), 4) for r in pts],
        # A basket's weight is net, so a long/short book plots as a flat line at zero.
        # Gross alongside it is what shows the book is actually holding something.
        "gross": [round(_gross(r), 4) for r in pts] if _is_basket(seg) else [],
        "trades": trades,
        # Pre-downsample count, so a chart can draw point markers when the curve is a
        # handful of observations and six rebalances cannot pose as a smooth line.
        "points_total": len(seg),
        "capital_usdt": seg[-1].get("capital_usdt"),
        "equity_usdt": float(seg[-1]["equity"]),
        "start": _ts(seg[0]).isoformat(),
        "end": _ts(seg[-1]).isoformat(),
        "mode": seg[-1].get("mode"),
    }


def _leg_notional(leg: dict) -> float:
    return abs(float(leg.get("qty") or 0)) * float(leg.get("fill_price") or leg.get("price") or 0)


def fills(name: str, limit: int = 100, max_legs: int = 25) -> dict:
    """The most recent fills, newest first, read off the WHOLE journal.

    The Trades panel used to fetch the last 200 journal rows and look for fills among
    them. On an hourly book 200 rows is eight days, so a strategy that had traded 148
    times showed "no fills yet" after a quiet week; and it rendered every row as one
    instrument's side/qty/price, which a basket rebalance does not have -- nine of the
    desk's books listed their trades as blank lines. A basket fill is summarised here
    (legs, turnover, gross/net) with its largest legs attached, so a 500-name rebalance
    does not ship 500 legs per row to a phone.
    """
    rows = [r for r in read_journal(name)
            if r.get("event") == "rebalance" and r.get("traded")]
    out = []
    for r in reversed(rows[-limit:] if limit else rows):
        f = {"ts": r.get("ts"), "weight": r.get("weight"), "equity": r.get("equity"),
             "fee": r.get("fee"), "turnover_usdt": _row_turnover(r),
             "mode": r.get("mode"), "backfill": bool(r.get("backfill"))}
        legs = r.get("legs")
        if legs is not None:
            ranked = sorted(legs, key=_leg_notional, reverse=True)
            f.update({
                "side": "REBAL", "gross": r.get("gross"), "net": r.get("net"),
                "legs_total": len(legs),
                "buys": sum(1 for g in legs if g.get("side") == "BUY"),
                "sells": sum(1 for g in legs if g.get("side") == "SELL"),
                "legs": [{"symbol": g.get("symbol"), "side": g.get("side"),
                          "qty": g.get("qty"), "price": g.get("fill_price") or g.get("price"),
                          "notional": _leg_notional(g), "target_weight": g.get("target_weight")}
                         for g in ranked[:max_legs]],
            })
        else:
            f.update({"side": r.get("side"),
                      "qty": r.get("filled_qty") or r.get("delta_qty"),
                      "price": r.get("fill_price") or r.get("price")})
        out.append(f)
    return {"fills": out, "total": len(rows)}


def portfolio_series(books: list, max_points: int = 900) -> dict:
    """Combined equity across several books, grouped by how real their fills are.

    A third thing this module refuses to do: add a simulated book to a funded one.  A
    `sim` or `shadow` book never sent an order to a venue, so folding its equity into
    the venue total would report money that was never at risk.  Books are grouped by
    the mode of their CURRENT segment and each group is summed on its own.

    Within a group the books start on different days, and a book is worth its capital
    before its first bar -- idle cash, not nothing.  Carrying it at capital from the
    start of the grid is what stops the total stepping up on the day a new strategy is
    deployed, which would otherwise read as a gain the desk never made.

    `books` is a list of {"name", "capital_usdt"}; the capital falls back to whatever
    the journal recorded.
    """
    loaded = []
    for b in books:
        seg = current_segment(read_journal(b["name"]))
        if len(seg) < 2:
            continue
        cap = float(b.get("capital_usdt") or seg[-1].get("capital_usdt") or 0)
        if cap <= 0:
            continue
        loaded.append({
            "name": b["name"], "capital": cap,
            "mode": seg[-1].get("mode") or ("sim" if seg[-1].get("shadow") else "live"),
            "pts": sorted((int(_ts(r).timestamp()), float(r["equity"])) for r in seg),
        })

    groups = {}
    for bk in loaded:
        groups.setdefault("live" if bk["mode"] == "live" else "paper", []).append(bk)

    out = {}
    for gname, bks in groups.items():
        grid = sorted({t for bk in bks for t, _ in bk["pts"]})
        if len(grid) < 2:
            continue
        total = [0.0] * len(grid)
        for bk in bks:
            i, cur = 0, bk["capital"]      # idle cash until this book's first bar
            for j, t in enumerate(grid):
                while i < len(bk["pts"]) and bk["pts"][i][0] <= t:
                    cur = bk["pts"][i][1]
                    i += 1
                total[j] += cur
        step = max(1, len(grid) // max_points)
        idx = list(range(0, len(grid), step))
        if idx[-1] != len(grid) - 1:
            idx.append(len(grid) - 1)
        base = total[0] or 1.0
        out[gname] = {
            "ts": [grid[k] for k in idx],
            "index": [round(total[k] / base * 100, 4) for k in idx],
            "usd": [round(total[k], 2) for k in idx],
            "books": sorted(bk["name"] for bk in bks),
            "capital_usdt": sum(bk["capital"] for bk in bks),
            "equity_usdt": total[-1],
        }
    return out


def _bucket(ts: datetime, step_s: int) -> int:
    """Floor a timestamp to a `step_s` grid, so two strategies' bars line up."""
    return int(ts.timestamp() // step_s)


def correlation(names: list, schedule_by_name: dict) -> dict:
    """Pairwise correlation of strategy returns, per schedule.

    A wall of 0.9s says the desk is one bet, not five. The venue books are all long-only
    crypto and expected to show it; the simulated ones span asset classes and go short,
    so for them a high number is a finding rather than a given.

    Only strategies on the SAME schedule are compared. `schedule_by_name` was accepted
    and then ignored, with every series bucketed to the hour regardless: a daily
    strategy contributed one return per day and an hourly one contributed the single
    return that happened to fall in the same hour, and the pair was reported as a
    correlation. Two series on different bar sizes have no shared return to correlate,
    so the honest answer is to not report the pair at all.
    """
    series = {}
    for n in names:
        sched = schedule_by_name.get(n) or "1h"
        step_s = SCHEDULE_SECONDS.get(sched)
        if step_s is None:
            continue
        seg = current_segment(read_journal(n))
        if len(seg) < 3:
            continue
        # Bar to bar, from each bar's boundary mark. Row to row, a bar holding a restart
        # row kept only that row's slice of return under the bucket and dropped the rest.
        by_ts = {}
        prev = None
        for r in _per_bar(seg, sched):
            e = float(r["equity"])
            if prev is not None and prev > 0:
                by_ts[_bucket(_ts(r), step_s)] = e / prev - 1.0
            prev = e
        if by_ts:
            series[n] = (sched, by_ts)
    out = {}
    for a in series:
        for b in series:
            if a >= b:
                continue
            (sched_a, ser_a), (sched_b, ser_b) = series[a], series[b]
            if sched_a != sched_b:
                continue
            shared = sorted(set(ser_a) & set(ser_b))
            if len(shared) < 10:
                continue
            xs = [ser_a[t] for t in shared]
            ys = [ser_b[t] for t in shared]
            mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
            cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
            vx = math.sqrt(sum((x - mx) ** 2 for x in xs))
            vy = math.sqrt(sum((y - my) ** 2 for y in ys))
            if vx > 0 and vy > 0:
                out[f"{a}|{b}"] = {"corr": cov / (vx * vy), "n": len(shared),
                                   "schedule": sched_a}
    return out


if __name__ == "__main__":
    import sys
    for n in (sys.argv[1:] or ["spot-btc/bult"]):
        print(json.dumps(compute(n), indent=2, default=str))
