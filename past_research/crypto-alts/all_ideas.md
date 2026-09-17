# All research ideas — Liquid altcoin cross-section (`crypto-alts`)

One line per idea. Status is **Working** for a profitable idea, **Failed** otherwise.
Each line links to the full report in `<short-name>/`.

| Date | Idea | Status | Key result |
|---|---|---|---|
| 2026-09-17 | [Regime-hedged betting-against-beta](xs-momentum-neutral/2026-09-17_xs_momentum_neutral.md) (`xs-momentum-neutral`) — long lowest-beta / short highest-beta tercile of a PIT top-20-by-volume alt universe (EWM-60 beta to BTC, 14-day tranches); beta-neutral legs when BTC > SMA50, dollar-neutral (negative beta) below. Also screened and failed: XS momentum 7–180d, 1–7d reversal, BTC lead-lag, residual momentum, per-alt and basket trend L/S, low-vol, vol targeting; 1101 configs, IS 2018-22 / OOS 2023-26, 10 bp/side. Adds `code/crypto-alts/shared/universe.py` and multi-asset helpers in `research_lib`. | **Working** (borderline vs "Sharpe ≥ 1, winning in bear markets") | Net Sharpe **1.22 full / 1.35 IS / 1.05 OOS** @10bp, CAGR 29.9%, MaxDD −30%, turnover 9×/yr, gross 1.0, beta −0.04; **positive in all 5 ex-post BTC bear phases** (pooled 1.49; 2018 +0.25, 2019-20 +0.26, 2021 +4.3, 2022 +2.7, 2025-26 OOS +0.78). Selection-free: 162-config median 1.03 full / 0.70 OOS, 100% bear-positive; walk-forward 2021-26 1.55. Binding risk is unmodelled short-leg funding (10%/yr → 1.04). |
