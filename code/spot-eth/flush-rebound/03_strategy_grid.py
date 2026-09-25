"""flush-rebound 03: costed long/flat strategy grid for the down-shock rebound.

Enter long 1.0 at the close of an event bar (z_k < -Z [and condition]), hold H hours
(a new event while in the trade extends the hold). 10 bp per side on |dw|.
Also reports each config's hourly-return correlation with the live eth-trend-filter.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
import numpy as np
import pandas as pd
from ethdata import bars, bt, row, to_daily, trend_filter_weights_daily

h = bars("ETHUSDT", "1h"); c = h["Close"]
lr = np.log(c).diff(); sig = lr.ewm(halflife=168, min_periods=168).std()
sma40d = c.rolling(960, min_periods=960).mean()


def hold_weights(ev, H):
    """1 for H bars after each event bar (inclusive of the event bar's close)."""
    ev = ev.fillna(False).astype(int)
    # bars since last event
    grp = ev.cumsum()
    since = ev.groupby(grp).cumcount()
    w = ((grp > 0) & (since < H)).astype(float)
    return w


# trend-filter baseline on daily closes (00:00 UTC), spread to hours
d = c.resample("1D").last()
w_tf_d = trend_filter_weights_daily(d)
# daily weight known at close of day D (bar labelled D closes at D+1 00:00) -> applies from D+1 00:00
w_tf_h = w_tf_d.shift(1, freq="D").reindex(c.index, method="ffill").fillna(0)
net_tf, s_tf = bt(w_tf_h, c)
print("trend-filter (hourly replay):", row(to_daily(net_tf), ann=365))

rows = []
for k in [2, 4, 8, 12]:
    z = np.log(c / c.shift(k)) / (sig.shift(k) * np.sqrt(k))
    for Z in [2.0, 2.5, 3.0]:
        for H in [12, 24, 48]:
            for cond in ["none", "uptrend"]:
                ev = z < -Z
                if cond == "uptrend":
                    ev &= c.shift(k) > sma40d.shift(k)
                w = hold_weights(ev, H)
                net, s = bt(w, c)
                nd = to_daily(net)
                r = row(nd, ann=365, extra=dict(k=k, Z=Z, H=H, cond=cond,
                                                TIM=s["TimeInMkt"], Turn=s["Turnover_ann"],
                                                rho_tf=np.corrcoef(net, net_tf)[0, 1]))
                rows.append(r)
df = pd.DataFrame(rows)
pd.set_option("display.width", 250, "display.max_rows", 500)
cols = ["k", "Z", "H", "cond", "Sh_Full", "Sh_IS", "Sh_OOS", "CAGR", "MDD", "TIM", "Turn", "rho_tf"]
print(df[cols].sort_values("Sh_IS", ascending=False).round(2).to_string(index=False))
print("\nN configs:", len(df), " median Sh Full/IS/OOS:", df[["Sh_Full", "Sh_IS", "Sh_OOS"]].median().round(2).tolist())
print("IS->OOS spearman:", round(df["Sh_IS"].corr(df["Sh_OOS"], method="spearman"), 2))
df.to_csv(os.path.join(os.path.dirname(__file__), "03_strategy_grid.csv"), index=False)
