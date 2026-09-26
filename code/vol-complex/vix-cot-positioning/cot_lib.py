"""Feature builders for vix-cot-positioning (weekly COT -> session rows, release-lagged)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
import numpy as np, pandas as pd
import vc_data as vc
import fetch_cot_vix as cot


def weekly_nets():
    tff = cot.fetch_tff().set_index("date")
    W = pd.DataFrame(index=tff.index)
    for g in ["dealer", "am", "lev", "oth", "nonrep"]:
        W[f"{g}_net"] = (tff[f"{g}_long"] - tff[f"{g}_short"]) / tff["oi"]
        W[f"{g}_gross"] = (tff[f"{g}_long"] + tff[f"{g}_short"]) / tff["oi"]
    W["oi"] = tff["oi"]
    return W, tff["avail_utc"]


def zscore(x, win, minp=None):
    minp = minp or win
    return (x - x.rolling(win, min_periods=minp).mean()) / x.rolling(win, min_periods=minp).std()


def session_features(idx, wins=(52, 104, 156)):
    W, av = weekly_nets()
    out = {}
    for c in ["am_net", "lev_net", "dealer_net", "oth_net"]:
        out[c] = W[c]
        for w in wins:
            out[f"{c}_z{w}"] = zscore(W[c], w, int(w * 0.67))
        out[f"{c}_pct104"] = W[c].rolling(104, min_periods=70).rank(pct=True)
    return cot.on_session_rows(pd.DataFrame(out), idx, av)
