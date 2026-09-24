"""exp02 — refine the only family that survived exp01: contrarian funding level.

Axes (all reported): lookback L in {14, 30, 60, 90}; holding h in {7, 14, 30};
weighting {quantile q=0.3, linear rank}; neutrality {dollar, beta (EWM-60 beta to BTC)}.
Plus leg decomposition and beta of the dollar-neutral book.
"""
import itertools
import numpy as np
import pandas as pd
import common as c
import research_lib as rl

close, vol, fund, mask = c.load()
ret = close.pct_change()
btc = ret["BTC-USD"]

# EWM-60 beta to BTC, known at close t
hl = 60
cov = ret.ewm(halflife=hl, min_periods=60).cov(btc)
varb = btc.ewm(halflife=hl, min_periods=60).var()
beta = cov.div(varb, axis=0).clip(-0.5, 3.0)


def beta_neutral(w, beta):
    """Scale the long and short legs so that the book beta is zero, keeping gross = 1."""
    b = beta.reindex_like(w).fillna(1.0)
    lw, sw = w.clip(lower=0), w.clip(upper=0)
    bl = (lw * b).sum(axis=1)
    bs = -(sw * b).sum(axis=1)
    # scale long by a, short by s so a*bl = s*bs and a*L + s*S = 1 (L=S=0.5)
    a = bs / (bl + bs)
    s = bl / (bl + bs)
    out = lw.mul(2 * a, axis=0) + sw.mul(2 * s, axis=0)
    return out.fillna(0.0)


if __name__ == "__main__":
    rows, nets = [], {}
    for L, h, wt, neu in itertools.product((14, 30, 60, 90), (7, 14, 30), ("q30", "lin"), ("dollar", "beta")):
        sig = -fund.rolling(L, min_periods=int(L * 0.7)).mean()
        if wt == "q30":
            w = rl.quantile_weights(sig, mask, q=0.3)
        else:
            w = rl.linear_weights(sig.where(mask).rank(axis=1), mask)
        if neu == "beta":
            w = beta_neutral(w, beta)
        w = c.tranche(w, h)
        name = f"L{L}_h{h}_{wt}_{neu}"
        net, row = c.evaluate(w, close, name)
        wb = (w.shift(1) * beta.reindex_like(w)).sum(axis=1)
        row["bookBeta"] = wb.loc[c.FULL[0]:].mean()
        rows.append(row)
        nets[name] = net
    res = pd.DataFrame(rows).set_index("name")
    res.to_csv("exp02_results.csv")
    pd.set_option("display.width", 200)
    print(rl.fmt(res).to_string())

    # leg decomposition for the L30 h7 q30 dollar cell
    sig = -fund.rolling(30, min_periods=21).mean()
    w = c.tranche(rl.quantile_weights(sig, mask, q=0.3), 7)
    ew = mask.astype(float).div(mask.sum(axis=1), axis=0)
    legs = {"long_leg": w.clip(lower=0) * 2, "short_leg_as_long": -w.clip(upper=0) * 2, "EW_universe": ew}
    for k, lw in legs.items():
        _, row = c.evaluate(lw, close, k)
        print(k, {kk: round(v, 2) for kk, v in row.items() if kk != "name"})
    lr = rl.backtest_xs(legs["long_leg"] - ew, close, 0)[0]
    sr = rl.backtest_xs(ew - legs["short_leg_as_long"], close, 0)[0]
    for nm, x in (("long-minus-EW (gross)", lr), ("EW-minus-short (gross)", sr)):
        print(nm, rl.split_stats(x.loc[c.FULL[0]:], c.SPLITS)["Sharpe"].round(2).to_dict())
