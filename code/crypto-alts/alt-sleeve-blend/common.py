"""alt-sleeve-blend: sleeve weight panels on one shared calendar/universe of columns."""
import os, sys, warnings
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
_HERE = os.path.dirname(os.path.abspath(__file__))
_CA = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(_CA, "shared")); sys.path.insert(0, os.path.join(_CA, "..", "shared"))
import research_lib as rl  # noqa
import study as S  # noqa
import importlib.util


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


BAB = _load(os.path.join(_CA, "xs-momentum-neutral", "strategy.py"), "bab_strategy")
DIL = _load(os.path.join(_CA, "token-dilution", "strategy.py"), "dil_strategy")
VOL = _load(os.path.join(_CA, "volume-attention", "strategy.py"), "vol_strategy")
FUND = _load(os.path.join(_CA, "..", "crypto-perps", "funding-xs-crowding", "strategy.py"), "fund_strategy")
sys.path.insert(0, os.path.join(_CA, "..", "crypto-perps", "shared"))


def sleeve_weights():
    """Dict of target-weight frames (columns: yfinance tickers incl. BTC-USD where hedged)."""
    inp = DIL.load_inputs()
    close, volume, btc = inp["close"], inp["volume"], inp["btc_close"]
    out = {
        "bab": BAB.alt_bab_weights(close, volume, btc),
        "dilution": DIL.dilution_weights(**inp),
        "volume": VOL.volume_attention_weights(close, volume, btc),
    }
    import funding_panel as fp
    from universe import load_panel, clean_close
    tick = list(fp.PERP_OF)                                   # exactly the crypto-perps study inputs
    pan = load_panel(tick)
    fc = clean_close(pan["Close"]); fv = pan["Volume"].reindex_like(fc)
    fund = fp.daily_funding(list(fc.columns))[0].reindex(index=fc.index, columns=fc.columns)
    wf = FUND.target_weights(fc.loc["2020-01-01":], fv.loc["2020-01-01":], fund.loc["2020-01-01":])
    out["funding"] = wf.reindex(close.index).fillna(0.0)
    full = close.join(btc.rename("BTC-USD"))
    extra = [t for t in wf.columns if t not in full.columns]
    full = full.join(fc[extra]) if extra else full
    return out, full
