# Market data available to research

Two stores sit under `data/`, and they answer different questions.

| Store | Shape | Read with | Good for |
|---|---|---|---|
| **Flat daily cache** | one parquet per instrument, `<TICKER>_d.parquet` | `research_lib.load_series` | Daily studies, macro overlays, anything already written |
| **Partitioned bar store** | `data/bars/<SYMBOL>/<freq>/<year>.parquet` | `bars.load_bars` | 1m and intraday, multi-year, multi-symbol |
| **Vintage store** | `data/vintages/<SERIES>.parquet` | `fetch_alfred.as_of` | Point-in-time macro — what was *knowable* on a date |
| **Tick store** | `data/ticks/...` (D: disk) | `ticks.load_aggtrades` | Every trade / quote: order flow, true costs, sub-minute bars |

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

## 4. Tick store — `ticks.py` (dedicated disk on D:)

Raw trades and quotes are too big for the distro disk (its VHDX sits on C:, ~300 GB free,
and never shrinks). They live on their own ext4 virtual disk:

    D:\WSL\autoquant-ticks.vhdx  ->  /mnt/wsl/autoquant-ticks  <-  data/ticks (symlink)

Set up once from an elevated prompt with `code/shared/ticks_disk.ps1` (creates, formats,
mounts, links `data/ticks` to it, and registers the logon task **"autoQuant ticks disk"**
that remounts it). After `wsl --shutdown` the disk is detached until next logon; remount
without UAC:

```bash
schtasks.exe /run /tn "autoQuant ticks disk"
```

`ticks_root()` **refuses** to run when the disk is not mounted — `/mnt/wsl` is a tmpfs, so a
write there fills RAM and a read sees an "empty" store. `AQ_TICKS_DIR` overrides for tests.

| Data | Path | Kept size |
|---|---|---|
| Binance aggTrades, spot BTC/ETH | `ticks/binance/spot/aggTrades/<SYM>/<YYYY-MM>.parquet` | ~30 GB |
| Binance aggTrades, USD-M perps BTC/ETH + 22 alts | `ticks/binance/um/aggTrades/...` | ~80 GB |
| Dukascopy bid/ask ticks, 7 majors 2012+ | `ticks/dukascopy/<SYM>/<YYYY-MM>.parquet` | ~7 GB |

```python
from ticks import load_aggtrades, load_fx_ticks, flow_bars, summary
t = load_aggtrades("BTCUSDT", "um", start="2024-03-12", end="2024-03-12 23:59:59")
b = flow_bars(t, "1s")     # OHLCV + qv n tb tq -- same schema as klines, any freq down to 1s
summary()                  # what is on the disk
```

aggTrades columns: `ts` (trade time, µs), `price`, `qty`, `buyer_maker` (**True = the taker
sold**), `n_trades` (fills merged), `agg_id`. Flow bars rebuilt from them match Binance's
own klines exactly (checked on LINKUSDT spot Dec-2024/Jan-2025, 1,488/1,488 hours, across the
ms→µs switch). USD-M perps agree to ~1e-4, not exactly: on ATOMUSDT Jan-2024 H/L/C match on
744/744 hours, but 5 opens are one tick off and ~0.02% of volume sits in the neighbouring hour
around the 3-Jan crash -- Binance's kline engine buckets a few boundary fills differently.
1m perp flow bars are materialised into the bar store as `<SYM>_PERP/1m`;
sub-minute bars are built on demand, not cached.

Mounting and backfilling are automatic: `autoquant-ticks.service` (installed by
`harness/install_autostart.sh`) mounts the disk whenever WSL comes up and keeps the backfill
running, resuming where it stopped and then fetching new data every 6 h. Service log:
`harness/logs/ticks.log`; job logs: `data/ticks/logs/`. By hand (resumable; skips a job the
service is already running):

```bash
code/shared/tick_backfill.sh              # binance + dukascopy
python code/shared/fetch_binance_vision.py aggtrades --market um --symbol SOLUSDT,XRPUSDT
python code/shared/fetch_dukascopy.py ticks --symbols EURUSD --start 2012-01-01 --workers 1
```

Deliberately **not** stored: Binance raw `trades` (same fills as aggTrades, 1.5× the size),
`1s` klines (rebuildable from aggTrades), full bookTicker history (~70 GB/yr zipped for
BTC; keep using `fetch_binance_vision.py book` windows), and equity/futures ticks — no free
full-history source exists (IEX HIST is one venue at ~2–3% of volume; CME/CBOE are paid).

---

## Still daily-only

Equities, ETFs, futures and rates remain daily yfinance OHLCV back to 2010. yfinance caps
intraday history at ~730 days, so there is no long intraday for those classes, and no
delisted tickers — which is why the `us-large-cap` survivorship brief cannot be fully
honoured on this data. That needs a paid vendor (Polygon or Databento) and is not wired up.

---

## 5. US large-cap panel — `code/us-large-cap/shared/`

Added 2026-09-16 by the `us-large-cap` research. Everything below reads and writes the
**flat daily cache** (one `data/<TICKER>_d.parquet` per name), so the sim book can price
any of it.

```python
import sys; sys.path.insert(0, "code/us-large-cap/shared")
from panel import load_panel          # dict: open/high/low/close/volume (wide), member (PIT bool), sector
from universe import membership_matrix, all_tickers_since   # fja05680/sp500 start/end spans, 1996+
from earnings import load_earnings, reaction_day_matrix     # data/SP500_earnings_dates.parquet
from xs_lib import xs_backtest, decile_weights, linear_weights, group_demean, ic_series
```

* **Membership** is point-in-time from `sp500_ticker_start_end.csv` (fja05680/sp500, cross-
  checked with Wikipedia's *Historical components* page). `sp500_current_raw.csv` carries
  GICS sectors for current names; `sectors_hist.csv` (yfinance `.info`) for past ones.
* **Survivorship**: yfinance serves *no delisted tickers*. Of 813 names that were members
  at some point since 2010, 646 are priced; coverage of the live index is 75 % in 2010,
  90 % in 2019, 98 % in 2026. Missing names are overwhelmingly acquisitions (BK, EA, MMC
  in 2026), not bankruptcies, but any long-only or long-loser result on this panel is
  biased upward. Refresh with `fetch_universe.py <tickers.txt>`.
* **Recycled tickers — trap.** yfinance answers an old symbol with whatever company holds
  it *today* (TIE, MEE, CBE, CPWR, EP, BMC …), producing 1000× fake moves. `load_panel`
  drops any ticker with ≥3 daily |returns| > 50 % and masks a ±1-day window around isolated
  ones. Do not read those files raw.
* **Earnings dates**: `data/SP500_earnings_dates.parquet` — ~100 announcements per ticker
  back to 2002 from `Ticker.get_earnings_dates(limit=100)`, with the Yahoo hour (16:00 ET
  = after close, ≤ 09:00 = before open) so the *reaction bar* can be placed. 79 % of
  reaction bars show volume > 1.5× the 20-day average (median 2.1×), i.e. the dates are
  right to the day for most events. Refresh with `fetch_earnings.py <tickers.txt>` (slow:
  one request per ticker, ~40 min for the universe).
* **pandas 3 `stack()` keeps NaN** — every event count computed with `.stack()` on a
  masked frame is the whole panel unless you `.dropna()`. It cost this research one wrong
  table before it was caught.

### 5.1 Point-in-time fundamentals, filings, insiders, index changes (added 2026-09-27)

| Store | Built by | Content |
|---|---|---|
| `data/SP500_xbrl_facts.parquet` | `code/us-large-cap/shared/fetch_xbrl.py [--refresh]` | 3.3 M SEC companyfacts rows (55 us-gaap/dei concepts), 625 tickers, every filing's version with its EDGAR `filed` date |
| `data/SP500_actions.parquet` | `fetch_actions.py` | 30 k split / cash-dividend ex-dates (Yahoo, split-adjusted amounts) |
| `data/SP500_insider_trades.parquet` | `fetch_form345.py` | 829 k Form 4 open-market P/S transactions 2006+, filing dates, owner roles |
| `data/SP500_filing_similarity.parquet` | `fetch_filing_text.py [--update]` | 41.5 k 10-K/10-Q: YoY TF / log-TF cosine, Jaccard, length ratio vs the same form a year earlier |
| `code/us-large-cap/shared/sp500_*.csv` | `fetch_sp500_changes.py` | Wikipedia constituents + changes table (moved to *Historical components of the S&P 500* in 2026) and PIT spans rolled forward |

Read fundamentals only through `code/us-large-cap/shared/xbrl.py` (`Fundamentals().ttm/instant/latest_avg/daily`). Traps it handles:

* **Recycled tickers at the SEC too**: `company_tickers.json` maps past members' symbols to later registrants (APC→ARKO, STI→Solidion, SE→Sea Ltd, S→SentinelOne …). `xbrl.RECYCLED` drops them; check `entityName` for any new past-member mapping.
* **Holding-company reorganisations** (XOM 2026, GOOGL 2015, DIS 2019, BLK 2024, AVGO, MDT, CI, ICE, ETN, APA …) start a new CIK: `fetch_xbrl.PREDECESSORS` attaches the old registrant's history. Without it XOM has no fundamentals before Aug-2026.
* **PIT means per-version, not per-period**: use the first-filed value of each (concept, period); when two tags describe a period, the lower-priority one counts until the preferred one is *filed*; TTM and year-ago "nearest period" joins may only use rows filed no later than the row being built. The first version of the reader violated the last two and a truncation test caught it (`large-cap-sleeve-blend/lookahead_check.py`).
* 10-Q cash-flow statements are **YTD only**: TTM = FY_prev + YTD − YTD_prior, not a sum of quarters. Share counts are period averages and must not be differenced.
* Market cap from the cache needs the **dividend adjustment undone** (`Fundamentals.div_factor`) and share counts **split-adjusted after their filing date**; BRK reports Class-A-equivalent shares (`SHARE_MULT`).
* EDGAR's 10 requests/s limit: the text fetcher is CPU-bound (multi-MB inline-XBRL documents), so it runs processes with per-process pacing. The full history takes ~3 h.
* Several idea folders each have a `strategy.py`: load them with `code/us-large-cap/shared/modload.load(path)`, not `import strategy`.
