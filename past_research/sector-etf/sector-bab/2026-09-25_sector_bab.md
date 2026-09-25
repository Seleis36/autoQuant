# sector-bab — betting against beta (and the low-risk family) across sectors

**Status: Failed.** Asset class `sector-etf`. Date 2026-09-25.

## Idea
Frazzini & Pedersen (2014) and Asness, Frazzini, Gormsen & Pedersen (2020) find the low-risk
premium across industries as well as within them: leverage-constrained investors overpay for
high-beta assets. The crypto-alts `xs-momentum-neutral` alpha (Working, 1.05 OOS) is a
regime-hedged BAB, so the same construction was ported: beta-neutral when SPY is above its
SMA(200), dollar-neutral (negative beta) below.

## Setup
Common sector-etf setup (IS 1999-2014 / OOS 2015-2026, 2 bp/side, close *t* → *t+1*).
**Returns are in excess of T-bills** (`sxlib.summary_rf`: DGS3MO charged on net dollar
exposure), because BAB books are structurally net long.

Grid (`bab_grid.py`, 34 cells): beta = EWM(63/126/252) or Frazzini-Pedersen (1y vol × 5y
3-day correlation, shrunk 0.6 to 1) × construction {FP rank-weighted legs each levered to
beta 1; bottom-3/top-3 beta with SPY hedge (TERC); same dollar-neutral (TERC-D);
regime switch (REGIME)} × {monthly, 21-day tranches}; plus low-vol bottom-3/top-3.

## Results
| Cell | Sharpe full | IS | OOS | vol | MaxDD | net $ | realised β |
|---|---|---|---|---|---|---|---|
| ewm252 TERC (best IS) | 0.15 | 0.30 | −0.03 | 7.0 % | −24 % | +0.29 | 0.01 |
| FP beta, TERC | 0.14 | 0.27 | −0.01 | 6.6 % | −28 % | +0.27 | 0.01 |
| FP construction (levered legs) | 0.10 | 0.19 | −0.06 | 21.7 % | −70 % | +0.86 | 0.07 |
| REGIME (crypto-alts twist) | 0.10 | 0.26 | −0.13 | 8.4 % | −28 % | +0.21 | −0.18 |
| dollar-neutral TERC-D | −0.07 | 0.16 | −0.40 | 9.1 % | −45 % | 0 | −0.29 |
| low-vol | 0.04 | −0.01 | 0.10 | 6.6 % | −35 % | +0.23 | 0.00 |

No cell exceeds 0.15 full or 0.10 OOS. The regime hedge, which rescued BAB in crypto, *hurts*
here: in equities the negative-beta leg pays in bear markets, but the trend filter switches
too late (2008-09, 2020, 2022 V-shapes) and costs more than it saves.

### Re-framing: the rest of the low-risk family (`lowrisk_ic.py`)
Monthly rank IC vs next-21-day beta-residual return (negative = low-risk premium):
beta −0.086 IS (t −2.7) / −0.044 OOS (t −1.1); correlation −0.076 / **+0.021**; MAX(21)
−0.060 / −0.015; vol −0.041 / −0.043; idio-vol −0.019 / −0.034; skew −0.037 / −0.022.
The beta IC looks respectable but is partly mechanical (residuals computed with the same noisy
beta that sorts them, in a rising market), which is why the hedged book that actually trades it
earns only 0.15. None of the others is significant in either half.

## Verdict
42 configurations. **No low-risk premium across the SPDR sectors since 1999.** With 9-11
names the "low-beta" leg is always XLP/XLU/XLV and the "high-beta" leg XLK/XLY/XLF/XLI, so the
book is a fixed defensive-vs-cyclical bet whose P&L is dominated by the tech cycle
(2000-02 good, 2009-21 bad). Binding constraint: **no premium, and a universe too small to
diversify the sector-specific noise.**

## Files
`code/sector-etf/sector-bab/`: `bab_grid.py` (+`bab_grid.csv`), `lowrisk_ic.py`.
