# FINAL RUL VALIDATION (2026-10-21)

Reproduced from `reports/metrics/rul_evaluation.json` directly — **no
model was refit this session.** This is a read-and-recompute-the-aggregate
pass over an existing, already-generated metrics file, not a fresh
evaluation run.

## FEMTO leave-one-bearing-out (6 bearings)
```
naive       mean MAE: 6584.76 s  (n=6 bearings)
extra_trees mean MAE: 5061.02 s  (n=6 bearings)
```
This reproduces the exact number already documented in
`.claude/rules/ml-data.md` ("ExtraTrees currently loses to naive on 2 of 6
FEMTO bearings") and `docs/decisions.md` — confirmed by direct recomputation,
not by trusting the doc text:

```
Bearing       naive_MAE   ET_MAE    ET beats naive?
1_1           12429.5     8001.8    True
1_2           4616.0      4910.3    False
2_1           4136.0      2396.6    True
2_2           5504.0      2479.1    True
3_1           8888.0      8411.2    True
3_2           3935.0      4167.2    False
```
ExtraTrees beats naive on **4 of 6 bearings** (loses on 1_2 and 3_2) —
matches the project's own documented honest finding exactly. Reported per
bearing, not just the mean, per `ml-data.md`'s own requirement.

## OOF / training-bearing safety (Phase 15)
Not independently re-verified this session — relied on the fact that
`femto_lobo` entries are explicitly leave-one-bearing-out (the held-out
bearing is excluded from its own training fold by construction of LOBO),
which is a property of the evaluation methodology already enforced by
`evaluation.py`'s `assert_no_leakage`, not re-derived from scratch here.

## College / hidden-set / cross-dataset metrics
Not reproduced this session (time budget). `reports/metrics/
hidden_set_evaluation.json` and `reports/metrics/cross_dataset.json` exist
but were not read and recomputed this session — remain NOT_TESTABLE_THIS_SESSION.

## Full_Test_Set (frozen hidden set) — explicitly NOT touched
No refit, no re-scoring attempt was made against `Full_Test_Set` this
session, per standing project policy (ml-data.md: "never refit against
Full_Test_Set") and the explicit instruction for this audit pass.

## SESSION 4 UPDATE: full per-bearing FEMTO LOBO table (from existing artifact, no refit)

```
bearing          model        n      MAE       medianAE   RMSE      overest%  underest%
femto:Bearing1_1 naive        2803   12429.5    14010.0    13895.5     0.1      99.9
femto:Bearing1_1 extra_trees  2803    8001.8     6651.3     9769.6    23.0      77.0
femto:Bearing1_2 naive         871    4616.0     4616.0     4616.0   100.0       0.0
femto:Bearing1_2 extra_trees   871    4910.3     4042.1     6290.6    96.3       3.7
femto:Bearing2_1 naive         911    4136.0     4136.0     4136.0   100.0       0.0
femto:Bearing2_1 extra_trees   911    2396.6     2054.8     2974.4    37.0      63.0
femto:Bearing2_2 naive         797    5504.0     5504.0     5504.0   100.0       0.0
femto:Bearing2_2 extra_trees   797    2479.1     1702.3     3523.8    88.6      11.4
femto:Bearing3_1 naive         515    8888.0     8888.0     8888.0   100.0       0.0
femto:Bearing3_1 extra_trees   515    8411.2     8249.5     8815.4   100.0       0.0
femto:Bearing3_2 naive        1637    3935.0     4576.0     4126.9     0.0     100.0
femto:Bearing3_2 extra_trees  1637    4167.2     4018.6     4801.4    53.4      46.6
```
All read directly from `reports/metrics/rul_evaluation.json` — no refit,
no recomputation of the model, only aggregation/formatting of existing
numbers. Naive's 100% (or 0%) over/under-estimate rate per bearing is
expected and explained: naive is a single constant value per held-out
bearing (predicted RUL doesn't vary within the bearing), so it is either
entirely above or entirely below the true RUL trajectory for that whole
bearing — this is a property of the naive baseline's definition, not an
error in this report.

## Prefix-invariance expanded (session 4): 3 FEMTO + 3 XJTU bearings, 3 points each
`apply_reference_hi()` on prefix vs. full trajectory, 18 points total
(Bearing1_1/2_1/3_1 for both datasets, early/middle/late): **18/18 exact
match, diff=0.00e+00 at every point.** This is the full scope requested
(>=3 FEMTO, >=3 XJTU, early/middle/late). Self-normalised features, stage,
applicability, and RUL were not separately prefix-tested (HI is the
upstream causal input to all of them; stage is a deterministic threshold
function of HI with a persistence window, so HI's causality is necessary
but not sufficient evidence for stage's — not independently re-derived
this session due to time budget).
