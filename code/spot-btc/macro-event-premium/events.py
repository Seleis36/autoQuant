"""Scheduled US macro release times in UTC: FOMC statements (14:00 ET), CPI and the
Employment Situation (08:30 ET). Dates come from the snapshots committed by
rates-bonds/treasury-flow-calendar (ALFRED vintage dates = release dates) and the
scheduled FOMC list in fx-majors/shared/fomc_dates.py."""
import os
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
SNAP = os.path.join(REPO, "code", "rates-bonds", "treasury-flow-calendar", "calendar_snapshots")
sys.path.insert(0, os.path.join(REPO, "code", "fx-majors", "shared"))
import fomc_dates  # noqa: E402


def _et(dates, hhmm):
    ts = pd.to_datetime([f"{d:%Y-%m-%d} {hhmm}" for d in dates])
    return ts.tz_localize("America/New_York").tz_convert("UTC").tz_localize(None)


def _one_per_month(dates):
    """ALFRED lists extra vintages (February seasonal-factor revisions). Keep the last
    vintage of each month, which is the scheduled release."""
    s = pd.Series(pd.to_datetime(dates)).sort_values()
    return pd.DatetimeIndex(s.groupby(s.dt.to_period("M")).max().values)


def event_times(start="2017-01-01"):
    fomc = fomc_dates.fomc_days()
    cpi = _one_per_month(pd.read_csv(os.path.join(SNAP, "cpi.csv"))["date"])
    nfp = _one_per_month(pd.read_csv(os.path.join(SNAP, "payrolls.csv"))["date"])
    ev = pd.concat([
        pd.DataFrame({"t": _et(fomc, "14:00"), "kind": "FOMC"}),
        pd.DataFrame({"t": _et(cpi, "08:30"), "kind": "CPI"}),
        pd.DataFrame({"t": _et(nfp, "08:30"), "kind": "NFP"}),
    ])
    ev = ev[ev.t >= start].sort_values("t").reset_index(drop=True)
    return ev
