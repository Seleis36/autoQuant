# credit-style-premia — fallen angels, short-dated credit and loans as hedged ETF alphas

**Date:** 2026-10-10 · **Asset class:** rates-bonds · **Status: Failed**

**Result.** Four structural credit premia from the literature — fallen angels, short-dated
high yield, short-dated investment grade, senior loans — each held as a long ETF hedged for
rates (IEF) and credit beta (HYG or LQD), in excess of cash, 2 bp per side. Every one has the
predicted positive sign over 2012-2026 (t 0.4 to 2.6) and every one fades out of sample:
the pre-registered equal-risk combination is **0.82 in sample (2012-18) / 0.23 out of sample
(2019-26)**, 0.16 since 2022. Fallen angels are the strongest (0.58 / 0.44, 2.9 %/yr) but half
of the total came in 2016 and nothing since 2022.

Code: `code/rates-bonds/credit-style-premia/`

## 1. Idea

The cost of trading has killed every daily signal on bond ETFs in this folder, so this idea
goes the other way: premia that need almost no turnover.

* **Fallen angels.** Investment-grade mandates must sell bonds downgraded to high yield;
  the bonds are bought cheap and recover (Ben Dor & Xu 2011). ETFs: ANGL (2012), FALN (2016).
* **Defensive / low-risk credit.** Short-maturity, low-beta credit earns more per unit of risk
  than long-maturity credit — the "defensive" factor of Israel, Palhares & Richardson (2018),
  betting-against-beta of Frazzini & Pedersen (2014). ETFs: SJNK, SHYG, HYS (short HY); VCSH,
  IGSB, SPSB (short IG); the long-dated side is VCLT, IGLB, SPLB.
* **Senior loans.** Secured, floating: low spread duration for the yield. BKLN, SRLN.

`credit-spread-trend` (2026-09) timed the *market* credit premium and failed. This asks
whether there is alpha *inside* credit, held statically.

## 2. Construction (`csp_lib.py`)

    leg = long X − b_rate × IEF − b_credit × (HYG or LQD)

Betas are trailing 250-session two-factor OLS, reset at the last close of each month (NYSE
calendar). Long-dated IG is hedged with TLT + LQD. Returns are **in excess of cash on the
leg's net exposure**. IS 2012-07 → 2018-12, OOS 2019-01 → 2026-10, fixed in advance; no
parameter is fitted, so the split only tests persistence.

**Trap (my first run).** A leg that is long 1 VCSH and short 0.25 of hedges holds 0.75 of
net exposure. Without subtracting the T-bill return on that, short-dated IG showed
"0.71 Sharpe out of sample, 1.9 %/yr" — which was 4-5 % cash rates in 2023-25. In excess
terms it is −0.03. Any hedged-long book with betas below one needs this correction.

## 3. Each leg (`01_premia.py`, net Sharpe, annual excess return)

| family | ETF | hedge betas (rate, credit) | IS | OOS | full | full t | max DD |
|---|---|---|---|---|---|---|---|
| fallen | ANGL | 0.07, 0.78 | 0.58 (4.2 %) | 0.35 (1.8 %) | 0.47 | 2.6 | −13.8 % |
| fallen | FALN | 0.10, 0.92 | −0.11¹ | 0.45 (2.0 %) | 0.36 | 1.1 | −13.0 % |
| short HY | SJNK | −0.04, 0.66 | 0.49 | 0.34 | 0.41 | 1.3 | −8.8 % |
| short HY | SHYG | −0.04, 0.67 | 0.33 | 0.21 | 0.26 | 1.0 | −5.3 % |
| short HY | HYS | −0.03, 0.67 | 0.88 | 0.19 | 0.49 | 2.0 | −7.7 % |
| short IG | VCSH | 0.10, 0.15 | 0.62 | −0.03 | 0.13 | 0.5 | −10.5 % |
| short IG | IGSB | 0.06, 0.13 | 0.38 | 0.03 | 0.09 | 0.4 | −11.0 % |
| short IG | SPSB | 0.03, 0.10 | 0.61 | −0.09 | 0.07 | 0.3 | −10.9 % |
| long IG (predicted ≤ 0) | VCLT / IGLB / SPLB | 0.23, 1.0 | 0.05-0.13 | 0.01-0.05 | 0.03-0.09 | 0.2-0.5 | −10 % |
| loans | BKLN | −0.07, 0.40 | 0.43 | −0.01 | 0.10 | 0.5 | −18.1 % |
| loans | SRLN | −0.09, 0.30 | 0.55 | 0.02 | 0.12 | 0.5 | −16.9 % |

¹ from 2017 only.

Family averages: fallen 0.58 / 0.44 (t 2.2 / 1.4); short HY 0.98 / 0.29 (2.3 / 0.7); short IG
0.77 / −0.03 (2.2 / −0.1); loans 0.66 / 0.00 (1.5 / 0.0); long IG 0.14 / 0.04.

Fallen-angel alpha by year (%): 2013 +6.3, 2014 +1.8, 2015 +1.0, **2016 +15.0**, 2017 +3.8,
2018 −4.2, 2019 +4.6, 2020 +6.4, 2021 +5.3, 2022 −2.9, 2023 +2.1, 2024 −0.2, 2025 −0.3,
2026 −0.1. The premium is paid after downgrade waves (2015-16 energy, 2020) and is absent
when there are none. Rolling three-year t-statistics of every family are below 2 at every
year-end since 2019.

## 4. Combinations and re-framings (`02_combos.py`)

| book | IS | OOS | full | 2022+ |
|---|---|---|---|---|
| **equal risk, four families (pre-registered)** | **0.82** | **0.23** | 0.34 | 0.16 |
| equal weight, four families | 0.85 | 0.23 | 0.47 | 0.12 |
| equal risk, fallen + short HY | 0.76 | 0.40 | 0.55 | 0.19 |
| equal risk, short HY + short IG | 1.15 | 0.17 | 0.39 | 0.29 |
| BAB inside HY: SJNK/SHYG/HYS − β × HYG | 0.94 | 0.32 | 0.61 | 0.63 |
| BAB inside IG: short-dated − β × long-dated | 0.88 | 0.07 | 0.22 | −0.26 |
| BKLN − β × HYG | 0.42 | 0.07 | 0.16 | 0.48 |

**Conditioning on a credit sell-off** (hold a family only after the duration-stripped HYG
return over the last 63 or 126 sessions was negative — the forced-selling story): in sample
the premia were earned after credit *gains* (fallen 0.80 vs −0.11; short HY 1.72 vs −0.09;
loans 1.57 vs −0.42), out of sample after credit *losses* (fallen 0.07 vs 0.62; short HY
−0.20 vs 0.75). The condition flips between halves; it is not a signal.

## 5. Why it fails

The premia are real in the bond-level literature because they are harvested with hundreds of
bonds, chosen by characteristic, against a matched index. An ETF pair gives one noisy draw:
SJNK against 0.66 of HYG differs by rating mix, call structure and sector as much as by
maturity, and those differences have 1.7-6 % of tracking volatility against 0.5-3 % of
premium. After 2019 the short-dated legs also lost their funding advantage (cash yields rose
to the level of their carry). 13 legs, 4 combinations, 10 BAB pairs and 16 conditional cells
were scored. No unconditional cell is above 0.45 out of sample; the two conditional cells that
are (0.62 and 0.75) were negative in sample.

Reusable: `csp_lib.py` (two-factor hedged legs, monthly reset, excess-of-cash accounting).
