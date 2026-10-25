\# M12-02 — Complete Raw Dataset → RUL Production Pipeline

\#\# Goal  
A user uploads a supported raw sensor dataset and receives a real predictive-maintenance result without manually creating a feature table.

\#\# Required pipeline  
Raw dataset/reference → inspect → metadata → compatibility → validation → preprocessing → segmentation/windowing → statistical/time-domain features → frequency/FFT features where valid → Health Indicator → model routing → RUL → diagnostics → structured result

\#\# Rules  
\- Reuse validated project modules.  
\- Preserve temporal ordering.  
\- Chunking is a memory strategy, not permission to drop rows.  
\- Reuse training-time preprocessing/scaler/PCA artifacts where required.  
\- Never fit inference-time transforms on uploaded prediction data unless the methodology explicitly requires it.  
\- Reject incomplete acquisitions when required.  
\- Fail closed on incompatibility.  
\- The explanation/LLM layer must not alter numerical RUL.

\#\# Result provenance  
Return compatibility state, adapter/version, preprocessing version, feature schema, model/version, RUL \+ units, HI/degradation, warnings, and relevant diagnostics.

\#\# Required black-box test  
Use a real supported raw fixture:  
raw CSV/files → real production pipeline → preprocessing → features → HI → real model → RUL.

No manually supplied pre-extracted feature dataframe is allowed in this acceptance test.

Compare against the trusted offline/reference output within defined tolerance.

Independent verifier must also test malformed, missing-sample-rate, incompatible, and incomplete acquisitions and prove none return a normal-looking prediction.