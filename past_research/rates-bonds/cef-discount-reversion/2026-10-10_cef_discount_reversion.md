# cef-discount-reversion — short-term reversal of bond closed-end fund discounts

**Date:** 2026-10-10 · **Asset class:** rates-bonds · **Status: Working** (capacity-limited, cost-sensitive)

**Result.** A dollar-neutral long/short book of bond closed-end funds, long the funds whose
discount to NAV has widened against their own 60-session average and against their peers,
short the ones that have run rich, entered one full session after the signal. Net of 10 bp
per side: Sharpe **2.71 in sample (2004-14) / 2.49 out of sample (2015-26)**, CAGR 9.4 %,
vol 3.5 %, max drawdown −3.1 %. At 20 bp per side: 2.20 / 1.71. It is a liquidity-provision
edge in a retail market: real, small (roughly $1-3M of capacity), and it depends on being able
to short closed-end funds and to trade at the close for about 10 bp.

Code: `code/rates-bonds/cef-discount-reversion/` · Spec: `alphas/rates-bonds/cef-discount-reversion/spec.md`

---

## 1. Idea

Closed-end funds (CEFs) issue a fixed number of shares. Nobody can create or redeem at NAV,
so the price and the NAV are two separate markets: the NAV is the bond market's valuation of
the portfolio, the price is whatever the fund's (mostly retail) shareholders pay each other.
Selling pressure in one fund widens its discount; nothing forces it back except the pressure
ending. Pontiff (1995) showed discounts mean-revert and predict fund returns; Patro, Piccotti
and Wu report a quintile long-short Sharpe near 1.9 on monthly data for 1998-2011.

This asset class had not been touched in the repo. The earlier `muni-reinvestment-flow` work
used muni *ETFs*; ETFs have an arbitrage channel and CEFs do not.

## 2. Data

* **Universe:** CEFConnect `api/v3/DailyPricing` (359 US CEFs alive today, with Morningstar
  category and NAV ticker). Bond categories kept, fixed before any return was looked at:
  Municipal (+ single-state, CA, NY) and High Yield, Senior Loans, Investment Grade,
  Multi-Sector, Global Income, Limited Duration, EM Income, Taxable Muni. Preferreds and
  convertibles left out as equity hybrids. 180 funds; 170 have both a price and a NAV series.
* **Prices and NAVs:** yfinance. The NAV of fund `NAD` is the ticker `XNADX`; histories start
  2000-2003. Panel cached at `data/CEF_BOND_panel_d.parquet` (886k rows, OHLC unadjusted,
  adjusted close, volume, NAV) by `fetch_cef.py`.
* **Liquidity:** the median fund trades about $1M a day at a $13 price. Funds with a trailing
  60-session median dollar volume ≥ $1M (and the other eligibility rules): 19 in 2004, 44 in 2010, 62-75 since 2013.

### Traps found in this data (each one moved a number before it was fixed)

| Trap | What it did | Fix |
|---|---|---|
| NAV is published in the evening | a signal using `nav[t]` cannot trade at close t | one-session skip everywhere; `strategy.target_weights` row t uses data ≤ t−1 |
| Yahoo split-adjusts prices but not the NAV ticker | `ln(price/NAV)` is off by `ln(ratio)` before every reverse split (BKT, FAX, MGF, MIN) | discount rebuilt from its own daily changes with one-day jumps > 0.4 zeroed; a deviation-from-mean signal is immune to the constant |
| Funds without a daily NAV | Yahoo's "NAV" for OXLC, OCCI, EARN, FSSL, PDCC is a copy of the price; discount is always 0, so the fund looked "rich" whenever its peers sold off | eligibility requires NAV ≠ close and a NAV that moved in the last 10 sessions |
| DHY | Yahoo's dividend history is 10× too large for its prices (implied yield ~100 %/yr), and in 2026 its price flips between $1.7 and $17 on alternate days | excluded; price floor now uses the 60-session median, not one print |
| My own return filter | `|ret| < 50 %` silently zeroed OXLC's real +54 % on 2020-03-19 — a 1.1 % loss on a short | removed; only a ×3 one-day print is treated as a bad tick |
| My own bad-tick rule | used `nav[t+1]` to recognise a bad `nav[t]` | replaced by a same-day rule |
| My own split rule (first version) | dropped a fund's whole history before its *last* split, so past weights depended on future splits | caught by the truncation test (§7); replaced by the rule above |

The vectorbt cross-check is what exposed the fifth one: the two engines disagreed (Sharpe 0.77
vs 2.37 out of sample) until the return filter was removed and the two data problems behind
it were fixed. After the fixes they agree to 0.02.

**Survivorship.** The panel holds only funds alive in October 2026. Merged, liquidated and
open-ended funds are absent and cannot be recovered from free data. See §8.

## 3. Protocol fixed before testing

* In sample 2004-01 → 2014-12; out of sample 2015-01 → 2026-10. Parameters chosen on IS only.
* Cost 10 bp per side as the headline, with 5 / 15 / 20 / 30 as sensitivities.
* Entry one session after the signal's close.
* Tradable universe: trailing median dollar volume ≥ $1M, price ≥ $3, 250 sessions listed.

## 4. Event study (`02_signal_ic.py`)

Cheap-minus-rich quintile spread, sorted inside muni / taxable, forward return measured from
the close one session after the signal:

| signal | horizon | IS spread (bp) | OOS spread (bp) | t IS / OOS |
|---|---|---|---|---|
| discount level | 5 d | 27 | 20 | 5.0 / 5.3 |
| 60-session z-score | 1 d | 22 | 13 | 16.1 / 20.5 |
| 60-session z-score | 5 d | 69 | 44 | 10.8 / 13.5 |
| 60-session z-score | 21 d | 118 | 73 | 4.2 / 7.2 |
| 120-session z-score | 5 d | 64 | 42 | 10.5 / 13.1 |
| 5-session change | 5 d | 60 | 40 | 10.1 / 11.7 |

Same sign in both halves for all 28 signal × horizon cells. The reversal is front-loaded:
about a third of the 21-day spread arrives in the first two sessions after the skip. A
long-short pair pays four sides, so 10 bp per side costs 40 bp per round trip: the 5-day
spread barely covers it and the book has to hold for weeks.

## 5. Books

### 5.1 Rank books (`03_grid.py`, 140 cells)

Seven signals × quantile (20 %, 33 %) × rebalance every 1/5/10/21 sessions × grouped or
pooled, plus hysteresis versions (enter in the extreme quantile, leave at the median).

* IS-best: hysteresis on the 120-session z-score, enter the extreme third, leave at the group
  median → **3.00 IS / 2.54 OOS** at 10 bp, 46× turnover. (Before the data fixes of §2 the
  top two cells were tied at 2.72-2.73 and swapped order between runs; the other one, a
  daily-rebalanced 60-session tercile book, is 1.48 OOS. The family mean is what to trust.)
* Whole grid: IS mean 1.63, OOS mean 1.06, IS/OOS rank correlation 0.80.
* **It is cost-fragile out of sample:** 15 bp → 1.29, 20 bp → 0.03. Calm years (2017, 2018,
  2025) barely pay for the turnover.

### 5.2 What does a trade cost? (`05_spreads.py`)

| estimator (full spread, bp, liquid funds) | median | mean |
|---|---|---|
| one cent / price (lower bound) | 7-9 | 8-11 |
| Abdi-Ranaldo close-high-low | 17-25 | 25-38 |
| Corwin-Schultz high-low | 18-32 | 22-34 |

Half of those is the cost per side: 4-5 bp at the tick floor, 12 bp median / 15 bp mean on
Abdi-Ranaldo. The range-based estimators are built on negative serial covariance of closing
prices — the same reversal this book earns — so they overstate the quoted spread. 10 bp per
side sits between the floor and the estimator; 20 bp is the stress case. Re-costing the rank
book with each fund's own Abdi-Ranaldo half-spread (16.3 bp trade-weighted): 1.91 / 1.43.

### 5.3 Threshold books (`06_cost_robust.py`, 48 cells) — the selected family

Designed after seeing §5.1's cost fragility: act only when the dislocation is large in price
terms, so a calm market produces few trades.

    dev  = disc − mean(disc, win)          rdev = dev − group median(dev)
    long from rdev ≤ −x_in until rdev ≥ −x_out ; short symmetric
    5 % per name on the smaller side, the other side scaled to match, 50 % cap per side

Grid: raw deviation (x_in 1.5 / 2.5 / 3.5 / 5 %) or z-score (1 / 1.5 / 2 / 2.5), windows
60 / 120 / 250, exit at 0 or half the entry. **Selection rule: IS net Sharpe at the 20 bp
stress cost.**

| cell | IS 20 bp | IS 10 bp | OOS 20 bp | OOS 10 bp | OOS own-spread | turnover |
|---|---|---|---|---|---|---|
| **dev 60, 2.5 %, exit 0 (selected)** | **2.21** | 2.71 | **1.71** | **2.49** | 1.95 | 21× |
| dev 60, 1.5 %, exit 0 | 2.20 | 3.07 | 1.47 | 2.90 | 2.12 | 36× |
| z 120, 1.0, exit 0 | 2.01 | 2.83 | 1.14 | 2.51 | 1.88 | 29× |
| dev 60, 3.5 %, exit 0 | 1.94 | 2.23 | 1.47 | 1.90 | 1.49 | 11× |
| grid mean (48) | 1.40 | 2.05 | 0.73 | 1.68 | 1.17 | |

IS/OOS rank correlation across the 48 cells: 0.91 at 20 bp, 0.96 at 10 bp; all 48 are positive
out of sample at 10 bp and 41 at 20 bp. The top two cells
are a tie in sample (2.21 vs 2.20); the rule picked the lower-turnover one, which has the
lower 10 bp number and the higher 20 bp number out of sample.

## 6. The selected book (`07_selected.py`, `strategy.py`)

| net, 10 bp per side | Sharpe | CAGR | Vol | MaxDD | t (NW) |
|---|---|---|---|---|---|
| IS 2004-14 | 2.71 | 11.7 % | 4.1 % | −3.1 % | 5.6 |
| OOS 2015-26 | 2.49 | 7.3 % | 2.8 % | −2.6 % | 5.9 |
| Full | 2.57 | 9.4 % | 3.5 % | −3.1 % | 7.9 |

Turnover 21× a year, average gross 0.60 (cap 1.00), net 0, about 16 names (8 + 8), average
holding 22 sessions, largest single weight 5 %. Daily skew +4.0, worst day −2.2 %
(2008-09-29), best +4.8 % (2008-10-13).

**Cost ladder (IS / OOS):** 0 bp 3.20 / 3.26 · 5 bp 2.96 / 2.88 · 10 bp 2.71 / 2.49 ·
15 bp 2.46 / 2.10 · 20 bp 2.20 / 1.71 · 25 bp 1.95 / 1.31 · 30 bp 1.69 / 0.91 · 40 bp 1.17 / 0.10.

**Entry delay on top of the one-session skip (10 bp):** +1 session 2.14 / 1.79 · +2 1.70 / 1.18 ·
+4 1.03 / 0.82 · +9 0.33 / 0.19. Entering one session *earlier* — using the NAV of the entry
close, which is not public yet — would show 3.19 / 3.28; that number is not tradable and is
the reason for the skip.

**By year, net 10 bp (sum of daily returns, %; the chart in the spec compounds them, so 2008
reads +54.7 % there):** 2004 2.6 · 05 1.8 · 06 1.8 · 07 6.5 · 08 44.2 · 09 22.2 · 10 7.4 ·
11 6.9 · 12 10.1 · 13 13.9 · 14 4.8 · 15 1.9 · 16 4.4 · 17 1.3 · 18 −0.4 · 19 4.7 · 20 21.6 ·
21 6.6 · 22 20.7 · 23 5.6 · 24 5.0 · 25 6.2 · 26 (to 9 Oct) 5.1. At 20 bp the only negative
year is 2018 (−1.9 %).

**Sub-periods (10 bp / 20 bp):** 2004-07 1.63 / 1.12 · 2008-09 4.09 / 3.67 · 2010-14 3.31 / 2.37 ·
2015-19 1.23 / 0.46 · 2020-22 4.06 / 3.26 · 2023-26 2.25 / 1.32. The return is paid for
providing liquidity in stress; quiet stretches earn little.

**Not a handful of days or funds.** Dropping the best 50 days: 1.94 IS / 1.72 OOS. Top-10
funds are 37 % of gross P&L; 111 of 131 traded funds are profitable; without the 13 PIMCO
funds 2.39 / 2.31; without the ten most profitable funds 2.30 / 2.29.

**Legs (10 bp).** Long leg alone 0.99 / 0.89 (carries CEF beta); short leg alone 0.50 / 0.38.
Against the equal-weight liquid universe at the same notional: long leg 2.17 / 1.70 (+4.0 %/yr),
short leg 2.59 / 2.31 (+5.0 %/yr). Both sides carry the effect.

**Borrow fee on shorts (10 bp cost):** 100 bp/yr 2.64 / 2.38 · 300 bp 2.51 / 2.15 · 500 bp 2.38 / 1.92.

**Liquidity floor (10 bp; 20 bp):** $0.5M 3.35 / 2.74 (2.64 / 1.81) · $1M 2.71 / 2.49 ·
$2M 1.76 / 1.82 (1.33 / 1.28), average gross 0.22 · $3M 0.75 / 0.93, gross 0.06. The effect
lives in the less liquid funds; above $3M a day there is almost nothing to trade.

**Groups.** Taxable only 2.56 / 2.24; muni only 1.58 / 1.64 (few muni dislocations reach 2.5 %).

**Parameter neighbours (10 bp IS / OOS):** window 40 → 2.38 / 2.43, 90 → 2.42 / 2.20; entry
1.5 % → 3.07 / 2.90, 2 % → 2.85 / 2.64, 3.5 % → 2.22 / 1.90; exit +0.5 % → 2.66 / 2.40; unit 3 %
→ 2.74 / 2.49, 10 % → 2.77 / 2.30; 500-session listing rule → 2.61 / 2.45. No cliff.

**Market exposure (2010-26 daily):** beta 0.02 to SPY, 0.05 to HYG, 0.06 to MUB, 0.00 to TLT.
Daily correlation with the deployed sleeves: −0.02 (treasury-flow-calendar), +0.03
(muni-reinvestment-flow); monthly 0.26 and 0.03. An inverse-vol blend of the two deployed
sleeves is 1.23 (2010-26); adding this book takes it to 2.56.

## 7. Lookahead checks (`08_lookahead_check.py`, `09_concentration_vbt.py`)

* **Truncation.** Inputs cut at ten dates (2008-10-15 … 2026-07-22, month-ends and
  mid-month): the last 40 rows of weights equal the full-history run exactly (max |Δw| = 0).
  The first version of the split rule failed this test at nine of ten dates.
* **Short history.** Weights from the last 400 / 500 / 750 / 1000 sessions equal the
  full-history run on the last 20 rows. With 300 sessions they can differ (the 250-session
  listing rule leaves too little room): the live runner should feed ≥ 500.
* **Permutation placebo.** Fund i trading on fund j's signal: gross Sharpe 0.06 ± 0.19 over
  20 permutations (max 0.32).
* **vectorbt.** `Portfolio.from_orders`, target-percent orders at the close, 10 bp fees:
  2.69 IS / 2.47 OOS against 2.71 / 2.49; daily return correlation 0.9988.

## 8. What is not established

1. **Out-of-sample purity.** The threshold family was designed after the rank family's OOS
   cost ladder had been seen. Its parameters were chosen on IS and the family holds across
   all 48 cells (rank correlation 0.91), but the OOS sample was not untouched when the
   family was conceived. 188 configurations were scored in total (140 + 48), plus 28 event-
   study cells and 12 neighbours. Deflated Sharpe probability on the OOS number with 188
   trials is 1.00; the t-statistics are 5.6-7.9.
2. **Survivorship.** Dead funds are missing. The signal is a deviation from a fund's own
   recent discount, so being alive in 2026 does not select on it directly. The cases that
   would hurt and are absent: shorts opened after a liquidation or open-ending announcement
   (the discount jumps narrower and keeps narrowing). At a ~4 % short weight and a further
   2-3 % of narrowing, each costs about 10 bp of capital; five to eight a year would be
   0.5-0.75 %/yr against 7.3 %/yr net OOS. That is an estimate, not a measurement.
3. **Fills.** The backtest trades at the official close for a flat 10 bp. A market-on-close
   order in a fund with a thin closing auction pays about the half-spread; the true figure
   for these names is somewhere between 4 and 15 bp and is the main uncertainty. Nothing
   here models borrow availability.
4. **Capacity.** Not a scalable edge. It suits a small book.

## 9. Variations that did not earn a place

* Discount *level* sorts (the classic Pontiff signal): 1.0 IS / 0.9-1.0 OOS at 10 bp —
  positive, but a third of the z-score books.
* 5- and 21-session discount *changes*: strong gross (OOS 2.5-4.9), eaten by turnover
  (hysteresis `chg5` −0.41 OOS net).
* Daily-rebalanced quantile books: the highest gross Sharpe (up to 6.6 OOS) and the worst
  net (OOS mean 0.30, min −2.91).
* Fixed-interval rebalancing (every 10 or 21 sessions): OOS 0.0-1.9, mean 1.0; dominated by
  hysteresis.
* z-score thresholds instead of percent thresholds: 1.42 vs 1.94 OOS on average at 10 bp,
  0.28 vs 1.17 at 20 bp —
  a 2-sigma move in a fund whose discount barely moves is too small to pay four sides.

* **Fixed size per name instead of equalised sides** (`12_sizing_variant.py`, decided on IS
  only). A third of the turnover is re-sizing: 4,277 round trips earn 134-187 bp each against
  their group (hit rate 73-77 %), but equalising the sides re-trades every position when one
  arrives or leaves. A fixed 3 % per name cuts turnover from 21.0× to 10.8× and lifts IS
  from 2.71 / 2.20 to 2.82 / 2.50 (10 / 20 bp); OOS 2.17 / 1.77 against 2.49 / 1.71. Not adopted:
  the book stops being dollar-neutral (mean |net| 8 % of capital, up to 39 %), which is
  a different risk from the one tested everywhere else in this report.

## 10. Files

`fetch_cef.py` (universe + panel) · `cef_universe.csv` (snapshot) · `cef_lib.py` ·
`01_data_checks.py` · `02_signal_ic.py` · `03_grid.py` · `04_stress.py` (stress of the rank book) · `05_spreads.py` · `06_cost_robust.py` · `07_selected.py` · `08_lookahead_check.py` ·
`09_concentration_vbt.py` · `10_figures.py` · `12_sizing_variant.py` · `strategy.py` (`11_round_trips.csv` lists every round trip). Run outputs (`*.out.txt`) and CSVs sit next to the
scripts.
