"""Exp 19 - (a) vectorbt cross-check of the custom engine, (b) independent-venue
replication on Bitstamp, (c) component ablation."""
import sys, os, json, time, urllib.request, numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from research_lib import *
from strategy import *
import vectorbt as vbt
pd.set_option("display.width", 260); pd.set_option("display.max_columns", 60)

H = load_hourly()
SPEC = dict(vol_target=0.35, vol_hl=20, gate_thr=-0.010, b=0.5)
COST = 3.0
w, P = build_signals(H, **SPEC); hret = P["hret"]; hclose = H["Close"]
net, turn = backtest_hourly(w, hret, COST)

# ---------------- (a) vectorbt cross-check
# our convention: w_T is established at bar T-1's CLOSE and earns hret[T].
# vectorbt from_orders executes at the bar close => vbt size at t must equal w[t+1].
vbt_size = w.shift(-1).fillna(0.0)
pf = vbt.Portfolio.from_orders(
    close=hclose, size=vbt_size, size_type="targetpercent",
    fees=COST/1e4, freq="1h", init_cash=100.0, cash_sharing=False)
vbt_ret = pf.returns()
print("=== (a) vectorbt cross-check ===")
cmp = pd.DataFrame({
    "custom engine": [ (1+net).prod()-1, net.mean()/net.std()*np.sqrt(HANN),
                       ((1+net).cumprod()/(1+net).cumprod().cummax()-1).min() ],
    "vectorbt":      [ (1+vbt_ret).prod()-1, vbt_ret.mean()/vbt_ret.std()*np.sqrt(HANN),
                       ((1+vbt_ret).cumprod()/(1+vbt_ret).cumprod().cummax()-1).min() ]},
    index=["total return", "Sharpe (ann)", "MaxDD"])
print(cmp.round(4).to_string())
al = pd.concat([net.rename("a"), vbt_ret.rename("b")], axis=1).dropna()
print(f"  correlation of return streams: {al.a.corr(al.b):.6f}")
print(f"  max abs per-bar difference   : {(al.a-al.b).abs().max():.3e}")
print(f"  vectorbt Sharpe (its own calc): {pf.sharpe_ratio():.4f}")

# ---------------- (b) independent venue: Bitstamp
def bitstamp_hourly():
    p = os.path.join(DATA_DIR, "BITSTAMP_1h.parquet")
    if os.path.exists(p): return pd.read_parquet(p)
    out, end = [], int(pd.Timestamp.now(tz="UTC").timestamp())
    for _ in range(60):
        u = f"https://www.bitstamp.net/api/v2/ohlc/btcusd/?step=3600&limit=1000&end={end}"
        try: d = json.loads(urllib.request.urlopen(u, timeout=30).read())["data"]["ohlc"]
        except Exception: break
        if not d: break
        out = d + out; end = int(d[0]["timestamp"]) - 3600; time.sleep(0.2)
    df = pd.DataFrame(out)
    df["ts"] = pd.to_datetime(df["timestamp"].astype(int), unit="s")
    df = df.drop_duplicates("ts").set_index("ts").sort_index()
    df = df[["open","high","low","close","volume"]].astype(float)
    df.columns = ["Open","High","Low","Close","Volume"]
    df.to_parquet(p); return df
BS = bitstamp_hourly()
print(f"\n=== (b) independent-venue replication: Bitstamp BTC/USD "
      f"({len(BS)} bars, {BS.index[0]} -> {BS.index[-1]}) ===")
wb, Pb = build_signals(BS, **SPEC)
nb, tb = backtest_hourly(wb, Pb["hret"], COST)
ov = net.loc[BS.index[0]:]
print(pd.DataFrame([stats(ov, turn.loc[BS.index[0]:], "Binance (same window)"),
                    stats(nb, tb, "Bitstamp")]).round(3).to_string())

# ---------------- (c) ablation: what each component contributes
print("\n=== (c) component ablation (3bp/side, full sample) ===")
rows = {}
def ev(lab, **kw):
    ww, PP = build_signals(H, **{**SPEC, **kw})
    nn, tt = backtest_hourly(ww, PP["hret"], COST)
    s = stats(nn, tt, lab)
    o = nn.loc["2022-01-01":]; s["SR_OOS"] = o.mean()/o.std()*np.sqrt(HANN)
    e = nn.loc["2024-01-11":]; s["SR_ETF"] = e.mean()/e.std()*np.sqrt(HANN)
    rows[lab] = s
ev("FULL (base + gated overlay)")
ev("no overlay (base only)", b=0.0)
ev("no macro sleeve", use_macro=False)
ev("no BTC trend sleeve", use_trend=False)
ev("no vol targeting", vol_target=99.0)
ev("overlay ungated (every day)", gate_thr=99.0)
# base-free: overlay only
ww, PP = build_signals(H, **SPEC)
only_ov = (0.5*PP["gate"]).clip(0,1)
nn, tt = backtest_hourly(only_ov, PP["hret"], COST)
s = stats(nn, tt, "overlay only (no base)")
o = nn.loc["2022-01-01":]; s["SR_OOS"] = o.mean()/o.std()*np.sqrt(HANN)
e = nn.loc["2024-01-11":]; s["SR_ETF"] = e.mean()/e.std()*np.sqrt(HANN)
rows["overlay only (no base)"] = s
bh = pd.Series(1.0, index=hclose.index)
nn, tt = backtest_hourly(bh, hret, 0.0); s = stats(nn, tt, "Buy & Hold")
o = nn.loc["2022-01-01":]; s["SR_OOS"] = o.mean()/o.std()*np.sqrt(HANN)
e = nn.loc["2024-01-11":]; s["SR_ETF"] = e.mean()/e.std()*np.sqrt(HANN)
rows["Buy & Hold"] = s
print(pd.DataFrame(rows).T.round(2).to_string())

# ---------------- (d) individual macro-series ablation
print("\n=== (d) drop-one macro series ===")
rows = {}
full_macro = {"HYG":+1, "LQD":+1, "DX-Y.NYB":-1, "^GSPC":+1}
for drop in [None] + list(full_macro):
    m = {k:v for k,v in full_macro.items() if k != drop}
    ww, PP = build_signals(H, **SPEC, macro=m)
    nn, tt = backtest_hourly(ww, PP["hret"], COST)
    o = nn.loc["2022-01-01":]
    rows["keep all" if drop is None else f"drop {drop}"] = {
        "Sharpe": nn.mean()/nn.std()*np.sqrt(HANN), "SR_OOS": o.mean()/o.std()*np.sqrt(HANN),
        "CAGR%": ((1+nn).cumprod().iloc[-1]**(HANN/len(nn))-1)*100,
        "MaxDD%": ((1+nn).cumprod()/(1+nn).cumprod().cummax()-1).min()*100}
print(pd.DataFrame(rows).T.round(2).to_string())
