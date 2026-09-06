"""Exp 09 - Four orthogonal sleeves -> combined spot-BTC long/flat timer."""
import sys, os, numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from research_lib import *
pd.set_option("display.width", 260); pd.set_option("display.max_columns", 60)

df = load_btc(); close = df["Close"]; ret = close.pct_change(); cal = close.index
G = lambda t: load_series(t)["Close"].reindex(cal).ffill()

# ---- sleeve 1: BTC trend ensemble
S_trend = pd.concat([(close > close.rolling(n).mean()).astype(float)
                     for n in [20,50,100,150,200]], axis=1).mean(axis=1)
# ---- sleeve 2: macro liquidity ensemble
MAC = {"HYG": (G("HYG"), +1), "LQD": (G("LQD"), +1), "DXY": (G("DX-Y.NYB"), -1), "SPX": (G("^GSPC"), +1)}
def ens_ma(s, sign, lbs=[50,100,150,200,250]):
    m = pd.concat([(s > s.rolling(n).mean()).astype(float) for n in lbs], axis=1).mean(axis=1)
    return m if sign > 0 else 1.0 - m
S_macro = pd.concat([ens_ma(s, sg) for s, sg in MAC.values()], axis=1).mean(axis=1)
# ---- sleeve 3: turn-of-month (pure calendar, zero estimation)
dm = pd.Series(cal.day, index=cal)
eom = pd.Series(cal.days_in_month, index=cal)
S_tom = ((dm >= eom - 4) | (dm <= 4)).astype(float)
# ---- sleeve 4: crypto risk appetite (ETH/BTC below its MA = BTC-favourable)
eth = G("ETH-USD"); ethbtc = eth / close
S_alt = pd.concat([(ethbtc < ethbtc.rolling(n).mean()).astype(float)
                   for n in [50,100,150,200]], axis=1).mean(axis=1)
S_alt = S_alt.fillna(0.5)     # pre-2018: neutral, no ETH data -> no lookahead

SL = {"trend": S_trend, "macro": S_macro, "tom": S_tom, "alt": S_alt}
print("=== sleeve signal correlations (levels) ===")
print(pd.DataFrame(SL).corr().round(3).to_string())

SPL = {"IS 2014-2020": ("2014-01-01","2020-12-31"), "OOS 2021-2026": ("2021-01-01","2026-12-31"),
       "2021": ("2021-01-01","2021-12-31"), "2022": ("2022-01-01","2022-12-31"),
       "2023": ("2023-01-01","2023-12-31"), "2024": ("2024-01-01","2024-12-31"),
       "2025": ("2025-01-01","2025-12-31"), "2026": ("2026-01-01","2026-12-31")}
def row(w, name, cost=10):
    net, st = backtest(w, close, cost_bps=cost, name=name)
    r = st[["CAGR","Vol","Sharpe","Sortino","MaxDD","Calmar","Turnover_ann","TimeInMkt","t_NW"]]
    return net, pd.concat([r, pd.Series({
        "SR_IS": perf_stats(net.loc[:"2020-12-31"])["Sharpe"],
        "SR_OOS": perf_stats(net.loc["2021-01-01":])["Sharpe"],
        "Calm_OOS": perf_stats(net.loc["2021-01-01":])["Calmar"]})])

print("\n=== each sleeve standalone (raw, no vol scaling) ===")
out = {}
for k, s in SL.items(): _, out[k] = row(s, k)
_, out["BuyHold"] = row(pd.Series(1.0, index=cal), "BuyHold", cost=0)
print(fmt(pd.DataFrame(out).T).to_string())

# turn-of-month as a TILT rather than a gate (it is only ~30% of days)
S_tom_tilt = 0.6 + 0.4*S_tom       # 0.6 mid-month, 1.0 at turn of month
S_alt_tilt = 0.6 + 0.4*S_alt

print("\n=== combinations (all with vol-scaling target 35%, cap 1.0) ===")
vs = vol_target_scalar(ret, target=0.35, halflife=20, cap=1.0)
combos = {
 "T x M":                     S_trend*S_macro,
 "T x M x tom_tilt":          S_trend*S_macro*S_tom_tilt,
 "T x M x alt_tilt":          S_trend*S_macro*S_alt_tilt,
 "T x M x tom x alt tilts":   S_trend*S_macro*S_tom_tilt*S_alt_tilt,
 "mean(T,M,tom,alt)":         (S_trend+S_macro+S_tom+S_alt)/4,
 "mean(T,M) x tom x alt":     ((S_trend+S_macro)/2)*S_tom_tilt*S_alt_tilt,
}
out = {}
for k, w in combos.items(): _, out[k+" [+vol35]"] = row(w*vs, k)
print(fmt(pd.DataFrame(out).T).to_string())

print("\n=== same combos WITHOUT vol scaling ===")
out = {}
for k, w in combos.items(): _, out[k] = row(w, k)
print(fmt(pd.DataFrame(out).T).to_string())

best_w = S_trend*S_macro*S_tom_tilt*S_alt_tilt*vs
net, st = row(best_w, "COMBO")
print("\n--- T x M x tom x alt tilts x vol35 : by period ---")
print(fmt(split_stats(net, SPL)).to_string())
