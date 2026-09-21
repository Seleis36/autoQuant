"""exp05 -- can exposure scaling make the Sharpe horizon-robust?
The always-on carry has daily Sharpe ~8.6 but monthly ~2.5 because funding levels persist (regime variance,
not loss variance). Variants that scale exposure with trailing P&L vol or trailing funding level are tested on
BTC+ETH, and the Sharpe is reported at daily, weekly and monthly aggregation. Costs 15+5 bp per unit turnover."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd
from carry_lib import *
pd.set_option("display.width", 220)
syms = ["BTCUSDT", "ETHUSDT"]
pairs = {s: load_pair(s, start="2020-01-01") for s in syms}
idx = pd.date_range("2020-01-01", min(p.index.max() for p in pairs.values()), freq="h")

def trailing_mean(df, k):
    fs = df["f"].where(df["f"] != 0).dropna()
    return fs.rolling(k).mean().reindex(df.index).ffill()

def port(weight_fn, fee=15.0, slip=5.0):
    tot = pd.Series(0.0, index=idx); turn_tot = pd.Series(0.0, index=idx)
    for s in syms:
        df = pairs[s]; w = weight_fn(df).clip(0, 1)
        net, we, turn = backtest_carry(df, w, fee_bps=fee, slip_bps=slip)
        tot += net.reindex(idx).fillna(0.0) / len(syms); turn_tot += turn.reindex(idx).fillna(0.0) / len(syms)
    return tot, turn_tot

def report(name, net, turn):
    d = daily(net); out = {"name": name}
    for freq, ann in (("D", 365), ("W", 52), ("MS", 12)):
        x = (1 + d).resample(freq).prod() - 1; out[f"Sh_{freq}"] = x.mean() / x.std() * np.sqrt(ann)
    s = perf_stats(d); out.update(CAGR=s.CAGR, Vol=s.Vol, MaxDD=s.MaxDD, Turn_yr=turn.sum() / (len(turn) / HOURS))
    for k, (a, b) in SPLITS.items():
        x = (1 + d.loc[a:b]).resample("MS").prod() - 1; out[f"ShM_{k}"] = x.mean() / x.std() * np.sqrt(12)
    return out

rows = []
rows.append(report("always_on", *port(lambda df: pd.Series(1.0, index=df.index))))
# (a) vol targeting on the hedged P&L: w = min(1, target / ewm_vol(leg returns)), updated at settlement stamps only
for hl in (24*7, 24*30):
    for tgt in (0.005, 0.01, 0.02):
        def fn(df, hl=hl, tgt=tgt):
            r = leg_returns(df); v = r.ewm(halflife=hl).std() * np.sqrt(HOURS)
            w = (tgt / v).clip(upper=1.0); return w.where(df.index.hour % 8 == 0).ffill().fillna(0.0)
        rows.append(report(f"voltgt_hl{hl//24}d_t{tgt*100:.1f}%", *port(fn)))
# (b) scale by trailing funding level: w = clip(c / trailing_mean_k) -- gives *less* exposure when funding is high
for k in (21, 63):
    for c in (0.00005, 0.0001, 0.0002):
        def fn(df, k=k, c=c):
            m = trailing_mean(df, k); w = (c / m.clip(lower=1e-6)).clip(upper=1.0)
            return w.where(m > 0, 0.0)
        rows.append(report(f"fundscale_k{k}_c{c*1e4:.1f}bp", *port(fn)))
# (c) funding-level sizing the other way (more when higher), capped, to show the contrast
for k in (21,):
    def fn(df, k=k):
        m = trailing_mean(df, k); return (m / 0.0002).clip(lower=0, upper=1.0)
    rows.append(report(f"fundlinear_k{k}", *port(fn)))
out = pd.DataFrame(rows).set_index("name")
print(out.round(3).to_string())
out.to_csv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "exp05_results.csv"))
