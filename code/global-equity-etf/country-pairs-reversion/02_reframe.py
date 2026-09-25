"""(a) is the daily gross edge just the 1-day (non-synchronous) reversal? -> lag the weights 1-5 days.
(b) slower bands: L = 250, entry |z|>2, exit at z crossing 0, 60d stop.
(c) cointegration-selected pairs: each month, among the 36 pairs keep those whose trailing-504d
    Engle-Granger ADF p-value < 0.05 on log prices; trade their 60d z with a band."""
import sys
sys.path.insert(0, "../shared")
exec(open("01_pairs.py").read().split("rows = []")[0])
from statsmodels.tsa.stattools import coint

def book_from_W(W, freq="D", lag=0, name=""):
    idx = W.loc["2003":].index
    reb = idx if freq == "D" else xs.rebalance_dates(idx, "W")
    Wr = W.shift(lag).loc[reb]
    raw = (Wr.reindex(C.index).ffill().shift(1) * R).sum(axis=1)
    bv = raw.rolling(126, min_periods=60).std().reindex(reb) * np.sqrt(252)
    Wr = Wr.mul((0.10 / bv).clip(upper=50), axis=0).fillna(0.0)
    net, gross, turn, We = xs.run(Wr, C.loc["2003":], cost_bps=5.0, name=name)
    r = xs.summarize(net, SPL, turn, We, name=name)
    g = xs.summarize(gross, SPL)
    r["FULL_SR_gross"], r["OOS_SR_gross"] = g["FULL_SR"], g["OOS_SR"]
    return r

rows = []
W = pd.DataFrame(0.0, index=C.index, columns=C.columns)
for a, b in ECON:
    wa, wb = pair_positions(a, b, 20, "linear")
    W[a] += wa.fillna(0.0); W[b] += wb.fillna(0.0)
W /= len(ECON)
for lag in [0, 1, 2, 5]:
    rows.append(book_from_W(W, "D", lag, f"ECON|L20|linear|lag{lag}"))

# (b) slow band
def slow_band(a, b, L=250, stop=60):
    h = R[a].rolling(252, min_periods=126).cov(R[b]) / R[b].rolling(252, min_periods=126).var()
    sp_ret = R[a] - h.shift(1) * R[b]
    spread = np.log((1 + sp_ret.fillna(0.0)).cumprod()).where(sp_ret.notna())
    z = (spread - spread.rolling(L).mean()) / spread.rolling(L).std()
    s = np.zeros(len(z)); cur = 0.0; age = 0
    for i, v in enumerate(z.values):
        if np.isnan(v): cur = 0.0
        elif cur == 0.0 and abs(v) > 2.0: cur = -np.sign(v); age = 0
        elif cur != 0.0 and (np.sign(v) == cur or age > stop): cur = 0.0
        age += 1; s[i] = cur
    vol = sp_ret.rolling(126, min_periods=60).std() * np.sqrt(252)
    pos = pd.Series(s, index=z.index) / vol
    return pos, -pos * h
for pairs, tag in [(ECON, "ECON"), (ALL, "ALL")]:
    W2 = pd.DataFrame(0.0, index=C.index, columns=C.columns)
    for a, b in pairs:
        wa, wb = slow_band(a, b)
        W2[a] += wa.fillna(0.0); W2[b] += wb.fillna(0.0)
    rows.append(book_from_W(W2 / len(pairs), "D", 0, f"{tag}|L250|band-to-zero"))

# (c) cointegration-selected pairs, re-selected monthly on trailing 504d log prices
months = xs.rebalance_dates(C.loc["2004":].index, "M")
sel = {}
for d in months:
    hist = lp.loc[:d].iloc[-504:]
    keep = []
    for a, b in ALL:
        x = hist[[a, b]].dropna()
        if len(x) < 400: continue
        try:
            p = coint(x[a], x[b])[1]
        except Exception:
            continue
        if p < 0.05: keep.append((a, b))
    sel[d] = keep
nsel = pd.Series({d: len(v) for d, v in sel.items()})
print("cointegrated pairs per month: mean %.1f, min %d, max %d" % (nsel.mean(), nsel.min(), nsel.max()))
active = pd.DataFrame(0.0, index=C.index, columns=pd.MultiIndex.from_tuples(ALL))
for d, keep in sel.items():
    for pr in keep: active.loc[d, pr] = 1.0
active = active.replace(0.0, np.nan)
for d in months: active.loc[d] = active.loc[d].fillna(0.0)
active = active.ffill().shift(1).fillna(0.0)          # selection at month-end t applies from t+1
W3 = pd.DataFrame(0.0, index=C.index, columns=C.columns)
for a, b in ALL:
    wa, wb = pair_positions(a, b, 60, "band")
    m = active[(a, b)]
    W3[a] += (wa * m).fillna(0.0); W3[b] += (wb * m).fillna(0.0)
rows.append(book_from_W(W3 / max(nsel.mean(), 1), "D", 0, "COINT|L60|band"))
df = pd.DataFrame(rows)
print(df[["FULL_SR", "FULL_SR_gross", "IS_SR", "OOS_SR", "OOS_SR_gross", "MaxDD", "Turn/yr"]].round(2).to_string())
