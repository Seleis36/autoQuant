"""Costed books: contrarian XS Korea premium level, Korean volume-share surge, and their
composite; BTC-beta-hedged linear-rank, flat on days with < 6 names on both venues."""
from common import *
d = S.load(); c, m = d["c_alt"], d["mask"]
bab = S.bab_reference(); beta = S.ewm_beta(d["ret"], d["btc"].pct_change(), 60)
raw, xs, upq = premium_panel(["BTC-USD", "ETH-USD"] + list(c.columns), c.index)
prem = xs.reindex(columns=c.columns)
bq = V.panel(V.binance_daily, list(c.columns), "QuoteVolume").reindex(c.index)
share = np.log(upq.reindex(columns=c.columns) / bq)       # KRW/USDT scale cancels in own-history demeaning
mm = m & prem.notna(); mm = mm & (mm.sum(axis=1) >= 6).values[:, None]
av = np.log(d["v_alt"].rolling(30).mean() / d["v_alt"].rolling(180, min_periods=60).mean().shift(30))
rows, nets = [], {}
def run(sig, name, hold):
    w = rl.linear_weights(rl.rank_xs(sig, mm), mm)
    w = S.tranche(w.assign(**{"BTC-USD": -(w * beta).sum(axis=1)}), hold)
    net, st = S.bt(w, d["close"])
    r = S.row(net, name); r.update(turn=st["Turnover_ann"], rho_bab=net.corr(bab)); rows.append(r); nets[name] = net
for k in (7, 14, 30):
    lvl = prem.rolling(k, min_periods=k // 2).mean()
    shr = share.rolling(k, min_periods=k // 2).mean() - share.rolling(180, min_periods=60).mean().shift(k)
    for hold in (7, 14, 30):
        run(-lvl, f"contra_prem{k}|h{hold}", hold)
        run(-shr, f"krshare_surge{k}|h{hold}", hold)
        comp = rl.rank_xs(-lvl, mm).fillna(0) + rl.rank_xs(-shr, mm).fillna(0)
        run(comp.where(mm), f"composite{k}|h{hold}", hold)
res = pd.DataFrame(rows).set_index("name")
pd.set_option("display.width", 250)
print(res.round(2).to_string()); res.to_csv("books_02.csv"); pd.DataFrame(nets).to_parquet("books_02_nets.parquet")
for fam in ("contra_prem", "krshare_surge", "composite"):
    r = res[res.index.str.startswith(fam)]
    print(fam, "median", r[["full", "IS", "OOS", "rho_bab"]].median().round(2).to_dict())
# is Korean share surge just global abnormal volume on the same names?
N = pd.DataFrame(nets)
va = pd.read_parquet("../volume-attention/grid_01_nets.parquet")["k30|b180|h30|bn"]
print("corr krshare_surge30|h30 vs volume-attention k30|h30:", round(N["krshare_surge30|h30"].corr(va), 2))
