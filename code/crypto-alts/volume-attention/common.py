"""volume-attention: abnormal trading volume (attention / disagreement, Miller 1977;
Garfinkel et al. 2025) -> subsequent cross-sectional underperformance of liquid alts."""
import os, sys, warnings
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "shared"))
sys.path.insert(0, os.path.join(_HERE, "..", "..", "shared"))
import research_lib as rl  # noqa
import study as S  # noqa


def abn_volume(vol, k=60, base=180, gap=True):
    """log(mean volume over the last k days / mean volume over the `base` days before that).
    Past data only (both windows end at t)."""
    num = vol.rolling(k, min_periods=max(2, int(k * 0.8))).mean()
    den = vol.rolling(base, min_periods=base // 3).mean().shift(k if gap else 0)
    return np.log(num / den)
