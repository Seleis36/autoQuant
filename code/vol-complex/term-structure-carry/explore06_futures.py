"""Build constant-maturity front-two-month index from CBOE VIX futures; test basis/roll signals (2013+)."""
import sys, os, numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tsc_lib import *
pd.set_option("display.width", 220); pd.set_option("display.max_columns", 30)
fut = pd.read_parquet(os.path.join(rl.DATA_DIR, "CBOE_VX_futures_d.parquet"))
fut = fut[fut.Settle > 0][["Trade Date", "expiry", "Settle"]].rename(columns={"Trade Date": "date"})
fut = fut[fut.expiry > fut.date]                                # contract still alive after today
fut = fut.sort_values(["date", "expiry"])
fut["rank"] = fut.groupby("date").cumcount()
F = fut[fut["rank"] < 3].pivot(index="date", columns="rank", values="Settle").rename(columns={0: "F1", 1: "F2", 2: "F3"})
E = fut[fut["rank"] < 2].pivot(index="date", columns="rank", values="expiry").rename(columns={0: "E1", 1: "E2"})
F = F.join(E)
# business days to expiry
bd = lambda a, b: np.busday_count(a.values.astype("datetime64[D]"), b.values.astype("datetime64[D]"))
F["ttm1"] = bd(pd.Series(F.index), F.E1); F["ttm2"] = bd(pd.Series(F.index), F.E2)
# SPVXSTR-style weights: w1 = ttm1/period
F["w1"] = (F.ttm1 / (F.ttm1 + (F.E2 - F.E1).dt.days * 5 / 7).clip(lower=1)).clip(0, 1)   # fraction of the roll period remaining
F["w2"] = 1 - F.w1
# index return: yesterday's weights, price changes of the same contracts
# careful at roll: when E1 changes, yesterday's F1 has expired (settled at open); use yesterday's F2 -> today's F1
prevE1 = F.E1.shift(1)
same = (F.E1 == prevE1)
dF1 = np.where(same, F.F1 - F.F1.shift(1), np.nan); dF2 = np.where(same, F.F2 - F.F2.shift(1), np.nan)
# on roll day (yesterday's E1 == today's date basically): yesterday's F2 becomes today's F1
dF2_roll = F.F1 - F.F2.shift(1)
dF1 = pd.Series(dF1, F.index); dF2 = pd.Series(dF2, F.index)
w1p, w2p = F.w1.shift(1), F.w2.shift(1)
num = np.where(same, w1p * dF1 + w2p * dF2, w2p * dF2_roll + w1p * 0.0)   # expired F1: its last-day pnl ~0 (settle to VIX SOQ; ignore)
den = w1p * F.F1.shift(1) + w2p * F.F2.shift(1)
F["idx_ret"] = pd.Series(num, F.index) / den
df = load_all(); f = features(df)
common = df.index.intersection(F.index)
vr = df.vixy.pct_change().reindex(common); ir = F.idx_ret.reindex(common)
print("corr(VIXY ret, synthetic index ret):", round(vr.corr(ir), 4), " mean diff bp/day:", round((vr - ir).mean() * 1e4, 2),
      " n=", len(common), common.min().date(), common.max().date())
by_year = pd.DataFrame({"vixy": vr, "syn": ir}).groupby(common.year).apply(lambda x: pd.Series({"corr": x.vixy.corr(x.syn), "vixy_cagr": (1 + x.vixy).prod() - 1, "syn_cagr": (1 + x.syn).prod() - 1}))
print(by_year.round(3).to_string())
# --- signals
S = F.reindex(common)
vix = df.vix.reindex(common)
S["basis1"] = S.F1 / vix - 1
S["roll12"] = S.F2 / S.F1 - 1                                    # VIXY's actual roll cost between front months
S["droll"] = (S.F1 - vix) / S.ttm1.clip(lower=1)                  # Simon-Campasano daily roll (points/day)
S["basket_basis"] = (S.w1 * S.F1 + S.w2 * S.F2) / vix - 1
S["slope"] = f.slope.reindex(common)
print("\ncorr of signals:\n", S[["basis1", "roll12", "droll", "basket_basis", "slope"]].corr().round(2))
closes = df[["vixy", "spy"]].reindex(common); COST = {"vixy": 5.0, "spy": 5.0}
res = {}
def run(name, w, lag=0):
    W = pd.DataFrame({"vixy": w, "spy": 0.0}, index=common).fillna(0.0)
    if lag: W = W.shift(lag).fillna(0.0)
    net, st = bt_multi(W, closes, COST, name=name); r = report(net)
    res[name] = {"Sh_full": r.Sharpe["full"], "Sh_IS": r.Sharpe["IS"], "Sh_OOS": r.Sharpe["OOS"], "CAGR": r.CAGR["full"], "MDD": r.MaxDD["full"], "TO": st["Turnover_ann"], "Gross": st["GrossExp"], "t_NW": r.t_NW["full"]}
    return net
run("ref: slope>1 (2013+)", -(S.slope > 1).astype(float))
run("ref: always short (2013+)", pd.Series(-1.0, common))
for th in [0.0, 0.02, 0.05, 0.10]:
    run(f"basis1>{th}", -(S.basis1 > th).astype(float))
    run(f"basket_basis>{th}", -(S.basket_basis > th).astype(float))
    run(f"roll12>{th}", -(S.roll12 > th).astype(float))
for th in [0.0, 0.05, 0.10, 0.20]:
    run(f"droll>{th} short / <-{th} long", -(S.droll > th).astype(float) + (S.droll < -th).astype(float))
    run(f"droll>{th} short-only", -(S.droll > th).astype(float))
run("basis1>0 & roll12>0", -((S.basis1 > 0) & (S.roll12 > 0)).astype(float))
run("basis1>0.05 lag1", -(S.basis1 > 0.05).astype(float), lag=1)
print(pd.DataFrame(res).T.round(2).to_string())
F.to_parquet(os.path.join(os.path.dirname(os.path.abspath(__file__)), "vx_curve.parquet"))
