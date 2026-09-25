"""Deployment detail: effect of capping total gross exposure (proportional scale-down on the
days the cap binds). Reported, not used to pick the spec (spec = uncapped, max gross 2.4)."""
import sys, os
_H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(_H, "..", "shared"))
import importlib.util as iu, numpy as np, pandas as pd, data, sxlib as sx
sp = iu.spec_from_file_location("bs", os.path.join(_H, "strategy.py")); m = iu.module_from_spec(sp); sp.loader.exec_module(m)
c = data.load_panel(); o = data.load_panel(field="Open")
W = m.target_weights(c, o, gross_cap=None)
rows = []
for cap in [None, 2.0, 1.5, 1.0]:
    Wc = W if cap is None else W.mul((cap / W.abs().sum(axis=1)).clip(upper=1).fillna(1), axis=0)
    st, _ = sx.summary_rf(Wc, c, name=f"cap {cap}", start="2002-01-01")
    st["days_binding_%"] = 0 if cap is None else (W.abs().sum(axis=1).loc["2002":] > cap).mean() * 100
    rows.append(st)
print(sx.fmt(pd.DataFrame(rows).rename(columns={"CAGRx": "CAGR"})))

# tail check: worst single days and 1% daily VaR by cap
for cap in [None, 2.0, 1.5, 1.0]:
    Wc = W if cap is None else W.mul((cap / W.abs().sum(axis=1)).clip(upper=1).fillna(1), axis=0)
    _, net = sx.summary(Wc, c, start="2002-01-01")
    print(f"cap {cap}: worst days % {(net.nsmallest(3) * 100).round(2).tolist()}  1% VaR {net.quantile(0.01) * 100:.2f}%  "
          f"DIP-driven worst: 2011-08-08 {net.loc['2011-08-08'] * 100:.2f}%")
