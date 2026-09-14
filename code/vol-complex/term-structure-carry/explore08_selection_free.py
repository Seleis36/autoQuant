"""Selection-free check of the calendar legs: choose offsets on IS (2011-2018) only, score OOS; and
expanding-window yearly re-selection."""
import sys, os, numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tsc_lib import *
pd.set_option("display.width", 220)
df = load_all(); f = features(df); cal = df.index
r = df.vixy.pct_change()
closes = df[["vixy"]]; COST = {"vixy": 5.0}
fomc = pd.to_datetime(pd.read_csv("code/rates-bonds/treasury-flow-calendar/calendar_snapshots/fomc.csv")["date"])
def third_friday(y, m):
    d = pd.Timestamp(y, m, 15); return d + pd.offsets.Week(weekday=4) if d.weekday() != 4 else d
opex = [third_friday(y, m) for y in range(2011, 2027) for m in range(1, 13)]
vxexp = [x - pd.Timedelta(days=30) for x in opex]
EVENTS = {"fomc": fomc, "opex": opex, "vxexp": vxexp}
def day_flags(events, k):
    """1 on trading day d when d is at offset k from an event (return realised ON d)."""
    ev = pd.DatetimeIndex(events); ev = ev[(ev >= cal[0]) & (ev <= cal[-1])]; p0 = cal.searchsorted(ev)
    d = pd.DatetimeIndex(sorted({cal[p + k] for p in p0 if 0 <= p + k < len(cal)}))
    return pd.Series(cal.isin(d).astype(float), index=cal)
flags = {(e, k): day_flags(ev, k) for e, ev in EVENTS.items() for k in range(-4, 5)}
def select(start, end, tmin=2.0):
    chosen = {}
    for key, fl in flags.items():
        x = r.loc[start:end][fl.loc[start:end] == 1]
        if len(x) < 20: continue
        t = x.mean() / x.std() * np.sqrt(len(x))
        if abs(t) >= tmin: chosen[key] = np.sign(x.mean())      # short (-1) on days VIXY historically fell
    return chosen
def weights_from(chosen):
    w = pd.Series(0.0, index=cal)
    for key, s in chosen.items():
        w = w + s * flags[key]
    return w.clip(-1, 1).shift(-1).fillna(0.0)      # weight set at close t for the return realised on t+1
def bt(w, a, b):
    net, st = bt_multi(pd.DataFrame({"vixy": w}), closes, COST); return net.loc[a:b]
for tmin in [1.5, 2.0, 2.5]:
    ch = select("2011", IS_END, tmin)
    net_oos = bt(weights_from(ch), OOS_START, END); net_is = bt(weights_from(ch), "2011", IS_END)
    print(f"tmin={tmin}: IS-selected legs {sorted(ch.items())}")
    print(f"   IS Sharpe {rl.perf_stats(net_is, ANN).Sharpe:.2f}   OOS Sharpe {rl.perf_stats(net_oos, ANN).Sharpe:.2f}  (n legs={len(ch)})")
# expanding-window yearly re-selection, first scoring year 2015
parts = []
for y in range(2015, 2027):
    ch = select("2011", f"{y-1}-12-31", 2.0)
    parts.append(bt(weights_from(ch), f"{y}-01-01", f"{y}-12-31"))
wf = pd.concat(parts)
print("\nExpanding-window yearly re-selection (2015-2026) calendar-only: Sharpe", round(rl.perf_stats(wf, ANN).Sharpe, 2), "CAGR", round(rl.perf_stats(wf, ANN).CAGR, 3), "MDD", round(rl.perf_stats(wf, ANN).MaxDD, 3))
print(yearly_sharpe(wf).round(2).to_string())
# with carry
contango = (f.slope > 1).astype(float)
parts = []
for y in range(2015, 2027):
    ch = select("2011", f"{y-1}-12-31", 2.0)
    w = (weights_from(ch) - 0.5 * contango).clip(-1, 1)
    parts.append(bt(w, f"{y}-01-01", f"{y}-12-31"))
wf2 = pd.concat(parts)
print("\nWalk-forward calendar + 0.5 contango carry (2015-2026): Sharpe", round(rl.perf_stats(wf2, ANN).Sharpe, 2), "CAGR", round(rl.perf_stats(wf2, ANN).CAGR, 3), "MDD", round(rl.perf_stats(wf2, ANN).MaxDD, 3))
print("carry alone same window:", round(rl.perf_stats(bt(-contango, "2015", END), ANN).Sharpe, 2), " 0.5 carry alone:", round(rl.perf_stats(bt(-0.5 * contango, "2015", END), ANN).Sharpe, 2))
wf2.to_frame("ret").to_parquet(os.path.join(os.path.dirname(os.path.abspath(__file__)), "walkforward_returns.parquet"))
