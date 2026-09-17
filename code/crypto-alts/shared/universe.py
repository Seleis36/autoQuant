"""Liquid altcoin cross-section: candidate list, panel loader, point-in-time universe.

Everything reads/writes the flat daily cache (`data/<TICKER>_d.parquet`) through
`research_lib.load_series`, so the simulated book can price any name used here.

Survivorship note: yfinance serves no delisted tickers. The candidate list below
deliberately includes names that were top-20 by market cap at some point and have since
faded (EOS, IOTA, NEO, DASH, XEM, BSV, OMG, QTUM, ...), but coins that disappeared from
Yahoo entirely are not recoverable. The point-in-time universe rule (trailing dollar
volume rank, past data only) never looks at today's ranking.
"""
import os
import sys
import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(_HERE)), "shared"))
import research_lib as rl  # noqa: E402

# Reference / hedge instruments (not part of the alt cross-section)
MAJORS = ["BTC-USD", "ETH-USD"]

# Alt candidates: the brief's core eight first, then other names that were large-cap
# and liquid at some point since 2017.
CORE = ["SOL-USD", "XRP-USD", "ADA-USD", "AVAX-USD", "LINK-USD", "DOT-USD", "LTC-USD", "BCH-USD"]
EXTENDED = [
    "XLM-USD", "EOS-USD", "TRX-USD", "ETC-USD", "XMR-USD", "NEO-USD", "IOTA-USD",
    "DASH-USD", "ZEC-USD", "ATOM-USD", "DOGE-USD", "BNB-USD", "VET-USD", "ALGO-USD",
    "FIL-USD", "AAVE-USD", "XTZ-USD", "UNI-USD", "NEAR-USD", "BSV-USD", "XEM-USD",
    "QTUM-USD", "OMG-USD", "ICP-USD", "APT-USD", "OP-USD", "SUI-USD",
    "SHIB-USD", "MATIC-USD", "POL-USD", "HBAR-USD", "THETA-USD", "EGLD-USD", "FTM-USD",
    "SAND-USD", "MANA-USD", "AXS-USD", "GRT-USD", "MKR-USD", "COMP-USD", "SNX-USD",
    "CRV-USD", "LDO-USD", "INJ-USD", "RUNE-USD", "KSM-USD", "WAVES-USD", "ZIL-USD",
    "ONT-USD", "BAT-USD", "ENJ-USD", "CHZ-USD", "FLOW-USD", "KAVA-USD", "ONE-USD",
    "CAKE-USD", "STX-USD", "TIA-USD", "SEI-USD", "PEPE-USD", "WIF-USD", "RENDER-USD",
    "IMX-USD", "FET-USD", "TAO-USD", "TON11419-USD", "TRUMP-USD", "BONK-USD",
]
ALTS = CORE + [t for t in EXTENDED if t not in CORE]

# Yahoo serves a different (pre-launch / namesake) coin under these symbols before the
# real project listed; everything before the date is masked. ARB-USD (a 2017 namesake,
# not Arbitrum) is excluded from the candidate list altogether.
VALID_FROM = {"FIL-USD": "2020-10-15", "ONE-USD": "2019-06-01", "RENDER-USD": "2021-01-01"}


def load_panel(tickers=None, fields=("Close", "Volume"), cache=True):
    """Wide frames {field: DataFrame[date x ticker]} for the given tickers."""
    tickers = list(tickers or (MAJORS + ALTS))
    out = {f: {} for f in fields}
    for t in tickers:
        try:
            df = rl.load_series(t, cache=cache)
        except Exception as e:  # network / unknown ticker
            print(f"skip {t}: {e}")
            continue
        if df is None or len(df) < 30:
            continue
        for f in fields:
            if f in df:
                out[f][t] = df[f]
    return {f: pd.DataFrame(out[f]).sort_index() for f in fields}


def clean_close(close, max_abs_ret=1.5, min_price=1e-6):
    """Mask obviously bad prints: zero/negative prices and isolated >150% daily moves
    (yfinance crypto files occasionally carry a single corrupt row)."""
    c = close.where(close > min_price)
    for t, d in VALID_FROM.items():
        if t in c:
            c.loc[:pd.Timestamp(d) - pd.Timedelta(days=1), t] = np.nan
    r = c.pct_change()
    bad = r.abs() > max_abs_ret
    c = c.mask(bad | bad.shift(-1, fill_value=False))
    return c


def dollar_volume(close, volume):
    """yfinance quotes crypto `Volume` in USD already (24h notional), so dollar volume
    is the volume column itself. `close` is accepted for signature symmetry only."""
    return volume


def pit_universe(close, volume, n_top=10, lookback=90, min_history=120,
                 min_dv=1e6, exclude=()):
    """Boolean membership mask [date x ticker], computed from PAST data only.

    A name is eligible on date t if it has >= `min_history` valid closes up to t, its
    trailing `lookback`-day median dollar volume is >= `min_dv`, and it ranks in the
    top `n_top` eligible names by that trailing median dollar volume.
    """
    dv = dollar_volume(close, volume)
    med = dv.rolling(lookback, min_periods=lookback // 2).median()
    hist = close.notna().cumsum()
    elig = (hist >= min_history) & (med >= min_dv) & close.notna()
    for t in exclude:
        if t in elig:
            elig[t] = False
    ranked = med.where(elig).rank(axis=1, ascending=False)
    return (ranked <= n_top) & elig


def btc_regime(btc_close, sma=200):
    """1 = bull (BTC above its SMA), 0 = bear. Uses only past data."""
    return (btc_close > btc_close.rolling(sma).mean()).astype(float)
