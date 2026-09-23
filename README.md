# RULGuard - Streamlit Community Cloud deployment branch

This is a **deployment-only orphan branch**. It carries no history, no raw
datasets and no Git LFS objects - only what the hosted demo actually executes.

The research project, its full pipeline, tests, documentation and datasets live
on [`main`](https://github.com/krish17kp/rulgaurd/tree/main). Read that branch
first; nothing here should be treated as the source of truth for the science.

## Community Cloud settings

| Setting | Value |
|---|---|
| Repository | `krish17kp/rulgaurd` |
| Branch | `streamlit-cloud` |
| Main file path | `streamlit_app.py` |
| Python version | 3.12 |

## What is in here

```
streamlit_app.py     entrypoint: puts src/ on sys.path, calls the dashboard
src/bearing_pdm/     the package (dashboard + the modules it imports)
deploy_data/         ~3.5MB snapshot of real pipeline outputs
requirements.txt     runtime dependencies, pinned to verified versions
```

`deploy_data/` was produced on `main` by
`scripts/build_deploy_snapshot.py` from the project's own pipeline. It holds
three FEMTO bearings (one per operating condition) with their complete feature
history, twelve genuinely measured raw vibration windows, the fitted
health-indicator and naive models, and the evaluation metric files.

## What the hosted app is and is not

- Every number, curve and waveform is a **real** pipeline output. Nothing is
  simulated, regenerated or fabricated at page load.
- It is a **representative subset**, not the full datasets. Three of the six
  FEMTO learning bearings ship; the raw archives do not.
- The fitted ExtraTrees forest (~104 MB) exceeds GitHub's file limit and is not
  bundled. The RUL view shows that model's **leave-one-bearing-out** prediction,
  read from the evaluation artifact - out-of-sample by construction.
- No model is trained on page load. No dataset is downloaded at runtime.
- There is no backend service, API, database server, cloud component or live
  sensor feed, and no LSTM/CNN/transformer or LLM/RAG layer anywhere.
