"""alt-sleeve-blend -> equal-risk, weight-level blend of four uncorrelated liquid-alt sleeves:

  bab       regime-hedged betting-against-beta     code/crypto-alts/xs-momentum-neutral/strategy.py
  dilution  12-week circulating-supply growth      code/crypto-alts/token-dilution/strategy.py
  volume    abnormal-volume (attention) ensemble   code/crypto-alts/volume-attention/strategy.py
  funding   contrarian perp-funding crowding       code/crypto-perps/funding-xs-crowding/strategy.py

    inputs  = load_inputs(refresh_cmc=False)
    weights = blend_weights(inputs)               # DataFrame [date x yfinance ticker], incl. BTC-USD

Each sleeve's target weights (known at the close of day t, applied to t+1 exactly as
`research_lib.backtest_xs` does) are multiplied by a constant risk weight = 1 / (its daily net-return
volatility over 2018-03-08..2022-12-31, active days only), normalised to sum to 1, summed, and
multiplied by `leverage`. The constants below were fixed on the in-sample period and are NOT
re-estimated live. Net trades across sleeves offset, so the blend's turnover is below the sum of
the sleeves'.

At leverage 1.0 the blend runs ~12 % vol with average gross 0.54 (max 1.0). The spec default
leverage 2.0 (≈ BAB's own vol) gives average gross ~1.1 and max ~2.0. See
alphas/crypto-alts/alt-sleeve-blend/spec.md.

Data the live runner must keep fresh: the yfinance daily cache (all sleeves), the weekly CoinMarketCap
snapshots (`code/crypto-alts/shared/cmc.py::fetch_weekly`, incremental, dilution sleeve) and the
Binance USD-M funding history (`code/crypto-perps/shared/funding_panel.py`, funding sleeve).
"""
import importlib.util
import os
import sys

import numpy as np
import pandas as pd

RISK_WEIGHTS = {"bab": 0.2226, "dilution": 0.292143, "volume": 0.246063, "funding": 0.239194}
LEVERAGE = 2.0

_HERE = os.path.dirname(os.path.abspath(__file__))
_CA = os.path.dirname(_HERE)


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _sleeves():
    return dict(
        bab=_load(os.path.join(_CA, "xs-momentum-neutral", "strategy.py"), "asb_bab"),
        dilution=_load(os.path.join(_CA, "token-dilution", "strategy.py"), "asb_dil"),
        volume=_load(os.path.join(_CA, "volume-attention", "strategy.py"), "asb_vol"),
        funding=_load(os.path.join(_CA, "..", "crypto-perps", "funding-xs-crowding", "strategy.py"), "asb_fund"),
    )


def load_inputs(refresh_cmc=False):
    """Everything the four sleeves need, from the shared flat cache."""
    mods = _sleeves()
    inp = mods["dilution"].load_inputs(refresh_cmc=refresh_cmc)       # close, volume, btc_close, circ_supply
    sys.path.insert(0, os.path.join(_CA, "shared"))
    sys.path.insert(0, os.path.join(_CA, "..", "crypto-perps", "shared"))
    import funding_panel as fp
    from universe import load_panel, clean_close
    pan = load_panel(list(fp.PERP_OF))
    fc = clean_close(pan["Close"])
    fv = pan["Volume"].reindex_like(fc)
    fund = fp.daily_funding(list(fc.columns))[0].reindex(index=fc.index, columns=fc.columns)
    inp.update(fund_close=fc.loc["2020-01-01":], fund_volume=fv.loc["2020-01-01":],
               funding=fund.loc["2020-01-01":])
    return inp


def sleeve_weights(inp):
    mods = _sleeves()
    close, volume, btc = inp["close"], inp["volume"], inp["btc_close"]
    w = {
        "bab": mods["bab"].alt_bab_weights(close, volume, btc),
        "dilution": mods["dilution"].dilution_weights(close, volume, btc, inp["circ_supply"]),
        "volume": mods["volume"].volume_attention_weights(close, volume, btc),
        "funding": mods["funding"].target_weights(inp["fund_close"], inp["fund_volume"], inp["funding"]),
    }
    return {k: v.reindex(close.index).fillna(0.0) for k, v in w.items()}


def blend_weights(inp, risk_weights=None, leverage=LEVERAGE, sleeves=None):
    rw = dict(risk_weights or RISK_WEIGHTS)
    W = sleeve_weights(inp)
    keys = list(sleeves or rw)
    tot = sum(rw[k] for k in keys)
    cols = sorted(set().union(*[W[k].columns for k in keys]))
    out = sum(W[k].reindex(columns=cols).fillna(0.0) * (rw[k] / tot) for k in keys)
    return out * leverage
