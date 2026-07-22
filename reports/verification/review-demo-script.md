# Review Demo Script (5-8 minutes)

## 1. Problem and dataset (1 min)
"Estimate bearing Remaining Useful Life from vibration/temperature sensor data, using two datasets: FEMTO/PRONOSTIA (IEEE PHM 2012 challenge, 6 complete + 11 censored + 11 hidden bearing trajectories) and a college lab run-to-failure recording (one NSK 6205 bearing, 129 hourly files, 128 hours to failure)."

## 2. Architecture (1 min)
Show `docs/architecture.md`'s Mermaid diagram: two separate adapters normalize into one canonical feature-row contract, features go to Parquet + DuckDB lineage, then health indicator -> RUL model -> dashboard. Point out: raw high-frequency samples never touch the database (`docs/architecture.md` "why raw samples stay outside the database").

## 3. Raw signal and FFT (1 min)
Dashboard -> Signal & FFT tab. Select FEMTO, Bearing1_1, move the slider from index 0 to near the end - point out vibration amplitude visibly growing. Note the signal is re-read from the real source file on demand, not a fabricated cache.

## 4. Feature extraction (30s)
Scroll down on the same tab - show the feature table (RMS, kurtosis, spectral features) computed for the selected row.

## 5. Health indicator (1 min)
Health Indicator tab. Show the trend for Bearing1_1: near 1.0 (healthy) for most of life, sharp drop near the end. Mention two HI approaches were compared (`docs/decisions.md` D7/D8 - two real bugs found and fixed by checking against real data) and the transparent one was selected by trend correlation.

## 6. RUL prediction (1 min)
RUL Prediction tab. Show ExtraTrees vs naive prediction vs ground truth. Be upfront: this number is from the frozen pipeline (trained on all 6 bearings), so it's near-perfect on training data - the real generalization evidence is next.

## 7. Metrics (1 min)
Model Evaluation tab. Show the leave-one-bearing-out table: extra_trees beats naive on 4/6 held-out bearings (mean MAE 5061s vs 6585s). Switch dataset to college, show the walk-forward result, and proactively explain the college-naive-MAE-0.0 finding (D10) before being asked.

## 8. Limitations (1 min)
Architecture & Limitations tab. Walk through the non-claims list and the "known limitations found during development" list - frame the real bugs found (D6-D11) as evidence of a working verification process, not embarrassments.

## 9. Next steps after review (30s)
Full 129-file college processing, degradation-stage classification (M5), optional 1D-CNN-over-HI experiment (M6), RAG + local LLM reporting (M7), final reproducibility audit (M9). Reference `docs/milestone.md` for the full M0-M9 plan.
