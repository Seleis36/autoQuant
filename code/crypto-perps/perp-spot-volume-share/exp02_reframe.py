"""exp02 — re-framings of perp-vs-spot activity (declared before running):

A. Time series, market-wide speculation: BTC's own share s_btc = log(perp qv / spot qv), and the
   aggregate share over the universe; z vs trailing 365d. Forward BTC 7/30d IC; rule
   "BTC x inverse-vol, flat when z > 1" vs inverse-vol alone.
B. Leveraged-flow differential: d = perp taker-buy share - spot taker-buy share
   (TakerBuyQuote / QuoteVolume on each venue, Binance daily klines). Aggressive buying on the
   levered venue in excess of the spot venue = levered speculation. Cross-sectional 7d mean,
   raw and own-90d demeaned, both signs, h7, q30 beta-neutral (same set-up as exp01);
   time-series for BTC (7d mean, z vs 365d).
"""
import os
import importlib.util
import numpy as np
import pandas as pd

from common import load, IS, OOS, _spot_base
import research_lib as rl
import funding_panel as fp
import venues

_spec = importlib.util.spec_from_file_location(
    "rcx", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "retail-crowding-xs", "common.py"))
rcx = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rcx)

close, vol, pq, sq, share, mask = load()
beta = rcx.btc_beta(close)

# taker-buy shares
ptb, stb = {}, {}
for t in close.columns:
    sym = fp.PERP_OF.get(t)
    pp = os.path.join(rl.DATA_DIR, f"BINANCE_{sym}_PERP_1d.parquet")
    sp = venues.binance_path(_spot_base(sym)) if sym else None
    if sym and os.path.exists(pp) and os.path.exists(sp):
        p, s = pd.read_parquet(pp), pd.read_parquet(sp)
        if len(p) and len(s):
            ptb[t] = p["TakerBuyQuote"] / p["QuoteVolume"].where(p["QuoteVolume"] > 0)
            stb[t] = s["TakerBuyQuote"] / s["QuoteVolume"].where(s["QuoteVolume"] > 0)
ptb = pd.DataFrame(ptb).reindex(index=close.index, columns=close.columns)
stb = pd.DataFrame(stb).reindex(index=close.index, columns=close.columns)
d = (ptb - stb)
d7 = d.rolling(7, min_periods=5).mean()

rows = []
SPL = {"full": ("2020-09-01", "2026-12-31"), "IS": IS, "OOS": OOS}


def ev_xs(sig, name):
    w = rcx.tranche(rcx.beta_neutral(rcx.quantile_ls(sig, mask), beta), 7)
    net, st = rl.backtest_xs(w, close, cost_bps=10.0)
    r = {"name": name}
    for k, (a, b) in SPL.items():
        r[f"SR_{k}"] = rl.perf_stats(net.loc[a:b])["Sharpe"]
    r["Turn"] = st["Turnover_ann"]
    rows.append(r)


for sign in (-1, 1):
    ev_xs(sign * d7, f"B xs {'-' if sign < 0 else '+'}flowdiff7 raw")
    ev_xs(sign * (d7 - d.rolling(90, min_periods=60).mean()), f"B xs {'-' if sign < 0 else '+'}flowdiff7 dm90")
ic = rcx.ic_table(-d7, close, mask)
for per, (a, b) in {"IS": IS, "OOS": OOS}.items():
    seg = ic.loc[a:b]
    print(f"B contrarian flowdiff7 IC {per}:", {h: round(seg[h].mean(), 3) for h in seg})

# time series on BTC
btc = close["BTC-USD"]
ret = btc.pct_change()
vt = rl.vol_target_scalar(ret, target=0.40, halflife=20, cap=1.0)
agg = np.log(pq.where(mask).sum(axis=1) / sq.where(mask).sum(axis=1)).where(mask.sum(axis=1) >= 15)


def zf(x, win=365):
    return (x - x.rolling(win, min_periods=win // 2).mean()) / x.rolling(win, min_periods=win // 2).std()


ts = {"A s_btc (7d mean)": share["BTC-USD"].rolling(7, min_periods=5).mean(),
      "A aggregate share (7d mean)": agg.rolling(7, min_periods=5).mean(),
      "B btc flowdiff7": d7["BTC-USD"]}
for nm, x in ts.items():
    z = zf(x)
    for h in (7, 30):
        f = btc.shift(-h) / btc - 1
        for per, (a, b) in {"IS": IS, "OOS": OOS}.items():
            g = pd.concat([z, f], axis=1).loc[a:b].dropna()
            print(f"{nm} h{h} {per}: IC {g.corr(method='spearman').iloc[0, 1]:+.3f} (n={len(g)})")
    for rule, w in {"flat if z>1": (z <= 1).astype(float), "flat if z<-1": (z >= -1).astype(float)}.items():
        w = (w.where(z.notna()) * vt)
        start = z.dropna().index[0]
        net, st = rl.backtest(w.fillna(0).loc[start:], btc.loc[start:], cost_bps=10)
        r = {"name": f"{nm}: {rule} x inv-vol", "SR_full": rl.perf_stats(net)["Sharpe"],
             "SR_IS": rl.perf_stats(net.loc[:IS[1]])["Sharpe"], "SR_OOS": rl.perf_stats(net.loc[OOS[0]:])["Sharpe"],
             "Turn": st["Turnover_ann"]}
        rows.append(r)
start = zf(ts["A s_btc (7d mean)"]).dropna().index[0]
net, _ = rl.backtest(vt.loc[start:], btc.loc[start:], cost_bps=10)
rows.append({"name": "reference: BTC inverse-vol alone", "SR_full": rl.perf_stats(net)["Sharpe"],
             "SR_IS": rl.perf_stats(net.loc[:IS[1]])["Sharpe"], "SR_OOS": rl.perf_stats(net.loc[OOS[0]:])["Sharpe"]})
pd.set_option("display.width", 200)
print(pd.DataFrame(rows).round(2).to_string(index=False))
pd.DataFrame(rows).to_csv("exp02_results.csv", index=False)
