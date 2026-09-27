"""Point-in-time fundamental panels from data/SP500_xbrl_facts.parquet (see fetch_xbrl.py).

    from xbrl import Fundamentals
    F = Fundamentals()                                  # loads facts + actions once
    ni  = F.ttm(["NetIncomeLoss", "ProfitLoss"])        # long: ticker, end, avail, val
    at  = F.instant(["Assets"])
    W   = F.daily(ni, dates, tickers)                   # wide daily panel, value usable at close of each date

PIT rules (load-bearing):
  * only the FIRST-filed value of each (concept, start, end) is used -- later restatements and
    10-K comparatives are ignored, because the market saw the original number first;
  * a value is usable at the close of the first trading day STRICTLY AFTER its EDGAR `filed`
    date (filings accepted after 17:30 ET carry the next day's date, and the 8-K press release
    usually came earlier, so this is conservative, never early);
  * trailing-twelve-month flows = FY value when the period is a fiscal year end, else
    FY_prev + YTD - YTD_prior_year (10-Q cash-flow statements are YTD only, so summing 3-month
    rows would miss them); the TTM becomes available when its LAST component was filed;
  * a ticker whose CIK was taken from SEC's current ticker list (past S&P members) is kept only
    if that registrant actually filed during the ticker's price history -- otherwise the ticker
    has been recycled to another company.
"""
import os, sys
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "shared"))
from research_lib import DATA_DIR

FACTS = os.path.join(DATA_DIR, "SP500_xbrl_facts.parquet")
ACTIONS = os.path.join(DATA_DIR, "SP500_actions.parquet")

REVENUE = ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax",
           "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueNet",
           "SalesRevenueGoodsNet", "RevenuesNetOfInterestExpense", "SalesRevenueServicesNet"]
COGS = ["CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfGoodsSold", "CostOfServices"]
NETINC = ["NetIncomeLoss", "ProfitLoss", "NetIncomeLossAvailableToCommonStockholdersBasic"]
CFO = ["NetCashProvidedByUsedInOperatingActivities", "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"]
EQUITY = ["StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"]
# past-member tickers that SEC's current ticker list maps to a DIFFERENT, later registrant
# (checked by entity name, 2026-09): Anadarko->ARKO, BB&T->Beacon, Beam->Beam Therapeutics ...
RECYCLED = {"APC", "BBT", "BEAM", "CPWR", "EP", "KG", "LIFE", "MI", "POM", "S", "SE", "STI",
            "SUN", "TE", "MMI", "FCPT"}
# share counts reported in a different class unit than the traded line (BRK: Class A equivalents)
SHARE_MULT = {"BRK-B": 1500.0}
DIL_SHARES = ["WeightedAverageNumberOfDilutedSharesOutstanding", "WeightedAverageNumberOfSharesOutstandingBasic"]


def _nearest_pit(L, R, lkey, rkey, by, tol_days, lfiled, rfiled):
    """merge_asof(direction='nearest') restricted to right rows filed no later than the left row:
    the match a reader could have made on the left row's filing date. L must carry a unique 'rid'.
    Left rows without a match keep NaN right columns."""
    m = L[by + ["rid", lkey, lfiled]].merge(R, on=by, how="inner")
    m = m[((m[lkey] - m[rkey]).dt.days.abs() <= tol_days) & (m[rfiled] <= m[lfiled])]
    m = m.assign(_dist=(m[lkey] - m[rkey]).dt.days.abs()).sort_values(["rid", "_dist", rfiled])
    m = m.drop_duplicates("rid", keep="first")
    add = [c for c in R.columns if c not in by]
    return L.merge(m[["rid"] + add], on="rid", how="left")


class Fundamentals:
    def __init__(self, facts_path=FACTS):
        f = pd.read_parquet(facts_path)
        f = f[f.form.isin(["10-Q", "10-K", "10-Q/A", "10-K/A", "10-KT", "20-F", "40-F", "10-KT/A"])]
        # first-filed value per (ticker, concept, unit, start, end)
        f = f[~f.ticker.isin(RECYCLED)]
        for t, k in SHARE_MULT.items():
            sel = (f.ticker == t) & (f.unit == "shares")
            f.loc[sel, "val"] = f.loc[sel, "val"] * k
        f = f.sort_values(["filed", "accn"]).drop_duplicates(["ticker", "concept", "unit", "start", "end"], keep="first")
        self.facts = f
        self._recycled_check()
        self.actions = pd.read_parquet(ACTIONS) if os.path.exists(ACTIONS) else None

    def _recycled_check(self):
        """Drop tickers whose registrant never filed while the ticker's price history ran."""
        from research_lib import daily_cache_path
        keep = []
        for t, g in self.facts.groupby("ticker"):
            p = daily_cache_path(t)
            if not os.path.exists(p):
                continue
            idx = pd.read_parquet(p, columns=["Close"]).index
            a, b = pd.Timestamp(idx.min()).tz_localize(None), pd.Timestamp(idx.max()).tz_localize(None)
            n_in = ((g.filed >= a) & (g.filed <= b + pd.Timedelta(days=120))).sum()
            if n_in >= 20:
                keep.append(t)
        self.dropped = sorted(set(self.facts.ticker) - set(keep))
        self.facts = self.facts[self.facts.ticker.isin(keep)]

    # ------------------------------------------------------------------ flows
    def _dur_facts(self, concepts, unit):
        f = self.facts[self.facts.concept.isin(concepts) & (self.facts.unit == unit)].dropna(subset=["start"]).copy()
        f["dur"] = (f["end"] - f["start"]).dt.days
        f["prio"] = f.concept.map({c: i for i, c in enumerate(concepts)})
        return f[["ticker", "concept", "prio", "start", "end", "dur", "val", "filed"]]

    def ttm(self, concepts, unit="USD"):
        """TTM flow per (ticker, period end). Concepts are alternatives in priority order.
        Every choice is point-in-time: the YTD row is the longest among those FIRST filed for that
        period end, and the prior-FY / prior-year-YTD components must have been filed no later
        than it (so the TTM is available on the YTD's own filing date)."""
        f = self._dur_facts(concepts, unit)
        ann = f[(f.dur >= 350) & (f.dur <= 380)]
        ytd = f[(f.dur >= 80) & (f.dur < 350)]
        first = ytd.groupby(["ticker", "concept", "end"])["filed"].transform("min")
        Y = ytd[ytd.filed == first].sort_values("dur").drop_duplicates(["ticker", "concept", "end"], keep="last").copy()
        Y["qn"] = (Y.dur / 91.3).round().astype(int)
        Y["rid"] = np.arange(len(Y))
        # prior fiscal year ending the day before the YTD start
        A = ann[["ticker", "concept", "end", "val", "filed"]].rename(columns={"end": "a_end", "val": "a_val", "filed": "a_filed"})
        Y["a_key"] = Y["start"] - pd.Timedelta(days=1)
        Y = _nearest_pit(Y, A, "a_key", "a_end", ["ticker", "concept"], 10, "filed", "a_filed")
        # prior-year YTD of the same length
        P = ytd.copy(); P["qn"] = (P.dur / 91.3).round().astype(int)
        P = P[["ticker", "concept", "qn", "end", "val", "filed"]].rename(columns={"end": "p_end", "val": "p_val", "filed": "p_filed"})
        Y["p_key"] = Y["end"] - pd.Timedelta(days=364)
        Y = _nearest_pit(Y, P, "p_key", "p_end", ["ticker", "concept", "qn"], 10, "filed", "p_filed")
        Y = Y.dropna(subset=["a_val", "p_val"])
        Y["ttm"] = Y.a_val + Y.val - Y.p_val
        Y["avail"] = Y["filed"]
        d = pd.concat([ann.rename(columns={"filed": "avail"})[["ticker", "prio", "end", "avail", "val"]],
                       Y.rename(columns={"val": "ytd", "ttm": "val"})[["ticker", "prio", "end", "avail", "val"]]])
        # an annual row and a derived row can share an end (FY end): keep the annual (listed first)
        d = d.drop_duplicates(["ticker", "prio", "end"], keep="first")
        return self._merge_prio(d)

    def quarterly(self, concepts, unit="USD"):
        """Single-quarter (3-month) flow per (ticker, end): direct 3-month rows, else the
        difference of two cumulative rows with the same start ~3 months apart (Q4 = FY - 9M)."""
        f = self._dur_facts(concepts, unit)
        q = f[(f.dur >= 80) & (f.dur <= 100)].rename(columns={"filed": "avail"})
        C = f[(f.dur > 100) & (f.dur <= 380)].copy()
        C["key"] = C["end"] - pd.Timedelta(days=91)
        prev = f[["ticker", "concept", "start", "end", "val", "filed"]].rename(
            columns={"end": "p_end", "val": "p_val", "filed": "p_filed"})
        C["rid"] = np.arange(len(C))
        C = _nearest_pit(C, prev, "key", "p_end", ["ticker", "concept", "start"], 12, "filed", "p_filed")
        C = C.dropna(subset=["p_val"])
        C["val"] = C.val - C.p_val
        C["avail"] = C["filed"]
        d = pd.concat([q[["ticker", "prio", "end", "avail", "val"]], C[["ticker", "prio", "end", "avail", "val"]]])
        d = d.drop_duplicates(["ticker", "prio", "end"], keep="first")
        return self._merge_prio(d)

    def latest_avg(self, concepts, unit="shares"):
        """Period averages that must not be differenced (weighted share counts): per (ticker,
        end) the shortest-duration row, i.e. the latest quarter's average when one is reported."""
        f = self._dur_facts(concepts, unit)
        f = f[(f.dur >= 80) & (f.dur <= 380)].sort_values("dur").drop_duplicates(["ticker", "prio", "end"], keep="first")
        return self._merge_prio(f.rename(columns={"filed": "avail"})[["ticker", "prio", "end", "avail", "val"]])

    # --------------------------------------------------------------- instants
    def instant(self, concepts, unit="USD"):
        f = self.facts[self.facts.concept.isin(concepts) & (self.facts.unit == unit) & self.facts.start.isna()]
        d = f[["ticker", "end", "filed", "val", "concept"]].rename(columns={"filed": "avail"})
        d["prio"] = d.concept.map({c: i for i, c in enumerate(concepts)})
        return self._merge_prio(d.drop(columns="concept"))

    @staticmethod
    def _merge_prio(d):
        """One value per (ticker, end) AT EACH POINT IN TIME: rows are taken in filing order and a
        row is kept only if its concept outranks every earlier-filed row for that period. So a
        lower-priority tag is used until the preferred one is filed, never shadowed by it in
        hindsight (daily() lets the later version replace the earlier one on its own date)."""
        d = d.sort_values(["ticker", "end", "avail", "prio"])
        best = d.groupby(["ticker", "end"])["prio"].cummin()
        prev = best.groupby([d["ticker"], d["end"]]).shift(1)
        d = d[prev.isna() | (d["prio"] < prev)]
        return d[["ticker", "end", "avail", "val"]].reset_index(drop=True)

    # ------------------------------------------------------------ to daily
    @staticmethod
    def daily(long, dates, tickers=None, max_age_days=400, field="val"):
        """Wide panel: at close of date d, the value with the latest period `end` among those
        filed strictly before d. Values whose period ended > `max_age_days` ago go NaN.
        field='end' returns the period-end date (as datetime64) instead of the value."""
        dates = pd.DatetimeIndex(dates)
        g = long if tickers is None else long[long.ticker.isin(tickers)]
        g = g.sort_values(["ticker", "avail", "end"])
        # a later-filed row with an OLDER period end (late comparative) never replaces a newer one
        g = g[g["end"] >= g.groupby("ticker")["end"].cummax()]
        pos = dates.searchsorted(g["avail"].values, side="right")        # first date > avail
        g = g.assign(pos=pos)[pos < len(dates)]
        g = g.assign(d=dates[g.pos.values])
        V = g.pivot_table(index="d", columns="ticker", values="val", aggfunc="last")
        E = g.assign(e=g["end"].astype("int64")).pivot_table(index="d", columns="ticker", values="e", aggfunc="last")
        V = V.reindex(dates).ffill(); E = E.reindex(dates).ffill()
        age = (dates.values.astype("int64")[:, None] - E.values) / 86400e9
        V = V.where(age <= max_age_days)
        if tickers is not None:
            V = V.reindex(columns=pd.Index(tickers))
        return V

    # ------------------------------------------------------------- splits
    def split_factor_after(self, dates, tickers):
        """Wide: product of split ratios with ex-date strictly after d (1 if none). Multiply a
        share count reported on date d by this to put it on today's (split-adjusted) basis."""
        dates = pd.DatetimeIndex(dates)
        out = pd.DataFrame(1.0, index=dates, columns=pd.Index(tickers))
        sp = self.actions[self.actions.split > 0]
        for t, g in sp[sp.ticker.isin(tickers)].groupby("ticker"):
            f = pd.Series(1.0, index=dates)
            for dt, ratio in zip(g.date, g.split):
                f[dates < dt] *= ratio
            out[t] = f.values
        return out

    def div_factor(self, adj_close):
        """Wide: Yahoo dividend adjustment factor F_t (adj = split-only-adjusted x F). Rebuilt
        from ex-dates: going back past ex-date u, F_{u-1} = F_u * (C - D)/C with the split-
        adjusted close C = adj_{u-1}/F_u + D."""
        F = pd.DataFrame(1.0, index=adj_close.index, columns=adj_close.columns)
        dv = self.actions[self.actions.dividend > 0]
        idx = adj_close.index
        for t, g in dv[dv.ticker.isin(adj_close.columns)].groupby("ticker"):
            px = adj_close[t]
            f = np.ones(len(idx))
            cur = 1.0
            for dt, D in sorted(zip(g.date, g.dividend), reverse=True):
                k = idx.searchsorted(dt)             # ex-date bar
                if k <= 0 or k >= len(idx):
                    continue
                p_prev = px.iloc[k - 1]
                if not np.isfinite(p_prev):
                    continue
                C = p_prev / cur + D
                cur = cur * (C - D) / C
                f[:k] = cur
            F[t] = f
        return F
