import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd
from sleeves import all_sleeves  # noqa: sets sys.path
import data, sxlib as sx
from sleeves import all_sleeves
c = data.load_panel(); o = data.load_panel(field="Open")
sl = all_sleeves(c, o)
R = {}; rows = []
for k, W in sl.items():
    st, net = sx.summary(W, c, name=k); rows.append(st); R[k] = net
R = pd.DataFrame(R).loc["2000":]
R["SPY"] = c["SPY"].pct_change().loc[R.index]
print(sx.fmt(pd.DataFrame(rows)))
print(R.corr().round(2))
print("IS corr"); print(R.loc[:"2014"].corr().round(2))
print("OOS corr"); print(R.loc["2015":].corr().round(2))
R.to_parquet(os.path.join(os.path.dirname(os.path.abspath(__file__)), "sleeve_returns.parquet"))
