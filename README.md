# RULGuard: Bearing Health Monitoring and Remaining Useful Life Prediction

Research capstone project. Estimates rolling-bearing degradation state and Remaining Useful Life (RUL) from vibration (+ temperature where available) sensor data, and explains predictions with evidence-grounded retrieval. **Research prototype, not a production or safety system.** The LLM/RAG layer never alters the numeric RUL prediction.

## Status (read this first)

- **Accelerated review MVP (deadline 2026-07-25): DONE.** Milestones M0-M4 plus a minimal M8 (Streamlit dashboard) are complete, each backed by a real-data run with evidence under `artifacts/evidence/REVIEW-M*/`.
- **The full M0-M9 capstone is NOT finished.** M5 (degradation-stage classification), M6 (optional 1D-CNN-over-HI), M7 (RAG/local-LLM report generation), and M9 (final reproducibility/scientific audit) are deferred, post-review work. See `docs/milestone.md` and `TODO.md` for the authoritative per-task status.
- Do not read "review-ready" as "feature-complete." It means the reviewed subset is real, tested, and honestly reported — not that every planned capability exists yet.

## Known limitations (stated up front, not buried)

1. The college dataset is a **single bearing run-to-failure trajectory** (129 hourly files, one NSK 6205 bearing). There is no cross-bearing generalization claim from it.
2. College's naive RUL baseline scores a mathematically trivial `MAE=0.0` — this is an identity of how the label is defined on an uncensored single run, **not evidence of a working predictor**. See `docs/decisions.md` D10. Only the `extra_trees` college numbers are real evidence.
3. FEMTO-trained models (fit only on the 6 FEMTO `Learning_set` bearings) are **never applied to college data** — the dashboard explicitly gates on dataset and shows a domain-mismatch message instead of a silently-wrong number (`docs/decisions.md` D11).
4. No physical fault-type diagnosis (inner/outer race, ball, lubrication) is claimed anywhere — this is RUL regression, not fault diagnosis, and bearing-frequency (BPFO/BPFI/BSF/FTF) claims require verified geometry this project does not have.
5. College feature extraction currently uses a 1-in-5 file sample (26/129 files) for the review run, not the full archive — see `reports/verification/review-readiness.md` for why and what a full run would need.
6. `Validation_Set/Full_Test_Set` (FEMTO's hidden RUL continuation) has not been scored yet — the pipeline is frozen but hidden-set evaluation is a deliberately separate later step, not skipped by accident.

## Architecture

Two independent adapters (`femto.py`, `college.py`) normalize into one canonical feature-row contract (`docs/data-contract.md`), features land in Parquet with DuckDB lineage/metadata (never raw high-frequency rows), then health indicator -> RUL model -> Streamlit dashboard. Full diagram and trust boundaries in `docs/architecture.md`.

## Install

```bash
git clone <this-repo-url>
cd rulgaurd-public   # or wherever you cloned it
pip install -e . --no-deps
pip install -r requirements.txt
# optional, only needed for the deferred M7 RAG work:
pip install -r requirements-rag.txt
```

Requires Python >=3.11 (developed on 3.13). The importable package is `bearing_pdm` (`src/bearing_pdm/`); the distribution/repo name is `rulguard` / `rulgaurd`.

### Datasets — intentionally NOT included in this repo

This is a lightweight, code-only public repo. The two raw datasets together are **~19GB** (18GB college CSVs + 1.1GB FEMTO archives), which exceeds GitHub's free 10GB/month Git LFS storage — so the full raw data is **deliberately excluded** here. Everything needed to read, understand, and re-run the methodology is included; the bulk sensor files are not. `data/fixtures/` ships tiny real excerpts (a few hundred KB) so the test suite runs with zero downloads, and `reports/figures/` + `reports/metrics/` ship the real plots/screenshots/metrics from the last verified full run so you can inspect results without regenerating them.

**1. Official dataset sources**

| Dataset | Source | Size |
|---|---|---|
| FEMTO/PRONOSTIA (IEEE PHM 2012 Prognostic Challenge) | NASA Prognostics Data Repository: `https://phm-datasets.s3.amazonaws.com/NASA/10.+FEMTO+Bearing.zip` (mirror index: [NASA PCoE Data Set Repository](https://www.nasa.gov/intelligent-systems-division/discovery-and-systems-health/pcoe/pcoe-data-set-repository/), [PHM Society mirror](https://data.phmsociety.org/nasa/)) | ~1.1GB zipped |
| College run-to-failure recording | User-collected (one NSK 6205 bearing, 128h to failure), not publicly hosted elsewhere. Contact the repo owner for access, or substitute your own run-to-failure CSVs matching the 4-column headerless schema in `docs/data-contract.md`. | ~18GB (129 CSVs) |

Cite the IEEE PHM 2012 Challenge / FEMTO-ST PRONOSTIA platform if you reuse the FEMTO data; cite this repository if you reuse the college data or the pipeline itself.

**2. Downloading and locating each dataset**

```bash
# FEMTO — download and extract the official archive
curl -o femto.zip https://phm-datasets.s3.amazonaws.com/NASA/10.+FEMTO+Bearing.zip
# unzip femto.zip into any local folder, e.g. D:\data\femto\
# inside you'll find Training_set/Learning_set, Test_set/Test_set, Validation_Set/Full_Test_Set

# College — obtain the 129 LogFile_*.csv files separately (see table above),
# place them in any local folder, e.g. D:\data\college\
```

**3. Expected local directory structure** (outside this repo — never committed here)

```
D:\data\
├── college\
│   ├── LogFile_2022-06-20-17-00-31.csv
│   ├── LogFile_2022-06-20-18-00-31.csv
│   └── ... (129 files total)
└── femto\
    ├── Training_set\Learning_set\Bearing1_1\...
    ├── Test_set\Test_set\Bearing1_3\...
    └── Validation_Set\Full_Test_Set\Bearing1_3\...
```

**4. Configuring `config/data_paths.toml`**

```bash
cp config/data_paths.example.toml config/data_paths.toml
```

Edit the copy to point at wherever you put the two datasets above, e.g.:

```toml
[college]
raw_dir = "D:/data/college"

[femto]
training_dir = "D:/data/femto/Training_set/Learning_set"
test_dir = "D:/data/femto/Test_set/Test_set"
validation_dir = "D:/data/femto/Validation_Set/Full_Test_Set"
```

`config/data_paths.toml` is gitignored — your local paths never get committed.

**5.** To repeat: **the full raw datasets are intentionally excluded from this repository** because of their combined size (~19GB) relative to GitHub's free LFS quota (10GB/month). This is a deliberate packaging decision, not a missing-data bug.

## Run

Once `config/data_paths.toml` points at downloaded datasets:

```bash
python scripts/build_features.py --dataset femto --config config/data_paths.toml
python scripts/build_features.py --dataset college --config config/data_paths.toml
python scripts/build_health.py --config config/data_paths.toml
python scripts/train_models.py --config config/data_paths.toml
python scripts/evaluate_models.py --config config/data_paths.toml
python scripts/run_dashboard.py
```

The dashboard loads cached artifacts only (Parquet feature batches + `artifacts/models/*.joblib`) — it never trains on page load. Those cached artifacts are generated locally by the commands above and are gitignored (not shipped in this repo, since they're derived from the excluded raw data). `scripts/audit_data.py` is not yet written; the M0/M1 dataset audit was done via direct inspection and is recorded in `docs/dataset-audit.md`, independently re-verified by the adapters' own tests.

**6. Running without downloading anything**

- **Tests** need no dataset download at all — they run entirely against the tiny real fixtures in `data/fixtures/`:
  ```bash
  pytest -q
  ruff check .
  ```
- **Dashboard** needs the cached Parquet/DuckDB/joblib artifacts described above, which in turn need the full datasets — there's no fixtures-only dashboard mode. If you just want to see what it produces without downloading/running anything, look at the committed cached review outputs instead:
  - `reports/figures/dashboard_*.png` — real dashboard screenshots (signal/FFT, health indicator, RUL, metrics, limits tabs, both datasets)
  - `reports/figures/hi_transparent.png`, `hi_pca.png` — health-indicator comparison plots
  - `reports/metrics/rul_evaluation.json`, `reports/metrics/health_indicator_comparison.json` — the real numeric results
  - `artifacts/evidence/REVIEW-M*/summary.md` — per-milestone evidence write-ups

## Reproducing the review results

See `reports/verification/review-readiness.md` for exact commands, environment, and the real metrics from the last verified run (FEMTO leave-one-bearing-out MAE, college walk-forward MAE, health-indicator comparison). `reports/verification/review-demo-script.md` walks through the same material as a live demo script.

## Methodology

- `docs/prd.md` — problem, goals, non-goals, explicit non-claims.
- `docs/data-contract.md` — canonical feature-row schema both adapters emit.
- `docs/architecture.md` — data flow, trust boundaries, why raw samples stay out of the database.
- `docs/dataset-audit.md` — real file inspection results (schemas, counts, hidden-RUL derivation).
- `docs/decisions.md` — every source conflict and bug found during development, with resolution and evidence, in date order (D1-D12). Read this if you want to know what actually went wrong and how it was caught.
- `docs/milestone.md` / `TODO.md` — per-milestone and per-task status, acceptance criteria, evidence pointers.

## Continuing development

Post-review work is scoped in `docs/milestone.md` (M5 stage classification, M6 optional CNN, M7 RAG/local-LLM, M9 final audit) and tracked task-by-task in `TODO.md`. `CLAUDE.md` documents the non-negotiable rules (no leakage, adapter separation, no fabricated labels/fault claims) that any new work must keep following.

## License and citation

Research/educational capstone code. FEMTO/PRONOSTIA data is the IEEE PHM 2012 Prognostic Challenge dataset — cite the challenge if you reuse it. College dataset is user-collected; cite this repository if you reuse it. No warranty; not validated for production or safety-critical use.
