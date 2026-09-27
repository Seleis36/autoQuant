# taker-flow-imbalance — Binance taker-buy share as a cross-sectional alt signal

**Date:** 2026-09-28 · **Asset class:** crypto-alts · **Status:** Failed

## 1. Idea

Anastasopoulos, Gradojevic, Liu, Maynard & Tsiakas ("Order flow and cryptocurrency returns",
*J. Financial Markets* 2026) find that signed order flow carries permanent price information in
crypto. Binance publishes a free proxy for it in every kline: the quote volume bought by takers.
Hypothesis: across the liquid alts, coins with net aggressive buying over the last k days
(taker-buy share above 50 %, or above their own norm) keep outperforming, and returns that
order flow does not support reverse (Llorente-Michaely-Saar-Wang). This is a different data
source from anything tried in this asset class before, and the idea is uncorrelated with BAB
by construction.

## 2. Data

* New shared fetcher `code/crypto-alts/shared/venues.py`: Binance spot `<COIN>USDT` 1d klines
  (REST, with a `data.binance.vision` fallback for delisted pairs) → `data/BINANCE_<COIN>USDT_1d.parquet`,
  77 of 78 candidates (no BSV). Fields: QuoteVolume, TakerBuyQuote, Trades, Volume, OHLC.
  The same module fetches Coinbase and Upbit daily candles for the next ideas.
* Bar D covers [D, D+1) UTC, closing at the same instant as the yfinance crypto close stamped D,
  so a signal from bar D is tradable at that close; `research_lib.backtest_xs` shifts weights by
  one bar. P&L on yfinance closes (what the book trades).
* Universe: `study.load()` = the PIT top-20 by trailing 90-day median yfinance USD volume
  (≥ 120 closes, ≥ $5M), unchanged from `xs-momentum-neutral`, intersected with Binance
  coverage (avg 18 names; 7.7 in 2018, 16 in 2019, 19-20 from 2020).
* Split fixed in advance and shared with the earlier study: IS 2018-2022, OOS 2023-2026-09,
  10 bp/side, ANN 365.

## 3. What was tried

| Stage | Script | Cells | What |
|---|---|---|---|
| IC screen 1 | `01_ic.py` → `ic_01.csv` | 36 features × 5 horizons | taker-buy share level `tbr_k` (k = 1…60), vs own 180d history (`tbrz`, `tbrdm`), flow orthogonal to same-window return (`flowres`), avg USD trade size, plain return control |
| IC screen 2 | `02_ic_activity.py` → `ic_02.csv` | 40 × 3 | trade size in USD and base units, trade count, Binance and yfinance volume vs own history, Binance share of volume, price vs own history; Fama-MacBeth partials with price and return controls |
| Books | `03_books.py` → `books_03.csv` | 40 | 5 signal families × k ∈ {3,7,14,30} × hold ∈ {7,14}; dollar-neutral linear-rank weights |
| Diagnostics | `04_diag.py` → `diag_04.log` | — | rank persistence, per-coin average taker share IS/OOS, frozen fixed-effect book |

## 4. Results

**ICs (daily Spearman vs forward XS-demeaned return, NW t).**
* Raw taker-buy share predicts in-sample and not out-of-sample: `tbr7` → 7d IC 0.049 (t 3.8) IS,
  0.009 (t 0.7) OOS; `tbr30` → 30d 0.078 (t 3.3) IS, 0.004 OOS. Every k shows the same collapse.
* Measured against each coin's own history (`tbrz`, `tbrdm`), the signal is zero in both halves (|IC| < 0.02, |t| < 2).
  The part of flow that is *news* has no predictive content at 1-30 days.
* Flow orthogonal to returns (`flowres`): IS ≈ 0, OOS 0.01-0.02 (t ≤ 2.2 at one cell). Not stable.
* One-day reversal (`ret1` → 1d, IC −0.03 to −0.04, t −6 in both halves) is real but untradable at
  10 bp: the earlier study measured 70-340×/yr turnover for it.

**Costed books (40 configs; median full 0.38 / IS 0.55 / OOS −0.03).**

| Family (hold 14) | k=3 | k=7 | k=14 | k=30 |
|---|---|---|---|---|
| raw `tbr` IS / OOS | 1.44 / −0.36 | 1.34 / −0.36 | 1.40 / −0.18 | 1.31 / −0.32 |
| `tbrdm` (vs own history) | 0.59 / −0.04 | 0.62 / −0.03 | 0.73 / 0.12 | 0.77 / −0.08 |
| `flowres` | 0.34 / 0.08 | 0.54 / 0.07 | 0.19 / 0.31 | 0.68 / 0.36 |
| Llorente unsupported-return fade | −0.51 / −0.40 | −0.45 / −0.51 | −1.12 / −0.33 | −1.01 / 0.32 |
| flow-supported momentum | 0.72 / −0.16 | 0.52 / 0.16 | 0.88 / 0.09 | 0.67 / −0.42 |

The best OOS cell (`flowres7|h7`, 0.66) has IS 0.27, and the best full-sample cell (`tbr14|h14`,
0.82) is −0.18 OOS. No cell is ≥ 0.5 in both halves apart from `flowres30` (0.54-0.68 IS /
0.36-0.46 OOS, full 0.51-0.56). That is one neighbourhood out of 40, and its IS-selected best
would be a raw `tbr` cell that fails.

**Why raw taker share looked good in-sample.** It is mostly a coin fixed effect. The cross-sectional
rank of 30d taker share has autocorrelation 0.33 at 90 days and 0.20 at a year. Through 2018-22
the highest average taker share belonged to TRX, BNB, EOS and XLM, and the lowest to WAVES, OMG,
FIL, ATOM and LINK. A book on the *frozen 2018-20 average* taker share earns 1.42 in 2021-22 and
−0.05 in 2023-26. Once the IS winners (BNB, TRX) stopped leading, their taker bias went with
them (BNB 0.0137 → −0.0002). The mechanism is probably market-maker and rebate programmes and
quote-currency habits, not information.

**By-product worth following up.** In IC screen 2, *abnormal activity* (60-day vs prior-180-day
yfinance volume, Binance volume and trade count) predicts lower returns in both halves: `yvol60` →
30d IC −0.072 (t −2.8) IS, −0.055 (t −2.1) OOS. It survives Fama-MacBeth controls for price-vs-history
and past return (`qvol60` partial t −3.4 full). Average USD trade size looked predictive, but it
is a price-level artefact: in base units its IC is ≈ 0 or positive. The volume effect is a separate
mechanism (attention/speculative overpricing) and is taken up as its own idea,
[`volume-attention`](../volume-attention/).

## 5. Verdict

**Failed.** Taker-buy order flow on Binance spot has no out-of-sample cross-sectional predictive
power for the liquid alts at 1-30 day horizons once the persistent coin-level bias is removed.
The in-sample 1.3-1.4 Sharpe of the raw level comes from a coin fixed effect that did not survive
into 2023-26. Variants evaluated: ~300 IC cells and 40 costed books. Nothing is deployable.

## 6. Files

* `code/crypto-alts/taker-flow-imbalance/`: `00_fetch.py`, `common.py`, `01_ic.py`, `02_ic_activity.py`,
  `03_books.py`, `04_diag.py`, CSV/log outputs.
* Shared: `code/crypto-alts/shared/venues.py` (Binance/Coinbase/Upbit daily candles),
  `code/crypto-alts/shared/study.py` (loader, fixed splits, bear windows, summary row, BAB reference).
