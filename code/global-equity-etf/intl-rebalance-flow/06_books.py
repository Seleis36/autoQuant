"""intl-rebalance-flow books. Pre-registered spec (fixed before this script ran):
  position in the hedged spread over the LAST session of the month (set at close L-1)
  = clip(Z, -2, 2) / 2 * k, Z = MTD (SPY - INTL) through L-1 / (spread vol x sqrt(n)),
  k scales the active-day spread position to 1.0 per unit of |clipped Z|/2 (no vol target:
  the book is one day a month). Costs 5 bp/side country ETFs, 1 bp SPY.
Variants reported for completeness: sign(Z); window L-1..L; quarter-ends only; day L+1 give-back."""
import numpy as np, pandas as pd
from lib import load, spreads, month_end_positions, SPL, spread_book_weights, run_book, stats

C, R = load()
S = spreads(R)
idx = S.index; pe = month_end_positions(idx)
rel_us = S["spy"] - S["intl"]
vol = S["hedged"].rolling(252, min_periods=126).std().shift(1)
beta = S["beta"].shift(-1)      # S.beta is lagged; un-lag so beta[t] uses data through t

def pos_series(days=(0,), sizing="clip", qend_only=False, sign_flip=1.0, scale=4.0):
    """days: relative offsets (0 = L, 1 = L+1) whose returns the position earns."""
    pos = pd.Series(0.0, index=idx)
    for a, b in zip(pe[:-1], pe[1:]):
        if qend_only and idx[b].month not in (3, 6, 9, 12):
            continue
        end = b - 1                                  # signal through close L-1
        if end - a < 4: continue
        z = rel_us.iloc[a + 1:end + 1].sum() / (vol.iloc[end] * np.sqrt(end - a))
        if not np.isfinite(z): continue
        x = np.sign(z) if sizing == "sign" else np.clip(z, -2, 2) / 2
        for d in days:
            p = b + d - 1                            # weight set at close before earned day
            if 0 <= p < len(idx): pos.iloc[p] = sign_flip * x * scale
    return pos

rows = {}
cfg = {"SPEC L, clip": dict(), "L, sign": dict(sizing="sign"), "L-1..L, clip": dict(days=(-1, 0)),
       "L, qend only": dict(qend_only=True), "L+1 give-back (short)": dict(days=(1,), sign_flip=-1.0),
       "L..L+1 (L long, L+1 short)": None}
for name, kw in cfg.items():
    if kw is None:
        pos = pos_series((0,)) + pos_series((1,), sign_flip=-1.0)
    else:
        pos = pos_series(**kw)
    w = spread_book_weights(pos, C, beta)
    net, gross, turn, We = run_book(w, C)
    st = stats(net, turn=turn, We=We)
    st["FULL_gross"] = gross.loc["1999-06":].mean() / gross.loc["1999-06":].std() * np.sqrt(252)
    for c_ in (2.0, 10.0):
        n2, *_ = run_book(w, C, cost=c_)
        st[f"FULL@{c_:.0f}bp"] = n2.loc["1999-06":].mean() / n2.loc["1999-06":].std() * np.sqrt(252)
    rows[name] = st
pd.set_option("display.width", 220)
print(pd.DataFrame(rows).T.round(3).to_string())
net, *_ = run_book(spread_book_weights(pos_series(), C, beta), C)
yr = net.groupby(net.index.year).sum()
print("\nSPEC calendar-year net returns (%):\n", (yr * 100).round(2).to_string())
net.to_frame("spec").to_parquet("nets_06.parquet")
