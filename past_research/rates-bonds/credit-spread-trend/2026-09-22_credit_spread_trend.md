# credit-spread-trend — timing the HY credit risk premium as a crypto hedge

**Date:** 2026-09-22 · **Asset class:** rates-bonds · **Status:** **Failed**

**Brief:** "1+ sharpe strat, CAGR > 10% hedging against current crypto strats."

## 1. Why this idea

The brief asks for a *hedge*, so the first job was to find which part of the rates
complex actually co-moves with the live crypto book. I built a proxy for that book as the
equal-weight daily net returns of the four deployed crypto alphas that publish a daily
backtest series — `spot-eth/eth-trend-filter`, `crypto-alts/xs-momentum-neutral`,
`spot-btc/coinbase-premium`, `spot-btc/weekday-trend` (`spot-btc/bult` is hourly and
publishes none). Over 2018-03 → 2026-09 that proxy runs Sharpe 1.80, CAGR 37.8 %,
vol 18.8 %, max DD −24.6 %.

Conditioning daily rates-ETF returns on the book's worst decile of days gives the whole
answer:

| | book worst decile | all other days |
|---|---|---|
| SPY | −30.0 bp | +10.1 bp |
| HYG | −10.6 bp | +3.3 bp |
| LQD | −7.7 bp | +2.1 bp |
| TIP | −1.9 bp | +1.5 bp |
| **TLT** | **−0.9 bp** | −0.0 bp |
| **IEF** | **−0.0 bp** | +0.6 bp |
| SHY | +1.0 bp | +0.8 bp |

**Duration is not a crypto hedge post-2018 — credit is the only axis that moves.** A
strategy that is short credit risk in stress is short exactly when the crypto book bleeds.
So: trade the HY credit risk premium, duration-stripped, and time it.

## 2. The traded object

Long 1 HYG / short 0.47 IEF. The hedge ratio is the ratio of published effective
durations (HYG ≈ 3.4y, IEF ≈ 7.3y), fixed a priori, not fitted. That strips the ~3.4y of
duration inside HYG and leaves a clean credit-risk premium.

Buy-and-hold of that object, 252-day annualisation:

| Window | CAGR | Vol | Sharpe | MaxDD | Skew |
|---|---|---|---|---|---|
| PRE 2007-04→2009-12 | −0.9 % | 21.9 % | 0.07 | −39.4 % | +0.69 |
| IS 2010→2017 | 4.0 % | 9.0 % | 0.48 | −17.9 % | −0.57 |
| OOS 2018→2026 | 3.7 % | 8.7 % | 0.47 | −25.0 % | −0.31 |

Sharpe ≈ 0.47 unconditionally, and it is a negatively-skewed carry asset. To reach
CAGR 10 % on buy-and-hold alone you need ~2.6× leverage and inherit a −65 % drawdown.
Timing has to do real work.

**Split, fixed before the first backtest and never moved:** PRE 2007-04-11→2009-12-31
(HYG inception, untouched holdout), IS 2010-01-01→2017-12-31, OOS 2018-01-01→2026-09-21.
Cost 3 bp per side charged on gross turnover of *both* legs (1.47× notional per unit).

## 3. What was tried, and what each did (IS 2010-2017)

### 3a. Trend on the credit premium — `explore.py`, `explore_output.txt`

24 configurations: momentum of the excess return at 5/10/20/40/60/90/120/180/252 days,
long/short and long/flat, plus price-vs-MA on the cumulative index at 7 lookbacks.

| Family | best IS Sharpe | vs buy-and-hold 0.48 |
|---|---|---|
| long/short sign of L-day mean | **0.18** (L=120) | far worse |
| long/flat | **0.50** (L=180) | a wash, at 6.4×/yr turnover |
| price vs MA of the index | **0.19** (L=20) | far worse |

**Trend does not time credit.** Credit is a carry asset whose drawdowns are fast and
V-shaped (2011, 2015-16 energy, 2018-12, 2020-03); a trend follower sells the bottom and
buys back higher. Every long/short variant was worse than doing nothing.

### 3b. Sleeve screen — `screen.py`, `screen_output.txt`

32 configurations across four families: credit carry with inverse-vol sizing (3), credit
carry gated by the index's own drawdown (9), gated by VIX vs its MA (2) and by SPY
momentum (3); TLT duration trend at 7 lookbacks plus a multi-horizon blend; curve slope
conditioning of IEF−SHY (4); breakeven trend TIP−IEF (3).

Nothing in the credit or duration families cleared IS Sharpe 0.43. The only entries above
0.6 were `C_slope*` — long IEF vs SHY whenever the 10y−3m slope exceeds a threshold —
and those are an artefact: 2010-2017 contains no inversion, so the signal is a constant
and the "strategy" is buy-and-hold curve carry. Its short side is untested in-sample,
which is precisely why it is not evidence.

### 3c. The explicitly risk-off family — `riskoff_screen.py`, `riskoff_output.txt`

26 configurations, built to pay in risk-off rather than to earn carry: long TLT after a
VIX spike (3 thresholds × 4 holding periods), long TLT after a ≥1.5σ SPY down day (4
holding periods), the next-day flight-to-quality reversal, short HY on credit-vol spikes
(3), credit carry gated off on credit-vol spikes (3), HYG-vs-LQD relative momentum (3).

| | IS 2010-2017 | OOS 2018-2026 |
|---|---|---|
| `vixspike10_h10` (long TLT 10d after VIX >10 % over its 20d MA) | **Sharpe 0.54** | **−0.11** |
| `vixspike10_h3` | 0.44 | 0.04 |
| `vixspike10_h5` | 0.36 | −0.09 |
| `vixspike30_h10` | 0.36 | −0.10 |
| `vixspike20_h10` | 0.27 | −0.26 |

This is the single most informative table in the study. **Buying duration on a vol spike
worked through 2017 and stopped working entirely afterwards** — the same regime break
that flipped the stock-bond correlation positive in 2022. The IS-best configuration has
an OOS Sharpe of −0.11 and loses 3.4 % annualised *inside* the crypto book's drawdowns:
it is not merely unprofitable, it fails at the one job it was built for.

Short-credit-on-vol-spike (`credit_volgate*`) is between −0.35 and −0.52 IS: the spike
arrives after the spread has already widened, so it shorts the bottom.

HY-vs-IG relative momentum is the worst thing in the study (IS −0.47 to −1.13), killed by
94-148×/yr turnover on a 2-leg spread.

## 4. Verdict

No configuration in ~82 tried reaches IS Sharpe 0.6, and the ones that clear 0.5 in-sample
are flat-to-negative out of sample. The credit premium is real (Sharpe 0.47 unconditional,
stable across IS and OOS) but it is **untimeable at daily frequency with these signals**,
and the risk-off duration hedge that used to exist has been gone since 2018.

Nothing here is deployable. No alpha spec, no `strategy.py`.

## 5. What a future researcher should take from this

1. **Post-2018, TLT/IEF do not hedge crypto.** −0.9 bp and −0.0 bp on the book's worst
   decile. Do not build a rates crisis hedge on duration without first re-checking this
   table — it was a different number before 2018 and may become one again.
2. **Credit is the only rates axis with crypto-stress beta** (HYG −10.6 bp on those days).
   If a rates hedge exists, it is a short-credit one — but see (3).
3. **Short-credit signals are all too slow.** By the time realised credit vol, a credit
   drawdown or a VIX spike confirms, the spread has already widened. Anything that works
   here has to be *leading*, not confirming — the crypto book's own positioning, dealer
   inventory, or primary-market supply, not price-derived credit stress.
4. Duration-stripping HYG with a fixed 0.47 IEF leg works cleanly and is reusable
   (`data_lib.hy_excess`), as is the crypto-book proxy and hedge diagnostics
   (`data_lib.crypto_book`, `data_lib.hedge_report`).

## 6. Files

* `code/rates-bonds/credit-spread-trend/data_lib.py` — data plumbing, duration-stripped HY
  excess return, crypto-book proxy, hedge diagnostics.
* `fetch_pre2010.py` — pre-2010 ETF history into the `*_d_pre2010.parquet` convention.
* `explore.py` / `explore_output.txt` — trend on the credit premium (24 configs).
* `screen.py` / `screen_output.txt` — four-family sleeve screen (32 configs).
* `riskoff_screen.py` / `riskoff_output.txt` — the risk-off family (26 configs).
