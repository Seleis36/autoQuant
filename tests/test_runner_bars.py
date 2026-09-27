"""Bar-advance gating, state merging, and rebuilding a broker from its meta.json.

The gating is what lets a strategy trade an instrument that is not open 24/7 without
a market calendar: the runner acts when the printed bar changes and does nothing when
it has not, so a weekend, a holiday, a half-day and a late data vendor are all the
same non-event.
"""
import json

import pytest

import live_lib
from live_lib import QuoteSource, SimBroker, StrategyRunner


class StubQuotes(QuoteSource):
    name = "stub"
    bars_per_year_daily = 252.0

    def __init__(self, price=100.0, bar=None):
        self._price, self.bar = price, bar

    def price(self, symbol):
        return self._price

    def bar_key(self, symbol):
        return self.bar


def make_runner(tmp_path, quotes, weight=1.0, schedule="1d"):
    b = SimBroker("SPY", capital_usdt=10_000.0, quotes=quotes,
                  state_file=str(tmp_path / "ledger.json"))
    return StrategyRunner("sim/x", "SPY", schedule, compute_weight=lambda now: weight,
                          broker=b, state_dir=str(tmp_path))


def rebalances(tmp_path):
    p = tmp_path / "journal.jsonl"
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()
            and json.loads(l).get("event") == "rebalance"]


# --------------------------------------------------------------------- gating

def test_a_continuous_market_trades_every_tick(tmp_path):
    """Crypto behaviour, unchanged: no bar identity means every boundary is fresh."""
    r = make_runner(tmp_path, StubQuotes(bar=None))
    r._tick()
    r._tick()
    assert len(rebalances(tmp_path)) == 2


def test_a_session_market_trades_once_per_bar(tmp_path):
    q = StubQuotes(bar="2026-09-09")
    r = make_runner(tmp_path, q)
    assert r._tick() is not None
    assert r._tick() is None, "the same bar must not be traded twice"
    assert r._tick() is None
    assert len(rebalances(tmp_path)) == 1


def test_a_new_bar_releases_the_gate(tmp_path):
    q = StubQuotes(bar="2026-09-09")
    r = make_runner(tmp_path, q)
    r._tick()
    q.bar = "2026-09-10"
    assert r._tick() is not None
    assert len(rebalances(tmp_path)) == 2


def test_a_restart_does_not_re_trade_the_last_bar(tmp_path):
    q = StubQuotes(bar="2026-09-09")
    make_runner(tmp_path, q)._tick()
    r2 = make_runner(tmp_path, q)                 # fresh process, same state dir
    assert r2._last_bar == "2026-09-09"
    assert r2._tick() is None
    assert len(rebalances(tmp_path)) == 1


def test_a_skipped_poll_is_journalled_as_nothing(tmp_path):
    """A weekend must not fill the journal with rows the metrics would read as bars."""
    q = StubQuotes(bar="2026-09-09")
    r = make_runner(tmp_path, q)
    r._tick()
    for _ in range(5):
        r._tick()
    assert len(rebalances(tmp_path)) == 1


def test_step_once_ignores_the_gate(tmp_path):
    """`--once` is an operator forcing a rebalance by hand; it should obey them."""
    q = StubQuotes(bar="2026-09-09")
    r = make_runner(tmp_path, q)
    r._tick()
    r.step_once()
    assert len(rebalances(tmp_path)) == 2


# --------------------------------------------------------------------- state

def test_a_skipped_poll_keeps_the_daemon_looking_alive(tmp_path):
    """`last_run` drives the staleness watchdog. Leaving it at the last TRADE would
    show every equity strategy as hung from Friday evening until Monday."""
    q = StubQuotes(bar="2026-09-09")
    r = make_runner(tmp_path, q)
    r._tick()
    first = json.loads((tmp_path / "state.json").read_text())["last_run"]
    r._tick()
    st = json.loads((tmp_path / "state.json").read_text())
    assert st["last_run"] > first
    assert st["waiting_for_new_bar"] is True


def test_a_skipped_poll_does_not_erase_the_last_numbers(tmp_path):
    """The dashboard reads these. Rewriting state.json from scratch on a quiet poll
    would blank a perfectly healthy strategy."""
    q = StubQuotes(bar="2026-09-09")
    r = make_runner(tmp_path, q)
    r._tick()
    before = json.loads((tmp_path / "state.json").read_text())
    r._tick()
    after = json.loads((tmp_path / "state.json").read_text())
    for k in ("last_weight", "equity", "position", "capital_usdt"):
        assert after[k] == before[k], f"{k} was lost on a quiet poll"


def test_state_records_the_mode_so_sim_is_distinguishable(tmp_path):
    r = make_runner(tmp_path, StubQuotes(bar=None))
    r._tick()
    st = json.loads((tmp_path / "state.json").read_text())
    assert st["mode"] == "sim" and st["shadow"] is True


def test_the_journal_carries_its_own_annualisation(tmp_path):
    r = make_runner(tmp_path, StubQuotes(bar="2026-09-09"))
    r._tick()
    assert rebalances(tmp_path)[0]["bars_per_year"] == 252.0


def test_a_continuous_daily_book_annualises_at_365(tmp_path):
    b = SimBroker("BTCUSDT", capital_usdt=1000.0, quotes="binance-public",
                  state_file=str(tmp_path / "ledger.json"))
    r = StrategyRunner("sim/btc", "BTCUSDT", "1d", compute_weight=lambda now: 0.0,
                       broker=b, state_dir=str(tmp_path))
    assert r._journal_context(None)["bars_per_year"] == 365.0


# --------------------------------------------------- rebuilding a broker from meta

def test_meta_without_a_book_rebuilds_the_venue_broker(tmp_path):
    b = live_lib.broker_from_meta({"symbol": "BTCUSDT", "capital_usdt": 2500.0,
                                   "quotes": "binance-public"},
                                  state_file=str(tmp_path / "l.json"))
    assert isinstance(b, live_lib.PaperBroker)


def test_a_sim_meta_rebuilds_a_sim_broker(tmp_path):
    b = live_lib.broker_from_meta({"symbol": "SPY", "book": "sim",
                                   "capital_usdt": 2500.0, "allow_short": True},
                                  state_file=str(tmp_path / "l.json"))
    assert isinstance(b, live_lib.SimBroker)
    assert b.allow_short is True and b.mode == "sim"


def test_a_basket_meta_rebuilds_a_portfolio_broker(tmp_path):
    """The flatten button used to assume a PaperBroker. Pointed at a basket it would
    read a ledger it cannot parse, find no position, and report success having sold
    nothing."""
    from portfolio import SimPortfolioBroker
    b = live_lib.broker_from_meta({"symbols": ["XLK", "XLE"], "book": "sim",
                                   "capital_usdt": 5000.0, "max_gross": 2.0},
                                  state_file=str(tmp_path / "l.json"))
    assert isinstance(b, SimPortfolioBroker)
    assert b.symbols == ["XLK", "XLE"] and b.max_gross == 2.0


def test_a_basket_meta_carries_an_open_universe(tmp_path):
    """Flatten must rebuild the book the daemon runs: a closed-universe rebuild of an
    index book would read its ledger as another basket's and flatten nothing."""
    b = live_lib.broker_from_meta({"symbols": ["XLK"], "book": "sim", "open_universe": True},
                                  state_file=str(tmp_path / "l.json"))
    assert b.open_universe


def test_a_meta_naming_no_instrument_is_refused(tmp_path):
    with pytest.raises(ValueError, match="neither"):
        live_lib.broker_from_meta({"book": "sim"}, state_file=str(tmp_path / "l.json"))


def test_once_records_the_bar_it_traded(tmp_path):
    """`--once` bypasses the gate, but a daemon started after it must not re-trade the
    bar it already acted on -- which is exactly what an unrecorded bar caused."""
    q = StubQuotes(bar="2026-09-09")
    r = make_runner(tmp_path, q)
    r.cli(["--once"])
    assert json.loads((tmp_path / "state.json").read_text())["last_bar"] == "2026-09-09"

    r2 = make_runner(tmp_path, q)
    assert r2._tick() is None
    assert len(rebalances(tmp_path)) == 1


def test_once_still_forces_a_rebalance_on_a_traded_bar(tmp_path):
    q = StubQuotes(bar="2026-09-09")
    r = make_runner(tmp_path, q)
    r._tick()
    r.cli(["--once"])
    assert len(rebalances(tmp_path)) == 2, "--once must ignore the gate"


# ------------------------------------------------- re-checking a bar that is late

class FakeStop:
    """Stands in for the runner's threading.Event so `run()` is drivable in a test.

    Records every sleep the loop asks for and ends the loop after `iterations`.
    """

    def __init__(self, iterations):
        self.left = iterations
        self.waits = []

    def is_set(self):
        return self.left <= 0

    def wait(self, seconds):
        self.waits.append(seconds)
        self.left -= 1
        return False

    def set(self):
        self.left = 0


def test_waiting_for_a_bar_is_recorded_on_the_runner(tmp_path):
    q = StubQuotes(bar="2026-09-09")
    r = make_runner(tmp_path, q)
    r._tick()
    assert r._waiting_for_bar is False, "it just traded this bar"
    r._tick()
    assert r._waiting_for_bar is True, "same bar again: now waiting"
    q.bar = "2026-09-10"
    r._tick()
    assert r._waiting_for_bar is False, "a new bar clears the wait"


def test_the_wait_is_logged_once_per_bar_not_once_per_recheck(tmp_path, capsys):
    """The loop now re-checks every recheck_s while it waits. Logging each one would
    bury a weekend's worth of real entries under identical lines.

    Read off stdout rather than caplog: _setup_logging uses basicConfig(force=True),
    which drops caplog's handler the moment a runner is constructed.
    """
    q = StubQuotes(bar="2026-09-09")
    r = make_runner(tmp_path, q)
    r._tick()
    for _ in range(5):
        r._tick()
    q.bar = "2026-09-10"
    r._tick()              # trades
    for _ in range(5):
        r._tick()          # waits on the new bar
    waits = [l for l in capsys.readouterr().out.splitlines() if "already traded" in l]
    assert len(waits) == 2, f"one line per bar waited on, got {waits}"
    assert "2026-09-09" in waits[0] and "2026-09-10" in waits[1]


def test_a_late_vendor_is_rechecked_long_before_the_next_daily_boundary(tmp_path):
    """The bug this fixes: on a 1d schedule the next boundary is up to 24h away, so a
    vendor that had not published by the wake-up meant the session's decision was
    skipped in silence -- TLT skipped 2026-09-16 and 2026-09-17 that way."""
    q = StubQuotes(bar="2026-09-09")
    r = make_runner(tmp_path, q)
    r.recheck_s = 60.0
    r._stop = FakeStop(iterations=2)
    r.run()

    assert len(r._stop.waits) == 2
    assert r._stop.waits[0] > 3600, "just traded: sleep to the next daily boundary"
    assert r._stop.waits[1] <= 60.0, "waiting on a late bar: come back soon"


def test_a_recheck_that_finds_the_new_bar_trades_it(tmp_path):
    q = StubQuotes(bar="2026-09-09")
    r = make_runner(tmp_path, q)
    r.recheck_s = 60.0
    r._stop = FakeStop(iterations=2)

    real_wait = r._stop.wait

    def publish_then_wait(seconds):          # the vendor catches up mid-sleep
        out = real_wait(seconds)
        q.bar = "2026-09-10"
        return out

    r._stop.wait = publish_then_wait
    r.run()
    traded = [b["bar"] for b in rebalances(tmp_path)]
    assert traded == ["2026-09-09", "2026-09-10"], traded


def test_recheck_can_be_switched_off(tmp_path):
    """recheck_s=0 restores the old behaviour: one look per boundary."""
    q = StubQuotes(bar="2026-09-09")
    r = make_runner(tmp_path, q)
    r.recheck_s = 0.0
    r._stop = FakeStop(iterations=2)
    r.run()
    assert all(w > 3600 for w in r._stop.waits), r._stop.waits


def test_a_continuous_market_never_waits_and_keeps_its_boundary_sleep(tmp_path):
    """Crypto is unaffected: bar_key() is None, so every wake-up trades."""
    r = make_runner(tmp_path, StubQuotes(bar=None), schedule="1h")
    r._stop = FakeStop(iterations=2)
    r.run()
    assert r._waiting_for_bar is False
    assert all(w > 60 for w in r._stop.waits), r._stop.waits
    assert len(rebalances(tmp_path)) == 3
