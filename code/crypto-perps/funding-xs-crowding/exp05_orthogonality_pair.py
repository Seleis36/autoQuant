"""exp05 — (B) is contrarian funding just betting-against-beta? correlation + 50/50 combo.
(D) ETH/BTC pair timed by the ETH-minus-BTC funding spread (both signs, k in 3,7,14,30)."""
import itertools
import numpy as np
import pandas as pd
import common as c
import research_lib as rl
from exp02_refine import beta_neutral, beta

close, vol, fund, mask = c.load()
ret = close.pct_change()

# (B)
wf = c.tranche(beta_neutral(rl.quantile_weights(-fund.rolling(30, min_periods=21).mean(), mask, q=0.3), beta), 7)
wb = c.tranche(beta_neutral(rl.quantile_weights(-beta, mask & beta.notna(), q=0.3), beta), 14)
nf, rf = c.evaluate(wf, close, "funding_L30_h7_beta")
nb, rb = c.evaluate(wb, close, "BAB_beta_neutral_h14")
nc, rc = c.evaluate(0.5 * wf + 0.5 * wb, close, "combo_50_50")
print(pd.DataFrame([rf, rb, rc]).set_index("name").round(2).to_string())
print("corr daily funding vs BAB:", round(nf.corr(nb), 2))
# rank correlation of the two signals
fr = (-fund.rolling(30, min_periods=21).mean()).where(mask).rank(axis=1)
br = (-beta).where(mask).rank(axis=1)
print("avg XS rank corr (signal level):", round(fr.corrwith(br, axis=1).mean(), 2))
# residual: funding factor regressed on BAB
x = pd.concat([nf, nb], axis=1).dropna()
b = np.polyfit(x.iloc[:, 1], x.iloc[:, 0], 1)
res = x.iloc[:, 0] - b[0] * x.iloc[:, 1]
print("funding loading on BAB:", round(b[0], 2), "alpha Sharpe:", rl.split_stats(res, c.SPLITS)["Sharpe"].round(2).to_dict())

# (D) ETH/BTC pair
spread = fund["ETH-USD"] - fund["BTC-USD"]
pair_close = pd.concat([close["ETH-USD"], close["BTC-USD"]], axis=1)
rows = []
for k, sign, h in itertools.product((3, 7, 14, 30), (+1, -1), (1, 7)):
    s = np.sign(spread.rolling(k).mean() - spread.rolling(90, min_periods=60).mean()) * sign
    w = pd.DataFrame({"ETH-USD": 0.5 * s, "BTC-USD": -0.5 * s}).fillna(0)
    w = c.tranche(w, h)
    _, row = c.evaluate(w, pair_close, f"ethbtc_{'+' if sign > 0 else '-'}k{k}_h{h}")
    rows.append(row)
print(rl.fmt(pd.DataFrame(rows).set_index("name")).to_string())
