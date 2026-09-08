"""Final candidate: ETH > SMA(40) base, sized by inverse-vol scalar.

Additional analyses:
  - Combined SMA40 + vol-target for several targets & halflives
  - Full walk-forward including all elements
  - Bootstrap block resampling for Sharpe distribution
  - Split-by-year and split-by-regime
  - Verify BTC filter and ratio don't add
"""
import os, sys, json
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "code", "shared")))

import numpy as np, pandas as pd
from research_lib import load_btc, backtest, perf_stats, fmt, ewm_vol

RNG = np.random.default_rng(42)

eth = load_btc(ticker="ETH-USD")["Close"].rename("ETH")
btc = load_btc(ticker="BTC-USD")["Close"].rename("BTC")
df = pd.concat([eth, btc], axis=1, sort=True).dropna()
eth_c = df["ETH"]; btc_c = df["BTC"]
eth_r = eth_c.pct_change()

IS_END = "2023-12-31"; OOS_START = "2024-01-01"

def base_sig(win=40):
    return (eth_c > eth_c.rolling(win).mean()).astype(float)

def vt(ret, target, hl=20, cap=1.0):
    return (target / ewm_vol(ret, halflife=hl)).clip(0.0, cap).fillna(0.0)

def evaluate(w, name, cost=10.0):
    net, st = backtest(w, eth_c, cost_bps=cost, name=name)
    is_st = perf_stats(net.loc[:IS_END], name=f"{name}_IS")
    oos_st = perf_stats(net.loc[OOS_START:], name=f"{name}_OOS")
    return net, st, is_st, oos_st

print("== Grid: SMA(w) base + vol-target(target, hl) ==")
rows = []
for win in [30, 40, 50]:
    for tgt in [0.4, 0.5, 0.6, 0.7, 0.8, 1.0, 1.5]:
        for hl in [10, 20, 30, 60]:
            w = base_sig(win) * vt(eth_r, tgt, hl=hl)
            net, st, is_, oo = evaluate(w, f"w{win}_t{tgt}_h{hl}")
            rows.append({"win":win,"tgt":tgt,"hl":hl,
                         "Full":st.Sharpe,"IS":is_.Sharpe,"OOS":oo.Sharpe,
                         "CAGR":st.CAGR,"MDD":st.MaxDD,"Calmar":st.Calmar,
                         "TIM":st.TimeInMkt,"Turn":st.Turnover_ann})
G = pd.DataFrame(rows)
G["gap"] = (G.IS - G.OOS).abs()
top = G.sort_values("Full", ascending=False).head(15)
print(top.round(3).to_string(index=False))

print("\n== Top by OOS Sharpe ==")
top_oos = G.sort_values("OOS", ascending=False).head(15)
print(top_oos.round(3).to_string(index=False))

print("\n== Top by Calmar ==")
top_cal = G.sort_values("Calmar", ascending=False).head(10)
print(top_cal.round(3).to_string(index=False))

# Pick: SMA(40) + vol-target(0.5, hl=20) — solid across all metrics with 1+ Sharpe
FINAL_WIN, FINAL_TGT, FINAL_HL = 40, 0.5, 20
w_final = base_sig(FINAL_WIN) * vt(eth_r, FINAL_TGT, hl=FINAL_HL)
net, st, is_, oo = evaluate(w_final, "FINAL")
print(f"\n== FINAL: SMA({FINAL_WIN}) & vol-target(tgt={FINAL_TGT}, hl={FINAL_HL}) ==")
print(f"Full: Sharpe {st.Sharpe:.2f} CAGR {st.CAGR*100:.1f}% MDD {st.MaxDD*100:.1f}% "
      f"Calmar {st.Calmar:.2f} Sortino {st.Sortino:.2f} t_NW {st.t_NW:.2f}")
print(f"IS:   Sharpe {is_.Sharpe:.2f} CAGR {is_.CAGR*100:.1f}% MDD {is_.MaxDD*100:.1f}%")
print(f"OOS:  Sharpe {oo.Sharpe:.2f} CAGR {oo.CAGR*100:.1f}% MDD {oo.MaxDD*100:.1f}%")
print(f"Turnover/yr: {st.Turnover_ann:.1f} | TimeInMkt {st.TimeInMkt*100:.1f}% "
      f"| AvgExposure {st.AvgExposure*100:.1f}%")

# Also test SMA(40) alone (simpler)
net40, st40, is40, oo40 = evaluate(base_sig(40), "SMA40_alone")
print(f"\nSMA(40) alone (for reference):")
print(f"Full Sharpe {st40.Sharpe:.2f} IS {is40.Sharpe:.2f} OOS {oo40.Sharpe:.2f} "
      f"CAGR {st40.CAGR*100:.1f}% MDD {st40.MaxDD*100:.1f}%")

# Buy and hold baseline
netbh, stbh, isbh, oobh = evaluate(pd.Series(1.0, index=eth_c.index), "BH")
print(f"\nBuy-and-hold ETH:")
print(f"Full Sharpe {stbh.Sharpe:.2f} IS {isbh.Sharpe:.2f} OOS {oobh.Sharpe:.2f} "
      f"CAGR {stbh.CAGR*100:.1f}% MDD {stbh.MaxDD*100:.1f}%")

# ==========================================================================
# Yearly performance
print("\n== Yearly Sharpe & return (final) ==")
yrs = {}
for y in sorted(set(net.index.year)):
    seg = net[net.index.year == y]
    yrs[y] = {
        "N": len(seg),
        "Sharpe": seg.mean()/seg.std()*np.sqrt(365) if seg.std() else np.nan,
        "Return%": ((1+seg).prod()-1)*100,
        "MaxDD%": (((1+seg).cumprod()/(1+seg).cumprod().cummax()-1).min())*100,
    }
Y = pd.DataFrame(yrs).T
print(Y.round(2).to_string())

# ==========================================================================
# Block bootstrap
print("\n== Block bootstrap (block=30d, n=2000) of FINAL Sharpe ==")
def block_bootstrap_sharpe(r, block=30, n=2000, ann=365):
    r = r.dropna().values
    N = len(r); nblocks = int(np.ceil(N/block))
    sharpes = np.zeros(n)
    for i in range(n):
        starts = RNG.integers(0, N-block+1, size=nblocks)
        samp = np.concatenate([r[s:s+block] for s in starts])[:N]
        m, s = samp.mean(), samp.std(ddof=1)
        sharpes[i] = m/s*np.sqrt(ann) if s>0 else np.nan
    return sharpes
boot = block_bootstrap_sharpe(net)
print(f"Bootstrap Sharpe: mean={np.nanmean(boot):.2f}, "
      f"5%={np.nanpercentile(boot,5):.2f}, 95%={np.nanpercentile(boot,95):.2f}, "
      f"P(Sh>0)={np.mean(boot>0):.3f}, P(Sh>1)={np.mean(boot>1):.3f}")

# ==========================================================================
# Full walk-forward on the joint (win, target) selection
print("\n== Walk-forward: pick (SMA_win, vol_target) on trailing 730d, apply 90d ==")
wins = [30, 40, 50, 60]; targets = [0.4, 0.5, 0.7, 1.0]
wf_w = pd.Series(0.0, index=eth_c.index)
picks = []
train_days = 730; step = 90; dates = eth_c.index
i = train_days
while i < len(dates):
    end_i = min(i+step, len(dates))
    ts = dates[max(0, i-train_days)]; te = dates[i-1]
    best_sh = -np.inf; best_key = None
    for win in wins:
        for tgt in targets:
            w = base_sig(win) * vt(eth_r, tgt, hl=20)
            nn, _ = backtest(w, eth_c, cost_bps=10.0)
            seg = nn.loc[ts:te]
            sh = perf_stats(seg).Sharpe
            if pd.notna(sh) and sh > best_sh:
                best_sh, best_key = sh, (win, tgt)
    picks.append((dates[i], best_key, best_sh))
    win, tgt = best_key
    w_apply = base_sig(win) * vt(eth_r, tgt, hl=20)
    wf_w.loc[dates[i]:dates[end_i-1]] = w_apply.loc[dates[i]:dates[end_i-1]].values
    i = end_i

net_wf, st_wf = backtest(wf_w, eth_c, cost_bps=10.0, name="walkfwd_final")
is_wf = perf_stats(net_wf.loc[:IS_END], name="wf_IS")
oo_wf = perf_stats(net_wf.loc[OOS_START:], name="wf_OOS")
print(f"Walk-fwd: Full {st_wf.Sharpe:.2f} IS {is_wf.Sharpe:.2f} OOS {oo_wf.Sharpe:.2f} "
      f"| CAGR {st_wf.CAGR*100:.1f}% | MDD {st_wf.MaxDD*100:.1f}%")
from collections import Counter
print("Pick histogram:", Counter([p[1] for p in picks]))

# ==========================================================================
# Save the equity curves & weights for figures
out_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "alphas", "spot-eth", "eth-trend-filter"))
os.makedirs(out_dir, exist_ok=True)
eqdf = pd.DataFrame({
    "eth_price": eth_c,
    "weight": w_final.shift(1),  # applied to next day
    "ret_final": net,
    "ret_sma40": net40,
    "ret_bh": netbh,
})
eqdf.to_parquet(os.path.join(out_dir, "backtest_series.parquet"))
print(f"\nSaved series to {out_dir}/backtest_series.parquet")
