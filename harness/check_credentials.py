#!/usr/bin/env python3
"""Which Binance account do the keys in .env actually belong to?

    .venv/bin/python harness/check_credentials.py

Binance runs several independent account databases. A key minted on the futures
testnet does not exist on the spot testnet, and neither exists in production --
they are different sites with different signups. The permission checkboxes you tick
when creating a key ("Enable Spot & Margin Trading") only apply within the site that
issued it, so a futures-testnet key with spot enabled still cannot trade spot.

This probes each host and reports which one recognises the key, so the harness's
venue can be confirmed rather than assumed.
"""
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from live_lib import SPOT_KEY_ENV, SPOT_SECRET_ENV, load_env  # noqa: E402

HOSTS = [
    ("Binance SPOT testnet     ", "https://testnet.binance.vision", "/api/v3/account",
     "THIS IS THE ONE THE HARNESS USES"),
    ("Binance FUTURES testnet  ", "https://testnet.binancefuture.com", "/fapi/v2/account",
     "futures testnet -- separate account, not used by the harness"),
    ("Binance SPOT production  ", "https://api.binance.com", "/api/v3/account",
     "REAL MONEY -- the harness must never trade here"),
    ("Binance FUTURES production", "https://fapi.binance.com", "/fapi/v2/account",
     "REAL MONEY -- the harness must never trade here"),
]


def probe(key, secret, base, path):
    try:
        srv = json.load(urllib.request.urlopen(
            base + ("/fapi/v1/time" if path.startswith("/fapi") else "/api/v3/time"),
            timeout=10))["serverTime"]
    except Exception:  # noqa: BLE001
        srv = int(time.time() * 1000)
    q = urllib.parse.urlencode({"timestamp": srv, "recvWindow": 20_000})
    sig = hmac.new(secret.encode(), q.encode(), hashlib.sha256).hexdigest()
    req = urllib.request.Request(f"{base}{path}?{q}&signature={sig}",
                                 headers={"X-MBX-APIKEY": key})
    try:
        return True, json.load(urllib.request.urlopen(req, timeout=15))
    except urllib.error.HTTPError as e:
        try:
            return False, json.loads(e.read().decode())
        except Exception:  # noqa: BLE001
            return False, {"code": e.code, "msg": "unparseable error"}
    except Exception as e:  # noqa: BLE001
        return False, {"code": "net", "msg": str(e)}


def equity(payload):
    if "balances" in payload:      # spot
        rows = [(b["asset"], float(b["free"]) + float(b["locked"]))
                for b in payload["balances"]]
        held = {a: v for a, v in rows if v > 0}
        return f"{len(held)} funded asset(s): " + (str(held) if held else "none -- EMPTY")
    if "totalMarginBalance" in payload:   # futures
        return f"margin balance {payload['totalMarginBalance']} USDT"
    return "authenticated"


def main():
    load_env()
    pairs = [(SPOT_KEY_ENV, SPOT_SECRET_ENV), ("BINANCE_API_KEY_PAPER", "BINANCE_SECRET_KEY_PAPER")]
    tested = 0
    for kname, sname in pairs:
        key, secret = os.environ.get(kname, ""), os.environ.get(sname, "")
        if not key or not secret:
            print(f"\n{kname}: not set in .env")
            continue
        tested += 1
        print(f"\n=== {kname} (…{key[-6:]}) ===")
        for label, base, path, note in HOSTS:
            ok, payload = probe(key, secret, base, path)
            if ok:
                print(f"  RECOGNISED  {label} {equity(payload)}")
                print(f"              -> {note}")
            else:
                print(f"  rejected    {label} [{payload.get('code')}] {payload.get('msg')}")
    if not tested:
        print("No Binance credentials found in .env.")
        return 2
    print(f"\nThe harness trades spot testnet only. If no key above is RECOGNISED there,\n"
          f"create one at https://testnet.binance.vision (log in with GitHub, 'Generate\n"
          f"HMAC_SHA256 Key') and add it to .env as:\n"
          f"  {SPOT_KEY_ENV}=...\n  {SPOT_SECRET_ENV}=...\n"
          "Until then strategies run in clearly-labelled shadow mode.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
