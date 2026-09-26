# Non-synchronous overreaction of country ETFs — Failed

**Asset class:** `global-equity-etf` · **Short name:** `nonsync-overreaction` · **Date:** 2026-09-26
**Status:** **Failed**. There is a real, economically explained effect, but it has decayed after
2012 to a size that no longer pays a round trip.

## Idea

Levy & Lieberman (2013, *J. Banking & Finance* 37(5)) found that US-listed country ETFs
**over-react to the S&P 500 during hours when their home market is closed**. During synchronous
hours the ETF follows its NAV. During non-synchronous hours the S&P dominates, by more than the
foreign index later delivers. The US session is fully non-synchronous for the Asian ETFs (EWJ,
EWY, EWA, FXI, INDA, EEM) and half non-synchronous for Europe (EWG, EWU, EFA; local close 11:30
ET). It is synchronous for the Americas (EWC, EWZ), which gives a natural **control group**.

Tradeable form, daily bars, fill at the close: at close t compute the ETF's US-session residual
`u_t = r^oc_{i,t} − β_{t−1} r^oc_{SPY,t}` (open→close, β = rolling 250d intraday beta, lagged).
Z-score it by its trailing 60d std, lagged. Fade it for one day, SPY-hedged on the rolling
close-to-close beta.

## Data and conventions

* ETFs spliced 1996+ (`code/global-equity-etf/shared/data.py`, pre-2010 in `data/<T>_d_pre2010.parquet`),
  local indices `^N225 ^KS11 ^AXJO ^HSI ^NSEI ^GDAXI ^FTSE ^BVSP ^GSPTSE`, FX ETFs FXY/FXA/FXE/FXB.
* **Sample starts 2003-01-01.** Fixed on data quality before any result was seen. In 1999-2001,
  20-58 % of EWZ/EWY/EWA/EWC bars have Open == Close and many have zero volume. Stale closes
  manufacture exactly the reversal this idea looks for.
* **Split fixed in advance for the whole session:** IS ≤ 2012-12-31, OOS 2013-01-01 → 2026-09-25.
  That also makes the OOS a post-publication test.
* Costs: 5 bp/side on country ETFs, 1 bp/side on the SPY hedge. 0 and 2 bp are shown to locate the
  gross edge.
* **Bid-ask bounce check.** A closing-print bounce of ±5 bp (EWJ traded near $10 with a 1 c tick
  before its 2016 reverse split) implies a reversal coefficient of −(0.0005/0.006)² ≈ −0.007. The
  measured coefficients are 15-30× larger, so bounce is not the source. It is also not a stale
  print: the control group (EWC, EWZ), with similar liquidity, does not reverse.
* **yfinance FX timing trap (documented in passing).** FXY's day-t return correlates 0.57 with
  `JPY=X` row t+1 and 0.25 with row t. The `=X` row t+1 holds day t's US-hours move, so a NAV proxy
  built from `=X` row t is stale but safe, and row t+1 is look-ahead. The NAV proxy here uses the
  synchronous FX ETFs instead.

## Results

### 1. Regressions (`01_explore.py`): next-day return on lagged moves, HAC t-stats

The next-day return's loading on the ETF's own US-session return (controlling for SPY's intraday
return and next-day SPY):

| ETF | session | IS b (t) | OOS b (t) |
|---|---|---:|---:|
| EWJ | Asia | −0.23 (−4.7) | −0.12 (−2.6) |
| EWY | Asia | −0.11 (−1.6) | −0.27 (−4.3) |
| EWA | Asia | −0.19 (−5.2) | −0.12 (−2.6) |
| FXI | Asia | −0.18 (−3.4) | −0.06 (−1.0) |
| INDA | Asia | n/a (2012 list) | −0.16 (−3.3) |
| EWU | Europe | −0.24 (−6.6) | +0.02 (0.4) |
| EWG | Europe | −0.10 (−3.2) | +0.01 (0.2) |
| EWC | Americas | −0.05 (−2.1) | +0.01 (0.3) |
| EWZ | Americas | +0.02 (0.6) | −0.04 (−1.4) |

The ranking the mechanism predicts (Asia > Europe > Americas) holds. The European effect
disappears after 2012; the Asian one roughly halves.

### 2. Quintiles and decay (`02_quintiles.py`)

Spearman IC of z with the next-day hedged return: EWJ −0.084 IS → −0.031 OOS, EWY −0.075 → −0.023,
EWU −0.135 → +0.012. Fading |z| > 1.5 earns 11-22 bp per trade IS and **4-11 bp OOS** on the
Asian names. IC at t+2 and t+3..5 is ≈ 0 or positive, so the reversal completes in one day. It
cannot be smoothed into a lower-turnover multi-day signal.

### 3. Hedged books (`03_book.py`), 25 configurations × 3 cost levels

Selected rows, Sharpe:

| Book | gross full | gross IS | gross OOS | net 2 bp OOS | net 5 bp full | net 5 bp OOS | ETF turnover/yr |
|---|---:|---:|---:|---:|---:|---:|---:|
| ASIA4 (EWJ EWY EWA INDA) linear z | 0.93 | 1.37 | 0.73 | −0.08 | −0.65 | −1.00 | 128× |
| ASIA4 tail \|z\|>1.5 | 0.77 | 1.22 | 0.55 | 0.04 | −0.19 | −0.52 | 26× |
| ASIA4 tail \|z\|>2 | 0.53 | 0.82 | 0.39 | 0.03 | −0.14 | −0.36 | 12× |
| ASIA6 linear z | 0.52 | 0.85 | 0.37 | −0.43 | −1.06 | −1.32 | 125× |
| EUR (EWG EWU EFA) linear z | 0.53 | **2.03** | −0.24 | −1.02 | −1.06 | −1.86 | 169× |
| ASIA+EUR tail \|z\|>1.5 | 0.63 | 1.49 | 0.23 | −0.38 | −0.61 | −1.05 | 30× |
| AMER (control) linear z | −0.18 | −0.46 | −0.01 | −0.62 | −1.40 | −1.29 | 136× |

No configuration has a positive net Sharpe OOS at 5 bp, and none exceeds 0.05 at 2 bp. The
Europe book had a gross IS Sharpe of 2.0, which is what the effect looked like when Levy-Lieberman
wrote it up. It is negative gross since 2013.

### 4. NAV-premium form (`04_nav_premium.py`), 2007+

Premium = log ETF − log(local index × FX ETF), demeaned over 20d and z-scored. IS 2007-12 it
beats the residual signal: IC −0.08 to −0.11, t ≈ −3 on EWJ, EWU, FXI, EWG and INDA. OOS it is
dead: IC −0.06 to +0.02, and no t-stat below −2.

### 5. VIX regime (`05_vix_regime.py`)

Fade edge per |z|>1.5 trade by VIX bucket. IS: 0-15 +14 bp, 15-20 +7, 20-30 +14, **>30 −33 bp**.
OOS: +2, −2, +16, +25 bp. The best OOS buckets are the ones IS says to avoid, so a gate chosen
in-sample (VIX < 30) earns about 4-5 bp per trade OOS, below the ~11 bp round trip.

## Verdict

**Failed.** The effect is real and economically placed: it appears in the non-synchronous
markets, is stronger where more of the day is non-synchronous, and is absent in the synchronous
control. But after 2012 its size is 4-11 bp per trade against a 10+ bp round trip. It is a
one-day effect, so the turnover cannot be reduced. The binding constraint is cost. Gross OOS
Sharpe tops out at 0.73.

Variants: ≈ 29 book configurations (25 in `03_book.py`, 4 VIX buckets) plus descriptive regressions
on 11 ETFs and the 7-ETF premium study. With ~29 trials, the expected best-of-N Sharpe under the
null is already ~0.5, so even the gross numbers are unremarkable after deflation.

## What would change the verdict

* Real closing-auction costs below ~1.5 bp/side on EWJ/EWY/EWA/INDA. Plausible today for EWJ
  and INDA, not for EWA or historically. I did not relax the cost assumption.
* Using the signal as a free timing overlay on turnover a book already does (e.g. delaying
  a rebalance buy of an Asian ETF by a day after a large positive US-session residual). This is
  execution, not alpha.

## Files

`code/global-equity-etf/nonsync-overreaction/`: `lib.py`, `01_explore.py` … `05_vix_regime.py`.
