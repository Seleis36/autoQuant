# Deleveraging rebound — buy the forced-liquidation flush (`deleveraging-rebound`, crypto-perps)

**Date:** 2026-09-30 · **Status: Failed.** The apparent rebound after "OI collapse + price drop" days
is a market-wide bounce. Once returns are market-adjusted and events are clustered by date, no event
type is significant in both halves. BTC-only flush days rebound in both halves, but on 14 events each.

## 0. Idea

When open interest collapses on a down day, positions were closed by force: liquidations and margin
calls. Forced selling is liquidity-driven, not informed (Brunnermeier & Pedersen 2009, liquidity
spirals), so its price impact should revert.

The spot-eth `flush-rebound` screen found no reversal after price-only down-shocks. The new element
is the OI filter, which separates *forced* from *informed* selling.

## 1. Set-up

- **Panel:** the 64 perps of `funding_panel.PERP_OF` (63 with Binance spot). Prices are Binance spot
  `<BASE>USDT` daily closes.
  - yfinance was tried first. OP-USD and TIA-USD carry namesake-ticker prints (2,000× and 30,000×
    one-day "returns") that `clean_close` does not catch.
  - `retail-crowding-xs` was checked: neither name is in its universe on a bad day.
- **OI:** Binance metrics archive, OI in coins, last stamp before 23:00 UTC. BTC from 2020-09, the
  rest from 2021-12.
- **Features:**
  - doi = Δlog OI (24 h), r1 = daily return;
  - z = value / trailing-90-day std, past only.
- **Pre-declared events:**
  - LIQ_DOWN: z_doi ≤ −2 and z_r1 ≤ −1
  - PX_DOWN: z_r1 ≤ −2
  - PX_DOWN_noOI: PX_DOWN with z_doi > −1
  - PX_DOWN_withOI: PX_DOWN with z_doi ≤ −1
  - LIQ_UP: z_doi ≤ −2 and z_r1 ≥ +1
  - BUILD_UP: z_doi ≥ +2 and r1 > 0
- **Split:** IS through 2023-12, OOS 2024+.

## 2. exp01 — raw event study (10 majors, then all 63 coins)

Forward return minus the coin's own mean, in bp, (t), pooled events. **The t-stats overstate**:
events cluster on market crash days.

| event | IS n | IS 1d / 3d / 7d | OOS n | OOS 1d / 3d / 7d |
|---|---|---|---|---|
| LIQ_DOWN | 307 | −22 / **+128 (2.6)** / −92 | 501 | +2 / **+200 (3.7)** / +298 (3.8) |
| PX_DOWN | 942 | **+104 (4.1)** / +48 / −138 | 1279 | **+58 (3.2)** / +175 / +193 |
| PX_DOWN_noOI | 570 | +212 (6.7) / +39 / −124 | 854 | +66 (3.0) / +97 / +84 |
| LIQ_UP | 105 | −83 / −146 / −159 | 166 | +91 / +1 / +14 |
| BUILD_UP | 1019 | +26 / −7 / +20 | 1254 | +21 / +82 / +227 (3.8) |

On the first 10-major run, LIQ_DOWN at 7 days was −350 bp IS and +188 bp OOS, a sign flip.

Pooled regression (h1): the price coefficient flips from −21 bp per σ IS (reversal) to +16 bp OOS
(continuation).

## 3. exp02 — market-adjusted, date-clustered

Forward return minus the equal-weight forward return of all coins that day, averaged per event date:

| event | IS dates | IS 1d / 3d / 7d bp (t_cl) | OOS dates | OOS 1d / 3d / 7d bp (t_cl) |
|---|---|---|---|---|
| LIQ_DOWN | 119 | +23 (1.0) / +16 / −33 | 145 | −39 (−1.4) / +20 / +61 |
| PX_DOWN | 111 | −30 (−1.2) / −33 / −23 | 177 | +23 (0.6) / +17 / +51 |
| PX_DOWN_noOI | 96 | −11 / −1 / −13 | 160 | +37 (0.9) / +38 / +32 |
| PX_DOWN_withOI | 69 | **−63 (−2.5)** / −117 / −106 | 80 | −6 / +52 / +210 |
| BUILD_UP | 516 | 0 / −12 / −20 | 580 | −31 (−1.6) / +24 / +111 |

- Pooled regression with date-clustered SE: no coefficient has |t| > 2 in both halves.
  - The OI coefficient is −2 bp (t −1.0) IS and −3.5 bp (t −1.9) OOS.
- **Market-level deleveraging days** (median coin z_doi ≤ −1 and EW z ≤ −1): 5 IS days with
  −63 bp EW at 3 days, and 10 OOS days with +443 bp. Too few, opposite signs.
- Market drops *without* a flush: IS 3-day −121 bp, OOS −57 bp.

**BTC / ETH alone** (forward bp; BTC unconditional 3d is +47 IS / +28 OOS):

| event | IS n | IS 3d / 7d | OOS n | OOS 3d / 7d |
|---|---|---|---|---|
| BTC LIQ_DOWN | 14 | +117 / +217 | 14 | +156 / +13 |
| BTC 3-day OI flush + price down | 23 | −17 / +35 | 17 | −25 / −144 |
| ETH LIQ_DOWN | 6 | +336 / −51 | 8 | +186 / +212 |
| ETH 3-day OI flush + price down | 5 | +239 / +257 | 17 | −167 / −308 |

## 4. Verdict

**Failed.**
- The idiosyncratic part of a coin's rebound after a flush day is zero.
- What looked like a rebound in the pooled study is the whole market bouncing after crash days,
  which is BTC beta, not a deleveraging premium.
- The one consistent-sign cell (BTC LIQ_DOWN, +1.2–1.6 % excess over 3 days in both halves) rests on
  14 + 14 events, has t < 1, and its 3-day-flush variant has the opposite sign.
- **No tradeable rule was built:** the event study never cleared the bar at which a rule would be
  worth costing.

Variants: 6 event types × 4 horizons × 2 panels (exp01), 5 × 3 market-adjusted, 3 market-level
conditions, 3 × 2 BTC/ETH. About 20 distinct event definitions.

## 5. Files

```
code/crypto-perps/deleveraging-rebound/exp01_events.py   (--all: 63-coin panel -> exp01_panel_all.parquet)
code/crypto-perps/deleveraging-rebound/exp02_clustered.py
```
