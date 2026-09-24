"""exp07 — (a) strategy.py reproduces the exp06 ensemble; (b) is the funding sleeve better when
funding is dispersed across coins? Regime = trailing-30d mean of the XS std of daily funding;
threshold = its IS median (fixed from IS data only). Sleeve on only in high-dispersion regime."""
import numpy as np
import pandas as pd
import common as c
import research_lib as rl
import strategy as st

close, vol, fund, mask = c.load()
w = st.target_weights(close, vol, fund)
net, row = c.evaluate(w, close, "strategy.py")
print({k: round(v, 2) if isinstance(v, float) else v for k, v in row.items()})

disp = fund.where(mask).std(axis=1).rolling(30).mean()
thr = disp.loc[c.IS[0]:c.IS[1]].median()
rows = []
for nm, on in (("always", pd.Series(1.0, index=w.index)),
               ("high_disp", (disp > thr).astype(float)),
               ("low_disp", (disp <= thr).astype(float))):
    _, r = c.evaluate(w.mul(on, axis=0), close, nm)
    r["time_on"] = on.loc[c.FULL[0]:].mean()
    rows.append(r)
print(rl.fmt(pd.DataFrame(rows).set_index("name")).to_string())
