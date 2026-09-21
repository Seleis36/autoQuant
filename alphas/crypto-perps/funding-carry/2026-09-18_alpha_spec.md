# Alpha spec — `funding-carry` (crypto-perps)

**Status: Working** against the brief "Sharpe ≥ 3" under the repo's convention (daily returns,
annualised √365). See the horizon caveat below before reading the headline number.

## Mechanism

Cash-and-carry on Binance. For each coin, hold **+1 unit of spot** and **−1 unit of the USD-M
perpetual** of the same coin. The position is delta-neutral to the coin price; its P&L is the
funding paid by perp longs to perp shorts every 8 hours (00:00 / 08:00 / 16:00 UTC), minus the
mark-to-market of the perp-minus-spot basis. Funding on BTC and ETH has been positive 86 % of the
time since 2020 (longs pay shorts), averaging 11.7 % / 13.9 % per year on notional.

There is **no directional signal**. Every timing rule tested (trailing-funding thresholds,
hysteresis, basis sign) lost to the 20 bp cost of a switch relative to ~3 bp/day of funding.

## Instruments, direction, sizing

| Item | Value |
|---|---|
| Instruments | `BTCUSDT` spot (long) + `BTCUSDT` USD-M perp (short); `ETHUSDT` spot (long) + `ETHUSDT` USD-M perp (short) |
| Direction | long spot / short perp, one unit each, per coin. Never net directional. |
| Coin weights | equal: each coin gets half the capital |
| Perp leverage | **L = 1**: perp margin equals perp notional. Capital per coin = spot notional + perp margin = 2 × one-leg notional. `capital_factor = 1/(1+1/L) = 0.5` |
| Exposure scaler | per coin, `w = min(1, 0.02 / σ)` where σ = EWM std (halflife 30 days = 720 hourly bars) of the hourly hedged P&L on one-leg notional, annualised √8760. Re-evaluated **only at funding stamps** (00/08/16 UTC), held in between. |
| Target weight of total capital | spot leg `+0.5 × w / 2` per coin, perp leg `−0.5 × w / 2` per coin (max 0.25 each) |
| Rebalance | at 00/08/16 UTC; realised turnover 0.64 units of capital per year |
| Bars / timezone | Binance hourly klines, UTC, bar-open stamps; decision at the close of hour t, applied from t+1 |
| Cost assumed | 15 bp fees (10 spot taker + 5 perp taker) + 5 bp slippage = **20 bp per unit of notional switched, both legs together** |
| Margin management | BTC/ETH spot must serve as collateral for the perp short (Binance Multi-Assets mode, or coin-margined perp), otherwise a +100 % rally between margin top-ups would liquidate the short at L = 1. Largest intra-month rally in-sample: +79 % (Feb 2021). |

`code/crypto-perps/funding-carry/strategy.py :: target_weights(spot, perp, funding)` returns the
per-instrument weight frame with every parameter defaulted to the values above.

## Headline numbers (return on capital, 2020-01 → 2026-08, 20 bp/switch)

| | Full | IS 2020-22 | OOS 2023-26 |
|---|---|---|---|
| Sharpe (daily) | **10.18** | 8.99 | 12.69 |
| Sharpe (weekly) | 5.74 | 5.39 | 6.34 |
| Sharpe (monthly) | **3.53** | 3.58 | 3.50 |
| Sharpe (quarterly) | 2.54 | 2.68 | 2.36 |
| CAGR | 3.88 % | 4.28 % | 3.55 % |
| Vol | 0.37 % | 0.47 % | 0.28 % |
| Max drawdown | −0.35 % | −0.35 % | −0.26 % |

Rolling 12-month daily Sharpe: min 2.54, 5th pct 3.57, median 12.6. Block-bootstrap daily Sharpe
5–95 %: 8.95–11.69; monthly-return bootstrap 5–95 %: 3.09–4.24, P(monthly Sharpe > 3) = 0.97.
Beta to BTC −0.001. Average one-leg exposure 0.41 of capital (max 0.5). Cost at 80 bp/switch:
Sharpe 7.96, CAGR 3.48 %.

Same construction always-on (no vol scaler): Sharpe 8.65 daily / 4.33 weekly / 2.47 monthly,
CAGR 6.6 % on capital, MaxDD −0.74 %. The scaler halves the 2020-21 exposure, where both funding
and basis noise were extreme, and is what lifts the monthly figure over 3.

## Read this before trusting the Sharpe

1. **The Sharpe is horizon-dependent.** Daily returns are autocorrelated (ρ₁ = 0.44) because
   funding levels persist for weeks. Daily-annualised Sharpe 10.2 falls to 5.7 weekly, 3.5
   monthly, 2.5 quarterly. The strategy has *no* losing quarter; the variance at long horizons is
   the variance of *how much* it earns, not whether. Judge it on the monthly figure.
2. **Absolute return is small: ~4 % per year on capital** at L = 1 (~7 % always-on). The
   Sharpe is high because the vol is 0.4 %. It is a yield, not an alpha, and 2025-26 funding has
   compressed to ~5 % / ~3 % on notional.
3. **Unmodelled risks** are exactly the ones that dominate this trade in practice: exchange
   counterparty risk (spot and margin on Binance), liquidation if margin is not collateralised by
   the spot leg, auto-deleveraging, funding-rate cap/floor changes, and a bar-close fill
   assumption for both legs. The −2 % perp discount of 2020-03-12 is in-sample and cost 1.2 % on
   notional that day.
4. **Not paper-tradeable in the current harness.** Neither the venue book (long/flat spot only)
   nor the simulated book (price-only fills, no funding cash-flows) pays or charges funding, so a
   live paper run would show only the basis leg. Deploying it needs a funding-aware ledger.

## Figures

- `equity.png` — growth of 1, spec vs BTC and ETH sleeves
- `drawdown_exposure.png` — drawdown and the vol-scaled exposure
- `yearly.png` — Sharpe and return by calendar year
- `horizon.png` — Sharpe vs aggregation horizon
- `decomposition.png` — BTC monthly funding vs basis mark-to-market (always-on, one-leg notional)
