# vol-etp-flow-sentiment — daily vol-ETP dollar volume as a crowding gauge

**Status: Failed.** A daily, price-based stand-in for the weekly COT crowding signal
(`vix-cot-positioning`), built from long-vol vs inverse-vol ETP dollar volume.

* The long-vs-inverse volume share carries no information (IC ≈ 0).
* *Abnormal* vol-ETP dollar volume has a negative IC with forward VIXY returns in both halves. But
  in IS that is fully explained by the VIX level (partial t −0.16).
* As a gate on carry it hurts: median 0.42 vs carry 0.60.
* Blended with the COT book it dilutes it: 0.90 vs 1.00.

36 configurations plus screens were evaluated.

Date: 2026-09-27 · Asset class: vol-complex · Author: research agent (Opus 5.5)

## 1. Idea

Idea 1 showed that the CFTC asset-manager net position in VIX futures, largely the vol-ETP sponsors,
is a useful crowding gauge. But it is weekly and released with a 3–6 day lag. ETP dollar volume
is daily and immediate:
* the share of long-vol ETP volume (UVXY, VIXY, VXX) vs inverse (SVXY) should proxy which side the
  retail crowd is on;
* abnormal volume (5- or 10-day vs 126-day average) should proxy attention and panic.

## 2. Screen (01_screen.py): Spearman IC vs forward VIXY log return

| feature | 1d IS | 5d IS | 21d IS | 1d OOS | 5d OOS | 21d OOS |
|---|---|---|---|---|---|---|
| long-vol share of ETP dollar volume, 5/21/63 d | ≈ 0 | ≈ 0 | −0.02…0.06 | ≈ 0 | −0.03…−0.05 | ≈ 0 |
| long share z-score vs 252 d | 0.01 | 0.02 | 0.01 | −0.03 | −0.04 | −0.03 |
| abnormal long-vol dollar volume (5 d / 126 d) | −0.05 | −0.10 | −0.13 | −0.11 | −0.18 | −0.27 |
| abnormal inverse dollar volume | −0.04 | −0.11 | −0.22 | −0.07 | −0.11 | −0.20 |

The volume share is uncorrelated with the COT score (−0.02) and correlated 0.45 with log VIX. SVXY
trades far less than the long-vol products (long share 0.5–0.97), so the share mostly tracks
long-vol attention. The COT asset-manager series nets *positions*, which volume cannot.

## 3. Attribution and gates (02_attrib_gates.py)

HAC t-stats of abnormal total ETP dollar volume on forward 21-day VIXY return, with log VIX,
lagged slope, VIX momentum and the VIXY 21-day return as controls: **IS −0.16, OOS −2.24**. The IS
effect is entirely the VIX level: volume spikes when VIX spikes, and VIXY then decays.

Pre-declared grid: short VIXY in contango (lagged slope) only when abnormal volume > θ, with
leg ∈ {long, inverse, all} × window {5, 10} × θ {0, 0.25, 0.5} = 18 rules:

| | full | IS | OOS | 2022+ |
|---|---|---|---|---|
| carry reference | 0.60 | 0.66 | 0.54 | 0.17 |
| median of 18 gates | 0.42 | 0.41 | 0.42 | −0.27 |
| best (long 10 d > 0.25) | 0.70 | 0.63 | 0.78 | 0.13 |
| 18-rule ensemble | 0.51 | 0.52 | 0.49 | −0.25 |
| standalone short on abnormal volume (no contango) | 0.37 | 0.51 | 0.25 | 0.18 |
| COT book | 1.00 | 1.04 | 0.96 | 0.38 |
| average of COT book and gate ensemble | 0.90 | 0.91 | 0.89 | 0.02 |

The gates cut exposure to 7–40 % and raise turnover to 15–26× a year. The short-vol premium is
spread across normal days too; waiting for abnormal activity misses it.

## 4. Conclusion

ETP volume measures attention, not positioning. Attention is a function of the VIX level, which
the carry rule already conditions on. The COT signal works because it nets long against inverse
holdings in open interest, and dollar volume cannot reconstruct that. Failed. The weekly COT series
stays the only positioning input.

## 5. Files

`code/vol-complex/vol-etp-flow-sentiment/`: `01_screen.py`, `02_attrib_gates.py`. No alpha spec.
