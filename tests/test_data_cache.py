"""The shared `data/` cache: one name per series, atomic writes, and a depth floor.

`data/` is written by the live runners AND by every research agent. Three real bugs
lived in that sharing, and each has a test here.
"""
import os
import sys

import pandas as pd
import pytest

import live_lib

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "code", "shared"))
import research_lib  # noqa: E402


# --------------------------------------------------------------------- naming

@pytest.mark.parametrize("ticker", ["^GSPC", "BTC-USD", "EURUSD=X", "DX-Y.NYB", "SPY"])
def test_research_and_live_name_a_series_identically(ticker, monkeypatch, tmp_path):
    """`^GSPC` was cached twice -- `IDX_GSPC_d.parquet` from research and
    `^GSPC_d.parquet` from the runners -- as two independently-refreshed partial
    copies of one series."""
    monkeypatch.setattr(live_lib, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(research_lib, "DATA_DIR", str(tmp_path))
    assert live_lib.daily_cache_path(ticker) == research_lib.daily_cache_path(ticker)


def test_the_cache_floor_is_shared_too():
    """While these disagreed, whichever module reached a ticker first decided how far
    back the other could see it."""
    assert live_lib.DAILY_CACHE_START == research_lib.DAILY_CACHE_START


# --------------------------------------------------------------------- atomicity

def _frame(n=5):
    return pd.DataFrame({"Close": range(n)},
                        index=pd.date_range("2026-01-01", periods=n))


def test_a_reader_never_sees_a_half_written_cache(tmp_path):
    """`to_parquet` truncates in place; a reader landing mid-write gets a torn file."""
    path = str(tmp_path / "X_d.parquet")
    live_lib._atomic_parquet(_frame(10), path)
    original = pd.read_parquet(path)

    real = pd.DataFrame.to_parquet

    def explode(self, where, *a, **k):
        real(self, where, *a, **k)          # the temp file is written...
        raise OSError("disk full")          # ...and then the write dies

    with pytest.raises(OSError):
        pd.DataFrame.to_parquet = explode
        try:
            live_lib._atomic_parquet(_frame(3), path)
        finally:
            pd.DataFrame.to_parquet = real

    assert pd.read_parquet(path).equals(original), "the old cache must survive"
    assert not [f for f in os.listdir(tmp_path) if f.endswith(".tmp")], "temp file leaked"


def test_concurrent_writers_do_not_share_a_temp_name(tmp_path, monkeypatch):
    """Two daemons refreshing one ticker would otherwise clobber each other's partial
    file and `os.replace` whichever half won."""
    seen = []
    real = pd.DataFrame.to_parquet

    def record(self, where, *a, **k):
        seen.append(str(where))
        return real(self, where, *a, **k)

    monkeypatch.setattr(pd.DataFrame, "to_parquet", record)
    live_lib._atomic_parquet(_frame(), str(tmp_path / "A_d.parquet"))
    assert str(os.getpid()) in seen[0]


# --------------------------------------------------------------------- depth floor

def test_a_short_lookback_does_not_create_a_short_cache(tmp_path, monkeypatch):
    """A runner asking for 30 days used to CREATE a 30-day file, and the next backtest
    to read that ticker silently got a 30-day series."""
    monkeypatch.setattr(live_lib, "DATA_DIR", str(tmp_path))
    asked = {}

    def fake_download(ticker, start=None, **kw):
        asked["start"] = start
        idx = pd.date_range(start, "2026-09-09", freq="B")
        return pd.DataFrame({"Open": 1.0, "High": 1.0, "Low": 1.0,
                             "Close": 1.0, "Volume": 1.0}, index=idx)

    fake_yf = type("yf", (), {"download": staticmethod(fake_download)})
    monkeypatch.setitem(sys.modules, "yfinance", fake_yf)

    md = live_lib.MarketData()
    md.daily("SPY", lookback_days=30)
    assert asked["start"] == live_lib.DAILY_CACHE_START, (
        "the shared file must be filled to the floor whatever the caller asked for")


def test_a_deeper_request_than_the_floor_is_honoured(tmp_path, monkeypatch):
    monkeypatch.setattr(live_lib, "DATA_DIR", str(tmp_path))
    asked = {}

    def fake_download(ticker, start=None, **kw):
        asked["start"] = start
        idx = pd.date_range(start, "2026-09-09", freq="B")
        return pd.DataFrame({"Open": 1.0, "High": 1.0, "Low": 1.0,
                             "Close": 1.0, "Volume": 1.0}, index=idx)

    monkeypatch.setitem(sys.modules, "yfinance",
                        type("yf", (), {"download": staticmethod(fake_download)}))
    live_lib.MarketData().daily("SPY", lookback_days=40_000)     # ~110 years
    assert asked["start"] < live_lib.DAILY_CACHE_START


def test_a_refresh_never_drops_bars_the_cache_already_had(tmp_path, monkeypatch):
    monkeypatch.setattr(live_lib, "DATA_DIR", str(tmp_path))
    path = live_lib.daily_cache_path("SPY")
    old = pd.DataFrame({"Open": 1.0, "High": 1.0, "Low": 1.0, "Close": 1.0,
                        "Volume": 1.0},
                       index=pd.date_range("2005-01-03", periods=200, freq="B"))
    live_lib._atomic_parquet(old, path)
    os.utime(path, (0, 0))                          # force a refresh

    def fake_download(ticker, start=None, **kw):
        idx = pd.date_range("2026-01-01", "2026-09-09", freq="B")
        return pd.DataFrame({"Open": 2.0, "High": 2.0, "Low": 2.0, "Close": 2.0,
                             "Volume": 2.0}, index=idx)

    monkeypatch.setitem(sys.modules, "yfinance",
                        type("yf", (), {"download": staticmethod(fake_download)}))
    out = live_lib.MarketData().daily("SPY")
    assert out.index.min() == pd.Timestamp("2005-01-03"), "history was truncated"
    assert out.index.max() == pd.Timestamp("2026-09-09"), "the refresh was lost"
