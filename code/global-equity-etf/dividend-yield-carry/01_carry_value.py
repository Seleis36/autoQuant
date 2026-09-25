"""Cross-country carry/value on the 9 country ETFs + SPY, monthly.
carry: unhedged ETF excess return = equity carry (D/P - r_loc) + FX carry (r_loc - r_US) = D/P - r_US,
so cross-sectionally the carry signal is the dividend (distribution) yield.
Signals (all known at the month-end close):
  dy      exponentially-smoothed distribution yield (tau = 2y), ex-date dividends / prior unadjusted close
  dy_rel  log dy minus its trailing 5y mean (cheap vs own history)
  ltr     -(log P[t-252] - log P[t-1260])  5y-to-1y long-term reversal (price-based value)
  mom     12-1 momentum (for the value+momentum combination, Asness-Moskowitz-Pedersen 2013)
"""
import sys, os
sys.path.insert(0, "../shared")
import numpy as np, pandas as pd
import data as D, xs

START = "2001-01-01"
SPL = {"FULL": ("2001", "2026"), "IS": ("2001", "2012"), "OOS": ("2013", "2026")}
U = xs.COUNTRY10
C = D.load_panel(U, "Close", start="1996-01-01")
ret = C.pct_change()


def dy_signal(tau_years=2.0):
    out = {}
    for t in U:
        d = D.load_dividends(t)
        p = D.load_unadjusted_close(t).reindex(C.index).ffill()
        x = (d.groupby(d.index).sum().reindex(C.index).fillna(0.0) / p.shift(1)).fillna(0.0)
        delta = np.exp(-1.0 / (252 * tau_years))
        S = x.copy() * 0.0
        acc = 0.0
        for i, v in enumerate(x.values):
            acc = acc * delta + v
            S.iloc[i] = acc
        dy = S / tau_years
        first = x[x > 0].index.min()
        valid = C.index >= (first + pd.Timedelta(days=int(365 * tau_years)))
        out[t] = dy.where(valid & C[t].notna())
    return pd.DataFrame(out)


dy = dy_signal(2.0)
lp = np.log(C)
sig = {
    "dy": dy,
    "dy_rel": np.log(dy) - np.log(dy).rolling(1260, min_periods=756).mean(),
    "ltr": -(lp.shift(252) - lp.shift(1260)),
    "mom": lp.shift(21) - lp.shift(252),
}
def z(s):
    return s.sub(s.mean(axis=1), axis=0).div(s.std(axis=1), axis=0)
sig["dy+mom"] = z(sig["dy"]) + z(sig["mom"])
sig["ltr+mom"] = z(sig["ltr"]) + z(sig["mom"])
sig["dyrel+mom"] = z(sig["dy_rel"]) + z(sig["mom"])
sig["dy+ltr"] = z(sig["dy"]) + z(sig["ltr"])
sig["dy+ltr+mom"] = z(sig["dy"]) + z(sig["ltr"]) + z(sig["mom"])

reb = xs.rebalance_dates(C.loc[START:].index, "M")
rows = []
nets = {}
for name, s in sig.items():
    for scheme in ["rank", "tercile"]:
        S = s.loc[reb]
        mask = S.notna() & C.loc[reb].notna()
        mask = mask.where(mask.sum(axis=1) >= 6, False)       # need >= 6 names to rank
        w = xs.rank_weights(S, mask) if scheme == "rank" else xs.tercile_weights(S, mask, k=3)
        w = xs.vol_target_book(w, ret, target=0.10)
        net, gross, turn, We = xs.run(w, C.loc[START:], cost_bps=5.0, spy_cost_bps=1.0)
        r = xs.summarize(net, SPL, turn, We, name=f"{name}|{scheme}")
        g = xs.summarize(gross, SPL, name="g")
        r["OOS_SR_gross"] = g["OOS_SR"]
        rows.append(r); nets[f"{name}|{scheme}"] = net
df = pd.DataFrame(rows)
pd.set_option("display.width", 250)
print(df[["FULL_SR", "IS_SR", "OOS_SR", "OOS_SR_gross", "FULL_CAGR", "MaxDD", "Vol", "t_NW", "Turn/yr", "Gross", "Net"]].round(2).to_string())
pd.DataFrame(nets).to_parquet("nets_01.parquet")
# which countries does dy favour? average rank position
print("\nmean dy (%) by year-end:")
print((dy.loc[reb].groupby(reb.year).last() * 100).round(2).iloc[::3].to_string())
