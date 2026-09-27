# korea-premium-xs — coin-specific kimchi premium as a cross-sectional alt signal

**Date:** 2026-09-28 · **Asset class:** crypto-alts · **Status:** Failed

## 1. Idea

Korean retail is a large, capital-controlled pool of alt demand. When it piles into one coin,
that coin trades at a premium on Upbit over the global price, beyond the market-wide kimchi
premium. Pre-registered hypothesis: the *coin-specific* premium (the Upbit/Binance log price ratio
minus the same-day cross-sectional median, which cancels USDKRW, the USDT basis and the market-wide
kimchi premium) marks retail froth, and those coins underperform globally afterwards (contrarian,
negative sign). A second measure is Upbit's share of the coin's volume vs its own history (Korean
attention). The ETH-only time-series version (`spot-eth/kimchi-froth`) failed; this is the
cross-sectional form, which the ETH study could not test.

## 2. Data and setup
* `code/crypto-alts/shared/venues.py::upbit_daily` → `data/UPBIT_KRW<COIN>_d.parquet` (56 of 78
  candidates; the Upbit API only serves currently listed KRW markets, so delisted pairs and LTC/EOS
  are missing). Upbit daily candles are UTC-aligned (close at D+1 00:00 UTC = yfinance close D).
* Coverage in the PIT top-20: 5 names/day in 2018, 9-15 afterwards. Books trade only on days with
  ≥ 6 names. |XS premium| > 30 % is masked as halted deposits / bad prints. 5-95 % range −36…+44 bp.
* PIT top-20 universe, IS 2018-22 / OOS 2023-26, 10 bp/side, BTC-beta-hedged linear-rank books.

## 3. Results

**IC screen (`01_ic.py` → `ic_01.csv`, 20 features × 5 horizons).**
* Premium level, contrarian as hypothesised, **in-sample only**: `lvl14` → 7d IC −0.060 (t −3.2) IS
  vs +0.004 OOS, and `lvl7` → 14d −0.062 (t −3.0) IS vs +0.009 OOS. At 1 day the OOS sign is even
  positive (`dm1` +0.020, t 2.7).
* Korean volume share vs own history: negative in both halves but weak (1d −0.032 IS / −0.015 OOS;
  30d −0.02 IS / −0.06 OOS, t −0.5 / −1.9).

**Costed books (`02_books.py` → `books_02.csv`, 27 books).**

| Family | median full / IS / OOS | best cell |
|---|---|---|
| contrarian premium level | 0.09 / 0.22 / 0.06 | `contra_prem14|h14` 0.37 / 0.44 / 0.24 |
| Korean-share surge | 0.01 / 0.01 / 0.04 | `krshare_surge30|h14` 0.12 / 0.06 / 0.21 |
| composite | 0.13 / 0.21 / 0.11 | `composite14|h7` 0.28 / 0.38 / 0.13 |

Every contrarian book loses −2 to −4 Sharpe in the Apr-Jul 2021 bear. During that crash Korean
buyers paid up for the coins that then held up best, which is the opposite of froth. The share
surge has ρ 0.12 with the `volume-attention` book: it is a noisier, Korea-only version of the same
attention effect.

## 4. Verdict

**Failed.** The coin-specific kimchi premium behaved like a contrarian signal in 2018-22 (t ≈ −3)
and carries nothing in 2023-26. No book is above 0.4 full or 0.3 OOS. Variants: 100 IC cells + 27 books.

## 5. Files
`code/crypto-alts/korea-premium-xs/`: `00_fetch.py`, `common.py` (`premium_panel`), `01_ic.py`,
`02_books.py`, `ic_01.csv`, `books_02.csv`, `books_02_nets.parquet`.
