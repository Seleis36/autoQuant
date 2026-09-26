"""Long SPY / VIX panel 1999-2026 (flat-cache pre2010 + current files) and excess-return backtest."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
import numpy as np, pandas as pd
import vc_data as vc, research_lib as rl

def _long(stem):
    a = pd.read_parquet(os.path.join(rl.DATA_DIR, f"{stem}_d_pre2010.parquet"))
    b = pd.read_parquet(os.path.join(rl.DATA_DIR, f"{stem}_d.parquet"))
    d = pd.concat([a[a.index < b.index.min()], b])
    d.index = pd.to_datetime(d.index).tz_localize(None)
    return d[~d.index.duplicated(keep="last")].sort_index()

def long_panel():
    spy = _long("SPY")
    idx = spy.index
    out = pd.DataFrame({"SPY": spy["Close"], "SPY_open": spy["Open"],
                        "VIX": _long("IDX_VIX")["Close"].reindex(idx).ffill(),
                        "VIX3M": _long("IDX_VIX3M")["Close"].reindex(idx).ffill(),
                        "IRX": _long("IDX_IRX")["Close"].reindex(idx).ffill()})
    out.loc[out.index < "2006-07-17", "VIX3M"] = np.nan
    return out

SPL = {"FULL": ("1999-01-01", "2026-12-31"), "PRE 99-10": ("1999-01-01", "2010-12-31"),
       "IS 11-18": ("2011-01-01", "2018-12-31"), "OOS 19-26": ("2019-01-01", "2026-12-31"),
       "08-26": ("2008-01-01", "2026-12-31")}

def bt_excess(w, P, cost_bps=2.0):
    """w: SPY weight set at close t, earns SPY excess return t->t+1; cost on |dw|."""
    r = P["SPY"].pct_change()
    rf = (P["IRX"] / 100 / 252).shift(1).fillna(0)
    w = pd.Series(np.asarray(w, dtype=float), index=P.index) if not isinstance(w, pd.Series) else w
    w = w.reindex(P.index).fillna(0)
    we = w.shift(1).fillna(0)
    net = we * (r - rf) - (we - we.shift(1).fillna(0)).abs() * cost_bps / 1e4
    return net.fillna(0), we

def row(net, we, start="1999-01-01"):
    out = {}
    for k, (a, b) in SPL.items():
        a = max(pd.Timestamp(a), pd.Timestamp(start))
        out[k] = vc.sh(net.loc[a:b])
    st = rl.perf_stats(net.loc[start:], ann=252)
    out.update({"CAGRx": st["CAGR"], "Vol": st["Vol"], "MaxDD": st["MaxDD"], "Skew": st["Skew"],
                "Exp": we.loc[start:].mean(), "TO": (we.diff().abs().sum() / (len(we.loc[start:]) / 252))})
    return out
