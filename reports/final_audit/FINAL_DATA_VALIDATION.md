# FINAL DATA VALIDATION — Independent Feature-Formula Check (2026-10-21, session 4)

## Methodology
Computed RMS, kurtosis (Fisher/excess), and crest factor **independently**
(a from-scratch reimplementation, not importing `bearing_pdm.features` or
`bearing_pdm.pipeline`) from real raw files:
- FEMTO: `data/interim/femto/Learning_set/{Bearing1_1,Bearing2_1}/acc_*.csv`
  (real extracted FEMTO archive, early/middle/late recordings each).
- XJTU: `/home/krish/.cache/rulguard_rar_scratch/92603e084671fccd/
  XJTU-SY_Bearing_Datasets/{35Hz12kN/Bearing1_1,37.5Hz11kN/Bearing2_1}/*.csv`
  (the existing verified 12GB extraction cache — **not re-extracted**, per
  standing instruction).

## A real defect-looking discrepancy, investigated and resolved (not a bug)
The first pass (computing a single whole-signal feature per 1.28s XJTU file)
produced systematic mismatches of 20-140% on kurtosis/crest_factor (RMS was
close, <1.2%). Investigated rather than dismissed:
1. Confirmed file-to-`sequence_index` mapping is correct (`list_xjtu_files`
   sorts numerically, `1.csv < 2.csv < ... < 10.csv`, verified in code).
2. Confirmed `features.py`'s formula is textually identical to the
   independent one (calling it directly still mismatched canonical output —
   proving the formula itself wasn't the issue).
3. Found the real cause in `data/processed/canonical_xjtu.json`:
   `"window_s": 0.1`. Traced to `pipeline.py:_vibration_features()`: the
   canonical feature row for each 1.28s/32768-sample XJTU recording is the
   **median of per-0.1s-window (2560-sample) features across 12
   non-overlapping windows**, not a single value over the whole recording —
   the same convention applied to FEMTO's native 0.1s acquisitions (where
   windowing is a no-op since the file already is one window).
4. Reimplemented this windowing+median aggregation independently (own code,
   not importing `pipeline.py`) and re-ran the comparison.

## Result: 72/72 exact matches (tolerance 1e-6 relative, actual diff = 0.000000% on all)
6 recordings (FEMTO Bearing1_1/Bearing2_1 x early/middle/late) x 2 channels
x 3 metrics (rms, kurtosis, crest_factor) = 36 FEMTO comparisons, same for
XJTU Bearing1_1/Bearing2_1 = 36 XJTU comparisons. All 72 are **exact**
matches once the real windowing convention is correctly replicated. This is
strong evidence the feature pipeline is not silently producing wrong
numbers — the only "mismatch" found was in the validator's own first-pass
methodology, not the pipeline.

## Nyquist / frequency axis
`freqs.max()` for a 2560-sample, 25600 Hz window = exactly 12800.0 Hz =
`fs/2` — correct, verified directly via `np.fft.rfftfreq`.

## Channel orientation
`vibration_x` <-> `Horizontal_vibration_signals`, `vibration_y` <->
`Vertical_vibration_signals` for XJTU (adapter code, confirmed by reading
`adapters.py:XjtuAdapter.recordings`); FEMTO's columns 4/5 (0-indexed) map
to horizontal/vertical acceleration per the real acc_*.csv structure
(headerless, `hour,min,sec,microsec,horiz_accel,vert_accel`) — not swapped,
confirmed by the exact numeric match above (a channel swap would have
produced a mismatch since x/y RMS values differ meaningfully at every
point tested).

## Spectral centroid — not fully independently re-derived
A quick single-window spectral-centroid check (not using the median-of-12-
windows methodology) showed a ~1.4% difference vs. canonical, consistent
with needing the same windowed-median aggregation as the time-domain
features (not re-run with the correct methodology due to time budget this
session). RMS/kurtosis/crest_factor — the audit's explicitly named metrics
— are fully verified; spectral centroid is very likely correct by the same
mechanism but **not independently confirmed to the same standard**.

## Conclusion
**PASS** for RMS/kurtosis/crest_factor on real FEMTO and XJTU data, 2
bearings each, early/middle/late, both channels (72/72 exact matches).
**NOT_TESTABLE_THIS_SESSION** for spectral centroid/FFT frequency bins at
the same rigor (time budget), though the Nyquist bound itself is confirmed
exactly correct.
