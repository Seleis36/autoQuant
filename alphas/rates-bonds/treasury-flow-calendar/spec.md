# Alpha spec — `treasury-flow-calendar`

Report: `past_research/rates-bonds/treasury-flow-calendar/2026-09-14_treasury_flow_calendar.md`

## Instrument & mechanics

| Field | Value |
|---|---|
| Instrument | **TLT** (iShares 20+ Year Treasury Bond ETF), single name |
| Book | simulated (`SimBroker("TLT", allow_short=True)`) |
| Direction | long / short / flat; netted weight in {−1, 0, +1} |
| Max gross exposure | **1.0** (no leverage validated beyond this; Sharpe is leverage-invariant, so a higher cap is a sizing choice, not a research one) |
| Rebalance | once daily at the NYSE close; weight set at close *t* is held from close *t* to close *t+1* |
| Bar convention | yfinance daily bars, adjusted close, tz-naive index (calendar date of the US session) |
| Cost assumed | **2 bp per side** (TLT quoted spread ≈ 1 bp). Do not run it at 10 bp: Sharpe 0.60 there |
| Average exposure | 32 % of days non-zero (19 % long, 13 % short) |
| Turnover | ≈ 66 one-way weight changes of size 1 per year |

## Signal (lookahead-safe)

Let `cal` be the NYSE trading calendar (observed bars, extended forward with NYSE holidays),
and `next(t)` the trading day after `t`.

```
month_end_t   = 1 if next(t) is one of the last 3 trading days of its month          else 0
fomc_t        = 1 if next(t) is an FOMC statement day or the trading day before one   else 0
pre_auction_t = 1 if next(t) is one of the 2 trading days before a 10y or 20y auction else 0
                (reopenings count; dates from TreasuryDirect, announced ≥ 1 week ahead)

target_weight_t = clip(month_end_t + fomc_t − pre_auction_t, −1, +1)
```

Parameters: `month_end_n=3`, `fomc_before=1`, `auction_before=2`, `tenors=("10y","20y")`, `cap=1.0`.

## Reference performance (TLT, 2 bp/side, strategy.py weights)

| Window | Sharpe | CAGR | Vol | MaxDD | t_NW |
|---|---|---|---|---|---|
| FULL 2010-01 → 2026-09 | **1.26** | 10.4 % | 8.1 % | −11.5 % | 5.4 |
| IS 2010 → 2017 | 0.88 | 6.4 % | 7.4 % | −11.5 % | 2.7 |
| OOS 2018 → 2026-09 | 1.57 | 14.2 % | 8.7 % | −6.9 % | 4.8 |
| Holdout ETF 2002-07 → 2009 | 0.63 | 3.9 % | 6.4 % | −13.0 % | 1.7 |
| Holdout synthetic 30y / 10y, 1990 → 2009 | 0.89 / 0.87 | 5.5 % / 3.3 % | | | 3.9 |
| Walk-forward leg selection, 2010 → 2026 | 0.75 – 0.88 | 7 – 10 % | | −15 to −22 % | |
| TLT buy & hold 2010 → 2026 | 0.23 | 2.3 % | 14.9 % | −48.4 % | |

Per leg, 2010→2026: month-end 0.78 · FOMC 0.63 · pre-auction 0.72. Month-end + FOMC alone: 1.00
full, 0.96–0.99 on 1990–2009. The pre-auction leg is a post-2010 regime feature (≈0 before
2010) and is the first thing to break if auction sizes shrink.

Block-bootstrap 5–95 % Sharpe [0.91, 1.63]; P(Sharpe > 1) = 0.89. Expected live Sharpe 0.9–1.2.

## Deployment interface

```python
import sys; sys.path.insert(0, "code/rates-bonds/treasury-flow-calendar")
from strategy import target_weight

# close: pd.Series of TLT daily closes, tz-naive DatetimeIndex (only the index is used)
w = target_weight(close)          # values in {-1, 0, +1}; w[t] held from close_t to close_{t+1}
```

Calendars default to the committed snapshots in `code/rates-bonds/treasury-flow-calendar/calendar_snapshots/`:

* `fomc.csv` covers every scheduled meeting through **2027-12-08**;
* `auctions.csv` covers all auctions to date plus those announced by TreasuryDirect at snapshot
  time (2026-09-14). **Refresh monthly** with `python code/rates-bonds/treasury-flow-calendar/calendars.py`
  (it re-pulls history and `securities/upcoming`), or pass `auction_dates=` explicitly. With a
  stale auction file the short leg silently goes flat; the two long legs are unaffected.

The `weights_and_returns.csv` next to this file is the bar-for-bar reference for the
runner's `--check`: weights match the research builder on every bar except the final four of
the sample, where the research builder cannot see the next auction and `strategy.py` can.

## Figures

`01_equity.png` growth of $1 vs TLT · `02_drawdown.png` · `03_yearly_sharpe.png` ·
`04_leg_attribution.png` cumulative net return per leg · `05_weight_sample.png` weight path Jan–Jun 2025.
