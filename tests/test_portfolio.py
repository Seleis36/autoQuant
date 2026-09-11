"""The cross-sectional book: leverage caps, ordering, shorting, and restart safety.

These are the strategies the desk could not deploy at all -- `sector-etf` trading the
SPDRs against each other, `fx-majors` on crosses, a short-vol leg -- so the arithmetic
here has never been exercised by the venue path and is tested from scratch.
"""
import json

import pytest

from live_lib import QuoteSource
from portfolio import PortfolioRunner, SimPortfolioBroker

SYMS = ["XLK", "XLE", "XLF"]


class StubQuotes(QuoteSource):
    name = "stub"
    bars_per_year_daily = 252.0

    def __init__(self, prices, bars=None):
        self.prices = dict(prices)
        self.bars = dict(bars or {})

    def price(self, symbol):
        return self.prices[symbol]

    def bar_key(self, symbol):
        return self.bars.get(symbol, "2026-09-09")


@pytest.fixture
def quotes():
    return StubQuotes({"XLK": 100.0, "XLE": 50.0, "XLF": 25.0})


@pytest.fixture
def book(tmp_path, quotes):
    return SimPortfolioBroker(SYMS, capital_usdt=100_000.0, quotes=quotes,
                              allow_short=True, state_file=str(tmp_path / "l.json"))


# --------------------------------------------------------------------- construction

def test_a_portfolio_needs_symbols(quotes):
    with pytest.raises(ValueError, match="at least one symbol"):
        SimPortfolioBroker([], quotes=quotes)


def test_duplicate_symbols_collapse_but_keep_order(quotes):
    b = SimPortfolioBroker(["XLK", "XLE", "XLK"], quotes=quotes)
    assert b.symbols == ["XLK", "XLE"]


def test_a_scalar_weight_is_refused_rather_than_applied_to_a_guess(book):
    with pytest.raises(TypeError, match="set_target_weights"):
        book.set_target_weight(1.0)


# --------------------------------------------------------------------- exposure

def test_a_market_neutral_book_holds_its_net_at_zero(book):
    rep = book.set_target_weights({"XLK": 0.5, "XLE": -0.5, "XLF": 0.0})
    assert rep["net"] == pytest.approx(0.0, abs=1e-9)
    # Legs are sized against PRE-trade equity, so paying the cost of getting there
    # leaves realised gross a hair over the target -- 100000/99890 here. It is not
    # worth iterating to remove: the next rebalance sizes off the new equity.
    assert 1.0 <= rep["gross"] < 1.005


def test_gross_above_the_cap_is_scaled_not_clipped(book):
    """Clipping the largest leg would quietly change the strategy's relative bets --
    a different strategy wearing the same name."""
    rep = book.set_target_weights({"XLK": 1.0, "XLE": -0.5, "XLF": 0.0})
    assert rep["scaled_by"] == pytest.approx(1 / 1.5)
    assert rep["requested_gross"] == pytest.approx(1.5)
    w = rep["target_weights"]
    assert w["XLK"] / -w["XLE"] == pytest.approx(2.0)     # the 2:1 bet survived


def test_a_book_inside_the_cap_is_left_alone(book):
    rep = book.set_target_weights({"XLK": 0.3, "XLE": -0.2, "XLF": 0.1})
    assert "scaled_by" not in rep
    assert rep["gross"] == pytest.approx(0.6, rel=1e-3)


def test_shorts_are_zeroed_and_reported_when_not_allowed(tmp_path, quotes):
    b = SimPortfolioBroker(SYMS, capital_usdt=100_000.0, quotes=quotes,
                           allow_short=False, state_file=str(tmp_path / "l.json"))
    rep = b.set_target_weights({"XLK": 0.5, "XLE": -0.5, "XLF": 0.0})
    assert rep["clamped_shorts"] == ["XLE"]
    assert b.position("XLE") == 0.0
    assert b.position("XLK") > 0


# --------------------------------------------------------------------- execution

def test_sells_are_executed_before_buys(book):
    book.set_target_weights({"XLK": 0.6, "XLE": 0.0, "XLF": 0.0})
    rep = book.set_target_weights({"XLK": 0.0, "XLE": 0.6, "XLF": 0.0})
    sides = [l["side"] for l in rep["legs"]]
    assert sides.index("SELL") < sides.index("BUY"), (
        "a rotation must fund its buys from the sale, not dip the cash balance")
    assert rep["cash"] >= 0


def test_turnover_and_fees_are_reported_for_the_whole_basket(book):
    rep = book.set_target_weights({"XLK": 0.5, "XLE": -0.5, "XLF": 0.0})
    assert rep["turnover_usdt"] == pytest.approx(100_000.0, rel=1e-3)
    assert rep["fee"] == pytest.approx(100.0, rel=1e-3)     # 10bp of the notional


def test_equity_is_conserved_across_a_costless_rebalance(tmp_path, quotes):
    b = SimPortfolioBroker(SYMS, capital_usdt=100_000.0, quotes=quotes,
                           allow_short=True, fee_bps=0.0, slippage_bps=0.0,
                           state_file=str(tmp_path / "l.json"))
    b.set_target_weights({"XLK": 0.5, "XLE": -0.5, "XLF": 0.0})
    assert b.equity() == pytest.approx(100_000.0)


def test_a_price_move_flows_into_equity_with_the_right_sign(book, quotes):
    book.set_target_weights({"XLK": 0.5, "XLE": -0.5, "XLF": 0.0})
    before = book.equity()
    quotes.prices["XLK"] = 110.0            # the long leg rallies
    assert book.equity() > before
    quotes.prices["XLK"] = 100.0
    quotes.prices["XLE"] = 55.0             # the short leg rallies
    assert book.equity() < before


def test_an_unknown_symbol_is_refused_not_ignored(book):
    with pytest.raises(ValueError, match="does not hold"):
        book.set_target_weights({"XLK": 0.5, "TSLA": 0.5})


def test_a_nan_weight_is_refused(book):
    with pytest.raises(ValueError, match="NaN"):
        book.set_target_weights({"XLK": float("nan")})


def test_an_omitted_symbol_means_flat_not_unchanged(book):
    book.set_target_weights({"XLK": 0.5, "XLE": 0.3, "XLF": 0.0})
    book.set_target_weights({"XLK": 0.5})
    assert book.position("XLE") == pytest.approx(0.0, abs=1e-9)


def test_flatten_closes_every_leg(book):
    book.set_target_weights({"XLK": 0.4, "XLE": -0.4, "XLF": 0.2})
    rep = book.flatten()
    assert rep["gross"] == pytest.approx(0.0, abs=1e-9)
    assert all(abs(v) < 1e-9 for v in book.position().values())


def test_a_wiped_out_book_refuses_to_trade(book):
    book._cash = -1_000_000.0
    with pytest.raises(RuntimeError, match="wiped out"):
        book.set_target_weights({"XLK": 0.5})


# --------------------------------------------------------------------- bars

def test_the_book_waits_for_the_slowest_leg(book, quotes):
    """Rebalancing a cross-section against a stale leg trades the whole basket on
    information one of its members has not produced yet."""
    quotes.bars = {"XLK": "2026-09-09", "XLE": "2026-09-08", "XLF": "2026-09-09"}
    assert book.bar_key() == "2026-09-08"
    quotes.bars["XLE"] = "2026-09-09"
    assert book.bar_key() == "2026-09-09"


def test_a_continuous_leg_makes_the_book_continuous(tmp_path):
    class Continuous(StubQuotes):
        def bar_key(self, symbol):
            return None
    b = SimPortfolioBroker(SYMS, quotes=Continuous({s: 1.0 for s in SYMS}),
                           state_file=str(tmp_path / "l.json"))
    assert b.bar_key() is None


# --------------------------------------------------------------------- persistence

def test_the_book_survives_a_restart(tmp_path, quotes):
    f = str(tmp_path / "l.json")
    b1 = SimPortfolioBroker(SYMS, capital_usdt=100_000.0, quotes=quotes,
                            allow_short=True, state_file=f)
    b1.set_target_weights({"XLK": 0.4, "XLE": -0.3, "XLF": 0.1})
    b2 = SimPortfolioBroker(SYMS, capital_usdt=100_000.0, quotes=quotes,
                            allow_short=True, state_file=f)
    assert b2.position() == pytest.approx(b1.position())
    assert b2.equity() == pytest.approx(b1.equity())


def test_a_ledger_for_a_different_basket_is_not_adopted(tmp_path, quotes):
    f = tmp_path / "l.json"
    f.write_text(json.dumps({"symbols": ["AAA", "BBB"], "positions": {"AAA": 9.0},
                             "cash": 5.0}))
    b = SimPortfolioBroker(SYMS, capital_usdt=100_000.0, quotes=quotes,
                           state_file=str(f))
    assert b.equity() == 100_000.0
    assert all(v == 0.0 for v in b.position().values())


# --------------------------------------------------------------------- the runner

def test_the_runner_journals_a_basket_the_metrics_can_read(tmp_path, quotes):
    """`weight` must be net exposure and `price` must be absent -- a basket has no
    instrument to buy and hold, and inventing one puts a fake benchmark on the chart."""
    b = SimPortfolioBroker(SYMS, capital_usdt=100_000.0, quotes=quotes,
                           allow_short=True, state_file=str(tmp_path / "l.json"))
    r = PortfolioRunner("sector-etf/x", SYMS, "1d",
                        compute_weights=lambda now: {"XLK": 0.5, "XLE": -0.5},
                        broker=b, state_dir=str(tmp_path))
    r.step_once(bar="2026-09-09")
    row = json.loads((tmp_path / "journal.jsonl").read_text().strip())
    assert row["event"] == "rebalance"
    assert row["weight"] == pytest.approx(0.0, abs=1e-9)
    assert "price" not in row
    assert row["turnover_usdt"] > 0
    assert row["bars_per_year"] == 252.0
    assert row["bar"] == "2026-09-09"


def test_the_runner_refuses_a_non_mapping(tmp_path, quotes):
    b = SimPortfolioBroker(SYMS, quotes=quotes, state_file=str(tmp_path / "l.json"))
    r = PortfolioRunner("x/y", SYMS, "1d", compute_weights=lambda now: 0.5,
                        broker=b, state_dir=str(tmp_path))
    with pytest.raises(TypeError, match="must return a dict"):
        r.step_once()


@pytest.mark.parametrize("bad", [0.0, -1.0])
def test_a_non_positive_leverage_cap_is_refused(quotes, bad):
    """Scaling only fires when `gross > max_gross > 0`, so a zero cap would wave every
    level of leverage through -- the opposite of what it looks like it does."""
    with pytest.raises(ValueError, match="max_gross must be positive"):
        SimPortfolioBroker(SYMS, quotes=quotes, max_gross=bad)


def test_leverage_above_one_is_allowed_when_asked_for(tmp_path, quotes):
    """`max_gross` is a cap, not a fixed 1.0: the cash balance goes negative and equity
    still reconciles, which is what borrowing to hold 2x actually looks like."""
    b = SimPortfolioBroker(SYMS, capital_usdt=100_000.0, quotes=quotes, max_gross=2.0,
                           fee_bps=0.0, slippage_bps=0.0, allow_short=False,
                           state_file=str(tmp_path / "l.json"))
    rep = b.set_target_weights({"XLK": 1.0, "XLE": 1.0})
    assert rep["gross"] == pytest.approx(2.0)
    assert rep["cash"] == pytest.approx(-100_000.0)
    assert b.equity() == pytest.approx(100_000.0)
