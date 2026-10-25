\# M12-01 — Dataset Compatibility, Metadata, and Adapter System

\#\# Goal  
Build the production compatibility layer that decides whether an uploaded dataset can safely enter the prediction pipeline.

\#\# Required states  
\- FULLY\_SUPPORTED  
\- ADAPTER\_REQUIRED  
\- RETRAIN\_REQUIRED  
\- UNSUPPORTED  
\- INVALID\_INPUT

Create or strengthen canonical metadata covering file structure, sensor/channel identity, timestamps/order, sampling frequency and its source, units, acquisition length, machine/bearing metadata required by the model, adapter version, preprocessing version, feature schema version, and trained model/domain.

Rules:  
\- Parsing successfully is not equivalent to model compatibility.  
\- Never guess sampling frequency.  
\- Never silently choose ambiguous sensor columns.  
\- Missing required metadata must produce an explicit state.  
\- Structural adaptation is not predictive generalization.  
\- A different machine needing retraining must be RETRAIN\_REQUIRED.  
\- Unsupported/invalid data must fail closed before RUL inference.

Deliver:  
\- canonical metadata structure  
\- adapter registry  
\- compatibility evaluator  
\- reason codes  
\- API-safe compatibility response  
\- tests for all five states  
\- negative tests for misleading schemas, wrong units, missing/contradictory sampling metadata, and model-incompatible machines

Use an isolated worktree and a fresh independent high-end verifier.