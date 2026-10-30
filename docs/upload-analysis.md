# Upload analysis: health reliability and RUL learned from the uploaded dataset

What forevue.tech computes for a dataset uploaded through the Upload page, and when it
withholds a result. Code: `src/bearing_pdm/dataset_jobs.py`, `health.py`
(`health_quality`), `upload_rul.py` (`dataset_rul`). Decision record: D32.

## Which files can be read

- Known datasets (FEMTO, XJTU-SY, IMS, college) are recognised automatically.
- Any other dataset: CSV or text tables, MATLAB `.mat` files (every numeric vector or
  narrow matrix becomes a column; scalars such as an RPM are not signals) and `.wav`
  files (one column per channel). One folder per bearing, one file per recording,
  recordings in natural file-name order.
- An unknown dataset is not analysed until the user confirms which columns are vibration,
  the sampling rate (read from a time column or a `.wav` header, otherwise entered by the
  user, never assumed) and the time between recordings.
- MATLAB v7.3 (HDF5) files cannot be read and are reported as such.

## What every analysed upload gets

Health indicator and degradation stage per recording, from the cross-domain amplitude
health indicator (self-normalised RMS and peak-to-peak, fit on the FEMTO learning set only,
D26). The stage is a severity band on the HI, not a fault diagnosis.

**How reliable is the health rating.** Rated from the uploaded trajectories themselves:
the mean over bearings of the trend `-Spearman(HI, elapsed time)`. Strong from 0.7,
moderate from 0.4, otherwise weak. The thresholds were fixed before any upload was seen.
The mean is used, not the median, so a bearing whose health rises over time lowers the
rating instead of being hidden, and every such bearing is named. Smoothness is the
monotonicity of the HI. Agreement at failure (prognosability, Coble and Hines 2009) is
reported only when every bearing's end of life is known. Without known failure points
the accuracy of the HI cannot be measured, only its consistency. A bearing needs at
least 10 recordings to be rated.

On the deployed routing trajectories: XJTU-SY 0.64 (moderate), FEMTO learning set 0.26
(weak).

## When RUL is shown

RUL (remaining useful life) is the time left before a bearing fails. RUL accuracy is the
error of that prediction against the real failure time, so it can only be measured on
bearings that ran until they failed.

The FEMTO-trained models are not applied to other machines without held-out evidence:
a different rig's vibration differs even when healthy (feature shift up to 7x on
XJTU-SY), so their RUL would look precise and mean nothing.

Instead, for an upload whose bearings ran to failure, RUL is learned and tested on that
dataset alone:

1. Run-to-failure bearings are taken from the adapter for known datasets. For a custom
   dataset only the user's confirmation makes a bearing run-to-failure, because nothing
   in the files says it failed; the last recording is then its failure point.
2. At least 3 such bearings are needed: one is held out while the model learns from the
   others and is calibrated on them.
3. The model is fixed in advance: ExtraTrees on the primary pipeline's feature columns,
   predicting RUL in seconds. Channels the dataset lacks are dropped.
4. Leave-one-bearing-out: each bearing is predicted by a model trained only on the other
   bearings. The held-out bearing never touches the model, the conformal interval
   calibration or the applicability fit.
5. RUL is shown only when the held-out MAE, averaged over bearings, beats the naive
   baseline (mean life of the training bearings minus elapsed time). Otherwise it is
   withheld and the reason is stated.

Reported: average error (MAE), the naive baseline's error, improvement over it, how
often the true remaining life fell inside the 90% conformal range, and the error per
held-out bearing. Every RUL value shown is a held-out prediction: no bearing is
predicted by a model that saw it.

A bearing marked as failed whose last recording is still HEALTHY is flagged, because it
may not have failed.

Checked on cached real features: XJTU-SY, 15 bearings, MAE 22,283 s vs naive 32,456 s
(the published within-domain result, reproduced exactly); FEMTO learning set, 6
bearings, MAE 4,900 s vs naive 6,556 s.

## What is never done

- No RUL from a dataset without known failures.
- No refit of the frozen FEMTO models or the reference HI, and nothing is fit on the
  FEMTO `Full_Test_Set`.
- No fault-type claim (inner race, outer race, ball): no upload carries fault labels.
- The explanation assistant never changes a number: an online answer containing a
  number found neither in the model result nor in the cited evidence is replaced by the
  deterministic template answer.
