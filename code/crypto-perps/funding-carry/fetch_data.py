"""Fetch what the funding-carry study needs from data.binance.vision.

  data/bars/<SYM>_PERP/1h/   USD-M perpetual 1h klines (stored under a _PERP suffix so
                             they never collide with the spot partitions of the same symbol)
  data/bars/<SYM>/1h/        spot 1h klines for alts (BTC/ETH spot come from the 1m store)
  data/<SYM>_fundingRate.parquet   every funding settlement since perp launch

Reuses the transport helpers of code/shared/fetch_binance_vision.py.
"""
import io, os, sys
import pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(ROOT, "code", "shared"))
import bars as barstore
import fetch_binance_vision as fbv

def fetch_perp_klines(symbol, freq="1h", start="2019-09-08", end=None):
    end = pd.Timestamp(end) if end else fbv._utcnow().normalize()
    buf, total = [], 0
    for kind, when in fbv._periods(start, end):
        stamp = when.strftime("%Y-%m" if kind == "monthly" else "%Y-%m-%d")
        url = f"{fbv.BASE}/data/futures/um/{kind}/klines/{symbol}/{freq}/{symbol}-{freq}-{stamp}.zip"
        blob = fbv._get(url)
        if blob is None:
            continue
        csv = fbv._unzip(blob, url, verify=False)
        df = pd.read_csv(io.BytesIO(csv), header=None, names=fbv.KLINE_COLS, on_bad_lines="skip")
        df = df[pd.to_numeric(df["ot"], errors="coerce").notna()]
        df["ts"] = fbv._to_datetime(df["ot"])
        df = df.drop(columns=["ot"] + fbv.KLINE_DROP).set_index("ts").apply(pd.to_numeric, errors="coerce")
        buf.append(df)
        print(f"  {symbol}_PERP {stamp} {len(df)} bars", flush=True)
    if buf:
        total = barstore.write_bars(pd.concat(buf), f"{symbol}_PERP", freq)
    return total

if __name__ == "__main__":
    syms = sys.argv[1:] or ["BTCUSDT", "ETHUSDT"]
    starts = {"BTCUSDT": "2019-09-08", "ETHUSDT": "2019-11-27"}
    for s in syms:
        st = starts.get(s, "2020-01-01")
        print("== funding", s); fbv.fetch_funding(s, start=st)
        print("== perp 1h", s); fetch_perp_klines(s, "1h", start=st)
        if s not in ("BTCUSDT", "ETHUSDT"):
            print("== spot 1h", s); fbv.fetch_klines(s, "1h", "spot", start=st, verify=False)
