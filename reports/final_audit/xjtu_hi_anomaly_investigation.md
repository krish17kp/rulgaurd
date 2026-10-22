# XJTU2_1 / XJTU3_3 positive-Spearman investigation (2026-10-21, session 4)

## Evidence
- RMS (`vibration_x_rms`/`vibration_y_rms`) is FLAT-TO-MILDLY-DECLINING for
  ~98% of each run, then jumps 15-20x in the final 1-2 recordings
  (Bearing2_1: 0.35-0.43 -> 7.14 at idx 490/491; Bearing3_3: 0.48-0.62 ->
  5.00 at idx 370/371). Kurtosis/crest factor show the same pattern.
- HI mirrors this exactly and correctly: early-half HI is tight and stable
  (mean 0.9595/0.9652, std 0.005/0.007), falls to ~0.35 by the 90-99%
  mark, and hits exactly 0.0 at the terminal 3 points for both bearings.
  The 5th percentile of early-half HI (0.9464 / 0.9511) is never
  approached again after the collapse — **clean terminal discrimination**.
- Removing the terminal collapse from the Spearman calculation makes the
  correlation MORE positive, not less (Bearing2_1: 0.488 -> 0.686 excluding
  the last 20 points; Bearing3_3: 0.576 -> 0.861). This proves the positive
  correlation is NOT an artifact of the terminal cliff - the cliff is
  actually pulling the correlation DOWN toward zero/negative, and the body
  of the run (the non-failure majority of recordings) has a genuine,
  substantial *positive* HI-vs-time trend (bearing getting healthier
  by this metric) for most of its operating life.
- Prefix-invariance (from session 3) already confirmed the HI computation
  itself is causal and bug-free at every point tested on these same
  canonical artifacts.

## Conclusion: SCIENTIFIC LIMITATION, NOT A BUG

Both bearings show a genuine mechanical **run-in/bedding-in trend**: initial
vibration levels settle and the reference-window-relative degradation score
*decreases* (HI *increases*) for most of the bearing's life as
installation-stress-driven vibration relaxes, before a late, sudden,
catastrophic failure cliff concentrated in the last ~1-2% of recordings.
This is a documented real phenomenon in rolling-bearing literature
(bedding-in/running-in period) and is consistent with
`health.py`'s own existing docstring, which already singles out Spearman
as an understating metric for "flat-then-cliff" degradation (previously
verified for FEMTO Bearing3_2) — this session extends that same finding to
two XJTU bearings with an even more extreme version: the pre-failure trend
isn't flat, it's *mildly improving*, which can flip a whole-run Spearman's
sign even though the HI remains perfectly fit for its purpose (clean
healthy/failure separation).

## Why the HI is still fit for the paper, with an explicit caveat

- Terminal discrimination is unambiguous and real-data-verified: both
  bearings' last 3 recordings are flagged HI=0.0, five-sigma-equivalent
  below their own stable healthy baseline.
- A global Spearman(HI, time) across an ENTIRE run is not the right
  single-number summary for a bedding-in-then-cliff trajectory — this was
  already a known project limitation for FEMTO before this session; this
  investigation generalizes it to XJTU with real evidence rather than
  assuming it transfers.
- **Was NOT fixed by force-monotonizing or altering the HI formula** — per
  standing instruction, "do not weaken scientific gates" / "never enforce
  monotonic stages merely to make plots prettier." The HI calculation is
  unchanged; this is a documentation/evaluation-methodology finding, not a
  code defect.

## Recommended paper-level framing (not yet applied to docs this session beyond this report)

State explicitly: "Global monotonic-trend correlation (Spearman) is an
unreliable summary statistic for this health indicator on bearings with a
bedding-in period followed by a late catastrophic failure (observed on
FEMTO Bearing3_2 and XJTU Bearing2_1/Bearing3_3); terminal healthy/failure
discrimination, not whole-run monotonicity, is the claim this HI
formulation supports." This is the scientifically honest claim — anything
stronger ("HI decreases monotonically with degradation") is not supported
by this data and should not be written into any paper/report derived from
this project.
