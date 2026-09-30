"""exp02 — the one surviving feature, OI / market cap (leverage intensity). What is it?

1. XS rank correlations with: log mcap (size), raw retail L/S ratio (retail-crowding-xs),
   beta, 30d vol, mom30, 30d funding, 30d USD volume / mcap (turnover).
2. Quintile spreads (forward 7d excess return, IS / OOS) - why a strong IC but a modest book?
3. Variants: linear rank, q20/q50, h14/h30, residual on log mcap / on the L/S ratio / on
   turnover, frozen IS coin means, long-leg and short-leg decomposition.
4. Correlation with retail-crowding-xs, and a pre-declared 50/50 rank composite of the two.
"""
import os
import sys
import importlib.util
import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("rcx", os.path.join(_HERE, "..", "retail-crowding-xs", "common.py"))
rcx = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rcx)
sys.path.insert(0, os.path.join(rcx.ROOT, "code", "crypto-alts", "shared"))
import cmc  # noqa: E402
import funding_panel as fp  # noqa: E402
import research_lib as rl  # noqa: E402

close, vol, met, mask = rcx.load()
IS, OOS = rcx.IS, rcx.OOS
beta = rcx.btc_beta(close)
ret = close.pct_change(fill_method=None)
oiv = met["sum_open_interest_value"].where(met["sum_open_interest_value"] > 0)
idmap = cmc.yahoo_map(close)
mcap = (cmc.wide("circulatingSupply", idmap, index=close.index) * close)
mcap = mcap.where(mcap > 0)
lev = np.log(oiv / mcap)
x = np.log(met["count_long_short_ratio"])
fund, _ = fp.daily_funding(close.columns)
fund = fund.reindex(index=close.index, columns=close.columns)
turnover = np.log(vol.rolling(30, min_periods=20).mean() / mcap)

cands = {"logmcap": np.log(mcap), "ls_ratio": x, "beta": beta, "vol30": ret.rolling(30, min_periods=20).std(),
         "mom30": close.pct_change(30, fill_method=None), "fund30": fund.rolling(30, min_periods=20).mean(),
         "turnover": turnover}
lr = lev.where(mask).rank(axis=1)
print("XS Spearman corr of log(OI/mcap) with:")
for k, v in cands.items():
    c = lr.corrwith(v.where(mask).rank(axis=1), axis=1)
    print(f"  {k:9s} IS {c.loc[IS[0]:IS[1]].mean():+.2f}  OOS {c.loc[OOS[0]:].mean():+.2f}")

# quintile spreads of forward 7d excess returns
fwd = close.shift(-7) / close - 1
fwd = fwd.sub(fwd.where(mask).mean(axis=1), axis=0).where(mask)
q = lev.where(mask).rank(axis=1, pct=True)
for per, (a, b) in {"IS": IS, "OOS": OOS}.items():
    rowq = {}
    for i in range(5):
        sel = (q > i / 5) & (q <= (i + 1) / 5)
        rowq[f"Q{i+1}"] = fwd.where(sel).loc[a:b].stack().mean() * 1e4
    print(per, "fwd 7d excess bp by OI/mcap quintile (Q5 = most levered):", {k: round(v, 1) for k, v in rowq.items()})


def resid(y, xx):
    ym, xm = y.where(mask).rank(axis=1), xx.where(mask).rank(axis=1)
    yd, xd = ym.sub(ym.mean(axis=1), axis=0), xm.sub(xm.mean(axis=1), axis=0)
    b = (yd * xd).sum(axis=1) / (xd ** 2).sum(axis=1)
    return yd - xd.mul(b, axis=0)


rows, nets = [], {}


def run(sig, name, h=7, weight="q30"):
    if weight == "lin":
        w = rcx.linear_ls(sig, mask)
    else:
        w = rcx.quantile_ls(sig, mask, q=float(weight[1:]) / 100)
    w = rcx.tranche(rcx.beta_neutral(w, beta), h)
    net, row = rcx.evaluate(w, close, name)
    rows.append(row)
    nets[name] = net
    return net, w


base, wb = run(-lev, "-oi_mcap q30 h7 (exp01 cell)")
run(-lev, "linear", weight="lin")
run(-lev, "q20", weight="q20")
run(-lev, "q50", weight="q50")
run(-lev, "h14", h=14)
run(-lev, "h30", h=30)
for k in ("logmcap", "ls_ratio", "turnover", "beta"):
    run(-resid(lev, cands[k]), f"resid on {k}")
fe = lev.loc[IS[0]:IS[1]].mean()
run(-pd.DataFrame(np.tile(fe.values, (len(lev), 1)), index=lev.index, columns=lev.columns), "frozen IS coin means")
run(-cands["logmcap"], "control: small-minus-big (-logmcap)")
run(cands["logmcap"], "control: big-minus-small (+logmcap)")
rc, _ = run(-x, "retail-crowding-xs base")
comp = (-lev).where(mask).rank(axis=1, pct=True) + (-x).where(mask).rank(axis=1, pct=True)
run(comp, "composite rank(-oi_mcap) + rank(-ls_ratio)")
pd.set_option("display.width", 220)
res = pd.DataFrame(rows)
print(res.round(2).to_string(index=False))
res.to_csv("exp02_results.csv", index=False)
print("daily P&L corr oi_mcap vs retail-crowding:", round(base.loc[IS[0]:].corr(rc.loc[IS[0]:]), 3))

# legs (gross)
we = wb.shift(1)
ew = ret.where(mask.shift(1).fillna(False).astype(bool)).mean(axis=1)
lw, sw = we.clip(lower=0), -we.clip(upper=0)
lr_ = (lw * ret.fillna(0)).sum(axis=1) / lw.sum(axis=1).replace(0, np.nan) - ew
sr_ = ew - (sw * ret.fillna(0)).sum(axis=1) / sw.sum(axis=1).replace(0, np.nan)
for nm, s in {"long-EW": lr_, "EW-short": sr_}.items():
    s = s.loc[IS[0]:]
    print(nm, "SR full", round(rl.perf_stats(s)["Sharpe"], 2), "IS", round(rl.perf_stats(s.loc[:IS[1]])["Sharpe"], 2),
          "OOS", round(rl.perf_stats(s.loc[OOS[0]:])["Sharpe"], 2))
sw_ = wb.loc[IS[0]:]
print("most-shorted:", (sw_ < 0).mean().sort_values(ascending=False).head(6).round(2).to_dict())
print("most-longed:", (sw_ > 0).mean().sort_values(ascending=False).head(6).round(2).to_dict())
