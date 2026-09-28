# auction-demand-signal — do Treasury auction results predict the next days' returns?

**Date:** 2026-09-29 · **Asset class:** rates-bonds · **Status:** **Failed**

## 1. Idea

Treasury publishes each coupon auction's results at ~13:00 ET, three hours before the ETF
close: bid-to-cover, the split of the award between primary dealers, direct and indirect
bidders, and the high / median / low accepted yield. A "weak" auction — dealers forced to take
a large share, low cover, a wide bid distribution — tells you who is left holding the new
supply. Dealer-inventory theory gives two predictions of opposite sign, so the direction was
to be chosen in-sample:

* **inventory overhang:** dealers distribute unwanted paper over the following days →
  continued underperformance;
* **liquidity provision:** the auction cleared at a concession that is paid back as
  inventory is placed → recovery (the conditional version of Lou-Yan-Zhang's post-auction
  rebound, which `treasury-flow-calendar` found dead unconditionally since 2017).

## 2. Data and setup — `01_event_study.py`, `01_event_study_output.txt`

* `code/rates-bonds/shared/fetch_auctions.py` (new, reusable) → `data/UST_auctions.parquet`:
  every note/bond/TIPS auction 1990-2026 from TreasuryDirect `TA_WS/securities/search`, with
  all result fields. Investor-class allocations are populated from **2008-04**.
* Metrics z-scored against the same tenor's trailing 12 auctions: dealer share, indirect share,
  bid-to-cover, dispersion (high − median yield), composite `weak` = mean(z_dealer, −z_indirect,
  −z_btc, z_disp).
* Target: excess return of the auctioned maturity (synthetic CMT par bond: 2y/3y → 2y,
  5y/7y → 5y, 10y → 10y, 20y/30y → 30y) over t+1…t+h, t = auction-day close; plus the auction
  day's own close-to-close return for context.
* 1,341 nominal auctions with all metrics. **Split fixed in advance:** IS 2008-04 → 2016
  (570), OOS 2017 → 2026 (771).

## 3. Results

Spearman IC (positive = metric high → bond up):

| Metric | auction day (not tradable) IS / OOS | t+1 IS / OOS | t+1..t+2 IS / OOS | t+1..t+5 IS / OOS |
|---|---|---|---|---|
| weak (composite) | **−0.25 / −0.19** | −0.06 / +0.04 | −0.14 / +0.05 | −0.05 / +0.09 |
| bid-to-cover | +0.25 / +0.20 | +0.03 / −0.00 | +0.13 / −0.02 | +0.08 / −0.09 |
| dealer share | −0.18 / −0.12 | −0.07 / +0.01 | −0.09 / +0.01 | −0.02 / +0.06 |
| indirect share | +0.15 / +0.09 | +0.09 / −0.07 | +0.10 / −0.04 | +0.01 / −0.05 |
| dispersion | −0.20 / −0.19 | +0.03 / +0.06 | −0.05 / +0.08 | −0.02 / +0.09 |

Quintiles of `weak`, mean return in bp (0 = strongest demand):

| | day 0 | t+1..t+2 | t+1..t+5 |
|---|---|---|---|
| IS, strongest / weakest | +13.9 / −18.6 | +22.0 / +1.9 | +22.7 / +13.9 |
| OOS, strongest / weakest | +10.9 / −11.6 | −5.0 / +4.4 | −15.3 / +8.4 |

* The auction result is **priced on the day**: weak auctions close 25-30 bp worse than strong
  ones, in both windows. But the reaction happens between 13:00 and the 16:00 close, and a
  daily-bar strategy fills at the close, after it.
* After the close, the sign **flips between windows**. In 2008-2016 weak auctions keep
  underperforming for two days (inventory overhang, IC −0.14). In 2017-2026 they recover
  over the following week (liquidity provision, IC +0.05 to +0.09). The flip holds for
  every metric and most tenors. A direction chosen in-sample loses out of sample.

## 4. Verdict

**Failed.** 5 metrics × 6 horizons × 2 windows plus per-tenor and quintile cuts (~100 cells).
The only large effect is the auction-day repricing, which daily bars cannot reach. The
post-auction drift changes sign across the 2017 split. Nothing was built into a book,
because a direction fixed on IS has negative OOS IC by construction.

## 5. Reusable

`code/rates-bonds/shared/fetch_auctions.py` — full TreasuryDirect auction results (1990+;
investor classes 2008+). It is the input for any intraday auction study, if intraday
Treasury data ever becomes available.
