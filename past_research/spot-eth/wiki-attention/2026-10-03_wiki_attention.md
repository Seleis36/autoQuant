# wiki-attention — investor attention (Wikipedia pageviews, market activity) as a predictor of spot ETH

**Date:** 2026-10-03
**Asset:** spot ETH/USDT (Binance daily bars, 00:00 UTC), long/flat, 10 bp/side
**Status:** **Failed** — the Liu–Tsyvinski attention effect replicates in 2017–2023 (partial IC up to +0.31 at 30 days, t 4.1) and is absent from 2024 on; no rule beats the trend filter.

| 2018-09 → 2026-10, 10 bp/side | full | IS ≤ 2023 | OOS 2024+ | alpha t vs TF, OOS |
|---|---|---|---|---|
| vol-scaled B&H | 0.74 | 0.90 | 0.45 | |
| live `eth-trend-filter` | 1.14 | 1.12 | 1.18 | |
| attention above its 1-year norm × vol (IS-best) | 0.89 | 1.27 | 0.26 | −0.66 |
| Liu–Tsyvinski form (7 d vs prior 28 d > 0) × vol | 0.65 | 0.89 | 0.13 | −0.92 |
| TF OR attention above norm | 1.09 | 1.27 | 0.76 | −0.69 |

## 1. Idea

Liu & Tsyvinski (*Risks and Returns of Cryptocurrency*, RFS 2021) find that abnormal Google
search volume predicts crypto returns positively over the next one to six weeks, for Bitcoin,
Ethereum and XRP: new attention brings new buyers. Wikipedia pageviews are the keyless,
never-revised, daily counterpart (Google Trends is rescaled per query window and is not
point-in-time). Features follow the paper — this week's attention against the previous four
weeks — plus longer norms, a crypto-wide composite and ETH's share of attention against BTC.

## 2. Data and timing

- Wikimedia REST pageviews API, `en.wikipedia`, human traffic only, 2015-07-01 → 2026-10-02:
  Ethereum, Bitcoin, Cryptocurrency, Vitalik Buterin (plus six more articles cached for later
  use). Cache `data/WIKI_PAGEVIEWS_d.parquet`, fetcher `fetch_wiki.py`.
- The count for UTC day D is published during D+1, so every feature is lagged one full day.
- 7-day means remove the weekday pattern in traffic. Logs throughout.
- IS 2017-09 → 2023-12, OOS 2024-01 → 2026-10.

## 3. Screen (`exp01_screen.py`) — 19 features × 4 horizons

| partial IC after trend controls (HAC t) | h = 7 IS | h = 7 OOS | h = 30 IS | h = 30 OOS |
|---|---|---|---|---|
| ETH views, 7 d vs prior 28 d (L&T) | +0.01 (−0.1) | −0.02 (−0.8) | +0.15 (2.4) | −0.00 (−0.1) |
| ETH views, 7 d vs 90 d | +0.08 (2.1) | +0.03 (−0.2) | +0.21 (3.7) | +0.14 (1.1) |
| ETH views, 7 d z-score vs 365 d | +0.14 (3.2) | −0.02 (−0.6) | **+0.31 (4.1)** | −0.06 (−0.6) |
| ETH views, 30 d vs 180 d | +0.11 (3.6) | +0.00 (0.0) | +0.22 (4.6) | −0.03 (−0.2) |
| BTC views, 7 d z-score vs 365 d | +0.10 (3.5) | +0.05 (0.3) | +0.25 (4.9) | +0.09 (0.6) |
| "Cryptocurrency" views, 7 d vs prior 28 d | +0.04 (0.7) | −0.04 (−1.2) | +0.15 (2.5) | **−0.19 (−2.2)** |
| ETH minus BTC views, 7 d z vs 365 d | −0.01 (−0.8) | −0.07 (−0.4) | −0.05 (−0.3) | −0.08 (−1.1) |

| | h = 1 | h = 7 | h = 14 | h = 30 |
|---|---|---|---|---|
| IS \|t\| ≥ 2, raw / partial | 6 / 6 | 8 / 9 | 9 / 9 | 12 / 13 |
| of which \|t\| ≥ 2 with the same sign OOS | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| IS→OOS Spearman of t, raw / partial | +0.30 / +0.51 | 0.00 / +0.18 | −0.28 / +0.06 | +0.06 / +0.09 |

- The paper's result is there in sample: 13 of 19 features have a partial \|t\| ≥ 2 at 30 days,
  all positive. The effect is not a trend proxy — the partial ICs are *larger* than the raw ones.
- None survives out of sample. The largest OOS \|t\| with the IS sign is 1.1.
- ETH's share of attention says nothing about ETH or about ETH/BTC (against the pair: IS→OOS
  rank correlation of t-stats −0.22 to −0.60).

**Where the in-sample effect lives** (`exp02`, yearly IC at h = 30, partial):

| | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|---|---|---|
| ETH views z 7/365 | −0.18 | −0.43 | +0.38 | +0.23 | +0.06 | +0.30 | −0.03 | −0.30 | +0.21 |
| BTC views z 7/365 | −0.25 | −0.58 | +0.45 | +0.40 | +0.15 | +0.31 | +0.58 | −0.22 | −0.31 |
| ETH views 30/180 | −0.23 | −0.42 | +0.38 | +0.01 | +0.19 | +0.22 | +0.45 | −0.52 | +0.62 |

Negative in 2018–19, strongly positive in the 2020–21 retail bull market, unstable since. The
pooled IS t-stat is the 2020–21 cycle.

**The proxy itself is fading.** Mean daily views of the Ethereum article: 6,115 (2017), 7,775
(2021), 3,292 (2022), 1,461 (2025), 768 (2026). The marginal buyer in 2024–26 arrives through
ETFs and treasury companies, not through an encyclopedia.

## 4. Rules and re-framing (`exp02_rules_and_market_attention.py`)

A-priori rules, 2018-09 → 2026-10:

| | full | IS | OOS | MaxDD | turn | alpha t vs TF full / IS / OOS |
|---|---|---|---|---|---|---|
| vol B&H | 0.74 | 0.90 | 0.45 | −54% | 4× | |
| TF_live | 1.14 | 1.12 | 1.18 | −48% | 18× | |
| ETH 7 d vs prior 28 d > 0 × vol (L&T) | 0.65 | 0.89 | 0.13 | −39% | 16× | −0.23 / 0.53 / −0.92 |
| ETH 7 d vs 90 d > 0 × vol | 0.68 | 0.81 | 0.41 | −35% | 10× | −0.04 / 0.33 / −0.51 |
| ETH z 7/365 > 0 × vol | 0.89 | 1.27 | 0.26 | −46% | 5× | 0.95 / 1.87 / −0.66 |
| ETH 30 d vs 180 d > 0 × vol | 0.82 | 1.06 | 0.32 | −39% | 4× | 0.57 / 1.15 / −0.73 |
| composite 7 vs 28 > 0 × vol | 0.35 | 0.66 | −0.32 | −58% | 14× | −1.13 / −0.16 / −1.58 |
| TF AND ETH 7 vs 90 > 0 | 0.92 | 0.90 | 0.99 | −39% | 11× | 0.33 / 0.17 / 0.42 |
| TF AND ETH z 7/365 > 0 | 0.98 | 1.10 | 0.71 | −37% | 8× | 0.75 / 1.02 / −0.21 |
| TF OR ETH z 7/365 > 0 | 1.09 | 1.27 | 0.76 | −52% | 16× | 0.48 / 1.74 / −0.69 |
| TF veto ETH z 7/365 > 2 (mania) | 1.11 | 1.09 | 1.15 | −48% | 18× | 0.31 / 0.24 / 0.23 |
| TF × (0.5 + 0.5·1{7 vs 90 > 0}) | 1.12 | 1.09 | 1.19 | −42% | 14× | 0.33 / 0.17 / 0.42 |

**Attention measured in the market.** If Wikipedia stopped being where attention shows, the
trade tape might still show it: abnormal Binance trade count, quote volume and average trade
size (small trades = retail), plus the taker-buy share; 14 features × 3 horizons.

- Trade count and volume: no IS \|t\| ≥ 2 raw; OOS signs opposite (IS→OOS rank correlation of
  t-stats −0.75 / −0.64 / −0.58 at h = 1 / 7 / 30).
- Average trade size: smaller trades precede higher returns in IS (partial t −2.8 at h = 7),
  same sign but t −1.1 OOS.
- 7 d taker-buy share: IC −0.17 IS (t −2.7) and **+0.18** OOS (t 1.8) at h = 30 — a sign flip.
- Rules: trade count above its 90 d norm × vol 0.82 / 0.95 / 0.58; as a gate on TF 1.15 / 1.21 /
  1.03 against TF 1.14 / 1.12 / 1.18. Nothing added.

## 5. Verdict

**Failed.** Abnormal attention predicted ETH in the retail-driven cycle of 2020–21, which is the
sample the literature was written on. It has no out-of-sample content: zero of 19 Wikipedia
features and zero of 14 market-activity features keep a \|t\| ≥ 2 after 2023, and every costed
rule falls to 0.1–0.4 OOS against 1.18 for the trend filter.

Binding constraint: the population of marginal buyers changed. A usable attention series today
would have to measure the channels they use (ETF creations, treasury-company announcements), and
those start in mid-2024.

Configurations evaluated: 19 Wikipedia features × 4 horizons × {raw, partial, vs ETH/BTC};
14 market-activity features × 3 horizons × {raw, partial}; 16 costed rules.

## 6. Files

- `code/spot-eth/wiki-attention/fetch_wiki.py` — fetcher + cache (`data/WIKI_PAGEVIEWS_d.parquet`)
- `exp01_screen.py` (+ `exp01_raw_ic.csv`, `exp01_partial_ic.csv`), `exp02_rules_and_market_attention.py`
