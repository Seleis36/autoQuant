"""Dollar re-framings: (a) long-cycle reversal of the dollar (5y and 3y change, the ~8-year
dollar cycle), (b) 1y z-score mean reversion, (c) risk-off regime = dollar rising AND VIX above
its 1y median (Bruno-Shin: dollar as global risk-appetite barometer) -> short ex-US vs SPY."""
import sys
sys.path.insert(0, "../shared")
exec(open("01_dollar_tilt.py").read().split("nets = {}")[0])
vix = D.load_panel(["^VIX"], "Close", start="1998-12-01")["^VIX"]
ld = np.log(dxy)
sigs = {
    "DXY_rev5y": -np.sign(ld - ld.shift(1260)) * -1,      # dollar up over 5y -> expect dollar down -> long ex-US
    "DXY_rev3y": -np.sign(ld - ld.shift(756)) * -1,
    "DXY_z1y_mr": ((ld - ld.rolling(252).mean()) / ld.rolling(252).std()).clip(-2, 2) / 2,   # rich dollar -> long ex-US
    "RISKOFF": -((np.sign(ld - ld.shift(63)) > 0) & (vix > vix.rolling(252).median())).astype(float)
               + ((np.sign(ld - ld.shift(63)) < 0) & (vix < vix.rolling(252).median())).astype(float),
}
for leg in ["EEMvsSPY", "EXUSvsSPY"]:
    pr, b = pair_ret(legs[leg])
    for k, s in sigs.items():
        book(pr, s, "M", f"{leg}|{k}|M")
    # correlation of DXY ensemble signal with pair own trend signal
    pair_px = (1 + pr.fillna(0.0)).cumprod()
    print(leg, "corr(DXY_ens signal, OWN_ens signal) =", round((-trend_sig(dxy, LB)).corr(trend_sig(pair_px, LB)), 2))
df = pd.DataFrame(rows)
print(df[["FULL_SR", "IS_SR", "OOS_SR", "FULL_CAGR", "MaxDD", "t_NW", "Turn/yr"]].round(2).to_string())
