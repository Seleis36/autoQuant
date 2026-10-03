# Alpha spec — options-expiry-drift (pre-settlement short on spot ETH)

**Status:** Working (borderline) · **Date:** 2026-10-03
**Report:** `past_research/spot-eth/options-expiry-drift/2026-10-03_options_expiry_drift.md`
**Signal:** `code/spot-eth/options-expiry-drift/strategy.py :: target_weight(close)`

## Rule

Short ETH, one times equity, from **Friday 00:00 UTC to Friday 08:00 UTC on the last Friday of
each calendar month** (the Deribit monthly / quarterly option expiry, settled at 08:00 UTC).
Flat at all other times. Twelve round trips a year.

| | |
|---|---|
| Instrument | ETH/USDT, Binance spot price (`ETHUSDT`) |
| Book | **Simulated** (`SimBroker`, `quotes="binance-public"`) — the rule is short-only and the spot testnet is long/flat |
| Direction | short / flat |
| Maximum leverage | 1.0× gross (weight −1.0 in the window, 0 otherwise) |
| Sizing | fixed −1.0; no volatility scaling, no signal strength |
| Rebalance | hourly schedule; trades only at Fri 00:00 and Fri 08:00 UTC of the expiry Friday |
| Bars / timezone | hourly bars indexed by bar-open time, UTC, tz-naive; `w[t]` is held over the bar stamped t+1h |
| Parameters | `entry_hour=0`, `exit_hour=8`, `size=-1.0`, `which="last"` — none fitted |
| Cost assumed | 10 bp per side |
| Data needed | the hourly index only (the calendar is a function of the timestamp) |

Runner note: at Fri 00:00 the last closed bar is Thu 23:00 and `target_weight(...).iloc[-1]` is
−1; at Fri 08:00 the last closed bar is Fri 07:00 and it is 0. The last-Friday test looks at the
whole calendar month, not at the last date in the data, so it gives the same answer mid-month
(truncation test: max |Δw| = 0 at four cut dates, two of them inside an event).

## Numbers (10 bp/side, 2020-01 → 2026-10)

| | full | IS 2020–23 | OOS 2024+ |
|---|---|---|---|
| Sharpe | 0.71 | 0.58 | 0.88 |
| Net per event | +39 bp | +28 bp | +54 bp |
| Events | 81 | 48 | 33 |

- CAGR 4.5%, volatility 6.5%, MaxDD −6.0%.
- Turnover 24×/yr; time in the market 1.1%; average exposure −0.011.
- Bootstrap 5–95% interval of the Sharpe: [0.16, 1.27].
- Costs 0 / 5 / 10 / 20 / 30 bp per side: 1.05 / 0.89 / 0.71 / 0.35 / −0.03.
- Correlation with the live `eth-trend-filter`: −0.06.

## Why it should work

Option open interest is concentrated in the month-end expiry, and the settlement price is a
30-minute TWAP ending at 08:00 UTC. In the hours before it ETH loses 61 bp on average (median
49 bp), against +10 to +25 bp on other Fridays and +27 bp on last Fridays before ETH options had
open interest (2017–19). BTC shows the same move at the same clock time.

## What would make it stop working

- The effect is small against its cost: a round trip above ~40 bp removes it.
- Three events supply half of the Sharpe (0.36 without them).
- The quarterly expiries — the largest — show no dip. If the mechanism were purely a hedging
  flow they should show the most.
- A change in Deribit's settlement time or method changes the window.

Review trigger: eight consecutive losing events (the backtest's longest losing run is six), or a
cumulative net loss of 6% (the backtest's maximum drawdown).

## Figures

- `fig1_path.png` — mean cumulative return from T−24h to T+8h: month-end expiry, other Fridays, Tuesdays
- `fig2_equity.png` — net equity of the sleeve
- `fig3_yearly.png` — net return by calendar year
