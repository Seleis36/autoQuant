"""Re-framings of carry/value: (a) beta-neutral legs (each name SPY-hedged, so the book cannot
be a disguised EM-beta bet), (b) ex-US cross-section (9 countries, SPY excluded), (c) dividend
growth = fundamental momentum (USD dividend-per-share growth over 1y / 2y), (d) quarterly."""
import sys
sys.path.insert(0, "../shared")
exec(open("01_carry_value.py").read().split("reb = xs.rebalance_dates")[0])   # reuse signals
import warnings; warnings.filterwarnings("ignore")

divlvl = dy * C                                       # smoothed USD dividends per share (per yr)
sig["dgrow1"] = np.log(divlvl) - np.log(divlvl.shift(252))
sig["dgrow2"] = np.log(divlvl) - np.log(divlvl.shift(504))
sig["dgrow1+mom"] = z(sig["dgrow1"]) + z(sig["mom"])

def beta_cc(win=252):
    cov = ret.rolling(win, min_periods=126).cov(ret["SPY"])
    return cov.div(ret["SPY"].rolling(win, min_periods=126).var(), axis=0)
B = beta_cc()

rows = []
for name in ["dy", "dy_rel", "ltr", "dgrow1", "dgrow2", "dgrow1+mom", "dy+mom"]:
    s = sig[name]
    for variant in ["base", "beta_neutral", "exUS", "quarterly"]:
        freq = "Q" if variant == "quarterly" else "M"
        reb = xs.rebalance_dates(C.loc[START:].index, freq)
        S = s.loc[reb]
        mask = S.notna() & C.loc[reb].notna()
        if variant == "exUS":
            mask["SPY"] = False
        mask = mask.where(mask.sum(axis=1) >= 6, False)
        w = xs.rank_weights(S, mask)
        if variant == "beta_neutral":
            # SPY leg set so that total book beta (on trailing 252d close-close betas) is zero
            w["SPY"] = -(w.drop(columns="SPY") * B.loc[reb].drop(columns="SPY")).sum(axis=1)
        w = xs.vol_target_book(w, ret, target=0.10)
        net, gross, turn, We = xs.run(w, C.loc[START:], cost_bps=5.0, spy_cost_bps=1.0)
        r = xs.summarize(net, SPL, turn, We, name=f"{name}|{variant}")
        bk = (We * B.shift(1).reindex(We.index)).sum(axis=1)
        r["book_beta"] = bk.loc[net.ne(0).idxmax():].mean()
        rows.append(r)
df = pd.DataFrame(rows)
print(df[["FULL_SR", "IS_SR", "OOS_SR", "FULL_CAGR", "MaxDD", "t_NW", "Turn/yr", "book_beta"]].round(2).to_string())
