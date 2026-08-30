# RULGuard — Review 2 Status
**Date:** 2026-08-30 · **Repo:** `data/rlguard` · **Last verified:** 132 tests passing, ruff clean

Every number here is read from a generated artifact (`reports/metrics/*.json`). Nothing is hand-typed.

---

## 1. Project objective
Estimate rolling-bearing degradation and **Remaining Useful Life (RUL)** from vibration and
temperature data, with an evidence-grounded explanation layer that never overrides the numeric
prediction. Research capstone, not a production system.

## 2. Overall architecture
Batch pipeline plus a local Streamlit reader. No backend service, no HTTP API, no database server.

```
raw archives → dataset adapters (femto.py / college.py, never shared)
             → canonical feature contract (docs/data-contract.md)
             → Parquet feature store + DuckDB lineage (raw rows never enter DuckDB)
             → health indicator (health.py)  →  degradation stages (stages.py)
             → RUL regression (modeling.py: naive + ExtraTrees)
             → leakage-safe evaluation (evaluation.py)
             → Streamlit dashboard (reads cached artifacts only, never fits)
```

## 3. Datasets used — never pooled
| | FEMTO / PRONOSTIA | College test rig |
|---|---|---|
| Units | 6 learning bearings + 11 censored test bearings | **1 bearing, 1 run** |
| Rows | 7,534 learning + 13,959 censored acquisitions | 129 hourly CSVs (sampled batch: 4,030 rows) |
| Label | censored (hidden continuation) | complete run |
| Role | primary evidence | real-machine offline validation only |

The two are never pooled: the RUL label is constructed differently for each (censored vs complete run).

## 4. Preprocessing
Chunked reads throughout (a full college file is ~2 M rows / ~64 MB; the full run is ~18 GB).
FEMTO uses the full 2,560-sample acquisition undivided; college uses 25,600-sample windows
(~1 s) at 50 % overlap. NaN means "not recorded" and is preserved — never globally imputed.
Columns a bearing genuinely never had (e.g. temperature on Bearing2_2/3_2) are excluded
structurally via `max_nan_fraction`, not filled.

## 5. Main extracted features
Per acquisition, per channel (x = horizontal, y = vertical):
- **Time domain:** mean, abs-mean, RMS, std, var, min, max, peak-to-peak, crest factor,
  shape factor, impulse factor, clearance factor, kurtosis, skewness
- **Frequency domain:** dominant frequency, spectral centroid, spectral entropy, frequency RMS,
  total spectral energy, low/mid/high band-energy fractions
- **Temperature:** mean, min, max, std, slope (where recorded)

## 6. Health indicator — the main work of this session
The previously selected HI was **broken**, and fixing it was the blocker for M5.

**Measured defect:** 47.5 % of all learning acquisitions pinned at exactly HI = 1.0 —
**87.4 % of Bearing3_1 and 88.9 % of Bearing3_2, both with an interquartile range of 0.00.**

**Four compounding causes** (`docs/decisions.md` D18):
1. A hard floor — `anomaly.clip(lower=0)` then `1/(1+anomaly)`, so every at-or-below-reference row → exactly 1.0.
2. A healthy reference **pooled across three operating conditions** (1800/4000, 1650/4200, 1500/5000 rpm/N). Pooled healthy `x_rms` = 0.401 while Bearing3_1/3_2 sit at ~0.31 for most of life → permanently "below reference" → pinned.
3. Feature ranking inverted by an **early-life run-in transient** (Bearing3_1 `x_rms` by decile: 0.458 → 0.324 → 0.310 → … → 0.305), which also contaminated the reference window itself.
4. Non-robust scale/fusion — pooled kurtosis std 15.34 on a mean of 2.12 (raw range 0.02–412).

**The signal was never missing; the pooled reference hid it.** Each bearing's own end-of-life
vs its own early life: RMS 1.57–4.28×, crest factor 1.44–1.86×, kurtosis 25–331×, on all six.
Yet no feature is consistently signed against a *pooled* baseline (`x_rms` Spearman +0.86 on
Bearing1_1, −0.42 on Bearing3_1).

**Fix — reference HI:** fixed physically-motivated feature set (RMS, peak-to-peak, kurtosis,
crest factor, both channels), `log1p` on kurtosis, **per-bearing healthy reference** = median of
that bearing's own acquisitions [10, 60) (fixed count + offset, not a fraction of total life),
MAD scale frozen from training bearings, trailing rolling median, and a **logistic map** onto
the open interval (0, 1) — which makes pinning structurally impossible rather than clipped away.

**Implementation diagnostics (leave-one-bearing-out calibration)** — these confirm the fix
behaved as designed, not primary validation evidence (they are close-to-guaranteed by
construction: the logistic is centred to put the healthy reference near 0.95, and is
structurally open-interval so pinning cannot occur):

| bearing | % at HI=1.0 before | after | HI in healthy window | HI at final 1 % | Spearman |
|---|---|---|---|---|---|
| Bearing1_1 | 39.0 % | **0.00 %** | 0.953 | 0.000 | −0.844 |
| Bearing1_2 | 34.0 % | **0.00 %** | 0.954 | 0.000 | −0.323 |
| Bearing2_1 | 11.4 % | **0.00 %** | 0.952 | 0.001 | −0.744 |
| Bearing2_2 | 24.5 % | **0.00 %** | 0.949 | 0.000 | −0.633 |
| Bearing3_1 | 87.4 % | **0.00 %** | 0.954 | 0.063 | −0.477 |
| Bearing3_2 | 88.9 % | **0.00 %** | 0.959 | 0.000 | −0.181 |

**Defensible comparative evidence** — mean |Spearman| and usable p05–p95 range, computed the
same way for all three HIs (`health.evaluate_hi`, `reports/metrics/health_indicator_comparison.json`;
docs/decisions.md D20 item 3, correcting an earlier apples-to-oranges comparison that mixed
Pearson for the legacy HIs with Spearman for the reference HI):

| HI | mean &#124;Spearman&#124; | usable range (p05–p95) |
|---|---|---|
| reference_hi (selected) | **0.534** | **0.776** |
| transparent_hi (legacy, rejected — pins) | 0.414 | 0.679 |
| pca_hi (legacy, rejected — collapsed range) | 0.398 | 0.106 |

Pinning went from a mean of 47.5 % to 0.00 % on every bearing, and every bearing now reaches
failure territory, including the two whose HI previously never moved at all — but the number
that actually argues reference_hi is a *better* indicator, not merely an unpinned one, is the
Spearman/usable-range table above.

**Leakage-safety:** the per-bearing reference reads only that bearing's own acquisitions 10–59
— strictly in the past, available at inference, present on all 11 censored bearings (verified:
every censored prefix starts at `sequence_index == 0`). Scale and anchors fit on training
bearings only, frozen in `ReferenceHIModel`. `rul_seconds` never read. Smoothing trailing-only,
and now sorts each bearing's rows by `sequence_index` internally rather than trusting caller
order (D20 item 4). `health_indicator` added to `NON_FEATURE_COLUMNS` so it can never become a
RUL input.

**Disclosure:** the feature set, `SKIP=10`, `N=50`, and `smooth_window=11` were chosen by
inspecting the six FEMTO learning bearings' own measured behaviour (the run-in transient, the
terminal-cliff width), not re-derived per fold. The per-fold anchors/scales above are genuinely
leave-one-bearing-out; the underlying design choices are not a fully untouched evaluation
against those six bearings. The 11 hidden/censored bearings were never used to choose any of
this (docs/decisions.md D20 item 6).

## 7. ExtraTrees RUL model
`ExtraTreesRegressor(n_estimators=100, random_state=42)` on the non-contract feature columns,
median-fill carried inside the fitted dataclass. Target `rul_seconds`. Naive baseline =
training-mean total life − elapsed. **Not retrained this session.**

## 8. Why ExtraTrees rather than an LSTM (for now)
The first objective is a *valid* baseline, not the best score. ExtraTrees is deterministic under
a fixed seed, trains in seconds so leave-one-bearing-out is cheap, needs no sequence-length or
architecture choices that would need their own validation, and its feature importances are
inspectable. Deep learning stays a **planned comparison with a stated hypothesis**, never an
automatic substitution because the data is time-series. The hidden-set diagnosis (§11) is now
the strongest argument *for* eventually trying a sequence-aware model.

## 9. Evaluation methodology
- **FEMTO: leave-one-bearing-out.** Whole bearings held out — never random row/window splits
  (consecutive windows are near-duplicates and would score near-perfectly for nothing).
- **FEMTO hidden set:** the 11 censored bearings, scored **once** after the pipeline was frozen,
  one prediction per bearing at the last acquisition of its censored prefix (n = 11, not 13,959).
  Ground truth re-derived from the archives, cross-checked against the official table.
- **College: strict chronological expanding window.** `evaluation.py` runtime-asserts
  `train.sequence_index.max() < test.sequence_index.min()`.
- **Everything fits inside the fold** — scalers, PCA, feature selection, median fills, HI
  references, stage thresholds.

## 10. Current FEMTO results

**Hidden set, 11 unseen bearings** (`reports/metrics/hidden_set_evaluation.json`).
Ground truth = the **archive-derived** variant. Bearing1_4's true RUL is genuinely ambiguous
between the official challenge table (339 s) and the archives (2,890 s), so both variants are
carried and scored (D17). Under the **official** variant the same frozen models score ExtraTrees
MAE 4,323.5 s against naive (corrected) 5,122.5 s.

**Corrected 2026-08-30 (docs/decisions.md D20 item 1):** `score_hidden_set` was passing the
naive baseline only the last row of each bearing's censored prefix, so its elapsed-time term
collapsed to 0 and every bearing got the same constant prediction. The bug made naive look far
worse than it is (originally reported: MAE 9,459.4 s, "2.08x better"). Fixed by giving the
baseline the whole chronologically-ordered prefix; only naive's numbers change below —
ExtraTrees is a row-wise predictor and was never affected (`rul_evaluation.json` reproduces
byte-identically).

| model | MAE | RMSE | mean abs %Er | PHM2012 | over-estimates |
|---|---|---|---|---|---|
| **ExtraTrees** | **4,555.4 s** | 5,388.0 s | 347.5 % | **0.0682** | 8 / 11 |
| naive (corrected) | 5,203.9 s | 5,917.9 s | 383.3 % | 0.0294 | **4 / 11** |
| ~~naive (original, bugged)~~ | ~~9,459.4 s~~ | ~~9,786.4 s~~ | ~~681.7 %~~ | ~~0.0000~~ | ~~11 / 11~~ |

**Leave-one-bearing-out, 6 learning bearings** (`reports/metrics/rul_evaluation.json`):

| held-out bearing | ExtraTrees MAE | naive MAE |
|---|---|---|
| Bearing1_1 | 8,001.8 s | 12,429.5 s |
| Bearing1_2 | 4,910.3 s | **4,616.0 s** |
| Bearing2_1 | 2,396.6 s | 4,136.0 s |
| Bearing2_2 | 2,479.1 s | 5,504.0 s |
| Bearing3_1 | 8,411.2 s | 8,888.0 s |
| Bearing3_2 | 4,167.2 s | **3,935.0 s** |
| **mean** | **5,061.0 s** | 6,584.8 s |

ExtraTrees beats naive on **4 of 6** bearings. The mean hides that it loses on two — reported.

## 11. What the results honestly mean
ExtraTrees beats the corrected naive baseline by **~1.14×** on data it has never seen (4,555.4 s
vs 5,203.9 s MAE) — a real but narrow margin, not the 2.08× originally reported before the D20
naive-baseline bug was found and fixed. It is still the first evidence the model learned
something transferable rather than memorising the learning bearings, but the margin does not
support calling ExtraTrees decisively better than naive on this benchmark.

Absolute accuracy is **poor** either way: 347 % mean absolute percent error, PHM2012 score
0.068, and **8 of 11 predictions are over-estimates — the unsafe direction** for maintenance
planning. The corrected naive baseline is actually safer by this measure: it over-estimates on
only 4 of 11.

Diagnosis: the model sees only instantaneous statistics of a single 2,560-sample acquisition,
with no notion of elapsed time or trajectory (correctly so — elapsed time is excluded to prevent
leakage). Two bearings with similar instantaneous RMS can be at very different points in their
lives, and tree ensembles cannot extrapolate outside the training target range. A formulation
limitation, not a bug.

## 12. Degradation stages (M5, new this session)
**HEALTHY / DEGRADING / CRITICAL** — a statistical alarm band on the HI plus a persistence rule.
`hi_warn` = 5th percentile over training healthy windows — a genuine fitted quantile that moves
with the data. `hi_critical` = median over training end-of-life windows, which is computed from
data but is **not** an independent fit in the same sense: the reference HI's fixed logistic
steepness pins the end-of-life score near a constant (≈0.047) regardless of the training
bearings, so `hi_critical` measures 0.0474–0.0477 across every leave-one-bearing-out fold — a
threshold derived from the score mapping's own end-of-life anchor, not two independently fitted
quantiles the way the previous wording implied (docs/decisions.md D20 item 2). A stage change is
committed only after **5 consecutive acquisitions agree**, so a single noise spike cannot trip
an alarm. `rul_seconds` is never used to fit a boundary — only afterwards to score the result.
A run with no valid HI reading (leading gap, or entirely missing) now reports `UNKNOWN`, never
silently `HEALTHY` (D20 item 5).

| bearing | HEALTHY | DEGRADING | CRITICAL | life frac at 1st CRITICAL | **RUL at 1st CRITICAL** | reversions |
|---|---|---|---|---|---|---|
| Bearing1_1 | 0.51 | 0.46 | 0.03 | 0.47 | **14,740 s** | 5 |
| Bearing1_2 | 0.22 | 0.56 | 0.22 | 0.15 | 7,430 s | 19 |
| Bearing2_1 | 0.14 | 0.84 | 0.02 | 0.94 | 550 s | 1 |
| Bearing2_2 | 0.23 | 0.65 | 0.11 | 0.55 | 3,570 s | 1 |
| Bearing3_1 | 0.56 | 0.42 | 0.02 | 0.97 | **120 s** | 8 |
| Bearing3_2 | 0.10 | 0.84 | 0.06 | 0.88 | 1,970 s | 4 |

Every bearing reaches CRITICAL before failing, but warning lead time spans two orders of
magnitude. That is the flat-then-cliff shape showing through — see §15.

**A stage is a severity band on a health indicator, not a fault diagnosis.** No inner-race /
outer-race / ball / cage / lubrication claim: bearing geometry is not verified here and
BPFO/BPFI/BSF/FTF are not derivable.

## 13. Dashboard status
Streamlit, five tabs, reads cached artifacts only — never fits a model on page load. Verified
headlessly via `AppTest` against the real artifacts, and by launching the real server (HTTP 200).
Shows: bearing/batch identity and role, signal + FFT re-read from the actual source file,
the reference HI with both legacy HIs for comparison, the **degradation stage badge** with its
fitted thresholds, ExtraTrees and naive RUL **in hours**, ground truth where it exists, and a
limitations tab that is part of the deliverable.

## 14. Real-machine / college-data status
The college rig is **one bearing, one run, one rig**. It is real-machine **offline** validation:
evidence that the pipeline runs end-to-end on real machine data. It is **not** evidence of
generalisation across machines, and it is **not** a deployment. Offline replay of recorded CSVs
is never described as "live" or "real-time".

College's `rul_seconds` uses the known final timestamp, so on an expanding window that always
starts at true t=0, the naive baseline scores **MAE = 0.0 by construction** (D10). That is an
oracle, not a predictor, and "ExtraTrees vs naive" on college is not a fair comparison.

## 15. Current limitations
- Absolute RUL accuracy is poor; 8/11 hidden-set predictions err in the **unsafe** direction.
- **FEMTO degradation is flat-then-cliff, not gradual.** Bearing3_2's `x_rms` sits at ~0.30 for
  ~95 % of life then jumps 6× inside the final ~17 acquisitions. So Bearing3_1 gets only **120 s**
  of CRITICAL warning — a property of the bearing, not a tuning choice.
- Bearing3_1's usable HI range is 0.083 for the same reason.
- Per-acquisition monotonicity is low (0.01–0.11) for every HI tried; `|mean(sign(diff))|` is
  near zero for any noisy real signal, so Spearman + healthy-vs-EOL separation are the headline
  metrics instead.
- The reference HI assumes the bearing is healthy during its own acquisitions 10–59 — true by
  construction here, but not for a bearing first instrumented mid-life.
- Single college bearing → no cross-machine claim. No fault-type diagnosis. No uncertainty
  interval on the RUL point estimate. Bearing1_4's ground truth is genuinely ambiguous (D17), so
  both variants are carried and reported.

## 16. What remains after Review 2
- **M6** — sequence-aware comparison model (CNN/LSTM) with a stated hypothesis, as a *comparison*.
- **M7** — RAG / local LLM explanation layer. The LLM never produces or adjusts a number.
- **M9** — final scientific audit.
- College-specific HI fit (now feasible for the first time, since the reference HI normalises
  each bearing against its own early life).
- The full 129-file college run (currently a 1-in-5 sample).
- Uncertainty intervals on the RUL point estimate.

---

## Verification run for this session
```
pytest -q                  →  132 passed          (was 105 before this session)
ruff check .               →  All checks passed!
scripts/build_health.py    →  reference_hi selected; transparent_hi rejected at 88.9% pinned
scripts/evaluate_models.py →  rul_evaluation.json reproduces BYTE-IDENTICALLY (sha256)
streamlit run …            →  HTTP 200, no errors
```
The byte-identical reproduction is the regression proof that the HI change did not leak into
the RUL feature matrix. ExtraTrees was not retrained.
