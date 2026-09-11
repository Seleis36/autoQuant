"""Capital books: migration from the single pool, per-book accounting, and the caps.

`allocate` writes to a real file, so every test here points `ALLOC_PATH` at tmp_path
first. A test that forgot would rewrite the running desk's allocations.
"""
import json

import pytest

import live_lib
from live_lib import SIM_BOOK, VENUE_BOOK


@pytest.fixture
def alloc(tmp_path, monkeypatch):
    p = tmp_path / "allocations.json"
    monkeypatch.setattr(live_lib, "ALLOC_PATH", str(p))
    return p


def write_v1(path, pool=10_000.0, **strategies):
    """The pre-books file: one top-level pool, no `book` on any strategy."""
    path.write_text(json.dumps({
        "pool_usdt": pool,
        "strategies": {k: {"capital_usdt": v} for k, v in strategies.items()},
    }))


# --------------------------------------------------------------------- migration

def test_a_v1_file_migrates_its_pool_to_the_venue_book(alloc):
    write_v1(alloc, 10_000.0, **{"spot-btc/bult": 2500.0})
    d = live_lib._read_allocations()
    assert d["books"][VENUE_BOOK]["pool_usdt"] == 10_000.0
    assert d["books"][SIM_BOOK]["unlimited"] is True


def test_v1_strategies_are_venue_backed_not_simulated(alloc):
    """The decisive one: those ledgers ARE backed by a real shared testnet balance.
    Reading them as `sim` would uncap a pool a live account still has to cover."""
    write_v1(alloc, 10_000.0, **{"spot-btc/bult": 2500.0, "spot-eth/etf": 2500.0})
    d = live_lib._read_allocations()
    assert all(s["book"] == VENUE_BOOK for s in d["strategies"].values())


def test_a_missing_file_still_yields_both_books(alloc):
    d = live_lib._read_allocations()
    assert set(d["books"]) == {VENUE_BOOK, SIM_BOOK}
    assert d["strategies"] == {}


def test_an_unreadable_file_does_not_take_the_harness_down(alloc):
    alloc.write_text("{ this is not json")
    d = live_lib._read_allocations()
    assert d["strategies"] == {}
    assert d["books"][VENUE_BOOK]["pool_usdt"] == 10_000.0


def test_migration_is_persisted_on_the_next_write(alloc):
    write_v1(alloc, 10_000.0, **{"spot-btc/bult": 2500.0})
    live_lib.allocate("sim-one", 1e6, book=SIM_BOOK)
    on_disk = json.loads(alloc.read_text())
    assert on_disk["version"] == 2
    assert on_disk["strategies"]["spot-btc/bult"]["book"] == VENUE_BOOK


# --------------------------------------------------------------------- the venue cap

def test_the_venue_pool_still_refuses_to_oversubscribe(alloc):
    write_v1(alloc, 10_000.0, a=2500.0, b=2500.0, c=2500.0)
    live_lib.allocate("d", 2500.0, book=VENUE_BOOK)          # exactly fills it
    with pytest.raises(ValueError, match="cannot allocate"):
        live_lib.allocate("e", 2500.0, book=VENUE_BOOK)


def test_reallocating_a_strategy_does_not_charge_it_twice(alloc):
    write_v1(alloc, 10_000.0, a=7500.0)
    live_lib.allocate("a", 10_000.0, book=VENUE_BOOK)        # same name, resized
    assert live_lib.allocations_summary()[VENUE_BOOK]["committed_usdt"] == 10_000.0


def test_the_error_names_the_way_out(alloc):
    write_v1(alloc, 10_000.0, a=10_000.0)
    with pytest.raises(ValueError, match=f"'{SIM_BOOK}'"):
        live_lib.allocate("b", 100.0, book=VENUE_BOOK)


# --------------------------------------------------------------------- the sim book

def test_the_sim_book_is_not_rationed(alloc):
    """The four-strategy ceiling was the single pool. Nothing is shared between two
    simulated books, so there is no scarcity left to ration."""
    for i in range(50):
        live_lib.allocate(f"sim/s{i}", 2500.0, book=SIM_BOOK)
    s = live_lib.allocations_summary()[SIM_BOOK]
    assert s["strategies"] == 50
    assert s["committed_usdt"] == 125_000.0
    assert s["free_usdt"] is None and s["unlimited"] is True


def test_sim_allocations_never_consume_the_venue_pool(alloc):
    write_v1(alloc, 10_000.0, a=2500.0)
    for i in range(20):
        live_lib.allocate(f"sim/s{i}", 5000.0, book=SIM_BOOK)
    venue = live_lib.allocations_summary()[VENUE_BOOK]
    assert venue["committed_usdt"] == 2500.0
    assert venue["free_usdt"] == 7500.0
    live_lib.allocate("b", 7500.0, book=VENUE_BOOK)          # still fits


def test_venue_allocations_are_not_charged_for_simulated_books(alloc):
    """The old accounting summed every strategy against one pool, so a simulated
    deployment ate the venue's headroom for no reason."""
    for i in range(4):
        live_lib.allocate(f"sim/s{i}", 2500.0, book=SIM_BOOK)
    live_lib.allocate("v", 10_000.0, book=VENUE_BOOK)
    assert live_lib.allocations_summary()[VENUE_BOOK]["free_usdt"] == 0.0


# --------------------------------------------------------------------- validation

@pytest.mark.parametrize("capital", [0.0, -1.0])
def test_a_non_positive_allocation_is_refused(alloc, capital):
    with pytest.raises(ValueError, match="positive"):
        live_lib.allocate("x", capital, book=SIM_BOOK)


def test_an_unknown_book_is_refused(alloc):
    with pytest.raises(ValueError, match="unknown book"):
        live_lib.allocate("x", 100.0, book="offshore")


def test_release_frees_only_its_own_book(alloc):
    live_lib.allocate("v", 5000.0, book=VENUE_BOOK)
    live_lib.allocate("s", 5000.0, book=SIM_BOOK)
    live_lib.release("v")
    assert live_lib.allocations_summary()[VENUE_BOOK]["strategies"] == 0
    assert live_lib.allocations_summary()[SIM_BOOK]["strategies"] == 1


def test_book_of_reports_where_a_strategy_draws_from(alloc):
    live_lib.allocate("v", 100.0, book=VENUE_BOOK)
    live_lib.allocate("s", 100.0, book=SIM_BOOK)
    assert live_lib.book_of("v") == VENUE_BOOK
    assert live_lib.book_of("s") == SIM_BOOK
