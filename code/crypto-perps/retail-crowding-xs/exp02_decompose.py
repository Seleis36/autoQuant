"""exp02 — what is the raw-level retail L/S signal? Momentum, beta, funding, size, vol, or a
coin fixed effect?

1. Daily XS rank correlations of the raw log ratio with candidate explanations.
2. Residual signal: raw ratio regressed cross-sectionally (daily) on momentum 7/30/90,
   beta, 30d vol, log mcap, 30d funding -> residual traded the same way (h7, q30, beta-neutral).
3. Fixed-effect test: a book frozen on each coin's IS-average ratio (rank computed once on
   2022-03..2023-12, then held in OOS on the PIT universe) vs the live signal.
4. Controls traded alone: momentum 30/90, funding 30d, BAB (low minus high beta).
5. Gross-of-cost numbers for the base cell.
"""
import os
import sys
import numpy as np
import pandas as pd

from common import (load, btc_beta, beta_neutral, quantile_ls, tranche, evaluate, ic_table,
                    IS, OOS, ROOT)
import research_lib as rl
import funding_panel as fp
sys.path.insert(0, os.path.join(ROOT, "code", "crypto-alts", "shared"))
import cmc  # noqa: E402

close, vol, met, mask = load()
beta = btc_beta(close)
x = np.log(met["count_long_short_ratio"])
ret = close.pct_change(fill_method=None)
fund, _ = fp.daily_funding(close.columns)
fund = fund.reindex(index=close.index, columns=close.columns)
idmap = cmc.yahoo_map(close)
mcap = (cmc.wide("circulatingSupply", idmap, index=close.index) * close)

cands = {
    "mom7": close.pct_change(7, fill_method=None),
    "mom30": close.pct_change(30, fill_method=None),
    "mom90": close.pct_change(90, fill_method=None),
    "beta": beta,
    "vol30": ret.rolling(30, min_periods=20).std(),
    "logmcap": np.log(mcap.where(mcap > 0)),
    "fund30": fund.rolling(30, min_periods=20).mean(),
    "toptrader_acc": np.log(met["count_toptrader_long_short_ratio"]),
    "toptrader_pos": np.log(met["sum_toptrader_long_short_ratio"]),
}
xr = x.where(mask).rank(axis=1)
print("mean daily XS Spearman corr of raw log L/S ratio with:")
for k, v in cands.items():
    c = xr.corrwith(v.where(mask).rank(axis=1), axis=1)
    print(f"  {k:14s} {c.loc[IS[0]:IS[1]].mean():+.2f} IS  {c.loc[OOS[0]:].mean():+.2f} OOS")


def xs_resid(y, Xs):
    """Daily cross-sectional OLS residual of y on the columns in Xs (dict of frames)."""
    out = pd.DataFrame(np.nan, index=y.index, columns=y.columns)
    for d in y.index:
        m = mask.loc[d]
        if m.sum() < 8:
            continue
        cols = m[m].index
        Y = y.loc[d, cols]
        X = pd.DataFrame({k: v.loc[d, cols] for k, v in Xs.items()})
        ok = Y.notna() & X.notna().all(axis=1)
        if ok.sum() < len(Xs) + 4:
            continue
        Xa = np.column_stack([np.ones(ok.sum()), X[ok].rank().values])
        b = np.linalg.lstsq(Xa, Y[ok].rank().values, rcond=None)[0]
        out.loc[d, Y[ok].index] = Y[ok].rank().values - Xa @ b
    return out


rows = []


def run(sig, name, h=7, cost=10.0):
    w = tranche(beta_neutral(quantile_ls(sig, mask), beta), h)
    net, row = evaluate(w, close, name, cost=cost)
    rows.append(row)
    return net, w


base_net, base_w = run(-x, "-raw_h7 (base)")
run(-x, "-raw_h7 gross", cost=0.0)
run(-x.rolling(7, min_periods=5).mean(), "-raw_sm7_h7")
for h in (14, 30):
    run(-x, f"-raw_h{h}", h=h)
for k in ("mom30", "mom90", "fund30", "beta", "vol30", "logmcap"):
    run(-xs_resid(x, {k: cands[k]}), f"-raw resid[{k}]_h7")
res_all = xs_resid(x, {k: cands[k] for k in ("mom7", "mom30", "mom90", "beta", "vol30", "fund30")})
run(-res_all, "-raw resid[mom7,30,90,beta,vol,fund]_h7")
run(-xs_resid(x, {k: cands[k] for k in ("mom7", "mom30", "mom90", "beta", "vol30", "fund30", "logmcap")}),
    "-raw resid[all + logmcap]_h7")

# fixed effect: freeze each coin's IS-average level, trade it OOS on the PIT universe
fe = x.loc[IS[0]:IS[1]].mean()
fe_sig = pd.DataFrame(np.tile(fe.values, (len(x), 1)), index=x.index, columns=x.columns)
fe_net, _ = run(-fe_sig, "FROZEN IS coin means_h7 (OOS column is the test)")
# within-coin variation only (level minus the coin's expanding mean)
run(-(x - x.expanding(min_periods=60).mean()), "-within (x - expanding mean)_h7")

# controls alone
run(cands["mom30"], "+mom30_h7 (control)")
run(-cands["mom30"], "-mom30_h7 (control)")
run(cands["mom90"], "+mom90_h7 (control)")
run(-cands["fund30"], "-fund30_h7 (control)")
run(-beta, "BAB low-beta_h7 (control)")
run(-cands["toptrader_acc"], "-toptrader_acc_h7")
run(-cands["toptrader_pos"], "-toptrader_pos_h7")

pd.set_option("display.width", 220)
res = pd.DataFrame(rows)
print(res.round(2).to_string(index=False))
res.to_csv("exp02_results.csv", index=False)

# correlation of daily P&L with controls
nets = {}
for nm, sig in {"mom30": cands["mom30"], "rev30": -cands["mom30"], "fund": -cands["fund30"], "BAB": -beta}.items():
    w = tranche(beta_neutral(quantile_ls(sig, mask), beta), 7)
    nets[nm], _ = rl.backtest_xs(w, close, 10.0)
C = pd.DataFrame(nets).loc[IS[0]:]
print("P&L corr of base with:", C.corrwith(base_net.loc[IS[0]:]).round(2).to_dict())
# per-coin: average signal rank and share of time long / short
sw = base_w.loc[IS[0]:]
print("most-shorted coins:", (sw.clip(upper=0) < 0).mean().sort_values(ascending=False).head(8).round(2).to_dict())
print("most-longed coins:", (sw.clip(lower=0) > 0).mean().sort_values(ascending=False).head(8).round(2).to_dict())
