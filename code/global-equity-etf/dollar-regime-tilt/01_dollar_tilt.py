"""Dollar-regime tilt: does the trend of the US dollar (DXY, lagged 1 day -- the ICE close is
after 16:00 ET) time non-US vs US equity?  Traded legs, each vol-targeted to 10 %:
  EEMvsSPY  : EEM - beta*SPY
  EFAvsSPY  : EFA - beta*SPY
  EXUSvsSPY : equal-weight 9 country ETFs - beta*SPY
  XS_FXBETA : cross-section tilted by each country's dollar beta (rolling 1y, SPY-controlled),
              weight_i = -trend * (beta_i - mean beta), dollar-neutral
Signal = -sign(dollar trend) averaged over lookbacks {21,63,126,252} (pre-registered ensemble),
also each lookback alone.  Control: the pair's OWN momentum (same lookbacks) -- if the dollar
adds nothing beyond the pair's own trend, it is just the country momentum that already failed.
Weekly (Friday) and monthly rebalance; 5 bp/side (SPY 1 bp)."""
import sys
sys.path.insert(0, "../shared")
import numpy as np, pandas as pd, warnings
warnings.filterwarnings("ignore")
import data as D, xs

START = "2001-01-01"
SPL = {"FULL": ("2001", "2026"), "IS": ("2001", "2012"), "OOS": ("2013", "2026")}
names = ["EWJ", "EWG", "EWU", "EWZ", "EWY", "EWA", "EWC", "FXI", "INDA"]
C = D.load_panel(names + ["EEM", "EFA", "SPY", "DX-Y.NYB"], "Close", start="1998-12-01")
dxy = C["DX-Y.NYB"].shift(1)                     # known at close t: yesterday's ICE close
ret = C.pct_change()
LB = [21, 63, 126, 252]

def beta(y, x, win=252):
    return y.rolling(win, min_periods=126).cov(x) / x.rolling(win, min_periods=126).var()

# synthetic pair returns: leg - beta*SPY, beta from trailing 252d (known at t)
def pair_ret(leg_ret):
    b = beta(leg_ret, ret["SPY"]).shift(1)
    return leg_ret - b * ret["SPY"], b

legs = {"EEMvsSPY": ret["EEM"], "EFAvsSPY": ret["EFA"],
        "EXUSvsSPY": ret[names].mean(axis=1, skipna=True)}

def trend_sig(px, lbs):
    return pd.concat([np.sign(np.log(px) - np.log(px.shift(l))) for l in lbs], axis=1).mean(axis=1)

rows = []
def book(pr, s, freq, name):
    """pr: daily pair return (already beta-hedged), s: signal in [-1,1] known at close t."""
    idx = pr.loc[START:].index
    reb = xs.rebalance_dates(idx, freq)
    vol = pr.rolling(126, min_periods=60).std() * np.sqrt(252)
    pos = (s * 0.10 / vol).reindex(reb)
    pos = pos.reindex(idx).ffill().fillna(0.0)
    pe = pos.shift(1).fillna(0.0)
    # turnover: leg + hedge, approximated as |dpos| * (1 + beta) at 5 bp leg / 1 bp SPY
    turn = pe.diff().abs().fillna(0.0)
    net = pe * pr.reindex(idx).fillna(0.0) - turn * (5.0 + 1.0) / 1e4
    r = xs.summarize(net, SPL, name=name)
    r["Turn/yr"] = turn.sum() / (len(turn) / 252); r["AvgAbsPos"] = pe.abs().mean()
    rows.append(r)
    return net

nets = {}
for leg, lr in legs.items():
    pr, b = pair_ret(lr)
    pair_px = (1 + pr.fillna(0.0)).cumprod()
    for freq in ["W", "M"]:
        s_dxy = -trend_sig(dxy, LB)
        nets[f"{leg}|DXY_ens|{freq}"] = book(pr, s_dxy, freq, f"{leg}|DXY_ens|{freq}")
        book(pr, trend_sig(pair_px, LB), freq, f"{leg}|OWN_ens|{freq}")
        book(pr, 0.5 * s_dxy + 0.5 * trend_sig(pair_px, LB), freq, f"{leg}|DXY+OWN|{freq}")
        if freq == "W":
            for l in LB:
                book(pr, -trend_sig(dxy, [l]), freq, f"{leg}|DXY_{l}|{freq}")
    # always-long pair (is there drift?)
    book(pr, pd.Series(1.0, index=pr.index), "M", f"{leg}|ALWAYS_LONG|M")

# XS: tilt by each country's dollar beta, controlling for SPY
rd = np.log(dxy).diff()
bfx = {}
for t in names:
    X = pd.concat([ret["SPY"], rd], axis=1).dropna()
    # 2-factor rolling OLS via covariances
    y = ret[t]
    c_ys = y.rolling(252, min_periods=126).cov(ret["SPY"]); c_yd = y.rolling(252, min_periods=126).cov(rd)
    v_s = ret["SPY"].rolling(252, min_periods=126).var(); v_d = rd.rolling(252, min_periods=126).var()
    c_sd = ret["SPY"].rolling(252, min_periods=126).cov(rd)
    det = v_s * v_d - c_sd ** 2
    bfx[t] = (c_yd * v_s - c_ys * c_sd) / det
bfx = pd.DataFrame(bfx)
for freq in ["W", "M"]:
    reb = xs.rebalance_dates(C.loc[START:].index, freq)
    tr = trend_sig(dxy, LB)
    raw = bfx.loc[reb].mul(tr.loc[reb], axis=0)        # dollar up & positive beta -> long
    w = xs.rank_weights(raw, raw.notna())
    w = xs.vol_target_book(w, ret[names], target=0.10)
    net, gross, turn, We = xs.run(w, C.loc[START:, names], cost_bps=5.0)
    r = xs.summarize(net, SPL, turn, We, name=f"XS_FXBETA|DXY_ens|{freq}")
    rows.append(r)
df = pd.DataFrame(rows)
pd.set_option("display.width", 250)
print(df[["FULL_SR", "IS_SR", "OOS_SR", "FULL_CAGR", "MaxDD", "Vol", "t_NW", "Turn/yr"]].round(2).to_string())
pd.DataFrame(nets).to_parquet("nets_01.parquet")
