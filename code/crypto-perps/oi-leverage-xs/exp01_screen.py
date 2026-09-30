"""exp01 — does leverage build-up (open interest) predict cross-sectional spot returns?

Same pre-registered universe, split and cost as retail-crowding-xs (common.py there):
PIT top-20 of the 64 funding_panel perps, IS 2022-03..2023-12, OOS 2024-01.., 10 bp.
OI = Binance USD-M `sum_open_interest` (coins) / `sum_open_interest_value` (USDT), last
5-min stamp before 23:00 UTC of D.

Pre-declared features (contrarian = short high):
  oig7, oig30     7 / 30-day log change of OI in coins (positions opened, price-free)
  oig7_res        oig7 residual of a daily XS regression on the 7-day return
  oi_mcap         log(OI value / market cap), mcap = CMC weekly circulating supply
                  (known +1 day) x close; raw level and own-90d-demeaned (oi_mcap_dm)
  oi_vol          log(OI value / 30d mean USD volume), own-90d-demeaned
Hold 1 day or 7-day tranches, q30, beta-neutral.
"""
import os
import sys
import importlib.util
import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("rcx", os.path.join(_HERE, "..", "retail-crowding-xs", "common.py"))
rcx = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rcx)
sys.path.insert(0, os.path.join(rcx.ROOT, "code", "crypto-alts", "shared"))
import cmc  # noqa: E402

close, vol, met, mask = rcx.load()
beta = rcx.btc_beta(close)
oi = met["sum_open_interest"].where(met["sum_open_interest"] > 0)
oiv = met["sum_open_interest_value"].where(met["sum_open_interest_value"] > 0)
ret7 = close.pct_change(7, fill_method=None)

idmap = cmc.yahoo_map(close)
supply = cmc.wide("circulatingSupply", idmap, index=close.index)
mcap = (supply * close).where(supply > 0)


def xs_resid(y, x):
    ym, xm = y.where(mask), x.where(mask)
    yd, xd = ym.sub(ym.mean(axis=1), axis=0), xm.sub(xm.mean(axis=1), axis=0)
    b = (yd * xd).sum(axis=1) / (xd ** 2).sum(axis=1)
    return yd - xd.mul(b, axis=0)


oig7 = np.log(oi).diff(7)
lv_m = np.log(oiv / mcap)
lv_v = np.log(oiv / vol.rolling(30, min_periods=20).mean())
feats = {
    "oig7": oig7,
    "oig30": np.log(oi).diff(30),
    "oig7_res": xs_resid(oig7, ret7),
    "oi_mcap": lv_m,
    "oi_mcap_dm": lv_m - lv_m.rolling(90, min_periods=60).mean(),
    "oi_vol_dm": lv_v - lv_v.rolling(90, min_periods=60).mean(),
}
rows, ics = [], []
for fn, f in feats.items():
    ic = rcx.ic_table(-f, close, mask)
    for per, (a, b) in {"IS": rcx.IS, "OOS": rcx.OOS}.items():
        seg = ic.loc[a:b]
        ics.append({"feat": fn, "per": per, **{f"IC{h}": seg[h].mean() for h in seg},
                    **{f"t{h}": seg[h].mean() / seg[h].std() * np.sqrt(seg[h].notna().sum() / h) for h in seg}})
    for sign in (-1, 1):
        for h in (1, 7):
            w = rcx.tranche(rcx.beta_neutral(rcx.quantile_ls(sign * f, mask), beta), h)
            _, row = rcx.evaluate(w, close, f"{'-' if sign < 0 else '+'}{fn}_h{h}")
            rows.append(row)
pd.set_option("display.width", 200)
print("mcap coverage in universe:", round(float(mcap.where(mask).notna().sum().sum() / mask.sum().sum()), 3))
print("contrarian ICs (signal = -feature)")
print(pd.DataFrame(ics).round(3).to_string(index=False))
res = pd.DataFrame(rows)
print(res.round(2).to_string(index=False))
res.to_csv("exp01_results.csv", index=False)
