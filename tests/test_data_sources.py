"""The three ingest paths, tested at their wire formats rather than over the network.

Each test here stands for a way the source can be silently wrong -- not a way it can
fail loudly. A 404 announces itself; a timestamp read in the wrong unit, a spread
averaged over the wrong weights, or a macro print read six weeks early do not.
"""
import io
import lzma
import os
import struct
import sys
import zipfile

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "code", "shared"))
import bars  # noqa: E402
import fetch_alfred  # noqa: E402
import fetch_binance_vision as bv  # noqa: E402
import fetch_dukascopy as duka  # noqa: E402
import research_lib  # noqa: E402


# ==================================================================== binance

def test_millisecond_and_microsecond_stamps_both_decode_to_the_right_year():
    """Binance switched kline stamps from ms to us during 2025. Reading a 16-digit
    microsecond value as milliseconds lands in the year 57000, and pandas does not
    complain -- the bars just sort to the end of the frame and every rolling window
    spanning the join goes quiet."""
    ms = 1502942400000        # 2017-08-17 04:00 UTC, 13 digits
    us = 1748736000000000     # 2025-06-01 00:00 UTC, 16 digits
    got = bv._to_datetime(pd.Series([ms, us]))
    assert got.iloc[0] == pd.Timestamp("2017-08-17 04:00:00")
    assert got.iloc[1] == pd.Timestamp("2025-06-01 00:00:00")


def test_a_frame_straddling_the_unit_switch_stays_coherent():
    s = pd.Series([1502942400000, 1502942460000, 1748736000000000, 1748736060000000])
    got = bv._to_datetime(s)
    assert got.is_monotonic_increasing
    assert got.dt.year.tolist() == [2017, 2017, 2025, 2025]


def test_the_current_month_is_fetched_as_daily_files():
    """A monthly file appears only after its month closes. Stopping at the monthly
    boundary ends the history weeks early without reporting anything missing."""
    now = pd.Timestamp.now("UTC").tz_convert(None).normalize()
    periods = bv._periods(now - pd.Timedelta(days=70), now)
    kinds = {k for k, _ in periods}
    assert "daily" in kinds, "no daily fallback for the unpublished current month"
    assert max(d for _, d in periods).normalize() == now, "history stops short of today"


def test_monthly_and_daily_windows_do_not_overlap():
    """Overlap is not corrupting -- the store de-duplicates -- but it silently doubles
    the download for every backfill."""
    periods = bv._periods("2024-01-01", "2026-09-12")
    monthly = [d for k, d in periods if k == "monthly"]
    daily = [d for k, d in periods if k == "daily"]
    if monthly and daily:
        last_month_end = (max(monthly) + pd.Timedelta(days=32)).replace(day=1)
        assert min(daily) >= last_month_end


def test_a_kline_zip_becomes_bars_with_open_time_stamps():
    rows = [
        # open_time(ms), O, H, L, C, V, close_time, qv, n, tb, tq, ignore
        [1704067200000, "1.0", "2.0", "0.5", "1.5", "10", 1704067259999, "15", 3, "4", "6", "0"],
        [1704067260000, "1.5", "2.5", "1.0", "2.0", "20", 1704067319999, "30", 5, "8", "9", "0"],
    ]
    csv = "\n".join(",".join(str(c) for c in r) for r in rows).encode()
    df = pd.read_csv(io.BytesIO(csv), header=None, names=bv.KLINE_COLS)
    df["ts"] = bv._to_datetime(df["ot"])
    df = df.drop(columns=["ot"] + bv.KLINE_DROP).set_index("ts").apply(pd.to_numeric)

    assert df.index[0] == pd.Timestamp("2024-01-01 00:00:00")
    assert list(df.columns) == ["Open", "High", "Low", "Close", "Volume", "qv", "n", "tb", "tq"]
    assert df["Close"].iloc[1] == 2.0


def test_checksum_mismatch_is_refused(monkeypatch):
    """A truncated archive download unzips fine and yields a short month."""
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as z:
        z.writestr("x.csv", "1704067200000,1,2,3,4,5,6,7,8,9,10,0\n")
    blob = payload.getvalue()
    monkeypatch.setattr(bv, "_get", lambda url, **k: b"0" * 64 + b"  x.csv")
    with pytest.raises(RuntimeError, match="checksum mismatch"):
        bv._unzip(blob, "https://example/x.zip", verify=True)


def test_book_spreads_are_time_weighted_not_quote_weighted():
    """Quotes cluster exactly when the book is widest, so a plain mean over updates
    reports a market more expensive than the one that was tradable. Here a 1 bp spread
    of 0.01 stands for 50 of the 60 seconds while one of 0.10 is requoted 4 times in the
    last 10 -- time-weighted gives 0.025, quote-weighted gives 0.082, and only the first
    is the cost you would actually have paid."""
    t0 = pd.Timestamp("2024-01-01 00:00:00")
    times, bids, asks = [], [], []
    times.append(t0);                          bids.append(100.0); asks.append(100.01)
    for s in [50, 52, 54, 56]:
        times.append(t0 + pd.Timedelta(seconds=s)); bids.append(100.0); asks.append(100.10)
    times.append(t0 + pd.Timedelta(seconds=60))   # next minute closes the last quote
    bids.append(100.0); asks.append(100.01)

    csv = pd.DataFrame({
        "update_id": range(len(times)),
        "best_bid_price": bids, "best_ask_price": asks,
        "best_bid_qty": 1.0, "best_ask_qty": 1.0,
        "transaction_time": [int(t.timestamp() * 1000) for t in times],
        "event_time": [int(t.timestamp() * 1000) for t in times],
    }).to_csv(index=False).encode()

    out, _ = bv._spread_minutes(csv)
    tw = out.loc[t0, "Spread"]
    quote_weighted = np.mean([0.01, 0.10, 0.10, 0.10, 0.10])
    assert tw < quote_weighted / 2, f"{tw} looks quote-weighted, not time-weighted"
    assert tw == pytest.approx(0.01 * (50 / 60) + 0.10 * (10 / 60), rel=1e-6)


# ================================================================== dukascopy

def test_jpy_pairs_scale_by_three_digits_and_the_rest_by_five():
    """Getting this backwards puts USDJPY at 0.141558 or EURUSD at 1101.50 -- both of
    which backtest perfectly well and mean nothing."""
    assert duka.digits("EURUSD") == 5
    assert duka.digits("USDJPY") == 3
    assert duka.digits("audjpy") == 3


def test_the_feed_url_uses_a_zero_indexed_month():
    """Verified against the live feed by the weekend hole: 2024/00/06 and 00/07 are
    empty (Sat/Sun 6-7 January) while 00/05 and 00/08 are not. A 1-indexed month reads
    February's ticks as January's and every calendar study silently shifts a month."""
    url = duka._url("EURUSD", pd.Timestamp("2024-01-02"), 10)
    assert url.endswith("/EURUSD/2024/00/02/10h_ticks.bi5")
    dec = duka._url("EURUSD", pd.Timestamp("2024-12-31"), 23)
    assert dec.endswith("/EURUSD/2024/11/31/23h_ticks.bi5")


def _bi5(records, hour_start):
    """Build a bi5 body the way the feed does: LZMA over 20-byte big-endian records."""
    raw = b"".join(struct.pack(">IIIff", *r) for r in records)
    return lzma.compress(raw, format=lzma.FORMAT_ALONE)


def test_ticks_decode_to_real_prices():
    hour = pd.Timestamp("2024-01-02 10:00")
    blob = _bi5([(224, 110150, 110149, 0.99, 4.5), (328, 110150, 110147, 3.6, 6.02)], hour)
    df = duka.decode_ticks(blob, "EURUSD", hour)
    assert len(df) == 2
    assert df.index[0] == hour + pd.Timedelta(milliseconds=224)
    assert df["ask"].iloc[0] == pytest.approx(1.10150)
    assert df["bid"].iloc[0] == pytest.approx(1.10149)


def test_an_empty_hour_is_a_closed_market_not_an_error():
    """Weekends and holidays return a 0-byte 200, not a 404."""
    got = duka.decode_ticks(b"", "EURUSD", pd.Timestamp("2024-01-06 12:00"))
    assert got.empty
    assert list(got.columns) == ["bid", "ask", "bid_vol", "ask_vol"]


def test_fx_bars_price_the_mid_and_carry_the_spread_separately():
    hour = pd.Timestamp("2024-01-02 10:00")
    ticks = pd.DataFrame({
        "bid": [1.1000, 1.1002, 1.1001],
        "ask": [1.1002, 1.1004, 1.1002],
        "bid_vol": [1.0, 1.0, 1.0], "ask_vol": [1.0, 1.0, 1.0],
    }, index=pd.DatetimeIndex([hour, hour + pd.Timedelta(seconds=20),
                               hour + pd.Timedelta(seconds=40)], name="ts"))
    b = duka.ticks_to_bars(ticks, "1m")
    assert len(b) == 1
    assert b["Open"].iloc[0] == pytest.approx(1.1001)      # mid of the first quote
    assert b["Close"].iloc[0] == pytest.approx(1.10015)    # mid of the last
    assert b["Bid"].iloc[0] == pytest.approx(1.1001)
    assert b["Ask"].iloc[0] == pytest.approx(1.1002)
    assert b["Ticks"].iloc[0] == 3
    assert 0 < b["SpreadBps"].iloc[0] < 5


def test_spread_weight_does_not_leak_across_a_bar_boundary():
    """A quote standing from 09:59:59 to 10:00:30 belongs to 09:59 for one second, not
    for thirty-one. Left unclipped, one wide quote before a quiet hour poisons the next
    bar's cost."""
    t = pd.DatetimeIndex(["2024-01-02 09:59:59", "2024-01-02 10:00:30"], name="ts")
    ticks = pd.DataFrame({"bid": [1.0, 1.0], "ask": [1.10, 1.0001],
                          "bid_vol": [1.0, 1.0], "ask_vol": [1.0, 1.0]}, index=t)
    b = duka.ticks_to_bars(ticks, "1m")
    assert b.loc[pd.Timestamp("2024-01-02 10:00"), "Spread"] == pytest.approx(0.0001, rel=1e-6)


def test_the_sampled_days_cover_every_quarter():
    """Uniform sampling lets calm years crowd out 2015 SNB and 2020 March, which is
    exactly where a flat cost assumption does its damage."""
    days = duka.sample_days("2014-01-01", "2016-12-31", per_quarter=3)
    quarters = pd.DatetimeIndex(days).to_period("Q").unique()
    assert len(quarters) == 12
    assert (pd.DatetimeIndex(days).dayofweek < 5).all(), "sampled a weekend"


# ====================================================================== alfred

@pytest.fixture
def vintages(tmp_path, monkeypatch):
    """CPI as ALFRED really serves it: March's print appears only in the April vintage."""
    monkeypatch.setattr(research_lib, "DATA_DIR", str(tmp_path))
    rows = []
    obs = pd.date_range("2024-01-01", periods=4, freq="MS")
    for vi, v in enumerate(pd.date_range("2024-02-01", periods=4, freq="MS")):
        for oi, o in enumerate(obs):
            if o >= v:                 # not yet observed
                continue
            if (v - o).days < 25:      # observed, but not yet published
                continue
            rows.append({"vintage_date": v, "obs_date": o,
                         "value": 100.0 + oi + 0.1 * vi})   # later vintages revise up
    df = pd.DataFrame(rows)
    os.makedirs(fetch_alfred.vintages_dir(), exist_ok=True)
    df.to_parquet(fetch_alfred.vintages_path("TESTCPI"))
    return df


def test_as_of_never_returns_a_value_published_after_the_asked_date(vintages):
    """The quiet one. A frame indexed by observation date puts March CPI on 2024-03-01,
    six weeks before anyone could read it -- every month, with no jump in the equity
    curve to give it away."""
    s = fetch_alfred.as_of("TESTCPI", "2024-03-15")
    assert s.index.max() <= pd.Timestamp("2024-02-01"), (
        "as_of handed back an observation that had not been published yet")


def test_as_of_uses_the_newest_vintage_at_or_before_the_date(vintages):
    early = fetch_alfred.as_of("TESTCPI", "2024-03-01")
    late = fetch_alfred.as_of("TESTCPI", "2024-05-01")
    common = early.index.intersection(late.index)
    assert len(common) > 0
    assert (late[common] >= early[common]).all(), "did not pick up the later revision"


def test_asking_before_the_first_vintage_returns_nothing_rather_than_the_oldest(vintages):
    """Handing back the 2024 vintage to a 2009 caller is precisely the look-ahead this
    module exists to remove, and it would look like a clean series."""
    s = fetch_alfred.as_of("TESTCPI", "2009-01-01")
    assert s.empty


def test_pit_frame_gives_one_observable_value_per_decision_date(vintages):
    dates = pd.date_range("2024-03-01", periods=3, freq="MS")
    out = fetch_alfred.pit_frame("TESTCPI", dates)
    assert list(out.index) == list(dates)
    assert out.notna().any(), "no observable value on any decision date"


def test_the_revision_report_measures_how_far_first_print_moves(vintages):
    r = fetch_alfred.revision_report("TESTCPI")
    assert r["observations"] > 0
    assert r["mean_abs_revision"] >= 0.0
    assert 0.0 <= r["pct_revised"] <= 100.0


def test_a_missing_vintage_cache_is_an_error_not_a_silent_empty():
    with pytest.raises(FileNotFoundError, match="no vintages cached"):
        fetch_alfred.as_of("NEVERFETCHED", "2024-01-01")
