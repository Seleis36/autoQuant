"""Independent pre-sample test of the relative trend on 1980-2000 (never used to choose
anything): USD-converted local price indices, monthly, ex-US EW vs S&P 500.
FX: FRED H.10 daily noon rates, month-end. Germany only from 1999 (EUR): the pre-1999 DM series
on FRED is a monthly AVERAGE, and averaging manufactures positive autocorrelation -- exactly the
bias a trend test must not have."""
import sys, os
sys.path.insert(0, "../shared")
import numpy as np, pandas as pd, warnings
warnings.filterwarnings("ignore")
import data as D, research_lib as rl

def idx_long(t):
    a = pd.read_parquet(rl.daily_cache_path(t).replace("_d.parquet", "_d_long.parquet"))["Close"]
    b = D.load_ohlcv(t)["Close"]
    a.index = pd.to_datetime(a.index); k = b.iloc[0] / a.reindex(b.index[:1], method="ffill").iloc[0] if False else 1.0
    s = pd.concat([a[a.index < b.index.min()], b]).sort_index()
    return s[~s.index.duplicated()]

def me(s):  # month-end value
    return s.resample("ME").last()

fx = {"JP": 1 / D.load_fred("DEXJPUS"), "UK": D.load_fred("DEXUSUK"), "CA": 1 / D.load_fred("DEXCAUS"),
      "AU": D.load_fred("DEXUSAL"), "HK": 1 / D.load_fred("DEXHKUS"), "DE": D.load_fred("DEXUSEU")}
loc = {"JP": "^N225", "UK": "^FTSE", "CA": "^GSPTSE", "AU": "^AXJO", "HK": "^HSI", "DE": "^GDAXI"}
lvl = {}
for c, t in loc.items():
    li = me(idx_long(t)); f = me(fx[c])
    x = (li * f).dropna()
    if c == "DE":
        x = x[x.index >= "1999-01-31"]
    lvl[c] = x
L = pd.DataFrame(lvl)
us = me(idx_long("^GSPC"))
R = L.pct_change(fill_method=None); rus = us.pct_change().reindex(R.index)
# only count a country once it has 24 months of history
R = R.where(L.notna() & L.shift(24).notna())
print("countries available by year:", R.notna().sum(axis=1).groupby(R.index.year).max().loc[[1976, 1980, 1985, 1988, 1993, 1999, 2005]].to_dict())

def beta36(y, x):
    return y.rolling(36, min_periods=24).cov(x) / x.rolling(36, min_periods=24).var()

def run(spread, lbs, name):
    lp = np.log((1 + spread.fillna(0.0)).cumprod()).where(spread.notna())
    s = sum(np.sign(lp - lp.shift(l)) for l in lbs) / len(lbs)
    vol = spread.rolling(36, min_periods=24).std() * np.sqrt(12)
    pos = (s * 0.10 / vol).shift(1)
    cost = pos.diff().abs() * 2 * 5 / 1e4            # 5 bp on leg + hedge, per side
    net = pos * spread - cost
    out = {}
    for per, (a, b) in {"1980-2000": ("1980", "2000"), "1985-2000": ("1985", "2000"),
                        "2001-2012": ("2001", "2012"), "2013-2026": ("2013", "2026"), "ALL": ("1980", "2026")}.items():
        n = net.loc[a:b].dropna()
        out[per] = n.mean() / n.std() * np.sqrt(12) if len(n) > 24 else np.nan
    out["n_months_1980_2000"] = net.loc["1980":"2000"].dropna().shape[0]
    return pd.Series(out, name=name)

rows = []
exus = R.mean(axis=1, skipna=True).where(R.notna().sum(axis=1) >= 1)
b = beta36(exus, rus).shift(1)
agg = exus - b * rus
agg_dn = exus - rus
for lbs, tag in [((1, 3, 6, 12), "ens(1,3,6,12m)"), ((6, 12, 24), "slow(6,12,24m)"), ((12,), "12m"),
                 ((1,), "1m"), ((3,), "3m"), ((6,), "6m"), ((24,), "24m")]:
    rows.append(run(agg, lbs, f"AGG beta-hedged | {tag}"))
    rows.append(run(agg_dn, lbs, f"AGG dollar-neutral | {tag}"))
# diversified: per-country spreads, equal risk
for lbs, tag in [((1, 3, 6, 12), "ens"), ((6, 12, 24), "slow")]:
    parts = []
    for c in R.columns:
        bc = beta36(R[c], rus).shift(1)
        sp = R[c] - bc * rus
        lp = np.log((1 + sp.fillna(0.0)).cumprod()).where(sp.notna())
        s = sum(np.sign(lp - lp.shift(l)) for l in lbs) / len(lbs)
        vol = sp.rolling(36, min_periods=24).std() * np.sqrt(12)
        pos = (s * 0.10 / vol).shift(1)
        parts.append((pos * sp - pos.diff().abs() * 10 / 1e4).rename(c))
    P = pd.concat(parts, axis=1)
    net = P.mean(axis=1, skipna=True)
    out = {}
    for per, (a, b_) in {"1980-2000": ("1980", "2000"), "1985-2000": ("1985", "2000"), "2001-2012": ("2001", "2012"),
                         "2013-2026": ("2013", "2026"), "ALL": ("1980", "2026")}.items():
        n = net.loc[a:b_].dropna(); out[per] = n.mean() / n.std() * np.sqrt(12)
    rows.append(pd.Series(out, name=f"DIV per-country | {tag}"))
print(pd.DataFrame(rows).round(2).to_string())

# --- the deployed blend (50 % AGG + 50 % DIV, slow 6/12/24m), each sleeve at 10 % vol
def agg_net(lbs):
    lp = np.log((1 + agg.fillna(0.0)).cumprod()).where(agg.notna())
    s = sum(np.sign(lp - lp.shift(l)) for l in lbs) / len(lbs)
    vol = agg.rolling(36, min_periods=24).std() * np.sqrt(12)
    pos = (s * 0.10 / vol).shift(1)
    return pos * agg - pos.diff().abs() * 10 / 1e4
div_parts = []
for c in R.columns:
    bc = beta36(R[c], rus).shift(1); sp = R[c] - bc * rus
    lp = np.log((1 + sp.fillna(0.0)).cumprod()).where(sp.notna())
    s = sum(np.sign(lp - lp.shift(l)) for l in (6, 12, 24)) / 3
    vol = sp.rolling(36, min_periods=24).std() * np.sqrt(12)
    pos = (s * 0.10 / vol).shift(1)
    div_parts.append((pos * sp - pos.diff().abs() * 10 / 1e4).rename(c))
dn = pd.concat(div_parts, axis=1).mean(axis=1, skipna=True)
an = agg_net((6, 12, 24))
dn = dn * (0.10 / (dn.std() * np.sqrt(12)))       # equalise sleeve vol (ex-post scale only, Sharpe-neutral per sleeve)
an = an * (0.10 / (an.std() * np.sqrt(12)))
bl = (0.5 * an + 0.5 * dn).dropna()
print("\nBLEND 50/50 slow, monthly index data:")
for per, (a, b_) in {"1980-2000": ("1980", "2000"), "1985-2000": ("1985", "2000"), "2001-2012": ("2001", "2012"),
                     "2013-2026": ("2013", "2026"), "ALL": ("1980", "2026")}.items():
    n = bl.loc[a:b_]; print(f"  {per}: SR {n.mean()/n.std()*np.sqrt(12):.2f}  months {len(n)}")
print("  corr(AGG, DIV) monthly:", round(an.corr(dn), 2))
