"""The tick store: the mount guard, the aggTrades conversion, and trades -> bars.

Three things here fail silently if they are wrong. A tick write while the D: disk is
detached lands in the tmpfs under /mnt/wsl and eats RAM. Binance's two CSV dialects (spot:
8 columns, no header; USD-M: 7 columns under a header) and its ms -> us timestamp switch
each misread without an error. And `buyer_maker` is the inverse of "taker bought", which
is exactly the kind of flag that gets flipped once and then trusted for a year.
"""
import io
import os
import sys
import zipfile

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "code", "shared"))
import fetch_binance_vision as fbv  # noqa: E402
import research_lib  # noqa: E402
import ticks  # noqa: E402


@pytest.fixture
def tick_dir(tmp_path, monkeypatch):
    d = tmp_path / "ticks"
    monkeypatch.setenv("AQ_TICKS_DIR", str(d))
    return d


def test_root_refuses_an_unmounted_disk(tmp_path, monkeypatch):
    """data/ticks pointing at a plain directory must raise, not quietly become the store."""
    monkeypatch.delenv("AQ_TICKS_DIR", raising=False)
    monkeypatch.setattr(research_lib, "DATA_DIR", str(tmp_path))
    target = tmp_path / "not-a-mount"
    target.mkdir()
    os.symlink(target, tmp_path / "ticks")
    with pytest.raises(ticks.TickStoreUnavailable, match="schtasks"):
        ticks.ticks_root()


def _zip(tmp_path, name, text):
    p = tmp_path / name
    with zipfile.ZipFile(p, "w") as z:
        z.writestr(name.replace(".zip", ".csv"), text)
    return str(p)


def test_spot_dialect_and_microsecond_stamps(tmp_path):
    # Spot 2025+: no header, 8 columns, 16-digit microsecond stamps.
    csv = ("100,10.5,2.0,500,502,1735689600000000,True,True\n"
           "101,10.6,1.0,503,503,1735689600500000,False,True\n")
    out = tmp_path / "o.parquet"
    rows, t0, t1, gaps = fbv._aggtrades_zip_to_parquet(_zip(tmp_path, "s.zip", csv), str(out))
    df = pd.read_parquet(out)
    assert rows == 2 and gaps == 0
    assert df["ts"].iloc[0] == pd.Timestamp("2025-01-01 00:00:00")
    assert df["ts"].iloc[1] == pd.Timestamp("2025-01-01 00:00:00.5")
    assert df["n_trades"].tolist() == [3, 1]
    assert df["buyer_maker"].tolist() == [True, False]


def test_futures_dialect_with_header_and_millisecond_stamps(tmp_path):
    csv = ("agg_trade_id,price,quantity,first_trade_id,last_trade_id,transact_time,is_buyer_maker\n"
           "7,50000.0,0.01,1,1,1704067200000,false\n"
           "9,50001.0,0.02,2,4,1704067201000,true\n")
    out = tmp_path / "o.parquet"
    rows, t0, t1, gaps = fbv._aggtrades_zip_to_parquet(_zip(tmp_path, "f.zip", csv), str(out))
    df = pd.read_parquet(out)
    assert rows == 2
    assert gaps == 1                                  # id 8 is missing
    assert t0 == pd.Timestamp("2024-01-01 00:00:00")
    assert df["qty"].tolist() == [0.01, 0.02]


def test_flow_bars_split_taker_side_correctly():
    idx = pd.to_datetime(["2024-01-01 00:00:10", "2024-01-01 00:00:20",
                          "2024-01-01 00:00:50", "2024-01-01 00:01:05"])
    trades = pd.DataFrame({
        "price": [10.0, 12.0, 11.0, 9.0],
        "qty": [1.0, 2.0, 3.0, 4.0],
        # False = the maker was the seller = the taker BOUGHT.
        "buyer_maker": [False, True, False, True],
        "n_trades": [1, 2, 1, 1],
    }, index=pd.DatetimeIndex(idx, name="ts"))
    b = ticks.flow_bars(trades, "1m")
    first = b.loc["2024-01-01 00:00"]
    assert (first["Open"], first["High"], first["Low"], first["Close"]) == (10.0, 12.0, 10.0, 11.0)
    assert first["Volume"] == 6.0 and first["n"] == 4
    assert first["tb"] == 4.0                         # 1 + 3, the two taker buys
    assert first["tq"] == 10.0 * 1 + 11.0 * 3
    assert np.isclose(first["qv"] / first["Volume"], (10 + 24 + 33) / 6)
    assert b.loc["2024-01-01 00:01", "tb"] == 0.0


def test_months_round_trip_and_window(tick_dir):
    d = tick_dir / "binance" / "um" / "aggTrades" / "XUSDT"
    d.mkdir(parents=True)
    for m in ("2024-01", "2024-02"):
        ts = pd.date_range(m + "-01", periods=3, freq="10D")
        pd.DataFrame({"ts": ts, "price": 1.0, "qty": 1.0, "buyer_maker": False,
                      "n_trades": 1, "agg_id": range(3)}).to_parquet(d / f"{m}.parquet")
    assert ticks.cached_months(str(d)) == ["2024-01", "2024-02"]
    got = ticks.load_aggtrades("XUSDT", "um", start="2024-01-15", end="2024-02-05")
    assert list(got.index) == [pd.Timestamp("2024-01-21"), pd.Timestamp("2024-02-01")]


def test_fx_tick_crawl_resumes_and_closes_a_month_only_when_complete(tick_dir, monkeypatch):
    """A failed day holds the month open; a holiday is remembered as done; no Saturdays."""
    import fetch_dukascopy as fd

    calls, failed_once, written = [], set(), []

    def fake_day(sym, day, workers=1):
        day = pd.Timestamp(day)
        calls.append(day)
        if day == pd.Timestamp("2024-01-15") and day not in failed_once:
            failed_once.add(day)
            raise RuntimeError("throttled")
        if day == pd.Timestamp("2024-01-01"):
            return fd.decode_ticks(b"", sym, day)
        idx = pd.DatetimeIndex([day + pd.Timedelta(hours=1), day + pd.Timedelta(hours=2)],
                               name="ts")
        return pd.DataFrame({"bid": 1.1, "ask": 1.1001, "bid_vol": 1.0, "ask_vol": 1.0},
                            index=idx)

    monkeypatch.setattr(fd, "fetch_day", fake_day)
    monkeypatch.setattr(fd.barstore, "write_bars", lambda df, s, f: written.append(len(df)))

    kw = dict(start="2024-01-01", end="2024-01-31", verbose=False)
    assert fd.fetch_fx_ticks("EURUSD", **kw) == 0          # the 15th failed: month stays open
    assert ticks.cached_months(ticks.fx_ticks_dir("EURUSD")) == []
    assert not written
    assert not any(c.dayofweek == 5 for c in calls)

    calls.clear()
    assert fd.fetch_fx_ticks("EURUSD", **kw) == 1
    assert calls == [pd.Timestamp("2024-01-15")]           # only the missing day is re-fetched
    got = ticks.load_fx_ticks("EURUSD")
    assert len(got) == 2 * (31 - 4 - 1)                    # 4 Saturdays, 1 empty holiday
    assert not (got.index.dayofweek == 5).any()
    assert not os.listdir(os.path.join(ticks.fx_ticks_dir("EURUSD"), ".partial"))
    assert len(written) == 1 and written[0] > 0

    calls.clear()
    assert fd.fetch_fx_ticks("EURUSD", **kw) == 0          # closed month: nothing re-fetched
    assert calls == []
