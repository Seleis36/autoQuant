"""Does the abnormal-volume ensemble add to the live BAB book? Equal-risk blend with the
risk weights computed on IS only (2018-2022 vol), return-level blend."""
from common import *
bab = S.bab_reference()
N = pd.read_parquet("refine_02_nets.parquet")
rows = [S.row(bab, "BAB alone")]
for k in ("ens_av|linear", "ens_av|quantile", "ens_av_resvol|linear", "ens_av_up|quantile"):
    a = N[k]
    j = pd.concat([bab, a], axis=1).dropna(); j.columns = ["bab", "av"]
    vis = j.loc[S.IS[0]:S.IS[1]].std()
    for wa in (0.33, 0.5):
        wts = pd.Series({"bab": (1 - wa) / vis["bab"], "av": wa / vis["av"]})
        wts = wts / wts.sum() * 2 * (1 - wa)  # keep BAB near its own gross (scale doesn't change Sharpe)
        blend = (j * wts).sum(axis=1)
        r = S.row(blend, f"BAB+{k} riskw {wa}"); r["rho"] = j.corr().iloc[0, 1]; rows.append(r)
print(pd.DataFrame(rows).set_index("name").round(2).to_string())
