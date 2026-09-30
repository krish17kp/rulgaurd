# Cross-dataset / adaptive RUL framework

Status: implemented 2026-09-25 (branch `cross-dataset`). The numeric summaries below are historical; the generated `docs/cross-dataset-results.md` identifies its source as `reports/metrics/cross_dataset.json`. That JSON is absent in this audit worktree, so these summaries have not been revalidated here. Dataset facts and
provenance: `docs/external-datasets.md`. Design decisions: `docs/decisions.md` D23-D26.

## 1. What changed and why

### Before

```
FEMTO CSVs ── femto.py ──┐
                         ├─ pipeline.py (dataset-specific row builders) ─ features.py
college CSVs ─ college.py┘        │
                                  ├─ health.py (reference HI, FEMTO-fit)
                                  ├─ stages.py
                                  ├─ modeling.py (naive + ExtraTrees, RUL seconds)
                                  └─ evaluation.py (FEMTO LOBO, college walk-forward)
                                         └─ dashboard.py (FEMTO-gated HI/RUL tabs)
```

Two datasets, each with its own row builder and its own evaluation; the college data
could only be *gated away* from the FEMTO models (D11). There was no way to ask "is this
model applicable to that machine?", no uncertainty, and no external benchmark.

### After

```
MULTIPLE DATASETS    FEMTO | college | IMS (NASA) | XJTU-SY | unknown folder
        │
DATASET ADAPTERS     adapters.py  (femto.py, college.py, ims.py, xjtu.py stay parsing-only)
        │                        profiler.py attempts folder inspection, detects known dataset formats
CANONICAL FORMAT     BearingRun + Recording: vibration_x/_y, temperature_bearing/_ambient,
        │            sampling_rate_hz, rpm, radial_load_n, elapsed_s, role
DATA QUALITY         features.signal_quality (per recording), profiler.audit_recordings (full),
        │            routing.quality_gate
COMMON FEATURES      pipeline.canonical_feature_row - fixed 0.1 s windows at the REAL rate
        │            domain.py - self-normalised (SN) features, unit-invariant, causal
APPLICABILITY / OOD  applicability.py - robust-z kNN distance, in-domain LOBO threshold,
        │            metadata + life-time-scale checks -> HIGH / MEDIUM / LOW + reasons
HEALTH / RUL MODEL   health.py (reference HI, per-dataset reference window), stages.py,
        │            ExtraTrees: raw_seconds (frozen FEMTO) and sn_fraction (multi-dataset)
UNCERTAINTY          uncertainty.py - tree spread (diagnostic) + weighted split conformal
        │
ROUTING              routing.py - deterministic: quality -> skill -> applicability ->
        │            RUL_AVAILABLE / RUL_EXPERIMENTAL / RUL_SUPPRESSED (health always shown)
OUTPUT               scripts/analyze_dataset.py, dashboard cross-dataset analysis (currently titled "Universal Machine Analysis") and
                     "Cross-Dataset Validation" pages (dashboard_cross.py)
```

Nothing in the old path was removed. The frozen FEMTO ExtraTrees, the reference HI, the
stage thresholds, the legacy LOBO / hidden-set evaluation and the five existing dashboard
views are unchanged; `tests/test_cross_dataset.py` asserts that a FEMTO recording produces
**bit-identical** features through the new adapter path and the legacy builder (all 49
feature columns, all 7,534 learning rows checked during development).

## 2. How the datasets differ (and how each difference is handled)

| Difference | Where it bites | Handling |
|---|---|---|
| Sampling rate: 25.6 kHz (FEMTO, XJTU, college) vs 20 kHz (IMS) | FFT bins, spectral centroid, band energies | Every recording keeps its real `sampling_rate_hz`; FFT uses it (test: a 1 kHz tone reads 1 kHz at both rates). No resampling. |
| Recording length: 0.1 s / 1.024 s / 1.28 s / 78 s | kurtosis, crest factor, peak count how many impacts a window holds | Features on fixed **0.1 s windows** (FEMTO's native length), median over windows. A FEMTO acquisition is exactly one window, so legacy features are reproduced. |
| Units: g (FEMTO, XJTU), unstated (IMS, college) | absolute RMS/peak | Absolute features kept for the FEMTO model; cross-domain model uses **log-ratios to the bearing's own reference** - unit-invariant by construction (tested). |
| Load 4-5 kN vs 10-12 kN vs 26.7 kN; speed 1500-2400 rpm | absolute vibration level | Same self-normalisation; rpm/load are **metadata for applicability**, never features (they would encode dataset identity). |
| Channels: 2 accelerometers, or 1 (IMS tests 2-3); temperature only FEMTO/college | features of a missing channel | Absent channel = absent key, NaN features, `qc_*_constant = 1`; never filled. SN features average the channels that exist. Applicability reports a missing model feature and returns LOW. |
| Acquisition cadence 10 s / 1 min / 10 min / 1 h | "healthy reference window" in recordings | Per-dataset `reference_window` = (skip, n) fixed a priori from cadence (FEMTO 10/50, XJTU 2/10, IMS 10/50, college 1/5) - never from total life, which is unknown online. |
| Life scale: FEMTO 1-8 h, XJTU 0.7-42 h, college 128 h, IMS days | a tree trained on FEMTO labels cannot predict beyond ~7.8 h | Detected per recording by the **life time-scale check** (applicability.py); results also reported in life-fraction units that are comparable across scales. |
| Failure definition: 20 g (FEMTO), 10xA_h (XJTU), 85 °C + 9 m/s² (college), undocumented (IMS) | what "RUL = 0" means | One convention: RUL = time to the bearing's **last** recording, `rul_seconds = t_last - t`. Stated, not hidden: labels mean "time to end of the recorded run". |
| Censoring: FEMTO test prefixes, IMS survivors | no end of life | Role `test_censored` / `survivor`: no RUL label, never fit on (assert_no_leakage). |

## 3. Features

Existing formulas in `features.py` are reused unchanged: mean, |mean|, RMS, std, variance,
min, max, peak-to-peak, crest, shape, impulse and clearance factors, excess kurtosis,
skewness; dominant frequency, spectral centroid, spectral entropy, frequency RMS, total
spectral energy, energy fractions in 0-1 / 1-5 / 5-12.8 kHz bands; temperature
mean/min/max/std/slope. No new feature family was added: the evidence did not call for one
(section 7).

**Self-normalised features (domain.py).** Per bearing, per recording, per available
channel: amplitude/ratio features become `log(x) - median(log x over the reference window)`
(kurtosis uses `log(kurtosis + 3)`, i.e. Pearson kurtosis); fraction/signed features become
`x - median(reference)`; then averaged over channels. 14 features (`domain.SN_FEATURES`).
Properties, each tested: unit-invariant; causal (changing late recordings never changes an
earlier value); reference rows are excluded from evaluation.

## 4. Leakage controls

These controls separate fitted parameters from held-out bearings. They do not undo development-set design choices (D20) or the post-inspection amplitude-HI selection (D26).

- Splits are by **whole bearing** (`experiments._check_disjoint` raises on overlap).
- Every fitted object - model, median fill, conformal calibrator, applicability scaler and
  threshold, linear recalibration, HI anchors, stage thresholds - is fit on the training
  bearings only; `assert_no_leakage` refuses `test_censored`, `full_test`, `survivor` rows.
- Conformal calibration uses an **inner** GroupKFold over the *training* bearings; the
  held-out bearing is never a calibration row. Test: corrupting the held-out bearing's labels
  leaves every prediction and interval bit-identical.
- `NON_FEATURE_COLUMNS` now also excludes `elapsed_s`, `life_fraction`, `total_life_s`,
  `evaluable`, rpm/load/rate metadata and every `qc_*` column. Test: none of them can reach
  `candidate_feature_columns`.
- The FEMTO hidden set is scored once at its last censored recording (IEEE PHM 2012
  convention) against archive-derived RUL; nothing is fit on it.
- The CALIBRATED category uses labelled bearings of the target dataset **other than** the
  test bearing (leave-one-bearing-out inside the target).

## 5. Experiments

Categories are never mixed in one table (`docs/cross-dataset-results.md`):

| Category | Train | Test |
|---|---|---|
| WITHIN-DOMAIN | FEMTO LOBO (6); FEMTO hidden set (frozen model, 11); IMS LOBO (4 failed); XJTU LOBO (15) | the held-out bearing |
| ZERO-SHOT | all 6 FEMTO learning bearings (raw = the committed frozen model) | college, IMS, XJTU - no target labels used |
| CALIBRATED | FEMTO model + linear map on the *other* target-dataset bearings | each IMS / XJTU bearing (college has one bearing: impossible) |
| MULTI-DATASET | all run-to-failure bearings except the test one (LOBO, 26 bearings); and leave-one-domain-out | the held-out bearing / dataset |

Two model kinds: `raw_seconds` (the frozen pipeline: 44 absolute vibration features -> RUL
seconds) and `sn_fraction` (14 SN features -> life fraction -> seconds via elapsed time).
Metrics per bearing: MAE, RMSE, median AE (s), relative error, over/under-estimate counts
and %, life-fraction MAE and skill vs a constant guess, post-onset errors, coverage and width
of three interval types. Reproducible: seed 42, fixed folds, every split's train domains and
test bearings stored in `cross_dataset.json["config"]["splits"]`.

## 6. Applicability, uncertainty, routing

**Applicability** (applicability.py) answers "is this bearing like the training data?":
robust z-scores (training median/MAD), mean distance to the k=5 nearest training
recordings, divided by the largest leave-one-bearing-out distance *inside* the training set
(`shift_ratio`; 1 = as unfamiliar as the most unusual training bearing). HIGH <= 1 < MEDIUM
<= 2 < LOW. Hard reasons: a model feature unavailable (LOW); sampling rate / rpm / load
outside the training range (at most MEDIUM); the bearing has already run longer than any
training bearing's whole life (LOW for a seconds model, MEDIUM for the life-fraction model).

**Uncertainty** (uncertainty.py): (1) the spread of the 100 individual trees - reported as a
*diagnostic*, and measured to under-cover, i.e. it is **not** a calibrated confidence;
(2) split conformal intervals, normalised by tree spread and plain absolute-residual, with
each calibration bearing weighted equally and a finite-sample correction on the number of
bearings. Coverage is reported by bearing and by dataset. This weighted out-of-fold calibration is an empirical uncertainty method; a formal coverage guarantee for this implementation has not been established by this audit (D28). Exchangeability is not justified across rigs. Neither these intervals nor tree spread express the probability that a particular prediction is correct.

**Routing** (routing.py) is deterministic: quality gate -> only models with *validated
skill* (life-fraction skill > 0 in their own out-of-fold validation) are eligible -> first
eligible model with HIGH applicability gives `RUL_AVAILABLE`, MEDIUM gives
`RUL_EXPERIMENTAL`, otherwise `RUL_SUPPRESSED`. A bearing inside a model's training set is
shown its out-of-fold prediction, never an in-sample one. Health indicator, stage, signal
analysis and the reasons are shown in every case.

## 7. What the evidence says

Values below are copied from the generated `docs/cross-dataset-results.md` (run of
2026-09-25). "Skill" = life-fraction MAE improvement over a label-free constant guess
(f = 0.5); > 0 is better than the guess, 1 is perfect.

1. **Within FEMTO the frozen ExtraTrees has modest real skill.** LOBO (6 bearings): skill
   0.300, MAE 4,899.5 s vs naive 6,555.8 s on post-reference rows. Hidden set (11 bearings,
   frozen model): MAE 4,555.436 s, skill 0.174 - this is the historical "~4555 s" figure, and
   it reproduces from current code. It over-estimates on 8 of the 11 hidden bearings (72.7%).
2. **Zero-shot from FEMTO fails on the evaluated college and IMS cases.** College skill
   -0.734 and IMS -0.555 (raw model): a tree trained on <= 7.8 h lives predicts <= ~3 h for a
   128 h (college) or multi-day (IMS) run, and its conformal intervals collapse (coverage 0.073
   and 0.021). XJTU-SY, whose lives overlap FEMTO's, keeps a small positive zero-shot skill
   (0.123).
3. **Self-normalised features transfer the degradation shape, not the remaining time.** The
   SN model has no skill within FEMTO (-0.034) and none zero-shot to college (-0.593) or IMS
   (-0.690); during the long flat healthy phase nothing observable distinguishes 20% from 70%
   of life (D24).
4. **Labelled bearings of the target machine are what help.** IMS: zero-shot -0.555 ->
   CALIBRATED 0.213 -> multi-dataset LOBO 0.113 -> within-IMS LOBO 0.319 (raw). XJTU-SY:
   zero-shot 0.123 -> within 0.118 (SN) -> multi-dataset 0.142 -> CALIBRATED 0.210.
   Leave-one-*domain*-out (a machine type never seen with labels): college -0.288, FEMTO
   0.029, IMS -0.368, XJTU-SY 0.146 - mean -0.120, which is why routing treats an unseen
   machine type as having no validated skill.
5. **Applicability tracks shift, not error.** Raw model: bearing-level Spearman(shift ratio,
   life-fraction MAE) = -0.062 (no ranking), but at the decision level HIGH has median skill
   0.337 (n = 31) and LOW -0.044 (n = 22). SN model: HIGH 0.129 vs MEDIUM 0.099, Spearman
   -0.390 - self-normalisation removes the very shifts the distance measures. Post hoc (not
   used to tune anything): bearings that outlived every training life have median skill
   -0.446 (n = 10) vs 0.384 (n = 46) for the rest, raw model - the life-scale rule is the
   informative part of the gate.
6. **Uncertainty.** Conformal intervals reach roughly nominal coverage within a domain
   (absolute conformal 0.968 FEMTO LOBO, 0.946 XJTU LOBO, 0.983 IMS LOBO) and fail under shift
   (0.073 college, 0.021 IMS zero-shot, raw). The tree 5-95% spread under-covers almost
   everywhere (0.645 FEMTO LOBO): it is a diagnostic, not a confidence.
7. **Health indicator.** No single HI is best everywhere (D26): the fused SN HI is best on
   FEMTO (Spearman with elapsed -0.717), the amplitude SN HI on IMS (-0.682) and XJTU-SY
   (-0.636), and on college no HI is monotone because its vibration falls for ~120 of 128
   hours before a ~4-hour failure; there the amplitude HI works as a late-failure detector.
8. **What routing does with this** (reports/metrics/routing_*.parquet): college - RUL
   suppressed on all 129 recordings; FEMTO censored test bearings - validated raw model;
   IMS and XJTU-SY - the multi-dataset model, whose held-out skill there is positive but
   small (0.113 / 0.142) and shown next to every number; any machine type absent from
   validation - suppressed.

## 7a. College dataset: description claims checked against the data

Full audit of every sample of all 129 files (`scripts/audit_dataset.py` ->
`reports/metrics/audit_college.json`); figures in `reports/figures/college_*.png`.

| Description claim | Verified against the data |
|---|---|
| 129 hourly CSVs, 2022-06-20 17:00 -> 2022-06-26 01:00 (128 h) | 129 files, no duplicates (SHA-256), estimated missing 0; intervals 3,600 s for 124 gaps, but the last four gaps are 3,660 / 4,320 / 3,600 / 2,760 s (logging became irregular during failure); first->last start = 128 h |
| 4 columns: vibration x, y, bearing temperature, atmospheric temperature | yes, no header, every file exactly 2,000,001 rows |
| 25.6 kHz, 78.125 s per file | consistent (2,000,001 / 25,600 = 78.125 s); the rate itself cannot be measured - there is no time column |
| Sensor PCB 352C34; stop at > 85 °C bearing temperature and > 9 m/s² vibration | per-sample bearing temperature reaches 108.8 °C; \|vibration\| exceeds 9 (unit not stated in the files) only in the last 5 recordings (max 51.0 x, 44.5 y). Unit of the vibration columns remains UNVERIFIED - features used for cross-domain work are unit-invariant |
| 1770-1780 rpm constant; duty cycle "5 min operation, 15 min rest" | no recording contains a low-activity 1 s window (RMS < 20% of its median): the rest periods are not visible inside any 78 s capture |
| Data quality | every file has sensor-dropout NaN (6,400 per vibration channel, 10,537 per temperature channel in total), no Inf, no constant channel, no clipping (vibration saturation check) |

Behaviour over life (canonical features): vibration RMS drifts slowly **down** for ~120 h
(x ~0.37 -> ~0.27) while bearing temperature rises; the y channel shows level steps at ~47 h
and ~90 h that coincide with bearing-temperature steps (cause unknown - possibly a stop /
restart or load adjustment; not claimed). In the last ~4 hours RMS rises ~4-5x, temperature
passes 85 °C and reaches ~100 °C, the spectrum becomes broadband, and kurtosis / crest /
impulse factors **fall** - a non-impulsive failure signature, unlike FEMTO's. The first file's
mean bearing temperature (41.8 °C) is ~10 °C above the next two (31.7, 30.6 °C): a first-hour
anomaly, excluded from the SN reference window by `reference_window = (1, 5)`.

## 8. Examiner questions

- *Why should a FEMTO-trained model work on college data?* It should not be assumed to, and
  the zero-shot experiment shows it does not: the label range (<= 7.8 h) cannot represent a
  128 h life. The system detects this (life-scale + feature shift) and suppresses RUL.
- *How are features comparable across datasets?* Same formulas, same 0.1 s physical window,
  real sampling rate; for cross-domain use, self-normalised log-ratios that cancel a constant multiplicative scale. They do not establish invariance to arbitrary sensor response or changing load.
- *How do you know test data did not leak?* Bearing-level splits asserted; every fitted
  object fit on train bearings only; inner-fold calibration; a test that corrupts held-out
  labels and gets identical predictions; forbidden columns excluded and tested.
- *Why ExtraTrees, not an LSTM?* 6 FEMTO learning bearings, 26 run-to-failure bearings in
  total; the per-bearing sample is tiny for sequence models, and the failure mode found here
  (label time-scale, flat healthy phase) is a property of the data that a deeper model does not
  remove. ExtraTrees also gives per-tree predictions for the uncertainty diagnostic.
- *Why not retrain for every machine?* Retraining needs several labelled run-to-failure
  bearings of that machine; the college rig has one. Where several exist (XJTU, IMS), the
  WITHIN-DOMAIN and CALIBRATED results quantify what retraining buys.
- *How is the HI validated?* Monotonicity, trendability (worst bearing), prognosability and
  Spearman correlation with elapsed life and RUL, per dataset, for both the reference HI and
  the SN HI.
- *What does "applicability" mean exactly?* Distance of the bearing's recordings to the
  training recordings in robust-z units relative to the in-domain maximum, plus metadata and
  life-scale checks. It measures similarity, not accuracy; the life-scale part is what
  separates catastrophic from tolerable transfer (section 7.5).
- *How is uncertainty measured?* Conformal intervals with measured coverage; tree spread only
  as a diagnostic.
- *Completely unknown machine / no labels?* The profiler attempts structural inspection of readable files;
  without an adapter the system stops at the profile. With an adapter but no labels it gives
  health, stage and applicability; RUL only if a validated model is applicable.
- *When does it refuse?* Failed quality gate; no model with validated skill; LOW applicability.
- *Is the cross-dataset claim genuine?* Use the scoped claim below. RUL experiment categories distinguish held-out predictions; HI selection used observed learning and college behavior (D20/D26), so not every displayed statistic is independent validation.

## 9. Defensible claim

> The offline framework parses the implemented FEMTO, college, IMS and XJTU-SY formats
> and evaluates explicitly labelled within-domain and transfer experiments. Routing uses
> measured skill, data quality and similarity to suppress unsupported RUL outputs.
> Reported intervals describe empirical coverage, not guaranteed reliability on a new
> machine. The HTTP RUL/HI service remains FEMTO-only.

Not claimed: that it works on every machine or dataset; that zero-shot RUL transfers between
rigs with different life time-scales; that applicability predicts error magnitude; any fault
type diagnosis; any live or real-time deployment (all data is recorded and replayed offline).

## 10. Limitations

- One college bearing: no independent cross-bearing college validation is possible. Legacy chronological walk-forward evaluates portions of that same trajectory only; amplitude-HI selection inspected its outcome (D26).
- IMS: 4 failed bearings, one operating condition, units unstated, set 3 truncated at its
  documented end (D25); survivors carry no labels.
- Labels are "time to end of recorded run" under four different stop rules.
- Reference windows are fixed per dataset; a bearing instrumented mid-life would violate the
  "healthy reference" assumption.
- Coverage is measured empirically; exchangeability across domains and a coverage theorem for this weighted out-of-fold procedure are not established (D28).
- Applicability thresholds (1, 2) are a convention; the pre-registered policy is conservative
  (post-hoc analysis in the results document, not used to tune it).
- Stage thresholds are FEMTO-fit: before 80% of life 21-39% of recordings are already
  flagged non-HEALTHY on every dataset (D26); DEGRADING is an early flag, not a prediction.
- On college no HI is monotone over the life: vibration falls for ~120 of 128 hours before a
  ~4-hour failure; the HI is a late-failure detector there (D26).
- CWRU / Paderborn / MFPT are fault-classification datasets without degradation trajectories
  and are deliberately not used for RUL.

## 11. How to reproduce

```bash
PYTHONPATH=src python scripts/build_canonical_features.py --dataset femto --role learning
PYTHONPATH=src python scripts/build_canonical_features.py --dataset femto --role test_censored
PYTHONPATH=src python scripts/build_canonical_features.py --dataset college
PYTHONPATH=src python scripts/build_canonical_features.py --dataset ims  --root <ims root>
PYTHONPATH=src python scripts/build_canonical_features.py --dataset xjtu --root <XJTU-SY_Bearing_Datasets>
PYTHONPATH=src python scripts/audit_dataset.py --dataset college
PYTHONPATH=src python scripts/run_cross_dataset.py          # ~12 min on 12 cores
PYTHONPATH=src python scripts/analyze_dataset.py --root <any dataset folder>
PYTHONPATH=src python scripts/plot_cross_dataset.py         # reports/figures/*.png
PYTHONPATH=src python scripts/report_cross_dataset.py       # docs/cross-dataset-results.md
```

Raw external data is never placed in the repository: IMS and XJTU-SY are read from a folder
outside it (download routes and SHA-256 in `docs/external-datasets.md`); all generated
Parquet/JSON/joblib/PNG outputs are gitignored.
