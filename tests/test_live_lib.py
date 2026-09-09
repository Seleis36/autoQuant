"""Execution runtime: ledger arithmetic, bar scheduling, history assembly.

Nothing here touches the network. The broker is constructed with force_shadow=True (which
short-circuits every venue call in __init__) and the order path is exercised by stubbing
the one HTTP helper.
"""
import json
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

import live_lib
from live_lib import PaperBroker, next_boundary


MARK = 100.0


@pytest.fixture
def broker(tmp_path, monkeypatch):
    """A shadow broker with a fixed mark. force_shadow skips every venue call in
    __init__, but set_target_weight still prices the trade through mark_price()."""
    b = PaperBroker("BTCUSDT", capital_usdt=1000.0, force_shadow=True,
                    state_file=str(tmp_path / "ledger.json"))
    monkeypatch.setattr(b, "mark_price", lambda: MARK)
    return b


# --------------------------------------------------------------------- bar scheduling

@pytest.mark.parametrize("now,expected", [
    ("2026-01-01T00:00:00+00:00", "2026-01-01T00:00:20+00:00"),
    ("2026-01-01T00:00:19+00:00", "2026-01-01T00:00:20+00:00"),
    ("2026-01-01T00:00:20+00:00", "2026-01-01T01:00:20+00:00"),  # just past a boundary
    ("2026-01-01T00:59:59+00:00", "2026-01-01T01:00:20+00:00"),
])
def test_next_boundary_hourly(now, expected):
    got = next_boundary("1h", datetime.fromisoformat(now), offset_s=20.0)
    assert got == datetime.fromisoformat(expected)


def test_next_boundary_is_always_in_the_future():
    now = datetime(2026, 3, 4, 7, 0, 20, tzinfo=timezone.utc)
    for sched in live_lib._INTERVAL_SECONDS:
        assert next_boundary(sched, now, offset_s=20.0) > now


def test_next_boundary_rejects_an_unknown_schedule():
    with pytest.raises(ValueError):
        next_boundary("3s")


# --------------------------------------------------------------------- shadow ledger

def test_shadow_buy_then_sell_conserves_the_book(broker):
    rep = broker.set_target_weight(1.0)
    assert rep["traded"] and rep["side"] == "BUY"
    assert broker.position() > 0

    rep = broker.set_target_weight(0.0)
    assert rep["side"] == "SELL"
    assert broker.position() == pytest.approx(0.0, abs=1e-8)
    # Two crossings of a 10bp fee and 1bp slippage; the book must be down, not up.
    assert broker.equity(MARK) < 1000.0


def test_weight_is_clamped_to_long_flat(broker):
    """Spot testnet has no shorting, so a negative target is flat, not a short."""
    broker.set_target_weight(-1.0)
    assert broker.position() == 0.0
    rep = broker.set_target_weight(5.0)
    assert rep["weight"] <= broker.max_weight


def test_ledger_survives_a_restart(tmp_path, monkeypatch):
    f = str(tmp_path / "ledger.json")
    b1 = PaperBroker("BTCUSDT", capital_usdt=1000.0, force_shadow=True, state_file=f)
    monkeypatch.setattr(b1, "mark_price", lambda: MARK)
    b1.set_target_weight(1.0)
    pos, quote = b1.position(), b1._quote_units

    b2 = PaperBroker("BTCUSDT", capital_usdt=1000.0, force_shadow=True, state_file=f)
    assert b2.position() == pytest.approx(pos)
    assert b2._quote_units == pytest.approx(quote)


def test_a_ledger_for_a_different_symbol_is_not_adopted(tmp_path):
    f = tmp_path / "ledger.json"
    f.write_text(json.dumps({"symbol": "ETHUSDT", "base": 5.0, "quote": 1.0}))
    b = PaperBroker("BTCUSDT", capital_usdt=1000.0, force_shadow=True, state_file=str(f))
    assert b.position() == 0.0, "an ETH ledger must not seed a BTC book"


def test_round_qty_never_rounds_up(broker):
    broker.step, broker.qty_prec = 0.001, 3
    assert broker._round_qty(0.0019) == pytest.approx(0.001)
    assert broker._round_qty(0.002) == pytest.approx(0.002)


def test_a_sub_minimum_delta_is_skipped_not_traded(broker):
    broker.set_target_weight(1.0)
    before = broker.position()
    rep = broker.set_target_weight(0.9999999)
    assert rep["traded"] is False and "skipped" in rep
    assert broker.position() == before


# ------------------------------------------------------- live fills and commission
#
# Binance charges a BUY's commission in the BASE asset. Counting only quote-asset
# commission credited the ledger with base units the account never received, so the book
# drifted further from the exchange on every buy.

@pytest.fixture
def live_broker(tmp_path, monkeypatch):
    b = PaperBroker("BTCUSDT", capital_usdt=1000.0, force_shadow=True,
                    state_file=str(tmp_path / "ledger.json"))
    b.shadow = False                     # take the real order path, with stubbed HTTP
    b.key, b.secret = "k", "s"
    b.step, b.min_qty, b.min_notional, b.qty_prec = 1e-5, 1e-5, 5.0, 5
    monkeypatch.setattr(b, "mark_price", lambda: 100.0)
    monkeypatch.setattr(b, "account_balances", lambda: {
        "BTC": {"free": 100.0, "locked": 0.0}, "USDT": {"free": 1e6, "locked": 0.0}})
    return b


def test_buy_commission_in_the_base_asset_leaves_the_ledger(live_broker, monkeypatch):
    monkeypatch.setattr(live_broker, "_signed", lambda *a, **k: {
        "orderId": 1, "status": "FILLED", "executedQty": "1.0",
        "cummulativeQuoteQty": "100.0",
        "fills": [{"commission": "0.001", "commissionAsset": "BTC"}]})
    rep = live_broker.set_target_weight(0.1)
    assert live_broker.position() == pytest.approx(1.0 - 0.001), (
        "the base-asset commission must come out of the base units")
    assert rep["fee"] == pytest.approx(0.001 * 100.0), "fee is journalled in quote terms"


def test_sell_commission_in_the_quote_asset_leaves_the_ledger(live_broker, monkeypatch):
    live_broker._base_units, live_broker._quote_units = 2.0, 0.0
    monkeypatch.setattr(live_broker, "_signed", lambda *a, **k: {
        "orderId": 2, "status": "FILLED", "executedQty": "2.0",
        "cummulativeQuoteQty": "200.0",
        "fills": [{"commission": "0.2", "commissionAsset": "USDT"}]})
    live_broker.set_target_weight(0.0)
    assert live_broker.position() == pytest.approx(0.0)
    assert live_broker._quote_units == pytest.approx(200.0 - 0.2)


def test_a_rejected_order_does_not_move_the_ledger(live_broker, monkeypatch):
    def boom(*a, **k):
        raise live_lib.BinanceError(-2010, "insufficient balance", 400)
    monkeypatch.setattr(live_broker, "_signed", boom)
    rep = live_broker.set_target_weight(1.0)
    assert "error" in rep and rep["traded"] is False
    assert live_broker.position() == 0.0


# --------------------------------------------------------------------- http retries

def test_request_does_not_sleep_after_the_final_attempt(monkeypatch):
    """The backoff used to run after the last try too, adding 4s to every hard failure."""
    slept, tries = [], []
    monkeypatch.setattr(live_lib.time, "sleep", lambda s: slept.append(s))

    def fail(*a, **k):
        tries.append(1)
        raise OSError("down")
    monkeypatch.setattr(live_lib.urllib.request, "urlopen", fail)

    with pytest.raises(RuntimeError):
        live_lib._request("http://example.invalid", retries=3)
    assert len(tries) == 3
    assert slept == [1, 2], f"expected backoff between tries only, got {slept}"


def test_a_deterministic_4xx_is_not_retried(monkeypatch):
    import urllib.error
    tries = []

    def fail(*a, **k):
        tries.append(1)
        raise urllib.error.HTTPError("u", 400, "bad", {}, None)
    monkeypatch.setattr(live_lib.urllib.request, "urlopen", fail)
    monkeypatch.setattr(live_lib.time, "sleep", lambda s: None)

    with pytest.raises(live_lib.BinanceError):
        live_lib._request("http://example.invalid", retries=3)
    assert len(tries) == 1


# --------------------------------------------------------------------- history gaps

def _series(start, n, step_h=1):
    idx = pd.date_range(start, periods=n, freq=f"{step_h}h", tz="UTC")
    return pd.DataFrame({"Open": 1.0, "High": 1.0, "Low": 1.0, "Close": 1.0,
                         "Volume": 1.0}, index=idx)


def test_history_fills_a_gap_left_by_a_long_outage(tmp_path, monkeypatch):
    """The cache is already `bars` deep, so the old code took the cheap top-up branch:
    one tail fetch spliced straight onto a cache that ended 800 bars earlier, leaving a
    hole in the middle that every rolling window then silently spanned."""
    monkeypatch.setattr(live_lib, "DATA_DIR", str(tmp_path))
    full = _series("2026-01-01", 2000)          # the venue's whole history
    full.iloc[:1200].to_parquet(               # deep enough, but 800 bars stale
        tmp_path / "BTCUSDT_1h_public_live.parquet")

    md = live_lib.MarketData("public")
    monkeypatch.setattr(md, "_max_limit", lambda: 300)   # each fetch covers 300 bars

    def fake_klines(symbol, interval, limit=500, end_time=None):
        upto = full if end_time is None else full[full.index <= pd.Timestamp(end_time)]
        return upto.iloc[-limit:]
    monkeypatch.setattr(md, "klines", fake_klines)

    out = md.history("BTCUSDT", "1h", bars=1200)
    deltas = out.index.to_series().diff().dropna().dt.total_seconds().unique()
    assert list(deltas) == [3600.0], f"series is not contiguous: {deltas}"
    assert len(out) == 1200
    assert out.index[-1] == full.index[-1], "must reach the present"


def test_history_uses_a_single_fetch_when_the_cache_is_current(tmp_path, monkeypatch):
    monkeypatch.setattr(live_lib, "DATA_DIR", str(tmp_path))
    full = _series("2026-01-01", 500)
    full.iloc[:495].to_parquet(tmp_path / "BTCUSDT_1h_public_live.parquet")

    md = live_lib.MarketData("public")
    monkeypatch.setattr(md, "_max_limit", lambda: 300)
    calls = []

    def fake_klines(symbol, interval, limit=500, end_time=None):
        calls.append(end_time)
        upto = full if end_time is None else full[full.index <= pd.Timestamp(end_time)]
        return upto.iloc[-limit:]
    monkeypatch.setattr(md, "klines", fake_klines)

    out = md.history("BTCUSDT", "1h", bars=400)
    assert len(calls) == 1, "an overlapping top-up needs exactly one fetch"
    assert len(out) == 400
