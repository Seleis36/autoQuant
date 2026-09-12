# Market data available to research

Two stores sit under `data/`, and they answer different questions.

| Store | Shape | Read with | Good for |
|---|---|---|---|
| **Flat daily cache** | one parquet per instrument, `<TICKER>_d.parquet` | `research_lib.load_series` | Daily studies, macro overlays, anything already written |
| **Partitioned bar store** | `data/bars/<SYMBOL>/<freq>/<year>.parquet` | `bars.load_bars` | 1m and intraday, multi-year, multi-symbol |
| **Vintage store** | `data/vintages/<SERIES>.parquet` | `fetch_alfred.as_of` | Point-in-time macro — what was *knowable* on a date |

The flat cache is unchanged and still correct for daily work. Nothing below replaces it.

---

## 1. Intraday bars — `bars.py`

```python
import sys; sys.path.insert(0, "code/shared")
from bars import load_bars, resample_bars, coverage

m  = load_bars("BTCUSDT", "1m")                       # 4.76M bars, 2017-08 -> now
m  = load_bars("BTCUSDT", "1m", start="2023-01-01")   # reads 4 year-files, not 10
h  = load_bars("BTCUSDT", "1h", resample_from="1m")   # coarsen on the fly, no 2nd copy
```

Conventions, and they are load-bearing:

* the index is the bar **OPEN** time, UTC, tz-naive; a bar stamped `t` covers `[t, t+freq)`;
* resampling is **left-labelled and left-closed** — the 1m bar stamped 09:00 lands in the
  1h bar stamped 09:00. Labelling right shifts every signal one bar into its own future
  and the backtest quietly improves, which is why `resample_bars` does not take a `label`
  argument;
* empty periods are **dropped, not forward-filled**. A synthetic bar spanning a venue
  outage is indistinguishable downstream from a real one.

Check what you have before trusting a window:

```python
coverage("BTCUSDT", "1m")
# {'bars': 4761918, 'pct_present': 99.821, 'missing': 8562,
#  'largest_gaps': [{'at': '2018-02-09 09:59:00', 'gap': '1 days 09:31:00'}, ...]}
```

The 0.18% missing is real Binance downtime (the Feb 2018 outage is 33 hours), not a
fetch failure. It is identical across symbols, because it was exchange-wide.

### What is cached

| Symbol | Freq | Span | Notes |
|---|---|---|---|
| `BTCUSDT` | 1m | 2017-08-17 → now | 4.76M bars, spot |
| `ETHUSDT` | 1m | 2017-08-17 → now | 4.76M bars, spot |
| `<SYM>_book` | 1m | windowed | Time-weighted spread from futures bookTicker |

Extend with `fetch_binance_vision.py`:

```bash
python code/shared/fetch_binance_vision.py klines --symbol SOLUSDT --freq 1m --start 2020-08-11
python code/shared/fetch_binance_vision.py klines --symbol BTCUSDT --freq 1m --market um  # perps
python code/shared/fetch_binance_vision.py book   --symbol BTCUSDT --days 90              # spreads
python code/shared/fetch_binance_vision.py metrics --symbol BTCUSDT   # open interest, L/S ratios
```

Two traps this fetcher handles so you do not have to:

1. **Binance changed kline timestamps from milliseconds to microseconds during 2025.**
   Reading a 16-digit stamp as ms lands the bar in the year 57000, silently.
2. **The current month has no monthly archive file**, so the tail comes from daily files.
   Stopping at the monthly boundary ends your history weeks early without complaint.

`bookTicker` is **futures-only** and ~199 MB *per day* for BTCUSDT. It is never cached
raw — only the 1m time-weighted spread aggregate is kept. Pull windows, not history.

---

## 2. FX with real spreads — `fetch_dukascopy.py`

yfinance `=X` is an indicative feed: no bid, no ask, no volume, and its daily rows are
stamped a day late (row `D` is the close at 00:00 UTC on `D`, covering UTC day `D−1` —
the Monday row is Friday's session). Every FX cost assumption made against it is a guess.

**It matters.** `calendar-flow-ensemble` was charged a flat 2 bp per side and died at net
Sharpe 0.35 against a gross 0.69. Measured on Dukascopy ticks, EURUSD's median spread is
**≈0.25 bps** — the assumption was roughly an order of magnitude too punitive. That does
not rescue the idea (it needed 2.0), but it means the cost model, not the signal, was
doing the killing.

```python
from fetch_dukascopy import spread_bps
spread_bps("EURUSD", "2015-08-24 03:00")   # measured bps for that pair/year/hour
```

Two modes, because the feed is throttled to well under one file per second:

```bash
# Spread profile: stratified sample, ~4 days per quarter. Hours, not days, to run.
python code/shared/fetch_dukascopy.py profile --start 2012-01-01 --per-quarter 4

# Full 1m bid/ask bars. ~24 requests per pair per day -- seven majors over sixteen
# years is ~700k requests. Days of wall clock. Narrow the window.
python code/shared/fetch_dukascopy.py bars --symbols EURUSD --start 2024-01-01
```

Bars carry `Open/High/Low/Close` on the **mid** (so returns are spread-neutral), plus
`Bid`, `Ask`, `Spread`, `SpreadBps` and `Ticks`. Charge the spread that actually stood at
the time you traded rather than a flat number — the profile is keyed by hour of day
precisely because 03:00 and 13:00 are not the same market.

---

## 3. Point-in-time macro — `fetch_alfred.py`

FRED serves macro series *as they are today*. That is wrong for a backtest twice over:

1. **Revision** — GDP, payrolls and industrial production are revised for years.
2. **Release lag**, which is quieter and bites harder — March CPI is published in
   mid-April, so a frame indexed by observation date shows it on `2024-03-01`, six weeks
   before anyone could read it. Every month. With no jump in the equity curve.

```python
from fetch_alfred import as_of, pit_frame, revision_report

as_of("CPIAUCSL", "2024-04-01").index.max()   # -> 2024-02-01, because March was unpublished
pit_frame("PAYEMS", weight_dates)             # one observable value per decision date
revision_report("INDPRO")                     # how far first print moves
```

`as_of` before the first cached vintage returns **empty**, not the oldest vintage —
handing a 2010 vintage to a 2009 caller is exactly the look-ahead this exists to remove.

```bash
python code/shared/fetch_alfred.py --start 2010-01-01           # the default ten series
python code/shared/fetch_alfred.py --series CPIAUCSL --freq W   # weekly grid, finer timing
python code/shared/fetch_alfred.py --report                     # revision sizes
```

The monthly vintage grid is **conservative, not exact**: a value published on the 10th is
not visible until the next grid point, so signals can lag a release by up to ~30 days. It
never front-runs one. Use `--freq W` or `D` when release *timing* is itself the signal.

Daily market series (`DGS10`, `DFF`) are never revised — `research_lib.load_series` is
already correct for those, and they are deliberately absent from `PIT_SERIES`.

---

## Still daily-only

Equities, ETFs, futures and rates remain daily yfinance OHLCV back to 2010. yfinance caps
intraday history at ~730 days, so there is no long intraday for those classes, and no
delisted tickers — which is why the `us-large-cap` survivorship brief cannot be fully
honoured on this data. That needs a paid vendor (Polygon or Databento) and is not wired up.
