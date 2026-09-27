"""residual-momentum -- deployable target weights.

    from strategy import residual_momentum_weights, _panel_inputs
    X = _panel_inputs()                       # research panel: close, member, sector, RSP
    W = residual_momentum_weights(X)          # DataFrame (dates x tickers [+ 'RSP']) of target weights

Signal (Blitz-Huij-Martens 2011): for each S&P 500 member, regress daily returns on the EW
member market M and the EW member return of its GICS sector S over the last `est` bars;
residual e = r - bM*M - bS*S (betas as of t). Score = sum of e over bars [t-L+1, t-skip]
divided by its own std * sqrt(n) -- a residual-return t-stat, i.e. 12-1 momentum stripped of
market and sector moves and scaled by idiosyncratic vol.

Book: winsorised z-score, demeaned within sector, linear dollar-neutral weights (gross 1), set
at the close of the last NYSE session of each month and held. Beta hedge: the book's ex-ante
252-day beta is offset with the EW member basket (hedge="EW") or RSP (hedge="RSP").
Vol management (Barroso & Santa-Clara 2015): the whole book is scaled by
target_vol / realised vol of its own unscaled daily returns over `vol_win` bars, capped at
`max_scale`, re-set at each month-end only.

Timing: weights at close t earn t -> t+1 (research_lib / xs_lib convention); fills at the
close the signal was computed on. Costs in research: 5 bp per side on sum |dw|.
Every parameter defaults to the spec in alphas/us-large-cap/residual-momentum/.
"""
import os, sys
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "shared"))
sys.path.insert(0, os.path.join(HERE, "..", "..", "shared"))
from trading_calendar import month_end_sessions


def _panel_inputs(start="2010-01-01"):
    """Research inputs: PIT S&P 500 panel, GICS sector per ticker, RSP close."""
    from panel import load_panel
    from research_lib import load_series
    sys.path.insert(0, os.path.join(HERE, "..", "quality-value-composite"))
    from common import sector_map
    P = load_panel(start=start)
    return {"close": P["close"], "member": P["member"], "sector": sector_map(P),
            "rsp": load_series("RSP")["Close"].reindex(P["close"].index)}


def _zs(sig, mask, sector, clip=3.0):
    s = sig.where(mask)
    z = s.sub(s.mean(axis=1), axis=0).div(s.std(axis=1, ddof=1), axis=0).clip(-clip, clip)
    out = z.copy()
    sec = sector.reindex(z.columns).fillna("UNK")
    for _, cols in sec.groupby(sec).groups.items():
        cols = list(cols)
        out[cols] = z[cols].sub(z[cols].mean(axis=1), axis=0)
    return out


def residual_momentum_weights(X, est=252, L=252, skip=21, kind="linear", hedge="EW",
                              beta_win=252, vol_manage=True, vol_win=126, target_vol=0.10,
                              max_scale=3.6, start=None):
    close, member, sector = X["close"], X["member"].fillna(False).astype(bool), X["sector"]
    sector = sector.reindex(close.columns).fillna("UNK")
    dates, tix = close.index, close.columns
    ret = close.pct_change(fill_method=None)
    rr = ret.fillna(0.0)
    r_m = ret.where(member)
    M = r_m.mean(axis=1).fillna(0.0)
    S = pd.DataFrame(0.0, index=dates, columns=tix)
    for s, cols in sector.groupby(sector).groups.items():
        cols = list(cols)
        S[cols] = np.repeat(r_m[cols].mean(axis=1).fillna(0.0).values[:, None], len(cols), axis=1)
    Mf = pd.DataFrame(np.repeat(M.values[:, None], len(tix), axis=1), index=dates, columns=tix)

    # rolling 2-factor OLS betas (est window)
    k = dict(window=est, min_periods=int(est * 0.8))
    m1, m2, my = Mf.rolling(**k).mean(), S.rolling(**k).mean(), rr.rolling(**k).mean()
    c11 = (Mf * Mf).rolling(**k).mean() - m1 * m1
    c22 = (S * S).rolling(**k).mean() - m2 * m2
    c12 = (Mf * S).rolling(**k).mean() - m1 * m2
    c1y = (Mf * rr).rolling(**k).mean() - m1 * my
    c2y = (S * rr).rolling(**k).mean() - m2 * my
    det = c11 * c22 - c12 * c12
    bM = (c22 * c1y - c12 * c2y) / det
    bS = (c11 * c2y - c12 * c1y) / det

    # residual t-stat over the formation window [t-L+1, t-skip]
    n = L - skip
    agg = lambda a: a.rolling(n).sum().shift(skip)
    res_sum = agg(rr) - bM * agg(Mf) - bS * agg(S)
    SS = agg(rr * rr) + bM**2 * agg(Mf * Mf) + bS**2 * agg(S * S) \
        - 2 * bM * agg(rr * Mf) - 2 * bS * agg(rr * S) + 2 * bM * bS * agg(Mf * S)
    var = ((SS - res_sum**2 / n) / (n - 1)).clip(lower=1e-10)
    sig = (res_sum / np.sqrt(var * n)).replace([np.inf, -np.inf], np.nan)

    mask = member & close.notna() & sig.notna()
    z = _zs(sig, mask, sector)
    zz = z.where(mask)
    if kind == "linear":
        zz = zz.sub(zz.mean(axis=1), axis=0)
        w = zz.div(zz.abs().sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)
    else:
        nn = zz.notna().sum(axis=1); kq = (nn * 0.2).round().clip(lower=1)
        hi = zz.rank(axis=1, ascending=False).le(kq, axis=0) & zz.notna()
        lo = zz.rank(axis=1, ascending=True).le(kq, axis=0) & zz.notna()
        w = hi.astype(float).div(hi.sum(axis=1).replace(0, np.nan), axis=0) * 0.5 \
            - lo.astype(float).div(lo.sum(axis=1).replace(0, np.nan), axis=0) * 0.5
        w = w.fillna(0.0)

    rebal = month_end_sessions(dates)
    w = w.reindex(rebal).reindex(dates).ffill().fillna(0.0)

    # beta hedge
    if hedge is not None:
        beta = ret.rolling(beta_win, min_periods=int(beta_win * 0.8)).cov(M).div(
            M.rolling(beta_win, min_periods=int(beta_win * 0.8)).var(), axis=0)
        bw = (w * beta.fillna(1.0)).sum(axis=1)
        bw = bw.reindex(rebal).reindex(dates).ffill().fillna(0.0)       # hedge re-set monthly
        if hedge == "EW":
            mw = member.astype(float); mw = mw.div(mw.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)
            mw = mw.reindex(rebal).reindex(dates).ffill().fillna(0.0)
            w = w - mw.mul(bw, axis=0)
        elif hedge == "RSP":
            rsp_ret = X["rsp"].pct_change(fill_method=None)
            b_rsp = M.rolling(beta_win, min_periods=200).cov(rsp_ret) / rsp_ret.rolling(beta_win, min_periods=200).var()
            w = w.copy(); w["RSP"] = -(bw * b_rsp.reindex(rebal).reindex(dates).ffill().fillna(1.0))

    # vol management on the book's own past returns
    if vol_manage:
        R = ret.copy()
        if "RSP" in w.columns:
            R["RSP"] = X["rsp"].pct_change(fill_method=None)
        g = (w.shift(1) * R.reindex(columns=w.columns).fillna(0.0)).sum(axis=1)
        rv = g.rolling(vol_win, min_periods=60).std() * np.sqrt(252)
        sc = (target_vol / rv).clip(upper=max_scale)
        sc = sc.reindex(rebal).reindex(dates).ffill().fillna(0.0)
        w = w.mul(sc, axis=0)
    if start is not None:
        w = w.loc[start:]
    return w
