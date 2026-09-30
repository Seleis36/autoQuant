"""exp05 — out-of-asset replication of the leverage gate on ETH (metrics 2021-12+, first z
~2022-06): gate = z(log ETH OI coins / ETH supply, 365d) <= 1, x inverse-vol (40 %, cap 1),
vs buy & hold and SMA50 x inverse-vol. Same parameters as BTC, nothing re-fitted."""
import os, sys, importlib.util
import numpy as np
import pandas as pd
_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("rcx", os.path.join(_HERE, "..", "retail-crowding-xs", "common.py"))
rcx = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(rcx)
sys.path.insert(0, os.path.join(rcx.ROOT, "code", "crypto-alts", "shared"))
import cmc, metrics_panel as mp, research_lib as rl  # noqa: E401,E402

for tk, sym in (("ETH-USD", "ETHUSDT"), ("SOL-USD", "SOLUSDT"), ("XRP-USD", "XRPUSDT"), ("BNB-USD", "BNBUSDT")):
    px = rl.load_series(tk)["Close"].loc["2019-01-01":]
    sup = cmc.wide("circulatingSupply", cmc.yahoo_map(px.to_frame(tk)), index=px.index)[tk]
    oi = mp.daily_metrics([sym])["sum_open_interest"][sym].reindex(px.index)   # coins
    L = np.log(oi / sup).replace([np.inf, -np.inf], np.nan)
    z = (L - L.rolling(365, min_periods=180).mean()) / L.rolling(365, min_periods=180).std()
    ret = px.pct_change()
    vt = rl.vol_target_scalar(ret, target=0.40, halflife=20, cap=1.0)
    sma = (px > px.rolling(50).mean()).astype(float)
    gate = (z <= 1).astype(float).where(z.notna())
    start = z.dropna().index[0]
    out = {}
    for nm, w in {"buy&hold": pd.Series(1.0, index=px.index), "inv-vol": vt, "lev gate x inv-vol": gate * vt,
                  "SMA50 x inv-vol": sma * vt, "SMA50 x inv-vol x gate": sma * vt * gate}.items():
        net, st = rl.backtest(w.fillna(0).loc[start:], px.loc[start:], cost_bps=10)
        out[nm] = f"{rl.perf_stats(net)['Sharpe']:.2f} (OOS24+ {rl.perf_stats(net.loc['2024':])['Sharpe']:.2f}, DD {st['MaxDD']:.0%})"
    f30 = px.shift(-30) / px - 1
    ic = pd.concat([z, f30], axis=1).dropna().corr(method="spearman").iloc[0, 1]
    print(tk, "from", start.date(), f"IC30 {ic:+.3f}", out)
