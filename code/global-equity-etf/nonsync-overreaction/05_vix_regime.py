"""Regime check: is the Asian US-session-residual reversal large enough to pay costs when
VIX is high (overreaction should be largest in stress)? VIX known at close t."""
from lib import *
C, O = load()
vix = D.load_panel(["^VIX"], "Close", start="2003-01-01")["^VIX"]
names = ["EWJ", "EWY", "EWA", "INDA", "FXI", "EEM"]
r = C.pct_change()
u, z = residual_signal(C, O, names)
bcc = rolling_beta(r[names], r["SPY"], 250)
h1 = (r[names] - bcc.shift(1).mul(r["SPY"], axis=0)).shift(-1)
rows = []
for per, (a, b) in {"IS": ("2003", "2012"), "OOS": ("2013", "2026")}.items():
    for lo, hi in [(0, 15), (15, 20), (20, 30), (30, 200)]:
        m = (vix >= lo) & (vix < hi)
        zz = z.loc[a:b][m.loc[a:b]]; hh = h1.loc[a:b][m.loc[a:b]]
        st = zz.stack().dropna(); hs = hh.stack().reindex(st.index).dropna(); st = st.reindex(hs.index)
        tail = st.abs() > 1.5
        fade = (-np.sign(st[tail]) * hs[tail])
        rows.append({"per": per, "vix": f"{lo}-{hi}", "n_obs": len(st), "IC": st.corr(hs, method="spearman"),
                     "fade_bp": fade.mean() * 1e4, "fade_t": fade.mean() / fade.std() * np.sqrt(len(fade)), "n_tail": tail.sum()})
print(pd.DataFrame(rows).round(3).to_string())
