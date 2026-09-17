# Alpha spec — `crypto-alts / xs-momentum-neutral`

**Status:** Working (borderline against "Sharpe ≥ 1, winning in bear markets" — full-sample 1.22, OOS 1.05, all five BTC bear phases positive; the selection-free grid median is 1.03 full / 0.70 OOS, see §7).

**Mechanism:** regime-hedged betting-against-beta (BAB) on a point-in-time universe of the 20 most liquid altcoins. Long the lowest-beta tercile, short the highest-beta tercile. In a BTC bull regime the legs are sized beta-neutral (net long dollars); in a BTC bear regime they are sized dollar-neutral, which leaves the book with a naturally negative beta. The short high-beta leg is what earns in bear markets.

## Universe & bar

* Candidate list: `code/crypto-alts/shared/universe.py::ALTS` (61 yfinance `<COIN>-USD` tickers that were large-cap at some point since 2017; BTC and ETH are excluded from the cross-section, BTC is the beta/regime reference).
* Daily bars, yfinance calendar-day close (00:00 UTC stamp), `Volume` in USD. Use `research_lib.load_series` — every name lives in the flat `data/<TICKER>_d.parquet` cache.
* **Point-in-time membership** at close t: ≥120 valid closes, trailing 90-day median USD volume ≥ $5M, rank ≤ 20 by that median among eligible names. Past data only; 14 names held on average (min 12).
* Survivorship: yfinance has no delisted coins, so names that vanished entirely (LUNA, FTT, …) are missing — those would have been short-leg gains, so the bias runs against the strategy, not for it. Namesake-ticker traps handled in `universe.py` (ARB dropped, FIL/ONE/RENDER start dates masked).

## Signal (all at the close of day t)

```
ret_i     = pct_change(close_i)
beta_i,t  = EWMcov(ret_i, ret_BTC; halflife=60) / EWMvar(ret_BTC; halflife=60)
L_t       = equal-weight set of the lowest-beta 30% of members      (k = round(0.3 * n_members), ≥ 1)
S_t       = equal-weight set of the highest-beta 30% of members
beta_L    = Σ L_i * beta_i ;  beta_S = Σ S_i * beta_i
bull_t    = 1{ close_BTC,t > SMA(close_BTC, 50)_t }

bull:  a_t = beta_S / (beta_L + beta_S)          # portfolio beta = 0, a + b = 1
bear:  a_t = 0.5                                 # dollar-neutral, portfolio beta = (beta_L - beta_S)/2 < 0
w_raw,t   = a_t * L_t  -  (1 - a_t) * S_t        # gross exactly 1.0
w_t       = mean(w_raw over the last 14 days)    # overlapping 14-day tranches
```

**Weight w_t is applied to the return of day t+1** (rebalance on the close print of day t). `research_lib.backtest_xs` does exactly this.

* Gross exposure ≤ 1.0 (long ≈ 0.56, short ≈ 0.43 on average). Net exposure averages +0.13, ranges 0 (bear) to about +0.45 (bull). **Max leverage 1.0× gross.**
* Max single-name weight 0.12. Long/short: yes — the short leg is essential.
* Direction of the strategy is never net short in dollars; bear-market profits come from the negative beta of the dollar-neutral book.

## Costs and turnover

Modelled at **10 bp per side** on Σ|Δw|. Annual turnover ≈ 9× gross (i.e. the whole book turns over ~9 times a year); cost drag ≈ 1.8%/yr. Sharpe is 1.26 at 0 bp, 1.22 at 10 bp, 1.14 at 30 bp — costs are not the binding risk.

**Short-leg carry is.** Shorting alts means perps (funding) or margin borrow. The backtest charges none. Sensitivity, annualised drag on short notional (≈ 0.43 of NAV): 5% → Sharpe 1.13 / OOS 0.97; 10% → 1.04 / 0.88; 20% → 0.85 / 0.71. Budget ≤ 10%/yr on the short leg.

## Reference metrics (2018-03-08 → 2026-09-17, N = 3116, 10 bp/side)

| | Sharpe | Sortino | CAGR | Vol | MaxDD | Calmar | HitRate | t_NW | Turnover/y | AvgNet |
|---|---|---|---|---|---|---|---|---|---|---|
| Full | **1.22** | 1.80 | 29.9% | 23.9% | −30.4% | 0.99 | 52.8% | 3.15 | 9.1 | +0.13 |
| IS (≤ 2022-12-31) | 1.35 | 1.93 | 33.8% | 23.7% | −30.4% | 1.11 | 52.5% | 2.63 | | |
| OOS (≥ 2023-01-01) | **1.05** | 1.63 | 25.1% | 24.0% | −28.8% | 0.87 | 53.2% | 1.78 | | |
| BTC buy & hold (same window) | 0.63 | | 22% | 65% | −82% | | | | | |

Ex-post BTC bear phases (peak → trough of every >30% drawdown, frozen before evaluation; evaluation only, never a signal):

| Phase | BTC | Strategy Sharpe | Strategy CAGR | MaxDD |
|---|---|---|---|---|
| 2017-12-16 → 2018-12-15 | −83% | +0.25 | +3% | −17.5% |
| 2019-06-26 → 2020-03-12 | −62% | +0.26 | +3% | −26.4% |
| 2021-04-13 → 2021-07-20 | −53% | +4.32 | +320% ann. | −11.0% |
| 2021-11-08 → 2022-11-21 | −77% | +2.71 | +83% | −14.8% |
| 2025-10-06 → 2026-06-30 (OOS) | −53% | +0.78 | +18% | −17.3% |
| **All bear phases pooled** (1290 d) | | **+1.49** | +40% | −26.4% |
| Non-bear (1826 d) | | +1.02 | +24% | −30.6% |

Calendar years (Sharpe): 2018 −0.2, 2019 −0.5, 2020 +0.7, 2021 +3.0, 2022 +2.7, 2023 +0.5, 2024 +1.5, 2025 +2.4, 2026 YTD −0.7.

Beta to BTC: −0.04 overall (0.01 in bull, −0.08 in bear); corr to ETH −0.08.

Block bootstrap (30-day blocks, 2000 draws): mean 1.25, 5–95% [0.64, 1.82], P(Sharpe > 1) = 75%. Deflated Sharpe: 0.90 at 50 effective trials, 0.79 at 200, 0.63 at 1000 (1101 correlated configurations were evaluated in total).

## Robustness (selection-free numbers)

162-config grid over universe {15,20,25} × beta halflife {30,60,90} × tercile {0.25,0.3,0.4} × regime SMA {50,100} × hold {7,14,21}: full Sharpe min 0.68 / median 1.03 / max 1.38; OOS median 0.70; pooled-bear Sharpe > 0 in **100%** of configs, all five bear phases positive in 11%. Equal-weighting all 162 configs: 1.13 full / 1.41 IS / 0.78 OOS. Yearly-reselected walk-forward 2021-2026: 1.55 (2026 YTD −0.9). The spec's defaults were the "central" values fixed before the grid (universe 20 was the best size in an earlier screen, so it is not fully pre-registered).

## Assumed execution

* One decision per day at the 00:00 UTC yfinance daily close; execute both legs as a basket on spot (longs) and perps or margin (shorts) on a major venue.
* Slippage budget 10 bp per side on top; cost-insensitive to 30 bp.
* Position = NAV × w_t. Gross never exceeds 1.0.

## Kill switch (recommended)

* If trailing 90-day realised Sharpe < −1.0, halve gross until it recovers above 0.
* If the short leg's realised funding drag exceeds 15%/yr for a month, drop the strategy — the edge does not survive that carry.

## Files

* `../../past_research/crypto-alts/xs-momentum-neutral/2026-09-17_xs_momentum_neutral.md` — full research report.
* `../../code/crypto-alts/xs-momentum-neutral/strategy.py::alt_bab_weights` — the weight function, every parameter defaulted to this spec.
* `../../code/crypto-alts/xs-momentum-neutral/01–09_*.py` — screening and final scripts; `common.py` (splits, bear windows).
* `../../code/crypto-alts/shared/universe.py` — candidate list, panel loader, PIT universe.
* `01_equity.png`, `02_drawdown.png`, `03_rolling_sharpe.png`, `04_exposure.png`, `05_bear_and_yearly.png`, `backtest_series.parquet`.
