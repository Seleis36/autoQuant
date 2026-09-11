"""Live-performance metrics computed from a strategy journal."""
import json
import math

import pytest

import metrics
from conftest import write_strategy


def rebalance(i, equity, price=100.0, shadow=False, **kw):
    return {"ts": f"2026-01-{1 + i // 24:02d}T{i % 24:02d}:00:00+00:00",
            "event": "rebalance", "equity": equity, "price": price,
            "weight": 1.0, "shadow": shadow, **kw}


# ------------------------------------------------------------------ segmentation

def test_current_segment_stops_at_a_mode_switch(live_dir):
    rows = [rebalance(0, 100, shadow=True), rebalance(1, 101, shadow=True),
            rebalance(2, 102, shadow=False), rebalance(3, 103, shadow=False)]
    seg = metrics.current_segment(rows)
    assert [r["equity"] for r in seg] == [102, 103], "a shadow book must not be spliced on"


def test_current_segment_keeps_a_zero_equity_row(live_dir):
    """`if r.get("equity")` dropped a genuinely zero equity bar, silently shortening
    the segment and shifting the drawdown."""
    rows = [rebalance(0, 100.0), rebalance(1, 0.0), rebalance(2, 50.0)]
    assert len(metrics.current_segment(rows)) == 3


def test_segment_truncated_by_mode_switch_is_reported(live_dir):
    """A long-running strategy that flipped into shadow and back shows an empty chart;
    the reason has to say so rather than "not enough history yet"."""
    rows = [rebalance(i, 100 + i, shadow=True) for i in range(20)]
    rows.append(rebalance(21, 121, shadow=False))
    write_strategy(live_dir, "spot-btc/x", journal_rows=rows)
    out = metrics.compute("spot-btc/x")
    assert out["bars"] == 1
    assert out["mode_switched"] is True
    assert "switched" in out["reason"]


def test_no_mode_switch_reported_when_there_was_none(live_dir):
    write_strategy(live_dir, "spot-btc/x",
                   journal_rows=[rebalance(i, 100 + i) for i in range(3)])
    out = metrics.compute("spot-btc/x")
    assert out["mode_switched"] is False


# ------------------------------------------------------------------ statistics

def test_total_return_and_drawdown(live_dir):
    eq = [100.0, 110.0, 88.0, 99.0]
    write_strategy(live_dir, "spot-btc/x",
                   journal_rows=[rebalance(i, e) for i, e in enumerate(eq)])
    out = metrics.compute("spot-btc/x")
    assert out["total_return_pct"] == pytest.approx(-1.0)
    assert out["maxdd_pct"] == pytest.approx((88 / 110 - 1) * 100)


def test_sharpe_is_withheld_until_there_is_enough_history(live_dir):
    write_strategy(live_dir, "spot-btc/x",
                   journal_rows=[rebalance(i, 100 + i) for i in range(10)])
    out = metrics.compute("spot-btc/x")
    assert out["sufficient"] is False
    assert "days" in out["reason"]


def test_sufficient_once_past_the_minimum_window(live_dir):
    rows = [{"ts": f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}T00:00:00+00:00",
             "event": "rebalance", "equity": 100.0 + i, "price": 100.0,
             "weight": 1.0, "shadow": False} for i in range(45)]
    write_strategy(live_dir, "spot-btc/x", journal_rows=rows)
    out = metrics.compute("spot-btc/x", "1d")
    assert out["days"] >= metrics.MIN_DAYS_FOR_SHARPE
    assert out["sufficient"] is True
    assert "sharpe" in out


def test_read_journal_skips_a_torn_final_line(live_dir):
    d = write_strategy(live_dir, "spot-btc/x", journal_rows=[rebalance(0, 100)])
    with open(d / "journal.jsonl", "a") as fh:
        fh.write('{"ts": "2026-01-01T02:00:00+00:00", "event": "reba')   # torn write
    assert len(metrics.read_journal("spot-btc/x")) == 1


def test_missing_journal_is_empty_not_an_error(live_dir):
    assert metrics.read_journal("spot-btc/nothing-here") == []


# ------------------------------------------------------------------ equity series

def test_equity_series_is_normalised_to_100(live_dir):
    write_strategy(live_dir, "spot-btc/x",
                   journal_rows=[rebalance(i, 200.0 + i * 10, price=50.0 + i)
                                 for i in range(4)])
    s = metrics.equity_series("spot-btc/x")
    assert s["equity"][0] == 100.0
    assert s["benchmark"][0] == 100.0
    assert len(s["t"]) == len(s["equity"]) == len(s["weight"]) == 4


def test_equity_series_downsamples_but_keeps_the_last_point(live_dir):
    rows = [rebalance(i % 24, 100.0 + i) for i in range(300)]
    for i, r in enumerate(rows):                    # unique, ordered timestamps
        r["ts"] = f"2026-01-01T00:00:{i % 60:02d}.{i:06d}+00:00"
    write_strategy(live_dir, "spot-btc/x", journal_rows=rows)
    s = metrics.equity_series("spot-btc/x", max_points=50)
    assert len(s["equity"]) <= 52
    assert s["equity"][-1] == pytest.approx(100.0 * (100.0 + 299) / 100.0, rel=1e-9)


# ------------------------------------------------------------------ correlation
#
# `schedule_by_name` was accepted and then never read: every series was bucketed to the
# hour, so a 1d strategy and a 1h strategy were "correlated" on whichever single hourly
# return happened to share a clock hour with the daily one.

def test_correlation_refuses_to_mix_schedules(live_dir):
    hourly = [{"ts": f"2026-01-01T{i:02d}:00:00+00:00", "event": "rebalance",
               "equity": 100.0 + (i % 3), "price": 100.0, "shadow": False}
              for i in range(24)]
    daily = [{"ts": f"2026-01-{1 + i:02d}T00:00:00+00:00", "event": "rebalance",
              "equity": 100.0 + (i % 3), "price": 100.0, "shadow": False}
             for i in range(24)]
    write_strategy(live_dir, "spot-btc/h", journal_rows=hourly)
    write_strategy(live_dir, "spot-btc/d", journal_rows=daily)
    out = metrics.correlation(["spot-btc/h", "spot-btc/d"],
                              {"spot-btc/h": "1h", "spot-btc/d": "1d"})
    assert out == {}, "an hourly and a daily book share no comparable return"


def test_correlation_of_two_identical_hourly_books_is_one(live_dir):
    rows = lambda: [{"ts": f"2026-01-01T{i:02d}:00:00+00:00", "event": "rebalance",
                     "equity": 100.0 * (1.01 ** (i % 5)), "price": 100.0, "shadow": False}
                    for i in range(24)]
    write_strategy(live_dir, "spot-btc/a", journal_rows=rows())
    write_strategy(live_dir, "spot-btc/b", journal_rows=rows())
    out = metrics.correlation(["spot-btc/a", "spot-btc/b"],
                              {"spot-btc/a": "1h", "spot-btc/b": "1h"})
    key = "spot-btc/a|spot-btc/b"
    assert out[key]["corr"] == pytest.approx(1.0)
    assert out[key]["schedule"] == "1h"


def test_correlation_skips_an_unknown_schedule(live_dir):
    rows = [{"ts": f"2026-01-01T{i:02d}:00:00+00:00", "event": "rebalance",
             "equity": 100.0 + i, "price": 100.0, "shadow": False} for i in range(24)]
    write_strategy(live_dir, "spot-btc/a", journal_rows=rows)
    write_strategy(live_dir, "spot-btc/b", journal_rows=rows)
    out = metrics.correlation(["spot-btc/a", "spot-btc/b"],
                              {"spot-btc/a": "3s", "spot-btc/b": "1h"})
    assert out == {}


def test_schedule_tables_agree():
    """Three copies of this table existed; the dashboard's is now gone. The two that
    remain describe the same set of schedules and must not drift."""
    import live_lib
    assert set(metrics.SCHEDULE_SECONDS) == set(metrics.BARS_PER_YEAR)
    assert metrics.SCHEDULE_SECONDS == live_lib._INTERVAL_SECONDS


# ------------------------------------------------- annualisation and basket turnover
#
# A "1d" bar happens 365 times a year on a crypto venue and about 252 times on an
# equity one, and a basket has no single delta_qty/price pair to derive turnover from.
# Both were read off the schedule alone, which is right for exactly one of the books.

def _row(ts, equity, **kw):
    return {"ts": ts, "event": "rebalance", "equity": equity, "shadow": True, **kw}


def test_annualisation_prefers_what_the_journal_recorded():
    seg = [_row("2026-01-01T00:00:00+00:00", 100.0, bars_per_year=252.0),
           _row("2026-01-02T00:00:00+00:00", 101.0, bars_per_year=252.0)]
    assert metrics.bars_per_year(seg, "1d") == 252.0


def test_annualisation_falls_back_to_the_schedule_for_older_journals():
    seg = [_row("2026-01-01T00:00:00+00:00", 100.0)]
    assert metrics.bars_per_year(seg, "1d") == 365.0
    assert metrics.bars_per_year(seg, "1h") == 8_760


def test_an_equity_sharpe_is_not_inflated_by_the_crypto_year(live_dir):
    """Annualising 252 daily bars with 365 overstates the Sharpe by ~20% -- on the
    live number the desk compares straight against the backtest."""
    from datetime import datetime, timedelta, timezone
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows = [_row((t0 + timedelta(days=i)).isoformat(), 100.0 * (1.001 ** i),
                 weight=1.0, bars_per_year=252.0) for i in range(40)]
    write_strategy(live_dir, "sector-etf/x", journal_rows=rows)
    equity_ann = metrics.compute("sector-etf/x", "1d")["sharpe"]

    for r in rows:
        del r["bars_per_year"]
    write_strategy(live_dir, "spot-btc/y", journal_rows=rows)
    crypto_ann = metrics.compute("spot-btc/y", "1d")["sharpe"]

    assert equity_ann < crypto_ann
    assert equity_ann / crypto_ann == pytest.approx((252 / 365) ** 0.5, rel=1e-6)


def test_a_basket_reports_the_turnover_it_journalled(live_dir):
    """Deriving it the single-instrument way reports exactly zero for every
    cross-sectional strategy: there is no `delta_qty` and no `price` on the row."""
    rows = [_row("2026-01-01T00:00:00+00:00", 100_000.0, weight=0.0, traded=True,
                 turnover_usdt=50_000.0),
            _row("2026-01-02T00:00:00+00:00", 100_100.0, weight=0.0, traded=True,
                 turnover_usdt=25_000.0)]
    write_strategy(live_dir, "sector-etf/z", journal_rows=rows)
    assert metrics.compute("sector-etf/z", "1d")["turnover_usdt"] == 75_000.0


def test_a_basket_gets_no_invented_benchmark(live_dir):
    """With no instrument price on the row there is nothing to buy and hold, and a
    made-up benchmark line is worse than none."""
    rows = [_row(f"2026-01-{i + 1:02d}T00:00:00+00:00", 100_000.0 + i, weight=0.0,
                 turnover_usdt=1.0) for i in range(5)]
    write_strategy(live_dir, "sector-etf/w", journal_rows=rows)
    out = metrics.compute("sector-etf/w", "1d")
    assert "benchmark" not in out
    assert metrics.equity_series("sector-etf/w")["benchmark"] == []


def test_single_instrument_turnover_is_unchanged(live_dir):
    rows = [_row("2026-01-01T00:00:00+00:00", 1000.0, weight=1.0, traded=True,
                 delta_qty=2.0, price=50.0)]
    write_strategy(live_dir, "spot-btc/t", journal_rows=rows * 2)
    assert metrics.compute("spot-btc/t", "1d")["turnover_usdt"] == 200.0
