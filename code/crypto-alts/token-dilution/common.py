"""token-dilution: circulating-supply growth and locked-supply overhang (Guo 2026, "Token dilution
and the cross-section of cryptocurrency returns") on the liquid-alt book. Supply from weekly
CoinMarketCap snapshots, known one day after the snapshot date, forward-filled daily."""
import os, sys, warnings
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "shared"))
sys.path.insert(0, os.path.join(_HERE, "..", "..", "shared"))
import research_lib as rl  # noqa
import study as S  # noqa
import cmc  # noqa


def supply_panels(c):
    snaps = cmc.load_weekly()
    idmap = cmc.yahoo_map(c, snaps)
    W = {f: cmc.wide(f, idmap, snaps, c.index) for f in
         ("circulatingSupply", "totalSupply", "maxSupply", "marketCap", "dateAdded", "cmcRank")}
    return idmap, W


def ic_table(sig, fwd, mask, min_n=8):
    s = sig.where(mask); ok = s.notna() & fwd.notna(); n = ok.sum(axis=1)
    rs = s.where(ok).rank(axis=1); rf = fwd.where(ok).rank(axis=1)
    rs = rs.sub(rs.mean(axis=1), axis=0); rf = rf.sub(rf.mean(axis=1), axis=0)
    ic = ((rs * rf).sum(axis=1) / np.sqrt((rs ** 2).sum(axis=1) * (rf ** 2).sum(axis=1))).where(n >= min_n).dropna()
    out = {"avg_n": n[n >= min_n].mean()}
    for k, (a, b) in S.SPLITS.items():
        x = ic.loc[a:b]; out[f"IC_{k}"] = x.mean(); out[f"t_{k}"] = rl.newey_west_t(x.values, 30)
    return out
