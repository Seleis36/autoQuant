"""Compare hedge regimes (always-bn / switch / bear target betas), vol-targeting, and OOS leg composition."""
from common import *
from strategy import alt_bab_weights, pit_universe, ewm_beta
import itertools

p = load_panel(); close_all = clean_close(p["Close"]); vol_all = p["Volume"].reindex(columns=close_all.columns)
alts = [t for t in ALTS if t in close_all]
c, v, btc = close_all[alts], vol_all[alts], close_all["BTC-USD"]

def evaluate(w, cost=COST):
    net, st = rl.backtest_xs(w, c, cost_bps=cost, ann=ANN)
    sp = rl.split_stats(net, SPLITS, ann=ANN); bs = bear_stats(net)
    return net, dict(full=sp.loc["full","Sharpe"], IS=sp.loc["IS","Sharpe"], OOS=sp.loc["OOS","Sharpe"],
                     xbear=bs.loc["bear_pooled","Sharpe"], xnon=bs.loc["non_bear","Sharpe"],
                     b18=bs.iloc[1]["Sharpe"], b19=bs.iloc[2]["Sharpe"], b21=bs.iloc[3]["Sharpe"], b22=bs.iloc[4]["Sharpe"], b25=bs.iloc[5]["Sharpe"],
                     cagr=sp.loc["full","CAGR"], mdd=sp.loc["full","MaxDD"], turn=st["Turnover_ann"], netexp=st["AvgNet"])

# --- hedge-mode distributions over the same (ntop, hl, q, hold) grid
modes = {"always_bn": dict(regime_sma=None),
         "switch_dn": dict(regime_sma=50),
         "switch_b-0.1": dict(regime_sma=50, bear_target_beta=-0.10),
         "switch_b-0.2": dict(regime_sma=50, bear_target_beta=-0.20),
         "always_dn": dict(regime_sma=10**6)}                # rolling mean NaN -> never bull -> always dn
rows = {}
for (mname, kw), ntop, hl, q, hold in itertools.product(modes.items(), [15, 20, 25], [30, 60], [0.25, 0.3, 0.4], [7, 14, 21]):
    w = alt_bab_weights(c, v, btc, n_top=ntop, beta_halflife=hl, q=q, hold=hold, **kw)
    rows[(mname, ntop, hl, q, hold)] = evaluate(w)[1]
df = pd.DataFrame(rows).T; df.index.names = ["mode", "ntop", "hl", "q", "hold"]
pd.set_option("display.width", 250); pd.set_option("display.max_rows", 500)
print("median by mode (54 configs each):\n", df.groupby(level="mode")[["full","IS","OOS","xbear","xnon","b18","b19","b21","b22","b25","mdd","turn","netexp"]].median().round(2).to_string())
print("\n25th pct by mode:\n", df.groupby(level="mode")[["full","IS","OOS","xbear"]].quantile(0.25).round(2).to_string())
print("\nP(OOS>=1) by mode:\n", df.groupby(level="mode")["OOS"].apply(lambda s: (s>=1).mean()).round(2).to_string())
df.to_csv(os.path.join(HERE, "compare_07.csv"))

# --- vol targeting on the switch book (portfolio-level, scale-down only)
w0 = alt_bab_weights(c, v, btc)
net0, _ = rl.backtest_xs(w0, c, cost_bps=0.0, ann=ANN)      # gross-of-cost strategy return for vol estimate
print("\nbase:", {k: round(x, 2) for k, x in evaluate(w0)[1].items()})
for tgt in [0.15, 0.20, 0.25]:
    for hl in [10, 20]:
        vol = net0.ewm(halflife=hl, min_periods=hl).std() * np.sqrt(ANN)
        s = (tgt / vol).clip(upper=1.0).fillna(0.0)
        print(f"voltarget {tgt} hl{hl}:", {k: round(x, 2) for k, x in evaluate(w0.mul(s, axis=0))[1].items()})

# --- OOS leg composition
mask = pit_universe(c, v); beta = ewm_beta(c.pct_change(), btc.pct_change(), 60)
wl = w0.clip(lower=0); ws = w0.clip(upper=0)
print("\nOOS long-leg days held (top 15):\n", (wl.loc["2023":] > 0).sum().sort_values(ascending=False).head(15).to_string())
print("\nOOS short-leg days held (top 15):\n", (ws.loc["2023":] < 0).sum().sort_values(ascending=False).head(15).to_string())
# per-name contribution OOS
ret = c.pct_change()
contrib = (w0.shift(1) * ret).loc["2023":].sum().sort_values()
print("\nOOS contribution bottom 8:\n", contrib.head(8).round(3).to_string(), "\ntop 8:\n", contrib.tail(8).round(3).to_string())
print("\nuniverse size:", mask.sum(axis=1).loc["2018":].describe().round(1).to_dict())
print("first non-zero weight date:", w0.abs().sum(axis=1).gt(0).idxmax())
net_b, _ = rl.backtest_xs(w0, c, cost_bps=COST, ann=ANN)
print("\nyearly:\n", yearly(net_b).round(2).to_string())
print("\nmonthly 2025-2026:\n", net_b.loc["2025":].resample("ME").apply(lambda s: (1+s).prod()-1).round(3).to_string())
