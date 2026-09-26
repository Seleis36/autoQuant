"""Screen: CFTC VIX-futures positioning (TFF + legacy) vs forward VIXY returns.

Signals are built on the weekly report grid, mapped to session rows with the release lag
(first usable close = Monday after the Friday release), then correlated with forward VIXY
returns over 5 / 21 sessions. IS 2011-18 / OOS 2019-26.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
import numpy as np, pandas as pd
import vc_data as vc
import fetch_cot_vix as cot

P = vc.panel()
idx = P.index
tff = cot.fetch_tff().set_index("date")
leg = cot.fetch_legacy().set_index("date")
av_t, av_l = tff["avail_utc"], leg["avail_utc"]

W = pd.DataFrame(index=tff.index)
for g in ["dealer", "am", "lev", "oth", "nonrep"]:
    W[f"{g}_net"] = (tff[f"{g}_long"] - tff[f"{g}_short"]) / tff["oi"]
W["oi_log"] = np.log(tff["oi"])
L = pd.DataFrame(index=leg.index)
L["nc_net"] = (leg["nc_long"] - leg["nc_short"]) / leg["oi"]
L["c_net"] = (leg["c_long"] - leg["c_short"]) / leg["oi"]

def feats(df):
    out = {}
    for c in df.columns:
        x = df[c]
        out[c] = x
        out[c + "_z52"] = (x - x.rolling(52).mean()) / x.rolling(52).std()
        out[c + "_z156"] = (x - x.rolling(156, min_periods=104).mean()) / x.rolling(156, min_periods=104).std()
        out[c + "_d1"] = x.diff()
        out[c + "_d4"] = x.diff(4)
    return pd.DataFrame(out)

FT = cot.on_session_rows(feats(W), idx, av_t)
FL = cot.on_session_rows(feats(L), idx, av_l)
F = pd.concat([FT, FL], axis=1)

r = P["VIXY"].pct_change()
lr = np.log(P["VIXY"]).diff()
fwd = {h: lr.shift(-1).rolling(h).sum().shift(-(h - 1)) for h in (5, 21)}
rows = []
for c in F.columns:
    row = {"sig": c}
    for h, f in fwd.items():
        for k, (a, b) in {"IS": vc.IS, "OOS": vc.OOS}.items():
            d = pd.concat([F[c], f], axis=1).loc[a:b].dropna()
            # sample weekly (Mondays-ish: every 5th row) to avoid overlapping inflation
            d = d.iloc[::5]
            row[f"ic{h}_{k}"] = d.iloc[:, 0].corr(d.iloc[:, 1], method="spearman")
    rows.append(row)
res = pd.DataFrame(rows).set_index("sig").round(3)
pd.set_option("display.width", 200); pd.set_option("display.max_rows", 200)
print(res)
print(W.describe().round(3))
print(W.resample("YE").mean().round(3))
