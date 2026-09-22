# rates-carry-trend — carry and trend across the Treasury curve

**Date:** 2026-09-22 · **Asset class:** rates-bonds · **Status:** **Failed**

**Brief:** "1+ sharpe strat, CAGR > 10% hedging against current crypto strats."

Second idea of the session, opened after `credit-spread-trend` established that credit
cannot be timed at daily frequency and that duration no longer hedges risk assets. This
one drops the hedging angle as the *primary* driver and goes after the two best-documented
rates risk premia — carry (Koijen, Moskowitz, Pedersen & Vrugt 2018) and time-series
momentum (Moskowitz, Ooi & Pedersen 2012) — on the grounds that a genuinely 1.0-Sharpe
rates sleeve would be worth having even as a pure diversifier.

## 1. Method

**Synthetic constant-maturity returns.** SHY/IEF/TLT only have deep history from ~2010,
which is not enough sample to design on and still have an honest test. CMT par yields from
FRED (`DGS2/5/10/20/30`, `DGS3MO`) go back to 1981 and are never revised, so
`curve_lib.py` turns them into daily total returns of a constant-maturity par bond:

```
r_t = y_{t-1}/252  −  D(y_{t-1}, n)·dy  +  ½·C(y_{t-1}, n)·dy²
```

with `D`, `C` the closed-form modified duration and convexity of a par bond with
semiannual coupons. Excess returns net the 3m bill accrual. Sanity check, 1990+: buy-and-
hold excess Sharpe is 0.26 / 0.25 / 0.25 / 0.23 at 2y / 5y / 10y / 30y — the flat term
structure of Sharpe ratios that the literature reports, so the synthesis is not distorting.

**Split, fixed before the first backtest and never moved:**

* **IS 1990-01-01 → 2009-12-31** — synthetic only. Every parameter chosen here.
* **OOS 2010-01-01 → 2026-09-21** — the ETF era, and the crypto-book overlap.

This is a stronger split than a date cut: the instruments the strategy actually trades
(SHY 2002, IEF 2002, TLT 2002, all thin before 2010) barely existed in the design window,
so the test is out-of-sample in instrument as well as in period.

**Signals**, per maturity n ∈ {2, 10, 30} (mapped to SHY / IEF / TLT):

* *carry* = (y_n − y_3m) + D_n·(y_n − y_roll)/(n − n_roll), the yield pickup over cash plus
  one-year roll-down, rolling down to the next quoted CMT tenor.
* *trend* = mean of sign(index / SMA_L − 1) for L ∈ {63, 126, 252}.

**Sizing:** each leg inverse-vol scaled to 5 % vol on a 252d window, book vol-targeted to
10 % on trailing realised vol, gross capped at 6×, 21-day signal smoothing, 5 % no-trade
band. Cost 2 bp per side.

## 2. What was tried (IS 1990-2009)

### 2a. First pass — `backtest_is.py`, `backtest_is_output.txt`

| Signal | CAGR | Vol | Sharpe | Turnover/yr |
|---|---|---|---|---|
| carry as trailing 5y z-score | −6.2 % | 11.7 % | **−0.49** | 62× |
| trend only | 3.5 % | 11.2 % | 0.36 | 101× |
| carry-z + trend | −0.0 % | 10.8 % | 0.05 | 116× |

Two defects, both real: (i) z-scoring carry **inverts** the premium — bond carry is a
*level* effect (steep curve → long duration), not a deviation from its own recent mean,
and the z-score goes short exactly when a steep curve is steepest; (ii) daily re-scaling
of a vol-targeted book churns 60-116× notional a year, which is 120-230 bp/yr of cost.

### 2b. Fixed — `backtest_is2.py`, `backtest_is2_output.txt`

Raw carry level, 21-day smoothing, 5 % band:

| Signal | CAGR | Vol | Sharpe | MaxDD | Turnover/yr |
|---|---|---|---|---|---|
| carry level | 2.7 % | 11.4 % | 0.29 | −36.1 % | 12× |
| carry sign | 2.7 % | 10.9 % | 0.30 | −34.9 % | 10× |
| trend | 4.9 % | 10.8 % | 0.50 | −21.5 % | 23× |
| **carry level + trend** | **6.5 %** | **11.4 %** | **0.61** | **−19.7 %** | 19× |
| carry sign + trend | 5.0 % | 11.1 % | 0.49 | −26.5 % | 22× |

IS sleeve correlation carry-vs-trend = 0.29, so the blend does add something. Smoothing
sensitivity is monotone and well-behaved (Sharpe 0.39 → 0.53 as smoothing goes 1 → 21
days, turnover 71× → 14×); 21 days was taken from that table.

**The decay is already visible in-sample**, by 5-year block:

| | 1990-94 | 1995-99 | 2000-04 | 2005-09 |
|---|---|---|---|---|
| carry sign | 0.30 | 0.68 | 0.18 | 0.03 |
| trend | 1.12 | 0.78 | 0.25 | 0.18 |
| blend | 0.74 | 0.98 | 0.23 | 0.13 |

Half the in-sample Sharpe comes from 1990-1999. That is a warning, not a result.

### 2c. Curve trades — `backtest_is3.py`, `backtest_is3_output.txt`

Duration-neutral steepeners (2s10s, 2s5s, 5s30s, 10s30s, DV01-matched) on slope carry,
slope z-score, spread trend and blends — 6 configurations.

**Every single one is negative in-sample** (Sharpe −0.02 to −0.21), and buy-and-hold of
each steepener is negative too (−0.13 to −0.34). The cost structure is the killer: a
DV01-matched 2s10s is 5.2 units of notional per unit of spread exposure, so 2 bp per side
becomes 10 bp per side of spread. Abandoned.

## 3. Out of sample — `backtest_oos.py`, `backtest_oos_output.txt`

One configuration, frozen from §2b before any OOS number was computed: carry-level +
trend, 21d smoothing, 5 % band, 10 % vol target, 6× gross cap, 2 bp/side.

**Synthetic implementation**

| Window | CAGR | Vol | Sharpe | MaxDD | t(NW) | Turnover/yr | Avg gross |
|---|---|---|---|---|---|---|---|
| IS 1990-2009 | 6.3 % | 11.4 % | 0.59 | −22.2 % | 2.28 | 13× | 2.29 |
| **OOS 2010-2026** | **3.8 %** | 9.7 % | **0.44** | −20.0 % | 1.82 | 24× | 2.97 |
| FULL 1990-2026 | 5.0 % | 10.6 % | 0.52 | −22.2 % | 2.92 | 18× | 2.64 |

**ETF implementation** (SHY/IEF/TLT notional, excess of the 3m bill) — correlation with
the synthetic version over 2010-2026 is 0.94, so the mapping is faithful:

| Window | CAGR | Vol | Sharpe | MaxDD | Turnover/yr | Avg gross | Max gross |
|---|---|---|---|---|---|---|---|
| **2010-2026 (all OOS)** | **3.1 %** | **9.5 %** | **0.37** | **−21.4 %** | 25× | 2.97 | 6.08 |
| 2010-2017 | 3.3 % | 9.1 % | 0.40 | −12.8 % | 30× | 3.28 | 6.08 |
| 2018-2026 | 3.0 % | 9.8 % | 0.35 | −21.4 % | 20× | 2.69 | 6.06 |

Per-year OOS Sharpe: 0.21, 1.77, 0.12, −1.77, 1.24, −0.35, 0.29, 0.04, −0.73, 1.54, 1.29,
−0.50, 0.71, 0.22, 0.11, −0.94, −0.33. Seven of seventeen years are negative; the strategy
is carried by 2011, 2019, 2020.

**Against the criteria: OOS Sharpe 0.37 vs the 1.0 required, CAGR 3.1 % vs the 10 %
required.** Reaching 10 % CAGR from here needs 3.2× more leverage — average gross ~9.5×
across three bond ETFs, 30 % vol, −60 % drawdown — and the Sharpe would still be 0.37.

## 4. The hedging question

The one thing that did work is the diversification, and it is worth recording precisely
because it is not enough on its own:

| | ETF carry+trend | synthetic |
|---|---|---|
| corr with crypto book, all days | **−0.004** | −0.004 |
| strategy return on the book's worst decile of days | **+4.7 bp** | +5.8 bp |
| strategy return on all other days | +1.1 bp | +1.3 bp |
| strategy ann. return inside the book's drawdowns | +2.3 % | +3.6 % |

It earns *more* on the crypto book's worst days than on ordinary days — a genuine, if
mild, hedge, and better than `treasury-flow-calendar`'s ≈0 correlation. Blending it in:

| Mix | Sharpe | Ann. return | Max DD |
|---|---|---|---|
| 100 % crypto book | 1.72 | 35.1 % | −27.7 % |
| 75 % book + 25 % rates | **1.78** | 27.6 % | −21.8 % |
| 50 % book + 50 % rates | 1.71 | 20.2 % | −15.7 % |

A 25 % sleeve lifts book Sharpe 1.72 → 1.78 and cuts the drawdown by a fifth. That is a
real but small benefit bought with ~3× gross leverage in bond ETFs, and it does not make
the sleeve meet a 1.0-Sharpe / 10 %-CAGR standard on its own terms. **Not deployed.**

## 5. Verdict

Failed. ~29 configurations in this short name, ~111 across the session. The classic rates
risk premia are alive but small: OOS Sharpe 0.37-0.44 on a well-specified, honestly costed,
36-year-validated carry+trend book. That is roughly what the published literature reports
after costs, so the result is not a bug — it is the asset class. Nothing here reaches the
brief's bar, and no amount of leverage changes a Sharpe ratio.

Nothing deployable. No alpha spec, no `strategy.py`.

## 6. What a future researcher should take from this

1. **The infrastructure is reusable and it is the valuable part of this session.**
   `curve_lib.py` gives duration/convexity-correct synthetic constant-maturity Treasury
   returns from 1981 for any tenor — that is a 36-year design sample for any rates idea,
   and it maps to SHY/IEF/TLT at 0.94 correlation. `fetch_fred_daily.py` caches the daily
   never-revised FRED series to `data/FRED_<ID>_d.parquet`.
2. **Do not z-score bond carry.** It inverts the premium (IS Sharpe −0.49 vs +0.29 for the
   raw level). Carry is a level signal.
3. **Vol-targeted daily rebalancing of a rates book costs 120-230 bp/yr** before any
   signal churn. 21-day smoothing plus a 5 % no-trade band takes turnover from 71× to 14×
   and *raises* Sharpe. Do this first, not last.
4. **Curve trades are not viable through ETFs.** DV01-matching a 2s10s costs 5.2 units of
   notional per unit of exposure, which is ~10 bp per side of spread. Every variant was
   negative in-sample.
5. **FRED's ICE BofA OAS series (`BAMLH0A0HYM2`, `BAMLC0A0CM`) are truncated to the last
   ~3 years** by licensing, even with explicit `cosd`. There is no long daily OAS history
   from that source — use HYG/LQD ETFs and accept the 2007 start.

## 7. Files

* `code/rates-bonds/rates-carry-trend/fetch_fred_daily.py` — daily never-revised FRED cache.
* `curve_lib.py` — synthetic constant-maturity Treasury returns, carry, roll-down.
* `backtest_is.py` / `backtest_is2.py` / `backtest_is3.py` + `*_output.txt` — IS design.
* `backtest_oos.py` / `backtest_oos_output.txt` — the one frozen config, OOS + ETF + hedge.
* `backtest_series.parquet`, `weights_etf.parquet` — the OOS return and weight series.
