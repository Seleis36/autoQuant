# macro-event-premium — BTC around scheduled US macro releases (FOMC, CPI, payrolls)

**Date:** 2026-09-28
**Asset:** spot BTC/USDT (Binance 1m store), long/flat, unlevered
**Status:** **Failed (cost-bound).** There is a real, event-specific **pre-release drift**: +15 bp in the last hour and ≈ +26 bp over the last 3 hours before a scheduled US release, in both halves. The last hour is +16 bp IS and +13 bp OOS beyond a same-clock-time placebo, t 1.9 / 3.4. A 20 bp round trip at the testnet fee eats most of it. The best costed window (long T−6h → T) nets 12 bp/event: **Sharpe 0.44 full / 0.30 IS / 1.01 OOS** at 10 bp/side, with 2% of hours in the market.

---

## 1. Idea and literature

The pre-announcement drift in equities (Lucca & Moench 2015) and the announcement-day premium (Savor & Wilson 2013) say risk assets earn a premium for bearing scheduled macro-announcement risk. For BTC:
- a 2019 FRL paper finds +0.96% on the day *before* FOMC and −1% on the day itself;
- a 2026 FRL paper documents intraday FOMC event risk in crypto.

The event clock is set by the Fed and the BLS, not by BTC's own price, so any premium would be structurally uncorrelated with the trend-flavoured live sleeves.

## 2. Data (`events.py`)

- **FOMC statements:** 14:00 ET, from `code/fx-majors/shared/fomc_dates.py` (scheduled meetings only).
- **CPI and Employment Situation:** 08:30 ET. Release dates come from ALFRED vintage dates in `code/rates-bonds/treasury-flow-calendar/calendar_snapshots/`. The last vintage of each month is kept, which drops the February seasonal-factor revision vintages.
- ET is converted to UTC with DST.
- 2017-09 → 2026-09: 293 events (≈ 8 FOMC + 12 CPI + 12 NFP a year; the 2025 shutdown thinned CPI and NFP).
- Prices come from the Binance 1m store. The price *at* time t is the close of the 1m bar stamped t−1m, so every window is measured exactly from release time.
- The first version used hourly bars and silently dropped every 08:30 ET event (a :30 stamp is not on the hourly grid). The 1m version fixes that.

IS = events ≤ 2022-12-31, OOS = 2023+ (fixed in advance).

## 3. Event study (`exp01_event_study.py`) — 15 windows × 4 kinds × 2 halves

Excess log return versus the unconditional hourly mean × window length (bp):

| Window (h rel. to release) | ALL IS | ALL OOS | FOMC IS / OOS | CPI IS / OOS | NFP IS / OOS |
|---|---|---|---|---|---|
| [−24, 0) | +25 (t 0.9) | 0 | **+102 (1.7) / −8** | +9 / +62 | −9 / −58 |
| [−6, −1) | +12 | +17 (2.0) | +3 / +9 | +8 / +17 | +22 / +21 |
| **[−1, 0)** | **+16 (t 2.0)** | **+14 (t 4.6)** | +15 / +17 | +22 / +19 | +11 / +8 |
| [0, 1) | +10 | +12 | +42 / −1 | −15 / +31 | +14 / +2 |
| [1, 6) | −7 | −21 (−1.3) | +35 / −3 | −22 / −18 | −20 / −35 |
| [0, 24) | −21 | −9 | +35 / −57 | −87 / +61 | +8 / −45 |

- The literature's **day-before-FOMC premium** (+102 bp IS) is gone OOS (−8 bp).
- Longer windows flip sign between halves for every event type.
- Only the **final hours before the print** are positive in both halves and for all three event types.

## 4. Clock-time placebo (`exp02_placebo_and_trade.py` part 1)

CPI and NFP land at 12:30 / 13:30 UTC and FOMC at 18:00 / 19:00 UTC, so the drift could be an hour-of-day effect. The placebo uses the same window at the same clock time on the same weekday ±1 and ±2 weeks, dropping any placebo day that is itself an event day.

| Window | event IS | placebo IS | **diff IS (t)** | event OOS | placebo OOS | **diff OOS (t)** |
|---|---|---|---|---|---|---|
| [−1, 0) | 16.0 | −0.4 | **+16.4 (1.9)** | 14.9 | 1.6 | **+13.3 (3.4)** |
| [−3, 0) | 25.1 | 10.4 | +14.8 (1.3) | 26.0 | 1.4 | **+24.6 (3.9)** |
| [−6, 0) | 28.1 | 21.4 | +6.7 (0.4) | 35.2 | 1.3 | +33.9 (3.4) |
| [−12, 0) | 35.8 | 10.6 | +25.1 (1.0) | 27.5 | 11.1 | +16.4 (1.1) |

- The last hour is event-specific in both halves.
- In IS the [−6, −1) part is mostly clock time: the run into the US morning was positive on non-event days too before 2023.

## 5. Costed trade (part 2) — 6 windows × 3 cost levels × 2 gates = 36 cells

The trade is long BTC from T−k to T, exiting before the print; the book is flat otherwise. The Sharpe is on the daily P&L stream, flat days included.

| k | 0 bp: full / IS / OOS | 5 bp | **10 bp (testnet)** | net bp/event @10 |
|---|---|---|---|---|
| 1 h | 1.05 / 0.88 / 2.27 | 0.40 | **−0.27** | −4 |
| 3 h | 1.25 / 1.03 / 2.25 | 0.78 | **0.30** / 0.25 / 0.58 | +6 |
| 6 h | 1.14 / 0.88 / 2.17 | 0.80 | **0.44** / 0.30 / 1.01 | +12 |
| 12 h | 0.85 / 0.80 / 1.16 | 0.61 | 0.37 | +15 |
| 24 h | 0.50 / 0.56 / 0.39 | 0.33 | 0.16 | +10 |
| 6 h, only when BTC > SMA50 | 0.88 | 0.65 | 0.42 / 0.38 / 0.63 | +17 |
| 24 h, only when BTC > SMA50 | 0.86 | 0.74 | 0.62 / 0.79 / 0.29 | +50 |

- Even at zero cost the full-sample Sharpe tops out at 1.25.
- The gross drift is ≈ 26 bp per event over 3 h, only 32 events a year, and a round trip is 20 bp.
- The trend gate helps IS on long windows and fails OOS (24 h: 0.79 → 0.29).

## 6. Verdict and a note for the live sleeves

- **Failed.** The premium is real but too small per event for a 10 bp/side venue.
- Binding constraint: gross ≈ 15–30 bp per event against a 20 bp round trip.
- Configurations: 120 event-study cells, 48 placebo cells, 36 costed trades.

**Usable as an execution rule, not an alpha.** The sleeves already holding BTC (`weekday-trend`, `coinbase-premium`, `bult`) are long through these windows and earn the drift for free. A sleeve that has to *add* BTC on a CPI/NFP/FOMC day saves ~15 bp by buying before T−1h rather than at the release. A sleeve that has to *sell* does better at T than at T−1h. At these sleeves' turnover this is worth a few bp a year; it is recorded here, not deployed.
