"""The simulated single-instrument book, and the quote sources it marks against.

Nothing here touches the network: every broker is given a stub quote source, which is
also the point of the abstraction -- a paper book that needed a venue to be tested was
a paper book welded to that venue.
"""
import json

import pytest

import live_lib
from live_lib import QuoteSource, SimBroker, quote_source


class StubQuotes(QuoteSource):
    """A fixed price, and a bar identity the test controls."""

    name = "stub"
    bars_per_year_daily = 252.0

    def __init__(self, prices, bar=None):
        self.prices = dict(prices)
        self.bar = bar
        self.price_calls = 0

    def price(self, symbol):
        self.price_calls += 1
        return self.prices[symbol]

    def bar_key(self, symbol):
        return self.bar


@pytest.fixture
def quotes():
    return StubQuotes({"SPY": 100.0}, bar="2026-09-09")


@pytest.fixture
def broker(tmp_path, quotes):
    return SimBroker("SPY", capital_usdt=10_000.0, quotes=quotes,
                     state_file=str(tmp_path / "ledger.json"))


# --------------------------------------------------------------------- construction

def test_a_plain_ticker_is_its_own_base(broker):
    """Splitting `SPY` by the Binance BASE+QUOTE rule leaves an empty base, and every
    log line and reconciliation downstream then names nothing."""
    assert broker.base == "SPY"
    assert broker.quote == "USD"


def test_a_simulated_book_is_not_a_degraded_one(broker):
    """`shadow` is true for both, but only a venue book that lost its venue is a fault."""
    assert broker.shadow is True
    assert broker.mode == "sim"
    assert broker.preflight()["mode"] == "sim"
    assert "reason" not in broker.preflight()


def test_it_never_reaches_for_a_venue(broker, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("a simulated book must not make an HTTP request")
    monkeypatch.setattr(live_lib, "_request", boom)
    broker.preflight()
    broker.set_target_weight(0.5)
    broker.flatten()


# --------------------------------------------------------------------- fills

def test_fractional_sizing_holds_a_partial_share(broker):
    """A 2500-dollar book has to be able to hold a 763-dollar share."""
    rep = broker.set_target_weight(0.5)
    assert rep["traded"]
    assert broker.position() == pytest.approx(50.0)      # 5000 / 100, not rounded to a lot


def test_a_round_trip_costs_two_crossings(broker):
    broker.set_target_weight(1.0)
    broker.set_target_weight(0.0)
    assert broker.position() == pytest.approx(0.0, abs=1e-12)
    # 10bp fee + 1bp slippage, twice; the book must be down, never up.
    assert broker.equity(100.0) < 10_000.0
    assert broker.equity(100.0) > 9_950.0


def test_a_full_exit_leaves_no_dust(broker):
    """Weight 0 with a non-zero position would otherwise be a lie the journal carries
    forever: the exit is under `min_trade_usd` but must still go through."""
    broker.set_target_weight(1.0)
    broker.min_trade_usd = 1e9
    rep = broker.set_target_weight(0.0)
    assert rep["traded"] and "skipped" not in rep
    assert broker.position() == 0.0


def test_dust_below_the_trade_floor_is_skipped(broker):
    broker.set_target_weight(0.5)
    before = broker.position()
    broker.min_trade_usd = 100.0                 # nothing under $100 is worth trading
    rep = broker.set_target_weight(0.505)        # ~$47 of delta
    assert rep["traded"] is False and "skipped" in rep
    assert broker.position() == before


def test_a_delta_above_the_floor_does_trade(broker):
    """The other side of the floor, so the test above cannot pass by never trading."""
    broker.set_target_weight(0.5)
    broker.min_trade_usd = 10.0
    rep = broker.set_target_weight(0.6)          # ~$1000 of delta
    assert rep["traded"] is True and "skipped" not in rep


# --------------------------------------------------------------------- shorting

def test_shorting_is_refused_unless_asked_for(broker):
    broker.set_target_weight(-1.0)
    assert broker.position() == 0.0


def test_a_short_leaves_negative_units_and_the_cash_it_raised(tmp_path, quotes):
    b = SimBroker("SPY", capital_usdt=10_000.0, quotes=quotes, allow_short=True,
                  state_file=str(tmp_path / "l.json"))
    b.set_target_weight(-0.5)
    assert b.position() < 0
    assert b._quote_units > 10_000.0            # the sale proceeds are in cash
    assert b.equity(100.0) == pytest.approx(10_000.0, rel=2e-3)


def test_a_short_gains_when_the_price_falls(tmp_path, quotes):
    b = SimBroker("SPY", capital_usdt=10_000.0, quotes=quotes, allow_short=True,
                  state_file=str(tmp_path / "l.json"))
    b.set_target_weight(-1.0)
    assert b.equity(50.0) > b.equity(100.0)
    assert b.equity(150.0) < b.equity(100.0)


def test_leverage_is_capped_in_both_directions(tmp_path, quotes):
    b = SimBroker("SPY", capital_usdt=10_000.0, quotes=quotes, allow_short=True,
                  max_weight=0.5, state_file=str(tmp_path / "l.json"))
    assert b.set_target_weight(3.0)["weight"] == 0.5
    assert b.set_target_weight(-3.0)["weight"] == -0.5


# --------------------------------------------------------------------- persistence

def test_the_ledger_survives_a_restart(tmp_path, quotes):
    f = str(tmp_path / "l.json")
    b1 = SimBroker("SPY", capital_usdt=10_000.0, quotes=quotes, state_file=f)
    b1.set_target_weight(0.7)
    b2 = SimBroker("SPY", capital_usdt=10_000.0, quotes=quotes, state_file=f)
    assert b2.position() == pytest.approx(b1.position())
    assert b2._quote_units == pytest.approx(b1._quote_units)


def test_another_instruments_ledger_is_not_adopted(tmp_path, quotes):
    f = tmp_path / "l.json"
    f.write_text(json.dumps({"symbol": "QQQ", "base": 5.0, "quote": 1.0}))
    b = SimBroker("SPY", capital_usdt=10_000.0, quotes=quotes, state_file=str(f))
    assert b.position() == 0.0


def test_the_ledger_records_which_mode_wrote_it(tmp_path, quotes):
    f = tmp_path / "l.json"
    SimBroker("SPY", capital_usdt=1000.0, quotes=quotes,
              state_file=str(f)).set_target_weight(1.0)
    assert json.loads(f.read_text())["mode"] == "sim"


# --------------------------------------------------------------------- quote sources

def test_quote_source_accepts_a_name_or_an_instance():
    assert quote_source("binance-public").name == "binance-public"
    q = StubQuotes({})
    assert quote_source(q) is q


@pytest.mark.parametrize("bad,exc", [("nope", ValueError), (42, TypeError)])
def test_an_unusable_quote_source_is_refused(bad, exc):
    with pytest.raises(exc):
        quote_source(bad)


def test_a_continuous_market_reports_no_bar(tmp_path):
    b = SimBroker("BTCUSDT", quotes=StubQuotes({"BTCUSDT": 1.0}, bar=None),
                  state_file=str(tmp_path / "l.json"))
    assert b.bar_key() is None


def test_annualisation_follows_the_market_not_the_schedule(tmp_path, quotes):
    """A daily equity bar is one of ~252, not one of 365."""
    b = SimBroker("SPY", quotes=quotes, state_file=str(tmp_path / "l.json"))
    assert b.bars_per_year("1d") == 252.0
    assert b.bars_per_year("1h") is None        # sub-daily falls back to the table


def test_a_crypto_daily_bar_is_still_one_of_365(tmp_path):
    b = SimBroker("BTCUSDT", quotes="binance-public", state_file=str(tmp_path / "l.json"))
    assert b.bars_per_year("1d") == 365.0


def test_a_wiped_out_short_refuses_to_trade_rather_than_inverting(tmp_path):
    """`w * eq / px` flips sign once equity is negative, so a request to go fully LONG
    left the book SHORT. Unreachable on a long-only venue book, which is why it only
    appeared once shorting did."""
    q = StubQuotes({"X": 100.0})
    b = SimBroker("X", capital_usdt=1_000.0, quotes=q, allow_short=True,
                  fee_bps=0.0, slippage_bps=0.0, state_file=str(tmp_path / "l.json"))
    b.set_target_weight(-1.0)
    q.prices["X"] = 250.0                        # the short goes badly against us
    assert b.equity() < 0
    with pytest.raises(RuntimeError, match="wiped out"):
        b.set_target_weight(1.0)
    assert b.position() == -10.0, "the ledger must not have moved"


def test_a_solvent_book_is_unaffected_by_the_guard(broker):
    assert broker.set_target_weight(0.5)["traded"] is True


def _cache(tmp_path, monkeypatch, symbol, days):
    import pandas as pd
    monkeypatch.setattr(live_lib, "DATA_DIR", str(tmp_path))
    idx = pd.date_range("2025-06-01", periods=days, freq="D")
    pd.DataFrame({"Close": 1.0}, index=idx).to_parquet(live_lib.daily_cache_path(symbol))


def test_yahoo_crypto_prints_365_days_a_year(tmp_path, monkeypatch):
    """Yahoo carries both crypto and equities; the cached series says which this is."""
    _cache(tmp_path, monkeypatch, "SOL-USD", 500)
    assert live_lib.YahooQuotes().daily_bars_per_year("SOL-USD") == 365.0


def test_yahoo_weekday_series_stays_on_trading_days(tmp_path, monkeypatch):
    import pandas as pd
    monkeypatch.setattr(live_lib, "DATA_DIR", str(tmp_path))
    idx = pd.bdate_range("2025-06-02", periods=300)
    pd.DataFrame({"Close": 1.0}, index=idx).to_parquet(live_lib.daily_cache_path("SPY"))
    assert live_lib.YahooQuotes().daily_bars_per_year("SPY") == 252.0


def test_yahoo_without_a_cache_falls_back_and_never_downloads(tmp_path, monkeypatch):
    monkeypatch.setattr(live_lib, "DATA_DIR", str(tmp_path))
    q = live_lib.YahooQuotes()
    monkeypatch.setattr(q.md, "daily", lambda *a, **k: pytest.fail("touched the network"))
    assert q.daily_bars_per_year("NOPE") == 252.0
