"""Daily net returns of the rates-bonds sleeves already deployed, for correlation checks.

    from deployed_sleeves import deployed_returns
    r = deployed_returns()        # DataFrame: treasury-flow-calendar, muni-reinvestment-flow

Each sleeve is rebuilt from its own `strategy.py` with spec defaults and costed at the 2 bp
per side its research used. Modules are loaded by path, because every idea folder names its
entry point `strategy.py`.
"""
import importlib.util
import os
import sys

import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_RB = os.path.abspath(os.path.join(_HERE, ".."))
sys.path.insert(0, _HERE)
from rb_data import etf_close, rl  # noqa: E402


def load_strategy(short_name):
    path = os.path.join(_RB, short_name, "strategy.py")
    spec = importlib.util.spec_from_file_location(f"strategy_{short_name.replace('-', '_')}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def deployed_returns(cost_bps=2.0):
    out = {}
    tfc = load_strategy("treasury-flow-calendar")
    tlt = etf_close(["TLT"])["TLT"].dropna()
    w = tfc.target_weight(tlt)
    out["treasury-flow-calendar"], _ = rl.backtest(w, tlt, cost_bps=cost_bps, ann=252.0)
    mrf = load_strategy("muni-reinvestment-flow")
    px = etf_close(mrf.TICKERS).dropna(how="all")
    wm = mrf.target_weights(px)
    out["muni-reinvestment-flow"], _ = rl.backtest_xs(wm, px[wm.columns], cost_bps=cost_bps, ann=252.0)
    return pd.DataFrame(out)


if __name__ == "__main__":
    r = deployed_returns()
    for c in r:
        x = r[c].dropna()
        print(c, x.index[0].date(), "Sharpe %.2f" % (x.mean() / x.std() * 252 ** 0.5))
    print(r.corr().round(3))
