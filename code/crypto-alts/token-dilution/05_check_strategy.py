"""strategy.py must reproduce the research book exactly."""
from common import *
from strategy import load_inputs, dilution_weights
inp = load_inputs()
w = dilution_weights(**inp)
close = inp["close"].join(inp["btc_close"].rename("BTC-USD"))
net, st = rl.backtest_xs(w, close[w.columns], cost_bps=10, ann=365)
ref = pd.read_parquet("robust_03_nets.parquet")["BASE dil12w|h30|bn"]
j = pd.concat([net, ref], axis=1).dropna()
print("max |diff| vs research book:", float((j.iloc[:, 0] - j.iloc[:, 1]).abs().max()))
print(S.row(net, "strategy.py"))
print("stats:", st.round(3).to_dict())
print("latest weights:", w.iloc[-1][w.iloc[-1].abs() > 1e-4].round(4).sort_values().to_dict())
w.to_parquet("weights_final.parquet")
