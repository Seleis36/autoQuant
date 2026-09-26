"""Country-pair mean reversion. For a pair (A, B): hedge ratio h = rolling OLS of log A on log B
(or of returns, beta), spread = log A - h log B, z = (spread - mean_L) / std_L, all trailing.
Books: (1) linear  pos = -clip(z, 2)   (2) band: enter |z| > 2, exit |z| < 0.5 (or 20d stop).
Pairs: ECON (pre-specified economic twins) and ALL (36 country pairs).
Each pair's spread position is vol-scaled to equal risk; book to 10 % vol; 5 bp/side per leg.
Sample 2003+ (stale-print years excluded, see nonsync-overreaction), IS <= 2012, OOS 2013+."""
import sys, itertools
sys.path.insert(0, "../shared")
import numpy as np, pandas as pd, warnings
warnings.filterwarnings("ignore")
import data as D, xs

NAMES = ["EWJ", "EWG", "EWU", "EWZ", "EWY", "EWA", "EWC", "FXI", "INDA"]
ECON = [("EWA", "EWC"), ("EWG", "EWU"), ("EWJ", "EWY"), ("EWY", "FXI"), ("EWZ", "EWA"),
        ("EWZ", "EWC"), ("EWA", "FXI"), ("EFA", "EWU"), ("EFA", "EWG"), ("EEM", "FXI"), ("EEM", "EWY"), ("EEM", "EWZ")]
ALL = list(itertools.combinations(NAMES, 2))
C = D.load_panel(NAMES + ["EFA", "EEM", "SPY"], "Close", start="2001-01-01")
R = C.pct_change()
lp = np.log(C)
SPL = {"FULL": ("2003", "2026"), "IS": ("2003", "2012"), "OOS": ("2013", "2026")}

def pair_positions(a, b, L, mode, hedge_win=252):
    # return-beta hedge ratio (robust to level drift), known at t
    h = R[a].rolling(hedge_win, min_periods=126).cov(R[b]) / R[b].rolling(hedge_win, min_periods=126).var()
    sp_ret = R[a] - h.shift(1) * R[b]
    spread = np.log((1 + sp_ret.fillna(0.0)).cumprod()).where(sp_ret.notna())
    z = (spread - spread.rolling(L).mean()) / spread.rolling(L).std()
    if mode == "linear":
        s = -z.clip(-2, 2) / 2
    else:
        s = pd.Series(0.0, index=z.index); cur = 0.0; age = 0
        for i, v in enumerate(z.values):
            if np.isnan(v):
                cur = 0.0
            elif cur == 0.0 and abs(v) > 2.0:
                cur = -np.sign(v); age = 0
            elif cur != 0.0 and (abs(v) < 0.5 or age > 20 or np.sign(v) == cur):
                cur = 0.0 if (abs(v) < 0.5 or age > 20) else cur
            age += 1
            s.iloc[i] = cur
    vol = sp_ret.rolling(126, min_periods=60).std() * np.sqrt(252)
    pos = s / vol
    wa = pos; wb = -pos * h
    return wa, wb

rows = []
nets = {}
for pairs, ptag in [(ECON, "ECON"), (ALL, "ALL")]:
    for L in [20, 60, 120]:
        for mode in ["linear", "band"]:
            W = pd.DataFrame(0.0, index=C.index, columns=C.columns)
            for a, b in pairs:
                wa, wb = pair_positions(a, b, L, mode)
                W[a] = W[a] + wa.fillna(0.0); W[b] = W[b] + wb.fillna(0.0)
            W = W / len(pairs)
            for freq in (["D", "W"] if mode == "linear" else ["D"]):
                idx = W.loc["2003":].index
                reb = idx if freq == "D" else xs.rebalance_dates(idx, "W")
                Wr = W.loc[reb]
                # book vol target: scale by trailing realised vol of the unscaled book (lagged), cheap & causal
                raw = (Wr.reindex(C.index).ffill().shift(1) * R).sum(axis=1)
                bv = raw.rolling(126, min_periods=60).std().reindex(reb) * np.sqrt(252)
                Wr = Wr.mul((0.10 / bv).clip(upper=50), axis=0).fillna(0.0)
                net, gross, turn, We = xs.run(Wr, C.loc["2003":], cost_bps=5.0, name="x")
                r = xs.summarize(net, SPL, turn, We, name=f"{ptag}|L{L}|{mode}|{freq}")
                r["FULL_SR_gross"] = xs.summarize(gross, SPL)["FULL_SR"]
                r["OOS_SR_gross"] = xs.summarize(gross, SPL)["OOS_SR"]
                rows.append(r); nets[r.name] = net
df = pd.DataFrame(rows)
pd.set_option("display.width", 250)
print(df[["FULL_SR", "FULL_SR_gross", "IS_SR", "OOS_SR", "OOS_SR_gross", "MaxDD", "Vol", "Turn/yr", "Gross"]].round(2).to_string())
pd.DataFrame(nets).to_parquet("nets_01.parquet")
