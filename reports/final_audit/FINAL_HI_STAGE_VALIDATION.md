# FINAL HI/STAGE VALIDATION (2026-10-21)

All numbers below were computed by calling the real, already-fitted
`ReferenceHIModel` (`artifacts/models/reference_hi_model.joblib`) via
`apply_reference_hi()` against real canonical Parquet (`data/processed/
canonical_femto_learning.parquet`, `data/processed/canonical_xjtu.parquet`).
**Nothing was refit.** No `.fit()` call was made this session on any model.

## Prefix-invariance test (Phase 10) — PASS
For FEMTO `Bearing1_1` (n=2803) and XJTU `Bearing1_1` (n=123), HI was
computed on (a) the full trajectory and (b) a prefix truncated at t, at
three t values each past the per-bearing reference window. Result: **exact
byte-identical match (diff=0.00e+00) at every t tested**, confirming the HI
computation is causal by construction — a later recording never changes an
earlier recording's HI. This matches the code comment in `health.py`
("TRAILING rolling median per bearing. Trailing and uncentred by design").

```
FEMTO Bearing1_1: t=110  full=0.969309 prefix=0.969309 diff=0.00e+00 MATCH
                  t=1401 full=0.955408 prefix=0.955408 diff=0.00e+00 MATCH
                  t=2102 full=0.730697 prefix=0.730697 diff=0.00e+00 MATCH
XJTU  Bearing1_1: t=70   full=0.939249 prefix=0.939249 diff=0.00e+00 MATCH
                  t=61   full=0.958380 prefix=0.958380 diff=0.00e+00 MATCH
                  t=98   full=0.000312 prefix=0.000312 diff=0.00e+00 MATCH
```

Only HI was prefix-tested this session (not self-normalised features or
stage directly — stage is a deterministic threshold function of HI with
persistence, so causality of HI implies causality of stage up to the
persistence window, but this was not independently re-derived this
session).

## HI statistics per bearing (FEMTO learning set, 6 bearings)
```
Bearing      n     hi_first hi_10%  hi_50%  hi_90%  hi_last    spearman  reversion_events(>0.01 jump)
1_1          2803  0.9606   0.9638  0.9554  0.4146  0.000000   -0.838    258
1_2          871   0.9273   0.9477  0.7528  0.8588  0.000008   -0.327    148
2_1          911   0.9624   0.9685  0.7548  0.5700  0.000001   -0.779    147
2_2          797   0.9753   0.9567  0.1890  0.4640  0.000002   -0.643    82
3_1          515   0.9560   0.9540  0.9300  0.9211  0.049246   -0.470    33
3_2          1637  0.9819   0.8422  0.8989  0.0120  0.000001   -0.152    225
```
All 6 FEMTO bearings reach a near-zero terminal HI and all 6 have a
negative Spearman(HI, sequence_index) as expected for degradation — this
is **data-driven**, not a structural floor: the model is a logistic map
strictly in the open interval (0,1) (per `apply_reference_hi`'s own
docstring: "pinning is structurally impossible rather than clipped away"),
so a terminal value of 0.000000...1 reflects the actual degradation score
being far past the fitted failure anchor, not a hardcoded 0.

## XJTU: 2 of 15 bearings show POSITIVE Spearman correlation — flagged, not fixed
```
xjtu:Bearing2_1: spearman=+0.488, hi_first=0.9471, hi_last=0.000000
xjtu:Bearing3_3: spearman=+0.576, hi_first=0.9716, hi_last=0.000000
```
Both bearings still end near zero (consistent with run-to-failure), but
their HI trajectory is not monotonically decreasing overall — Spearman
over the whole run is positive, meaning there's a meaningful HI increase
somewhere before the terminal collapse. **This was not root-caused this
session** (would require inspecting the raw signal and feature trajectory
for these two bearings specifically — out of time budget this session).
Per the audit's own instruction ("do not conclude the HI is invalid
without investigation" / "do not enforce monotonicity merely to make plots
prettier"), this is reported as an observed anomaly requiring follow-up,
not silently hidden and not treated as a defect to "fix" by force-monotonizing.

The FEMTO Bearing1_2 "DEGRADING-then-HEALTHY" anomaly named in the audit
prompt was **not independently re-investigated this session** — out of
time budget. `hi_10%=0.9477` for Bearing1_2 is higher than `hi_first=0.9273`,
consistent with the described pattern (a run-in transient before the
true healthy reference stabilizes), but the root cause was not traced
through `_per_bearing_reference`'s reference-window selection this session.

## XJTU RUL suppression correctness (Phase 16) — CORRECT, not a bug
All 15/15 XJTU bearings have `status=RUL_SUPPRESSED` in
`reports/metrics/routing_xjtu.json`. Inspected `xjtu:Bearing1_1`'s full
decision record directly:

```
raw_seconds candidate:      applicability=LOW  (shift_ratio=2.09x), validated_skill=-0.644 (zero-shot)
sn_fraction_multi candidate: applicability=HIGH (shift_ratio=0.47x), validated_skill=-0.222 (multi-dataset LOBO)
-> both candidates ineligible: "not eligible - no validated skill over the baseline"
```

This is the exact scenario the audit prompt named as needing verification:
`sn_fraction_multi` has **HIGH applicability** but is still correctly
suppressed because its **validated held-out skill is negative** (worse
than a constant guess) — applicability alone does not establish predictive
skill, and the routing logic correctly gates on skill, not just
applicability. Confirmed by reading one real decision record directly, not
by trusting the suppression label. This gate (K in the audit's list) is
**CORRECT**, already explained in `status_banner()`'s UI text
(`dashboard_cross.py`), and visible in the real browser screenshot
`artifacts/evidence/final_publication_audit/xjtu_08_rul.png`.

## What remains (Phase 11-17 full scope)
- IMS bearing statistics not computed this session (IMS canonical artifact
  exists but was not analyzed this session for time reasons).
- HI ablation/sanity tests against controlled signal perturbations (Phase
  12) were not run this session.
- Uncertainty/conformal interval audit (Phase 18) was not run this session.
- Root cause of the 2 XJTU positive-Spearman bearings and the FEMTO
  Bearing1_2 early reversion remain open — flagged above for follow-up,
  not silently resolved.

## SESSION 4 UPDATE — XJTU anomaly resolved

The two XJTU bearings flagged above (Bearing2_1, Bearing3_3, positive
Spearman correlation) were investigated to a confirmed root cause: a real
mechanical bedding-in/running-in trend during the body of each run, not a
code bug, not an artifact of the terminal failure collapse (excluding the
terminal points makes the positive correlation STRONGER: 0.488->0.686 for
Bearing2_1, 0.576->0.861 for Bearing3_3). Terminal healthy/failure
discrimination remains clean and data-driven for both bearings. Not
force-fixed; not monotonized. Full evidence in
`xjtu_hi_anomaly_investigation.md`. Paper-level claims must state that
whole-run Spearman is an unreliable summary statistic for this HI on
bearings with a bedding-in phase, and that terminal discrimination — not
whole-run monotonicity — is the claim this HI formulation supports.
