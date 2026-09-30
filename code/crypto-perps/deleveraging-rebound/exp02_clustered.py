"""exp02 — does the OI flush add to plain price-drop reversal once events are clustered by
date and returns are market-adjusted?

Uses the exp01 --all panel (Binance spot, 63 coins). For each event type:
  raw   forward return minus the coin's mean (exp01's x_h)
  mkt   forward return minus the equal-weight forward return of all coins with data that day
  t_cl  t-stat of the per-DATE average (events on the same day are one observation)
Pooled regression of the market-adjusted forward return on z_r1, z_doi, z_r1*z_doi with
date-clustered standard errors.
Market-level version: on days when the median coin has z_doi <= -1 and the EW return is
<= -1 sigma ("market deleveraging day"), forward EW-market and BTC returns.
"""
import numpy as np
import pandas as pd

P = pd.read_parquet("exp01_panel_all.parquet")
P = P.replace([np.inf, -np.inf], np.nan)
P["date"] = P.index
H = (1, 3, 7, 14)
for h in H:
    mk = P.groupby("date")[f"f{h}"].transform("mean")
    P[f"m{h}"] = P[f"f{h}"] - mk
P["period"] = np.where(P.index <= "2023-12-31", "IS", "OOS")

ev = {
    "LIQ_DOWN": (P.z_doi <= -2) & (P.z_r1 <= -1),
    "PX_DOWN": P.z_r1 <= -2,
    "PX_DOWN_noOI": (P.z_r1 <= -2) & (P.z_doi > -1),
    "PX_DOWN_withOI": (P.z_r1 <= -2) & (P.z_doi <= -1),
    "BUILD_UP": (P.z_doi >= 2) & (P.r1 > 0),
}
rows = []
for name, m in ev.items():
    for per in ("IS", "OOS"):
        g = P[m & (P.period == per)]
        row = {"event": name, "per": per, "n": len(g), "dates": g.date.nunique()}
        for h in (1, 3, 7):
            d = g.groupby("date")[f"m{h}"].mean().dropna()
            row[f"mkt{h}_bp"] = d.mean() * 1e4
            row[f"tcl{h}"] = d.mean() / d.std() * np.sqrt(len(d) / h) if len(d) > 2 else np.nan
        rows.append(row)
pd.set_option("display.width", 220)
print("market-adjusted forward returns, date-clustered (t divides n by h for overlap)")
print(pd.DataFrame(rows).round(1).to_string(index=False))

# pooled regression, date-clustered SE
for per in ("IS", "OOS"):
    g = P[P.period == per].dropna(subset=["m1", "m3", "z_r1", "z_doi"])
    X = np.column_stack([np.ones(len(g)), g.z_r1.clip(-5, 5), g.z_doi.clip(-5, 5),
                         (g.z_r1.clip(-5, 5) * g.z_doi.clip(-5, 5))])
    for h in (1, 3):
        y = g[f"m{h}"].clip(-1, 1).values
        b = np.linalg.lstsq(X, y, rcond=None)[0]
        e = y - X @ b
        XtXi = np.linalg.inv(X.T @ X)
        meat = np.zeros((4, 4))
        for _, idx in pd.Series(np.arange(len(g)), index=g.date.values).groupby(level=0):
            s = X[idx.values].T @ e[idx.values]
            meat += np.outer(s, s)
        se = np.sqrt(np.diag(XtXi @ meat @ XtXi)) * np.sqrt(h)
        print(per, f"h{h} coef bp (z_r1, z_doi, z_r1*z_doi):", np.round(b[1:] * 1e4, 1),
              "t_cl:", np.round(b[1:] / se[1:], 2))

# market-level deleveraging days
day = P.groupby("date").agg(med_zdoi=("z_doi", "median"), ew=("r1", "mean"), n=("coin", "size"))
day["z_ew"] = day.ew / day.ew.rolling(90, min_periods=60).std().shift(1)
fw = P.groupby("date")[["f1", "f3", "f7"]].mean()
btc = P[P.coin == "BTC-USD"][["f1", "f3", "f7"]]
day = day.join(fw).join(btc, rsuffix="_btc")
base = day[day.n >= 20]
for cond_name, cond in {"mkt delever (med z_doi<=-1 & z_ew<=-1)": (base.med_zdoi <= -1) & (base.z_ew <= -1),
                        "mkt drop only (z_ew<=-1.5)": base.z_ew <= -1.5,
                        "mkt drop w/o delever": (base.z_ew <= -1.5) & (base.med_zdoi > -0.5)}.items():
    for per, (a, b_) in {"IS": ("2020", "2023"), "OOS": ("2024", "2026")}.items():
        g = base.loc[a:b_][cond.loc[a:b_]]
        u = base.loc[a:b_]
        print(f"{cond_name:42s} {per}: n={len(g):3d}  EW f1/f3/f7 {g.f1.mean()*1e4:+.0f}/{g.f3.mean()*1e4:+.0f}/{g.f7.mean()*1e4:+.0f} bp"
              f"  BTC f1/f3/f7 {g.f1_btc.mean()*1e4:+.0f}/{g.f3_btc.mean()*1e4:+.0f}/{g.f7_btc.mean()*1e4:+.0f}"
              f"  (uncond EW f3 {u.f3.mean()*1e4:+.0f})")
