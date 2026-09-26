"""Check the curve-residual momentum found in 02: autocorrelation, outlier dependence, VIXM staleness,
futures-rebuilt check, and net-of-cost momentum version."""
import sys, os
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "shared"))
import numpy as np, pandas as pd
import vc_data as vc

P = vc.panel()
V = vc.load_close(["VIXM", "VIXY"], "Volume").reindex(P.index)
R = P[["VIXY", "VIXM", "SPY"]].pct_change()
bm = (R["VIXY"].rolling(63).cov(R["VIXM"]) / R["VIXM"].rolling(63).var())
res = R["VIXY"] - bm.shift(1) * R["VIXM"]
for k, (a, b) in vc.SPLITS.items():
    x = res.loc[a:b].dropna()
    print(k, "AC1 %.3f AC2 %.3f  spearman AC1 %.3f" % (x.autocorr(1), x.autocorr(2), x.corr(x.shift(1), method="spearman")))
print("VIXY AC1 %.3f  VIXM AC1 %.3f" % (R["VIXY"].autocorr(1), R["VIXM"].autocorr(1)))
print("cross: corr(VIXY_t, VIXM_t+1) %.3f  corr(VIXM_t, VIXY_t+1) %.3f" % (
    R["VIXY"].corr(R["VIXM"].shift(-1)), R["VIXM"].corr(R["VIXY"].shift(-1))))
print("VIXM zero-volume days:", int((V["VIXM"] == 0).sum()), " median VIXM volume", V["VIXM"].median(), " VIXY", V["VIXY"].median())
print("VIXM zero-return days frac: %.3f  VIXY %.3f" % ((R["VIXM"] == 0).mean(), (R["VIXY"] == 0).mean()))
# lead-lag regressions: r_VIXM,t+1 on r_VIXY,t and r_VIXM,t
import statsmodels.api as sm
for k, (a, b) in {"IS": vc.IS, "OOS": vc.OOS}.items():
    d = pd.DataFrame({"m1": R["VIXM"].shift(-1), "y1": R["VIXY"].shift(-1), "y": R["VIXY"], "m": R["VIXM"]}).loc[a:b].dropna()
    for tgt in ("m1", "y1"):
        m = sm.OLS(d[tgt], sm.add_constant(d[["y", "m"]])).fit(cov_type="HC1")
        print(k, tgt, "coef", m.params.round(3).to_dict(), "t", m.tvalues.round(2).to_dict())

# gross vs net of the curve-residual fade from 02 (L=1, 3): is the -1.8 cost-driven?
zr = res / res.rolling(63).std().shift(1)
for L in (1, 3, 5):
    zz = zr.rolling(L).sum() / np.sqrt(L)
    s = -(zz / 2).clip(-1, 1)
    W = pd.DataFrame({"VIXY": s, "VIXM": -s * bm}).fillna(0)
    W = W.div(W.abs().sum(axis=1).replace(0, np.nan).clip(lower=1), axis=0).fillna(0)
    for c in (0, 2, 7):
        net, st = vc.bt_xs(W, P[["VIXY", "VIXM"]], c)
        print(f"curve fade L={L} cost {c}bp: Sh {vc.sh(net):.2f} IS {vc.sh(net.loc[:'2018']):.2f} OOS {vc.sh(net.loc['2019':]):.2f} vol {net.std()*np.sqrt(252):.3f} TO {st['Turnover_ann']:.0f}")
