"""Costed event books (windows fixed from the literature, not from 01's table):
  F10_EW9   long EW 9-country basket on FOMC days {-1, 0} (hold close(-2) -> close(0))
  F10_EEM   same on EEM
  F0_EEMSPY long EEM / short beta*SPY on FOMC day 0 only (global-beta premium, market-hedged)
  F10_HML   long top-3 / short bottom-3 beta countries on {-1, 0}
  CAL_EW9   FOMC{-1,0} + turn-of-month [-1,+3] + pre-holiday on EW9 (the sector desk's calendar)
Benchmarks: buy-and-hold EW9, EEM. 5 bp/side ETFs, 1 bp SPY. Sharpe on all days (flat = 0)."""
exec(open("01_event_study.py").read().split("for evname, events")[0])
import xs
SPL = {"FULL": ("2001", "2026"), "IS": ("2001", "2012"), "OOS": ("2013", "2026")}
off = offsets(fomc)
pos_idx = pd.Series(np.arange(len(idx)), index=idx)
# turn of month: last trading day of month = -1, first three of next = +1..+3
ym = pd.Series(idx.year * 12 + idx.month, index=idx)
last = ym != ym.shift(-1)
tom = last | (ym != ym.shift(1)) | (ym != ym.shift(2)) | (ym != ym.shift(3))
# pre-holiday: next trading day is > 1 business day away (weekday holiday gap)
nxt = pd.Series(idx, index=idx).shift(-1)
bd_gap = pd.Series([np.busday_count(a.date(), b.date()) if pd.notna(b) else 1 for a, b in zip(idx, nxt)], index=idx)
prehol = bd_gap > 1
def in_window(mask):
    """mask[t] = we want to EARN day t's return -> hold weight at close t-1 (so shift -1 for the weight)."""
    return mask.shift(-1).fillna(False).astype(bool)

earn_F10 = off.isin([-1, 0]); earn_F0 = off.eq(0)
earn_CAL = earn_F10 | tom | prehol.shift(1).fillna(False)    # pre-holiday day's return = day before holiday
rows = []; nets = {}
def run_w(W, name):
    net, gross, turn, We = xs.run(W.loc["2001":], C.loc["2001":, W.columns], cost_bps=5.0, spy_cost_bps=1.0, name=name)
    r = xs.summarize(net, SPL, turn, We, name=name); r["TimeInMkt"] = (We.abs().sum(axis=1) > 0).mean()
    r["FULL_SR_gross"] = xs.summarize(gross, SPL)["FULL_SR"]
    rows.append(r); nets[name] = net
ew = pd.DataFrame(0.0, index=idx, columns=NAMES + ["EEM", "SPY"])
avail = C[NAMES].notna()
ewt = avail.div(avail.sum(axis=1), axis=0)
for tag, earn in [("F10", earn_F10), ("F0", earn_F0), ("CAL", earn_CAL)]:
    w = in_window(earn)
    W = ew.copy(); W[NAMES] = ewt.mul(w, axis=0); run_w(W, f"{tag}_EW9")
    W = ew.copy(); W["EEM"] = w.astype(float); run_w(W, f"{tag}_EEM")
    b = (R["EEM"].rolling(252, min_periods=126).cov(R["SPY"]) / R["SPY"].rolling(252, min_periods=126).var())
    W = ew.copy(); W["EEM"] = w.astype(float); W["SPY"] = -b * w; run_w(W, f"{tag}_EEM-bSPY")
    W = ew.copy()
    W[NAMES] = (hi.astype(float).div(hi.sum(axis=1), axis=0) - lo.astype(float).div(lo.sum(axis=1), axis=0)).shift(-1).mul(w, axis=0).fillna(0.0) * 0.5 * 2
    run_w(W, f"{tag}_HMLbeta")
W = ew.copy(); W[NAMES] = ewt; run_w(W, "BH_EW9")
W = ew.copy(); W["EEM"] = 1.0; run_w(W, "BH_EEM")
W = ew.copy(); W["SPY"] = 1.0; run_w(W, "BH_SPY")
df = pd.DataFrame(rows)
pd.set_option("display.width", 250)
print(df[["FULL_SR", "FULL_SR_gross", "IS_SR", "OOS_SR", "FULL_CAGR", "OOS_CAGR", "MaxDD", "Vol", "t_NW", "Turn/yr", "TimeInMkt"]].round(3).to_string())
pd.DataFrame(nets).to_parquet("nets_02.parquet")
# correlation of the best candidates with intl-relative-trend
irt = pd.read_parquet("../intl-relative-trend/nets_03.parquet")["SPEC blend50 (5bp)"]
for k in ["F10_EW9", "F10_EEM", "F0_EEM-bSPY", "CAL_EW9"]:
    a = pd.concat([nets[k], irt], axis=1).dropna().loc["2002":]
    print(k, "corr with intl-relative-trend:", round(a.corr().iloc[0, 1], 3))
