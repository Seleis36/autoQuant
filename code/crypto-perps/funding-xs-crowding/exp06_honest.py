"""exp06 — honest selection of the funding sleeve and the combined book.

1. IS-only selection among the 48 exp02 cells.
2. Pre-declared ensemble (no selection): mean XS rank of -funding over L in {14,30,60,90},
   q30, beta-neutral, 7-day tranches.
3. Robustness of the ensemble: universe n_top in {15, 20, 30}, cost 5/10/20 bp, 1-day extra lag.
4. Combined book 50/50 with a plain beta-neutral BAB sleeve (exp05), same robustness.
5. Deflated Sharpe with the total number of cells evaluated in this idea.
"""
import numpy as np
import pandas as pd
import common as c
import research_lib as rl
from exp02_refine import beta_neutral, beta

e2 = pd.read_csv("exp02_results.csv", index_col=0)
best_is = e2.SR_IS.idxmax()
print("IS-selected cell:", best_is, e2.loc[best_is, ["SR_IS", "SR_OOS", "SR_full"]].round(2).to_dict())
print("exp02 grid mean  IS %.2f  OOS %.2f  full %.2f" % tuple(e2[["SR_IS", "SR_OOS", "SR_full"]].mean()))


def funding_ensemble(fund, mask, beta, lags=0, Ls=(14, 30, 60, 90), h=7):
    f = fund.shift(lags)
    ranks = [(-f.rolling(L, min_periods=int(L * .7)).mean()).where(mask).rank(axis=1, pct=True) for L in Ls]
    sig = sum(ranks) / len(ranks)
    return c.tranche(beta_neutral(rl.quantile_weights(sig, mask, q=0.3), beta), h)


def bab(mask, beta, h=14):
    return c.tranche(beta_neutral(rl.quantile_weights(-beta, mask & beta.notna(), q=0.3), beta), h)


rows, nets = [], {}
for n_top in (15, 20, 30):
    close, vol, fund, mask = c.load(n_top=n_top)
    b = beta.reindex_like(close)
    for lag in ((0, 1) if n_top == 20 else (0,)):
        wf = funding_ensemble(fund, mask, b, lags=lag)
        wb = bab(mask, b)
        for cost in ((5, 10, 20) if (n_top == 20 and lag == 0) else (10,)):
            for nm, w in (("fund_ens", wf), ("bab", wb), ("combo", 0.5 * wf + 0.5 * wb)):
                key = f"{nm}_n{n_top}_lag{lag}_c{cost}"
                net, row = c.evaluate(w, close, key, cost=cost)
                rows.append(row)
                nets[key] = net
res = pd.DataFrame(rows).set_index("name")
res.to_csv("exp06_results.csv")
pd.set_option("display.width", 200)
print(rl.fmt(res).to_string())
pd.DataFrame(nets).to_parquet("exp06_nets.parquet")

n_trials = 52 + 48 + 80 + 16 + 3  # exp01 + exp02 + exp03 + exp05 pair + exp05 combo cells
for key in ("fund_ens_n20_lag0_c10", "combo_n20_lag0_c10"):
    r = nets[key].loc[c.OOS[0]:]
    sr = r.mean() / r.std() * np.sqrt(365)
    print(key, "OOS SR %.2f" % sr, "DSR(N=%d) %.3f" % (n_trials,
          rl.deflated_sharpe(sr, len(r), n_trials, skew=r.skew(), kurt=r.kurt() + 3)))
