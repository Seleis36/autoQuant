# bond-etf-nav-premium — official premium to NAV and creation flows in bond ETFs

**Date:** 2026-10-10 · **Asset class:** rates-bonds · **Status: Failed**

**Result.** The official premium of a bond ETF over its NAV, and its creation/redemption flow,
do not predict the ETF's return once the NAV's publication time is respected. With the NAV
of day t usable from close t+1, a hedged long-discount / short-premium book earns a gross
Sharpe of 0.2-0.3 and loses at 2 bp per side (across 40 honest-timing cells no net Sharpe is
above 0.03 in sample or above −0.18 out of sample). The information is there — the same book entered at the close the NAV is struck
on shows 5.7 / 6.7 gross — but it is gone within one session, and that entry needs a number
nobody has yet. Tradable stand-ins for it keep a gross Sharpe near 2 and die on turnover.

Code: `code/rates-bonds/bond-etf-nav-premium/`

## 1. Idea

Fulkerson, Jordan and Riley (2014) report that bond ETFs at a discount to NAV outperform
those at a premium by about 1 % a month (2007-11, CRSP). Brown, Davies and Ringgenberg
(2021) read ETF creations as non-fundamental demand that later reverses. The previous
session's `equity-credit-lead-lag` found, out of sample only, that credit ETFs give back
large equity-driven moves the next day. A premium to NAV is the direct measure of such an
overshoot, so it should carry that reversal more cleanly.

## 2. Data

State Street posts each SPDR ETF's full daily history of NAV, shares outstanding and net
assets as a spreadsheet (`navhist-us-en-<ticker>.xlsx`, no login). 30 fixed-income funds:
Treasuries, TIPS, aggregate, MBS, IG, HY, loans, convertibles, preferreds, munis,
international and EM; 2007-05 → 2026-10; cached at `data/SPDR_BOND_panel_d.parquet` with
yfinance prices (`fetch_spdr_nav.py`, stdlib xlsx reader). iShares' equivalent download now
returns the product page, and Yahoo has no ETF NAV tickers, so this is the long free history.

* The file for day T is posted after the close of T. The NAV and share count of t are usable
  from close t+1.
* Median |premium| 11 bp; standard deviation of its daily change 29 bp (1 bp for T-bills,
  32-40 bp for HY, MBS, EM and international); first-order autocorrelation 0.68.
* Funds with ≥ $2M median daily volume: 1-11 in 2008-17, 18-27 in 2018-26. The in-sample
  period is thin; a ≥ $0.5M floor is shown alongside.

Returns are residuals to IEF and HYG with trailing 120-session betas, and every book hedges
its net IEF / HYG beta with those two ETFs. IS 2008-2017, OOS 2018-2026, 2 bp per side on
every leg including the hedges.

## 3. Event study (`01_event_study.py`)

Signal at close t, forward residual return from close t+1.

| signal | 1-day low-minus-high tercile, bp (IS / OOS) | t (IS / OOS) |
|---|---|---|
| premium, 60-session z | 0.7 / 0.9 | 1.0 / 2.3 |
| premium minus 60-session mean | 0.3 / 1.0 | 0.4 / 2.4 |
| premium, 20-session z | 0.6 / 0.8 | 0.9 / 2.0 |
| 1-day premium change | 1.4 / 0.6 | 1.9 / 1.5 |
| 5-day flow (sign: outflow long) | −0.6 / 0.2 | −0.8 / 0.7 |
| 21-day flow | 0.2 / 0.4 | 0.2 / 1.3 |

One basis point a day, before paying four sides. At 5 and 10 sessions the spreads are
unsigned noise. Flows carry nothing at any horizon.

## 4. Books (`02_books.py`, 160 cells + 20 pair cells)

Tercile long-short across funds, hedged; daily or 5-session rebalance; all funds or the
credit-like subset; all signals or |z| > 1.5 only; two liquidity floors.

| family | timing | gross IS / OOS (mean, best) | net 2 bp IS / OOS (mean, best) |
|---|---|---|---|
| A official premium | skip one session (honest) | 0.17, 0.87 / 0.29, 1.07 | −0.82, 0.03 / −1.49, −0.18 |
| B official premium | no skip — **not tradable** | 1.92, 5.72 / 2.07, 6.70 | 1.11, 3.78 / 0.46, 1.85 |
| C model premium | same close, tradable | 0.82, 2.36 / 0.95, 2.40 | −0.18, 0.44 / −0.76, 0.46 |
| D residual reversal 1/2/5 d | same close, tradable | 0.58, 2.11 / 0.47, 1.89 | −0.24, 0.50 / −1.03, 0.41 |
| E flows | skip one session | −0.24, 0.23 / −0.18, 0.50 | −0.73, −0.19 / −1.26, 0.08 |

* **B is the answer to "is there information".** Yes: a discount at the close is followed by
  a higher return the next session. But B uses the NAV struck at the entry close.
* **C replaces the unknown NAV** with yesterday's official premium plus today's unexplained
  price move. Gross 2.36 / 2.40 with all funds, daily; turnover 289× a year; the gross is
  worth 2.1 bp per unit traded in sample and 1.4 bp out of sample, so 2 bp ends it
  (0.40 IS → −1.81 OOS).
* **D** is the previous session's "credit ETFs reverse" finding with no NAV at all: gross
  2.11 / 1.89 for a one-day residual, −0.61 / −3.82 net. It is the same effect as C, and it
  does not survive a cost either.
* **Substitute pairs** (JNK/SPHY, JNK/SJNK, SPIB/SPBO, SPSB/SPIB, TFI/SHM, SPIP/TIPX, BWX/IBND …)
  on the gap in official premium: with the skip 0.09 / −0.03 gross for the basket; without
  it 4.47 / 5.08 (not tradable).

## 5. Last re-framing: large dislocations only (`03_threshold.py`)

The fix that rescued the closed-end fund book — trade only dislocations big enough to pay for
four sides — does not transfer, because an ETF dislocation does not keep reverting.

Pooled slope of the next k-session residual return on the model-premium deviation:
1 d −0.075, 2 d −0.08/−0.09, 5 d −0.08/−0.12, 10 d −0.01/−0.13. About 8 % of a dislocation
comes back and then it stops. A 100 bp dislocation is worth 8 bp against 8 bp of round-trip
cost on the fund leg alone, plus the hedges. (For closed-end funds the same slope keeps
building for three weeks, which is what made a threshold book pay.)

| entry threshold | gross IS / OOS | net 2 bp IS / OOS | turnover |
|---|---|---|---|
| 25 bp | 1.04 / 0.67 | −0.18 / −1.60 | 175× |
| 50 bp | 0.74 / 0.47 | −0.06 / −0.81 | 95× |
| 75 bp | 0.91 / 0.27 | 0.39 / −0.54 | 51× |
| 100 bp | 0.66 / 0.05 | 0.32 / −0.43 | 27× |
| 150 bp | 0.52 / 0.18 | 0.39 / −0.01 | 9× |

IS-best at 2 bp: 0.39 IS → −0.01 OOS. One extra session of delay takes its gross to 0.01 /
0.01. These fills are at the close that is also the signal's last input, so bid-ask bounce
flatters them; they are upper bounds.

## 6. Why it fails

A bond ETF has authorised participants. A premium large enough to matter is arbitraged by
creation the same day or closed by the NAV catching up to the price (the ETF trades until
16:00, the bonds are marked earlier). What is left for the next session is ~8 % of the gap,
once. A closed-end fund has no such channel, and its gap drifts back over weeks — see
`cef-discount-reversion`.

## 7. Variants

30 event-study cells, 160 book cells, 20 pair cells, 10 threshold cells + 3 delays: about
220. No tradable cell is positive net of 2 bp in both halves.

Reusable: `fetch_spdr_nav.py` (30-fund NAV / shares-outstanding history) and `nav_lib.py`
(two-factor trailing-beta residuals and a hedged book).
