# vix-cot-positioning — CFTC VIX-futures positioning as a crowding gate on short VIXY

**Status: Working (with caveats).** Short VIXY in contango only when asset managers hold more
VIX-futures net long than usual. Selection-free 25-vote ensemble, one-day-lagged slope, 5 bp/side:
**net Sharpe 1.00 full (2011-01 → 2026-09), 1.04 IS (2011–18), 0.96 OOS (2019–26)**, CAGR 32 %,
MaxDD −43 %, skew −1.5. The contango-carry baseline under the same timing: 0.60 / 0.66 / 0.54, MaxDD −86 %.
Main caveat: OOS is front-loaded. 2019–21 Sharpe 1.56, **2022–26 0.38** (carry 0.17 in that window).

Date: 2026-09-27 · Asset class: vol-complex · Author: research agent (Opus 5.5)

## 1. Idea

The previous vol-complex study (`term-structure-carry`, ~140 variants) showed that short-VIXY carry
earns ~0.8 Sharpe and that nothing built from VIX-complex *prices* (slope, VRP, VVIX, momentum,
futures basis, calendar) improves it. This idea uses a different information set: **who holds the
VIX futures**.

The CFTC's weekly Traders-in-Financial-Futures (TFF) report splits VIX-futures open interest
(contract 1170E1) into dealers, asset managers, leveraged funds and other reportables. The
asset-manager bucket is dominated by the ETP sponsors that hold futures directly: long-vol ETFs such as
VIXY/UVXY/VIXM, and inverse-vol ETFs such as SVXY/SVIX. Its net share is therefore a gauge of
retail vol-ETP crowding:

* **High** asset-manager net long, relative to its own history: the crowd has bought long-vol
  insurance, typically after a spike. The short-vol premium is rich and the curve normalises.
  Contrarian: be short vol.
* **Low / net short**: inverse-vol products are crowded, as in Jan-2018 (SVXY/XIV), Jul-2024
  (SVIX/SVXY), and now. The short-vol trade is crowded and a spike unwinds it violently. Stand aside.

This is the vol-complex analogue of the COT contrarian-positioning edge found in FX
(`fx-majors/cot-positioning`). The mechanism has academic support: Yoon (2022, *J. Futures Markets*)
links VIX-futures returns partly to investors' net positions in VIX futures.

## 2. Data

* `data/CFTC_COT_tff_vix_w.parquet` — **new**: VIX-futures TFF, weekly from 2006-08 (1 018 reports),
  and `data/CFTC_COT_legacy_vix_w.parquet` (legacy report, 2004+). Written by
  `code/vol-complex/shared/fetch_cot_vix.py`, which reuses the FX COT fetcher's download and
  release-timing logic. `refresh_current_year()` is available for live use.
* Release timing: positions are as of Tuesday, published Friday 15:30 ET, and later in holiday and
  shutdown weeks. A report is used only on sessions whose date is after `avail_utc` (Tuesday +
  4 days 21:00 UTC, holiday weeks +7 days, shutdown backlogs clipped to their release dates). The
  first close that trades a normal Friday release is therefore **Monday's**. This is one session
  more conservative than necessary.
* Source gap: the CFTC published no VIX-futures reports between 2008-12-16 and 2009-06-02, nor
  between 2008-11-18 and 12-16 (both reports, every contract name; open interest had halved to
  ~21k). The z-scores count reports, so around 2009 a 156-report window spans ~3.5 calendar
  years. Only the 2011–12 signals are affected, and there is no look-ahead.
* Prices: `^VIX`, `^VIX3M`, `VIXY`, `SVXY`, `SPY` from the shared flat cache, refreshed to
  2026-09-25.
* Split: IS 2011-01 → 2018-12 / OOS 2019-01 → 2026-09. This is the split `term-structure-carry`
  fixed; it was not re-picked.
* Contango uses VIX3M/VIX **lagged one session**. The index closes at 16:15 ET, after the 16:00 ETP
  fill. The same-day version is reported for comparison only.

## 3. Screen (01_screen.py)

Spearman IC of weekly-sampled features vs forward VIXY log return, IS / OOS:

| feature | 5d IS | 5d OOS | 21d IS | 21d OOS |
|---|---|---|---|---|
| asset-manager net share | −0.11 | −0.12 | −0.17 | **−0.27** |
| AM net z-score (156 w) | −0.13 | −0.12 | −0.22 | −0.27 |
| leveraged-fund net share | +0.09 | +0.08 | +0.13 | +0.15 |
| other-reportables net z (156 w) | +0.11 | +0.02 | +0.27 | +0.21 |
| dealer net | −0.06 | +0.07 | −0.11 | +0.15 (sign flips) |
| legacy non-commercial / commercial | ~0 | ~0 | ~0 | ~0 |
| open interest (level, z, change) | ~0 | ~0 | ~0 | ~0 |

Only the asset-manager and leveraged-fund buckets carry a same-sign signal in both halves; the two
are −0.63 correlated. The legacy report's coarse split carries no information.

**Beyond price state (03_attribution.py).** Regress forward 21-day VIXY returns on AM z156,
log VIX, VIX3M/VIX and 21-day VIX momentum (HAC t). The AM coefficient is t = −1.9 IS and
t = −2.0 OOS with the price controls in. AM z has correlation 0.24 with log VIX and −0.06 with
the slope.

Within contango, the annualised Sharpe of being short VIXY on the next day, by quintile of AM z156:

| quintile (low → high AM net) | Q1 | Q2 | Q3 | Q4 | Q5 |
|---|---|---|---|---|---|
| IS | 0.29 | 0.68 | 0.37 | 0.85 | **2.48** |
| OOS | 0.13 | 0.05 | 0.43 | 1.63 | **1.86** |

Contango carry earns essentially nothing when asset managers are light. The long-vol side (short
the bottom quintile) loses slightly in both halves, so the rule is short / flat, not long / short.

## 4. Variants

### 4.1 First pass (02_backtest.py, 40 configs + 2 baselines)

Four signal families (AM net, AM z52/104/156, AM pct-rank, leveraged-fund z, other z, dealer z),
each run four ways: linear long/short, sign long/short, short-only, and as a gate on carry
(same-day slope):

| family | lin L/S | sign L/S | short-only | gate on carry |
|---|---|---|---|---|
| AM z156 | 0.63 (0.99/0.30) | 0.64 | 0.87 (1.04/0.70) | **0.98 (1.00/0.97)** |
| AM z104 | 0.57 | 0.45 | 0.74 | 0.92 (0.92/0.91) |
| AM z52 | 0.51 | 0.47 | 0.76 | 0.87 (1.01/0.72) |
| LF z156 | 0.48 | 0.56 | 0.86 | 0.83 (0.87/0.78) |
| other z104 | 0.43 | 0.46 | 0.79 | 0.84 (0.88/0.81) |
| dealer z104 | 0.02 | 0.12 | 0.54 | 0.51 (0.88/0.19) |

Format: full (IS/OOS). Baselines: short always 0.63, carry 0.80 (0.88/0.72).

The long/short versions are weak because long VIXY loses money even when crowding is extreme.
The value lies in **gating the short**.

### 4.2 Pre-declared grid (04_grid.py, 50 configs)

Rule: short 1× VIXY if contango AND score > θ. Scores: AM z52/z104/z156, and
comp = (z(AM) − z(LF))/2 over 104/156. θ ∈ {−0.5, 0, 0.25, 0.5, 1.0}; slope lag ∈ {0, 1}.

* Every one of the 50 configs has full-sample Sharpe ≥ 0.61. The median is **0.90 / 0.93 IS /
  0.85 OOS** with the same-day slope and **0.87 / 0.91 / 0.83** with the lagged slope. The carry
  baselines are 0.80 and 0.60.
* IS-best (comp156, θ = 0.25) → OOS 0.80 same-day slope / 0.89 lagged.
* Lagging the slope costs carry 0.2 Sharpe but costs the COT gate almost nothing. Most of the
  gate's value is weekly information that does not depend on the 15-minute close mismatch.

### 4.3 Deployable rule: 25-vote ensemble (05_ensemble.py, strategy.py)

To avoid picking θ or a window, the weight is the **average of all 25 (score, θ) rules** with the
lagged slope. The result is a short VIXY position between 0 and 100 %.

| | Sharpe full | IS | OOS | CAGR | MaxDD | Skew | t_NW |
|---|---|---|---|---|---|---|---|
| **ensemble, slope lag 1 (spec)** | **1.00** | **1.04** | **0.96** | 32 % | −43 % | −1.5 | 4.3 |
| ensemble, same-day slope | 1.01 | 1.03 | 1.00 | 32 % | −37 % | −1.6 | 4.5 |
| continuous size clip(0.5+comp156/2) | 1.03 | 1.11 | 0.95 | 37 % | −47 % | −1.7 | 4.6 |
| ensemble as long SVXY | 0.95 | 1.05 | 0.91 | 23 % | −44 % | −0.8 | 4.0 |
| carry ref, slope lag 1 | 0.60 | 0.66 | 0.54 | 18 % | −86 % | −1.8 | 2.5 |

Turnover 10.7× per year one-way. Average short 0.40. In the market 72 % of days at an average size
of 0.55, and at full size on 9 % of days. Correlation with carry: 0.73.

### 4.4 Diagnostics (07_legs_diag.py)

Using the AM *long* share alone (long-vol ETP holdings) gives 0.70 full; the AM *short* share alone
(inverse-vol ETP holdings) gives 0.54; the net gives 0.93. The net measure, both sides of the ETP
crowd, is what carries the information.

## 5. Robustness (06_robustness.py, final.py)

* **Release lag placebo.** Adding 0 / 1 / 2 / 4 / 8 / 13 / 26 / 52 weeks of extra COT lag gives
  Sharpe 1.00 / 1.02 / 0.98 / 0.80 / 0.70 / 0.72 / 0.52 / 0.72. The signal decays smoothly
  instead of spiking at zero lag. It is not an artefact of release timing. At a very long lag it
  drifts back toward the ~0.6 of "short vol ~40 % of the time in contango".
* **Timing spot-check.** On 2018-02-05 (Monday of Volmageddon) the rule used the report as of
  2018-01-30, released 02-02. On 2024-08-05 it used the 2024-07-30 report. On Thanksgiving week
  2024 it waited until 12-04.
* **Truncation test.** Weights recomputed on data cut at 2019-06-14, 2022-03-31, 2024-08-02 and
  2026-06-30 equal the full-run weights exactly (max |diff| = 0).
* **Costs.** At 0 / 5 / 10 / 20 / 40 bp per side, Sharpe is 1.02 / 1.00 / 0.99 / 0.95 / 0.89.
* **Block bootstrap** (21-day blocks, 2 000 draws): Sharpe 5–95 % **[0.63, 1.38]**,
  P(Sharpe > 0.5) = 0.98, P(> 1) = 0.51.
* **Deflated Sharpe** (Bailey–López de Prado, skew and kurtosis adjusted): 0.96 at N = 25, 0.89 at
  N = 100, **0.87 at N = 150** trials. About 100 configurations were evaluated in this idea.
* **vectorbt cross-check** (`Portfolio.from_orders`, target percent, both directions, 5 bp fees):
  Sharpe 0.997 vs 1.003, return correlation 1.0000.
* **SPY attribution.** β = 0.96, α = **19 %/yr (t 2.7)** full; OOS β 0.71, α 17.5 %/yr (t 1.9).
  SPY-hedged Sharpe 0.67 full / 0.62 OOS. Unlike plain carry, whose beta-hedged Sharpe was
  negative, this has SPY-orthogonal return.
* **Stress windows**, strategy vs carry (lag 1):

  | window | strategy | carry |
  |---|---|---|
  | Aug-2015 | −8 % | −25 % |
  | Volmageddon 2018-01-29 → 02-12 | **0 %** (flat) | −46 % |
  | COVID 2020-02-20 → 03-20 | **0 %** | −33 % |
  | H1-2022 | −16 % | −58 % |
  | Aug-2024 | **0 %** | −60 % |
  | Apr-2025 tariffs | −28 % | −34 % |

* **Yearly Sharpe.** 2011 0.16, 2012 2.14, 2013 1.33, 2014 1.59, 2015 0.43, 2016 1.91, 2017 3.14,
  2018 −0.33, 2019 2.14, 2020 1.09, 2021 1.78, 2022 0.00, 2023 1.66, 2024 0.41, 2025 0.70,
  2026 YTD 0.07.

## 6. Risks and caveats (read before deploying)

1. **Recent performance is weaker.** Sub-period Sharpe: 2019–21 1.56 (64 %/yr); 2022–26 **0.38**
   (8.7 %/yr); 2023–26 0.49. The strategy still beats carry in 2022–26 (0.17), mainly by sitting out
   Aug-2024. But since the SVIX launch (2022) asset managers have trended net short, the z-scores
   sit low, and the book has been mostly flat. It is flat **today**: AM net −13 % of OI, a record
   low. Expect long idle stretches. Live Sharpe of 0.4–0.8 is a more honest expectation than 1.0.
2. **Gap risk is not removed.** This is still a short-vol book. VIXY's worst closes in the sample
   are +43 % (2024-08-05), +39 % (2020-03-16), +34 % (2018-02-05, 2020-06-11). At full size
   (−1.0), one such day costs 35–45 % of capital. The worst realised day was −25.5 % (2020-06-11
   at −0.76), and 2025-04-03 cost −19.7 %. The gate sat out the three largest spikes, but that
   depends on inverse-vol crowding showing up ahead of the spike, and Apr-2025 shows it will not
   always. A deployment that wants a smaller tail can scale `size` (Sharpe is scale-invariant); a
   size of 0.5 caps a +43 % day at about −21 %.
3. **Classification risk.** The mechanism relies on the CFTC putting the vol-ETP sponsors in
   "asset manager". A reclassification would move the series. The rolling z-scores re-centre within
   1–3 years, but a jump would mis-signal for a while.
4. **Borrow.** Short VIXY in a real account pays a borrow fee (historically 1–5 %/yr for VIXY, far
   more for UVXY). The sim book does not charge it. At the average 0.40 short, 3 % borrow is
   ~1.2 %/yr, about −0.04 Sharpe. Long SVXY avoids borrow, at Sharpe 0.95 and a smaller tail after
   2018 (−0.5× product).
5. **Data dependency.** A weekly CFTC download is required (`fetch_cot_vix.refresh_current_year()`).
   A missed update leaves the last report in force, which is benign because the signal is slow.

## 7. Conclusion

Positioning in VIX futures is information that VIX-complex prices do not contain. When the ETP crowd
is long insurance, selling it pays; when the crowd is short vol, stepping aside avoided the three
largest spikes of the decade. Used as a gate on contango carry, it lifts the knowable-at-the-fill
Sharpe from 0.60 to 1.00 (0.54 → 0.96 OOS), halves the drawdown and adds SPY-orthogonal alpha. It is
Working, with the caveat that its 2022–26 performance is weaker (0.38) and it has been mostly idle
since the inverse-vol ETP boom.

## 8. Files

* `code/vol-complex/shared/fetch_cot_vix.py` — CFTC VIX-futures TFF + legacy fetcher, release-lag
  mapping (`on_session_rows`).
* `code/vol-complex/shared/vc_data.py`, `vc_plot.py` — vol-complex panel, backtest wrappers, and
  figure style.
* `code/vol-complex/vix-cot-positioning/`: `01_screen.py`, `02_backtest.py`, `03_attribution.py`,
  `04_grid.py`, `05_ensemble.py`, `06_robustness.py`, `07_legs_diag.py`, `final.py`, `cot_lib.py`,
  `strategy.py` (`target_weight(vixy_close, vix, vix3m, tff)`).
* `alphas/vol-complex/vix-cot-positioning/`: `spec.md`, `stats.csv`, `yearly.csv`,
  `backtest_series.parquet`, `equity_drawdown.png`, `signal_exposure.png`, `yearly_sharpe.png`.
* Figures in this folder: `01_equity_drawdown.png`, `02_signal_exposure.png`, `03_yearly_sharpe.png`.
