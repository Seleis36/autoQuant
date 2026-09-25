"""upshock-continuation 01: event study split by trend state + costed long/flat grid.

Event at hourly close t: z_k = log(C_t/C_{t-k}) / (sigma_{t-k} sqrt(k)) > Z, sigma = EWM(168h) std
of 1h log returns up to t-k. Long 1.0 for H hours from the close of the event bar (re-trigger
extends). 10 bp per side. Sharpe on UTC-daily compounded returns.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
import numpy as np
import pandas as pd
from ethdata import bars, bt, row, to_daily, trend_filter_weights_daily, IS_END, OOS_START

h = bars("ETHUSDT", "1h"); c = h["Close"]
lr = np.log(c).diff(); sig = lr.ewm(halflife=168, min_periods=168).std()
sma40d = c.rolling(960, min_periods=960).mean()
up = (c > sma40d)


def hold_weights(ev, H):
    ev = ev.fillna(False).astype(int)
    grp = ev.cumsum(); since = ev.groupby(grp).cumcount()
    return ((grp > 0) & (since < H)).astype(float)


def declus(ev, H):
    idx, last = [], None
    for t in ev[ev.fillna(False)].index:
        if last is None or (t - last) >= pd.Timedelta(hours=H):
            idx.append(t); last = t
    return pd.DatetimeIndex(idx)


d = c.resample("1D").last()
w_tf_h = trend_filter_weights_daily(d).shift(1, freq="D").reindex(c.index, method="ffill").fillna(0)
net_tf, _ = bt(w_tf_h, c)

# --- event study by trend state
ev_rows = []
for k in [1, 2, 4, 8, 12]:
    z = np.log(c / c.shift(k)) / (sig.shift(k) * np.sqrt(k))
    for Z in [2.0, 2.5, 3.0]:
        for H in [12, 24, 48]:
            fwd = np.log(c.shift(-H) / c)
            for st, m in [("all", pd.Series(True, index=c.index)), ("uptrend", up), ("downtrend", ~up & sma40d.notna())]:
                f = fwd.reindex(declus((z > Z) & m, H)).dropna()
                u = fwd.where(m).dropna()
                r = dict(k=k, Z=Z, H=H, state=st)
                for part, (a, b) in {"IS": (None, IS_END), "OOS": (OOS_START, None)}.items():
                    fp = f.loc[a:b]; up_ = u.loc[a:b]
                    r[f"n_{part}"] = len(fp)
                    r[f"ex_bp_{part}"] = (fp.mean() - up_.mean()) * 1e4   # excess over same-state unconditional
                    r[f"t_{part}"] = (fp.mean() - up_.mean()) / fp.std() * np.sqrt(len(fp)) if len(fp) > 3 else np.nan
                ev_rows.append(r)
ev = pd.DataFrame(ev_rows)
print(ev.groupby("state")[["ex_bp_IS", "ex_bp_OOS", "t_IS", "t_OOS"]].mean().round(2))

# --- costed grid
rows = []
for k in [1, 2, 4, 8, 12]:
    z = np.log(c / c.shift(k)) / (sig.shift(k) * np.sqrt(k))
    for Z in [2.0, 2.5, 3.0]:
        for H in [12, 24, 48]:
            w = hold_weights(z > Z, H)
            net, s = bt(w, c)
            rows.append(row(to_daily(net), ann=365, extra=dict(
                k=k, Z=Z, H=H, TIM=s["TimeInMkt"], Turn=s["Turnover_ann"],
                rho_tf=np.corrcoef(net, net_tf)[0, 1])))
df = pd.DataFrame(rows)
pd.set_option("display.width", 250, "display.max_rows", 500)
cols = ["k", "Z", "H", "Sh_Full", "Sh_IS", "Sh_OOS", "CAGR", "MDD", "TIM", "Turn", "rho_tf"]
print(df[cols].sort_values("Sh_Full", ascending=False).round(2).to_string(index=False))
print("\nN:", len(df), "median Full/IS/OOS:", df[["Sh_Full", "Sh_IS", "Sh_OOS"]].median().round(2).tolist(),
      " IS->OOS spearman", round(df.Sh_IS.corr(df.Sh_OOS, method="spearman"), 2))
df.to_csv(os.path.join(os.path.dirname(__file__), "01_grid.csv"), index=False)
ev.to_csv(os.path.join(os.path.dirname(__file__), "01_event_by_state.csv"), index=False)
