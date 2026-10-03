"""exp03 — validation of the pre-expiry short (short ETH 00:00 -> 08:00 UTC on the last Friday
of each month, 10 bp/side).

1. Distribution: median, trimmed mean, largest events, leave-one-year-out.
2. Mechanism conditioning (a-priori): prior 7-day move, DVOL level, expiry size proxy (year).
3. Event bootstrap of the net Sharpe, deflated Sharpe at the honest trial count.
4. Entry/exit neighbourhood of the costed sleeve.
5. vectorbt cross-check.
6. Truncation test of strategy.target_weight.
"""
import importlib.util
import os

import numpy as np
import pandas as pd

import common as c
from common import ek

pd.set_option("display.width", 260)
H, D = pd.Timedelta(hours=1), pd.Timedelta(days=1)
p = c.price_at("ETHUSDT", start="2019-11-01")
pb = c.price_at("BTCUSDT", start="2019-11-01")
end = p.index.max() - 1 * D
ex = c.expiries(end)
me = ex.index[ex != "weekly"]
IS, OOS = (c.START, c.IS_END), (c.OOS_START, None)
x = c.window_ret(p, me, -8 * H, 0 * H)

print("1. distribution of the T-8h..T log return on month-end expiries (bp)")
for k, (a, b) in {"Full": (c.START, None), "IS": IS, "OOS": OOS}.items():
    s = x.loc[a:b].dropna() * 1e4
    tr = s.sort_values().iloc[2:-2]
    print(f"  {k:4s} n {len(s)}  mean {s.mean():+.0f}  median {s.median():+.0f}  trimmed(2+2) {tr.mean():+.0f}  sd {s.std():.0f}  "
          f"share<0 {np.mean(s < 0):.2f}  share<-20bp (pays the round trip) {np.mean(s < -20):.2f}  skew {s.skew():+.2f}")
print("  five most negative:", ", ".join(f"{d.date()} {v * 1e4:+.0f}" for d, v in x.nsmallest(5).items()))
print("  five most positive:", ", ".join(f"{d.date()} {v * 1e4:+.0f}" for d, v in x.nlargest(5).items()))
print("  leave-one-year-out mean (bp):", {y: round(x[x.index.year != y].mean() * 1e4) for y in range(2020, 2027)})

print("\n2. conditioning")
pre7 = c.window_ret(p, me, -7 * D, -8 * H)
pre30 = c.window_ret(p, me, -30 * D, -8 * H)
dv = pd.read_parquet(os.path.join(c.REPO, "data", "DERIBIT_DVOL_ETH_1h.parquet"))["Close"]
dv.index = pd.to_datetime(dv.index) + H                      # value known at the bar close
dvol = dv.reindex(me - 8 * H, method="ffill", tolerance=6 * H).set_axis(me)


def ms(s):
    s = s.dropna()
    return f"{s.mean() * 1e4:+5.0f} (t {s.mean() / s.std() * np.sqrt(len(s)):+.1f}, n {len(s)})" if len(s) > 4 else "n/a"


for nm, cond in (("prior 7 d up", pre7 > 0), ("prior 7 d down", pre7 <= 0), ("prior 30 d up", pre30 > 0), ("prior 30 d down", pre30 <= 0),
                 ("DVOL above its median", dvol > dvol.median()), ("DVOL below its median", dvol <= dvol.median())):
    print(f"  {nm:22s} IS {ms(x[cond].loc[IS[0]:IS[1]])}   OOS {ms(x[cond].loc[OOS[0]:])}   full {ms(x[cond])}")
print(f"  Spearman corr(prior 7 d move, dip) {pre7.corr(x, method='spearman'):+.2f}; with prior 30 d {pre30.corr(x, method='spearman'):+.2f}")

# ---------------------------------------------------------------- costed sleeve via strategy.py
spec = importlib.util.spec_from_file_location("strategy", os.path.join(c.HERE, "strategy.py"))
st = importlib.util.module_from_spec(spec); spec.loader.exec_module(st)
h = ek.ed.bars("ETHUSDT", "1h", start="2019-11-01")["Close"]
w = st.target_weight(h)
net, s0 = ek.ed.bt(w, h)
dnet = ek.ed.to_daily(net).loc[c.START:]
ev = net.loc[c.START:].groupby(pd.Grouper(freq="MS")).sum()
ev = ev[ev != 0]


def sh(d):
    return d.mean() / d.std() * np.sqrt(365)


print("\n3. costed sleeve (strategy.target_weight, 10 bp/side)")
eq = (1 + dnet).cumprod()
print(f"  Sharpe full {sh(dnet):.2f} / IS {sh(dnet.loc[:c.IS_END]):.2f} / OOS {sh(dnet.loc[c.OOS_START:]):.2f}; CAGR {eq.iloc[-1] ** (365 / len(dnet)) - 1:+.2%}; "
      f"vol {dnet.std() * np.sqrt(365):.2%}; MaxDD {(eq / eq.cummax() - 1).min():.2%}; events {len(ev)}; "
      f"net per event {ev.mean() * 1e4:+.0f} bp (t {ev.mean() / ev.std() * np.sqrt(len(ev)):+.2f}); hit {np.mean(ev > 0):.2f}")
hw = w.shift(1).fillna(0)
print(f"  time in market {np.mean(hw.loc[c.START:] != 0):.3%}; turnover {hw.diff().abs().loc[c.START:].sum() / (len(dnet) / 365):.1f}x/yr; avg exposure {hw.loc[c.START:].mean():+.4f}")
yr = dnet.groupby(dnet.index.year).agg(lambda s: (1 + s).prod() - 1)
print("  yearly return:", {int(k): f"{v:+.1%}" for k, v in yr.items()})

rng = np.random.default_rng(3)
e = ev.to_numpy()
bs = []
for _ in range(10000):
    s = rng.choice(e, len(e), replace=True)
    bs.append(s.mean() / s.std() * np.sqrt(12))
bs = np.array(bs)
print(f"  event bootstrap of annualised Sharpe (monthly events): median {np.median(bs):.2f}, 5-95% [{np.percentile(bs, 5):.2f}, {np.percentile(bs, 95):.2f}], P(>0) {np.mean(bs > 0):.3f}, P(>0.5) {np.mean(bs > 0.5):.2f}")
for n_tr in (1, 16, 64):
    print(f"  deflated Sharpe, {n_tr} trials: {ek.rl.deflated_sharpe(sh(dnet), len(dnet), n_tr, skew=dnet.skew(), kurt=dnet.kurtosis() + 3, ann=365):.2f}")
print("  costs:", {cst: round(sh(ek.ed.to_daily(ek.ed.bt(w, h, cost_bps=cst)[0]).loc[c.START:]), 2) for cst in (0, 5, 10, 15, 20, 30)})

print("\n4. neighbourhood: entry hour (UTC, on the expiry Friday; negative = Thursday) x exit hour, net Sharpe full | IS | OOS")
rows = {}
for entry in (-8, -4, 0, 2, 4, 6):
    r = {}
    for exit_ in (7, 8, 9, 12):
        w2 = st.target_weight(h, entry_hour=entry, exit_hour=exit_)
        d2 = ek.ed.to_daily(ek.ed.bt(w2, h)[0]).loc[c.START:]
        r[f"exit {exit_:02d}:00"] = f"{sh(d2):+.2f} | {sh(d2.loc[:c.IS_END]):+.2f} | {sh(d2.loc[c.OOS_START:]):+.2f}"
    rows[f"entry {entry:+d}h"] = r
print(pd.DataFrame(rows).T.to_string())
print("  other Fridays of the month with the spec window (placebo): ",
      {k: round(sh(ek.ed.to_daily(ek.ed.bt(st.target_weight(h, which=k), h)[0]).loc[c.START:]), 2) for k in ("first", "second", "third", "last")})
wb = st.target_weight(ek.ed.bars("BTCUSDT", "1h", start="2019-11-01")["Close"])
hb = ek.ed.bars("BTCUSDT", "1h", start="2019-11-01")["Close"]
db = ek.ed.to_daily(ek.ed.bt(wb, hb)[0]).loc[c.START:]
print(f"  same spec on BTC: {sh(db):+.2f} | {sh(db.loc[:c.IS_END]):+.2f} | {sh(db.loc[c.OOS_START:]):+.2f}; corr of daily P&L with the ETH sleeve {db.corr(dnet):.2f}")

print("\n5. vectorbt cross-check")
try:
    import vectorbt as vbt
    wv = w.shift(1).fillna(0.0)                          # weight in force during bar t
    size = wv.shift(-1).fillna(0.0)                      # order placed at the close of bar t for bar t+1
    pf = vbt.Portfolio.from_orders(h.loc["2019-12-01":], size=size.loc["2019-12-01":], size_type="targetpercent",
                                   fees=0.001, freq="1h", init_cash=1e6)
    rv = pf.returns()
    dv_ = (1 + rv).groupby(rv.index.floor("D")).prod() - 1
    dv_ = dv_.loc[c.START:]
    print(f"  vectorbt Sharpe {sh(dv_):.3f} vs research_lib {sh(dnet):.3f}; daily return corr {dv_.corr(dnet):.4f}; total return {pf.total_return():+.2%}")
except Exception as e_:  # noqa: BLE001
    print("  vectorbt failed:", repr(e_))

print("\n6. truncation test of strategy.target_weight")
for cut in ("2021-07-30 03:00", "2023-12-29 08:00", "2025-06-27 00:00", "2026-03-15 12:00"):
    h2 = h.loc[:cut]
    w2 = st.target_weight(h2)
    print(f"  cut {cut}: max|dw| = {(w2 - w.loc[:cut]).abs().max():.1e}; last weight {w2.iloc[-1]:+.0f}")
