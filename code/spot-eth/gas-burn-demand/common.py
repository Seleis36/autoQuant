"""Loaders and feature builders for gas-burn-demand (CoinMetrics community daily chain metrics).

Timing: a CoinMetrics daily row stamped D covers [D, D+1) UTC and is published a median 2.9 h
(90th percentile 10 h, tail of days) after D+1 00:00 (`fetch_fees.py`). Every chain series is
therefore lagged ONE FULL DAY: the signal at bar D (decided at D+1 00:00) uses the chain row of
D-1. `LAG` is that shift; exp02 shows the lag-0 and lag-2 sensitivity.
"""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO, "code", "spot-eth", "shared"))
import coinmetrics as cm  # noqa: E402
import evalkit as ek  # noqa: E402

LAG = 1
LONDON = "2021-08-05"     # EIP-1559: base fee burnt from here on
MERGE = "2022-09-15"      # proof-of-stake: issuance falls ~90%
DENCUN = "2024-03-13"     # blobs: rollups stop paying mainnet calldata fees


def chain():
    return cm.load("eth")


def z(x, n, minp=None):
    return (x - x.rolling(n, min_periods=minp or n).mean()) / x.rolling(n, min_periods=minp or n).std()


def features(index, lag=LAG):
    """Chain features aligned to the price index, lagged `lag` days (see module docstring)."""
    c = chain()
    fee = c["FeeTotNtv"].replace(0, np.nan)
    lf = np.log(fee)
    sply = c["SplyCur"]
    tx, adr = np.log(c["TxCnt"]), np.log(c["AdrActCnt"])
    F = {}
    # demand momentum: fees paid (in ETH, so not mechanically the price) now vs before
    for a, b in ((7, 30), (7, 90), (30, 90), (30, 180)):
        F[f"fee_mom_{a}_{b}"] = lf.rolling(a).mean() - lf.rolling(b).mean()
    # congestion spikes: how unusual is the fee level against its own recent distribution
    F["fee_z1_30"] = (lf - lf.rolling(30).mean()) / lf.rolling(30).std()
    F["fee_z7_90"] = z(lf.rolling(7).mean(), 90)
    F["fee_z7_365"] = z(lf.rolling(7).mean(), 365)
    F["fee_z30_365"] = z(lf.rolling(30).mean(), 365)
    # price of block space: fee per transaction
    lpt = lf - tx
    F["feepertx_mom_7_30"] = lpt.rolling(7).mean() - lpt.rolling(30).mean()
    F["feepertx_z7_90"] = z(lpt.rolling(7).mean(), 90)
    # fee yield on supply (a P/E): annualised fees / supply, level is regime-dependent -> rank
    fy = fee.rolling(30).sum() * 365 / 30 / sply
    F["feeyield30_lvl"] = np.log(fy)
    F["feeyield30_rank365"] = fy.rolling(365).rank(pct=True)
    # net issuance: annualised supply growth (burn - issuance sign flipped); low = scarce
    for k in (7, 30, 90):
        F[f"netiss_{k}"] = (sply / sply.shift(k) - 1) * 365 / k
    F["netiss_chg_30"] = F["netiss_30"] - F["netiss_30"].shift(30)
    # burn share: what fraction of issuance is burnt (post-London only)
    burn = (c["IssTotNtv"] - sply.diff()).clip(lower=0)
    bs = (burn.rolling(7).sum() / c["IssTotNtv"].rolling(7).sum()).where(c.index >= LONDON)
    F["burnshare_7"] = bs
    F["burnshare_z7_90"] = z(bs, 90)
    # activity counts (same demand mechanism measured without a price)
    for nm, s in (("tx", tx), ("adr", adr)):
        F[f"{nm}_mom_7_30"] = s.rolling(7).mean() - s.rolling(30).mean()
        F[f"{nm}_mom_30_90"] = s.rolling(30).mean() - s.rolling(90).mean()
        F[f"{nm}_z7_365"] = z(s.rolling(7).mean(), 365)
    out = pd.DataFrame(F).shift(lag)
    return out.reindex(index)
