# Perp/spot volume share — leveraged-speculation intensity (`perp-spot-volume-share`, crypto-perps)

**Date:** 2026-09-30 · **Status: Failed.**
- The cross-sectional contrarian level earns 1.38 IS and **0.07 OOS**, the textbook coin-fixed-effect
  decay.
- Own-history versions and the perp-minus-spot taker-flow differential are dead.
- The BTC time-series share has a small, *positive* partial IC in both halves, but the pre-declared
  rules do not beat inverse-vol.

## 0. Idea

The share of a coin's trading that happens on the levered perp rather than on spot measures leveraged
speculation. Baker & Stein (2004) and the lottery-demand literature say speculative demand overprices.

Hypothesis: coins with a high perp/spot volume share underperform. Trade it cross-sectionally,
β-neutral, on spot.

## 1. Data and set-up

- **Share:** s = log(perp quote volume / spot quote volume), both from Binance daily klines.
  - Perp: `data/BINANCE_<SYM>_PERP_1d.parquet`, fetched with `perp-listing-drift`.
  - Spot: `data/BINANCE_<BASE>USDT_1d.parquet`.
  - Bar D closes at the 00:00 UTC close where the weight is set, so the whole day is known.
- **Universe:** PIT top-20 of the 64 perps with ≥ 60 days of both volumes.
- **P&L:** yfinance spot, q30, β-neutral, 10 bp.
- **Split:** IS 2020-09 → 2022-12, OOS 2023+.
- Median share ranges from 1.2× (RUNE, VET, ONT) to 11× (MKR). BTC and ETH are 7.4–7.5×.

## 2. exp01 — cross-sectional screen (20 cells)

| cell | full | IS | OOS |
|---|---|---|---|
| **−raw, h7** (short high share) | 0.69 | **1.38** | **0.07** |
| −raw, h1 | 0.38 | 1.00 | −0.16 |
| −sm7 (7-day mean), h7 | 0.59 | 1.40 | −0.13 |
| −dm90 (own-history demeaned), h7 | 0.16 | 0.20 | 0.13 |
| −z90, h7 | 0.19 | 0.14 | 0.24 |
| −surge (7d vs prior 30d), h7 | −0.41 | −0.23 | −0.57 |
| every "+" cell | −0.1 … −1.8 | | |

- Contrarian IC7: raw 0.022 IS / −0.010 OOS; sm7 0.028 / −0.016.
- The time-varying versions have IC1 ≈ 0.02 IS (t ≈ 2) and ≈ 0 OOS.
- **This is the crypto-alts trap.** A raw level of a venue or flow feature works in 2020-22 and dies
  after, because it is a coin fixed effect.
  - The coins with low perp share in 2020-22 were old exchange-listed names (TRX, NEO, ONT, QTUM,
    VET) whose relative performance flipped.

## 3. exp02 — re-framings (declared before running)

**B. Leveraged-flow differential** (cross-sectional): d = perp taker-buy share − spot taker-buy
share, 7-day mean.

| cell | full | IS | OOS |
|---|---|---|---|
| −d raw | −0.48 | 0.12 | −1.14 |
| −d demeaned | −0.11 | 0.25 | −0.50 |
| +d raw | −0.12 | −0.53 | 0.30 |
| +d demeaned | −0.62 | −0.78 | −0.50 |

Contrarian IC7 is −0.027 IS and −0.012 OOS. Dead.

**A. Market-wide speculation as a BTC timer.** z = (7d-mean share − 365d mean) / 365d std, for
BTC's own share and for the universe aggregate.

| series | IC30 IS | IC30 OOS | partial IC30, controlling for SMA50 distance and mom30 (IS / OOS) |
|---|---|---|---|
| BTC share | **+0.131** | **+0.123** | **+0.152 / +0.126** |
| aggregate share | +0.140 | +0.075 | |
| BTC taker-flow differential | +0.112 | +0.032 | |

The sign is the *opposite* of the hypothesis: more perp speculation precedes *higher* BTC returns
over a month. The z is barely correlated with trend (−0.08 / −0.13).

| BTC rule, × inverse-vol (40 %, cap 1) | full | IS | OOS |
|---|---|---|---|
| inverse-vol alone (reference) | 0.71 | 0.04 | 1.10 |
| BTC share: flat if z > 1 | 0.47 | −0.29 | 0.91 |
| BTC share: flat if z < −1 | 0.59 | −0.02 | 0.93 |
| aggregate: flat if z > 1 / z < −1 | 0.41 / 0.66 | −0.22 / 0.48 | 0.78 / 0.75 |
| flow differential: flat if z > 1 / z < −1 | 0.38 / 0.48 | | |

No pre-declared rule beats inverse-vol alone.

**Artefact in the IS window.** Binance ran zero-fee spot BTC trading from July 2022 to March 2023.
BTC's perp/spot share fell from about 7× to 1.6× and then jumped to about 10× in April 2023. The
365-day z therefore carries the promotion through April 2024. The IS IC is contaminated, and only
the 2024+ IC (+0.12) is clean.

## 4. Verdict

**Failed.**
- The contrarian cross-sectional hypothesis is a fixed-effect illusion (1.38 → 0.07).
- The flow differential carries nothing.
- The one survivor points the other way: a small positive "speculation momentum" timing signal on
  BTC (partial IC ≈ +0.13). No rule was declared for it in advance, and the declared ones lose to
  inverse-vol.
- **Lead for a future spot-btc session:** test the positive BTC share signal with a pre-registered
  rule on 2024+ data only, where the zero-fee promotion is out of the window.

Variants: 20 (exp01) + 4 cross-sectional + 6 time-series rules + 3 IC series (exp02) = 33.

## 5. Files

```
code/crypto-perps/perp-spot-volume-share/common.py        loader (perp/spot quote volume, share, PIT universe)
code/crypto-perps/perp-spot-volume-share/exp01_screen.py  (+ exp01_results.csv)
code/crypto-perps/perp-spot-volume-share/exp02_reframe.py (+ exp02_results.csv)
```
