# cross-asset-tsmom — do past equity returns time US duration?

**Date:** 2026-09-29 · **Asset class:** rates-bonds · **Status:** **Failed**

## 1. Idea

Pitkäjärvi, Suominen & Vaittinen, *Cross-asset signals and time series momentum* (JFE 2020):
across 20 countries 1980-2016, past **bond** returns predict bond returns positively (TSMOM)
and past **equity** returns predict bond returns **negatively**; the combined "cross-asset
TSMOM" position beats plain TSMOM by ~45 % in Sharpe. Mechanism: slow-moving capital — after
an equity rally, balanced investors rotate out of bonds (and growth / rate expectations rise);
after a crash, they rotate in. `rates-carry-trend` already tested own-TSMOM on US duration
(IS 0.50 → OOS ~0.3); the new ingredient is the equity leg.

## 2. Setup — `01_screen.py`

* Bond: synthetic 10y constant-maturity excess return over the 3m bill (FRED CMT, 1982+,
  `rb_data.cmt_returns`); IEF and TLT excess returns for the ETF era (2002+ spliced).
* Equity: S&P 500 price index 1960+ (`IDX_GSPC_d_long` / `_pre2010` / current spliced), minus the bill.
* Signals at each month-end, lookback L ∈ {1, 3, 6, 12} months: `own` = sign(bond L-month
  excess), `eq` = −sign(equity L-month excess), `combo` = (own + eq)/2 (PSV).
* Book: signal × (10 % / EWMA-60d bond vol), cap 3×, set at the month-end close, held for the
  month, 2 bp/side.
* **Split fixed in advance:** IS 1985–2009 (synthetic only; IEF/TLT rows in the IS column
  cover 2002–2009), OOS 2010–2026-09.

## 3. Round 1 — PSV as published (`01_screen_output.txt`)

| Signal (syn10) | L=1 IS / OOS | L=3 IS / OOS | L=6 IS / OOS | L=12 IS / OOS |
|---|---|---|---|---|
| own TSMOM | 0.43 / −0.07 | 0.22 / 0.22 | 0.02 / 0.12 | 0.42 / 0.12 |
| −equity (cross-asset) | 0.47 / −0.04 | 0.49 / 0.02 | 0.06 / 0.05 | −0.19 / −0.09 |
| combo | **0.69** / −0.06 | 0.51 / 0.17 | 0.06 / 0.13 | 0.19 / 0.03 |
| vol-scaled long only | 0.58 / 0.12 | | | |

On IEF (OOS) the combo is 0.12–0.15 at L = 3, 6, 12 and −0.08 at L = 1; on TLT −0.08 to 0.15.
The cross-asset leg does work in 1985-2009 at short lookbacks (0.47–0.49, the published
result), but nothing in-sample beats **vol-scaled long-only** (0.58) by more than noise,
and **every cross-asset configuration is between −0.18 and +0.15 OOS**.

## 4. Round 2 — correlation-regime re-framing — `02_beta_regime.py`

The economic content of the negative equity predictor is "the bond keeps moving the way the
equity move implies", which reverses sign when the stock-bond correlation is positive
(trailing beta of the 10y on the S&P: positive 1982-1997, negative 1998-2022, positive again
2023+). Re-framed signal `imp = sign(β_252d × equity L-month return)`, alone and combined
with own-TSMOM, plus demeaned versions of all signals (subtract the expanding mean position so
the 1985-2009 bond bull does not count as timing). 96 cells on syn10 / IEF / TLT.

* `imp`: IS −0.13 to +0.84, **OOS −0.05 to −0.42 on every instrument and lookback**, and
  −0.6 to −1.4 in 2022-2026, the regime it was meant to handle.
* `combo_imp`: OOS −0.35 to +0.06.
* Demeaning helps IS for the ETF rows (2002-09) but moves no OOS number above 0.18.
* The best OOS cells anywhere are `combo_psv` at L = 6 (0.13–0.17) and the L = 12 variants
  in 2022-2026 (0.4–0.6 over 4.7 years), neither selectable from IS.

## 5. Verdict

**Failed.** 132 cells. The PSV cross-asset predictor is an in-sample (1985-2009) US result
that does not survive into 2010-2026 on synthetic 10y, IEF or TLT, with or without a
correlation-regime adjustment. Best IS→OOS: combo L=1 0.69 → −0.06. The binding problem is
the same as `rates-carry-trend`: US duration has had one broad trend reversal (2020-2023)
since 2010, and monthly directional signals get one or two independent bets per year.
