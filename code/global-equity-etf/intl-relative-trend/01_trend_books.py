"""Aggregate vs diversified relative trend; lookback grid; monthly vs weekly; 5 bp/side."""
from lib import *
import warnings; warnings.filterwarnings("ignore")
C, ret = load()
rows, nets = [], {}
# (A) aggregate EXUS spread = EW 9 countries - beta SPY  (as a synthetic single instrument)
ret["EXUS"] = ret[COUNTRIES].mean(axis=1, skipna=True)
C["EXUS"] = (1 + ret["EXUS"].fillna(0.0)).cumprod()
for universe, names in [("AGG_EXUS", ["EXUS"]), ("AGG_EFA", ["EFA"]), ("AGG_EEM", ["EEM"]),
                        ("DIV9", COUNTRIES), ("DIV9+EFA+EEM", COUNTRIES + ["EFA", "EEM"])]:
    sr, beta = spread_returns(ret, names)
    for freq in ["M", "W"]:
        reb = xs.rebalance_dates(C.loc["2001-01-01":].index, freq)
        for lbs, tag in [(LB, "ens"), ((21,), "21"), ((63,), "63"), ((126,), "126"), ((252,), "252"),
                         ((126, 252, 504), "ens_slow")]:
            if freq == "W" and tag not in ("ens",):
                continue
            s = trend_signal(sr, lbs)
            w = build_weights(s, sr, beta, names, reb)
            if universe == "AGG_EXUS":
                # EXUS is synthetic: expand into the 9 ETFs equally
                wx = w["EXUS"]
                w = pd.DataFrame({t: wx / len(COUNTRIES) * C.loc[reb, t].notna() * len(COUNTRIES) / C.loc[reb, COUNTRIES].notna().sum(axis=1) for t in COUNTRIES})
                w["SPY"] = build_weights(s, sr, beta, names, reb)["SPY"]
            net, gross, turn, We = book(C, ret, w, name=f"{universe}|{tag}|{freq}")
            rows.append(row(net, turn, We, f"{universe}|{tag}|{freq}", gross)); nets[f"{universe}|{tag}|{freq}"] = net
df = pd.DataFrame(rows)
pd.set_option("display.width", 250)
print(df[["FULL_SR", "FULL_SR_gross", "IS_SR", "OOS_SR", "FULL_CAGR", "MaxDD", "Vol", "t_NW", "Turn/yr", "Gross", "Net"]].round(2).to_string())
pd.DataFrame(nets).to_parquet("nets_01.parquet")
