"""exp04 -- (i) is it demand or convergence? next-24h return on Coinbase vs Binance by premium tercile.
           (ii) hourly hysteresis state machine on the premium z-score, 10bp/side.
           (iii) daily sizing with a no-trade band.
"""
import os, sys, warnings, itertools
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "shared"))
from research_lib import DATA_DIR, newey_west_t, backtest, split_stats, ANN
pd.set_option("display.width", 250); pd.set_option("display.max_rows", 200)
IS_END, OOS_START = "2022-12-31", "2023-01-01"
def naive(df): return (df.tz_convert("UTC").tz_localize(None) if df.index.tz is not None else df).sort_index()
b = naive(pd.read_parquet(os.path.join(DATA_DIR, "BTCUSDT_1h_flow.parquet")))
c = naive(pd.read_parquet(os.path.join(DATA_DIR, "COINBASE_BTCUSD_1h.parquet")))
idx = b.index.intersection(c.index); b, c = b.loc[idx], c.loc[idx]
px, cx = b["Close"], c["Close"]
prem = cx / px - 1
z1 = (prem - prem.rolling(720).mean()) / prem.rolling(720).std()
z4 = (prem.rolling(4).mean() - prem.rolling(720).mean()) / prem.rolling(720).std()

print("=== (i) demand vs convergence: tercile of z1 -> next-24h return (bp) on Binance vs Coinbase; IS | OOS")
for nm, seg in (("IS", slice(None, IS_END)), ("OOS", slice(OOS_START, None))):
    zz = z1.loc[seg].dropna(); q = pd.qcut(zz.rank(method="first"), 3, labels=False)
    fb = (px.shift(-24) / px - 1).loc[zz.index]; fc = (cx.shift(-24) / cx - 1).loc[zz.index]
    f1b = (px.shift(-1) / px - 1).loc[zz.index]; f1c = (cx.shift(-1) / cx - 1).loc[zz.index]
    print(nm, "24h Binance:", (fb.groupby(q).mean() * 1e4).round(1).tolist(), " Coinbase:", (fc.groupby(q).mean() * 1e4).round(1).tolist(),
          "| 1h Binance:", (f1b.groupby(q).mean() * 1e4).round(2).tolist(), " Coinbase:", (f1c.groupby(q).mean() * 1e4).round(2).tolist())

# ---------------- (ii) hysteresis state machine, hourly
def state_machine(z, enter, exit_):
    zv = z.values; w = np.zeros(len(zv)); s = 0.0
    for i in range(len(zv)):
        v = zv[i]
        if np.isnan(v): w[i] = s; continue
        if s == 0.0 and v > enter: s = 1.0
        elif s == 1.0 and v < exit_: s = 0.0
        w[i] = s
    return pd.Series(w, index=z.index)
HANN = 365 * 24
ret_h = px.pct_change()
ewv_h = ret_h.ewm(halflife=20 * 24, min_periods=20 * 24).std() * np.sqrt(HANN)
vscale_h = (0.40 / ewv_h).clip(0, 1).fillna(0)
sma50_h = (px > px.rolling(50 * 24).mean()).astype(float)
rows = []
for sig_nm, sig in (("z1", z1), ("z4", z4)):
    for enter, exit_ in itertools.product((0.0, 0.5, 1.0, 1.5), (-1.5, -1.0, -0.5, 0.0)):
        if exit_ >= enter and not (enter == 0.0 and exit_ == 0.0): continue
        w = state_machine(sig, enter, exit_)
        for gate_nm, g in (("none", 1.0), ("sma50xvol", sma50_h * vscale_h)):
            net, st = backtest(w * g, px, cost_bps=10, ann=HANN)
            sp = split_stats(net, {"IS": (None, IS_END), "OOS": (OOS_START, None)}, ann=HANN)
            rows.append(dict(sig=sig_nm, enter=enter, exit=exit_, gate=gate_nm, Sharpe=st["Sharpe"], IS=sp.loc["IS", "Sharpe"],
                             OOS=sp.loc["OOS", "Sharpe"], CAGR=st["CAGR"], MaxDD=st["MaxDD"], TO_yr=st["Turnover_ann"], Expo=st["AvgExposure"]))
df = pd.DataFrame(rows); df["minIO"] = df[["IS", "OOS"]].min(axis=1)
print("\n=== (ii) hourly hysteresis grid, 10bp/side (all cells)")
print(df.sort_values("minIO", ascending=False).round(2).to_string())

# ---------------- (iii) daily no-trade-band sizing
P = pd.read_parquet(os.path.join(HERE, "panel.parquet"))
close = P["close"]; ret = close.pct_change()
ewv = ret.ewm(halflife=20, min_periods=20).std() * np.sqrt(ANN); vscale = (0.40 / ewv).clip(0, 1).fillna(0)
z90 = P["cbprem_bin_z90"]; z30 = (P["cbprem_bin_mean"] - P["cbprem_bin_mean"].rolling(30).mean()) / P["cbprem_bin_mean"].rolling(30).std()
def band(target, width):
    t = target.fillna(0).values; w = np.zeros(len(t)); cur = 0.0
    for i in range(len(t)):
        if abs(t[i] - cur) > width: cur = t[i]
        w[i] = cur
    return pd.Series(w, index=target.index)
rows = []
for zn, z in (("z90", z90), ("z30", z30)):
    for form in ("lin", "step"):
        raw = (0.5 + 0.5 * z.clip(-1, 1)) if form == "lin" else (z > 0).astype(float)
        for gate_nm, g in (("none", 1.0), ("sma50", P["sma50_up"]), ("mom20", (P["mom20"] > 0).astype(float))):
            for width in (0.0, 0.2, 0.35, 0.5):
                w = band(raw * g * vscale, width)
                net, st = backtest(w, close, cost_bps=10)
                sp = split_stats(net, {"IS": (None, IS_END), "OOS": (OOS_START, None)})
                rows.append(dict(z=zn, form=form, gate=gate_nm, band=width, Sharpe=st["Sharpe"], IS=sp.loc["IS", "Sharpe"], OOS=sp.loc["OOS", "Sharpe"],
                                 CAGR=st["CAGR"], MaxDD=st["MaxDD"], TO=st["Turnover_ann"], Expo=st["AvgExposure"]))
df = pd.DataFrame(rows); df["minIO"] = df[["IS", "OOS"]].min(axis=1)
print("\n=== (iii) daily sizing with no-trade band (all cells)")
print(df.sort_values("minIO", ascending=False).round(2).to_string())
