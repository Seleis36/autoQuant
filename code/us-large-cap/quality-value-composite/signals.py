"""Point-in-time fundamental signals for the S&P 500 panel (quality-value-composite).

    from signals import build
    S, P = build()      # S: dict name -> wide daily signal (higher = buy), P: price panel

Every fundamental enters at the close of the first trading day after its EDGAR filing date
(xbrl.Fundamentals.daily). Market cap = split-only-adjusted close x split-adjusted weighted
diluted shares of the latest filed quarter -- the cache's dividend adjustment is undone first
so that high-yield names are not assigned a smaller historical market cap.
"""
import os, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "shared"))
sys.path.insert(0, os.path.join(HERE, "..", "..", "shared"))
from panel import load_panel
from xbrl import Fundamentals, REVENUE, COGS, NETINC, CFO, EQUITY, DIL_SHARES


def _lag_year(long, days=365, tol=20):
    """Attach the value of the same ticker ~1 year earlier (by period end) as `val_ly`, choosing
    only among rows already filed when this row was (point-in-time; see xbrl._nearest_pit)."""
    from xbrl import _nearest_pit
    a = long.copy().reset_index(drop=True)
    a["key"] = a["end"] - pd.Timedelta(days=days)
    a["rid"] = np.arange(len(a))
    b = long[["ticker", "end", "val", "avail"]].rename(columns={"end": "e_ly", "val": "val_ly", "avail": "avail_ly"})
    return _nearest_pit(a, b, "key", "e_ly", ["ticker"], tol, "avail", "avail_ly")


def build(start="2010-01-01"):
    P = load_panel(start=start)
    S, aux = build_signals(P["close"])
    return S, P, aux


def build_signals(close, F=None):
    """All signals from a wide close panel (dividend+split adjusted, as in the cache) and the
    point-in-time fundamentals store. Returns (signals dict, aux dict with mcap/at/ni/rev)."""
    dates = close.index; tick = list(close.columns)
    F = F or Fundamentals()
    D = lambda long, **k: F.daily(long, dates, tick, **k)

    rev_l = F.ttm(REVENUE); cogs_l = F.ttm(COGS); gp_l = F.ttm(["GrossProfit"])
    ni_l = F.ttm(NETINC); cfo_l = F.ttm(CFO); capex_l = F.ttm(["PaymentsToAcquirePropertyPlantAndEquipment"])
    div_l = F.ttm(["PaymentsOfDividends", "PaymentsOfDividendsCommonStock"])
    bb_l = F.ttm(["PaymentsForRepurchaseOfCommonStock"])
    at_l = F.instant(["Assets"]); lt_l = F.instant(["Liabilities"]); eq_l = F.instant(EQUITY)
    sh_l = F.latest_avg(DIL_SHARES, "shares")

    # split-adjust share counts to today's basis at their filing date
    sp = F.actions[F.actions.split > 0]
    def sf(row_t, row_d):
        g = sp[sp.ticker == row_t]
        return float(np.prod(g.split[g.date > row_d])) if len(g) else 1.0
    sh_l = sh_l.copy()
    sh_l["val"] = sh_l["val"] * [sf(t, d) for t, d in zip(sh_l.ticker, sh_l.avail)]

    rev, cogs, gp = D(rev_l), D(cogs_l), D(gp_l)
    ni, cfo, capex = D(ni_l), D(cfo_l), D(capex_l)
    divs, bb = D(div_l), D(bb_l)
    at, lt, eq = D(at_l), D(lt_l), D(eq_l)
    sh = D(sh_l)
    gp = gp.fillna(rev - cogs)

    divF = F.div_factor(close)
    mcap = close / divF * sh
    # guard: implausible caps (bad share tags) -> NaN
    mcap = mcap.where((mcap > 5e8) & (mcap < 2e13))

    at_ly = D(_lag_year(at_l).assign(val=lambda x: x["val_ly"]).dropna(subset=["val"]))
    sh_ly = _lag_year(sh_l).dropna(subset=["val_ly"])
    sh_ly = D(sh_ly.assign(val=sh_ly["val_ly"]))
    ni_ly = _lag_year(ni_l).dropna(subset=["val_ly"])
    ni_ly = D(ni_ly.assign(val=ni_ly["val_ly"]))

    pos = lambda x: x.where(x > 0)
    S = {
        # quality / profitability
        "gpa": gp / at,
        "roa": ni / at,
        "roe": ni / pos(eq),
        "cfoa": cfo / at,
        "accruals": -(ni - cfo) / at,
        "lev": -(lt / at),
        "agrowth": -(at / at_ly - 1.0),
        "issuance": -(sh / sh_ly - 1.0),
        "d_roa": (ni - ni_ly) / at,
        # value
        "ep": ni / mcap,
        "cfp": cfo / mcap,
        "bm": eq / mcap,
        "sp": rev / mcap,
        "fcfp": (cfo - capex.fillna(0)) / mcap,
        "shy": (divs.fillna(0) + bb.fillna(0)) / mcap,
        "size": -np.log(mcap),
    }
    # price-based controls
    lc = np.log(close)
    S["mom12_1"] = lc.shift(21) - lc.shift(252)
    r = close.pct_change()
    S["lowvol"] = -r.rolling(126, min_periods=100).std()
    for k in S:
        S[k] = S[k].replace([np.inf, -np.inf], np.nan)
    aux = {"mcap": mcap, "at": at, "ni": ni, "rev": rev}
    return S, aux


if __name__ == "__main__":
    import time
    t0 = time.time()
    S, P, aux = build()
    m = P["member"]
    print("built in", round(time.time() - t0), "s")
    for k, v in S.items():
        cov = (v.notna() & m).sum(axis=1) / m.sum(axis=1)
        print(f"{k:10s} coverage 2011: {cov.loc['2011'].mean():.2f}  2015: {cov.loc['2015'].mean():.2f}  2025: {cov.loc['2025'].mean():.2f}")
    mc = aux["mcap"]
    print(mc.iloc[-1][["AAPL", "MSFT", "NVDA", "JPM", "GOOGL", "BRK-B", "XOM"]] / 1e9)
    print(mc.loc["2015-06-30"][["AAPL", "MSFT", "NVDA", "JPM", "GOOGL", "BRK-B", "XOM"]] / 1e9)
