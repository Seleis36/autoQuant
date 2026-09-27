# filing-text-changes — "Lazy Prices": year-over-year textual similarity of 10-K/10-Q filings

**Status: Failed** as a standalone strategy; used as a sleeve in `large-cap-sleeve-blend`
(Working). The *level* of similarity works in the paper's direction: non-changers beat
changers. With a Jaccard metric over all forms, the quintile beta-hedged book earns
**0.55 full / 0.86 IS / 0.40 OOS** at 5 bp, at 2.3 % vol. The paper's *mechanism* does not
replicate, though. Similarity measured against the firm's own history (a surprise change) has
the **wrong sign** (−0.4 to −0.6). The residualised signal keeps 0.45 / 0.48 / 0.43 after
removing size, low-vol, profitability and leverage exposure, with ~0.3 Sharpe of alpha
beyond the other sleeves.

Date: 2026-09-27 · Asset class: us-large-cap · IS 2011–2017 / OOS 2018–2026-09 · 5 bp per side
· 48 books (6 metrics/forms × 2 books × 2 hedges × 2 form sets) + 2 diagnostics.

Code: `code/us-large-cap/filing-text-changes/` (`screen1.py`, `screen2_diag.py`,
**`strategy.py`** → `text_weights`). New shared data:
`code/us-large-cap/shared/fetch_filing_text.py` → `data/SP500_filing_similarity.parquet`.

## 1. Idea

Cohen, Malloy & Nguyen (2020, *Lazy Prices*, JF) find that when a firm's 10-K/10-Q differs
from last year's, the firm under-performs over the following months. Investors do not read
the changes, which are disproportionately bad news: new litigation, risk factors, executive
turnover. The portfolio of "non-changers minus changers" earned 30–60 bp/month in 5-factor
alpha, including in large caps, with no reversal. The signal is slow (quarterly), free
(EDGAR), point-in-time by construction (filing dates), and unrelated to prices or accounting
ratios.

## 2. Data (`fetch_filing_text.py`, new)

* Every 10-K/10-Q primary document filed 2008+ by the 607 priced panel issuers (current CIK +
  holdco predecessors): **41,548 filings**. Each is stripped of HTML and inline-XBRL headers
  and reduced to lowercase alphabetic tokens. It is compared with the **same form for the
  period one year earlier** (Q2 vs Q2, 10-K vs 10-K).
* Metrics kept (raw documents are discarded): TF cosine, log-TF cosine, Jaccard on word sets,
  and the log length ratio. TF cosine is saturated (median 0.999 for 10-Ks) because
  boilerplate stop words dominate. Log-TF cosine and Jaccard spread out (10-K Jaccard median
  0.885, IQR 0.857–0.908).
* A filing is usable from the first session after its filing date and expires 200 days after
  its period end. `--update` adds new filings incrementally for live use (verified to
  reproduce the stored metrics exactly).
* Download: about 3 h for the full history at ~8 requests/s. Tokenising multi-MB inline-XBRL
  documents is CPU-bound, so the fetcher uses processes, not threads.

## 3. Results

### 3.1 Screen (`screen1.py`, sector-neutral monthly books, net 5 bp)

| signal | book | raw | β-hedged (IS / OOS) |
|---|---|---|---|
| **Jaccard, all forms** | quintile | 0.36 | **0.55 (0.86 / 0.40)** |
| Jaccard, all forms | linear | 0.24 | 0.44 (0.64 / 0.34) |
| log-TF cosine, all forms | quintile | 0.21 | 0.38 (0.34 / 0.42) |
| TF cosine, all forms | quintile | 0.21 | 0.39 (0.18 / 0.52) |
| −abs(length change), all forms | quintile | −0.06 | 0.10 |
| Jaccard, 10-K only | quintile | 0.32 | 0.46 (0.18 / 0.65) |
| **log-TF cosine minus firm's own 8-filing mean** | quintile | **−0.51** | −0.49 |
| **Jaccard minus firm's own mean** | quintile | **−0.56** | −0.53 |

IC with the next 63-day return is 0.011–0.016 for the level metrics and −0.010 for the
firm-demeaned one. 10-K-only books turn over 1.8×/yr, and all-form books 5.7×/yr.

### 3.2 Is it a proxy? (`screen2_diag.py`)

* The average cross-sectional rank correlation with the `quality-value-composite` signals is
  small: ROA 0.15, CFO/A 0.13, B/M −0.11, low-vol 0.08, size −0.02.
* Residualising the text z-score each month on size, low-vol, ROA, GPA and leverage leaves
  **0.45 full / 0.48 IS / 0.43 OOS** (β-hedged quintile).
* Spanning regression on the QVC blend and residual momentum:
  * raw text: alpha Sharpe 0.22 full, 0.71 IS, **0.06 OOS**. OOS it loads 0.37 on QVC.
  * residualised text: alpha Sharpe 0.33 full, 0.46 IS, **0.32 OOS**.

The raw sleeve's OOS return is mostly quality exposure. The part orthogonal to quality has
held up, but that residualisation was chosen *after* this OOS-informed diagnostic, so it is
not used in the headline blend (it is reported there as a sensitivity).

## 4. Why the paper's mechanism fails here

In CMN the *change* is the information. Here, a firm whose similarity is unusually high
relative to its own history under-performs, and a firm whose text changed more than usual
does better. The level effect behaves like a slow characteristic instead. Firms with stable,
boilerplate-heavy disclosure (utilities, staples, mature industrials) out-perform on a beta-
and sector-neutral basis, in a way only partly explained by profitability. Likely reasons:

1. Large caps are read closely. The "lazy" investor inattention CMN document is weaker in
   S&P 500 names after 2010, and ESG/NLP vendors have scraped these filings since ~2015.
2. The 2019–2020 switch to inline XBRL changed every document's token mix. Firm-demeaned
   measures pick up the timing of that format change, not news.

## 5. Variants and multiple testing

48 books. The sleeve used in the blend (Jaccard, all forms, quintile, β-hedged) has the best
IS Sharpe of the *level* metrics, so the selection is IS-based. Its OOS 0.40 is the honest
number. Expected best-of-48 under the null is of the order of the IS figure, so the
standalone evidence is weak (Failed). The sleeve adds to the blend through its low
correlation with momentum and events.
