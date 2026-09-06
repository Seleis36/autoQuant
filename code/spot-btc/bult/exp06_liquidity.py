"""Exp 06 - "BTC Liquidity Regime" strategy.
Thesis: post-2020 BTC is a long-duration liquidity asset. Credit risk appetite (HYG),
IG credit/duration (LQD) and the dollar (DXY) describe the liquidity regime that BTC
levers. Build a long/flat spot BTC timer from EXOGENOUS macro state only, then test
whether it adds to (or replaces) BTC's own trend."""
import sys, os, numpy as np, pandas as pd
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "shared"))
from research_lib import *
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 60)

df = load_btc(); close = df["Close"]; ret = close.pct_change(); cal = close.index
G = lambda t: load_series(t)["Close"].reindex(cal).ffill()
HYG, LQD, DXY, SPX = G("HYG"), G("LQD"), G("DX-Y.NYB"), G("^GSPC")

SPL = {"IS 2014-2020": ("2014-01-01","2020-12-31"), "OOS 2021-2026": ("2021-01-01","2026-12-31"),
       "2021": ("2021-01-01","2021-12-31"), "2022": ("2022-01-01","2022-12-31"),
       "2023": ("2023-01-01","2023-12-31"), "2024": ("2024-01-01","2024-12-31"),
       "2025": ("2025-01-01","2025-12-31"), "2026": ("2026-01-01","2026-12-31")}

def above_ma(s, n=200):  return (s > s.rolling(n).mean()).astype(float)
def mom_pos(s, n=20):    return (s > s.shift(n)).astype(float)

# --- individual macro blocks (all binary, 0/1 = risk-off/risk-on for BTC)
B = {
    "HYG>MA200":  above_ma(HYG, 200),
    "LQD>MA200":  above_ma(LQD, 200),
    "DXY<MA200":  1.0 - above_ma(DXY, 200),
    "SPX mom20":  mom_pos(SPX, 20),
}
print("=== Individual macro blocks as standalone BTC long/flat timers (10bps) ===")
rows = {}
for k, s in B.items():
    net, st = backtest(s, close, cost_bps=10, name=k)
    rows[k] = pd.concat([st[["CAGR","Vol","Sharpe","MaxDD","Turnover_ann","TimeInMkt"]],
                         pd.Series({"SR_IS": perf_stats(net.loc[:"2020-12-31"])["Sharpe"],
                                    "SR_OOS": perf_stats(net.loc["2021-01-01":])["Sharpe"]})])
bh, bh_s = backtest(pd.Series(1.0, index=cal), close, cost_bps=0, name="BuyHold")
rows["BuyHold"] = pd.concat([bh_s[["CAGR","Vol","Sharpe","MaxDD","Turnover_ann","TimeInMkt"]],
                             pd.Series({"SR_IS": perf_stats(bh.loc[:"2020-12-31"])["Sharpe"],
                                        "SR_OOS": perf_stats(bh.loc["2021-01-01":])["Sharpe"]})])
print(fmt(pd.DataFrame(rows).T).to_string())

# --- composite: fraction of macro blocks that are risk-on, used as CONTINUOUS exposure
comp = sum(B.values()) / len(B)
print("\n=== Composite macro score -> exposure ===")
rows = {}
for name, w in [("MacroScore (continuous)", comp),
                ("Macro >=0.5", (comp >= 0.5).astype(float)),
                ("Macro >=0.75", (comp >= 0.75).astype(float)),
                ("Macro ==1.0", (comp >= 1.0).astype(float))]:
    net, st = backtest(w, close, cost_bps=10, name=name)
    rows[name] = pd.concat([st[["CAGR","Vol","Sharpe","Sortino","MaxDD","Calmar","Turnover_ann","TimeInMkt","t_NW"]],
                            pd.Series({"SR_IS": perf_stats(net.loc[:"2020-12-31"])["Sharpe"],
                                       "SR_OOS": perf_stats(net.loc["2021-01-01":])["Sharpe"]})])
print(fmt(pd.DataFrame(rows).T).to_string())

# --- does macro ADD to BTC's own trend?
btc_trend = (close > close.rolling(100).mean()).astype(float)
print("\n=== Macro x BTC-trend interaction ===")
rows = {}
for name, w in [("BTC trend only (MA100)", btc_trend),
                ("Macro only (continuous)", comp),
                ("Trend AND Macro>=0.5", btc_trend * (comp >= 0.5)),
                ("Trend x MacroScore", btc_trend * comp),
                ("0.5*(Trend + Macro)", 0.5 * (btc_trend + comp))]:
    net, st = backtest(w, close, cost_bps=10, name=name)
    rows[name] = pd.concat([st[["CAGR","Vol","Sharpe","Sortino","MaxDD","Calmar","Turnover_ann","TimeInMkt","t_NW"]],
                            pd.Series({"SR_IS": perf_stats(net.loc[:"2020-12-31"])["Sharpe"],
                                       "SR_OOS": perf_stats(net.loc["2021-01-01":])["Sharpe"]})])
print(fmt(pd.DataFrame(rows).T).to_string())

# --- year by year for the two leading candidates
for name, w in [("Macro only (continuous)", comp), ("Trend x MacroScore", btc_trend * comp)]:
    net, _ = backtest(w, close, cost_bps=10, name=name)
    print(f"\n--- {name}: by period ---")
    print(fmt(split_stats(net, SPL)).to_string())

# --- correlation: is macro just re-deriving BTC trend?
print(f"\ncorr(macro score, BTC MA100 trend) = {comp.corr(btc_trend):.3f}")
print(f"macro score mean={comp.mean():.3f}  ; distribution:\n{comp.value_counts().sort_index().to_string()}")
