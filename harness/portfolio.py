"""
Multi-instrument (cross-sectional) paper execution.

`live_lib.LedgerBroker` holds ONE instrument against cash, which is all a long/flat
spot strategy ever needs.  Most of this desk's research is not that shape:
`sector-etf` trades the eleven SPDRs against each other, `fx-majors` trades crosses,
`crypto-alts` ranks a basket and `vol-complex` wants a short leg.  Those need one book
holding many positions at once, so that is what lives here.

    from live_lib import SimBroker            # one instrument
    from portfolio import SimPortfolioBroker  # a basket

The two are deliberately separate types rather than one class with a mode flag.  A
single-instrument book takes a scalar weight and a basket takes a mapping; folding
them together would mean every caller checking which one it had.

Conventions
-----------
* `weights` maps symbol -> target weight, each the fraction of THIS STRATEGY's equity
  to hold in that instrument.  Negative is short.  Cash is the remainder and is not
  named.
* Gross exposure is `sum(|w|)`, net is `sum(w)`.  `max_gross` caps leverage; a book
  that asks for more is scaled down proportionally, never truncated symbol by symbol,
  so the strategy's relative bets survive the cap.
* Everything is simulated.  There is no venue, no order book and no rejection -- see
  the honesty note on `live_lib.SimBroker`, which applies here in full.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Callable, Dict, Optional

from live_lib import (DEFAULT_CAPITAL, LedgerBroker, StrategyRunner, quote_source)

log = logging.getLogger("live")


class SimPortfolioBroker(LedgerBroker):
    """A simulated book holding many instruments at once, long and short.

    Positions are per symbol; cash is a single balance.  Equity is cash plus every
    position at its mark, which is the only definition that stays correct when a
    position is short (negative units, and the cash raised by the sale already sitting
    in the balance).

    Inherits `LedgerBroker` for the ledger file, mode reporting and quote plumbing, and
    replaces the trading half wholesale -- `set_target_weight` is a scalar interface and
    is refused here rather than silently applied to an arbitrary leg.
    """

    market = "portfolio"
    default_quotes = "yahoo-daily"

    def __init__(self, symbols, capital_usdt: float = DEFAULT_CAPITAL,
                 max_gross: float = 1.0, slippage_bps: float = 1.0,
                 fee_bps: float = 10.0, state_file: Optional[str] = None,
                 quote: str = "USD", quotes=None, allow_short: bool = True,
                 min_trade_usd: float = 1.0, open_universe: bool = False):
        self.symbols = list(dict.fromkeys(symbols))     # de-duplicated, order kept
        # An index book (the S&P 500) cannot name its legs up front: members join and
        # leave every month. `open_universe` lets weights name new symbols and makes a
        # ledger written under a different symbol list resume rather than restart.
        self.open_universe = bool(open_universe)
        if not self.symbols:
            raise ValueError("a portfolio needs at least one symbol")
        self.quote = quote
        self.capital_usdt = float(capital_usdt)
        self.max_gross = float(max_gross)
        # `_clamp_weights` scales only when `gross > max_gross > 0`, so a zero or
        # negative cap would silently wave every level of leverage through -- the
        # opposite of what setting it to zero looks like it should do.
        if not self.max_gross > 0:
            raise ValueError(f"max_gross must be positive, got {self.max_gross}")
        # Inherited scalar-weight helpers are unreachable here (`set_target_weight`
        # refuses), but leaving the attribute they read undefined would turn any future
        # call into an AttributeError instead of the explicit refusal.
        self.max_weight = float(max_gross)
        self.slippage_bps = float(slippage_bps)
        self.fee_bps = float(fee_bps)
        self.allow_short = bool(allow_short)
        self.min_trade_usd = float(min_trade_usd)
        self.quotes = quote_source(quotes or self.default_quotes)
        self.shadow = True
        self._positions: Dict[str, float] = {s: 0.0 for s in self.symbols}
        self._cash = float(capital_usdt)
        self.state_file = state_file
        # Named for the journal and logs; a basket has no single base instrument.
        self.symbol = "+".join(self.symbols)
        self.base = self.symbol
        self.step, self.min_qty, self.min_notional, self.qty_prec = 0.0, 0.0, 0.0, 10
        self._load_ledger()

    # ---- ledger persistence

    def _load_ledger(self):
        if not self.state_file or not os.path.exists(self.state_file):
            return
        try:
            with open(self.state_file) as fh:
                st = json.load(fh)
            saved = st.get("symbols")
            held = {s: float(q) for s, q in st.get("positions", {}).items() if float(q)}
            if saved is not None and list(saved) != self.symbols:
                if not self.open_universe:
                    log.warning("ledger %s is for %s, not %s -- starting a fresh book",
                                self.state_file, saved, self.symbols)
                    return
                # Keep every symbol the book still holds; a flat one that has left the
                # universe is dropped so the list does not grow forever.
                self._add_symbols(s for s in saved if s in held)
            self._positions = {s: held.get(s, 0.0) for s in self.symbols}
            self._cash = float(st["cash"])
            log.info("resumed portfolio ledger: cash=%.2f positions=%s",
                     self._cash, {k: v for k, v in self._positions.items() if v})
        except Exception as e:  # noqa: BLE001
            log.warning("could not read ledger %s: %s", self.state_file, e)

    def _save_ledger(self):
        if not self.state_file:
            return
        os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
        tmp = self.state_file + ".tmp"
        with open(tmp, "w") as fh:
            json.dump({"symbols": self.symbols, "positions": self._positions,
                       "cash": self._cash, "capital_usdt": self.capital_usdt,
                       "shadow": self.shadow, "mode": self.mode,
                       "updated": datetime.now(timezone.utc).isoformat()}, fh, indent=2)
        os.replace(tmp, self.state_file)

    def _add_symbols(self, symbols):
        for s in symbols:
            if s not in self._positions:
                self.symbols.append(s)
                self._positions[s] = 0.0
        self.symbol = self.base = "+".join(self.symbols)

    # ---- state

    def prices(self) -> Dict[str, float]:
        return {s: float(self.quotes.price(s)) for s in self.symbols}

    def mark_price(self) -> float:
        """Equity per unit of starting capital -- the book's own index.

        A basket has no single price.  Returning an index of the book itself keeps
        `equity()` and the runner's logging working without inventing a number that
        looks like an instrument quote.
        """
        return self.equity() / self.capital_usdt if self.capital_usdt else 0.0

    def bar_key(self) -> Optional[str]:
        """The bar every leg agrees on, or None if the market is continuous.

        Legs can disagree: one vendor series updates before another, or a symbol halts
        for a day.  Acting on a partial cross-section would rebalance the whole book
        against a stale leg, so the earliest bar any leg has printed is the bar the
        book is on -- it advances only once they all have.
        """
        keys = [self.quotes.bar_key(s) for s in self.symbols]
        if any(k is None for k in keys):
            return None
        return min(keys)

    def position(self, symbol: Optional[str] = None):
        if symbol is None:
            return dict(self._positions)
        return self._positions.get(symbol, 0.0)

    def equity(self, prices: Optional[Dict[str, float]] = None) -> float:
        px = prices if prices is not None else self.prices()
        return self._cash + sum(self._positions[s] * px[s] for s in self.symbols)

    def exposure(self, prices: Optional[Dict[str, float]] = None) -> dict:
        """Gross and net exposure as fractions of equity."""
        px = prices if prices is not None else self.prices()
        eq = self.equity(px)
        if not eq:
            return {"gross": 0.0, "net": 0.0, "weights": {}}
        w = {s: self._positions[s] * px[s] / eq for s in self.symbols}
        return {"gross": sum(abs(v) for v in w.values()),
                "net": sum(w.values()), "weights": w}

    def preflight(self) -> dict:
        out = {"venue": self.quotes.name, "market": self.market,
               "symbols": self.symbols, "shadow": self.shadow, "mode": self.mode,
               "capital_usdt": self.capital_usdt, "max_gross": self.max_gross,
               "allow_short": self.allow_short,
               "ledger": {"cash": self._cash, "positions": dict(self._positions)}}
        self._save_ledger()
        return out

    def reconcile(self) -> dict:
        return {"shadow": True, "mode": self.mode, "symbols": self.symbols,
                "ledger_cash": self._cash, "ledger_positions": dict(self._positions)}

    # ---- trading

    def set_target_weight(self, weight):
        raise TypeError(
            "SimPortfolioBroker holds a basket -- call set_target_weights({symbol: w}). "
            "Applying one scalar weight here would have to pick a leg arbitrarily.")

    def _clamp_weights(self, weights: Dict[str, float]) -> tuple:
        """Apply the short and leverage rules, and say what they changed.

        Scaled proportionally rather than clipped per symbol: clipping the largest leg
        would quietly change the strategy's relative bets, which is a different
        strategy wearing the same name.
        """
        notes = {}
        if self.open_universe:
            self._add_symbols(s for s in weights if s not in self._positions)
        w = {}
        for s in self.symbols:
            v = float(weights.get(s, 0.0) or 0.0)
            if v != v:
                raise ValueError(f"weight for {s} is NaN")
            w[s] = v
        unknown = sorted(set(weights) - set(self.symbols))
        if unknown:
            raise ValueError(f"weights name symbols this book does not hold: {unknown}")

        if not self.allow_short:
            shorted = sorted(s for s, v in w.items() if v < 0)
            if shorted:
                notes["clamped_shorts"] = shorted
                log.warning("allow_short is False; zeroing short legs %s -- the book "
                            "being traded is not the one the weights asked for", shorted)
                w = {s: max(0.0, v) for s, v in w.items()}

        gross = sum(abs(v) for v in w.values())
        if gross > self.max_gross > 0:
            scale = self.max_gross / gross
            notes["scaled_by"] = scale
            notes["requested_gross"] = gross
            w = {s: v * scale for s, v in w.items()}
        return w, notes

    def set_target_weights(self, weights: Dict[str, float]) -> dict:
        """Move the book to `weights`, selling before buying."""
        w, notes = self._clamp_weights(weights)
        px = self.prices()
        eq = self.equity(px)
        if eq <= 0:
            raise RuntimeError(f"equity is {eq:.2f}; the book is wiped out, refusing to trade")

        legs, fees, turnover = [], 0.0, 0.0
        orders = []
        for s in self.symbols:
            target = w[s] * eq / px[s]
            delta = target - self._positions[s]
            closing = w[s] == 0.0 and self._positions[s] != 0.0
            if not closing and abs(delta) * px[s] < self.min_trade_usd:
                continue
            if delta == 0.0:
                continue
            orders.append((s, delta, px[s]))

        # Sells first: a simulated book has no settlement, but funding buys from the
        # proceeds of the same rebalance is what a real one would have to do, and it
        # keeps cash from dipping negative on a pure rotation.
        orders.sort(key=lambda o: o[1])

        for s, delta, price in orders:
            side = "BUY" if delta > 0 else "SELL"
            qty = abs(delta)
            fill = price * (1 + (self.slippage_bps / 1e4) * (1 if side == "BUY" else -1))
            cost = qty * fill
            fee = cost * self.fee_bps / 1e4
            if side == "BUY":
                self._cash -= cost + fee
                self._positions[s] += qty
            else:
                self._cash += cost - fee
                self._positions[s] -= qty
            fees += fee
            turnover += cost
            legs.append({"symbol": s, "side": side, "qty": qty, "price": price,
                         "fill_price": fill, "fee": fee, "target_weight": w[s]})

        self._save_ledger()
        after = self.exposure(px)
        return {
            # `weight` is net exposure so the shared metrics keep working on a basket;
            # `price` is deliberately absent -- there is no instrument to buy and hold,
            # and inventing one would put a meaningless benchmark on the chart.
            "weight": after["net"], "gross": after["gross"], "net": after["net"],
            "equity": self.equity(px), "cash": self._cash,
            "positions": dict(self._positions), "target_weights": w,
            "weights": after["weights"], "legs": legs,
            "fee": fees, "turnover_usdt": turnover, "traded": bool(legs),
            "shadow": self.shadow, "mode": self.mode, "market": self.market,
            "capital_usdt": self.capital_usdt, **notes,
        }

    def flatten(self) -> dict:
        return self.set_target_weights({s: 0.0 for s in self.symbols})


class PortfolioRunner(StrategyRunner):
    """`StrategyRunner` for a basket: `compute_weights(now) -> {symbol: weight}`.

    Everything the single-instrument runner does -- bar-advance gating, journalling,
    restart-safe state, graceful shutdown -- is inherited unchanged.  Only the shape of
    what the strategy returns, and therefore of the order it turns into, differs.
    """

    def __init__(self, name: str, symbols, schedule: str,
                 compute_weights: Callable[[datetime], Dict[str, float]],
                 broker: Optional[SimPortfolioBroker] = None, **kw):
        symbols = list(dict.fromkeys(symbols))
        self.compute_weights = compute_weights
        broker = broker or SimPortfolioBroker(symbols)
        super().__init__(name=name, symbol="+".join(symbols), schedule=schedule,
                         compute_weight=self._unused, broker=broker, **kw)
        self.symbols = symbols

    @staticmethod
    def _unused(now):
        raise AssertionError("PortfolioRunner uses compute_weights, not compute_weight")

    def step_once(self, now: Optional[datetime] = None,
                  bar: Optional[str] = None) -> dict:
        now = now or datetime.now(timezone.utc)
        weights = self.compute_weights(now)
        if not isinstance(weights, dict):
            raise TypeError(f"compute_weights must return a dict, got {type(weights).__name__}")
        rep = self.broker.set_target_weights(weights)
        self._journal({"event": "rebalance", **self._journal_context(bar), **rep})
        if bar:
            self._last_bar = bar
        self._save_state(last_weight=rep["weight"], gross=rep["gross"], net=rep["net"],
                         equity=rep.get("equity"), positions=rep.get("positions"),
                         capital_usdt=self.broker.capital_usdt,
                         last_run=now.isoformat(), last_bar=self._last_bar,
                         waiting_for_new_bar=False)
        log.info("gross=%.3f net=%+.3f eq=%.2f legs=%d%s", rep["gross"], rep["net"],
                 rep.get("equity", 0), len(rep.get("legs", [])),
                 " SIM" if rep.get("mode") == "sim" else "")
        return rep

    def check(self) -> dict:
        """Dry run: report the weights and the trades they imply, place nothing."""
        now = datetime.now(timezone.utc)
        pf = self.broker.preflight()
        weights = self.compute_weights(now)
        px = self.broker.prices()
        eq = self.broker.equity(px)
        w, notes = self.broker._clamp_weights(weights)
        out = {"strategy": self.name, "symbols": self.symbols,
               "schedule": self.schedule, "now": now.isoformat(),
               "requested_weights": weights, "applied_weights": w,
               "gross": sum(abs(v) for v in w.values()),
               "net": sum(w.values()), "prices": px,
               "capital_usdt": self.broker.capital_usdt, "equity": eq,
               "positions": self.broker.position(),
               "target_qty": {s: (w[s] * eq / px[s]) for s in self.symbols},
               "bar": self.broker.bar_key(), "last_bar_traded": self._last_bar,
               "shadow": pf.get("shadow"), "mode": self.broker.mode,
               "venue": pf.get("venue"), **notes}
        print(json.dumps(out, indent=2, default=str))
        for s, v in w.items():
            if not -1.0 <= v <= 1.0:
                raise ValueError(f"weight {v} for {s} outside [-1, 1]")
        return out
