"""The partitioned bar store: stamp discipline, join integrity, and resample direction.

Daily bars forgive a lot. At 1m the same mistakes stop being visible: a resample that
labels right instead of left shifts every signal one bar into its own future and the
equity curve just quietly improves, and an off-grid stamp drops rows from a cross-symbol
join without raising anything. Both are tested here because both were real.
"""
import os
import sys

import numpy as np
import pandas as pd
import pytest

import live_lib

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "code", "shared"))
import bars  # noqa: E402
import research_lib  # noqa: E402


@pytest.fixture
def store(tmp_path, monkeypatch):
    """An isolated bar store. `bars` resolves DATA_DIR through `research_lib` at call
    time, so patching the one name redirects the whole tree."""
    monkeypatch.setattr(research_lib, "DATA_DIR", str(tmp_path))
    return tmp_path


def _ohlcv(n=10, start="2024-01-01", freq="1min", base=100.0):
    idx = pd.date_range(start, periods=n, freq=freq)
    step = np.arange(n, dtype=float)
    return pd.DataFrame({
        "Open": base + step, "High": base + step + 1.0,
        "Low": base + step - 1.0, "Close": base + step + 0.5,
        "Volume": np.full(n, 2.0),
    }, index=pd.DatetimeIndex(idx, name="ts"))


# --------------------------------------------------------------- one DATA_DIR

def test_the_bar_store_shares_one_data_dir_with_research_and_live():
    """`^GSPC` was once cached twice because two modules disagreed about where `data/`
    is. A third writer makes that failure mode three-cornered, so it resolves the
    directory through `research_lib` rather than deriving its own."""
    assert bars._data_dir() == research_lib.DATA_DIR
    assert live_lib.DATA_DIR == research_lib.DATA_DIR


def test_symbols_that_are_not_filesystem_safe_get_stable_directories(store):
    for sym in ["EURUSD=X", "^GSPC", "BTC-USD", "ETH/USDT"]:
        component = bars.safe_symbol(sym)
        # the symbol becomes exactly one path component, whatever punctuation it carries
        assert os.sep not in component
        assert not (set(component) & set("=^/")), f"{sym} -> {component} is not safe"
        assert bars.bars_dir(sym, "1m").endswith(os.path.join(component, "1m"))
    # and the mapping is stable across calls -- an unstable one orphans cached bars
    assert bars.safe_symbol("EURUSD=X") == bars.safe_symbol("EURUSD=X") == "EURUSD_X"


# --------------------------------------------------------------- round trip

def test_a_written_bar_comes_back_unchanged(store):
    df = _ohlcv(120)
    bars.write_bars(df, "TEST", "1m")
    got = bars.load_bars("TEST", "1m")
    pd.testing.assert_frame_equal(got, df, check_freq=False)


def test_partitions_split_by_year_and_only_needed_years_are_read(store):
    df = pd.concat([_ohlcv(5, "2022-12-31 23:55"), _ohlcv(5, "2023-06-01")])
    bars.write_bars(df, "TEST", "1m")
    assert bars.cached_years("TEST", "1m") == [2022, 2023]
    assert os.path.exists(bars.bars_path("TEST", "1m", 2022))

    only23 = bars.load_bars("TEST", "1m", start="2023-01-01")
    assert only23.index.year.unique().tolist() == [2023]


def test_refetching_an_overlapping_window_corrects_rows_instead_of_duplicating(store):
    bars.write_bars(_ohlcv(10), "TEST", "1m")
    revised = _ohlcv(10)
    revised["Close"] += 99.0
    bars.write_bars(revised, "TEST", "1m")

    got = bars.load_bars("TEST", "1m")
    assert len(got) == 10, "overlapping refetch duplicated rows"
    assert got["Close"].iloc[0] == pytest.approx(revised["Close"].iloc[0]), "kept stale row"


# --------------------------------------------------------------- stamp discipline

def test_off_grid_stamps_are_snapped_so_cross_symbol_joins_stay_whole(store):
    """Binance's archive stamps ~21.6k 2017-18 bars off the minute grid, and the offset
    differs per symbol: BTCUSDT at .799 against ETHUSDT at .810 for the *same* minute.
    Unsnapped, an inner join on timestamp drops every one of those rows from both sides
    and reports a clean, shorter frame."""
    idx = pd.date_range("2018-01-01 06:00:00", periods=5, freq="1min")
    a = _ohlcv(5).set_axis(idx + pd.Timedelta(milliseconds=799))
    b = _ohlcv(5, base=50.0).set_axis(idx + pd.Timedelta(milliseconds=810))

    bars.write_bars(a, "AAA", "1m")
    bars.write_bars(b, "BBB", "1m")
    ga, gb = bars.load_bars("AAA", "1m"), bars.load_bars("BBB", "1m")

    assert len(ga.index.intersection(gb.index)) == 5, "snapping did not align the stamps"
    assert (ga.index.second == 0).all() and (ga.index.microsecond == 0).all()


def test_snapping_keeps_the_last_row_when_two_stamps_share_a_slot(store):
    idx = pd.DatetimeIndex(["2024-01-01 00:00:10", "2024-01-01 00:00:50"])
    df = pd.DataFrame({"Open": [1.0, 2.0], "High": [1.0, 2.0], "Low": [1.0, 2.0],
                       "Close": [1.0, 2.0], "Volume": [1.0, 1.0]}, index=idx)
    bars.write_bars(df, "TEST", "1m")
    got = bars.load_bars("TEST", "1m")
    assert len(got) == 1
    assert got["Close"].iloc[0] == 2.0


# --------------------------------------------------------------- resampling

def test_resampling_is_left_labelled_so_a_bar_never_reaches_into_its_own_future(store):
    """The bug this guards: with `label="right"` the 09:00-09:59 hour is stamped 10:00,
    a signal reading the bar stamped 10:00 at 10:00 has already seen 10:00's move, and
    the backtest silently improves."""
    df = _ohlcv(120, "2024-01-01 09:00")
    hourly = bars.resample_bars(df, "1h")

    assert hourly.index[0] == pd.Timestamp("2024-01-01 09:00")
    assert hourly["Open"].iloc[0] == df["Open"].iloc[0], "first hour did not open at 09:00"
    assert hourly["Close"].iloc[0] == df["Close"].iloc[59], "hour closed on the wrong bar"
    assert hourly["High"].iloc[0] == df["High"].iloc[:60].max()


def test_resampling_sums_quantities_and_averages_levels(store):
    df = _ohlcv(60, "2024-01-01 09:00")
    df["Spread"] = 2.0
    df["Ticks"] = 3.0
    out = bars.resample_bars(df, "1h")
    assert out["Volume"].iloc[0] == pytest.approx(120.0), "volume must sum"
    assert out["Ticks"].iloc[0] == pytest.approx(180.0), "tick count must sum"
    assert out["Spread"].iloc[0] == pytest.approx(2.0), "spread must average, not sum"


def test_an_outage_stays_a_hole_rather_than_becoming_a_flat_bar(store):
    """A synthetic bar across a venue outage is indistinguishable downstream from a real
    one, and every rolling window then spans the gap without saying so."""
    df = pd.concat([_ohlcv(60, "2024-01-01 00:00"), _ohlcv(60, "2024-01-01 05:00")])
    out = bars.resample_bars(df, "1h")
    assert len(out) == 2, "empty hours were filled instead of dropped"
    assert (out.index == pd.DatetimeIndex(["2024-01-01 00:00", "2024-01-01 05:00"])).all()


def test_load_can_coarsen_from_a_finer_cache_without_a_second_copy_on_disk(store):
    bars.write_bars(_ohlcv(180, "2024-01-01 00:00"), "TEST", "1m")
    hourly = bars.load_bars("TEST", "1h", resample_from="1m")
    assert len(hourly) == 3
    assert bars.cached_years("TEST", "1h") == [], "resampling should not write a cache"


# --------------------------------------------------------------- coverage

def test_coverage_counts_a_missing_bar_as_missing(store):
    df = _ohlcv(60)
    df = df.drop(df.index[10:20])
    bars.write_bars(df, "TEST", "1m")
    c = bars.coverage("TEST", "1m")
    assert c["bars"] == 50
    assert c["missing"] == 10
    assert c["pct_present"] < 100.0


def test_loading_an_uncached_symbol_returns_empty_rather_than_raising(store):
    got = bars.load_bars("NOPE", "1m")
    assert got.empty
    assert "Close" in got.columns
