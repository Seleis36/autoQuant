"""exp03 -- validation of the headline configuration (BTC+ETH always-on carry):
worst days, stress windows, yearly, block-bootstrap CI, premium-index cross-check,
margin/liquidation simulation, entry-basis slippage, and return on capital at several perp leverages."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd
from carry_lib import *
from research_lib import newey_west_t
OUT = os.path.dirname(os.path.abspath(__file__))
pd.set_option("display.width", 200)

syms = ["BTCUSDT", "ETHUSDT"]
pairs = {s: load_pair(s, start="2020-01-01") for s in syms}
idx = pd.date_range("2020-01-01", min(p.index.max() for p in pairs.values()), freq="h")
nets, avail = {}, {}
for s in syms:
    net, we, turn = backtest_carry(pairs[s], pd.Series(1.0, index=pairs[s].index))
    nets[s] = net.reindex(idx).fillna(0.0); avail[s] = pd.Series((idx >= pairs[s].index[0]).astype(float), index=idx)
N = pd.DataFrame(nets); A = pd.DataFrame(avail)
port = ((N * A).sum(axis=1) / A.sum(axis=1)).fillna(0.0)
d = daily(port)
print("=== headline BTC+ETH always-on, daily stats"); print(perf_stats(d).round(4).to_string())
print("\nyearly:"); print(d.groupby(d.index.year).agg(ret=lambda x:(1+x).prod()-1, sharpe=lambda x:x.mean()/x.std()*np.sqrt(365), mdd=lambda x:((1+x).cumprod()/(1+x).cumprod().cummax()-1).min()).round(4))
print("\nworst 10 days:"); print(d.nsmallest(10).round(5))
print("\nworst 10 weeks:"); w = (1+d).resample("W").prod()-1; print(w.nsmallest(10).round(5))
stress = {"covid_2020-03": ("2020-03-08","2020-03-20"), "may2021": ("2021-05-15","2021-05-25"), "luna_2022-05": ("2022-05-05","2022-05-15"),
          "ftx_2022-11": ("2022-11-06","2022-11-15"), "aug2024": ("2024-08-02","2024-08-08"), "feb2025": ("2025-02-01","2025-02-05")}
print("\nstress windows (cum return):")
for k,(a,b) in stress.items(): print(f"  {k:14s} {((1+d.loc[a:b]).prod()-1)*1e4:8.1f} bp")

# block bootstrap of the annualised Sharpe (daily, 10-day blocks)
rng = np.random.default_rng(0); x = d.values; n = len(x); B = 2000; L = 10
sh = []
for _ in range(B):
    starts = rng.integers(0, n - L, size=n // L + 1)
    smp = np.concatenate([x[s:s+L] for s in starts])[:n]
    sh.append(smp.mean()/smp.std()*np.sqrt(365))
print("\nbootstrap Sharpe 5/50/95%%: %.2f / %.2f / %.2f  P(Sharpe>3)=%.3f" % (*np.percentile(sh,[5,50,95]), np.mean(np.array(sh)>3)))
print("Newey-West t (21 lags): %.2f" % newey_west_t(x))

# premium-index cross-check for BTC: funding - d(premium) vs our perp-close basis
p = pd.read_parquet(os.path.join(DATA_DIR, "BTCUSDT_premium_1h.parquet"))["Close"]
b_close = pairs["BTCUSDT"]["b"]
j = pd.concat([p.rename("prem"), b_close.rename("basis")], axis=1).dropna()
print("\nBTC premium index vs perp/spot close basis: corr %.3f, mean prem %.5f basis %.5f, std prem %.5f basis %.5f" % (j.corr().iloc[0,1], j.prem.mean(), j.basis.mean(), j.prem.std(), j.basis.std()))

# funding contribution vs basis contribution (BTC)
df = pairs["BTCUSDT"]; r = leg_returns(df)
fund = (df["f"]*df["P"]/df["S"].shift(1)).fillna(0); basis = r - fund
print("BTC decomposition per year (bp): funding | basis-change | total")
for y, g in r.groupby(r.index.year):
    print(f"  {y}: {fund.loc[g.index].sum()*1e4:8.0f} | {basis.loc[g.index].sum()*1e4:8.0f} | {g.sum()*1e4:8.0f}")

# return on capital by perp leverage L: capital = N + N/L; plus margin simulation (isolated, no top-up between monthly resets)
print("\nreturn on capital by perp leverage (BTC+ETH always-on):")
for L in (1, 2, 3, 5):
    cf = 1/(1+1/L); dd = daily(port*cf); s = perf_stats(dd)
    print(f"  L={L}: CAGR {s.CAGR*100:5.2f}%  Vol {s.Vol*100:5.2f}%  Sharpe {s.Sharpe:5.2f}  MaxDD {s.MaxDD*100:6.2f}%")
print("\nmargin stress: max intra-month perp mark-to-market loss as % of perp notional at month start (BTC):")
S = df["S"]; P = df["P"]
worst = []
for m, g in P.groupby(P.index.to_period("M")):
    p0 = g.iloc[0]; worst.append((str(m), (g.max()/p0 - 1)))
worst = pd.Series(dict(worst)); print("  top 5 months:", worst.nlargest(5).round(3).to_dict())
print("  => with L=1 (margin = notional) and monthly margin resets, liquidation requires a +100%% move within a month; the largest was %.1f%%" % (worst.max()*100))
print("  => with L=2, liquidation requires ~+50%% within a month: months exceeding 50%%: %d" % (worst > 0.5).sum())
print("  => with L=3, ~+33%%: months exceeding: %d" % (worst > 0.33).sum())

# entry-basis sensitivity: entering when perp is *below* spot costs basis; what's the distribution of hourly basis at 00:00 UTC?
b0 = df["b"][df.index.hour == 0]
print("\nBTC basis at 00:00 UTC: mean %.1f bp, 5/50/95%%: %.1f / %.1f / %.1f bp" % (b0.mean()*1e4, *np.percentile(b0*1e4, [5,50,95])))

# save daily series for figures/report
pd.DataFrame({"port": d, **{s: daily(nets[s]) for s in syms}}).to_parquet(os.path.join(OUT, "exp03_daily.parquet"))

# --- horizon dependence: funding levels are persistent, so daily returns are positively autocorrelated
# and the daily-annualised Sharpe overstates the long-horizon Sharpe. Report both, plus Lo (2002) adjustment.
print("\n=== horizon dependence of the Sharpe (BTC+ETH always-on)")
print("daily autocorr lag 1/5/21: %.2f / %.2f / %.2f" % (d.autocorr(1), d.autocorr(5), d.autocorr(21)))
for freq, ann in (("D", 365), ("W", 52), ("MS", 12), ("QS", 4)):
    x = (1 + d).resample(freq).prod() - 1
    print(f"  {freq:2s}: Sharpe {x.mean()/x.std()*np.sqrt(ann):5.2f}  n={len(x):4d}  hit {(x>0).mean():.2f}  mean {x.mean()*100:.2f}%  std {x.std()*100:.2f}%")
for q in (5, 21, 63):
    rho = [d.autocorr(k) for k in range(1, q)]
    adj = np.sqrt(q) / np.sqrt(q + 2 * sum((q - k) * rho[k-1] for k in range(1, q)))
    print(f"  Lo(2002) q={q:2d}: daily Sharpe x {adj:.3f} = {d.mean()/d.std()*np.sqrt(365)*adj:.2f}")
