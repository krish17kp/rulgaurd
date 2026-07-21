# Claude Code Master Prompt

## Bearing RUL Predictive Maintenance Capstone

You are the lead engineer, scientific reviewer, and loop orchestrator for this capstone. Build a lean, reproducible, local-first system for rolling-bearing degradation monitoring and Remaining Useful Life prediction.

The code project name is:

`bearing-rul-predictive-maintenance`

The Python package name is:

`bearing_pdm`

Do not blindly generate an entire project in one pass. First inspect the real repository, datasets, documents, Claude Code setup, installed agents, skills, plugins, hooks, MCP servers, and available models. Then build the project milestone by milestone through bounded, evidence-based loops.

The actual data and test evidence are the source of truth. Correct weak assumptions from the original project idea before implementation.

---

Donot push code to github you just have to commit it and keep it push i will do manually

# 1. Project mission

Build an end-to-end student capstone that combines:

1. The FEMTO-ST / PRONOSTIA IEEE PHM 2012 bearing dataset as the main multi-bearing RUL benchmark.
2. The college laboratory run-to-failure dataset as a real-world single-bearing case study.
3. Streaming ingestion of large vibration and temperature CSV files.
4. Time-domain, frequency-domain, and selected time-frequency features.
5. Health-indicator construction and degradation-stage estimation.
6. Leakage-safe RUL prediction.
7. Optional, controlled deep-learning experiments.
8. Evidence-grounded Retrieval-Augmented Generation.
9. A local LLM through Ollama, with a deterministic fallback.
10. A Streamlit dashboard and downloadable PDF report.

This is a research prototype and capstone. Do not call it production-ready.

Primary objective:

> Estimate bearing degradation and Remaining Useful Life accurately enough to support an academically defensible comparison of methods.

Secondary objective:

> Convert measured evidence and model outputs into traceable, human-readable maintenance explanations.

The LLM is an explanation and reporting layer. It must never replace the numerical prediction model or alter the predicted RUL.

---

# 2. Inputs to locate and inspect

Locate these files in the current project, parent directories, configured local paths, or paths supplied by the user:

# 2A. Local-only `context/` folder policy

The user will create a local folder named:

```text
context/
```

This folder exists only to give Claude Code the documents, images, references, prompts, and project background needed to understand the capstone.

It must never be pushed to GitHub.

At the beginning of Phase A:

1. Confirm that the root `.gitignore` contains:

```gitignore
/context/
context/
```

2. Confirm with:

```bash
git check-ignore -v context/
git status --short
```

3. If `context/` is already tracked, stop and report it. Do not run destructive Git commands or remove it from the index without explicit user approval.

4. Do not commit, stage, upload, publish, or copy the contents of `context/` into tracked folders.

5. Treat files in `context/` as read-only source material unless the user explicitly requests an edit.

Recommended local structure:

```text
context/
├── README.md
├── MANIFEST.md
├── project-description/
│   └── Description.txt
├── literature/
│   ├── capstone-literature-review.docx
│   └── papers/
├── dataset-archives/
│   ├── Training_set.zip
│   ├── Validation_Set.zip
│   └── Test_set.7z
├── dataset-references/
│   ├── femto-source.md
│   └── college-data-source.md
├── diagrams/
├── prompts/
└── notes/
```

`context/MANIFEST.md` should record:

- local relative path,
- file title,
- file type,
- purpose,
- source URL where applicable,
- checksum,
- whether it contains raw data,
- whether it may be quoted,
- relevant pages or sections,
- known limitations.

Important storage rule:

- Do not duplicate the extracted 129 large college CSV files inside `context/` if they already exist elsewhere.
- Prefer a configured external path in `config/data_paths.toml`.
- A local shortcut, symlink, junction, or small pointer file may be used only after verifying that the current operating system and Claude Code can resolve it safely.
- Do not commit symlinks or pointer files that expose private absolute paths.
- The uploaded FEMTO archives may remain in `context/dataset-archives/` because they are reference inputs, but they must stay ignored by Git.
- Derived features, metrics, manifests, and reports belong in the normal project artifact folders, not in `context/`.

Claude must first read `context/README.md` and `context/MANIFEST.md`, then inspect only the files relevant to the active task. Do not load every large file into the conversation or working memory.

The existence of the local `context/` folder does not change the source-of-truth order. Actual raw files and reproducible inspection remain authoritative.

```text
Training_set.zip
Validation_Set.zip
Test_set.7z
Description.txt
capstone literature review(1).docx
Remaining_useful_life_prediction_for_rolling_beari.pdf
Predictive_Maintenance_for_Industrial_Machinery_Us (1).pdf
Using_Retrieval-Augmented_Generation_for_Fault_Prediction_and_Maintenance_on_the_Factory_Floor.pdf
Udmale2018_Article_ABearingVibrationDataAnalysisB.pdf
85620181122 (1).pdf
Vibration_Bearing_RuntoFailure/
```

Reference repositories:

```text
https://github.com/wkzs111/phm-ieee-2012-data-challenge-dataset
https://github.com/krish17kp/Data-collection-for-predictive-maintenance
```

The second repository is a large-data repository using Git LFS. Keep it separate from the code repository. Do not rename it, repurpose it, rewrite its history, change Git LFS configuration, or duplicate its large CSV files inside the application repository.

Use this source-priority order whenever information conflicts:

1. Actual raw files and reproducible inspection results.
2. Official dataset documentation and repository structure.
3. `Description.txt`.
4. Primary research papers.
5. The literature-review draft.
6. The original friend-provided project prompt.

Record every conflict and resolution in `docs/decisions.md`.

---

# 3. Dataset facts to verify, not blindly trust

## 3.1 College run-to-failure dataset

Expected folder:

`Vibration_Bearing_RuntoFailure`

Expected facts from `Description.txt`:

- One NSK 6205 steel-sealed ball bearing.
- 129 hourly CSV files.
- Approximate file range:
  - first: `LogFile_2022-06-20-17-00-31.csv`
  - last: `LogFile_2022-06-26-01-00-31.csv`
- Four columns:
  1. vibration X
  2. vibration Y
  3. bearing temperature
  4. atmospheric temperature
- Sampling rate: approximately 25.6 kHz.
- Duration represented by each CSV: approximately 78.125 seconds.
- Approximately 2,000,000 rows per CSV if the stated sampling information is correct.
- Operating speed: 1770 to 1780 RPM.
- Axial load: 300 kg, approximately 2.94 kN.
- Vertical load: 600 kg, approximately 5.88 kN.
- Total operating period: 128 hours.
- Stated stop criteria:
  - bearing temperature above 85 °C
  - vibration above 9 m/s²

Do not assume that “vibration above 9 m/s²” means RMS, absolute peak, vector magnitude, or an individual sample. Audit the final files and source documentation. If the definition cannot be proved, treat it only as terminal-event evidence and record the ambiguity.

The college data represents one physical bearing trajectory. It is useful for:

- streaming-pipeline validation,
- health-trend visualization,
- within-run walk-forward backtesting,
- dashboard demonstration,
- domain-shift comparison.

It is not enough to demonstrate cross-bearing RUL generalization.

The Git LFS objects are approximately 141 to 144 MB per file, so the full collection is roughly 18 GB. Never read all files into memory. Never copy them into the code repository. Process one file and one chunk at a time.

## 3.2 FEMTO-ST / PRONOSTIA dataset

The uploaded archive roles are expected to be:

- `Training_set.zip`: six complete learning run-to-failure trajectories.
- `Test_set.7z`: eleven censored challenge prefixes.
- `Validation_Set.zip`: the complete continuation of those eleven test bearings, effectively the `Full_Test_Set`, used only to derive final ground-truth RUL after the model is frozen.

`Validation_Set.zip` is not a normal tuning set. Never use its hidden continuation to fit:

- scalers,
- imputers,
- feature selection,
- PCA,
- health-indicator transformations,
- model hyperparameters,
- thresholds,
- classifiers,
- regressors.

Expected acceleration CSV schema:

```text
hour
minute
second
microsecond
horizontal_acceleration
vertical_acceleration
```

Expected acceleration properties:

- no header,
- six columns,
- usually 2560 rows,
- 25.6 kHz sampling,
- 0.1-second acquisition,
- one acquisition roughly every 10 seconds.

Temperature files are separate and may:

- have five columns,
- use comma or semicolon delimiters,
- have different row counts,
- be absent from some bearing folders.

The parser must detect these conditions. Missing temperature remains missing and receives an availability flag. Do not fabricate or globally forward-fill unavailable streams.

Expected operating conditions:

| Condition |    Speed |   Load |
| --------- | -------: | -----: |
| 1         | 1800 RPM | 4000 N |
| 2         | 1650 RPM | 4200 N |
| 3         | 1500 RPM | 5000 N |

Expected archive counts from a prior read-only inspection are listed below only as audit checkpoints. Recalculate them independently.

### Training archive checkpoints

| Bearing    | Acceleration files | Temperature files |
| ---------- | -----------------: | ----------------: |
| Bearing1_1 |               2803 |               466 |
| Bearing1_2 |                871 |               144 |
| Bearing2_1 |                911 |               151 |
| Bearing2_2 |                797 |                 0 |
| Bearing3_1 |                515 |                89 |
| Bearing3_2 |               1637 |                 0 |

### Full-test archive checkpoints

| Bearing    | Acceleration files | Temperature files |
| ---------- | -----------------: | ----------------: |
| Bearing1_3 |               2375 |                 0 |
| Bearing1_4 |               1428 |               237 |
| Bearing1_5 |               2463 |               410 |
| Bearing1_6 |               2448 |               408 |
| Bearing1_7 |               2259 |               376 |
| Bearing2_3 |               1955 |                 0 |
| Bearing2_4 |                751 |               125 |
| Bearing2_5 |               2311 |               386 |
| Bearing2_6 |                701 |               116 |
| Bearing2_7 |                230 |                38 |
| Bearing3_3 |                434 |                72 |

### Censored test-prefix checkpoints

| Bearing    | Acceleration files | Temperature files |
| ---------- | -----------------: | ----------------: |
| Bearing1_3 |               1802 |                 0 |
| Bearing1_4 |               1139 |               188 |
| Bearing1_5 |               2302 |               383 |
| Bearing1_6 |               2302 |               383 |
| Bearing1_7 |               1502 |               250 |
| Bearing2_3 |               1202 |                 0 |
| Bearing2_4 |                612 |               101 |
| Bearing2_5 |               2002 |               335 |
| Bearing2_6 |                572 |                 0 |
| Bearing2_7 |                172 |                28 |
| Bearing3_3 |                352 |                58 |

Expected hidden RUL values, calculated from missing 10-second acquisitions, must also be independently verified:

| Bearing    | Expected RUL seconds |
| ---------- | -------------------: |
| Bearing1_3 |                 5730 |
| Bearing1_4 |                 2890 |
| Bearing1_5 |                 1610 |
| Bearing1_6 |                 1460 |
| Bearing1_7 |                 7570 |
| Bearing2_3 |                 7530 |
| Bearing2_4 |                 1390 |
| Bearing2_5 |                 3090 |
| Bearing2_6 |                 1290 |
| Bearing2_7 |                  580 |
| Bearing3_3 |                  820 |

If calculated values differ, stop the affected benchmark task, preserve the evidence, and document the discrepancy. Do not force these values into the pipeline.

---

# 4. Mandatory scientific corrections

The original “CSV → Extra Trees → RUL → RAG → LLM → Streamlit” idea contains several invalid or weak assumptions. Correct them as follows.

## 4.1 Keep the datasets separate

FEMTO and the college dataset have different:

- schemas,
- sampling schedules,
- trajectory counts,
- operating conditions,
- temperature availability,
- failure definitions,
- validation roles.

Create separate adapters and normalize only their derived feature records into a shared feature contract.

## 4.2 RUL is the main task

The primary modeling task is RUL regression.

“Healthy / Warning / Critical / Failed” is a secondary degradation-stage task. It is not physical fault-type diagnosis.

Do not claim:

- inner-race fault,
- outer-race fault,
- ball fault,
- lubrication fault,
- misalignment,
- confirmed root cause,

unless a labeled dataset or independently validated diagnostic rule supports the claim.

## 4.3 Prevent leakage

Never randomly split overlapping windows or acquisitions from the same trajectory across train and test sets.

Use:

- grouped or leave-one-bearing-out evaluation for FEMTO,
- time-ordered expanding-window or rolling-origin backtesting for the college run.

Fit every learned transformation inside the training fold:

- scaling,
- imputation,
- outlier policy,
- feature selection,
- PCA,
- health-indicator orientation,
- model tuning.

## 4.4 Use physically meaningful windows

Do not default to 1024 samples for the college data.

At 25.6 kHz:

- 1024 samples cover only 0.04 seconds,
- FFT-bin spacing is about 25 Hz,
- shaft speed near 1770 RPM is about 29.5 Hz.

Use a configurable baseline of:

- 25,600 samples, approximately one second,
- 50% overlap.

Run smaller-window sensitivity tests only after the baseline works.

For FEMTO, use the complete 2560-sample acquisition as the default modeling record. Do not subdivide it unless a controlled experiment demonstrates value.

Do not save millions of overlapping raw windows. Compute features in streaming mode and save compact feature rows.

## 4.5 Do not manufacture labels

Do not label all earlier windows using the final 85 °C and 9 m/s² stop criteria.

Possible stage-label policies include:

- remaining-life fraction,
- change-point detection on a frozen training-derived health indicator,
- a documented rule-based health policy,
- labels used only for educational reproduction.

If a model is trained to reproduce labels generated from the same features, state that circularity clearly. It is not discovering an independent fault mechanism.

## 4.6 Do not overclaim bearing frequencies

Do not claim exact BPFO, BPFI, BSF, or FTF frequencies unless ball count, ball diameter, pitch diameter, and contact angle are available and verified.

## 4.7 RAG does not predict RUL

The numerical model predicts RUL.

The retrieval and LLM layers may explain:

- measured values,
- engineered features,
- health indicator,
- model prediction,
- uncertainty,
- evidence from manuals or papers,
- possible causes explicitly labeled as hypotheses,
- recommended inspection steps supported by retrieved sources.

They may not invent technical facts, override model outputs, or present hypotheses as confirmed failures.

---

# 5. Required first action: discovery only

Do not begin feature or model implementation immediately.

Perform a read-only discovery pass.

## 5.1 Inspect the repository and environment

Inspect:

- repository tree,
- current branch,
- git status,
- remotes,
- `.gitignore`,
- existing project files,
- Python version,
- package manager,
- available disk and memory,
- installed libraries,
- current Claude Code version,
- `.claude/` project configuration,
- user-level Claude configuration where accessible,
- installed plugins,
- installed skills,
- installed subagents,
- hooks,
- MCP servers,
- model availability,
- worktrees.

Use current Claude Code help and inventory commands. Do not invent commands or tool names.

## 5.2 Inspect data without full extraction

For each archive:

- list the archive tree,
- count files by bearing and modality,
- sample early, middle, and final files,
- inspect delimiters,
- verify schemas,
- verify row counts,
- inspect timestamp order,
- detect missing and duplicate files,
- detect non-finite values,
- inspect basic ranges,
- calculate stable archive checksums,
- estimate total processing cost.

For the college dataset:

- inspect at least three early, three middle, and three final files,
- read small chunks only,
- verify whether headers exist,
- verify column order and units where possible,
- estimate rows and memory,
- inspect final threshold behavior,
- confirm file ordering from parsed timestamps.

Keep all raw data immutable.

## 5.3 Inspect source documents

Read the relevant sections of every supplied document and create a source-to-decision map.

Required topics:

### `Remaining_useful_life_prediction_for_rolling_beari.pdf`

Study and reproduce only where justified:

- ten traditional time-domain features,
- frequency-domain sub-band features,
- wavelet-packet energy ratios,
- Pearson related-similarity features,
- trend and monotonicity,
- Cori feature screening,
- PCA health indicator,
- 1D CNN over health-indicator sequences,
- FEMTO evaluation design.

Treat paper thresholds and architecture settings as hypotheses, not universal defaults.

### `85620181122 (1).pdf`

Study:

- the twelve statistical features,
- Decision Tree and Randomized Lasso feature ranking,
- Random Forest,
- Gradient Boosting,
- Extra Trees,
- the reported influence of feature count and estimator count.

The paper’s reported best setting, Extra Trees with six DT-ranked features and 30 estimators, is a reproduction baseline only. Do not claim its reported accuracy will transfer to this project.

### `Udmale2018_Article_ABearingVibrationDataAnalysisB.pdf`

Study:

- spectral kurtosis,
- kurtograms,
- conversion of vibration data to 2D fault representations,
- ConvNet classification,
- the effect of kurtogram level.

This is an optional future fault-classification application. It is not valid on the current run-to-failure data unless proper physical fault labels are available. Do not add it to the MVP.

### `Predictive_Maintenance_for_Industrial_Machinery_Us (1).pdf`

Study the architectural path:

```text
sensor acquisition
-> edge device
-> storage
-> preprocessing
-> retrieval
-> LLM analysis
-> dashboard
-> alerts
-> human feedback
```

Use it as architectural inspiration. Do not copy Firebase, Flask, Brevo, LangChain, or its model-comparison claims into the MVP without independent justification.

### `Using_Retrieval-Augmented_Generation_for_Fault_Prediction_and_Maintenance_on_the_Factory_Floor.pdf`

Study:

- Data Ingestion Layer,
- Monitoring Agent,
- LSTM forecasting and anomaly error,
- RAG-enabled LLM Reasoning Core,
- Communication Agent,
- role-based notifications,
- alert cooldown,
- LangGraph state-machine orchestration,
- Llama 3.1 usage,
- limitations of synthetic validation.

The user’s “LMST” reference should be interpreted as “LSTM,” then verified against the paper.

Use the architecture principles, but do not add LSTM, LangGraph, asynchronous agents, or a communication service to the MVP unless a milestone-level experiment proves they are needed.

### Literature review

Treat it as a secondary draft. Verify major claims against primary sources and flag unsupported statements.

Create:

`docs/research-source-audit.md`

It must map each important project choice to:

- source title,
- author,
- year,
- page or section,
- local path or URL,
- how the source is used,
- limitations,
- whether the claim was accepted, modified, or rejected.

Do not copy long copyrighted passages.

---

# 6. Loop engineering operating system

Use a bounded loop, not an uncontrolled autonomous loop.

For every task:

```text
Discover
-> Plan
-> Minimize
-> Implement
-> Verify
-> Independent Review
-> Simplify
-> Record Evidence
-> Commit
-> Continue or Stop
```

## 6.1 Task states

Every task ends in exactly one state:

- `TODO`
- `IN_PROGRESS`
- `DONE`
- `BLOCKED_EXTERNAL`
- `BLOCKED_TECHNICAL`
- `DEFERRED`
- `REJECTED`

Definitions:

- `DONE`: acceptance criteria passed with fresh evidence tied to the current commit.
- `BLOCKED_EXTERNAL`: missing data, credentials, software, hardware, or a user decision.
- `BLOCKED_TECHNICAL`: reproducible technical failure remains after bounded retries.
- `DEFERRED`: intentionally outside the active milestone.
- `REJECTED`: unnecessary, invalid, or not worth its complexity.

An agent saying “done” is not evidence.

## 6.2 Retry policy

For each implementation task:

1. Run the narrowest relevant checks.
2. Use an independent reviewer that did not write the code.
3. Fix findings.
4. Rerun checks.
5. Allow no more than two complete correction cycles.
6. On the third failure, stop and mark the task blocked.

Never weaken a test, alter a metric, suppress a warning, delete a failing case, or leak future data to make a milestone pass.

## 6.3 Evidence

Store evidence under:

```text
artifacts/evidence/<TASK-ID>/
```

Evidence may include:

- command logs,
- test output,
- archive manifests,
- data-quality JSON,
- plots,
- metrics,
- screenshots,
- model cards,
- reviewer findings,
- Ponytail findings,
- hashes,
- commit SHA.

Never mark a task done without an evidence path.

## 6.4 Worktrees

Use a git worktree only when:

- two implementation tasks are independent,
- they do not edit the same files,
- isolation materially reduces merge risk,
- an experiment should remain separate.

Good examples:

- FEMTO adapter and college adapter in separate worktrees.
- Independent test implementation for a separate module.
- Optional CNN experiment isolated from the stable baseline.

Do not create worktrees for:

- README edits,
- TODO updates,
- one-line fixes,
- tightly coupled changes,
- formatting.

Integrate one worktree at a time and rerun the milestone gate after integration.

## 6.5 Automation and scheduling

Do not create cron jobs or unattended schedules during the foundation phase.

After a stable baseline, lightweight automation may cover:

- unit tests,
- linting,
- tiny-fixture smoke tests,
- report regeneration when model code changes.

Never process the full 18+ GB college dataset in CI.

---

# 7. Model, agent, skill, and plugin routing

## 7.1 Inventory before use

Before delegating:

- list actual available models,
- list installed agents,
- list skills and read their descriptions or `SKILL.md`,
- list plugins,
- list hooks,
- list MCP tools,
- inspect project-specific restrictions.

Record the inventory in:

`docs/tooling-inventory.md`

Do not invent or assume plugin commands.

Use only tools that directly help the active task.

## 7.2 Model routing

Map actual available models to capability classes.

### Cheapest / fastest model, normally Haiku

Use for:

- repository inventory,
- file discovery,
- read-only search,
- manifest generation after the algorithm is defined,
- README and TODO synchronization,
- formatting,
- changelog updates,
- exact small test additions,
- simple deterministic fixes,
- command-output summaries,
- commit-message drafts.

### General implementation model, normally Sonnet

Use for:

- Python adapters,
- chunked CSV processing,
- window-boundary logic,
- feature extraction,
- signal processing,
- database and storage code,
- model training,
- evaluation,
- Streamlit work,
- integration tests,
- normal debugging.

### Highest reasoning model, normally Opus

Use only for:

- initial scientific architecture review,
- leakage and experimental-design audit,
- ambiguous cross-dataset methodology,
- difficult mathematical decisions,
- a bug that survives two implementation-model attempts,
- final capstone scientific audit.

Do not use Opus or Sonnet for routine README edits, file renames, formatting, or status updates.

## 7.3 Subagents

Prefer installed subagents that match the task.

Create project-specific agents only when:

- no installed agent fits,
- the role will be reused,
- the added configuration saves more context than it costs.

Possible roles, only if missing:

- `data-auditor`: read-only, cheapest model.
- `signal-ml-builder`: implementation model.
- `independent-reviewer`: no-write review.
- `methodology-auditor`: highest reasoning model at milestone gates.

Subagents must return concise findings containing:

- files inspected,
- files changed,
- commands run,
- evidence paths,
- unresolved risks.

Subagents must not dump full raw files into the parent context. Subagents must not delegate to more subagents.

## 7.4 Ponytail policy

Ponytail is the mandatory anti-overengineering control if installed.

First discover its actual commands and supported modes.

Before implementation, apply this reduction ladder:

1. Does this need to exist?
2. Does equivalent code already exist?
3. Can the Python standard library do it?
4. Can a native platform feature do it?
5. Is an installed dependency already enough?
6. What is the minimum complete change that satisfies acceptance criteria?

Use Ponytail as follows:

- keep its normal or appropriate mode active during non-trivial implementation,
- run its review command on every meaningful diff,
- run its full audit at every milestone gate,
- run a final audit before delivery.

Do not run a whole-repository audit after every one-line edit. That wastes tokens and time without improving quality.

Ponytail checks complexity. It does not replace:

- correctness tests,
- security review,
- data-loss protection,
- performance checks,
- leakage audit,
- scientific-validity review.

Record accepted and rejected findings with reasons.

## 7.5 Caveman policy

Caveman is a token-saving tool, not a reasoning substitute.

Use `lite` or the least aggressive verified mode only for:

- progress summaries,
- routine command-result summaries,
- TODO status updates,
- commit-message drafts.

Never use Caveman compression for:

- architecture,
- PRD,
- formulas,
- database schema,
- data contracts,
- code,
- test failures,
- debugging,
- metric interpretation,
- methodology,
- research conclusions,
- citations,
- acceptance criteria,
- user-facing final documentation.

Do not automatically compress `CLAUDE.md`, architecture, PRD, research audit, dataset audit, or decision records. Compress only stable low-risk text after reviewing a normal-language diff and proving no constraint was lost.

Measure whether it saves total session tokens. Disable it when plugin overhead exceeds savings.

## 7.6 Graphify policy

Check whether Graphify is installed and identify its current official package, version, commands, and security source.

Do not install it during an empty foundation phase merely because it was mentioned.

Use or install it only when:

- the repository has enough code for a graph to add value,
- normal search is no longer sufficient,
- the expected context savings are documented,
- the current official installation instructions are verified,
- installation will not modify the project unexpectedly.

The user has expressed interest in Graphify. If it is absent and the M2 or later repository audit shows clear value, install the verified official version, record the version and commands in `docs/tooling-inventory.md`, and run a small usefulness test. If it adds no measurable value, remove or disable it.

Do not let Graphify become a mandatory runtime dependency of the capstone.

---

# 8. Foundation documents required before feature code

Create and fully populate:

```text
CLAUDE.md
AGENTS.md
TODO.md
docs/prd.md
docs/architecture.md
docs/milestone.md
docs/roadmap.md
docs/database-structure.md
docs/database-schema.md
docs/data-contract.md
docs/dataset-card.md
docs/dataset-audit.md
docs/tooling-inventory.md
docs/research-source-audit.md
docs/decisions.md
docs/risk-register.md
```

Do not create empty templates. Every document must reflect the inspected repository and actual data.

## 8.1 `CLAUDE.md`

Keep it concise, preferably under 200 lines.

Include:

- project mission,
- source-of-truth order,
- non-negotiable scientific rules,
- commands,
- folder ownership,
- task-state policy,
- prohibited actions,
- model-routing summary,
- current milestone pointer.

Move detailed procedures into documents or skills rather than making `CLAUDE.md` huge.

## 8.2 `AGENTS.md`

Document:

- available model classes,
- agent roles,
- plugin and skill selection policy,
- reviewer independence,
- worktree policy,
- Ponytail policy,
- Caveman policy,
- escalation rules.

## 8.3 `docs/prd.md`

Include:

- problem statement,
- target users,
- decisions supported,
- goals,
- non-goals,
- functional requirements,
- non-functional requirements,
- scientific-validity requirements,
- user stories,
- MVP scope,
- optional research scope,
- success metrics,
- limitations,
- privacy,
- licensing,
- risks,
- acceptance criteria,
- explicit non-claims.

Users:

- student researchers,
- faculty evaluators,
- maintenance engineers.

Explicit non-claims:

- no guaranteed physical root-cause diagnosis,
- no production safety certification,
- no cross-bearing validation from the single college run,
- no LLM-generated numeric prediction,
- no real-time industrial deployment unless separately implemented and tested.

## 8.4 `docs/architecture.md`

Include a Mermaid diagram showing separate dataset paths before normalization:

```text
FEMTO archives ----------------> FEMTO adapter ------\
                                                      \
                                                       -> canonical feature contract
                                                      /        |
College Git LFS CSV folder ----> College adapter ----/         v
                                                  streaming feature extraction
                                                            |
                                                        Parquet store
                                                            |
                                                    DuckDB metadata/lineage
                                                            |
                                      health indicator + stage model + RUL model
                                                            |
                                               prediction service functions
                                                            |
                                traceable knowledge -> FAISS retrieval
                                                            |
                                       Ollama or deterministic template
                                                            |
                                          Streamlit dashboard + PDF
```

Explain:

- trust boundaries,
- data lineage,
- training versus final evaluation separation,
- failure behavior,
- optional components,
- why raw high-frequency samples remain outside the database.

## 8.5 `docs/milestone.md`

Define milestones M0 through M9.

Every milestone must contain:

- purpose,
- entry criteria,
- task IDs,
- assigned model class,
- likely agent or skill,
- deliverables,
- acceptance criteria,
- verification commands,
- evidence paths,
- stop conditions,
- exit criteria.

## 8.6 `docs/roadmap.md`

Provide:

- dependency order,
- MVP versus optional research,
- realistic student schedule,
- estimated compute and storage needs,
- critical path,
- decision gates,
- fallback plan.

Do not promise dates that cannot be justified.

## 8.7 `docs/database-structure.md`

Use this lean storage architecture unless inspection proves it insufficient:

- Raw archives and CSVs remain external, immutable, and read-only.
- Local paths are configured through `config/data_paths.toml`.
- Small test fixtures are committed.
- Derived feature tables are Parquet.
- DuckDB stores metadata, lineage, experiment records, metrics, predictions, and report references.
- Scikit-learn models use Joblib.
- Optional neural models use their framework-native format.
- FAISS stores the local vector index.
- Figures, JSON metrics, and PDF reports are files referenced by path and checksum.

Explain why raw sensor rows are not stored in DuckDB.

## 8.8 `docs/database-schema.md`

Use DuckDB without an ORM.

Define at least:

- `datasets`
- `bearing_runs`
- `acquisitions`
- `feature_batches`
- `model_runs`
- `evaluation_metrics`
- `predictions`
- `knowledge_documents`
- `retrieval_events`
- `generated_reports`

For each table, define:

- primary key,
- foreign keys,
- data types,
- units,
- nullable fields,
- unique constraints,
- indexes where useful,
- source lineage,
- retention,
- related Parquet path,
- checksum fields.

Include:

- Mermaid ER diagram,
- SQL DDL,
- example queries,
- migration or schema-version strategy.

Store wide feature vectors in Parquet. The database stores their identifiers, schema version, paths, and hashes.

## 8.9 `docs/data-contract.md`

Define canonical records for:

- dataset,
- bearing run,
- acquisition,
- college window,
- feature row,
- RUL target,
- stage target,
- prediction,
- knowledge chunk.

Include:

- IDs,
- timestamp semantics,
- units,
- nullable fields,
- dataset-specific mappings,
- missing-temperature rules,
- train/test role,
- leakage guards,
- schema version.

## 8.10 `docs/dataset-card.md`

Document:

- provenance,
- licensing status,
- acquisition conditions,
- sampling design,
- archive roles,
- known gaps,
- intended use,
- prohibited claims,
- domain shift,
- class imbalance,
- single-run limitation,
- hidden-test handling.

## 8.11 `docs/dataset-audit.md`

Include:

- exact local paths,
- checksums,
- file counts,
- archive tree,
- per-bearing counts,
- schemas,
- separators,
- row counts,
- timestamp ranges,
- missing temperature,
- duplicates,
- non-finite values,
- memory estimates,
- units,
- confirmed facts,
- uncertain facts,
- leakage risks,
- processing recommendation.

## 8.12 `TODO.md`

`TODO.md` is the canonical loop state.

Use a table with:

| Field                       | Meaning                   |
| --------------------------- | ------------------------- |
| ID                          | Stable task ID            |
| Milestone                   | M0 to M9                  |
| Task                        | One bounded task          |
| Status                      | Allowed task state        |
| Dependencies                | Task IDs                  |
| Assigned model class        | Cheapest capable class    |
| Assigned agent/skill/plugin | Actual discovered tool    |
| Worktree/branch             | Isolation choice          |
| Files allowed to change     | Explicit scope            |
| Acceptance criteria         | Objective completion gate |
| Verification commands       | Exact commands            |
| Evidence path               | Fresh evidence            |
| Last update                 | Timestamp                 |
| Commit                      | Commit SHA when done      |

Update it after every task.

---

# 9. Recommended lean repository structure

Start with this structure and merge modules when Ponytail shows a split has no value:

```text
bearing-rul-predictive-maintenance/
├── CLAUDE.md
├── AGENTS.md
├── TODO.md
├── README.md
├── .gitignore
├── pyproject.toml
├── requirements.txt
├── requirements-rag.txt
├── config/
│   ├── data_paths.example.toml
│   └── project.example.toml
├── docs/
├── data/
│   ├── fixtures/
│   ├── interim/
│   └── processed/
├── artifacts/
│   ├── evidence/
│   ├── models/
│   ├── indices/
│   └── metadata.duckdb
├── reports/
│   ├── figures/
│   ├── metrics/
│   ├── verification/
│   └── pdf/
├── src/
│   └── bearing_pdm/
│       ├── __init__.py
│       ├── config.py
│       ├── manifest.py
│       ├── femto.py
│       ├── college.py
│       ├── features.py
│       ├── health.py
│       ├── modeling.py
│       ├── evaluation.py
│       ├── storage.py
│       ├── rag.py
│       ├── reporting.py
│       └── dashboard.py
├── scripts/
│   ├── audit_data.py
│   ├── build_features.py
│   ├── train_models.py
│   ├── evaluate_models.py
│   ├── build_index.py
│   └── run_dashboard.py
└── tests/
```

Do not add:

- microservices,
- a REST API,
- message queues,
- PostgreSQL,
- Kubernetes,
- cloud deployment,
- Firebase,
- Celery,
- Redis,
- LangGraph,
- LangChain,

unless an accepted requirement later proves the simpler local architecture inadequate.

Do not commit:

- raw datasets,
- full extracted archives,
- Git LFS objects,
- generated model binaries,
- FAISS indices,
- private absolute paths,
- Ollama model files,
- secrets,
- large generated reports.

---

# 10. Data processing

## 10.1 General rules

- Read in bounded memory.
- Sort using parsed timestamps.
- Preserve metadata and lineage.
- Preserve overlap across CSV chunk boundaries.
- Record transformation configuration and code version.
- Use deterministic seeds.
- Fit learned transformations on training data only.
- Cache derived features.
- Fail clearly on missing paths or invalid schema.
- Never silently coerce malformed data.

## 10.2 College adapter

Requirements:

- discover 129 files rather than hard-code them,
- parse timestamps from file names,
- detect header presence,
- validate four numeric columns,
- process CSV chunks,
- carry overlap between chunks,
- default to 25,600-sample windows with 50% overlap,
- avoid storing raw windows,
- emit one compact feature row per window,
- include file ID, timestamp, hour index, window index, row range, and source hash,
- calculate temperature features only when valid,
- preserve final incomplete-window policy in configuration,
- report any mismatch against stated 78.125-second duration.

## 10.3 FEMTO adapter

Requirements:

- read ZIP and 7z archives without unnecessary full extraction,
- discover bearings and modalities,
- detect acceleration and temperature files,
- parse acceleration files with six columns,
- detect temperature separators,
- preserve missing temperature,
- use one feature row per 2560-sample acceleration acquisition,
- align temperature by timestamp or nearest valid acquisition within a documented tolerance,
- preserve condition and bearing ID,
- distinguish complete learning, censored test, and hidden full-test records,
- derive hidden RUL only after predictions are frozen.

## 10.4 Feature engineering

Implement formula-level tests.

### Time-domain vibration features for X and Y

- mean
- absolute mean
- RMS
- standard deviation
- variance
- minimum
- maximum
- peak-to-peak
- crest factor
- shape factor
- impulse factor
- clearance factor
- kurtosis
- skewness

Use explicit definitions and numerical guards. Decide whether kurtosis is Fisher or Pearson form and document it.

### Frequency-domain features for X and Y

- FFT magnitude summaries
- dominant frequency
- spectral centroid
- spectral entropy
- frequency RMS
- total spectral energy
- normalized band energies
- optional envelope-spectrum summaries where justified

Define frequency bands in configuration. Do not choose arbitrary bands without documenting why.

### Temperature features

When available:

- mean
- minimum
- maximum
- standard deviation
- bearing minus atmospheric temperature
- within-window or within-file slope
- rolling trend based only on past observations
- missing-temperature flag

### Optional time-frequency features

Only after baseline gates:

- wavelet-packet energy ratios,
- similarity features,
- spectral kurtosis or kurtogram experiments.

Do not add these merely to make the system look advanced.

---

# 11. Health indicator

Implement and compare two approaches.

## 11.1 Transparent baseline HI

Use a small set of robustly normalized degradation features.

Requirements:

- training-derived orientation,
- clear meaning, preferably 1 = healthy and 0 = failed,
- documented weights,
- no future-data normalization,
- monotonicity and trend evaluation,
- sensitivity analysis.

## 11.2 Paper-inspired HI

Follow the RUL paper carefully:

1. Extract time, frequency, and optional wavelet-packet features.
2. Build related-similarity features relative to a training-derived healthy baseline.
3. Calculate trend and monotonicity.
4. Calculate the Cori index.
5. Select sensitive features using only training data.
6. Normalize using training parameters.
7. Fit PCA on training data.
8. Use and orient the first principal component as HI.
9. Freeze the entire transformation before validation and test.

Evaluate:

- monotonicity,
- trendability,
- smoothness,
- prognosability where mathematically meaningful,
- visual degradation consistency,
- RUL-model usefulness.

Paper thresholds such as 0.5 or 0.2 are hypotheses. Calibrate, justify, or reject them.

---

# 12. Modeling

## 12.1 RUL prediction, primary task

### FEMTO

Use the six complete learning bearings for model development.

Evaluation options:

- GroupKFold by bearing where feasible,
- leave-one-bearing-out,
- condition-aware reporting.

Targets:

```text
RUL_seconds = final acquisition time - current acquisition time
```

Baselines:

1. naive linear-life baseline,
2. simple last-observed health-trend baseline,
3. RandomForestRegressor,
4. ExtraTreesRegressor,
5. HistGradientBoostingRegressor only if it adds a meaningful comparison.

Do not add a large hyperparameter search. Use a small, documented search space.

Metrics:

- MAE,
- RMSE,
- normalized error,
- per-bearing error,
- R² with caveats,
- prediction-interval coverage if implemented,
- PHM challenge score only after verifying its authoritative formula.

Freeze the selected pipeline before evaluating censored prefixes against the hidden full-test continuation.

### College dataset

Use:

- expanding-window evaluation,
- rolling-origin backtesting,
- time-ordered splits.

Report:

- within-run error,
- degradation tracking,
- uncertainty,
- domain shift relative to FEMTO.

Do not claim independent-bearing generalization.

## 12.2 Degradation-stage classification, secondary task

Possible classes:

- Healthy
- Warning
- Critical
- Failed

Requirements:

- document the label policy,
- avoid circular labels where possible,
- never call it physical fault-type classification,
- preserve chronological and bearing-group splits.

Baselines:

- Logistic Regression,
- ExtraTreesClassifier,
- HistGradientBoostingClassifier if justified.

Include the paper-inspired reproduction baseline:

```python
ExtraTreesClassifier(n_estimators=30, random_state=42)
```

But do not assume 30 trees is optimal. Compare it with one modest stable setting, such as 200 trees, using group-aware validation and runtime evidence.

Metrics:

- balanced accuracy,
- macro precision,
- macro recall,
- macro F1,
- confusion matrix,
- per-class support.

Do not report a misleading single accuracy number on highly imbalanced classes.

## 12.3 Uncertainty

For forest models, use tree-level prediction distributions as a practical uncertainty estimate if validated.

Do not display a fake “confidence” score.

The dashboard must distinguish:

- model probability,
- empirical interval,
- retrieval score,
- LLM wording.

---

# 13. Optional research extensions

Do not begin these until the classical, leakage-safe baseline works.

## 13.1 1D CNN over health-indicator sequences

Reproduce the RUL paper as a bounded experiment:

- input sequences of HI values,
- small 1D CNN,
- sequence length documented,
- paper-inspired kernel count 64, kernel size 2, pool size 2 as one reproduction configuration,
- early stopping,
- fixed seed,
- no hidden-test tuning.

Compare against classical baselines.

Report:

- parameter count,
- training time,
- MAE,
- RMSE,
- per-bearing performance,
- ablation against simpler HI.

Reject the CNN from the final selected pipeline if it does not materially improve the result.

Do not add LSTM, BiLSTM, Transformers, attention, or autoencoders without a separate hypothesis and gate.

## 13.2 Spectral-kurtosis ConvNet

Only implement when a properly labeled fault dataset is available.

Requirements:

- clearly separate fault diagnosis from RUL,
- generate kurtograms at controlled levels,
- train a small 2D CNN,
- compare levels and a non-CNN baseline,
- use grouped splits by operating condition and specimen,
- do not infer labels from run-to-failure time.

Until then, mark this application `DEFERRED`.

## 13.3 LSTM monitoring agent

The RAG factory-floor paper uses LSTM next-step forecasting with a robust scaler and MSE threshold.

Treat this as an optional anomaly-detection experiment, not a required part of RUL prediction.

Only add it if:

- classical temporal baselines fail,
- a clear anomaly-detection question is defined,
- enough trajectories exist,
- the additional complexity passes Ponytail and methodology review.

---

# 14. RAG knowledge base

RAG is an evidence-grounding layer.

Do not have Claude invent:

- `bearing_faults.txt`,
- `maintenance_manual.txt`,
- lubrication guidance,
- safety procedures,
- repair instructions,

from model memory.

Build the knowledge base from traceable sources:

- supplied papers,
- official FEMTO documentation,
- verified manufacturer material,
- verified maintenance manuals,
- project data card,
- project model card,
- project limitations,
- user-supplied maintenance records.

Every chunk must store:

- source title,
- author or organization,
- date,
- page or section,
- local path or source URL,
- license status,
- checksum,
- chunk ID,
- extraction method.

Prefer direct libraries:

- `sentence-transformers/all-MiniLM-L6-v2`,
- FAISS where supported,
- NumPy cosine-search fallback,
- direct Ollama HTTP or Python client.

Do not add LangChain by default. Add it only when a concrete feature cannot be implemented cleanly with direct APIs.

Retrieval output must include:

- source ID,
- passage metadata,
- relevance score,
- cited text span.

Add:

- retrieval smoke tests,
- known-question tests,
- citation-presence tests,
- hallucination guard,
- rejection of uncited maintenance advice.

---

# 15. Local LLM reporting

Use an Ollama model already installed when possible.

Do not assume Mistral exists. Inventory available models first.

If several models are available, run a small deterministic comparison on:

- factual grounding,
- citation retention,
- structured-output validity,
- latency,
- memory use.

Do not reproduce weak benchmark claims from another paper as project truth.

The report must separate:

1. Measured sensor facts.
2. Engineered feature values.
3. Health indicator and stage.
4. Numerical RUL prediction and interval.
5. Retrieved maintenance evidence with citations.
6. Possible causes, labeled as hypotheses.
7. Recommended inspection actions supported by evidence.
8. Limitations and missing evidence.

If Ollama is absent or fails, generate a deterministic template report using the same measured facts and citations.

The dashboard and PDF report must still work without Ollama.

---

# 16. Streamlit dashboard

Build one lean local app with tabs or clearly separated sections.

Required functions:

- configured dataset path,
- bearing/run selection,
- manageable CSV upload,
- automatic schema detection,
- sampled raw X and Y plots,
- temperature trends when present,
- FFT spectrum,
- feature summary,
- health indicator,
- degradation stage,
- RUL prediction,
- uncertainty or limitation statement,
- model metadata,
- retrieved evidence,
- LLM or template report,
- downloadable PDF,
- precomputed model-evaluation page.

Performance rules:

- never send a full 143 MB CSV to the browser,
- downsample plots,
- stream large files,
- cache derived features and loaded models,
- never train on page load,
- degrade gracefully when optional dependencies are missing.

---

# 17. Dependencies

Start small.

Core candidates:

```text
numpy
pandas
scipy
scikit-learn
pyarrow
duckdb
joblib
matplotlib
plotly
streamlit
py7zr
pytest
reportlab
```

Use one lightweight lint/format tool only if justified, preferably Ruff.

Optional RAG dependencies belong in `requirements-rag.txt`:

```text
sentence-transformers
faiss-cpu
ollama
```

Do not add TensorFlow or PyTorch until the optional CNN milestone starts. Prefer whichever supported framework is already available.

Pin compatible versions only after a clean environment succeeds.

---

# 18. Milestones

## M0: repository, tooling, source, and foundation audit

Deliver:

- repository inventory,
- tooling inventory,
- archive inventory,
- representative data samples,
- source audit,
- all foundation documents,
- initial folder structure,
- `.gitignore`,
- initial TODO state.

Gate:

- datasets are separated,
- archive roles are correct,
- no hidden-test leakage,
- no unsupported fault claims,
- storage avoids raw-row database ingestion,
- Ponytail and independent scientific reviews pass.

## M1: dataset audit and adapters

Deliver:

```text
reports/data-audit.md
reports/data-manifest.parquet
reports/data-quality.json
```

Implement and test both dataset adapters.

Gate:

- bounded memory,
- schema detection works,
- delimiters work,
- timestamps and ordering work,
- missing temperature remains explicit,
- test-prefix/full-test RUL derivation is independently verified.

## M2: streaming feature pipeline and feature store

Deliver:

- tested feature formulas,
- chunk-safe college windowing,
- FEMTO acquisition features,
- Parquet feature store,
- DuckDB lineage records,
- feature manifest.

Gate:

- no raw-window explosion,
- deterministic output,
- schema version and hashes recorded,
- zero-denominator and constant-signal tests pass.

## M3: health-indicator baselines

Deliver:

- transparent HI,
- paper-inspired HI,
- metrics and plots,
- comparison report.

Gate:

- train-only fitting,
- monotonicity/trend evidence,
- no hidden-test use,
- one selected baseline or documented rejection.

## M4: RUL baselines and leakage-safe evaluation

Deliver:

- naive baseline,
- tree-based baselines,
- grouped FEMTO validation,
- college walk-forward results,
- model card,
- saved pipeline.

Gate:

- group/time splits,
- no preprocessing leakage,
- reproducible metrics,
- per-bearing results,
- frozen final pipeline.

## M5: degradation-stage classification

Deliver:

- documented labels,
- Extra Trees reproduction baseline,
- small baseline comparison,
- class metrics and confusion matrix.

Gate:

- task named correctly,
- no physical fault-type claims,
- imbalance handled in reporting,
- grouped/time-ordered evaluation.

## M6: optional paper-inspired deep-learning experiment

Deliver only if approved by M4 evidence:

- 1D CNN over HI,
- one controlled configuration,
- one ablation table,
- comparison with classical models,
- accept/reject decision.

Keep spectral-kurtosis ConvNet deferred unless labeled fault data is added.

## M7: RAG and local report generation

Deliver:

- traceable knowledge ingestion,
- embeddings and index,
- retrieval with citations,
- hallucination guard,
- Ollama integration,
- deterministic fallback.

Gate:

- uncited claims rejected,
- numeric RUL unchanged by LLM,
- retrieval tests pass,
- app works without optional LLM.

## M8: Streamlit dashboard and PDF

Deliver:

- dashboard,
- cached artifact loading,
- plots,
- prediction display,
- evidence display,
- PDF report,
- startup smoke test.

Gate:

- no page-load training,
- no browser loading of huge files,
- optional components fail gracefully.

## M9: reproducibility and final capstone audit

Deliver:

- final README,
- exact setup commands,
- data-path configuration,
- architecture and database diagrams,
- generated results tables,
- model card,
- dataset card,
- limitations,
- demo flow,
- final verification report,
- final Ponytail audit,
- final independent scientific audit.

Gate:

- clean environment succeeds,
- all fixture tests pass,
- no secrets,
- no unsupported claims,
- no stale documentation,
- no hidden absolute paths,
- raw data remain immutable.

---

# 19. Testing requirements

Create tiny committed fixtures with provenance. Never commit full dataset files.

Required tests:

- FEMTO acceleration parser.
- FEMTO temperature parser with comma delimiter.
- FEMTO temperature parser with semicolon delimiter.
- Missing-temperature handling.
- College four-column parser.
- Header detection.
- File-name timestamp parsing.
- Chronological ordering.
- Chunk-boundary window overlap.
- Final incomplete-window policy.
- Every feature formula.
- Zero-denominator guards.
- Constant-signal behavior.
- FFT frequency-axis correctness.
- Train-only scaling and PCA.
- Group split leakage guard.
- Time split leakage guard.
- RUL label construction.
- Test-prefix versus full-test RUL derivation.
- Model save/load.
- DuckDB schema and lineage.
- FAISS or fallback retrieval.
- Citation retention.
- Template report.
- PDF generation.
- Streamlit import/startup where feasible.

Every metric and chart must be generated by code. Never invent expected accuracy.

---

# 20. Verification commands

Provide cross-platform Python entry points.

At minimum:

```bash
python scripts/audit_data.py --config config/data_paths.toml
python scripts/build_features.py --dataset femto --config config/data_paths.toml
python scripts/build_features.py --dataset college --config config/data_paths.toml
python scripts/train_models.py --config config/data_paths.toml
python scripts/evaluate_models.py --config config/data_paths.toml
python scripts/build_index.py --config config/data_paths.toml
python scripts/run_dashboard.py
pytest -q
ruff check .
```

Commands must fail with clear, actionable messages when data paths or optional dependencies are missing.

Do not run the full college pipeline until the streaming smoke test, disk estimate, and user-configured output path are verified.

---

# 21. Git and change-control policy

- Keep raw data out of normal Git history.
- Keep the entire local `context/` folder ignored and untracked.
- Never stage, commit, push, publish, or upload files from `context/`.
- Do not rename remotes or repositories without explicit approval.
- Do not push without explicit approval.
- Do not delete user data.
- Do not rewrite history.
- Do not modify Git LFS settings.
- Make focused local commits after verified milestone slices.
- Include task ID in commit messages.
- Record commit SHA in evidence and TODO.
- Never have two agents edit the same file concurrently.

---

# 22. Mandatory stop conditions

Stop the affected task and report a blocker when:

- required files cannot be located,
- archive corruption is detected,
- the college schema materially differs from the description,
- units remain unknown and affect targets or thresholds,
- full-test RUL derivation differs from verified counts,
- a result depends on random row/window splitting,
- future data leaks into preprocessing,
- an unsupported physical fault claim is required,
- a destructive or remote action needs approval,
- a plugin name or command cannot be verified,
- a third implementation attempt fails,
- disk or memory requirements are unsafe,
- a dependency would add major complexity without measurable benefit.

Do not guess around these conditions.

---

# 23. Phase A execution instruction

For the first run, perform only:

1. Read-only repository and environment discovery.
2. Tool, plugin, agent, skill, hook, MCP, and model inventory.
3. Read-only dataset and archive audit.
4. Source-document audit.
5. Foundation folder creation.
6. Full population of the required foundation documents.
7. Initial `TODO.md`.
8. Independent consistency and scientific-validity review.
9. Ponytail review and milestone audit.
10. One focused local foundation commit if the repository is clean and local commits are permitted.

Do not generate feature or model code in Phase A.

After Phase A passes, continue automatically to the next unblocked M1 task unless a mandatory stop condition applies.

Do not generate the entire project in one uncontrolled pass.

---

# 24. Required response after Phase A

Return only these sections:

1. Files created or changed.
2. Dataset facts confirmed.
3. Discrepancies and uncertainties.
4. Corrections made to the original approach.
5. Chosen minimal architecture.
6. Tool, plugin, skill, agent, worktree, and model routing actually used.
7. Verification evidence and commit SHA.
8. Current blockers.
9. Exact next milestone and task IDs.

Do not claim that the application is built after the foundation phase. Do not report fake model metrics.

---

# 25. Definition of done

The capstone is complete only when:

- raw data remain immutable,
- both adapters are tested,
- large-file processing is bounded in memory,
- features are reproducible and cached,
- DuckDB metadata and Parquet lineage are reproducible,
- health indicators are compared quantitatively,
- RUL evaluation is grouped and leakage-safe,
- the single-run college limitation is explicit,
- stage classification is not misrepresented as fault diagnosis,
- optional deep learning is accepted or rejected by evidence,
- RAG sources are traceable,
- maintenance claims include citations,
- the LLM cannot alter numeric predictions,
- deterministic reporting works without Ollama,
- Streamlit uses saved artifacts,
- PDF generation works,
- tests pass on clean fixtures,
- setup commands work in a fresh environment,
- documentation agrees with the implementation,
- final Ponytail and independent scientific audits have no unresolved critical finding.

## Begin with Phase A now.

# 26. ACCELERATED REVIEW TRACK OVERRIDE

## Review deadline: 25 July 2026

This section temporarily supersedes the earlier Phase A-only sequencing and the normal M0-to-M9 pace.

The user has a project review on 25 July 2026 and needs a demonstrable working prototype, not only planning documents.

The immediate target is:

```text
M0 foundation
-> M1 dataset adapters
-> M2 feature pipeline
-> M3 health indicator
-> M4 baseline RUL model
-> minimal M8 Streamlit dashboard
```

Do not stop after Phase A unless a mandatory blocker exists.

Do not wait for user confirmation between these milestones.

Continue automatically through the accelerated review track, one verified task at a time.

The review build must be treated as an MVP demonstration, not as the final completed capstone.

## 26.1 Review-ready definition

By the review, the repository should demonstrate this working path:

```text
Dataset selection
-> data loading
-> signal preview
-> feature extraction
-> FFT
-> health indicator
-> RUL prediction
-> metrics
-> Streamlit dashboard
```

The review version is considered ready only when a faculty evaluator can:

1. Start the Streamlit application.
2. Select either a prepared FEMTO sample or a prepared college-data sample.
3. View X-axis and Y-axis vibration plots.
4. View temperature trends when temperature is available.
5. View an FFT spectrum.
6. View extracted feature values.
7. View a bearing health indicator or degradation trend.
8. View a baseline RUL prediction.
9. View model evaluation metrics generated from real code.
10. See the architecture and methodology documentation.
11. Run the demo again without retraining from scratch.
12. Use backup screenshots or saved outputs if the live demo environment fails.

## 26.2 Deadline priorities

Use this priority order until the review:

### Priority 1: Working and scientifically defensible

Must complete:

- real dataset inspection,
- correct adapters,
- bounded-memory processing,
- tested feature formulas,
- leakage-safe splits,
- at least one valid health indicator,
- at least one baseline RUL model,
- saved artifacts,
- a working dashboard.

### Priority 2: Clear demonstration

Must complete:

- visible signal plots,
- FFT plot,
- health trend,
- RUL output,
- basic metrics,
- concise architecture diagram,
- concise README commands,
- prepared demo dataset or cached results.

### Priority 3: Nice to have

Complete only if Priority 1 and Priority 2 are stable:

- degradation-stage classification,
- second RUL baseline,
- feature-importance plot,
- deterministic maintenance summary,
- PDF report.

### Defer until after review

Do not spend review-track time on:

- spectral-kurtosis ConvNet,
- full 1D CNN paper reproduction,
- LSTM monitoring agent,
- LangGraph orchestration,
- multi-agent runtime architecture,
- full RAG pipeline,
- Ollama model benchmarking,
- alerting,
- cloud deployment,
- CMMS integration,
- authentication,
- microservices,
- broad hyperparameter searches,
- polished final research-paper formatting.

Mark these tasks `DEFERRED_AFTER_REVIEW`, not failed.

## 26.3 Documentation time box

The original prompt requires substantial foundation documentation.

For the review track:

- complete all required documents,
- but keep them concise and implementation-oriented,
- do not spend more than four total engineering hours on M0 documentation,
- do not block feature implementation for cosmetic documentation improvements,
- update documents incrementally after working code exists.

Minimum M0 documents required before M1:

```text
CLAUDE.md
AGENTS.md
TODO.md
docs/prd.md
docs/architecture.md
docs/milestone.md
docs/database-structure.md
docs/database-schema.md
docs/data-contract.md
docs/dataset-audit.md
docs/decisions.md
```

The following may begin as concise but complete review-track versions and be expanded after 25 July:

```text
docs/roadmap.md
docs/dataset-card.md
docs/tooling-inventory.md
docs/research-source-audit.md
docs/risk-register.md
```

Do not create empty placeholders.

## 26.4 Accelerated milestone schedule

Use the actual current date from the system.

The intended schedule is:

### 21 July 2026: M0 and M1

Complete:

- repository and tool inventory,
- local `context/` verification,
- `.gitignore` verification,
- foundation documents,
- archive/file manifest,
- representative dataset audit,
- FEMTO parser,
- college parser,
- tiny fixtures,
- parser tests.

Exit evidence:

```text
artifacts/evidence/REVIEW-M0/
artifacts/evidence/REVIEW-M1/
```

### 22 July 2026: M2

Complete:

- time-domain features,
- FFT features,
- temperature features,
- chunk-safe college processing,
- FEMTO acquisition feature extraction,
- Parquet feature output,
- feature-formula tests,
- sample degradation plots.

Exit evidence:

```text
artifacts/evidence/REVIEW-M2/
```

### 23 July 2026: M3 and M4

Complete:

- transparent health indicator,
- training-only scaling,
- FEMTO RUL targets,
- naive baseline,
- ExtraTreesRegressor or RandomForestRegressor baseline,
- grouped validation by bearing,
- college walk-forward demonstration,
- saved selected model,
- generated metrics and plots.

Exit evidence:

```text
artifacts/evidence/REVIEW-M3/
artifacts/evidence/REVIEW-M4/
```

### 24 July 2026: minimal M8 and review package

Complete:

- Streamlit dashboard,
- cached sample outputs,
- model loading,
- signal plots,
- FFT,
- health indicator,
- RUL prediction,
- metrics page,
- architecture diagram,
- README run commands,
- review screenshots,
- optional short screen recording instructions,
- backup static report.

Exit evidence:

```text
artifacts/evidence/REVIEW-M8/
reports/verification/review-readiness.md
```

### 25 July 2026: stabilization only

Allowed work:

- fix crashes,
- repair paths,
- improve labels,
- verify environment,
- rerun tests,
- regenerate screenshots,
- rehearse demo sequence,
- prepare backup outputs.

Do not begin major new features on 25 July.

## 26.5 Review-track task routing

### Cheapest model

Use for:

- repository inventory,
- archive manifests,
- documentation synchronization,
- TODO updates,
- README commands,
- screenshot checklist,
- final review checklist.

### General implementation model

Use for:

- dataset parsers,
- chunked processing,
- features,
- model training,
- Streamlit,
- tests,
- debugging.

### Highest reasoning model

Use only for:

- initial leakage audit,
- ambiguous target construction,
- final review-readiness scientific audit,
- a blocker that survives two implementation attempts.

Do not spend expensive-model tokens on routine documentation.

## 26.6 Simplified review architecture

For the review build, prefer:

```text
raw data
-> adapter
-> features
-> Parquet
-> saved sklearn pipeline
-> Streamlit
```

DuckDB metadata is still useful, but do not let database polish block the working pipeline.

RAG and Ollama must not be on the review critical path.

A deterministic maintenance-summary template may be added after the core pipeline works.

## 26.7 Model scope for the review

Use simple, defensible models.

Required:

- naive RUL baseline,
- one tree-based RUL model.

Preferred second model if time allows:

- ExtraTreesRegressor,
- RandomForestRegressor.

Do not start with deep learning.

Use small, documented model settings.

Do not run expensive searches.

The first review objective is a valid baseline, not the best possible score.

## 26.8 Dataset processing scope for the review

### FEMTO

Use the complete learning bearings for baseline model development.

Use grouped evaluation by bearing.

Do not evaluate against hidden full-test continuation until the model pipeline is frozen.

### College data

Because the collection is very large:

1. Prove chunked processing on early, middle, and late files.
2. Build a review sample across the life trajectory.
3. Generate a health trend across representative hours.
4. Process the full collection only if disk, runtime, and memory estimates are safe.
5. Do not let full-dataset processing block the dashboard.

The review dashboard may use cached representative college features, provided they were generated by the real pipeline and clearly labeled.

## 26.9 Dashboard shortcuts that are allowed

For the review only, the dashboard may load:

- cached feature Parquet files,
- saved model artifacts,
- precomputed FFT examples,
- precomputed evaluation metrics,
- representative raw-signal samples.

It must clearly distinguish:

- live upload processing,
- cached benchmark results,
- representative review samples.

Do not pretend cached results were generated live.

Do not train models when the dashboard starts.

## 26.10 Review evidence package

Create:

```text
reports/verification/review-readiness.md
```

It must include:

- exact run commands,
- environment details,
- files and artifacts required,
- completed capabilities,
- deferred capabilities,
- known limitations,
- latest test results,
- dataset samples used,
- model metrics,
- screenshots produced,
- backup demo plan,
- five-minute demo sequence,
- likely faculty questions and evidence-based answers.

Also create:

```text
reports/verification/review-demo-script.md
```

The demo script should fit within five to eight minutes:

1. Problem and dataset.
2. Architecture.
3. Raw signal and FFT.
4. Feature extraction.
5. Health indicator.
6. RUL prediction.
7. Metrics.
8. Limitations.
9. Next steps after review.

## 26.11 Required progress reporting

At the end of each accelerated milestone, report:

1. Percentage of review target completed.
2. Task IDs completed.
3. Working features.
4. Tests passed.
5. Metrics generated.
6. Current blockers.
7. Exact next task.
8. Whether the July 25 review target is still achievable.

Do not report percentage based on files created.

Use this review-weighted completion model:

| Area                                 | Weight |
| ------------------------------------ | -----: |
| Foundation and dataset understanding |    15% |
| Dataset adapters                     |    15% |
| Feature pipeline                     |    20% |
| Health indicator                     |    15% |
| RUL model and evaluation             |    20% |
| Dashboard and demo package           |    15% |

A document-only repository cannot exceed 15%.

## 26.12 Review-track completion gate

The accelerated track is complete when:

- M0 foundation is sufficient,
- M1 adapters work,
- M2 features are generated,
- M3 health indicator is shown,
- M4 RUL baseline is evaluated,
- minimal M8 dashboard starts successfully,
- saved artifacts load without retraining,
- review-readiness report exists,
- backup screenshots exist,
- no hidden-test leakage exists,
- no unsupported physical fault claims exist.

After the review, return to the normal M5-to-M9 roadmap.

## 26.13 Immediate execution instruction

Begin the accelerated review track now.

Do not stop after foundation documentation.

Continue automatically through:

```text
M0 -> M1 -> M2 -> M3 -> M4 -> minimal M8
```

Stop only for:

- a mandatory scientific blocker,
- missing required local files,
- unsafe disk or memory requirements,
- destructive action requiring approval,
- inability to verify the hidden-test structure,
- a third failed implementation attempt.

When a noncritical optional feature fails, defer it and continue with the core review path.

The highest priority is a stable, honest, demonstrable RUL prototype by 25 July 2026.

---

# 27. SAFETY, RECOVERY, AND CORRECT WORKSPACE OVERRIDE

## Effective immediately after the interrupted 21 July 2026 session

This section has the highest priority and supersedes any earlier instruction that could be interpreted as permission to clean, deduplicate, relocate, rename, overwrite, or delete files.

The previous Claude Code session was started inside the large Git LFS data repository rather than the application code repository. It also found duplicate large data and low disk space. The user has now freed disk space, and the D: drive has approximately 41 GB free.

The current objective is to recover safely and resume the accelerated review track without altering source material.

## 27.1 Absolute no-delete rule

You are not authorized to delete, move, rename, overwrite, truncate, replace, clean, deduplicate, archive, or relocate any existing user file or folder.

This applies to every path, including:

```text
context/
Vibration_Bearing_RuntoFailure/
Training_set.zip
Validation_Set.zip
Test_set.7z
all PDF files
all DOCX files
all TXT files
all images
all Git LFS files
all existing repositories
```

Forbidden commands and equivalent operations include:

```text
rm
rmdir
del
erase
Remove-Item
Move-Item
git clean
git reset --hard
git checkout -- <path>
git restore <path>
git rm
filesystem cleanup tools
automatic duplicate removal
```

Do not use a destructive command merely because a file appears duplicated, ignored, deleted in Git status, unnecessary, large, or outside the desired repository structure.

If duplicate data exists, leave it untouched and record the paths in `docs/dataset-audit.md`.

Only the user may decide whether to remove a duplicate.

## 27.2 Existing `context/` content is immutable

The existing `context/` folder is user-owned, local reference material.

Treat it as strictly read-only.

You may:

- list files,
- read files,
- calculate checksums,
- extract small text or metadata for analysis,
- reference paths from configuration.

You may not:

- create files inside it,
- edit files inside it,
- rename files inside it,
- reorganize it,
- delete duplicates,
- convert or replace documents,
- move its contents into another folder,
- stage or commit its contents.

PDFs, DOCX files, TXT files, images, prompts, and datasets inside `context/` must remain exactly where they are.

If `context/README.md` or `context/MANIFEST.md` does not exist, do not create it inside `context/`. Instead create a tracked, non-destructive inventory at:

```text
docs/context-inventory.md
```

inside the code repository.

## 27.3 Recovery audit before any development

The interrupted session may have changed or removed files.

Before creating project code, perform a read-only recovery audit.

Do not repair or restore anything automatically.

Report:

1. Current working directory.
2. Current Git repository name and remote.
3. `git status --short`.
4. Every deleted, missing, or modified tracked path.
5. A bounded inventory of all PDFs, DOCX files, TXT files, ZIP files, 7z files, and images under the existing `context/` folder.
6. File names expected from the project prompt that are currently missing.
7. Whether each missing file was:
   - tracked by Git,
   - ignored or untracked,
   - found elsewhere on D:,
   - likely recoverable from the Windows Recycle Bin,
   - available from its original source.
8. The two or more locations containing the 129 college CSV files, if duplicates exist.
9. Current free disk space.
10. Any background process from the previous session that is still running.

Use bounded searches. Do not recursively hash or parse all 18 GB of CSV content during this recovery step.

If a PDF or other context document is missing, stop only the source-document audit that requires it. Continue with tasks that do not depend on that document after reporting the missing file.

Do not treat a missing optional paper as permission to delete or recreate other files.

## 27.4 Correct repository separation

There are two different repositories or work areas:

### A. Source-data repository

The existing Git LFS repository contains or references the large bearing dataset.

Treat it as read-only for this capstone build.

Do not:

- create application source code there,
- change `.gitattributes`,
- change Git LFS configuration,
- stage deleted CSV files,
- commit cleanup,
- repair its working tree,
- change its branch,
- change its remote,
- push it.

### B. Application code repository

Use this local path unless an existing code repository is found:

```text
D:\capstone\bearing-rul-predictive-maintenance
```

If the folder does not exist, create only this new folder.

Creating this new application folder is authorized.

Inside it:

- initialize a local Git repository only if no Git repository already exists,
- create project code and documentation,
- make local commits,
- never configure or push a remote,
- never copy raw datasets into it.

If another valid application code repository already exists, report it and use it instead of creating a duplicate.

Do not continue application development while the current working directory is the Git LFS data repository.

Change into the application code repository first and confirm the path.

## 27.5 VS Code workspace arrangement

The recommended VS Code multi-root workspace contains:

1. `D:\capstone\bearing-rul-predictive-maintenance`
2. the existing `context/` folder as a reference folder

The first folder is writable.

The `context/` folder is read-only by policy.

Do not add the complete large-data repository as the primary code workspace.

Do not assume that being visible in VS Code gives permission to edit a file.

## 27.6 Path configuration instead of copying

Create:

```text
config/data_paths.toml
```

inside the application code repository.

It should point to existing local data and context paths, for example:

```toml
[paths]
context_root = "D:/capstone/data/data collection git/context"
college_data = "<DISCOVERED_CANONICAL_PATH_TO_Vibration_Bearing_RuntoFailure>"
femto_training = "<DISCOVERED_PATH_TO_Training_set.zip>"
femto_test = "<DISCOVERED_PATH_TO_Test_set.7z>"
femto_full_test = "<DISCOVERED_PATH_TO_Validation_Set.zip>"
```

Use the actual discovered paths. Do not guess.

Also create a sanitized tracked example:

```text
config/data_paths.example.toml
```

Do not commit private absolute paths from `config/data_paths.toml`.

Add this to the application repository `.gitignore`:

```gitignore
config/data_paths.toml
artifacts/
data/processed/
data/interim/
*.joblib
*.pkl
*.faiss
```

The local `context/` folder is outside the application repository, so it does not need to be moved or copied.

## 27.7 Disk-space policy

The D: drive currently has approximately 41 GB free.

This is sufficient for the review MVP only if processing remains bounded.

Until after the 25 July review:

- do not extract all archives when streaming access works,
- do not duplicate raw data,
- do not generate raw window files,
- do not process all college CSVs merely to prove the pipeline,
- do not install large deep-learning frameworks,
- do not download large Ollama models,
- do not build large vector indexes,
- do not create multiple copies of feature outputs,
- do not run broad hyperparameter searches.

Before any task estimated to write more than 2 GB:

1. estimate output size,
2. report the estimate,
3. use an existing approved artifact directory,
4. continue only when at least 15 GB will remain free afterward.

For the review, use representative early, middle, and late college files plus the complete FEMTO learning set where feasible.

## 27.8 Git policy clarification

The user permits local commits in the application code repository.

The user does not permit GitHub pushes.

Therefore:

- local `git add` and `git commit` are allowed only in the application code repository,
- `git push` is forbidden,
- creating or changing a remote is forbidden,
- data repositories and `context/` are read-only,
- never stage raw datasets,
- never stage private path configuration,
- never commit from the Git LFS data repository.

Before every commit, show:

```text
repository path
branch
git status --short
files to be committed
```

Then commit locally.

Do not ask for permission for ordinary non-destructive code edits inside the application repository.

Ask before any action outside the application repository that would modify an existing file.

## 27.9 MCP authentication warning

An unauthenticated MCP server is not a blocker unless the active task specifically requires that server.

Do not spend review-track time authenticating unrelated MCP tools.

Record the unavailable MCP server and continue using local filesystem and shell tools.

Never send local project files to an external MCP server without explicit user approval.

## 27.10 Corrected immediate execution sequence

Resume in this exact order:

### Step 1: Read-only recovery report

Produce the recovery audit from section 27.3.

Do not modify existing files.

### Step 2: Establish the application repository

Use or create:

```text
D:\capstone\bearing-rul-predictive-maintenance
```

Do not initialize or edit the data repository.

### Step 3: Create path configuration

Reference existing data and context paths.

Do not copy source files.

### Step 4: Run accelerated M0

Create concise foundation documents in the application repository.

Time-box M0 documentation to a maximum of two hours from this resumed session.

### Step 5: Continue automatically

Continue through:

```text
M1 adapters
-> M2 features
-> M3 health indicator
-> M4 baseline RUL model
-> minimal M8 dashboard
```

Do not stop after documentation unless a mandatory blocker directly prevents code execution.

## 27.11 Review MVP simplification

For the 25 July review, the required output is:

```text
real data adapter
-> feature extraction
-> FFT
-> health indicator
-> RUL baseline
-> saved artifacts
-> Streamlit demo
```

The following are not on the critical path:

```text
RAG
Ollama
CNN
LSTM
LangGraph
Graphify
full college-dataset processing
PDF report
alerting
cloud deployment
```

Ponytail may be used only after its actual installed command is verified.

If Ponytail, Caveman, Graphify, a subagent, a skill, or an MCP server does not work immediately, record it and continue without it. Tooling must not block the project.

## 27.12 No background destructive work

Do not launch background scans or cleanup processes that continue after asking the user a question.

Before starting a background command, verify that it is:

- read-only,
- bounded,
- necessary,
- easy to stop.

Report the command and process ID.

Do not leave duplicate searches, archive extraction, hashing, model training, or data processing running after the session is interrupted.

## 27.13 Required response after recovery and setup

Return:

1. Exact application repository path.
2. Exact source-data paths.
3. Context files found.
4. Missing files.
5. Any files changed by the interrupted session.
6. Free disk space.
7. Confirmation that no file was deleted, moved, renamed, or overwritten during recovery.
8. Files created only inside the application repository.
9. Current review completion percentage.
10. Next active task ID.

Then continue automatically unless a truly destructive decision is required.
