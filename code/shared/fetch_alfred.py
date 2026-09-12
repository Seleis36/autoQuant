"""Point-in-time macro from ALFRED, the vintage archive behind FRED.

FRED serves the macro series *as they are today*. That is the wrong series for a
backtest, in two separate ways, and only one of them is the famous one:

  1. **Revision.** GDP, payrolls, industrial production and retail sales are revised for
     years after first print. A 2013 backtest reading today's GDPC1 trades on a number
     nobody could see until 2016.
  2. **Release lag, which bites harder and is quieter.** CPI for March is published in
     mid-April. A frame indexed by observation date puts that value on 2026-03-01, so a
     signal reading "CPI at month end" is reading roughly six weeks into its own future
     -- every month, in every backtest, with no jump in the equity curve to give it away.

ALFRED fixes both by keying on the *vintage date*: what the series looked like to
somebody standing on that day. `as_of(series, t)` is the primitive -- the series as
known at t, revisions and release lag both respected.

Access is keyless via the graph CSV endpoint:

    https://alfred.stlouisfed.org/graph/alfredgraph.csv?id=<SERIES>&vintage_date=<DATE>

One request per vintage -- the endpoint ignores repeated and comma-joined `vintage_date`
parameters, silently returning only the last, so batching is not available and the local
cache does the work instead. Vintages are stored long in
`data/vintages/<SERIES>.parquet` as (vintage_date, obs_date, value) and re-fetching only
pulls dates not already held.

Daily market series (`DGS10`, `DFF`, ...) are never revised and have no release lag
beyond a day, so they do not need this. It is the monthly and quarterly aggregates --
the ones that drive every macro overlay in this repo -- that do.
"""
import argparse
import io
import os
import sys
import time
import urllib.error
import urllib.request

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import research_lib
from research_lib import _atomic_parquet

ALFRED = "https://alfred.stlouisfed.org/graph/alfredgraph.csv"
FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv"
UA = {"User-Agent": "autoquant-research/1.0"}

#: Series worth having point-in-time, and why. Daily market rates are deliberately absent:
#: they are never revised, so `research_lib.load_series` is already correct for them.
PIT_SERIES = {
    "CPIAUCSL":   "CPI, all urban consumers, SA -- monthly, ~2 week release lag",
    "PAYEMS":     "Nonfarm payrolls -- monthly, first Friday, revised twice",
    "UNRATE":     "Unemployment rate -- monthly",
    "INDPRO":     "Industrial production -- monthly, revised for years",
    "GDPC1":      "Real GDP -- quarterly, three estimates then annual revisions",
    "PCEPILFE":   "Core PCE, the Fed's target -- monthly",
    "RSAFS":      "Retail sales -- monthly, heavily revised",
    "HOUST":      "Housing starts -- monthly, wide revisions",
    "UMCSENT":    "Michigan sentiment -- monthly, preliminary then final",
    "M2SL":       "M2 money stock -- monthly",
}


def vintages_dir():
    return os.path.join(research_lib.DATA_DIR, "vintages")


def vintages_path(series_id):
    return os.path.join(vintages_dir(), f"{series_id}.parquet")


def _get(url, tries=5, timeout=60):
    last = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            last = e
        except Exception as e:  # noqa: BLE001 -- transient, retried
            last = e
        time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"GET failed after {tries} tries: {url}") from last


def _parse(blob):
    """ALFRED CSV -> (obs_date, value). Missing observations print as '.'."""
    df = pd.read_csv(io.BytesIO(blob))
    if df.shape[1] < 2:
        return None
    obs, val = df.columns[0], df.columns[1]
    out = pd.DataFrame({
        "obs_date": pd.to_datetime(df[obs], errors="coerce"),
        "value": pd.to_numeric(df[val].replace(".", np.nan), errors="coerce"),
    }).dropna(subset=["obs_date"])
    return out


def fetch_vintage(series_id, vintage_date):
    """The whole series as published on `vintage_date`."""
    d = pd.Timestamp(vintage_date).strftime("%Y-%m-%d")
    blob = _get(f"{ALFRED}?id={series_id}&vintage_date={d}")
    if blob is None:
        return None
    out = _parse(blob)
    if out is None or out.empty:
        return None
    out["vintage_date"] = pd.Timestamp(vintage_date)
    return out[["vintage_date", "obs_date", "value"]]


def vintage_grid(start="2010-01-01", end=None, freq="MS"):
    """Vintage dates to sample.

    Monthly (the default) is *conservative, not exact*: a value published on the 10th is
    not visible until the next grid point, so a signal can lag a release by up to ~30
    days. It never front-runs one, which is the direction that matters -- a late signal
    costs return, an early one manufactures it. Pass `freq="W"` or `"D"` when the timing
    of the release is itself the signal (an NFP-day or CPI-day study), at the cost of one
    request per grid point per series.
    """
    end = pd.Timestamp(end) if end else pd.Timestamp.now("UTC").tz_convert(None).normalize()
    return pd.date_range(pd.Timestamp(start), end, freq=freq)


def fetch_series(series_id, start="2010-01-01", end=None, freq="MS", verbose=True):
    """Cache every vintage on the grid for `series_id`, skipping ones already held."""
    os.makedirs(vintages_dir(), exist_ok=True)
    path = vintages_path(series_id)
    have = pd.DataFrame(columns=["vintage_date", "obs_date", "value"])
    if os.path.exists(path):
        have = pd.read_parquet(path)
    known = set(pd.to_datetime(have["vintage_date"]).unique()) if len(have) else set()

    frames, fetched = [], 0
    for v in vintage_grid(start, end, freq):
        if v.to_datetime64() in known or v in known:
            continue
        part = fetch_vintage(series_id, v)
        if part is None:
            continue
        frames.append(part)
        fetched += 1
        if verbose and fetched % 24 == 0:
            print(f"    {series_id} {v.date()}  {fetched} vintages", flush=True)
        time.sleep(0.12)
    if not frames:
        return have
    out = pd.concat([have] + frames, ignore_index=True) if len(have) else pd.concat(frames, ignore_index=True)
    out["vintage_date"] = pd.to_datetime(out["vintage_date"])
    out["obs_date"] = pd.to_datetime(out["obs_date"])
    out = (out.drop_duplicates(subset=["vintage_date", "obs_date"], keep="last")
              .sort_values(["vintage_date", "obs_date"])
              .reset_index(drop=True))
    _atomic_parquet(out, path)
    return out


def load_vintages(series_id):
    path = vintages_path(series_id)
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"no vintages cached for {series_id}; run "
            f"`python code/shared/fetch_alfred.py --series {series_id}`")
    df = pd.read_parquet(path)
    df["vintage_date"] = pd.to_datetime(df["vintage_date"])
    df["obs_date"] = pd.to_datetime(df["obs_date"])
    return df


def as_of(series_id, when, vintages=None):
    """The series as it was known on `when` -- the point-in-time primitive.

    Uses the latest vintage at or before `when`, so the result contains only values that
    had actually been published by then. Asking before the first cached vintage returns
    an empty series rather than the oldest one: pretending 2009 saw the 2010 vintage is
    the exact error this module exists to prevent.
    """
    v = load_vintages(series_id) if vintages is None else vintages
    when = pd.Timestamp(when)
    usable = v[v["vintage_date"] <= when]
    if usable.empty:
        return pd.Series(dtype=float, name=series_id)
    latest = usable["vintage_date"].max()
    cut = usable[usable["vintage_date"] == latest]
    s = cut.set_index("obs_date")["value"].sort_index()
    s.name = series_id
    return s


def pit_frame(series_id, dates, vintages=None):
    """Point-in-time *observable* series: for each date in `dates`, the newest value that
    had been published by then.

    This is what a macro overlay actually wants -- one number per decision date, with the
    release lag already respected -- rather than a frame indexed by observation date that
    quietly front-runs every print.
    """
    v = load_vintages(series_id) if vintages is None else vintages
    rows = {}
    for d in pd.DatetimeIndex(dates):
        s = as_of(series_id, d, vintages=v)
        rows[d] = np.nan if s.empty else float(s.iloc[-1])
    out = pd.Series(rows, name=series_id)
    out.index.name = "ts"
    return out


def revision_report(series_id, vintages=None):
    """How much this series moves after first print -- the size of the look-ahead you
    take by using today's values in a backtest."""
    v = load_vintages(series_id) if vintages is None else vintages
    first = v.sort_values("vintage_date").groupby("obs_date")["value"].first()
    final = v.sort_values("vintage_date").groupby("obs_date")["value"].last()
    d = (final - first).dropna()
    rel = (d / first.reindex(d.index).abs().replace(0, np.nan)).dropna()
    return {
        "series": series_id,
        "observations": int(len(d)),
        "mean_abs_revision": float(d.abs().mean()),
        "mean_abs_revision_pct": float(rel.abs().mean() * 100),
        "max_abs_revision": float(d.abs().max()) if len(d) else float("nan"),
        "pct_revised": float((d.abs() > 1e-12).mean() * 100),
    }


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--series", default=",".join(PIT_SERIES),
                   help="comma-separated FRED ids")
    p.add_argument("--start", default="2010-01-01")
    p.add_argument("--end", default=None)
    p.add_argument("--freq", default="MS", help="vintage sampling grid (MS = monthly)")
    p.add_argument("--report", action="store_true", help="print revision sizes and exit")
    a = p.parse_args()

    ids = [s.strip().upper() for s in a.series.split(",") if s.strip()]
    for sid in ids:
        if a.report:
            try:
                r = revision_report(sid)
            except FileNotFoundError as e:
                print(f"{sid}: {e}")
                continue
            print(f"{sid:10s} n={r['observations']:>4}  revised {r['pct_revised']:5.1f}%  "
                  f"mean |rev| {r['mean_abs_revision_pct']:6.2f}%  "
                  f"max |rev| {r['max_abs_revision']:.3f}")
            continue
        print(f"== {sid}  {PIT_SERIES.get(sid, '')}", flush=True)
        df = fetch_series(sid, start=a.start, end=a.end, freq=a.freq)
        nv = df["vintage_date"].nunique() if len(df) else 0
        print(f"   {len(df):,} rows across {nv} vintages -> {vintages_path(sid)}", flush=True)


if __name__ == "__main__":
    main()
