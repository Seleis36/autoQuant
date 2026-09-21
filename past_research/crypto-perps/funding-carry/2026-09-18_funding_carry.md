# Funding carry — long spot / short perp on Binance (`funding-carry`, crypto-perps)

**Date:** 2026-09-18 · **Status: Working** against "Sharpe ≥ 3" under the repo's daily-return
convention, with a horizon caveat that is the most important line in this report (§6).

## 0. Why this idea, and why it is in `crypto-perps`

The brief for this session was "any data, any asset; find a strategy with Sharpe ≥ 3, strictly".
Every directional idea in this repo tops out at net Sharpe 1.2–1.6 (spot-btc `weekday-trend`
1.60, `bult` 1.48, `coinbase-premium` 1.48, rates `treasury-flow-calendar` 1.26, crypto-alts
`xs-momentum-neutral` 1.22), and nothing cross-sectional on daily bars has cleared 2 at
realistic costs. A Sharpe of 3 on a single directional series needs an information coefficient
no daily signal here has shown. The one family where a Sharpe of that size is *structurally*
available is carry that is hedged against the underlying: the return is a cash-flow (funding),
the residual risk is a bounded basis, and the two are nearly uncorrelated with the coin's price.

The Binance perpetual funding mechanism is the cleanest such carry: every 8 hours longs pay
shorts `rate × notional` (or the reverse when the rate is negative), and the rate is a clamped
average of the perp's premium to the spot index over the preceding 8 hours. Since 2020 the BTC
rate has been positive 86 % of the time and averaged 11.7 %/year (ETH 13.9 %). The
long-spot/short-perp position ("cash-and-carry", the trade Ethena and every basis desk run)
collects that with zero delta. He, Manela, Ross & von Wachter (2022, *Perpetual Futures
Pricing*) and Schmeling, Schrimpf & Todorov (2023, BIS WP 1087 *Crypto Carry*) document the
premium and its crash behaviour; the second paper is explicit that the unhedged carry crashes
while the hedged one does not.

The mechanism is a perp-funding trade, so it lives under `crypto-perps` (that index header
reads "funding & basis") rather than `spot-btc`, even though the long leg is spot BTC/ETH. The
`crypto-perps` index was empty before this report.

## 1. Data

All from `data.binance.vision` via `code/crypto-perps/funding-carry/fetch_data.py`, which reuses
the transport helpers of `code/shared/fetch_binance_vision.py`:

| Store | Content | Span |
|---|---|---|
| `data/bars/<SYM>_PERP/1h/` | USD-M perp 1h klines (new `_PERP` suffix so they never collide with the spot partitions of the same symbol) | BTC 2019-09, ETH 2019-11, BNB/SOL/XRP/ADA/DOGE/LINK 2020-21 → 2026-09 |
| `data/bars/<SYM>/1h/` | spot 1h klines for the alts (BTC/ETH spot resampled from the 1m store) | same |
| `data/<SYM>_fundingRate.parquet` | every funding settlement (`last_funding_rate`, `funding_interval_hours`) | **2020-01-01 → 2026-08-31** (the archive's fundingRate dataset starts 2020-01) |

Checks: BTC and ETH have exactly 3 settlements per day on every day, all at 8h intervals; the
sample is truncated at the last funding stamp (2026-08-31 16:00) so the tail does not carry
zero funding. The pre-existing `data/BTCUSDT_premium_1h.parquet` (premium index) correlates
0.89 with the perp-close/spot-close basis computed here and has the same mean (−1.3 bp) and
std (6.2 bp), which cross-validates the perp klines.

## 2. P&L engine (`carry_lib.py`)

Hourly bars, UTC, bar-open stamps. Position = +1 unit spot, −1 unit perp. Return on the
notional of one leg over hour t:

```
r_t = (S_t − S_{t−1})/S_{t−1} − (P_t − P_{t−1})/S_{t−1} + f_t · P_t / S_{t−1}
    ≈ −Δbasis_t + f_t,       basis = P/S − 1
```

with `f_t` the rate settled at stamp t (00/08/16 UTC), zero elsewhere. Weights decided at the
close of hour t apply from t+1. Funding settled at t is *known* at t (it is computed from the
premium over [t−8h, t]) and is used as a signal only for later hours. Costs: 10 bp spot taker +
5 bp perp taker + 5 bp slippage = **20 bp per unit of notional switched**, both legs together.
Return on *capital* = one-leg return × `1/(1+1/L)` for perp leverage L; at L = 1 that is 0.5.

Sharpe convention: daily returns (hourly compounded to calendar days), annualised √365, as in
`research_lib.perf_stats` and every other report here. §6 shows what happens at other horizons.

## 3. exp01 — BTC alone: always-on vs timing rules

`exp01_btc_carry.py`, 2020-01 → 2026-08, one-leg notional, 20 bp/switch. IS = 2020-22,
OOS = 2023-26, fixed before any result was seen.

| Rule | Sharpe full / IS / OOS | CAGR | MaxDD | switches/yr |
|---|---|---|---|---|
| **always on** | **8.78 / 9.34 / 12.57** | 12.4 % | −2.1 % | 0.15 |
| trailing-3 mean > 0 | 0.36 / 2.65 / −2.22 | 0.8 % | −28 % | 60 |
| trailing-9 mean > 0 | 4.85 / 6.19 / 3.54 | 8.6 % | −4.7 % | 20 |
| trailing-21 mean > 0 | 6.33 / 7.29 / 6.29 | 10.4 % | −2.8 % | 11 |
| hysteresis k9, in > +1 bp, out < −1 bp | 8.56 / 8.97 / 12.21 | 11.9 % | −0.9 % | 1.3 |
| hysteresis k9, in > 0, out < −1 bp | 8.59 / 9.05 / 12.57 | 12.3 % | −1.8 % | 2.5 |
| basis(8h mean) > 0 | −0.22 / 0.77 / −1.75 | −0.5 % | −20 % | 53 |

29 rules in total (5 trailing windows × 3 thresholds, 8 hysteresis pairs, 3 basis thresholds).
None beats always-on. Every rule that switches more than a few times a year is destroyed by the
20 bp switch cost against ~3 bp/day of funding; the slow hysteresis rules match always-on
because BTC funding is almost never negative for long. The basis sign is not a useful predictor
of the next settlement once costs are charged. ETH (same script): always-on **7.58 / 8.45 /
11.73**, CAGR 14.6 %, MaxDD −1.8 %. BNB: always-on **−0.03** — BNB funding averages zero (the
coin is borrowed as collateral, so shorts pay), and a trailing-3 rule is needed to make it
positive (3.30 / 4.76 / 1.48). This is why the spec is BTC+ETH only; see §5 for the alts.

## 4. exp03 — validation of BTC+ETH always-on (one-leg notional)

`exp03_validate.py`. Sharpe 8.63 full, CAGR 13.5 %, vol 1.47 %, MaxDD −1.49 %, hit rate 81 %,
NW t 7.28, skew +1.4, kurtosis 41. By year: 2020 9.3, 2021 14.5, **2022 3.6**, 2023 15.4,
2024 16.9, 2025 17.0, 2026 6.5. Worst day −1.17 % (2020-03-13, perp at a −2 % discount for
hours), then −0.32 % (2022-09-15, the Merge), −0.29 %, −0.28 % (2021-05-19). Worst week −0.52 %.
Stress windows: Covid −42 bp, May-2021 +37 bp, Luna +6 bp, FTX −28 bp, Aug-2024 +5 bp,
Feb-2025 +5 bp. Block bootstrap (10-day blocks) Sharpe 5/50/95 %: 7.48 / 8.80 / 9.94.
Decomposition (BTC, bp/yr): funding 1721 / 3065 / 416 / 786 / 1197 / 512 / 174 (2020→2026),
basis change −19 / +37 / +9 / −12 / +11 / +4 / +1. **All of the return is funding; the basis
leg is noise that nets to zero.** Beta to BTC −0.004, corr −0.15.

Return on capital by perp leverage: L=1 CAGR 6.6 % vol 0.74 %; L=2 8.8 %; L=3 10.0 %; L=5
11.2 % (Sharpe identical). Margin stress: the largest intra-month rally was +79 % (Feb 2021),
so L=2 with monthly margin resets would have been liquidated twice and L=3 eleven times.
**L=1 with the spot leg posted as collateral is the only configuration this report stands
behind.**

## 5. exp02 — multi-coin, equal weight and cross-sectional

`exp02_multicoin.py`, coins with paired spot+perp+funding data: BTC, ETH, BNB, SOL, XRP, ADA,
DOGE, LINK (the last two are discussed in §5a). Five rules per coin: always-on, hysteresis on the
9- and 21-settlement trailing mean (in above +1 bp / +0.5 bp, out below −1 bp / −0.5 bp),
21-mean > 0, 3-mean > 0. One-leg notional, 20 bp/switch.

**Per coin (Sharpe full / IS / OOS, always-on → best slow rule):**

| coin | always-on | best slow rule | note |
|---|---|---|---|
| BTC | 8.80 / 9.34 / 12.65 | k21 hyst 8.65 | always-on best |
| ETH | 7.60 / 8.45 / 11.81 | k21 hyst 7.55 | always-on best |
| BNB | −0.03 / 1.12 / −2.17 | k21 > 0 3.42 / 5.09 / 1.20 | funding ≈ 0; OOS weak either way |
| SOL | −0.04 / −0.39 / 2.63, **vol 12.5 %, MaxDD −42 %** | k21 hyst 3.34 / 3.65 / 4.60 | basis hit **−24 %** on 2022-11-09 (FTX) |
| XRP | 3.42 / 3.81 / 7.47 | k21 hyst 6.58 / 7.83 / 7.18 | basis −6.7 % on 2020-12-11 |
| ADA | 6.18 / 7.22 / 6.38 | k9 hyst 6.37 / 7.80 / 6.32 | |
| DOGE | 5.21 / 5.27 / 9.42 | k21 hyst 5.65 / 5.72 / 9.27 | basis +7.4 % in the Jan-2021 squeeze |
| LINK | 5.88 / 6.22 / 7.41 | k21 hyst 6.69 / 7.40 / 7.22 | MaxDD −6.0 %, the worst of the majors |

**Equal-weight baskets (Sharpe full / IS / OOS, CAGR on notional):** BTC+ETH always-on
**8.66 / 9.42 / 13.36**, 13.6 %; all-eight always-on 4.35 / 4.62 / 8.57, 10.9 %; all-eight
k21-hyst 7.85 / 8.93 / 10.27, 12.7 %; BTC+ETH+SOL k21-hyst 7.39 / 8.19 / 10.07, 12.5 %. Adding
alts never beats BTC+ETH: their extra funding is paid for with basis dislocations an order of
magnitude larger (BTC/ETH worst basis −2.6 %, 0.1 %/99.9 % quantiles ±0.2–0.4 %; SOL −24 %,
XRP −6.7 %). The hedged alt carry is exactly the "carry crash" of Schmeling et al.: on
2022-11-09 a long-spot/short-perp SOL position was marked −11 % in one hour and would have
been margin-called before the basis recovered.

**Cross-sectional top-n by trailing funding** (hold the n coins with the highest 9/21/63-
settlement mean funding, if positive, re-ranked at each settlement): every cell with k ≤ 21
is negative (top-1 k9 **−8.7**, top-3 k21 −2.0); k=63 top-3 is 2.45 full but −2.18 OOS.
Chasing the highest funding buys the coin whose premium is about to mean-revert and pays 20 bp
per rotation for it. Cost sensitivity for BTC+ETH always-on: 20 / 30 / 50 / 100 bp per switch →
8.66 / 8.63 / 8.56 / 8.29 (it barely trades); the slow hysteresis rules degrade faster (k21
hyst 8.58 → 6.12 at 100 bp).

Conclusion: the spec is BTC+ETH, always-on, no cross-section.

### 5a. DOGE and LINK

The two coins the fetch finished last. Both are ordinary large-cap perps with real funding, and
both behave like XRP/ADA rather than like SOL:

| coin | span | funding mean / % positive | always-on Sharpe full / IS / OOS | CAGR | MaxDD | basis min / max | basis 0.1 % / 99.9 % |
|---|---|---|---|---|---|---|---|
| DOGE | 2020-07-10 → 2026-08 | 12.4 %/yr / 82.1 % | 5.21 / 5.27 / **9.42** | 13.4 % | −2.2 % | −3.25 % / **+7.40 %** | −0.51 % / +0.56 % |
| LINK | 2020-01-17 → 2026-08 | 14.5 %/yr / 86.4 % | 5.88 / 6.22 / 7.41 | 14.6 % | **−6.0 %** | −2.76 % / +1.51 % | −0.45 % / +0.52 % |

Both earn more funding than BTC (11.8 %/yr) and neither has SOL's pathology — their 0.1 %
basis quantiles are −0.5 %, three times BTC/ETH's but seven times tighter than SOL's −3.4 %.
Yet both have a *lower* Sharpe than BTC or ETH, and for the same reason: the extra funding is
not large enough to pay for the extra basis variance. DOGE's basis reached **+7.4 %** during the
January-2021 retail squeeze — a long-spot/short-perp book is marked *against* a widening basis,
so that episode is a loss that funding took weeks to earn back. LINK's −6.0 % max drawdown is
the worst of any coin the spec would plausibly include, three times BTC's −2.1 %.

Adding them does not change the conclusion. The eight-coin always-on basket (4.35) and the
eight-coin k21-hysteresis basket (7.85) both remain below BTC+ETH always-on (8.66), and the
cross-sectional rules got *worse* with a wider universe, not better (top-3 k21 went from −0.8
on six coins to −2.0 on eight), because the extra coins are exactly the ones whose high
trailing funding precedes a basis reversion. **The spec stays BTC+ETH.**

## 6. exp05 — the Sharpe is horizon-dependent, and what the vol scaler does about it

Daily returns of the carry are positively autocorrelated (ρ₁ = 0.44, ρ₅ = 0.42, ρ₂₁ = 0.27)
because the funding level itself moves in regimes that last weeks. Aggregating the always-on
BTC+ETH returns before computing the Sharpe:

| horizon | daily | weekly | monthly | quarterly |
|---|---|---|---|---|
| Sharpe always-on | 8.65 | 4.33 | 2.47 | 1.59 |
| Lo (2002) q-adjusted daily | q=5: 5.05 | q=21: 2.86 | q=63: 1.91 | |
| hit rate | 81 % | 90 % | 94 % | **100 %** |

The strategy has no losing quarter in 27; the long-horizon variance is entirely *how much* it
earns (2021 months of +7 % vs 2025 months of +0.4 %). Sharpe penalises that symmetrically. A
strict reader could say the always-on version fails "Sharpe ≥ 3" at a monthly horizon.

The standard fix is to scale exposure to a constant risk budget. Grid (`exp05_horizon.py`):
EWM vol of the hedged P&L with halflife 7 d or 30 d, target 0.5 / 1 / 2 % ann. (one-leg
notional units), exposure `min(1, target/vol)` re-evaluated at funding stamps; plus scaling
by the inverse of the trailing funding level (k = 21 / 63 settlements, c = 0.5 / 1 / 2 bp), and
linear-in-funding sizing as a contrast.

| variant | Sh daily | Sh weekly | **Sh monthly** | ShM IS / OOS | CAGR (notional) | turnover/yr |
|---|---|---|---|---|---|---|
| always on | 8.66 | 4.33 | 2.47 | 2.79 / 3.72 | 13.6 % | 0.15 |
| voltgt hl7d 0.5 % | 8.63 | 5.21 | 3.23 | 3.19 / 3.24 | 1.9 % | 3.6 |
| voltgt hl7d 1 % | 9.23 | 5.60 | 3.48 | 3.19 / 3.74 | 4.1 % | 5.7 |
| voltgt hl7d 2 % | 10.22 | 5.85 | 3.62 | 3.56 / 3.74 | 7.9 % | 3.4 |
| voltgt hl30d 0.5 % | 10.74 | 6.10 | 3.72 | 3.58 / 3.81 | 2.2 % | 1.0 |
| voltgt hl30d 1 % | 10.85 | 6.16 | 3.76 | 3.58 / 3.86 | 4.6 % | 1.7 |
| **voltgt hl30d 2 %** | **10.75** | **5.89** | **3.55** | **3.63 / 3.48** | **8.0 %** | **1.3** |
| fundscale k21 1 bp | 4.37 | 3.53 | 2.33 | 2.22 / 2.40 | 3.7 % | 15.5 |
| fundscale k63 1 bp | 7.52 | 5.35 | 3.64 | 3.22 / 4.10 | 5.4 % | 7.2 |
| linear in funding k21 | 5.61 | 2.64 | 1.50 | 2.12 / 1.11 | 8.4 % | 10.8 |

All six vol-target cells clear 3 at the monthly horizon in both halves; the choice among them
is return (2 % target keeps the most). Inverse-funding scaling works too but with ten times the
turnover. Sizing *up* with funding is the wrong direction (1.50). The scaler is not a signal:
it cuts exposure in 2020-21 when both funding and basis noise were extreme, and sits at the
cap from 2023-08 onward (see `drawdown_exposure.png`). Its cost is half the CAGR.

## 7. exp06 — the spec, validated (return on capital, L=1)

`exp06_final.py` runs `strategy.target_weights` with its defaults.

| | Full 2020-01→2026-08 | IS 2020-22 | OOS 2023-26 |
|---|---|---|---|
| Sharpe daily | **10.18** | 8.99 | 12.69 |
| Sharpe weekly | 5.74 | 5.39 | 6.34 |
| Sharpe monthly | **3.53** | 3.58 | 3.50 |
| Sharpe quarterly | 2.54 | 2.68 | 2.36 |
| CAGR | 3.88 % | 4.28 % | 3.55 % |
| Vol | 0.37 % | 0.47 % | 0.28 % |
| MaxDD | −0.35 % | −0.35 % | −0.26 % |
| hit rate (daily) | 80 % | 77 % | 83 % |
| NW t | 9.9 | 6.6 | 7.7 |

Yearly return / daily Sharpe: 2020 5.7 % / 9.1; 2021 6.3 % / 17.6; **2022 0.9 % / 2.6**; 2023
3.4 % / 12.7; 2024 6.5 % / 16.9; 2025 2.6 % / 17.0; 2026 YTD 0.7 % / 6.7. Rolling 12-month
daily Sharpe min 2.54 (5th pct 3.57, median 12.6). Block-bootstrap daily Sharpe 5–95 %:
8.95–11.69. Monthly-return bootstrap 5–95 %: 3.09–4.24, P(> 3) = 0.97. Beta to BTC −0.001.
Turnover 0.64 units of capital per year; average one-leg exposure 0.41 (cap 0.50). Cost
sensitivity: 20 bp/switch Sharpe 10.18, 40 bp 9.50, 80 bp 7.96. Worst days −0.28 %
(2020-12-21), −0.15 %, −0.15 %, −0.10 % (2020-03-13), −0.10 % (2022-11-10).

There is no fitted parameter beyond the vol-target cell chosen in §6 (6 cells, all passing), so
a walk-forward would re-select the same rule; the rolling-window and bootstrap figures above
are the selection-free evidence.

## 8. What this is and is not

- **It is a yield, not an alpha.** 4 % a year on capital at L=1 (6.6 % always-on, ~11 % at
  L=5 if the operator accepts liquidation management). The Sharpe is high because the vol is
  0.4 %, not because the return is large. Funding has compressed: BTC 5 % on notional in 2025,
  3 % annualised in 2026.
- **The Sharpe depends on the horizon** (10.2 daily → 3.5 monthly → 2.5 quarterly). The repo's
  convention is daily; the honest single number for a carry with persistent levels is the
  monthly one, and that is the figure the acceptance block quotes alongside the daily one.
- **Risks the backtest cannot see** are the ones that matter: exchange counterparty risk on
  both legs, liquidation if the perp margin is not collateralised by the spot leg (a +79 %
  month is in-sample), auto-deleveraging of profitable shorts in a crash, changes to the
  funding cap/floor or interval, and fills at bar closes on both legs simultaneously. The
  −2 % perp discount on 2020-03-12 cost 1.2 % of notional in a day and is the shape of the
  tail.
- **It cannot be paper-traded in the current harness.** The venue book is long/flat spot; the
  simulated book fills against prices and has no funding cash-flow. A live run would show only
  the basis leg (Sharpe ≈ 0) and would falsely "fail" the backtest. Deployment needs a
  funding-aware ledger; that is the deployment agent's call and outside this PR.

## 9. Everything tried, in one list

1. BTC always-on cash-and-carry — **works** (8.78 daily).
2. 15 trailing-mean funding thresholds, 8 hysteresis pairs, 3 basis-sign rules on BTC — all
   ≤ always-on; the fast ones are strongly negative from switching costs.
3. ETH always-on — works (7.58). BNB always-on — dead (funding ≈ 0); needs a trailing rule.
4. Multi-coin (8 coins) equal weight and cross-sectional top-n by trailing funding — §5.
   No basket beats BTC+ETH; every cross-sectional cell with k ≤ 21 is negative. DOGE (5.21)
   and LINK (5.88) are real carries but below BTC/ETH and do not change the spec — §5a.
5. Exposure scaling: vol-target (6 cells, all lift the monthly Sharpe above 3), inverse-funding
   (works, high turnover), linear-in-funding (worse). Vol-target hl 30 d / 2 % chosen.
6. Perp leverage 1/2/3/5 and margin stress — only L=1 survives a Feb-2021 month without
   spot collateral.

## 10. Files

- report: this file
- spec + figures: `alphas/crypto-perps/funding-carry/2026-09-18_alpha_spec.md`, `equity.png`,
  `drawdown_exposure.png`, `yearly.png`, `horizon.png`, `decomposition.png`
- code: `code/crypto-perps/funding-carry/` — `fetch_data.py`, `carry_lib.py`, `strategy.py`,
  `exp01_btc_carry.py`, `exp02_multicoin.py`, `exp03_validate.py`, `exp04_figures.py`,
  `exp05_horizon.py`, `exp06_final.py`, result CSVs

## 11. Deployment review (PR #11, 2026-09-21) — merged as a research record, nothing deployed

The research is accepted as a complete, honest **Working** result: IS/OOS split declared before
the fact, costs charged at 20 bp per switch with a sensitivity to 80 bp, turnover stated, the
horizon dependence of the Sharpe disclosed in §6 rather than buried, and the variant count (29
timing rules, 6 vol-target cells, 6 funding-scaling cells, 8 coins, cross-sectional top-n)
accounted for with rolling-window and bootstrap evidence rather than a single best-of-N figure.
Nothing in it needs revising.

It is **not deployable in either book**, and no further research would change that — the
obstacle is the execution harness, not the alpha:

* **Neither quote source prices a USD-M perpetual.** `harness/live_lib.QUOTE_SOURCES` offers
  exactly three: `binance-testnet` and `binance-public` (both `/api/v3/ticker/price`, spot only)
  and `yahoo-daily` (the shared daily `data/` cache). There is no mark for the short leg.
  `MarketData(source="futures")` fetches real perp klines, but that is the *signal* path; no
  broker can hold or mark a perp position.
* **No broker accrues funding.** `LedgerBroker._execute` (`harness/live_lib.py`) and
  `SimPortfolioBroker.set_target_weights` (`harness/portfolio.py`) move quantity against price
  and charge `fee_bps`; there is no 8-hourly cash-flow anywhere in either ledger.
* Those two together are fatal *because all of this strategy's return is funding* — §7 shows the
  basis nets to approximately zero over the sample. A price-only paper book holding +1 spot and
  −1 perp would track the basis alone and report a Sharpe near zero. That would not be a failed
  strategy; it would be an unimplemented ledger misread as a result.
* The `venue` book is additionally long/flat spot only, so it cannot hold the short leg at all.

Deploying this needs a funding-aware perp book in `harness/` — a quote source on `fapi`, a
position that can be short a perp, and a ledger that credits `rate × notional` at 00/08/16 UTC —
plus the margin/collateral treatment §8 calls for. That is harness engineering, and it is the
one thing that would have to exist before this spec could be put to work. Until it does, the
verdict is `wontfix`: structurally undeployable here, not defective.

Two caveats an implementer would inherit from §8 and the spec, beyond the ledger itself: the
spot leg must be posted as collateral for the perp short (at L=1 without it, the +79 % month of
Feb 2021 liquidates), and the ~4 %/yr return on capital is a yield whose unmodelled risks —
exchange counterparty, auto-deleveraging, funding cap changes — dominate its 0.37 % modelled vol.
