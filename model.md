# model.md

> Single source of truth for model selection in this predictive-maintenance project.
> Read this file before choosing an AI coding model, scientific ML model, or RUL prediction approach.
> Last verified for coding-model availability: 2026-09-27.

## 1. Global Rules

1. Use the cheapest/fastest model that can reliably complete the task, but never trade away scientific correctness for cost.
2. Default coding work must use a strong general implementation model. Escalate only when the task is genuinely difficult.
3. Do not use an LLM to numerically predict Remaining Useful Life (RUL). RUL must come from the validated ML pipeline.
4. LLMs may inspect code, orchestrate workflows, explain model outputs, generate reports, and help with diagnostics.
5. Never change the scientific prediction pipeline only because a model suggests a "better" algorithm. Any scientific change requires evidence, tests, and a benchmark against the current baseline.
6. Never evaluate RUL models using random row-level train/test splitting when rows from the same bearing/run can leak across splits. Split/group by bearing/run/condition.
7. Never claim that an arbitrary uploaded dataset is supported. Run the compatibility gate first.
8. Never fabricate sampling frequency, sensor meaning, units, bearing metadata, or RUL labels. If missing and required, mark the dataset as requiring metadata/adaptation.
9. Preserve reproducibility: fixed random seeds, versioned configs, saved metrics, saved model artifacts, and logged dataset versions.
10. Any task touching prediction logic, feature definitions, RUL labels, health-indicator logic, dataset adapters, or evaluation metrics is a SCIENTIFIC task and gets a stronger reasoning model plus mandatory review.
11. Any task touching deployment, authentication, secrets, upload security, model loading, or production data paths is a PRODUCTION task and requires tests before merge.
12. Any overnight autonomous task must work in an isolated branch/worktree and must not directly overwrite stable code.
13. After every meaningful change, run the smallest relevant test set. Before merge, run the full project test suite.
14. When a task fails twice with the default model, escalate to the stronger model rather than repeatedly retrying the same approach.
15. Keep model choice visible in task notes or overnight reports.

---

# 2. AI Coding Model Router

## 2.1 Claude Code

### Claude Sonnet 5 — DEFAULT CLAUDE MODEL
Use for:
- Normal feature implementation.
- Next.js/React frontend development.
- FastAPI/backend implementation.
- API integration.
- Data validation code.
- Dataset adapters when the scientific rules are already defined.
- Test creation.
- Refactoring.
- Bug fixes with a reasonably clear root cause.
- CI/CD work.
- Docker/configuration.
- Documentation tied directly to implemented code.
- Routine repository exploration followed by implementation.
- Most overnight worker tasks.

Recommended settings:
- Model: `claude-sonnet-5`
- Thinking: use the model's current adaptive/default thinking behavior.
- Effort: medium for routine work, high for complicated implementation.
- Do not manually force old-style thinking-token budgets on current models.
- Do not set deprecated sampling controls unless current Anthropic documentation explicitly supports them.

Do NOT automatically escalate to Opus just because the task is large. Use Opus when the task is ambiguous, scientifically risky, architecturally difficult, or repeatedly failing.

### Claude Opus 5 — HARD PROBLEMS / ARCHITECTURE / SCIENTIFIC REVIEW
Use for:
- Designing the complete production architecture.
- Deciding boundaries between frontend, backend, model service, storage, and job processing.
- Dataset-generalization architecture.
- Cross-machine compatibility rules.
- RUL-label methodology.
- Health Indicator methodology changes.
- Feature-engineering changes that could alter scientific results.
- Evaluation methodology and leakage prevention.
- Investigating unexplained model-regression failures.
- Debugging failures spanning many modules.
- Reviewing large refactors before merge.
- Resolving complicated merge conflicts where scientific behavior may change.
- Planning high-risk migrations.
- Reviewing whether a result is scientifically defensible.
- Final overnight integration review.
- Tasks that Sonnet has attempted twice without a reliable solution.

Recommended settings:
- Model: `claude-opus-5`
- Thinking: adaptive/default.
- Effort: high normally.
- Effort: max only for genuinely difficult architecture/scientific investigations.
- Prefer one careful Opus pass over many blind retries.

### Claude Haiku 4.5 — FAST / CHEAP / REPETITIVE
Use for:
- Searching the repository for files/symbols.
- Summarizing logs.
- Categorizing test failures after the failures are already understood.
- Simple renames.
- Mechanical documentation cleanup.
- Generating repetitive test cases from an established pattern.
- Formatting JSON/YAML/Markdown.
- Checking lists of files for obvious consistency problems.
- Small lint fixes.
- Basic status extraction.
- Low-risk overnight housekeeping.

Recommended settings:
- Model: `claude-haiku-4-5`
- Keep instructions narrow and explicit.
- Do not give Haiku ownership of scientific architecture or ambiguous multi-module redesigns.

Do NOT use Haiku for:
- RUL model selection.
- Feature-engineering decisions.
- Health Indicator redesign.
- Cross-dataset generalization logic.
- Complex debugging.
- Architecture.
- Security-sensitive production changes.
- Final merge decisions.

---

## 2.2 Codex / OpenAI Coding Models

### GPT-6 Sol — DEFAULT OPENAI/CODEX WORKER
Use for:
- Most coding tasks in Codex.
- Repository-wide implementation.
- Backend/frontend features.
- Multi-file refactors.
- Agentic workflows using shell/tools.
- Test-driven fixes.
- Deployment configuration.
- Building adapters from an already approved specification.
- Long implementation sessions where strong coding plus tool use are needed.
- Overnight worker agents.

Recommended settings:
- Model: `gpt-6-sol`
- Reasoning effort: `medium` by default.
- Use `high` for complex implementation/debugging.
- Use `xhigh` only when the problem remains unresolved after a serious attempt.
- Use `max` only for exceptional, high-value tasks where latency/cost is acceptable.
- Prefer Responses-style tool use when available.

### GPT-6 Astra — HARDEST OPENAI REASONING
Use for:
- End-to-end architecture decisions.
- Scientific methodology review.
- Dataset-generalization strategy.
- Hardest debugging tasks.
- Cross-system failures involving ML + API + frontend + deployment.
- High-risk model/evaluation changes.
- Final review of a large overnight batch.
- Cases where GPT-6 Sol has failed twice or produced contradictory explanations.

Recommended settings:
- Model: `gpt-6-astra`
- Reasoning effort: `high` for most escalated tasks.
- Use `xhigh`/`max` for the hardest investigations.
- Do not spend Astra on routine formatting, file search, simple CRUD, or obvious lint fixes.

### GPT-6 Luna — FAST / HIGH-VOLUME OPENAI WORKER
Use for:
- Simple repo searches.
- Small deterministic transformations.
- Log summarization.
- Generating repetitive boilerplate from an approved template.
- Simple documentation synchronization.
- Low-risk classification of files/tasks.
- Cheap parallel overnight sub-tasks.
- Straightforward test-data generation.

Recommended settings:
- Model: `gpt-6-luna`
- Reasoning effort: `none` or `low` for mechanical work.
- `medium` only when necessary.

Do NOT use Luna for:
- Scientific model choices.
- RUL methodology.
- Dataset-compatibility decisions.
- Complex architecture.
- Security-sensitive production design.
- Hard debugging.

### GPT-5.3-Codex — CODEX-SPECIALIZED FALLBACK / LONG-RUN CODING
Use when:
- The environment specifically exposes `gpt-5.3-codex`.
- A Codex-specific agentic workflow performs better with the coding-tuned model.
- Long-running code modification is more important than broad research/reasoning.
- GPT-6 models are unavailable in the current Codex environment.

Recommended settings:
- Model: `gpt-5.3-codex`
- Reasoning effort: `medium` default.
- `high` for difficult coding.
- `xhigh` for the hardest coding/debugging work.

### OpenAI fallback order
If preferred models are unavailable:
1. `gpt-6-sol`
2. `gpt-5.3-codex`
3. `gpt-5.6-sol`
4. Use another available strong coding model only after recording the substitution.

---

# 3. Task-to-AI-Model Routing Table

| Task | Claude | Codex/OpenAI | Reasoning |
|---|---|---|---|
| Quick repo scan | Haiku 4.5 | GPT-6 Luna | low |
| Full repo status reconstruction | Sonnet 5 | GPT-6 Sol | medium/high |
| Architecture planning | Opus 5 | GPT-6 Astra | high |
| Frontend component implementation | Sonnet 5 | GPT-6 Sol | medium |
| High-end UI redesign | Sonnet 5, Opus review if needed | GPT-6 Sol, Astra review if needed | medium/high |
| FastAPI endpoint implementation | Sonnet 5 | GPT-6 Sol | medium |
| Upload pipeline | Sonnet 5 | GPT-6 Sol | medium |
| Dataset schema inference | Sonnet 5 | GPT-6 Sol | high |
| Scientific dataset compatibility rules | Opus 5 | GPT-6 Astra | high |
| New dataset adapter | Sonnet 5 after rules approved | GPT-6 Sol after rules approved | medium/high |
| FFT/feature extraction implementation | Sonnet 5 | GPT-6 Sol | high |
| Change FFT/feature definitions | Opus 5 | GPT-6 Astra | high |
| Health Indicator implementation from approved spec | Sonnet 5 | GPT-6 Sol | high |
| Health Indicator methodology change | Opus 5 | GPT-6 Astra | high/max |
| RUL-label logic change | Opus 5 | GPT-6 Astra | high/max |
| ExtraTrees implementation/tuning harness | Sonnet 5 | GPT-6 Sol | medium/high |
| Decide whether to replace ExtraTrees | Opus 5 | GPT-6 Astra | high |
| LSTM/CNN research benchmark | Opus plan + Sonnet implementation | Astra plan + Sol implementation | high |
| Cross-bearing evaluation | Opus review | Astra review | high |
| SHAP/explainability implementation | Sonnet 5 | GPT-6 Sol | medium |
| LLM/RAG explanation layer | Sonnet 5 | GPT-6 Sol | medium/high |
| Simple unit tests | Haiku/Sonnet | Luna/Sol | low/medium |
| Scientific regression tests | Sonnet + Opus review | Sol + Astra review | high |
| Debug simple failing test | Sonnet 5 | GPT-6 Sol | medium |
| Debug unknown multi-module regression | Opus 5 | GPT-6 Astra | high |
| Docker/container work | Sonnet 5 | GPT-6 Sol | medium |
| Vercel frontend deployment | Sonnet 5 | GPT-6 Sol | medium |
| ML backend deployment | Sonnet 5 | GPT-6 Sol | medium/high |
| Security/secret review | Opus 5 | GPT-6 Astra | high |
| CI/CD | Sonnet 5 | GPT-6 Sol | medium |
| Large merge/conflict review | Opus 5 | GPT-6 Astra | high |
| Markdown/docs cleanup | Haiku 4.5 | GPT-6 Luna | low |
| Final release readiness review | Opus 5 | GPT-6 Astra | high |
| Overnight orchestrator | Sonnet 5 normally | GPT-6 Sol normally | medium/high |
| Overnight final integrator | Opus 5 | GPT-6 Astra | high |

---

# 4. Scientific Prediction Model Policy

## 4.1 Production RUL Model

### Primary model: ExtraTreesRegressor
Status:
- Keep ExtraTrees as the current primary RUL regression model until a challenger beats it under the same leakage-safe evaluation.
- Do not replace it merely because LSTM/CNN is more fashionable.
- Tree ensembles are appropriate for engineered vibration/health features and are computationally practical for deployment.

Primary objective:
- Predict RUL in seconds or the project's canonical RUL unit.
- Optimize MAE first.
- Track RMSE and error distribution as secondary metrics.
- Track signed error because consistent overestimation of RUL is operationally important.

Recommended baseline configuration:
```python
ExtraTreesRegressor(
    n_estimators=500,
    max_features=1.0,
    max_depth=None,
    min_samples_split=2,
    min_samples_leaf=1,
    bootstrap=False,
    random_state=42,
    n_jobs=-1,
)
```

This is a starting configuration, not a scientifically guaranteed optimum.

Recommended tuning search space:
```text
n_estimators:        300, 500, 800, 1200
max_features:        0.5, 0.75, 1.0, "sqrt"
max_depth:           None, 12, 20, 32
min_samples_split:   2, 4, 8
min_samples_leaf:    1, 2, 4, 8
bootstrap:           False, True
criterion:           "squared_error"
random_state:        42
n_jobs:              -1
```

Tuning policy:
- Prefer RandomizedSearchCV or Optuna over a massive grid.
- Start with 40–80 trials.
- Use group-aware validation by bearing/run.
- Primary score: MAE.
- Never tune on the held-out final test bearings.
- Save best parameters to versioned config.
- Re-run all baselines after any feature-set change.

---

## 4.2 Mandatory Baselines

Every major RUL experiment should compare against:

### Naive baseline
Use:
- Mean/median RUL baseline or the project's existing naive degradation baseline.
Purpose:
- Proves the ML system adds value.

### Linear/Ridge regression
Suggested tuning:
```text
alpha for Ridge: 0.01, 0.1, 1, 10, 100
```
Purpose:
- Checks whether the problem is mostly linear.

### RandomForestRegressor
Suggested search:
```text
n_estimators:      300, 500, 800
max_depth:         None, 12, 20, 32
max_features:      "sqrt", 0.5, 1.0
min_samples_leaf:  1, 2, 4
```

### HistGradientBoostingRegressor or XGBoost
Use only if dependencies and deployment constraints allow it.

Suggested starting search for gradient boosting:
```text
learning_rate:     0.02, 0.05, 0.1
max_depth:         3, 5, 7
n_estimators:      200, 500, 800
subsample:         0.7, 0.9, 1.0
```

Do not add a model to production merely because it wins on one split.

---

# 5. Deep-Learning Models

## 5.1 LSTM
Status:
- Research/challenger model, not production default.
- Use only when sequential windows contain information that engineered features + ExtraTrees do not capture.
- Must beat ExtraTrees under identical bearing-level evaluation before promotion.

Suggested starting configuration:
```text
sequence_length:   10, 20, 30
LSTM layers:       1 or 2
hidden units:      32, 64, 128
dropout:           0.1, 0.2, 0.3
learning_rate:     1e-3, 3e-4
batch_size:        32, 64
optimizer:         Adam
loss:              MAE or Huber
epochs:            max 100
early stopping:    patience 8–12
restore_best:      True
seed:              fixed
```

Use LSTM for:
- Sequence-aware degradation modeling.
- Research comparison.
- Future cross-condition modeling if enough sequential data exists.

Do not use LSTM simply to make the project look more "AI".

## 5.2 1D CNN
Status:
- Research/challenger model.
- Good candidate when fixed-length vibration/HI sequences contain local patterns.
- Must pass the same leakage-safe benchmark.

Suggested starting configuration:
```text
sequence_length:   10, 20, 30
filters:           32, 64
kernel_size:       2 or 3
pool_size:         2
dense_units:       32 or 64
dropout:           0.2–0.4
learning_rate:     1e-3 or 3e-4
batch_size:        32 or 64
loss:              MAE or Huber
early_stopping:    patience 8–12
```

## 5.3 CNN/LSTM promotion rule
A deep model may replace ExtraTrees only if:
- It improves the primary group-held-out MAE materially.
- It does not introduce unacceptable worst-case overestimation.
- Results repeat across multiple bearing splits/seeds.
- Inference cost remains deployable.
- The improvement survives final untouched test evaluation.
- The model artifact and preprocessing pipeline can be reproduced from code.

---

# 6. Health Indicator Model

The Health Indicator is a scientific feature, not a decorative dashboard score.

Preferred policy:
- Preserve the existing validated HI implementation unless evidence supports a change.
- HI should track degradation direction consistently.
- Validate monotonicity/trend per bearing.
- Never fit HI transformations using information from the future test bearing.
- If PCA/fusion is used, fit transformation parameters only on allowed training/reference data.
- Keep a deterministic mapping from raw/engineered features to HI.

HI output should support:
- Numerical health score.
- Health stage.
- Degradation trend.
- Plot over time.
- Inputs/features used to create it.
- Clear distinction between measured/derived values and model predictions.

---

# 7. Feature Engineering Model/Algorithm Policy

## Time-domain features
Core candidates:
- RMS
- Mean
- Standard deviation
- Variance
- Peak
- Peak-to-peak
- Kurtosis
- Skewness
- Crest factor
- Impulse factor
- Shape factor
- Clearance factor

## Frequency-domain features
Core candidates:
- FFT spectrum.
- Dominant frequencies.
- Band energies.
- Spectral centroid where scientifically justified.
- Spectral RMS/energy.
- Frequency-band statistics.

## Time-frequency features
Use only when justified:
- Wavelet packet energy.
- STFT-derived features.
- Spectral kurtosis/kurtogram.

Rules:
- Do not add dozens of features without ablation testing.
- Unit-test feature formulas.
- Keep sampling frequency explicit.
- Do not compute meaningful frequency axes without a valid sample rate.
- Avoid test-data leakage during scaling/feature selection.
- Version the feature schema.

---

# 8. Dataset Compatibility and Adaptation

The goal is NOT "predict any CSV."
The goal is "automatically process supported or scientifically compatible datasets and safely reject unsupported ones."

Every uploaded dataset must pass these stages:

```text
Upload
→ File inspection
→ Schema detection
→ Sensor-channel mapping
→ Unit detection/confirmation
→ Sampling metadata validation
→ Time/order validation
→ Compatibility classification
→ Adapter selection
→ Preprocessing
→ Feature extraction
→ HI
→ Model selection
→ Prediction
→ Diagnostics
```

Compatibility states:
```text
FULLY_SUPPORTED
ADAPTER_REQUIRED
RETRAIN_REQUIRED
UNSUPPORTED
INVALID_INPUT
```

### FULLY_SUPPORTED
Use an existing adapter + model only when:
- Required channels are present.
- Units are known/convertible.
- Sampling information is compatible.
- Feature pipeline can reproduce the trained input schema.
- Operating context is within validated bounds or explicitly supported.

### ADAPTER_REQUIRED
Use when:
- Same physical problem but column names/file layout differ.
- Required signals exist.
- A deterministic mapping can make the dataset compatible without changing model semantics.

### RETRAIN_REQUIRED
Use when:
- Machine/bearing domain is materially different.
- Operating regime differs substantially.
- Signal distribution is outside validated range.
- Required feature schema differs.
- Existing model cannot be scientifically justified.

### UNSUPPORTED
Use when:
- Required signals are missing.
- Units cannot be determined.
- Sampling information is insufficient for required spectral analysis.
- Data represents a different prediction problem.

Never silently force incompatible data through the current model.

---

# 9. Adapter Model Selection

Dataset adapters are deterministic code first, AI-assisted only during development.

Preferred implementation:
- Schema detector.
- Adapter registry.
- Metadata contract.
- Unit converter.
- Column mapper.
- Sampling metadata parser.
- Validation report.
- Canonical internal dataset format.

LLM may suggest a mapping during development, but production ingestion must validate mappings deterministically.

---

# 10. Anomaly Detection Models

Anomaly detection is separate from RUL regression.

Preferred order:
1. Deterministic thresholds when physics/operating limits are known.
2. Statistical z-score/IQR checks for obvious sensor issues.
3. IsolationForest as an optional unsupervised baseline.
4. Sequence autoencoder/LSTM anomaly model only if enough normal sequential data exists.

Suggested IsolationForest starting values:
```text
n_estimators:    300
contamination:   "auto" initially
max_samples:     "auto"
random_state:    42
```

Do not convert an anomaly score directly into RUL.

---

# 11. Explainability Models

## Tree-model explainability
Preferred:
- Feature importance for quick overview.
- Permutation importance for more robust global interpretation.
- SHAP for per-prediction explanation when performance allows.

Rules:
- Do not present feature importance as causal proof.
- Separate model explanation from physical diagnosis.
- Log the exact feature values used for a prediction.

## LLM explanation layer
Optional role:
- Translate validated numeric outputs into readable maintenance language.
- Summarize RUL, HI, anomalies, and evidence.
- Explain uncertainty and unsupported conditions.

LLM must NOT:
- Invent failure causes.
- Override the numeric prediction.
- Claim unsupported certainty.
- Convert weak similarity into a guaranteed diagnosis.

---

# 12. RAG Model Policy

RAG is optional and belongs AFTER the core ML pipeline is stable.

Use RAG for:
- Maintenance manuals.
- Bearing specifications.
- Known failure modes.
- Maintenance procedures.
- Historical maintenance records.
- Explanation grounding.

Recommended architecture:
```text
Validated ML prediction
+ machine metadata
+ retrieved relevant maintenance knowledge
→ LLM explanation
```

Do not feed raw millions-of-row vibration CSVs directly into an LLM and call that predictive maintenance.

---

# 13. Frontend AI Model Selection

### Initial product design / information architecture
Use:
- Claude Opus 5 OR GPT-6 Astra for one architecture/design pass.

### Actual implementation
Use:
- Claude Sonnet 5 OR GPT-6 Sol.

### Component cleanup / repetitive UI work
Use:
- Claude Haiku 4.5 OR GPT-6 Luna only when the design system is already fixed.

Frontend quality checks:
- Avoid generic AI-dashboard styling.
- Use one coherent design system.
- Strong typography and spacing.
- Responsive desktop/mobile.
- Accessible contrast.
- Real loading/progress states for dataset analysis.
- Clear unsupported-dataset errors.
- No fake real-time values.
- No fake confidence percentages.

---

# 14. Backend/API Model Selection

Use Claude Sonnet 5 or GPT-6 Sol for:
- FastAPI routes.
- Upload endpoints.
- Job-state endpoints.
- Result APIs.
- Model-loader service.
- Validation service.
- Adapter service.
- Prediction orchestration.

Escalate to Opus/Astra for:
- Cross-service architecture.
- Concurrency/state problems.
- Hard memory/performance issues.
- Security-sensitive upload architecture.

---

# 15. Deployment Model Selection

### Frontend
Target:
- Next.js/React.
- Vercel-compatible deployment.

AI model:
- Sonnet 5 or GPT-6 Sol.

### ML backend
Do not force a heavy Python scientific stack into a frontend-only serverless path if it creates timeout/memory/model-artifact problems.

Backend deployment task:
- Sonnet 5/GPT-6 Sol for implementation.
- Opus 5/GPT-6 Astra for architecture review if model size, large uploads, queues, or concurrency are involved.

### Deployment requirements
- Reproducible environment.
- Health endpoint.
- Version endpoint.
- Model version.
- Feature-schema version.
- Timeout handling.
- Upload limits.
- Temporary-file cleanup.
- Structured logs.
- No secrets committed to Git.
- Production error handling.

---

# 16. Testing Model Router

### Generate routine unit tests
- Claude Haiku 4.5 / Sonnet 5.
- GPT-6 Luna / Sol.

### Scientific tests
- Sonnet 5 / GPT-6 Sol to implement.
- Opus 5 / GPT-6 Astra to review methodology.

Must-have test categories:
- Dataset schema validation.
- Unit conversion.
- Sampling-rate handling.
- Feature formulas.
- FFT frequency-axis correctness.
- HI consistency.
- Model input schema.
- Prediction determinism.
- Unsupported dataset rejection.
- API upload.
- Large-file behavior.
- Frontend/backend contract.
- Model loading.
- Regression metrics.
- Full end-to-end prediction.

---

# 17. Hyperparameter-Tuning Agent Policy

Use:
- Claude Opus 5 or GPT-6 Astra to DESIGN the tuning experiment.
- Claude Sonnet 5 or GPT-6 Sol to IMPLEMENT and RUN the tuning harness.
- Haiku/Luna may summarize completed trial logs.

Never allow the coding model to:
- Tune on the test set.
- Pick the winner using one convenient split.
- Delete poor experiments.
- Change the metric after seeing results.
- Increase model complexity without documenting the comparison.

Record for every experiment:
```text
experiment_id
git_commit
dataset_version
feature_schema_version
split_definition
model_class
hyperparameters
random_seed
MAE
RMSE
median_absolute_error
signed_error
worst_case_error
runtime
artifact_path
```

---

# 18. Evaluation Model Policy

Primary metric:
- MAE.

Secondary:
- RMSE.
- Median absolute error.
- Per-bearing MAE.
- Signed error/bias.
- Percentage of overpredictions vs underpredictions.
- Worst-case overprediction.
- Runtime/inference latency.

Why:
- A model with acceptable average MAE can still dangerously overestimate RUL on individual bearings.

Mandatory:
- Per-bearing result table.
- Overall aggregate.
- Prediction-vs-actual plot.
- Error distribution.
- Baseline comparison.
- Held-out bearing evaluation.

---

# 19. Overnight Autonomous Work Router

## Orchestrator
Default:
- Claude Sonnet 5 OR GPT-6 Sol.

Responsibilities:
- Read `goals.md`.
- Read `model.md`.
- Inspect current repository.
- Break work into independent tasks.
- Create separate branches/worktrees where file overlap is low.
- Route each task to the correct model.
- Keep a task ledger.
- Stop a task if requirements become scientifically ambiguous.
- Never silently alter stable model behavior.

## Planner / Scientific Reviewer
Use:
- Claude Opus 5 OR GPT-6 Astra.

Invoke for:
- Scientific changes.
- Architecture.
- Dataset adaptation.
- Hard blockers.
- Final integration review.

## Worker
Use:
- Claude Sonnet 5 OR GPT-6 Sol.

## Cheap scanner
Use:
- Claude Haiku 4.5 OR GPT-6 Luna.

## End-of-night integration
Use:
- Opus 5 or GPT-6 Astra for review.
- Sonnet 5 or GPT-6 Sol for mechanical merge/test fixes after the review.

Required overnight completion loop:
```text
implement
→ targeted tests
→ fix
→ targeted tests green
→ merge candidate
→ integration tests
→ full test suite
→ fix regressions
→ full test suite green
→ produce report
```

Never mark an overnight task complete only because code was written.

---

# 20. Escalation Rules

### Level 1
Use Haiku/Luna only for narrow mechanical tasks.

### Level 2
Default implementation:
- Sonnet 5.
- GPT-6 Sol.

### Level 3
Escalate when:
- Two serious attempts fail.
- Root cause is unclear.
- Changes affect scientific correctness.
- More than one subsystem behaves unexpectedly.
- Architecture must be decided.
- Evaluation results contradict expectations.

Use:
- Opus 5.
- GPT-6 Astra.

### Level 4
If strongest model still cannot resolve:
- Stop autonomous modification.
- Preserve logs.
- Record attempted fixes.
- Produce a blocker report.
- Do not brute-force random changes overnight.

---

# 21. Cross-Model Review Rules

For high-risk scientific changes, prefer two-stage review:

Option A:
```text
Claude Opus 5: methodology/reasoning
GPT-6 Sol: implementation
Claude Opus 5 or GPT-6 Astra: final review
```

Option B:
```text
GPT-6 Astra: methodology/reasoning
Claude Sonnet 5: implementation
GPT-6 Astra or Claude Opus 5: final review
```

Use cross-model review for:
- New RUL label definitions.
- New Health Indicator.
- Feature-set replacement.
- Model replacement.
- Dataset compatibility logic.
- Final metric claims.
- Publication/report claims based on code results.

Do not require expensive cross-model review for routine CSS, docs, or simple tests.

---

# 22. Model Promotion Rules

A challenger model becomes the new primary model only if all are true:

1. Same dataset version.
2. Same leakage-safe splits.
3. Same feature availability or clearly documented change.
4. Same primary metric.
5. Better aggregate result.
6. No unacceptable degradation on individual bearings.
7. No major increase in worst-case RUL overestimation.
8. Repeated result across seeds/splits where applicable.
9. Reproducible training script.
10. Saved artifact loads correctly.
11. End-to-end API prediction works.
12. Regression tests updated.
13. Results documented.
14. Previous model retained for rollback.

---

# 23. Things AI Agents Must Never Do

- Do not invent dataset compatibility.
- Do not claim "works on any machine."
- Do not use test data for feature selection or hyperparameter tuning.
- Do not randomly split samples from the same bearing across train/test.
- Do not report training accuracy as production performance.
- Do not silently change units.
- Do not infer sampling rate from guesswork.
- Do not use LLM text generation as the RUL predictor.
- Do not replace ExtraTrees with LSTM/CNN without a controlled benchmark.
- Do not hide failed experiments.
- Do not commit secrets.
- Do not bypass tests to make CI green.
- Do not modify stable model artifacts without versioning.
- Do not overwrite the main branch during overnight work.
- Do not merge a task with failing relevant tests.
- Do not present confidence values unless they come from a defined method.
- Do not present SHAP/feature importance as physical causality.
- Do not fabricate maintenance diagnoses.

---

# 24. Default Decision Cheat Sheet

```text
Need simple file search?              → Haiku 4.5 / GPT-6 Luna
Need normal coding?                   → Sonnet 5 / GPT-6 Sol
Need frontend implementation?         → Sonnet 5 / GPT-6 Sol
Need backend implementation?          → Sonnet 5 / GPT-6 Sol
Need architecture?                    → Opus 5 / GPT-6 Astra
Need scientific methodology?          → Opus 5 / GPT-6 Astra
Need hard debugging?                  → Opus 5 / GPT-6 Astra
Need repetitive docs/test cleanup?    → Haiku 4.5 / GPT-6 Luna
Need Codex-specific fallback?          → GPT-5.3-Codex
Need RUL prediction?                  → ExtraTrees pipeline, NOT an LLM
Need sequential research benchmark?   → LSTM / 1D CNN as challengers
Need anomaly detection?               → thresholds/statistics first, IsolationForest optional
Need prediction explanation?          → SHAP + optional grounded LLM explanation
Need new dataset?                     → compatibility gate → adapter or retrain
Need overnight worker?                → Sonnet 5 / GPT-6 Sol
Need overnight final review?          → Opus 5 / GPT-6 Astra
```

---

# 25. Final Project Model Stack

Preferred current stack:

```text
AI planning / scientific review:
    Claude Opus 5
    or GPT-6 Astra

Default coding:
    Claude Sonnet 5
    or GPT-6 Sol

Fast low-risk tasks:
    Claude Haiku 4.5
    or GPT-6 Luna

Codex-specialized fallback:
    GPT-5.3-Codex

Production RUL:
    ExtraTreesRegressor

RUL challengers:
    RandomForest / Gradient Boosting
    LSTM
    1D CNN

Signal processing:
    deterministic Python/NumPy/SciPy feature pipeline

Health Indicator:
    validated deterministic/fusion pipeline

Explainability:
    feature importance / permutation importance / SHAP

Dataset portability:
    deterministic compatibility gate + adapter registry

Natural-language explanation:
    optional LLM/RAG layer AFTER numeric prediction

Frontend:
    Next.js/React

ML/API backend:
    Python service, preferably FastAPI-style API

Deployment:
    frontend and ML inference separated when required by runtime/model-size constraints
```

This file overrides casual model-selection guesses made by autonomous agents. If a task does not fit a category above, select the closest task type, use the default implementation model, and escalate only when the risk or complexity justifies it.
