"""Robustness of the flow-calendar strategy on TLT.

 (a) per-year Sharpe of every leg and of the a-priori core3 combination
 (b) walk-forward leg selection: each year, keep only legs whose Newey-West t on all
     data *before* that year exceeds a threshold -- no leg is ever chosen on its own year
 (c) vol-targeted sizing of the calendar position
 (d) deflated Sharpe over the number of configurations evaluated
 (e) correlation with the live spot-BTC / spot-ETH trend strategies (proxied by their
     published rules) and hedge value on their worst days
 (f) block bootstrap CI on the full-sample Sharpe
"""
import os, sys
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "../../shared"))
sys.path.insert(0, os.path.join(HERE, "../../spot-btc/weekday-trend"))
sys.path.insert(0, HERE)
import research_lib as rl
import backtest_calendar as bc

ANN = 252
COST = 2.0


def yearly_sharpe(net):
    g = net.groupby(net.index.year)
    return (g.mean() / g.std() * np.sqrt(ANN)).round(2)


def main():
    pd.set_option("display.width", 220, "display.max_columns", 40, "display.max_rows", 200)
    tlt = bc.load_close("TLT"); idx = tlt.index
    legs = {
        "month_end3": bc.leg_month_end(idx, 3),
        "month_end2": bc.leg_month_end(idx, 2),
        "month_end4": bc.leg_month_end(idx, 4),
        "month_start_short": bc.leg_month_start(idx, (3, 5)),
        "fomc_1b+0": bc.leg_fomc(idx, 1, True),
        "fomc_0": bc.leg_fomc(idx, 0, True),
        "fomc_2b+0": bc.leg_fomc(idx, 2, True),
        "pre_auc_10y20y_2d": bc.leg_pre_auction(idx, ("10y", "20y"), 2),
        "pre_auc_10y_2d": bc.leg_pre_auction(idx, ("10y",), 2),
        "pre_auc_10y20y_1d": bc.leg_pre_auction(idx, ("10y", "20y"), 1),
        "pre_auc_10y20y_3d": bc.leg_pre_auction(idx, ("10y", "20y"), 3),
        "pre_auc_10y30y20y_2d": bc.leg_pre_auction(idx, ("10y", "30y", "20y"), 2),
        "post_auc_10y30y_12": bc.leg_post_auction(idx, ("10y", "30y"), (1, 2)),
    }
    core = ["month_end3", "fomc_1b+0", "pre_auc_10y20y_2d"]
    nets = {n: rl.backtest(w, tlt, COST, ANN, n)[0] for n, w in legs.items()}
    w_core = bc.combine([legs[p] for p in core])
    nets["core3"] = rl.backtest(w_core, tlt, COST, ANN, "core3")[0]

    print("\n(a) per-year Sharpe (2 bp/side)")
    print(pd.DataFrame({n: yearly_sharpe(v) for n, v in nets.items()}).T.to_string())

    # ------------------------------------------------------------------ (b) walk-forward
    print("\n(b) walk-forward leg selection (expanding window from 2002, first test year 2010)")
    # candidate families, one representative per family to keep the search honest
    cands = ["month_end3", "month_start_short", "fomc_1b+0", "pre_auc_10y20y_2d", "post_auc_10y30y_12"]
    years = range(2010, 2027)
    wf_w = pd.Series(0.0, index=idx)
    chosen_log = {}
    for thr in (1.0, 1.5, 2.0):
        wf_w = pd.Series(0.0, index=idx)
        for y in years:
            train = slice(None, f"{y-1}-12-31")
            keep = []
            for c in cands:
                r = nets[c].loc[train]
                r = r[legs[c].shift(1).loc[train].abs() > 0]   # only active days matter for the t-stat
                if len(r) > 60 and rl.newey_west_t(r.values, lags=5) > thr:
                    keep.append(c)
            chosen_log[(thr, y)] = keep
            if keep:
                wy = bc.combine([legs[c] for c in keep]).loc[str(y)]
                wf_w.loc[str(y)] = wy
        net_wf, st = rl.backtest(wf_w, tlt, COST, ANN, f"wf_thr{thr}")
        sub = net_wf.loc["2010":]
        print(f"  thr={thr}: Sharpe 2010-26 {rl.perf_stats(sub, ANN)['Sharpe']:.2f} | "
              f"2010-17 {rl.perf_stats(sub.loc[:'2017'], ANN)['Sharpe']:.2f} | "
              f"2018-26 {rl.perf_stats(sub.loc['2018':], ANN)['Sharpe']:.2f} | "
              f"CAGR {rl.perf_stats(sub, ANN)['CAGR']*100:.1f}% MaxDD {rl.perf_stats(sub, ANN)['MaxDD']*100:.1f}%")
        if thr == 1.5:
            for y in years:
                print(f"     {y}: {chosen_log[(thr, y)]}")
            net_wf.to_frame("wf").to_parquet(os.path.join(HERE, "walkforward_returns.parquet"))

    # ------------------------------------------------------------------ (c) vol targeting
    print("\n(c) vol-targeted sizing of core3: w = sign * clip(target/ewm_vol, 0, cap)")
    ret = tlt.pct_change()
    ewv = ret.ewm(halflife=20, min_periods=20).std() * np.sqrt(ANN)
    for target, cap in [(0.12, 1.0), (0.15, 1.5), (0.15, 2.0), (0.20, 2.0)]:
        scale = (target / ewv).clip(0, cap).fillna(0.0)
        w = w_core * scale
        _, df = bc.evaluate(w, tlt, COST, f"vt{target}_cap{cap}")
        print(f"  target={target} cap={cap}:", rl.fmt(df)[["Sharpe", "CAGR", "MaxDD", "AvgExpo", "Turn/yr"]].to_dict("index"))

    # ------------------------------------------------------------------ (d) deflated Sharpe
    n_trials = 25
    full = nets["core3"].loc["2010":]
    s = rl.perf_stats(full, ANN)
    dsr = rl.deflated_sharpe(s["Sharpe"], len(full), n_trials, skew=s["Skew"], kurt=s["Kurt"] + 3, ann=ANN)
    print(f"\n(d) core3 full 2010-26: Sharpe {s['Sharpe']:.2f}, skew {s['Skew']:.2f}, kurt(excess) {s['Kurt']:.2f}; "
          f"deflated-Sharpe P(SR>0 | {n_trials} trials) = {dsr:.3f}")

    # ------------------------------------------------------------------ (f) bootstrap
    rng = np.random.default_rng(0)
    x = full.values; n = len(x); B = 2000; blk = 21
    srs = []
    for _ in range(B):
        starts = rng.integers(0, n - blk, size=n // blk + 1)
        y = np.concatenate([x[s0:s0 + blk] for s0 in starts])[:n]
        srs.append(y.mean() / y.std(ddof=1) * np.sqrt(ANN))
    srs = np.array(srs)
    print(f"(f) block-bootstrap (21d blocks) Sharpe 5-95%: [{np.percentile(srs,5):.2f}, {np.percentile(srs,95):.2f}], P(SR>1)={np.mean(srs>1):.2f}")

    # ------------------------------------------------------------------ (e) live-book hedge value
    print("\n(e) correlation with the live spot-crypto trend book (proxied by published rules)")
    from strategy import target_weight as btc_weight   # weekday-trend
    btc = rl.load_series("BTC-USD")["Close"]; eth = rl.load_series("ETH-USD")["Close"]
    btc_net, _ = rl.backtest(btc_weight(btc), btc, 10.0, 365, "btc_weekday_trend")
    eth_ret = eth.pct_change()
    eth_scale = (0.5 / (eth_ret.ewm(halflife=20, min_periods=20).std() * np.sqrt(365))).clip(0, 1).fillna(0)
    eth_w = (eth > eth.rolling(40).mean()).astype(float) * eth_scale
    eth_net, _ = rl.backtest(eth_w, eth, 10.0, 365, "eth_trend_filter")
    book = pd.concat({"btc_wt": btc_net, "eth_tf": eth_net, "btc_bh": btc.pct_change(), "tlt_bh": ret,
                      "core3": nets["core3"], "me3": nets["month_end3"]}, axis=1).loc["2018":].dropna()
    print(book.corr().round(3).to_string())
    # weekly aggregation (crypto trades 7 days; bonds 5) to avoid calendar-mismatch artefacts
    wk = book.resample("W").sum()
    print("\n  weekly-return correlations:"); print(wk.corr().round(3).loc[["core3", "me3", "tlt_bh"], ["btc_wt", "eth_tf", "btc_bh"]].to_string())
    bad = wk[wk["btc_wt"] < wk["btc_wt"].quantile(0.10)]
    print(f"\n  in the worst-decile weeks of btc weekday-trend (n={len(bad)}): mean btc_wt {bad['btc_wt'].mean()*100:.2f}%, "
          f"core3 {bad['core3'].mean()*100:+.2f}%, tlt_bh {bad['tlt_bh'].mean()*100:+.2f}%")
    # what does adding core3 to the book do?
    for lev in (0.5, 1.0, 2.0):
        mix = wk["btc_wt"] + lev * wk["core3"]
        print(f"  book + {lev}x core3: weekly Sharpe {mix.mean()/mix.std()*np.sqrt(52):.2f} (book alone {wk['btc_wt'].mean()/wk['btc_wt'].std()*np.sqrt(52):.2f})")


if __name__ == "__main__":
    main()
