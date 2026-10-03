"""exp01 — ETH returns and volatility around Deribit option expiries (Friday 08:00 UTC).

For each expiry class (quarterly / monthly / weekly) and a Tuesday-08:00 placebo: mean log return
in windows from T-7d to T+7d, per half (IS 2020-23, OOS 2024+), plus the realised-vol ratio
after/before (pinning release) and the pre-move -> post-move relation (reversal vs continuation).
"""
import numpy as np
import pandas as pd

import common as c

pd.set_option("display.width", 260)
H, D, M = pd.Timedelta(hours=1), pd.Timedelta(days=1), pd.Timedelta(minutes=1)
p = c.price_at()
end = p.index.max() - 7 * D
ex = c.expiries(end)
pl = c.placebo_times(end)
print(f"expiries {ex.index.min()} -> {ex.index.max()}: {ex.value_counts().to_dict()}; placebo Tuesdays {len(pl)}")

WIN = {"T-7d..T-3d": (-7 * D, -3 * D), "T-72h..T-24h": (-72 * H, -24 * H), "T-24h..T": (-24 * H, 0 * H),
       "T-8h..T": (-8 * H, 0 * H), "T-2h..T": (-2 * H, 0 * H), "T-30m..T": (-30 * M, 0 * H),
       "T..T+1h": (0 * H, 1 * H), "T..T+4h": (0 * H, 4 * H), "T..T+8h": (0 * H, 8 * H),
       "T..T+16h": (0 * H, 16 * H), "T..T+24h": (0 * H, 24 * H), "T..T+72h": (0 * H, 72 * H), "T..T+7d": (0 * H, 7 * D)}
groups = {"quarterly": ex.index[ex == "quarterly"], "monthly": ex.index[ex == "monthly"],
          "month-end (q+m)": ex.index[ex != "weekly"], "weekly": ex.index[ex == "weekly"], "Tue placebo": pl}


def cell(x):
    x = x.dropna()
    if len(x) < 5:
        return "      n/a"
    return f"{x.mean() * 1e4:+6.0f} ({x.mean() / x.std() * np.sqrt(len(x)):+.1f})"


R = {g: pd.DataFrame({w: c.window_ret(p, t, a, b) for w, (a, b) in WIN.items()}) for g, t in groups.items()}
for split, (s0, s1) in (("IS 2020-2023", (c.START, c.IS_END)), ("OOS 2024+", (c.OOS_START, None))):
    print(f"\n{split}: mean log return in bp (t-stat)")
    tab = pd.DataFrame({g: {w: cell(R[g][w].loc[s0:s1]) for w in WIN} for g in groups})
    tab.loc["n"] = {g: str(len(R[g].loc[s0:s1])) for g in groups}
    print(tab.to_string())

# month-end minus weekly-Friday difference (Welch t) for the main windows
print("\nmonth-end expiry minus weekly Friday, bp (Welch t)")
rows = {}
for w in WIN:
    r = {}
    for split, (s0, s1) in (("IS", (c.START, c.IS_END)), ("OOS", (c.OOS_START, None)), ("Full", (c.START, None))):
        a, b = R["month-end (q+m)"][w].loc[s0:s1].dropna(), R["weekly"][w].loc[s0:s1].dropna()
        se = np.sqrt(a.var() / len(a) + b.var() / len(b))
        r[split] = f"{(a.mean() - b.mean()) * 1e4:+6.0f} ({(a.mean() - b.mean()) / se:+.1f})"
    rows[w] = r
print(pd.DataFrame(rows).T.to_string())

# volatility: realised vol of 5-minute returns in the 24 h after vs the 24 h before
p5 = np.log(p[p.index.minute % 5 == 0])
r5sq = p5.diff().pow(2)
cs = r5sq.cumsum()


def rv(times, a, b):
    t0, t1 = pd.DatetimeIndex(times) + a, pd.DatetimeIndex(times) + b
    v0 = cs.reindex(t0, method="ffill").to_numpy(); v1 = cs.reindex(t1, method="ffill").to_numpy()
    return pd.Series(np.sqrt(v1 - v0), index=pd.DatetimeIndex(times))


print("\nrealised vol ratio: 24 h after / 24 h before, and 8 h after / 8 h before (median; pinning predicts > 1)")
for g, t in groups.items():
    x24 = (rv(t, 0 * H, 24 * H) / rv(t, -24 * H, 0 * H)).dropna()
    x8 = (rv(t, 0 * H, 8 * H) / rv(t, -8 * H, 0 * H)).dropna()
    out = []
    for s0, s1 in ((c.START, c.IS_END), (c.OOS_START, None)):
        out.append(f"{x24.loc[s0:s1].median():.2f} / {x8.loc[s0:s1].median():.2f}")
    print(f"  {g:16s} IS {out[0]}   OOS {out[1]}")

# reversal or continuation: correlation of the pre-expiry move with the post-expiry move
print("\nSpearman corr(pre move, post move) by class, IS | OOS")
for pre, post in (("T-24h..T", "T..T+24h"), ("T-72h..T-24h", "T..T+72h"), ("T-8h..T", "T..T+8h"), ("T-7d..T-3d", "T..T+7d")):
    line = f"  {pre:>13s} -> {post:<9s}"
    for g in ("month-end (q+m)", "weekly", "Tue placebo"):
        v = []
        for s0, s1 in ((c.START, c.IS_END), (c.OOS_START, None)):
            dd = R[g][[pre, post]].loc[s0:s1].dropna()
            v.append(f"{dd[pre].corr(dd[post], method='spearman'):+.2f}")
        line += f"   {g}: {v[0]} | {v[1]}"
    print(line)

pd.concat(R, names=["group"]).to_csv("exp01_event_returns.csv")
