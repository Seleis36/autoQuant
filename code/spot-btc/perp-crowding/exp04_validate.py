"""Validation of the contrarian retail-crowding signal (global long/short ACCOUNT ratio).

State: crowd = expanding percentile rank of log(global L/S account ratio) at day-end;
       on = 1{rank < 0.5} (crowd less long than its own history).
P1 standalone   on x inv-vol(40%, hl 20 d, cap 1)                    daily
P2 trend gate   on x SMA50 x inv-vol                                   daily
P3 cbprem AND   coinbase-premium live state x on(prev day) x SMA1200h x vol   hourly

Checks: timing (snapshot 2 h / 6 h before day end; state lagged 1-2 days; ILLEGAL next-day
state), funding control (partial IC after funding 7d + return), yearly Sharpe, block
bootstrap, circular-shift placebo of the ratio, deflated Sharpe, costs, vectorbt, correlation
with the live-style sleeves.
"""
import importlib.util
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "shared"))
from btc_data import btc_daily, btc_hourly, evaluate  # noqa: E402
import research_lib as rl  # noqa: E402
from exp01_screen import MET, ranks  # noqa: E402
from exp02_backtest import START, exp_rank  # noqa: E402

rng = np.random.default_rng(11)
HPY = 365 * 24


def glob_daily(idx, cutoff_hours=0):
    """log global L/S account ratio from the last snapshot stamped < D+1 00:00 - cutoff."""
    m = pd.read_parquet(MET)["count_long_short_ratio"]
    m = m[m > 0]
    if cutoff_hours:
        m.index = m.index + pd.Timedelta(hours=cutoff_hours)     # a snapshot counts only `cutoff` h later
    d = np.log(m).resample("1D", label="left", closed="left").last()
    return d.reindex(idx)


def load_cbp():
    spec = importlib.util.spec_from_file_location("cbp", os.path.join(REPO, "code", "spot-btc", "coinbase-premium", "strategy.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def sh(net, a=None, b=None, ann=365):
    s = net.loc[a:b]
    return s.mean() / s.std() * np.sqrt(ann)


def main():
    d = btc_daily()
    close = d.Close
    r = close.pct_change()
    vs = rl.vol_target_scalar(r, target=0.40, halflife=20, cap=1.0)
    trend = (close > close.rolling(50).mean()).astype(float)
    g0 = glob_daily(close.index)
    rk = exp_rank(g0)
    on = (rk < 0).astype(float).where(rk.notna(), 0.0)
    rows, nets = [], {}

    def run(nm, w, cost=10.0):
        nets[nm], st = evaluate(w.fillna(0), close, start=START, cost_bps=cost, name=nm)
        rows.append(st)

    run("vol B&H", vs)
    run("SMA50 x vol", trend * vs)
    run("P1 standalone", on * vs)
    run("P2 trend gate", on * trend * vs)
    for ch in (2, 6):
        rk_c = exp_rank(glob_daily(close.index, ch))
        on_c = (rk_c < 0).astype(float).where(rk_c.notna(), 0.0)
        run(f"P1 snapshot {ch}h earlier", on_c * vs)
        run(f"P2 snapshot {ch}h earlier", on_c * trend * vs)
    for k in (1, 2, -1):
        tag = "legal" if k > 0 else "ILLEGAL"
        run(f"P1 state shifted {k:+d}d ({tag})", on.shift(k) * vs)
        run(f"P2 state shifted {k:+d}d ({tag})", on.shift(k) * trend * vs)
    for c in (0.0, 5.0, 20.0):
        run(f"P1 @{c:g}bp", on * vs, c)
        run(f"P2 @{c:g}bp", on * trend * vs, c)
    res = pd.concat(rows)
    pd.set_option("display.width", 200)
    print(res.round(2).to_string())
    res.to_csv(os.path.join(HERE, "exp04_validate.csv"))

    yr = pd.DataFrame({k: nets[k].loc[START:] for k in ("P1 standalone", "P2 trend gate", "SMA50 x vol", "vol B&H")})
    gy = yr.groupby(yr.index.year)
    print("\nyearly Sharpe:\n", (gy.mean() / gy.std() * np.sqrt(365)).round(2).T.to_string())
    print("\nexposure by year (P1):", on.shift(1).loc[START:].groupby(on.loc[START:].index.year).mean().round(2).to_dict())

    # funding control: partial IC of the ratio after 7d funding + 3d return
    fr = pd.read_parquet(os.path.join(REPO, "data", "BTCUSDT_fundingRate.parquet"))["last_funding_rate"]
    f7 = fr.resample("1D").sum().rolling(7).mean().reindex(close.index)   # stamps <= D 16:00 known by D+1 00:00
    fwd3 = close.shift(-3) / close - 1
    samp = close.index[::3]
    for half, (a, b) in {"IS": ("2020-09-01", "2022-12-31"), "OOS": ("2023-01-01", None)}.items():
        X = pd.DataFrame({"g": g0, "f7": f7, "r3": close.pct_change(3), "y": fwd3}).loc[samp].loc[a:b].dropna()
        R = X.rank()
        R = (R - R.mean()) / R.std()
        C = np.column_stack([R.f7, R.r3, np.ones(len(R))])
        res_g = R.g - C @ np.linalg.lstsq(C, R.g, rcond=None)[0]
        p = (res_g / res_g.std() * R.y).values
        pf = (R.f7 * R.y).values
        print(f"{half}: IC(ratio | funding7d, ret3) = {p.mean():.3f} (t {rl.newey_west_t(p, 1):.2f});"
              f" IC(funding7d) = {pf.mean():.3f} (t {rl.newey_west_t(pf, 1):.2f}); corr(ratio, funding7d) = {X.g.corr(X.f7):.2f}")

    # bootstrap, placebo, DSR
    for nm in ("P1 standalone", "P2 trend gate", "SMA50 x vol"):
        v = nets[nm].loc[START:].values
        L, B = 21, 2000
        nb = int(np.ceil(len(v) / L))
        shs = []
        for _ in range(B):
            idx = np.concatenate([np.arange(s, s + L) for s in rng.integers(0, len(v) - L, nb)])[:len(v)]
            x = v[idx]
            shs.append(x.mean() / x.std() * np.sqrt(365))
        shs = np.array(shs)
        print(f"bootstrap {nm}: median {np.median(shs):.2f} 5-95% [{np.percentile(shs, 5):.2f}, {np.percentile(shs, 95):.2f}] P(>1) {np.mean(shs > 1):.2f}")
    gv = g0.values
    ok = ~np.isnan(gv)
    pl1, pl2 = [], []
    for _ in range(200):
        k = int(rng.integers(90, ok.sum() - 90))
        gs = g0.copy()
        gs[ok] = np.roll(gv[ok], k)
        rks = exp_rank(gs)
        ons = (rks < 0).astype(float).where(rks.notna(), 0.0)
        pl1.append(sh(evaluate(ons * vs, close, start=START)[0]))
        pl2.append(sh(evaluate(ons * trend * vs, close, start=START)[0]))
    for nm, pl in (("P1 standalone", pl1), ("P2 trend gate", pl2)):
        pl = np.array(pl)
        real = sh(nets[nm])
        print(f"placebo {nm}: real {real:.2f} | mean {pl.mean():.2f} sd {pl.std():.2f} max {pl.max():.2f} | p = {np.mean(pl >= real):.3f}")
    for nm, trials in (("P1 standalone", 80), ("P2 trend gate", 80)):
        x = nets[nm].loc[START:]
        print(f"DSR {nm}: {rl.deflated_sharpe(sh(x), len(x), trials, x.skew(), x.kurt() + 3):.3f}")

    # hourly P3 + vectorbt + correlations with coinbase-premium
    cbp = load_cbp()
    hh = btc_hourly()
    hc = hh.Close
    cbc = pd.read_parquet(os.path.join(REPO, "data", "COINBASE_BTCUSD_1h.parquet"))["Close"].reindex(hc.index).ffill(limit=3)
    sp = cbp.hysteresis_state(cbp.premium_zscore(hc, cbc, 720), 0.0, -1.5)
    hr = hc.pct_change()
    hvs = (0.40 / (hr.ewm(halflife=480, min_periods=480).std() * np.sqrt(HPY))).clip(0, 1).fillna(0)
    htr = (hc > hc.rolling(1200).mean()).astype(float)
    # daily state decided at close of D (= D+1 00:00) applies to hourly bars of D+1:
    on_h = on.copy()
    on_h.index = on_h.index + pd.Timedelta(days=1) - pd.Timedelta(hours=1)   # known at the 23:00 bar's close
    on_h = on_h.reindex(hc.index, method="ffill").fillna(0)
    wc = sp * htr * hvs
    w3 = wc * on_h
    n_c, _ = rl.backtest(wc, hc, cost_bps=10, ann=HPY)
    n_3, _ = rl.backtest(w3, hc, cost_bps=10, ann=HPY)
    for nm, n in (("cbprem live spec", n_c), ("P3 cbprem AND not-crowded", n_3)):
        eq = (1 + n.loc[START:]).cumprod()
        print(f"{nm}: {sh(n, START, None, HPY):.2f} | IS {sh(n, START, '2022-12-31', HPY):.2f} | OOS {sh(n, '2023-01-01', None, HPY):.2f}"
              f" | MaxDD {(eq / eq.cummax() - 1).min():.3f}")
    dP1 = nets["P1 standalone"].loc[START:]
    dcb = n_c.loc[START:].resample("1D").sum().reindex(dP1.index)
    print("daily P&L corr: P1 vs cbprem", round(dP1.corr(dcb), 2), "| P1 vs SMA50xvol", round(dP1.corr(nets["SMA50 x vol"].loc[START:]), 2),
          "| weight corr P1 vs cbprem (hourly)", round((on_h * hvs).loc[START:].corr(wc.loc[START:]), 2))
    import vectorbt as vbt
    px = close.loc[START:]
    pf = vbt.Portfolio.from_orders(px, size=(on * vs).loc[START:], size_type="targetpercent", fees=0.001, freq="1D", init_cash=1e6)
    vr = pf.returns()
    print(f"vectorbt P1: Sharpe {vr.mean() / vr.std() * np.sqrt(365):.3f} vs custom {sh(dP1):.3f} corr {vr.corr(dP1):.4f}")


if __name__ == "__main__":
    main()
