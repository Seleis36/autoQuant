"""funding-carry -- market-neutral cash-and-carry on Binance: long spot, short the USD-M perp of
the same coin, collect funding. One reusable function turns raw market data into target weights.

Spec (alphas/crypto-perps/funding-carry/):
  * coins BTC and ETH, equal weight; one unit of spot long per unit of perp short on each coin;
  * exposure per coin = min(1, target_vol / EWM vol of the hedged P&L), EWM halflife 30 days on
    hourly returns, target 2 % annualised (one-leg-notional units), re-evaluated only at funding
    settlement stamps (00/08/16 UTC) so turnover stays ~1.3 units/year;
  * perp leverage L = 1 (margin equal to the perp notional), so capital_factor = 1/(1+1/L) = 0.5
    of total capital can sit in each leg's notional. Weights below are fractions of TOTAL capital.

No directional signal: the timing rules in exp01/exp02 all lose to switching costs on BTC/ETH.
The vol scaler is a risk overlay (exp05) -- it halves exposure in 2020-21 when basis noise and
funding were both extreme and makes the Sharpe hold up at weekly/monthly aggregation.

Output: DataFrame indexed by `index` with one column per instrument:
    BTCUSDT (spot)        +w_btc      BTCUSDT_PERP (perp)   -w_btc
    ETHUSDT (spot)        +w_eth      ETHUSDT_PERP (perp)   -w_eth
Weights decided at stamp t are meant to be applied from t+1 (the caller shifts them).
"""
import numpy as np
import pandas as pd

HOURS = 24 * 365

def hedged_leg_returns(spot_close, perp_close, funding):
    """Hourly return on one-leg notional of long-spot/short-perp: dS/S - dP/S + f*P/S.
    funding: series of settled rates indexed at settlement stamps (0 elsewhere after reindex)."""
    S, P = spot_close, perp_close.reindex(spot_close.index)
    f = funding.reindex(spot_close.index).fillna(0.0)
    return (S.pct_change() - P.diff() / S.shift(1) + f * P / S.shift(1)).fillna(0.0)

def target_weights(spot, perp, funding, coins=("BTCUSDT", "ETHUSDT"), leverage=1.0,
                   target_vol=0.02, halflife_hours=24 * 30, settle_hours=(0, 8, 16), cap=1.0):
    """spot, perp: dict coin -> hourly close series (UTC bar-open stamps, same grid).
    funding: dict coin -> series of settled funding rates at settlement stamps.
    Returns DataFrame of target weights (fraction of total capital) per instrument."""
    cf = 1.0 / (1.0 + 1.0 / leverage)
    per_coin = cf / len(coins)
    out = {}
    for c in coins:
        S = spot[c]
        r = hedged_leg_returns(S, perp[c], funding[c])
        vol = r.ewm(halflife=halflife_hours).std() * np.sqrt(HOURS)
        w = (target_vol / vol).clip(upper=cap)
        w = w.where(S.index.hour.isin(settle_hours)).ffill().fillna(0.0)
        out[c] = per_coin * w
        out[f"{c}_PERP"] = -per_coin * w
    return pd.DataFrame(out, index=S.index)

if __name__ == "__main__":
    import os, sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from carry_lib import load_pair
    pairs = {c: load_pair(c, start="2025-01-01") for c in ("BTCUSDT", "ETHUSDT")}
    W = target_weights({c: p["S"] for c, p in pairs.items()}, {c: p["P"] for c, p in pairs.items()},
                       {c: p["f"].where(p["f"] != 0).dropna() for c, p in pairs.items()})
    print(W.tail()); print(W.describe().round(3))
