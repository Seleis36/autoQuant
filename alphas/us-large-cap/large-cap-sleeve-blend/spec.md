# Alpha spec — large-cap-sleeve-blend (us-large-cap)

**Status:** Working — recommended deploy. Net Sharpe **1.03 full / 1.57 IS (2011-17) / 0.81 OOS
(2018-2026-09)** at 5 bp per side.

| field | value |
|---|---|
| Instruments | S&P 500 constituents (single names, flat daily cache `data/<TICKER>_d.parquet`); hedges are EW member / EW sector baskets of the same names |
| Direction | long/short, beta-neutral (β −0.00 to the EW member market; net dollars avg +0.30) |
| Sleeves and multipliers | RM residual momentum 0.457 · QVC fundamental quality 2.478 · TXT filing-text similarity 2.664 · REC short-additions 1.211 (inverse IS vol, 10 % IS vol) |
| Rebalance | RM/QVC/TXT books at the last NYSE session of each month (`trading_calendar.month_end_sessions`); QVC/TXT beta hedges re-sized daily, RM hedge and vol scale monthly; REC on event days (short at the close of an addition's first session in the index, cover 5 sessions later) |
| Sizing | `blend_weights(X)` = Σ MULT_k · W_k (target weights, fraction of capital) |
| Leverage | average gross 4.44, max 6.29 (validated) |
| Bar / timezone | daily closes, US/Eastern; weights computed at close t, filled at close t, earn t→t+1 |
| Cost assumed | 5 bp per side on Σ|Δw| (weight level) |
| Turnover | 42× per year one-way |
| Names held | ≈ 430 |

## Performance (net, weight level)

| | Sharpe | CAGR | max DD | vol |
|---|---|---|---|---|
| Full 2011-01 → 2026-09 | 1.03 | 14.4 % | −23.0 % | 14.1 % |
| IS 2011-2017 | 1.57 | | | |
| OOS 2018-2026-09 | 0.81 | 12.9 % | −23.0 % | 16.6 % |
| cost 2 bp / 10 bp (full / OOS) | 1.12 / 0.89 · 0.88 / 0.69 | | | |

Correlation to SPY 0.06. Leave-one-out OOS: without RM 0.66, without QVC 0.76, without TXT
0.82, without REC 0.70.

## Code

```python
import sys; sys.path.insert(0, "code/us-large-cap/large-cap-sleeve-blend")
from strategy import blend_weights, panel_inputs, sleeve_weights, MULT
X = panel_inputs()          # {"close", "member", "sector", "rsp"} from the flat cache + PIT membership
W = blend_weights(X)        # dates x tickers target weights; all defaults = this spec
```

Sleeve functions: `code/us-large-cap/residual-momentum/strategy.py:residual_momentum_weights`,
`quality-value-composite/strategy.py:qvc_weights`, `filing-text-changes/strategy.py:text_weights`,
`index-reconstitution/strategy.py:recon_weights`.

## Data to refresh before each close (live)

```bash
python code/us-large-cap/shared/fetch_sp500_changes.py          # constituents, changes table, PIT membership spans
python code/us-large-cap/shared/fetch_universe.py code/us-large-cap/shared/tickers_current.txt   # new members' prices (or live_lib.daily)
python code/us-large-cap/shared/fetch_actions.py                # splits + dividends (market cap reconstruction)
python code/us-large-cap/shared/fetch_xbrl.py --refresh         # EDGAR companyfacts -> data/SP500_xbrl_facts.parquet
python code/us-large-cap/shared/fetch_filing_text.py --update --workers 10   # new 10-K/10-Q only -> data/SP500_filing_similarity.parquet
```

The SEC asks for <= 10 requests/s with a descriptive User-Agent (the fetchers pace themselves).
Fundamentals and filings become usable at the close of the first session after their filing
date. Lookahead check: `code/us-large-cap/large-cap-sleeve-blend/lookahead_check.py`
(truncated vs full-sample weights agree to < 1e-6 on all sleeves).

Fallback if the EDGAR pipelines cannot run live: `alphas/us-large-cap/residual-momentum/`
(prices only, 0.63 OOS).

Report: `past_research/us-large-cap/large-cap-sleeve-blend/2026-09-27_large_cap_sleeve_blend.md`.
