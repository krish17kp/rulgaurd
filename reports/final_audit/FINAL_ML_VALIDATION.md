# FINAL ML VALIDATION (2026-10-21, session 4)

Consolidates ML-specific findings from FINAL_HI_STAGE_VALIDATION.md,
FINAL_RUL_VALIDATION.md, and xjtu_hi_anomaly_investigation.md.

## Leakage
`assert_no_leakage` read directly (not re-derived from scratch): enforced
for FEMTO (`allowed_roles={"learning"}`) and college
(`allowed_roles={"college_run"}`). FEMTO LOBO evaluation holds out whole
bearings (`held_out_bearing` field in `rul_evaluation.json` — a given
bearing's rows never appear in its own training fold by construction of
leave-one-bearing-out). `Full_Test_Set` was not touched, queried for
refit, or scored this session.

## Causality (prefix-invariance)
18/18 exact matches across 6 bearings (3 FEMTO, 3 XJTU), early/middle/late
points. See FINAL_HI_STAGE_VALIDATION.md / FINAL_RUL_VALIDATION.md.

## Feature correctness
72/72 exact independent-formula matches (RMS, kurtosis, crest_factor) on
real FEMTO and XJTU raw data, 2 bearings each dataset, early/middle/late,
both channels. See FINAL_DATA_VALIDATION.md. A genuine-looking discrepancy
was investigated to a confirmed root cause (windowed-median aggregation,
`window_s=0.1`) rather than dismissed or silently corrected.

## HI scientific validity
Terminal healthy/failure discrimination confirmed data-driven (not a
structural floor) for all 6 FEMTO + 15 XJTU bearings. Two XJTU bearings
show a real, investigated, documented limitation (bedding-in trend
dominating whole-run Spearman) — not a bug, not force-fixed. See
xjtu_hi_anomaly_investigation.md.

## RUL
FEMTO LOBO mean MAE (naive 6584.76s vs. ET 5061.02s) and full per-bearing
table reproduced exactly from `reports/metrics/rul_evaluation.json`. ET
beats naive on 4/6 bearings, loses on 2/6 — reported honestly, matching
the project's own prior documented finding. College/hidden-set/
cross-dataset RUL metrics were NOT reproduced this session
(NOT_TESTABLE_THIS_SESSION).

## XJTU RUL suppression
Confirmed correct, not a bug: `xjtu:Bearing1_1`'s `sn_fraction_multi`
candidate has HIGH applicability (0.47x shift) but negative validated
skill (-0.222) over multi-dataset leave-one-domain-out evaluation — "high
applicability" and "validated predictive skill" are different gates, and
the system correctly requires both.
