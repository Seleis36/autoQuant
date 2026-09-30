# Smart money vs retail divergence (`smart-retail-divergence`, crypto-perps)

**Date:** 2026-09-30 · **Status: Failed.** Binance "top traders" are not informed relative to the
retail crowd.
- **Cross-sectionally** the divergence is dead in every cell.
- **On BTC**, a divergence gate lifts inverse-vol BTC from 0.49 to 1.02, but it is the retail account
  ratio re-expressed (ρ −0.90). It adds nothing to the live `spot-btc/perp-crowding` rule
  (1.23 → 1.22) and does not replicate across coins.

## 0. Idea

Binance publishes two positioning views of each perp:
- the **global account ratio**, a head count dominated by retail;
- the **top-trader ratios**, covering the top 20 % of accounts by margin balance, both as a head
  count and as long/short *position notional*.

The folklore ("smart money vs dumb money") is that large accounts are informed. Hypothesis: go long
where top-trader positions are more long than the retail crowd.

It is distinct from `retail-crowding-xs`, which uses the retail level alone. Here the claim is about
the *gap* between two groups.

## 1. Set-up

- **Series** (last stamp before D 23:00 UTC, `metrics_panel.daily_metrics`):
  - acc = log global account ratio
  - tacc = log top-trader account ratio
  - pos = log top-trader position ratio
- **Divergences** (pre-declared):
  - div_pa = pos − acc (big money vs crowd)
  - div_pt = pos − tacc (within top traders: notional vs head count)
- **Cross-sectional set-up:** identical to `retail-crowding-xs`. PIT top-20 of the 64 perps, q30,
  β-neutral, 7-day tranches, IS 2022-03 → 2023-12, OOS 2024+, 10 bp.
- In the cross-section, div_pa correlates −0.66 with acc and +0.43 with pos.

## 2. exp01 — cross-section (8 cells) and BTC time series

| cell ("+" = long where big money is more long) | full | IS | OOS |
|---|---|---|---|
| +div_pa raw | −0.14 | −0.14 | −0.15 |
| −div_pa raw | −0.26 | −0.22 | −0.28 |
| +div_pa own-90d demeaned | −0.76 | −0.20 | −1.04 |
| −div_pa demeaned | 0.18 | −0.26 | 0.39 |
| +div_pt raw / demeaned | −0.08 / −0.85 | | |
| −div_pt raw / demeaned | −0.32 / 0.26 | | |

- ICs: |IC7| ≤ 0.05 and |t| < 1.6 in every cell and half.
- Where there is a sign, "big money more long than usual" *under*performs.

**BTC time series.** z = 365-day z-score of the divergence.

| | IC30 IS | IC30 OOS |
|---|---|---|
| z(div_pa) | +0.313 | +0.102 |
| z(div_pt) | +0.330 | +0.109 |

- Pre-declared gate "BTC × inverse-vol, flat when z(div_pa) < −1": **1.04** (IS 0.93 / OOS 1.15),
  vs inverse-vol alone 0.51.
- The opposite gate (flat when z > +1) earns 0.05.

## 3. exp02 — is the BTC gate new information?

| | IC30 IS | IC30 OOS |
|---|---|---|
| z(div_pa) | +0.315 | +0.102 |
| z(acc), the retail ratio | −0.224 | −0.143 |
| z(pos) | −0.164 | −0.145 |
| **partial IC of z(div), controlling for z(acc), mom30 and SMA50 distance** | −0.221 | **+0.011** |
| partial IC of z(div), controlling for z(pos), mom30 and SMA50 distance | +0.299 | +0.219 |

- z(div) correlates **−0.90** with z(acc). Its OOS information is exactly the retail account ratio,
  which is the live `perp-crowding` signal.

| BTC rule, × inverse-vol, 2021-03 → 2026-09 | full | IS | OOS | MaxDD |
|---|---|---|---|---|
| inverse-vol alone | 0.49 | 0.32 | 0.68 | −61 % |
| divergence gate | 1.02 | 0.89 | 1.15 | −33 % |
| retail-only gate (flat if z_acc > 1) | 0.76 | 0.76 | 0.76 | −46 % |
| top-trader-only gate (flat if z_pos < −1) | 0.49 | 0.45 | 0.53 | −55 % |
| SMA50 × inverse-vol | 0.90 | 0.75 | 1.06 | −43 % |
| SMA50 × divergence gate | 1.18 | 1.28 | 1.16 | −25 % |
| **live perp-crowding × inverse-vol** | **1.23** | 1.35 | 1.11 | −30 % |
| **perp-crowding × divergence gate** | **1.22** | 1.34 | 1.16 | −29 % |
| gate threshold −0.5 / −1.5 | 0.96 / 0.69 | | | |
| z window 180 / 730 | 0.92 / 0.96 | | | |

- The divergence gate is 0.70 correlated with perp-crowding and adds nothing on top of it.

**Replication, same parameters** (IC30, then gate × inverse-vol vs inverse-vol alone, from 2023-05):

| ETH | SOL | XRP | BNB | DOGE |
|---|---|---|---|---|
| +0.04, 0.52 vs 0.57 | +0.09, 1.33 vs 1.06 | −0.09, 0.84 vs 0.88 | +0.26, 1.43 vs 0.94 | +0.03, 0.74 vs 0.64 |

Mixed: it helps on BNB and SOL, and is flat or negative elsewhere.

## 4. Verdict

**Failed.**
- Top traders carry no cross-sectional information relative to the crowd.
- The BTC time-series gate works only because it contains the retail ratio, which is already
  deployed.
- Across these tests, the top-trader *position* ratio behaves like another crowd measure: it is
  contrarian on its own (−pos XS 1.16 in `retail-crowding-xs` exp02). It is not a smart-money signal.

Variants: 8 cross-sectional + 4 BTC ICs + 2 BTC gates (exp01), 12 BTC rules + 5 replications (exp02).

## 5. Files

```
code/crypto-perps/smart-retail-divergence/exp01_screen.py  (+ exp01_results.csv)
code/crypto-perps/smart-retail-divergence/exp02_btc_gate.py
```
