"""Screen mechanism families that can be net short in bear markets."""
from common import *

D = load(n_top=15)
c, mask, btc, ret = D["c_alt"], D["mask"], D["btc"], D["ret"]
n = mask.sum(axis=1).replace(0, np.nan)
ew = mask.astype(float).div(n, axis=0)                      # equal-weight PIT basket
basket_ret = (ew.shift(1) * ret).sum(axis=1)                 # EW alt basket close-to-close
basket_idx = (1 + basket_ret).cumprod()
btc_ret = btc.pct_change()
rows = {}

def rec(name, w, close=c, cost=COST):
    net, st = rl.backtest_xs(w, close, cost_bps=cost, ann=ANN)
    sp = rl.split_stats(net, SPLITS, ann=ANN); rg = regime_table(net, btc)
    rows[name] = dict(full=sp.loc["full","Sharpe"], IS=sp.loc["IS","Sharpe"], OOS=sp.loc["OOS","Sharpe"],
                      bull=rg.loc["bull","Sharpe"], bear=rg.loc["bear","Sharpe"],
                      cagr=sp.loc["full","CAGR"], mdd=sp.loc["full","MaxDD"], turn=st["Turnover_ann"], gross=st["AvgGross"])
    return net

# vol scaling per asset (past data only)
vol = ret.ewm(halflife=20, min_periods=20).std() * np.sqrt(ANN)

# --- A. per-alt TSMOM long/short, equal risk, gross capped at 1
for lb in [14, 21, 30, 60, 90, 120]:
    sgn = np.sign(c / c.shift(lb) - 1).where(mask)
    w = (sgn * (0.5 / vol)).where(mask).fillna(0.0)
    w = w.div(w.abs().sum(axis=1).clip(lower=1.0), axis=0)          # gross <= 1
    rec(f"A_tsmom_{lb}", w)
    # long/flat vs short-only legs
    rec(f"A_tsmom_{lb}_shortonly", w.clip(upper=0))
    rec(f"A_tsmom_{lb}_longonly", w.clip(lower=0))

# --- A2. SMA-based per-alt trend
for lb in [20, 50, 100, 200]:
    sgn = np.sign(c - c.rolling(lb).mean()).where(mask)
    w = (sgn * (0.5 / vol)).where(mask).fillna(0.0)
    w = w.div(w.abs().sum(axis=1).clip(lower=1.0), axis=0)
    rec(f"A2_sma_{lb}", w)

# --- B. alt vs BTC relative TSMOM: long alt/short BTC or reverse, hedged with BTC
rel = c.div(btc, axis=0)
closeB = pd.concat([c, btc.rename("BTC-USD")], axis=1)
for lb in [14, 30, 60, 90]:
    sgn = np.sign(rel / rel.shift(lb) - 1).where(mask)
    w_alt = (sgn / n.values[:, None]).where(mask).fillna(0.0) * 0.5
    w = w_alt.copy(); w["BTC-USD"] = -w_alt.sum(axis=1)
    rec(f"B_relmom_{lb}", w, closeB)
    # short-only relative: only short alts that are weak vs BTC, long BTC
    w_alt_s = w_alt.clip(upper=0); w2 = w_alt_s.copy(); w2["BTC-USD"] = -w_alt_s.sum(axis=1)
    rec(f"B_relmom_{lb}_short_alt", w2, closeB)

# --- B2. structural: always short EW alt basket vs long BTC
w = -ew * 0.5; w["BTC-USD"] = 0.5
rec("B2_short_alts_long_btc", w, closeB)

# --- C. basket-level trend: long/short EW basket by basket SMA / BTC SMA
for lb in [20, 50, 100, 200]:
    for src, sname in ((basket_idx, "basket"), (btc, "btc")):
        sgn = np.sign(src - src.rolling(lb).mean())
        w = ew.mul(sgn, axis=0).fillna(0.0)
        rec(f"C_{sname}sma_{lb}_LS", w)
        rec(f"C_{sname}sma_{lb}_L0", w.clip(lower=0))
        rec(f"C_{sname}sma_{lb}_0S", w.clip(upper=0))

# --- D. betting against beta (60d beta to BTC), dollar-neutral rank weights
for lb in [30, 60, 90]:
    cov = ret.rolling(lb).cov(btc_ret); var = btc_ret.rolling(lb).var()
    beta = cov.div(var, axis=0)
    w = rl.linear_weights(-rl.rank_xs(beta, mask), mask, gross=1.0)
    rec(f"D_bab_{lb}", w)
    w = rl.linear_weights(-rl.rank_xs(beta, mask), mask, gross=1.0).rolling(7, min_periods=1).mean()
    rec(f"D_bab_{lb}_h7", w)

# --- E. low vol XS
for lb in [30, 60]:
    rv = ret.rolling(lb).std()
    w = rl.linear_weights(-rl.rank_xs(rv, mask), mask, gross=1.0).rolling(7, min_periods=1).mean()
    rec(f"E_lowvol_{lb}", w)

# --- F. regime-conditioned XS momentum: bull -> long top; bear -> short bottom (14d, hold 7)
mom = c / c.shift(14) - 1
reg = btc_regime(btc, 200)
wl = rl.quantile_weights(mom, mask, q=0.3, gross=1.0, long_only=True)
ws = -rl.quantile_weights(-mom, mask, q=0.3, gross=1.0, long_only=True)
w = wl.mul(reg, axis=0) + ws.mul(1 - reg, axis=0)
rec("F_regime_mom14", w.rolling(7, min_periods=1).mean())
wq = rl.quantile_weights(mom, mask, q=0.3, gross=1.0)
rec("F_neutral_mom14_h7", wq.rolling(7, min_periods=1).mean())
# neutral book + regime tilt (net long in bull, net short in bear), gross 1
w = 0.5 * wq.rolling(7, min_periods=1).mean() + 0.5 * ew.mul(2 * reg - 1, axis=0)
rec("F_neutral_plus_regime", w)

# --- G. references
rec("G_ew_basket_BH", ew)
rec("G_btc_BH", pd.DataFrame({"BTC-USD": 1.0}, index=btc.index), pd.DataFrame({"BTC-USD": btc}))

df = pd.DataFrame(rows).T
pd.set_option("display.width", 220)
print(df.round(2).to_string())
df.to_csv(os.path.join(HERE, "families_02.csv"))
