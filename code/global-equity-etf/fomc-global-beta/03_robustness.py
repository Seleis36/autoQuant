"""F10_EW9 robustness: per-event distribution, concentration, sub-periods, leave-one-country-out,
cost sensitivity, shifted windows (placebo), and the value added to intl-relative-trend."""
exec(open("02_books.py").read().split("rows = []; nets = {}")[0])
import xs
earn = off.isin([-1, 0]); w = in_window(earn)
ev_ret = []
evs = [d for d in fomc if d >= pd.Timestamp("2001-01-01") and d <= idx[-1]]
EW = R[NAMES].mean(axis=1)
for d in evs:
    i = idx.searchsorted(d)
    if i >= len(idx) or i < 2: continue
    r2 = (1 + EW.iloc[i - 1]) * (1 + EW.iloc[i]) - 1 - 2 * 5 / 1e4
    ev_ret.append((idx[i], r2))
E = pd.Series(dict(ev_ret))
print(f"events {len(E)}, mean {E.mean()*1e4:.1f} bp net, median {E.median()*1e4:.1f}, hit {np.mean(E>0):.2f}, t {E.mean()/E.std()*np.sqrt(len(E)):.2f}")
top = E.sort_values(ascending=False)
print("share of total P&L from top-5 events: %.2f ; without top-5: mean %.1f bp, t %.2f" %
      (top.iloc[:5].sum() / E.sum(), top.iloc[5:].mean() * 1e4, top.iloc[5:].mean() / top.iloc[5:].std() * np.sqrt(len(top) - 5)))
for a, b in [("2001", "2006"), ("2007", "2012"), ("2013", "2019"), ("2020", "2026")]:
    x = E.loc[a:b]; print(f"  {a}-{b}: n {len(x)}, mean {x.mean()*1e4:6.1f} bp, t {x.mean()/x.std()*np.sqrt(len(x)):5.2f}, hit {np.mean(x>0):.2f}")
# placebo: same 2-day window shifted to other offsets
print("window placebo (EW9, 2-day windows, net mean bp per event, IS / OOS):")
for k in [-5, -4, -3, -2, -1, 0, 1, 2, 3, 4]:
    vals = []
    for d in evs:
        i = idx.searchsorted(d) + k
        if 1 <= i < len(idx): vals.append((idx[i], (1 + EW.iloc[i - 1]) * (1 + EW.iloc[i]) - 1 - 10 / 1e4))
    s = pd.Series(dict(vals))
    print(f"  days {k-1:+d},{k:+d}: IS {s.loc[:'2012'].mean()*1e4:6.1f}  OOS {s.loc['2013':].mean()*1e4:6.1f}")
# leave one country out (full-period Sharpe of the daily book)
rows = []
for drop in [None] + NAMES:
    names = [n for n in NAMES if n != drop]
    av = C[names].notna(); wt = av.div(av.sum(axis=1), axis=0).mul(w, axis=0)
    W = wt.reindex(columns=names).fillna(0.0)
    for cost in ([5.0, 10.0] if drop is None else [5.0]):
        net, gross, turn, We = xs.run(W.loc["2001":], C.loc["2001":, names], cost_bps=cost, name="x")
        r = xs.summarize(net, SPL, name=f"drop {drop} | {cost}bp"); rows.append(r)
print(pd.DataFrame(rows)[["FULL_SR", "IS_SR", "OOS_SR", "MaxDD"]].round(2).to_string())
# combination with intl-relative-trend: fixed 50/50 risk weights (ex-ante: each sleeve's own vol target)
irt = pd.read_parquet("../intl-relative-trend/nets_03.parquet")["SPEC blend50 (5bp)"]
f = pd.read_parquet("nets_02.parquet")["F10_EW9"]
a = pd.concat([irt, f], axis=1, keys=["irt", "fomc"]).loc["2001-07-02":].fillna(0.0)
# scale the FOMC sleeve to the same unconditional vol as irt using the IS (<=2012) vol ratio only
k = a["irt"].loc[:"2012"].std() / a["fomc"].loc[:"2012"].std()
print(f"IS vol ratio used to scale FOMC sleeve: {k:.2f} (-> in-window gross {k:.2f}x)")
for wf in [0.0, 0.25, 0.5]:
    comb = (1 - wf) * a["irt"] + wf * k * a["fomc"]
    print(f"  FOMC risk share {wf:.2f}: " + "  ".join(f"{p} SR {comb.loc[x:y].mean()/comb.loc[x:y].std()*np.sqrt(252):.2f}"
          for p, (x, y) in SPL.items()))
