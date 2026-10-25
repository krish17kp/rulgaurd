# prompts.md

These prompts are designed to execute every goal in `goals.md`.

## Mandatory model rule

- **Implementation/build work:** use the model router in `model.md`. Routine implementation may use Claude Sonnet 5 or GPT-6 Sol, and narrow mechanical work may use a cheaper model where `model.md` allows it.
- **Testing, verification, scientific review, acceptance, and merge approval:** **MUST use a high-end model only: Claude Opus 5 or GPT-6 Astra.**
- Claude Haiku, Claude Sonnet, GPT-6 Luna, GPT-6 Sol, or other lower/default worker models may help build, but they **must not be the final verifier for any goal**.
- The implementation agent is not allowed to mark its own work complete. Completion requires a separate high-model verification pass.
- Every implementation prompt must be executed in an isolated branch/worktree when autonomous or overnight work is involved.
- Before implementing anything, read `goals.md`, `model.md`, relevant project documentation, current tests, and the code paths affected by the task.
- Preserve existing validated scientific behavior unless the goal explicitly requires a scientific change.
- Never fabricate prediction performance, model support, dataset compatibility, confidence, sample rate, units, or test results.

## Universal High-Model Acceptance Prompt

Use this after **every** implementation task, in addition to that task's specific test prompt:

> **MODEL REQUIREMENT: Run this verification only with Claude Opus 5 or GPT-6 Astra. Do not delegate final testing or acceptance to a lower-end model.** Independently inspect the implementation and its Git diff. Reconstruct the goal from `goals.md` instead of trusting the worker's summary. Run all relevant existing tests plus new targeted tests, test failure paths and edge cases, and check for regressions, security issues, scientific inconsistency, data leakage, unsupported claims, and accidental scope changes. Do not mark PASS because the code looks reasonable. A PASS requires executed evidence. If any defect is found, report the exact reproduction, affected files, severity, and required fix. After fixes, rerun the affected tests and then the required integration/full suite. Output exactly: `GOAL`, `VERIFIER MODEL`, `TESTS RUN`, `RESULTS`, `DEFECTS`, `REGRESSIONS`, `SCIENTIFIC/SECURITY CHECK`, and final `PASS` or `FAIL`.

---

## Goal 1: Replace Streamlit with a proper production-style web application.

### Implementation prompt

> Read `goals.md` and `model.md` first. Work only on **Goal 1: Replace Streamlit with a proper production-style web application.** Inspect the current repository and reuse existing correct project logic rather than rebuilding blindly. Inspect the existing Streamlit application and extract its actual product capabilities before replacing it. Build a proper web architecture with a modern frontend and API-based backend while preserving existing working analysis/prediction behavior. Do not simply wrap Streamlit or embed it. Remove Streamlit from the production path only after equivalent functionality exists and the old implementation can remain as a temporary reference until parity is proven. Add or update targeted tests for the code you implement, but do **not** self-certify the goal as complete. Keep the change scoped, document important design decisions, preserve backward compatibility where practical, and finish by reporting changed files, commands run, tests run, known limitations, and the commit/branch or worktree containing the work. Hand the result to the high-model verifier.

### High-model testing / acceptance prompt

> **Use Claude Opus 5 or GPT-6 Astra only. Lower-end models are prohibited for final testing.** Independently verify **Goal 1: Replace Streamlit with a proper production-style web application.** Do not trust the implementation agent's claims. Independently verify that the production path no longer depends on Streamlit. Compare old and new functionality, run frontend/backend integration tests, inspect routes and dependencies, and prove that core analysis/prediction functions still work without launching Streamlit. Inspect the Git diff for unintended changes and run the relevant regression/integration tests after targeted checks. If anything fails, return `FAIL` with exact evidence and required fixes; after fixes, rerun tests. Mark `PASS` only when the implementation satisfies the goal with executed evidence and does not weaken scientific correctness, security, or existing functionality.

---

## Goal 2: Build a polished, professional frontend suitable for an industrial predictive-maintenance product.

### Implementation prompt

> Read `goals.md` and `model.md` first. Work only on **Goal 2: Build a polished, professional frontend suitable for an industrial predictive-maintenance product.** Inspect the current repository and reuse existing correct project logic rather than rebuilding blindly. Create a coherent visual system for an industrial predictive-maintenance product: typography, spacing, navigation, cards, charts, status semantics, upload flows, prediction summaries, and diagnostics. Avoid generic template-dashboard styling and avoid decorative UI that obscures scientific information. Use reusable components and establish a consistent design system rather than page-specific CSS hacks. Add or update targeted tests for the code you implement, but do **not** self-certify the goal as complete. Keep the change scoped, document important design decisions, preserve backward compatibility where practical, and finish by reporting changed files, commands run, tests run, known limitations, and the commit/branch or worktree containing the work. Hand the result to the high-model verifier.

### High-model testing / acceptance prompt

> **Use Claude Opus 5 or GPT-6 Astra only. Lower-end models are prohibited for final testing.** Independently verify **Goal 2: Build a polished, professional frontend suitable for an industrial predictive-maintenance product.** Do not trust the implementation agent's claims. Review the frontend as both a UI system and a working product. Test consistency, accessibility, information hierarchy, chart legibility, empty/loading/error states, keyboard behavior where relevant, and verify that every displayed scientific value is sourced from real API data rather than placeholders. Inspect the Git diff for unintended changes and run the relevant regression/integration tests after targeted checks. If anything fails, return `FAIL` with exact evidence and required fixes; after fixes, rerun tests. Mark `PASS` only when the implementation satisfies the goal with executed evidence and does not weaken scientific correctness, security, or existing functionality.

---

## Goal 3: Deploy the frontend using a modern hosting platform such as Vercel.

### Implementation prompt

> Read `goals.md` and `model.md` first. Work only on **Goal 3: Deploy the frontend using a modern hosting platform such as Vercel.** Inspect the current repository and reuse existing correct project logic rather than rebuilding blindly. Prepare the frontend for Vercel-compatible deployment, including build configuration, environment-variable handling, API base URLs, production build checks, and deployment documentation. Do not place large ML artifacts or Python inference dependencies inside the frontend deployment. Verify that a clean production build succeeds locally before treating the task as complete. Add or update targeted tests for the code you implement, but do **not** self-certify the goal as complete. Keep the change scoped, document important design decisions, preserve backward compatibility where practical, and finish by reporting changed files, commands run, tests run, known limitations, and the commit/branch or worktree containing the work. Hand the result to the high-model verifier.

### High-model testing / acceptance prompt

> **Use Claude Opus 5 or GPT-6 Astra only. Lower-end models are prohibited for final testing.** Independently verify **Goal 3: Deploy the frontend using a modern hosting platform such as Vercel.** Do not trust the implementation agent's claims. Run a clean production frontend build, validate environment-variable handling, inspect bundle/runtime assumptions, verify API connectivity configuration, and test the deployed or deployment-equivalent build. Fail the task if local dev works but production build/deploy does not. Inspect the Git diff for unintended changes and run the relevant regression/integration tests after targeted checks. If anything fails, return `FAIL` with exact evidence and required fixes; after fixes, rerun tests. Mark `PASS` only when the implementation satisfies the goal with executed evidence and does not weaken scientific correctness, security, or existing functionality.

---

## Goal 4: Keep the Python/ML prediction service separate from the frontend deployment where required.

### Implementation prompt

> Read `goals.md` and `model.md` first. Work only on **Goal 4: Keep the Python/ML prediction service separate from the frontend deployment where required.** Inspect the current repository and reuse existing correct project logic rather than rebuilding blindly. Define and implement a clean separation between the web frontend and the Python/ML inference service. Establish an explicit API contract, request/response schemas, error schemas, model/version metadata, and timeouts. Keep scientific preprocessing and inference server-side so the browser never becomes the source of truth for model logic. Add or update targeted tests for the code you implement, but do **not** self-certify the goal as complete. Keep the change scoped, document important design decisions, preserve backward compatibility where practical, and finish by reporting changed files, commands run, tests run, known limitations, and the commit/branch or worktree containing the work. Hand the result to the high-model verifier.

### High-model testing / acceptance prompt

> **Use Claude Opus 5 or GPT-6 Astra only. Lower-end models are prohibited for final testing.** Independently verify **Goal 4: Keep the Python/ML prediction service separate from the frontend deployment where required.** Do not trust the implementation agent's claims. Verify service separation by inspecting imports, runtime dependencies, network contracts, and failure behavior. Ensure frontend code cannot silently execute or duplicate scientific model logic and that backend errors are correctly represented at the frontend boundary. Inspect the Git diff for unintended changes and run the relevant regression/integration tests after targeted checks. If anything fails, return `FAIL` with exact evidence and required fixes; after fixes, rerun tests. Mark `PASS` only when the implementation satisfies the goal with executed evidence and does not weaken scientific correctness, security, or existing functionality.

---

## Goal 5: Build a complete dashboard for machine health and predictive-maintenance results.

### Implementation prompt

> Read `goals.md` and `model.md` first. Work only on **Goal 5: Build a complete dashboard for machine health and predictive-maintenance results.** Inspect the current repository and reuse existing correct project logic rather than rebuilding blindly. Build the main dashboard around real project outputs: machine/dataset summary, current health state, RUL result, degradation curve, key sensor statistics, recent analyses, warnings, and diagnostic detail. Every displayed value must trace back to actual backend data, not placeholders or invented demo numbers. Add or update targeted tests for the code you implement, but do **not** self-certify the goal as complete. Keep the change scoped, document important design decisions, preserve backward compatibility where practical, and finish by reporting changed files, commands run, tests run, known limitations, and the commit/branch or worktree containing the work. Hand the result to the high-model verifier.

### High-model testing / acceptance prompt

> **Use Claude Opus 5 or GPT-6 Astra only. Lower-end models are prohibited for final testing.** Independently verify **Goal 5: Build a complete dashboard for machine health and predictive-maintenance results.** Do not trust the implementation agent's claims. Exercise the dashboard with representative healthy, degrading, failed/near-failure, invalid, and unsupported fixtures. Confirm every widget is accurate, linked to backend results, and resilient to missing optional fields. Inspect the Git diff for unintended changes and run the relevant regression/integration tests after targeted checks. If anything fails, return `FAIL` with exact evidence and required fixes; after fixes, rerun tests. Mark `PASS` only when the implementation satisfies the goal with executed evidence and does not weaken scientific correctness, security, or existing functionality.

---

## Goal 6: Show Remaining Useful Life (RUL) prediction clearly in the frontend.

### Implementation prompt

> Read `goals.md` and `model.md` first. Work only on **Goal 6: Show Remaining Useful Life (RUL) prediction clearly in the frontend.** Inspect the current repository and reuse existing correct project logic rather than rebuilding blindly. Design and implement the RUL result view so the predicted remaining life is prominent, unit-labeled, model-versioned, and contextualized. Include actual supported reliability/uncertainty information only where the backend can justify it. Never display a fabricated confidence percentage. Add or update targeted tests for the code you implement, but do **not** self-certify the goal as complete. Keep the change scoped, document important design decisions, preserve backward compatibility where practical, and finish by reporting changed files, commands run, tests run, known limitations, and the commit/branch or worktree containing the work. Hand the result to the high-model verifier.

### High-model testing / acceptance prompt

> **Use Claude Opus 5 or GPT-6 Astra only. Lower-end models are prohibited for final testing.** Independently verify **Goal 6: Show Remaining Useful Life (RUL) prediction clearly in the frontend.** Do not trust the implementation agent's claims. Test RUL rendering with known fixture predictions, units, edge values, failures, and unsupported inputs. Confirm rounding/display cannot materially change interpretation and that no unsupported confidence value appears. Inspect the Git diff for unintended changes and run the relevant regression/integration tests after targeted checks. If anything fails, return `FAIL` with exact evidence and required fixes; after fixes, rerun tests. Mark `PASS` only when the implementation satisfies the goal with executed evidence and does not weaken scientific correctness, security, or existing functionality.

---

## Goal 7: Show machine degradation and health-indicator trends clearly.

### Implementation prompt

> Read `goals.md` and `model.md` first. Work only on **Goal 7: Show machine degradation and health-indicator trends clearly.** Inspect the current repository and reuse existing correct project logic rather than rebuilding blindly. Implement degradation and Health Indicator visualizations using the project's actual HI values and lifecycle ordering. Show direction, stage/state, timestamps or sample progression, and relevant thresholds if they are scientifically defined. Ensure the plot does not invert or normalize the HI differently from the backend's validated logic. Add or update targeted tests for the code you implement, but do **not** self-certify the goal as complete. Keep the change scoped, document important design decisions, preserve backward compatibility where practical, and finish by reporting changed files, commands run, tests run, known limitations, and the commit/branch or worktree containing the work. Hand the result to the high-model verifier.

### High-model testing / acceptance prompt

> **Use Claude Opus 5 or GPT-6 Astra only. Lower-end models are prohibited for final testing.** Independently verify **Goal 7: Show machine degradation and health-indicator trends clearly.** Do not trust the implementation agent's claims. Compare rendered HI/degradation curves to backend/reference values point-by-point on fixed fixtures. Verify ordering, normalization, stage labels, axes, units, and threshold rendering. Inspect the Git diff for unintended changes and run the relevant regression/integration tests after targeted checks. If anything fails, return `FAIL` with exact evidence and required fixes; after fixes, rerun tests. Mark `PASS` only when the implementation satisfies the goal with executed evidence and does not weaken scientific correctness, security, or existing functionality.

---

## Goal 8: Show FFT, signal-processing outputs, extracted features, and relevant diagnostics.

### Implementation prompt

> Read `goals.md` and `model.md` first. Work only on **Goal 8: Show FFT, signal-processing outputs, extracted features, and relevant diagnostics.** Inspect the current repository and reuse existing correct project logic rather than rebuilding blindly. Expose relevant signal-analysis results in the UI: FFT/spectrum, time-domain statistics, extracted features, and diagnostics that are genuinely produced by the pipeline. Keep sampling-rate-dependent axes correct and label units. Do not create visually impressive but scientifically meaningless charts. Add or update targeted tests for the code you implement, but do **not** self-certify the goal as complete. Keep the change scoped, document important design decisions, preserve backward compatibility where practical, and finish by reporting changed files, commands run, tests run, known limitations, and the commit/branch or worktree containing the work. Hand the result to the high-model verifier.

### High-model testing / acceptance prompt

> **Use Claude Opus 5 or GPT-6 Astra only. Lower-end models are prohibited for final testing.** Independently verify **Goal 8: Show FFT, signal-processing outputs, extracted features, and relevant diagnostics.** Do not trust the implementation agent's claims. Validate FFT and feature displays against independently recomputed reference outputs. Specifically test frequency-axis correctness at known sampling rates and verify that missing sample-rate metadata blocks invalid spectral interpretation. Inspect the Git diff for unintended changes and run the relevant regression/integration tests after targeted checks. If anything fails, return `FAIL` with exact evidence and required fixes; after fixes, rerun tests. Mark `PASS` only when the implementation satisfies the goal with executed evidence and does not weaken scientific correctness, security, or existing functionality.

---

## Goal 9: Support dataset upload directly from the web application.

### Implementation prompt

> Read `goals.md` and `model.md` first. Work only on **Goal 9: Support dataset upload directly from the web application.** Inspect the current repository and reuse existing correct project logic rather than rebuilding blindly. Implement a secure dataset-upload flow from the browser to the backend with file-type validation, size limits, progress state, cancellation/failure handling where practical, and a clear analysis lifecycle. The frontend must not assume upload success until the backend confirms it. Add or update targeted tests for the code you implement, but do **not** self-certify the goal as complete. Keep the change scoped, document important design decisions, preserve backward compatibility where practical, and finish by reporting changed files, commands run, tests run, known limitations, and the commit/branch or worktree containing the work. Hand the result to the high-model verifier.

### High-model testing / acceptance prompt

> **Use Claude Opus 5 or GPT-6 Astra only. Lower-end models are prohibited for final testing.** Independently verify **Goal 9: Support dataset upload directly from the web application.** Do not trust the implementation agent's claims. Test valid uploads, wrong extensions, corrupted files, oversized files, interrupted requests, backend rejection, repeated uploads, and safe filenames. Inspect server behavior for path traversal or unsafe file handling. Inspect the Git diff for unintended changes and run the relevant regression/integration tests after targeted checks. If anything fails, return `FAIL` with exact evidence and required fixes; after fixes, rerun tests. Mark `PASS` only when the implementation satisfies the goal with executed evidence and does not weaken scientific correctness, security, or existing functionality.

---

## Goal 10: Automatically inspect the uploaded dataset structure.

### Implementation prompt

> Read `goals.md` and `model.md` first. Work only on **Goal 10: Automatically inspect the uploaded dataset structure.** Inspect the current repository and reuse existing correct project logic rather than rebuilding blindly. Build a dataset-inspection stage that determines files, rows, columns, datatypes, missing values, likely timestamp/order fields, candidate sensor columns, metadata, and structural anomalies before preprocessing. Return a structured inspection report that later pipeline stages can consume. Add or update targeted tests for the code you implement, but do **not** self-certify the goal as complete. Keep the change scoped, document important design decisions, preserve backward compatibility where practical, and finish by reporting changed files, commands run, tests run, known limitations, and the commit/branch or worktree containing the work. Hand the result to the high-model verifier.

### High-model testing / acceptance prompt

> **Use Claude Opus 5 or GPT-6 Astra only. Lower-end models are prohibited for final testing.** Independently verify **Goal 10: Automatically inspect the uploaded dataset structure.** Do not trust the implementation agent's claims. Feed multiple representative datasets and malformed structures into the inspector. Compare reported rows/columns/types/missingness/order fields with ground truth and verify no preprocessing happens before inspection completes. Inspect the Git diff for unintended changes and run the relevant regression/integration tests after targeted checks. If anything fails, return `FAIL` with exact evidence and required fixes; after fixes, rerun tests. Mark `PASS` only when the implementation satisfies the goal with executed evidence and does not weaken scientific correctness, security, or existing functionality.

---

## Goal 11: Automatically identify available sensor channels.

### Implementation prompt

> Read `goals.md` and `model.md` first. Work only on **Goal 11: Automatically identify available sensor channels.** Inspect the current repository and reuse existing correct project logic rather than rebuilding blindly. Implement sensor-channel discovery using deterministic rules, aliases, metadata, units, and schema adapters. Distinguish confirmed mappings from ambiguous guesses. For ambiguous channels, return a validation requirement instead of silently choosing the most convenient column. Add or update targeted tests for the code you implement, but do **not** self-certify the goal as complete. Keep the change scoped, document important design decisions, preserve backward compatibility where practical, and finish by reporting changed files, commands run, tests run, known limitations, and the commit/branch or worktree containing the work. Hand the result to the high-model verifier.

### High-model testing / acceptance prompt

> **Use Claude Opus 5 or GPT-6 Astra only. Lower-end models are prohibited for final testing.** Independently verify **Goal 11: Automatically identify available sensor channels.** Do not trust the implementation agent's claims. Create fixtures with obvious channel names, aliases, misleading names, duplicated candidates, and ambiguous mappings. Verify confirmed mappings are correct and ambiguous cases are rejected or require confirmation rather than guessed. Inspect the Git diff for unintended changes and run the relevant regression/integration tests after targeted checks. If anything fails, return `FAIL` with exact evidence and required fixes; after fixes, rerun tests. Mark `PASS` only when the implementation satisfies the goal with executed evidence and does not weaken scientific correctness, security, or existing functionality.

---

## Goal 12: Automatically detect or obtain sampling information required for analysis.

### Implementation prompt

> Read `goals.md` and `model.md` first. Work only on **Goal 12: Automatically detect or obtain sampling information required for analysis.** Inspect the current repository and reuse existing correct project logic rather than rebuilding blindly. Implement sampling-information handling. Read sample rate, timestamps, file metadata, or adapter metadata when available; derive sampling frequency only when mathematically justified; otherwise require user/dataset metadata. Never guess a sample rate because FFT results depend on it. Add or update targeted tests for the code you implement, but do **not** self-certify the goal as complete. Keep the change scoped, document important design decisions, preserve backward compatibility where practical, and finish by reporting changed files, commands run, tests run, known limitations, and the commit/branch or worktree containing the work. Hand the result to the high-model verifier.

### High-model testing / acceptance prompt

> **Use Claude Opus 5 or GPT-6 Astra only. Lower-end models are prohibited for final testing.** Independently verify **Goal 12: Automatically detect or obtain sampling information required for analysis.** Do not trust the implementation agent's claims. Test explicit sample rate, timestamp-derived sample rate, irregular timestamps, missing metadata, contradictory metadata, and known-rate synthetic signals. Verify derived frequency axes match the known signal frequency. Inspect the Git diff for unintended changes and run the relevant regression/integration tests after targeted checks. If anything fails, return `FAIL` with exact evidence and required fixes; after fixes, rerun tests. Mark `PASS` only when the implementation satisfies the goal with executed evidence and does not weaken scientific correctness, security, or existing functionality.

---

## Goal 13: Automatically map uploaded data into the format expected by the prediction pipeline.

### Implementation prompt

> Read `goals.md` and `model.md` first. Work only on **Goal 13: Automatically map uploaded data into the format expected by the prediction pipeline.** Inspect the current repository and reuse existing correct project logic rather than rebuilding blindly. Create a canonical internal data schema and deterministic mapping layer from supported uploaded formats into that schema. Preserve units, ordering, channel identity, metadata, and provenance. Keep adapter-specific logic isolated so adding a new format does not rewrite the core prediction pipeline. Add or update targeted tests for the code you implement, but do **not** self-certify the goal as complete. Keep the change scoped, document important design decisions, preserve backward compatibility where practical, and finish by reporting changed files, commands run, tests run, known limitations, and the commit/branch or worktree containing the work. Hand the result to the high-model verifier.

### High-model testing / acceptance prompt

> **Use Claude Opus 5 or GPT-6 Astra only. Lower-end models are prohibited for final testing.** Independently verify **Goal 13: Automatically map uploaded data into the format expected by the prediction pipeline.** Do not trust the implementation agent's claims. Test each adapter against its source format and compare resulting canonical records. Confirm units, order, channel identities, metadata, and values are preserved; verify unsupported schemas cannot accidentally match an adapter. Inspect the Git diff for unintended changes and run the relevant regression/integration tests after targeted checks. If anything fails, return `FAIL` with exact evidence and required fixes; after fixes, rerun tests. Mark `PASS` only when the implementation satisfies the goal with executed evidence and does not weaken scientific correctness, security, or existing functionality.

---

## Goal 14: Automatically validate whether the uploaded dataset is usable.

### Implementation prompt

> Read `goals.md` and `model.md` first. Work only on **Goal 14: Automatically validate whether the uploaded dataset is usable.** Inspect the current repository and reuse existing correct project logic rather than rebuilding blindly. Implement a validation gate before scientific analysis. Validate required channels, numeric quality, missingness, ordering, sampling information, units, minimum data length, supported operating assumptions, and model/feature compatibility. Return explicit validation errors and compatibility status instead of forcing bad data through the model. Add or update targeted tests for the code you implement, but do **not** self-certify the goal as complete. Keep the change scoped, document important design decisions, preserve backward compatibility where practical, and finish by reporting changed files, commands run, tests run, known limitations, and the commit/branch or worktree containing the work. Hand the result to the high-model verifier.

### High-model testing / acceptance prompt

> **Use Claude Opus 5 or GPT-6 Astra only. Lower-end models are prohibited for final testing.** Independently verify **Goal 14: Automatically validate whether the uploaded dataset is usable.** Do not trust the implementation agent's claims. Run invalid and boundary fixtures through validation: missing channels, NaNs, infinities, short sequences, unsorted time, unknown units, absent sample rate, incompatible schemas, and valid controls. Confirm exact compatibility/error states. Inspect the Git diff for unintended changes and run the relevant regression/integration tests after targeted checks. If anything fails, return `FAIL` with exact evidence and required fixes; after fixes, rerun tests. Mark `PASS` only when the implementation satisfies the goal with executed evidence and does not weaken scientific correctness, security, or existing functionality.

---

## Goal 15: Automatically preprocess uploaded sensor data.

### Implementation prompt

> Read `goals.md` and `model.md` first. Work only on **Goal 15: Automatically preprocess uploaded sensor data.** Inspect the current repository and reuse existing correct project logic rather than rebuilding blindly. Implement preprocessing as a reusable, versioned pipeline that mirrors training-time behavior exactly. Handle cleaning, missing values, filtering, scaling/normalization, segmentation, ordering, and unit conversion only according to validated project rules. Prevent train/inference skew. Add or update targeted tests for the code you implement, but do **not** self-certify the goal as complete. Keep the change scoped, document important design decisions, preserve backward compatibility where practical, and finish by reporting changed files, commands run, tests run, known limitations, and the commit/branch or worktree containing the work. Hand the result to the high-model verifier.

### High-model testing / acceptance prompt

> **Use Claude Opus 5 or GPT-6 Astra only. Lower-end models are prohibited for final testing.** Independently verify **Goal 15: Automatically preprocess uploaded sensor data.** Do not trust the implementation agent's claims. Compare production preprocessing output against the reference/training pipeline on frozen fixtures. Check scaling parameters, filtering, segment boundaries, missing-value handling, unit conversion, ordering, and deterministic repeatability. Inspect the Git diff for unintended changes and run the relevant regression/integration tests after targeted checks. If anything fails, return `FAIL` with exact evidence and required fixes; after fixes, rerun tests. Mark `PASS` only when the implementation satisfies the goal with executed evidence and does not weaken scientific correctness, security, or existing functionality.

---

## Goal 16: Automatically extract the required statistical, time-domain, and frequency-domain features.

### Implementation prompt

> Read `goals.md` and `model.md` first. Work only on **Goal 16: Automatically extract the required statistical, time-domain, and frequency-domain features.** Inspect the current repository and reuse existing correct project logic rather than rebuilding blindly. Implement the project's required time-domain, statistical, and frequency-domain feature extraction as deterministic functions with a versioned feature schema. Include RMS, kurtosis and other approved features plus FFT-derived features where used. Ensure sample-rate-dependent features use validated sampling metadata. Add or update targeted tests for the code you implement, but do **not** self-certify the goal as complete. Keep the change scoped, document important design decisions, preserve backward compatibility where practical, and finish by reporting changed files, commands run, tests run, known limitations, and the commit/branch or worktree containing the work. Hand the result to the high-model verifier.

### High-model testing / acceptance prompt

> **Use Claude Opus 5 or GPT-6 Astra only. Lower-end models are prohibited for final testing.** Independently verify **Goal 16: Automatically extract the required statistical, time-domain, and frequency-domain features.** Do not trust the implementation agent's claims. Independently recompute approved features on controlled synthetic signals and frozen real fixtures. Validate formulas, numerical tolerances, FFT bins, band energies, feature ordering, and schema version. Inspect the Git diff for unintended changes and run the relevant regression/integration tests after targeted checks. If anything fails, return `FAIL` with exact evidence and required fixes; after fixes, rerun tests. Mark `PASS` only when the implementation satisfies the goal with executed evidence and does not weaken scientific correctness, security, or existing functionality.

---

## Goal 17: Automatically calculate the health indicator and degradation state.

### Implementation prompt

> Read `goals.md` and `model.md` first. Work only on **Goal 17: Automatically calculate the health indicator and degradation state.** Inspect the current repository and reuse existing correct project logic rather than rebuilding blindly. Implement Health Indicator calculation and degradation-stage classification using the project's current validated logic. Keep the calculation deterministic, versioned, and reusable for both offline evaluation and production inference. Do not redefine the HI for aesthetics. Add or update targeted tests for the code you implement, but do **not** self-certify the goal as complete. Keep the change scoped, document important design decisions, preserve backward compatibility where practical, and finish by reporting changed files, commands run, tests run, known limitations, and the commit/branch or worktree containing the work. Hand the result to the high-model verifier.

### High-model testing / acceptance prompt

> **Use Claude Opus 5 or GPT-6 Astra only. Lower-end models are prohibited for final testing.** Independently verify **Goal 17: Automatically calculate the health indicator and degradation state.** Do not trust the implementation agent's claims. Compare HI and degradation stages with trusted reference outputs across multiple bearings and lifecycle positions. Test monotonic/trend properties where expected and make sure test/future information is not used improperly. Inspect the Git diff for unintended changes and run the relevant regression/integration tests after targeted checks. If anything fails, return `FAIL` with exact evidence and required fixes; after fixes, rerun tests. Mark `PASS` only when the implementation satisfies the goal with executed evidence and does not weaken scientific correctness, security, or existing functionality.

---

## Goal 18: Automatically run the correct trained prediction pipeline.

### Implementation prompt

> Read `goals.md` and `model.md` first. Work only on **Goal 18: Automatically run the correct trained prediction pipeline.** Inspect the current repository and reuse existing correct project logic rather than rebuilding blindly. Implement model routing so a validated dataset is sent only to a trained model whose expected feature schema, adapter/domain, units, and preprocessing version match. Load model artifacts safely and expose model/version metadata in the result. Fail closed when compatibility cannot be established. Add or update targeted tests for the code you implement, but do **not** self-certify the goal as complete. Keep the change scoped, document important design decisions, preserve backward compatibility where practical, and finish by reporting changed files, commands run, tests run, known limitations, and the commit/branch or worktree containing the work. Hand the result to the high-model verifier.

### High-model testing / acceptance prompt

> **Use Claude Opus 5 or GPT-6 Astra only. Lower-end models are prohibited for final testing.** Independently verify **Goal 18: Automatically run the correct trained prediction pipeline.** Do not trust the implementation agent's claims. Test model routing with matching and mismatching model metadata, feature schemas, adapters, and preprocessing versions. Confirm only the correct artifact is loaded and that mismatches fail closed. Inspect the Git diff for unintended changes and run the relevant regression/integration tests after targeted checks. If anything fails, return `FAIL` with exact evidence and required fixes; after fixes, rerun tests. Mark `PASS` only when the implementation satisfies the goal with executed evidence and does not weaken scientific correctness, security, or existing functionality.

---

## Goal 19: Return the predicted RUL or failure-related prediction to the user.

### Implementation prompt

> Read `goals.md` and `model.md` first. Work only on **Goal 19: Return the predicted RUL or failure-related prediction to the user.** Inspect the current repository and reuse existing correct project logic rather than rebuilding blindly. Implement the prediction-result response and UI flow. Return RUL or the project's approved failure-related output, units, model identity/version, input compatibility state, warnings, and supporting derived values. Ensure failed/unsupported analysis never renders as a successful prediction. Add or update targeted tests for the code you implement, but do **not** self-certify the goal as complete. Keep the change scoped, document important design decisions, preserve backward compatibility where practical, and finish by reporting changed files, commands run, tests run, known limitations, and the commit/branch or worktree containing the work. Hand the result to the high-model verifier.

### High-model testing / acceptance prompt

> **Use Claude Opus 5 or GPT-6 Astra only. Lower-end models are prohibited for final testing.** Independently verify **Goal 19: Return the predicted RUL or failure-related prediction to the user.** Do not trust the implementation agent's claims. Run known fixtures through the real API and compare returned predictions with offline/reference values. Test units, model/version metadata, warnings, rounding, and all non-success states. Inspect the Git diff for unintended changes and run the relevant regression/integration tests after targeted checks. If anything fails, return `FAIL` with exact evidence and required fixes; after fixes, rerun tests. Mark `PASS` only when the implementation satisfies the goal with executed evidence and does not weaken scientific correctness, security, or existing functionality.

---

## Goal 20: Provide understandable diagnostic and prediction explanations.

### Implementation prompt

> Read `goals.md` and `model.md` first. Work only on **Goal 20: Provide understandable diagnostic and prediction explanations.** Inspect the current repository and reuse existing correct project logic rather than rebuilding blindly. Build a diagnostic explanation layer around validated numerical outputs. Explain health state, degradation trend, important features/anomalies, model limitations, and practical interpretation in plain language. If an LLM is used, ground it in structured backend results and prevent it from changing numeric predictions or inventing root causes. Add or update targeted tests for the code you implement, but do **not** self-certify the goal as complete. Keep the change scoped, document important design decisions, preserve backward compatibility where practical, and finish by reporting changed files, commands run, tests run, known limitations, and the commit/branch or worktree containing the work. Hand the result to the high-model verifier.

### High-model testing / acceptance prompt

> **Use Claude Opus 5 or GPT-6 Astra only. Lower-end models are prohibited for final testing.** Independently verify **Goal 20: Provide understandable diagnostic and prediction explanations.** Do not trust the implementation agent's claims. Review explanations against the underlying numeric result and source fields. Use adversarial cases to ensure the explanation does not invent faults, change RUL, claim unsupported causality, or hide uncertainty. Inspect the Git diff for unintended changes and run the relevant regression/integration tests after targeted checks. If anything fails, return `FAIL` with exact evidence and required fixes; after fixes, rerun tests. Mark `PASS` only when the implementation satisfies the goal with executed evidence and does not weaken scientific correctness, security, or existing functionality.

---

## Goal 21: Provide confidence, validation, or reliability information with predictions where supported.

### Implementation prompt

> Read `goals.md` and `model.md` first. Work only on **Goal 21: Provide confidence, validation, or reliability information with predictions where supported.** Inspect the current repository and reuse existing correct project logic rather than rebuilding blindly. Define and implement reliability information only from defensible methods available in the project, such as held-out error statistics, applicability/compatibility checks, prediction intervals if properly calibrated, or out-of-distribution warnings. Do not synthesize a 'confidence score' from arbitrary heuristics and present it as probability. Add or update targeted tests for the code you implement, but do **not** self-certify the goal as complete. Keep the change scoped, document important design decisions, preserve backward compatibility where practical, and finish by reporting changed files, commands run, tests run, known limitations, and the commit/branch or worktree containing the work. Hand the result to the high-model verifier.

### High-model testing / acceptance prompt

> **Use Claude Opus 5 or GPT-6 Astra only. Lower-end models are prohibited for final testing.** Independently verify **Goal 21: Provide confidence, validation, or reliability information with predictions where supported.** Do not trust the implementation agent's claims. Audit every reliability/confidence field back to a defined calculation or validated statistic. Test out-of-domain cases, weak-data cases, and normal cases. Fail the goal if a number looks probabilistic but has no defensible derivation. Inspect the Git diff for unintended changes and run the relevant regression/integration tests after targeted checks. If anything fails, return `FAIL` with exact evidence and required fixes; after fixes, rerun tests. Mark `PASS` only when the implementation satisfies the goal with executed evidence and does not weaken scientific correctness, security, or existing functionality.

---

## Goal 22: Detect whether an uploaded dataset is compatible with an existing trained model.

### Implementation prompt

> Read `goals.md` and `model.md` first. Work only on **Goal 22: Detect whether an uploaded dataset is compatible with an existing trained model.** Inspect the current repository and reuse existing correct project logic rather than rebuilding blindly. Implement a compatibility gate that compares the uploaded dataset against supported adapters, required signals, units, sampling assumptions, feature schema, operating domain, and trained-model metadata. Return a machine-readable compatibility result such as FULLY_SUPPORTED, ADAPTER_REQUIRED, RETRAIN_REQUIRED, UNSUPPORTED, or INVALID_INPUT. Add or update targeted tests for the code you implement, but do **not** self-certify the goal as complete. Keep the change scoped, document important design decisions, preserve backward compatibility where practical, and finish by reporting changed files, commands run, tests run, known limitations, and the commit/branch or worktree containing the work. Hand the result to the high-model verifier.

### High-model testing / acceptance prompt

> **Use Claude Opus 5 or GPT-6 Astra only. Lower-end models are prohibited for final testing.** Independently verify **Goal 22: Detect whether an uploaded dataset is compatible with an existing trained model.** Do not trust the implementation agent's claims. Build a compatibility matrix of supported, adapter-needed, retrain-needed, unsupported, and invalid fixtures. Verify exact classification and confirm that 'parses successfully' is never treated as equivalent to 'model supported'. Inspect the Git diff for unintended changes and run the relevant regression/integration tests after targeted checks. If anything fails, return `FAIL` with exact evidence and required fixes; after fixes, rerun tests. Mark `PASS` only when the implementation satisfies the goal with executed evidence and does not weaken scientific correctness, security, or existing functionality.

---

## Goal 23: Prevent unsupported datasets from receiving misleading or fabricated predictions.

### Implementation prompt

> Read `goals.md` and `model.md` first. Work only on **Goal 23: Prevent unsupported datasets from receiving misleading or fabricated predictions.** Inspect the current repository and reuse existing correct project logic rather than rebuilding blindly. Enforce fail-closed behavior throughout the API and UI. Unsupported or invalid data must never reach normal production inference, and the frontend must not convert an error into a prediction card. Add explicit guards against fallback models or default values generating plausible-looking fake results. Add or update targeted tests for the code you implement, but do **not** self-certify the goal as complete. Keep the change scoped, document important design decisions, preserve backward compatibility where practical, and finish by reporting changed files, commands run, tests run, known limitations, and the commit/branch or worktree containing the work. Hand the result to the high-model verifier.

### High-model testing / acceptance prompt

> **Use Claude Opus 5 or GPT-6 Astra only. Lower-end models are prohibited for final testing.** Independently verify **Goal 23: Prevent unsupported datasets from receiving misleading or fabricated predictions.** Do not trust the implementation agent's claims. Attempt to bypass validation via API calls, malformed metadata, renamed columns, default values, and direct prediction endpoints. Confirm unsupported inputs cannot obtain a normal prediction response. Inspect the Git diff for unintended changes and run the relevant regression/integration tests after targeted checks. If anything fails, return `FAIL` with exact evidence and required fixes; after fixes, rerun tests. Mark `PASS` only when the implementation satisfies the goal with executed evidence and does not weaken scientific correctness, security, or existing functionality.

---

## Goal 24: Clearly inform the user when a new adapter, model, or retraining is required.

### Implementation prompt

> Read `goals.md` and `model.md` first. Work only on **Goal 24: Clearly inform the user when a new adapter, model, or retraining is required.** Inspect the current repository and reuse existing correct project logic rather than rebuilding blindly. Implement clear user-facing outcomes for adapter-required, retrain-required, unsupported, and invalid datasets. State exactly what information or development step is missing, without pretending that the current model generalizes beyond its evidence. Add or update targeted tests for the code you implement, but do **not** self-certify the goal as complete. Keep the change scoped, document important design decisions, preserve backward compatibility where practical, and finish by reporting changed files, commands run, tests run, known limitations, and the commit/branch or worktree containing the work. Hand the result to the high-model verifier.

### High-model testing / acceptance prompt

> **Use Claude Opus 5 or GPT-6 Astra only. Lower-end models are prohibited for final testing.** Independently verify **Goal 24: Clearly inform the user when a new adapter, model, or retraining is required.** Do not trust the implementation agent's claims. Verify each non-supported state produces a clear, truthful and actionable message in both API and frontend. Ensure messages do not promise automatic support or retraining that the system cannot perform. Inspect the Git diff for unintended changes and run the relevant regression/integration tests after targeted checks. If anything fails, return `FAIL` with exact evidence and required fixes; after fixes, rerun tests. Mark `PASS` only when the implementation satisfies the goal with executed evidence and does not weaken scientific correctness, security, or existing functionality.

---

## Goal 25: Make the system adaptable to multiple compatible bearing or machine datasets instead of depending on one fixed dataset format.

### Implementation prompt

> Read `goals.md` and `model.md` first. Work only on **Goal 25: Make the system adaptable to multiple compatible bearing or machine datasets instead of depending on one fixed dataset format.** Inspect the current repository and reuse existing correct project logic rather than rebuilding blindly. Refactor data ingestion around an adapter registry and canonical schema so new compatible bearing/machine datasets can be supported without forking the full analysis pipeline. Add at least one non-original format fixture/adapter path to prove the abstraction is real rather than theoretical. Add or update targeted tests for the code you implement, but do **not** self-certify the goal as complete. Keep the change scoped, document important design decisions, preserve backward compatibility where practical, and finish by reporting changed files, commands run, tests run, known limitations, and the commit/branch or worktree containing the work. Hand the result to the high-model verifier.

### High-model testing / acceptance prompt

> **Use Claude Opus 5 or GPT-6 Astra only. Lower-end models are prohibited for final testing.** Independently verify **Goal 25: Make the system adaptable to multiple compatible bearing or machine datasets instead of depending on one fixed dataset format.** Do not trust the implementation agent's claims. Run at least two structurally different supported formats through adapters and compare their canonical outputs for equivalent signals. Add negative fixtures to prove the registry does not overmatch arbitrary files. Inspect the Git diff for unintended changes and run the relevant regression/integration tests after targeted checks. If anything fails, return `FAIL` with exact evidence and required fixes; after fixes, rerun tests. Mark `PASS` only when the implementation satisfies the goal with executed evidence and does not weaken scientific correctness, security, or existing functionality.

---

## Goal 26: Implement the complete pipeline: Upload or Live Data → Dataset Detection → Validation → Preprocessing → Feature Extraction → Health Indicator → Prediction → Diagnostics → Visual Results.

### Implementation prompt

> Read `goals.md` and `model.md` first. Work only on **Goal 26: Implement the complete pipeline: Upload or Live Data → Dataset Detection → Validation → Preprocessing → Feature Extraction → Health Indicator → Prediction → Diagnostics → Visual Results.** Inspect the current repository and reuse existing correct project logic rather than rebuilding blindly. Connect every production stage into one traceable workflow: ingestion, inspection, compatibility, validation, preprocessing, feature extraction, HI, model routing, prediction, diagnostics, and visualization. Use explicit stage states and structured outputs so failures are attributable to the correct stage rather than becoming generic 'analysis failed' errors. Add or update targeted tests for the code you implement, but do **not** self-certify the goal as complete. Keep the change scoped, document important design decisions, preserve backward compatibility where practical, and finish by reporting changed files, commands run, tests run, known limitations, and the commit/branch or worktree containing the work. Hand the result to the high-model verifier.

### High-model testing / acceptance prompt

> **Use Claude Opus 5 or GPT-6 Astra only. Lower-end models are prohibited for final testing.** Independently verify **Goal 26: Implement the complete pipeline: Upload or Live Data → Dataset Detection → Validation → Preprocessing → Feature Extraction → Health Indicator → Prediction → Diagnostics → Visual Results.** Do not trust the implementation agent's claims. Execute the full production workflow and capture stage-by-stage artifacts/status. Inject a failure at every stage and verify the system reports the correct stage, cleans up safely, and never returns a misleading final success. Inspect the Git diff for unintended changes and run the relevant regression/integration tests after targeted checks. If anything fails, return `FAIL` with exact evidence and required fixes; after fixes, rerun tests. Mark `PASS` only when the implementation satisfies the goal with executed evidence and does not weaken scientific correctness, security, or existing functionality.

---

## Goal 27: Package the ML models and preprocessing components cleanly for production inference.

### Implementation prompt

> Read `goals.md` and `model.md` first. Work only on **Goal 27: Package the ML models and preprocessing components cleanly for production inference.** Inspect the current repository and reuse existing correct project logic rather than rebuilding blindly. Package model artifacts, preprocessing state, feature-schema metadata, model metadata, and loader code into a production inference package. A fresh process must be able to load the exact approved artifact and reproduce the same prediction for the same canonical input. Add or update targeted tests for the code you implement, but do **not** self-certify the goal as complete. Keep the change scoped, document important design decisions, preserve backward compatibility where practical, and finish by reporting changed files, commands run, tests run, known limitations, and the commit/branch or worktree containing the work. Hand the result to the high-model verifier.

### High-model testing / acceptance prompt

> **Use Claude Opus 5 or GPT-6 Astra only. Lower-end models are prohibited for final testing.** Independently verify **Goal 27: Package the ML models and preprocessing components cleanly for production inference.** Do not trust the implementation agent's claims. Start a fresh process/environment, load packaged artifacts, and reproduce frozen reference predictions. Test missing/corrupt/wrong-version artifacts and verify failures are explicit and safe. Inspect the Git diff for unintended changes and run the relevant regression/integration tests after targeted checks. If anything fails, return `FAIL` with exact evidence and required fixes; after fixes, rerun tests. Mark `PASS` only when the implementation satisfies the goal with executed evidence and does not weaken scientific correctness, security, or existing functionality.

---

## Goal 28: Create backend APIs for dataset analysis and prediction.

### Implementation prompt

> Read `goals.md` and `model.md` first. Work only on **Goal 28: Create backend APIs for dataset analysis and prediction.** Inspect the current repository and reuse existing correct project logic rather than rebuilding blindly. Create backend APIs for upload/inspection, validation/compatibility, analysis/prediction, job/result retrieval if needed, model/version metadata, and health checks. Use typed request/response schemas, consistent error handling, and a clean boundary between HTTP code and scientific pipeline code. Add or update targeted tests for the code you implement, but do **not** self-certify the goal as complete. Keep the change scoped, document important design decisions, preserve backward compatibility where practical, and finish by reporting changed files, commands run, tests run, known limitations, and the commit/branch or worktree containing the work. Hand the result to the high-model verifier.

### High-model testing / acceptance prompt

> **Use Claude Opus 5 or GPT-6 Astra only. Lower-end models are prohibited for final testing.** Independently verify **Goal 28: Create backend APIs for dataset analysis and prediction.** Do not trust the implementation agent's claims. Contract-test every API endpoint, including validation errors, content types, status codes, timeouts, health/version responses, and frontend compatibility. Run the real model path at least once rather than testing only mocks. Inspect the Git diff for unintended changes and run the relevant regression/integration tests after targeted checks. If anything fails, return `FAIL` with exact evidence and required fixes; after fixes, rerun tests. Mark `PASS` only when the implementation satisfies the goal with executed evidence and does not weaken scientific correctness, security, or existing functionality.

---

## Goal 29: Handle large dataset uploads safely and efficiently.

### Implementation prompt

> Read `goals.md` and `model.md` first. Work only on **Goal 29: Handle large dataset uploads safely and efficiently.** Inspect the current repository and reuse existing correct project logic rather than rebuilding blindly. Design large-file handling based on actual dataset sizes and runtime constraints. Use streaming uploads, temporary storage, chunked parsing, background jobs or equivalent only where justified. Prevent memory explosions, enforce limits, clean temporary files, and return useful progress/status information. Add or update targeted tests for the code you implement, but do **not** self-certify the goal as complete. Keep the change scoped, document important design decisions, preserve backward compatibility where practical, and finish by reporting changed files, commands run, tests run, known limitations, and the commit/branch or worktree containing the work. Hand the result to the high-model verifier.

### High-model testing / acceptance prompt

> **Use Claude Opus 5 or GPT-6 Astra only. Lower-end models are prohibited for final testing.** Independently verify **Goal 29: Handle large dataset uploads safely and efficiently.** Do not trust the implementation agent's claims. Load-test representative and near-limit upload sizes, monitor memory/CPU/temp files, test concurrent uploads if supported, cancellation/timeouts, and cleanup after success/failure. Verify configured limits are actually enforced. Inspect the Git diff for unintended changes and run the relevant regression/integration tests after targeted checks. If anything fails, return `FAIL` with exact evidence and required fixes; after fixes, rerun tests. Mark `PASS` only when the implementation satisfies the goal with executed evidence and does not weaken scientific correctness, security, or existing functionality.

---

## Goal 30: Add prediction history and result tracking.

### Implementation prompt

> Read `goals.md` and `model.md` first. Work only on **Goal 30: Add prediction history and result tracking.** Inspect the current repository and reuse existing correct project logic rather than rebuilding blindly. Add durable prediction-history/result tracking with identifiers, timestamps, dataset fingerprint or safe metadata, model version, feature-schema version, compatibility state, prediction result, warnings, and status. Do not store raw uploaded sensor data indefinitely unless explicitly required. Add or update targeted tests for the code you implement, but do **not** self-certify the goal as complete. Keep the change scoped, document important design decisions, preserve backward compatibility where practical, and finish by reporting changed files, commands run, tests run, known limitations, and the commit/branch or worktree containing the work. Hand the result to the high-model verifier.

### High-model testing / acceptance prompt

> **Use Claude Opus 5 or GPT-6 Astra only. Lower-end models are prohibited for final testing.** Independently verify **Goal 30: Add prediction history and result tracking.** Do not trust the implementation agent's claims. Create multiple prediction records, refresh/restart as appropriate, retrieve history, and verify IDs, timestamps, versions, statuses, and access behavior. Ensure failed jobs are distinguishable and sensitive raw payloads are not unintentionally persisted. Inspect the Git diff for unintended changes and run the relevant regression/integration tests after targeted checks. If anything fails, return `FAIL` with exact evidence and required fixes; after fixes, rerun tests. Mark `PASS` only when the implementation satisfies the goal with executed evidence and does not weaken scientific correctness, security, or existing functionality.

---

## Goal 31: Add proper loading, failure, validation, and error states in the frontend.

### Implementation prompt

> Read `goals.md` and `model.md` first. Work only on **Goal 31: Add proper loading, failure, validation, and error states in the frontend.** Inspect the current repository and reuse existing correct project logic rather than rebuilding blindly. Implement complete frontend state handling for upload, inspection, validation, processing, success, partial results, unsupported data, server errors, timeouts, and retry. Users must always know what stage failed and what they can do next. Add or update targeted tests for the code you implement, but do **not** self-certify the goal as complete. Keep the change scoped, document important design decisions, preserve backward compatibility where practical, and finish by reporting changed files, commands run, tests run, known limitations, and the commit/branch or worktree containing the work. Hand the result to the high-model verifier.

### High-model testing / acceptance prompt

> **Use Claude Opus 5 or GPT-6 Astra only. Lower-end models are prohibited for final testing.** Independently verify **Goal 31: Add proper loading, failure, validation, and error states in the frontend.** Do not trust the implementation agent's claims. Force every major frontend state from real or controlled backend responses. Verify no infinite spinners, stale success cards, swallowed errors, duplicate submissions, or misleading fallback content. Inspect the Git diff for unintended changes and run the relevant regression/integration tests after targeted checks. If anything fails, return `FAIL` with exact evidence and required fixes; after fixes, rerun tests. Mark `PASS` only when the implementation satisfies the goal with executed evidence and does not weaken scientific correctness, security, or existing functionality.

---

## Goal 32: Make the frontend responsive and visually strong across desktop and mobile.

### Implementation prompt

> Read `goals.md` and `model.md` first. Work only on **Goal 32: Make the frontend responsive and visually strong across desktop and mobile.** Inspect the current repository and reuse existing correct project logic rather than rebuilding blindly. Make the web application responsive and visually coherent across common desktop, tablet, and mobile widths. Preserve chart readability, navigation, upload usability, tables, and result hierarchy. Avoid desktop-only layouts hidden behind horizontal scrolling. Add or update targeted tests for the code you implement, but do **not** self-certify the goal as complete. Keep the change scoped, document important design decisions, preserve backward compatibility where practical, and finish by reporting changed files, commands run, tests run, known limitations, and the commit/branch or worktree containing the work. Hand the result to the high-model verifier.

### High-model testing / acceptance prompt

> **Use Claude Opus 5 or GPT-6 Astra only. Lower-end models are prohibited for final testing.** Independently verify **Goal 32: Make the frontend responsive and visually strong across desktop and mobile.** Do not trust the implementation agent's claims. Test defined viewport sizes and browser-equivalent rendering. Check charts, tables, dialogs, navigation, upload controls, touch targets, wrapping, overflow, and readable result hierarchy. Inspect the Git diff for unintended changes and run the relevant regression/integration tests after targeted checks. If anything fails, return `FAIL` with exact evidence and required fixes; after fixes, rerun tests. Mark `PASS` only when the implementation satisfies the goal with executed evidence and does not weaken scientific correctness, security, or existing functionality.

---

## Goal 33: Test the full prediction flow end-to-end using existing project datasets.

### Implementation prompt

> Read `goals.md` and `model.md` first. Work only on **Goal 33: Test the full prediction flow end-to-end using existing project datasets.** Inspect the current repository and reuse existing correct project logic rather than rebuilding blindly. Create an end-to-end test path using the project's existing validated datasets and model artifacts. Exercise the real pipeline from input ingestion through the API to the final returned prediction, using expected numeric tolerances and version checks rather than mocked success. Add or update targeted tests for the code you implement, but do **not** self-certify the goal as complete. Keep the change scoped, document important design decisions, preserve backward compatibility where practical, and finish by reporting changed files, commands run, tests run, known limitations, and the commit/branch or worktree containing the work. Hand the result to the high-model verifier.

### High-model testing / acceptance prompt

> **Use Claude Opus 5 or GPT-6 Astra only. Lower-end models are prohibited for final testing.** Independently verify **Goal 33: Test the full prediction flow end-to-end using existing project datasets.** Do not trust the implementation agent's claims. Run a true black-box end-to-end test from a known dataset upload to final rendered result. Compare prediction and intermediate key values against frozen reference expectations and record evidence of the full path. Inspect the Git diff for unintended changes and run the relevant regression/integration tests after targeted checks. If anything fails, return `FAIL` with exact evidence and required fixes; after fixes, rerun tests. Mark `PASS` only when the implementation satisfies the goal with executed evidence and does not weaken scientific correctness, security, or existing functionality.

---

## Goal 34: Test the system with datasets that differ from the original training format.

### Implementation prompt

> Read `goals.md` and `model.md` first. Work only on **Goal 34: Test the system with datasets that differ from the original training format.** Inspect the current repository and reuse existing correct project logic rather than rebuilding blindly. Build test fixtures representing supported but structurally different input formats, renamed columns, optional metadata locations, different file organization, and deliberately unsupported cases. Verify adapter behavior separately from model generalization. Do not call a dataset 'supported' merely because parsing succeeds. Add or update targeted tests for the code you implement, but do **not** self-certify the goal as complete. Keep the change scoped, document important design decisions, preserve backward compatibility where practical, and finish by reporting changed files, commands run, tests run, known limitations, and the commit/branch or worktree containing the work. Hand the result to the high-model verifier.

### High-model testing / acceptance prompt

> **Use Claude Opus 5 or GPT-6 Astra only. Lower-end models are prohibited for final testing.** Independently verify **Goal 34: Test the system with datasets that differ from the original training format.** Do not trust the implementation agent's claims. Use multiple alternate-format fixtures including one requiring an adapter and one that must be rejected/retrained. Verify structural adaptation is supported without falsely claiming cross-machine predictive validity. Inspect the Git diff for unintended changes and run the relevant regression/integration tests after targeted checks. If anything fails, return `FAIL` with exact evidence and required fixes; after fixes, rerun tests. Mark `PASS` only when the implementation satisfies the goal with executed evidence and does not weaken scientific correctness, security, or existing functionality.

---

## Goal 35: Verify that preprocessing and inference remain scientifically consistent after deployment.

### Implementation prompt

> Read `goals.md` and `model.md` first. Work only on **Goal 35: Verify that preprocessing and inference remain scientifically consistent after deployment.** Inspect the current repository and reuse existing correct project logic rather than rebuilding blindly. Compare deployment inference against the trusted offline/reference pipeline on fixed fixtures. Confirm identical or tolerance-bounded preprocessing outputs, feature vectors, HI values, model inputs, and predictions. Treat any unexplained divergence as a release blocker. Add or update targeted tests for the code you implement, but do **not** self-certify the goal as complete. Keep the change scoped, document important design decisions, preserve backward compatibility where practical, and finish by reporting changed files, commands run, tests run, known limitations, and the commit/branch or worktree containing the work. Hand the result to the high-model verifier.

### High-model testing / acceptance prompt

> **Use Claude Opus 5 or GPT-6 Astra only. Lower-end models are prohibited for final testing.** Independently verify **Goal 35: Verify that preprocessing and inference remain scientifically consistent after deployment.** Do not trust the implementation agent's claims. Run the same frozen datasets through offline/reference and deployed inference. Compare preprocessing tensors/features, HI, routed model/version, and final output under strict tolerances. Investigate every mismatch. Inspect the Git diff for unintended changes and run the relevant regression/integration tests after targeted checks. If anything fails, return `FAIL` with exact evidence and required fixes; after fixes, rerun tests. Mark `PASS` only when the implementation satisfies the goal with executed evidence and does not weaken scientific correctness, security, or existing functionality.

---

## Goal 36: Add automated tests for dataset validation, preprocessing, feature extraction, health indicators, prediction, APIs, and frontend integration.

### Implementation prompt

> Read `goals.md` and `model.md` first. Work only on **Goal 36: Add automated tests for dataset validation, preprocessing, feature extraction, health indicators, prediction, APIs, and frontend integration.** Inspect the current repository and reuse existing correct project logic rather than rebuilding blindly. Build an automated test suite covering schema inspection, mapping, compatibility, validation, preprocessing, feature extraction, FFT correctness, HI, model routing, prediction, API contracts, upload behavior, and frontend integration. Include regression fixtures for previously fixed bugs and unsupported-input cases. Add or update targeted tests for the code you implement, but do **not** self-certify the goal as complete. Keep the change scoped, document important design decisions, preserve backward compatibility where practical, and finish by reporting changed files, commands run, tests run, known limitations, and the commit/branch or worktree containing the work. Hand the result to the high-model verifier.

### High-model testing / acceptance prompt

> **Use Claude Opus 5 or GPT-6 Astra only. Lower-end models are prohibited for final testing.** Independently verify **Goal 36: Add automated tests for dataset validation, preprocessing, feature extraction, health indicators, prediction, APIs, and frontend integration.** Do not trust the implementation agent's claims. Review test coverage by subsystem and run the complete suite. Add mutation/adversarial cases for scientific gates, confirm tests actually fail when key logic is intentionally perturbed, then restore code and rerun green. Inspect the Git diff for unintended changes and run the relevant regression/integration tests after targeted checks. If anything fails, return `FAIL` with exact evidence and required fixes; after fixes, rerun tests. Mark `PASS` only when the implementation satisfies the goal with executed evidence and does not weaken scientific correctness, security, or existing functionality.

---

## Goal 37: Add monitoring and logging for prediction requests, failures, and deployment issues.

### Implementation prompt

> Read `goals.md` and `model.md` first. Work only on **Goal 37: Add monitoring and logging for prediction requests, failures, and deployment issues.** Inspect the current repository and reuse existing correct project logic rather than rebuilding blindly. Add structured observability for request IDs, pipeline stage, model version, feature-schema version, compatibility outcome, processing duration, failures, and deployment health. Never log secrets or unnecessary raw sensor payloads. Make failures diagnosable from logs without reproducing user data exposure. Add or update targeted tests for the code you implement, but do **not** self-certify the goal as complete. Keep the change scoped, document important design decisions, preserve backward compatibility where practical, and finish by reporting changed files, commands run, tests run, known limitations, and the commit/branch or worktree containing the work. Hand the result to the high-model verifier.

### High-model testing / acceptance prompt

> **Use Claude Opus 5 or GPT-6 Astra only. Lower-end models are prohibited for final testing.** Independently verify **Goal 37: Add monitoring and logging for prediction requests, failures, and deployment issues.** Do not trust the implementation agent's claims. Generate successful and failing requests, inspect logs/metrics, correlate request IDs, confirm timing/model/version fields, and verify no secrets or excessive raw sensor content are logged. Test health monitoring under a simulated backend/model failure. Inspect the Git diff for unintended changes and run the relevant regression/integration tests after targeted checks. If anything fails, return `FAIL` with exact evidence and required fixes; after fixes, rerun tests. Mark `PASS` only when the implementation satisfies the goal with executed evidence and does not weaken scientific correctness, security, or existing functionality.

---

## Goal 38: Prepare the application for production deployment.

### Implementation prompt

> Read `goals.md` and `model.md` first. Work only on **Goal 38: Prepare the application for production deployment.** Inspect the current repository and reuse existing correct project logic rather than rebuilding blindly. Create production-readiness configuration and documentation: environment variables, secrets, frontend/backend URLs, model artifact location, startup/health checks, build commands, migrations if any, CORS, upload limits, cleanup, rollback, and release checklist. A clean environment should be able to deploy from documented steps. Add or update targeted tests for the code you implement, but do **not** self-certify the goal as complete. Keep the change scoped, document important design decisions, preserve backward compatibility where practical, and finish by reporting changed files, commands run, tests run, known limitations, and the commit/branch or worktree containing the work. Hand the result to the high-model verifier.

### High-model testing / acceptance prompt

> **Use Claude Opus 5 or GPT-6 Astra only. Lower-end models are prohibited for final testing.** Independently verify **Goal 38: Prepare the application for production deployment.** Do not trust the implementation agent's claims. Perform a release-readiness verification from a clean checkout/environment: install, build, test, load model, run smoke prediction, verify secrets/env handling, health checks, CORS/upload limits, deployment docs, and rollback path. Inspect the Git diff for unintended changes and run the relevant regression/integration tests after targeted checks. If anything fails, return `FAIL` with exact evidence and required fixes; after fixes, rerun tests. Mark `PASS` only when the implementation satisfies the goal with executed evidence and does not weaken scientific correctness, security, or existing functionality.

---

## Goal 39: Create a reliable overnight autonomous-development workflow for the project.

### Implementation prompt

> Read `goals.md` and `model.md` first. Work only on **Goal 39: Create a reliable overnight autonomous-development workflow for the project.** Inspect the current repository and reuse existing correct project logic rather than rebuilding blindly. Build a controlled overnight development workflow that reads goals.md and model.md, selects unfinished tasks, creates isolated work, records task state, runs implementation, hands verification to a high-end model, and produces a morning report. It must stop on ambiguous scientific decisions instead of improvising. Add or update targeted tests for the code you implement, but do **not** self-certify the goal as complete. Keep the change scoped, document important design decisions, preserve backward compatibility where practical, and finish by reporting changed files, commands run, tests run, known limitations, and the commit/branch or worktree containing the work. Hand the result to the high-model verifier.

### High-model testing / acceptance prompt

> **Use Claude Opus 5 or GPT-6 Astra only. Lower-end models are prohibited for final testing.** Independently verify **Goal 39: Create a reliable overnight autonomous-development workflow for the project.** Do not trust the implementation agent's claims. Dry-run the overnight workflow with several independent tasks plus one deliberate failure. Verify routing, isolation, checkpoints, high-model verification, stop conditions, and morning reporting without touching main unexpectedly. Inspect the Git diff for unintended changes and run the relevant regression/integration tests after targeted checks. If anything fails, return `FAIL` with exact evidence and required fixes; after fixes, rerun tests. Mark `PASS` only when the implementation satisfies the goal with executed evidence and does not weaken scientific correctness, security, or existing functionality.

---

## Goal 40: Ensure overnight development work uses isolated branches or worktrees for independent tasks.

### Implementation prompt

> Read `goals.md` and `model.md` first. Work only on **Goal 40: Ensure overnight development work uses isolated branches or worktrees for independent tasks.** Inspect the current repository and reuse existing correct project logic rather than rebuilding blindly. Implement a Git worktree/branch strategy for independent overnight tasks. Give each worker an isolated branch/worktree, avoid parallel editing of overlapping files where possible, record ownership, and provide a deterministic integration order. Add or update targeted tests for the code you implement, but do **not** self-certify the goal as complete. Keep the change scoped, document important design decisions, preserve backward compatibility where practical, and finish by reporting changed files, commands run, tests run, known limitations, and the commit/branch or worktree containing the work. Hand the result to the high-model verifier.

### High-model testing / acceptance prompt

> **Use Claude Opus 5 or GPT-6 Astra only. Lower-end models are prohibited for final testing.** Independently verify **Goal 40: Ensure overnight development work uses isolated branches or worktrees for independent tasks.** Do not trust the implementation agent's claims. Create parallel worktrees/branches and simulate independent edits plus one controlled overlap. Verify ownership, conflict detection, integration order, cleanup, and no changes leak between worktrees. Inspect the Git diff for unintended changes and run the relevant regression/integration tests after targeted checks. If anything fails, return `FAIL` with exact evidence and required fixes; after fixes, rerun tests. Mark `PASS` only when the implementation satisfies the goal with executed evidence and does not weaken scientific correctness, security, or existing functionality.

---

## Goal 41: Ensure autonomous agents do not directly damage or overwrite stable project code.

### Implementation prompt

> Read `goals.md` and `model.md` first. Work only on **Goal 41: Ensure autonomous agents do not directly damage or overwrite stable project code.** Inspect the current repository and reuse existing correct project logic rather than rebuilding blindly. Add safety controls for autonomous agents: never force-push main, never reset/delete unrelated work, never commit secrets, never rewrite stable model artifacts without versioning, never bypass failing tests, and checkpoint before risky changes. Agents should fail safely and leave recoverable state. Add or update targeted tests for the code you implement, but do **not** self-certify the goal as complete. Keep the change scoped, document important design decisions, preserve backward compatibility where practical, and finish by reporting changed files, commands run, tests run, known limitations, and the commit/branch or worktree containing the work. Hand the result to the high-model verifier.

### High-model testing / acceptance prompt

> **Use Claude Opus 5 or GPT-6 Astra only. Lower-end models are prohibited for final testing.** Independently verify **Goal 41: Ensure autonomous agents do not directly damage or overwrite stable project code.** Do not trust the implementation agent's claims. Perform destructive-safety tests in a sandbox repository: simulate failed tasks, dirty worktrees, missing secrets, failing tests, and attempted risky commands. Verify guardrails prevent force-push/reset/secret commit/main corruption. Inspect the Git diff for unintended changes and run the relevant regression/integration tests after targeted checks. If anything fails, return `FAIL` with exact evidence and required fixes; after fixes, rerun tests. Mark `PASS` only when the implementation satisfies the goal with executed evidence and does not weaken scientific correctness, security, or existing functionality.

---

## Goal 42: Run automated tests after each meaningful overnight implementation task.

### Implementation prompt

> Read `goals.md` and `model.md` first. Work only on **Goal 42: Run automated tests after each meaningful overnight implementation task.** Inspect the current repository and reuse existing correct project logic rather than rebuilding blindly. After every meaningful implementation task, automatically invoke the high-model verification workflow rather than allowing the worker to self-approve. Record the exact tests run, results, model used for verification, and any defects found. Add or update targeted tests for the code you implement, but do **not** self-certify the goal as complete. Keep the change scoped, document important design decisions, preserve backward compatibility where practical, and finish by reporting changed files, commands run, tests run, known limitations, and the commit/branch or worktree containing the work. Hand the result to the high-model verifier.

### High-model testing / acceptance prompt

> **Use Claude Opus 5 or GPT-6 Astra only. Lower-end models are prohibited for final testing.** Independently verify **Goal 42: Run automated tests after each meaningful overnight implementation task.** Do not trust the implementation agent's claims. Audit overnight task records and prove each meaningful implementation was followed by verification from Claude Opus 5 or GPT-6 Astra, not Haiku/Luna/Sonnet/Sol alone. Spot-check tests and reject self-certified tasks. Inspect the Git diff for unintended changes and run the relevant regression/integration tests after targeted checks. If anything fails, return `FAIL` with exact evidence and required fixes; after fixes, rerun tests. Mark `PASS` only when the implementation satisfies the goal with executed evidence and does not weaken scientific correctness, security, or existing functionality.

---

## Goal 43: Merge completed overnight work only after validation.

### Implementation prompt

> Read `goals.md` and `model.md` first. Work only on **Goal 43: Merge completed overnight work only after validation.** Inspect the current repository and reuse existing correct project logic rather than rebuilding blindly. Create an integration gate that allows merge only after the high-end verifier has reviewed the diff and required tests are green. Resolve conflicts deliberately, rerun affected tests after conflict resolution, then run the required integration/full suite before final merge. Add or update targeted tests for the code you implement, but do **not** self-certify the goal as complete. Keep the change scoped, document important design decisions, preserve backward compatibility where practical, and finish by reporting changed files, commands run, tests run, known limitations, and the commit/branch or worktree containing the work. Hand the result to the high-model verifier.

### High-model testing / acceptance prompt

> **Use Claude Opus 5 or GPT-6 Astra only. Lower-end models are prohibited for final testing.** Independently verify **Goal 43: Merge completed overnight work only after validation.** Do not trust the implementation agent's claims. Test the merge gate with a passing branch, a failing branch, stale tests, and a conflict-resolution scenario. Confirm merge is blocked until high-model review plus required test suites are green after integration. Inspect the Git diff for unintended changes and run the relevant regression/integration tests after targeted checks. If anything fails, return `FAIL` with exact evidence and required fixes; after fixes, rerun tests. Mark `PASS` only when the implementation satisfies the goal with executed evidence and does not weaken scientific correctness, security, or existing functionality.

---

## Goal 44: Produce a final overnight report containing completed work, failed tasks, test results, changed files, and remaining work.

### Implementation prompt

> Read `goals.md` and `model.md` first. Work only on **Goal 44: Produce a final overnight report containing completed work, failed tasks, test results, changed files, and remaining work.** Inspect the current repository and reuse existing correct project logic rather than rebuilding blindly. Generate a structured end-of-night report containing completed goals, incomplete goals, blockers, branches/worktrees, commits, changed files, tests executed, failures/fixes, final test status, model versions used, and exact next actions. Do not hide failed attempts. Add or update targeted tests for the code you implement, but do **not** self-certify the goal as complete. Keep the change scoped, document important design decisions, preserve backward compatibility where practical, and finish by reporting changed files, commands run, tests run, known limitations, and the commit/branch or worktree containing the work. Hand the result to the high-model verifier.

### High-model testing / acceptance prompt

> **Use Claude Opus 5 or GPT-6 Astra only. Lower-end models are prohibited for final testing.** Independently verify **Goal 44: Produce a final overnight report containing completed work, failed tasks, test results, changed files, and remaining work.** Do not trust the implementation agent's claims. Validate the generated report against Git history, worktree state, test logs, and task records. Ensure completed/failed counts, commits, files, tests, blockers, and next actions are factual and reproducible. Inspect the Git diff for unintended changes and run the relevant regression/integration tests after targeted checks. If anything fails, return `FAIL` with exact evidence and required fixes; after fixes, rerun tests. Mark `PASS` only when the implementation satisfies the goal with executed evidence and does not weaken scientific correctness, security, or existing functionality.

---

## Goal 45: Keep the project scientifically defensible and avoid claiming support for machines or datasets that have not been validated.

### Implementation prompt

> Read `goals.md` and `model.md` first. Work only on **Goal 45: Keep the project scientifically defensible and avoid claiming support for machines or datasets that have not been validated.** Inspect the current repository and reuse existing correct project logic rather than rebuilding blindly. Audit scientific claims and system behavior against what the code, datasets, and evaluation actually support. Ensure the UI/API/docs distinguish validated domains from unsupported machines, avoid universal claims, preserve leakage-safe evaluation, and expose limitations where relevant. Add or update targeted tests for the code you implement, but do **not** self-certify the goal as complete. Keep the change scoped, document important design decisions, preserve backward compatibility where practical, and finish by reporting changed files, commands run, tests run, known limitations, and the commit/branch or worktree containing the work. Hand the result to the high-model verifier.

### High-model testing / acceptance prompt

> **Use Claude Opus 5 or GPT-6 Astra only. Lower-end models are prohibited for final testing.** Independently verify **Goal 45: Keep the project scientifically defensible and avoid claiming support for machines or datasets that have not been validated.** Do not trust the implementation agent's claims. Perform an independent scientific audit of supported claims, dataset/model boundaries, split/evaluation logic, units, sampling assumptions, HI/RUL behavior, and UI wording. Search specifically for universal or causal claims that exceed evidence and mark them as release blockers. Inspect the Git diff for unintended changes and run the relevant regression/integration tests after targeted checks. If anything fails, return `FAIL` with exact evidence and required fixes; after fixes, rerun tests. Mark `PASS` only when the implementation satisfies the goal with executed evidence and does not weaken scientific correctness, security, or existing functionality.

---

# Master Overnight Execution Prompt

> Read `goals.md`, `model.md`, and `prompts.md` completely before touching code. Reconstruct the repository's current state and mark each goal as `DONE`, `PARTIAL`, `NOT_STARTED`, or `BLOCKED` based on code and executed evidence, not documentation claims. Choose the highest-priority unfinished goals that can be worked on safely tonight. Route implementation according to `model.md`; routine build work may use Sonnet 5/GPT-6 Sol and narrow mechanical tasks may use cheaper approved workers. **Every goal's final testing and acceptance must be performed by Claude Opus 5 or GPT-6 Astra only. No lower-end worker may approve its own work.**
>
> For independent tasks, create isolated Git worktrees/branches. Avoid parallel tasks that modify the same files. For each selected goal: run its implementation prompt, run targeted worker tests, then hand the exact diff to the goal's high-model testing prompt. If the verifier returns FAIL, fix the verified defects and send it back to the high-model verifier until PASS or a real blocker is reached. Do not brute-force scientific uncertainty. Do not force-push or directly rewrite main. Once individual goals pass, integrate them in a controlled order, resolve conflicts deliberately, then have Claude Opus 5 or GPT-6 Astra perform integration verification and run the complete relevant/full test suite. Merge only after high-model acceptance.
>
> At the end, produce a morning report with: goals attempted, goals completed, goals blocked, branches/worktrees, commits, changed files, implementation model used for each goal, **verification model used for each goal**, tests executed, pass/fail evidence, defects found and fixed, unresolved issues, integration/full-suite result, and exact next actions. Never claim a goal is complete without high-model verification evidence.

# Final Integration Testing Prompt

> **Run only with Claude Opus 5 or GPT-6 Astra.** Act as the independent release verifier after all individually accepted branches have been integrated. Read `goals.md`, `model.md`, `prompts.md`, inspect the complete diff from the last known-good base, and verify that individually correct changes still work together. Run the full automated suite, end-to-end dataset-to-prediction flow, alternate-format/unsupported dataset checks, API contract tests, frontend production build, frontend/backend integration, model artifact loading, scientific parity tests, and production smoke tests that are available. Check for data leakage, train/inference skew, incorrect sample-rate handling, unit errors, fake confidence, unsupported-machine claims, secret exposure, unsafe upload behavior, stale UI states, regressions, and merge-conflict damage. Return a release-blocking defect list for every failure. Final output must be `INTEGRATION PASS` only if executed evidence supports release; otherwise output `INTEGRATION FAIL`.

# Scientific Acceptance Prompt

> **Run only with Claude Opus 5 or GPT-6 Astra.** Independently audit the project's scientific pipeline after major changes. Verify dataset splits are leakage-safe, preprocessing at inference matches training, feature definitions are correct and versioned, FFT uses valid sampling information, Health Indicator logic is unchanged unless explicitly approved, model routing respects compatibility, ExtraTrees/challenger comparisons use the same evaluation protocol, RUL metrics include per-bearing behavior and overprediction risk, and unsupported machines/datasets cannot receive normal predictions. Recompute representative results from frozen fixtures. Treat undocumented scientific behavior changes or unverifiable performance claims as FAIL.

# Frontend Acceptance Prompt

> **Run only with Claude Opus 5 or GPT-6 Astra.** Verify the production frontend from a user's perspective and against backend truth. Test upload, inspection, validation, processing, results, unsupported data, server failures, timeouts, retry, history, responsiveness, accessibility, production build, API contracts, chart correctness, RUL/HI display, diagnostic wording, and absence of fabricated values. Cross-check representative UI values against raw API responses. Return PASS only if the interface is both visually production-ready and scientifically faithful.

# Backend/API Acceptance Prompt

> **Run only with Claude Opus 5 or GPT-6 Astra.** Verify API schemas, upload security, validation/compatibility gating, preprocessing, feature extraction, HI, model routing, prediction, errors, health/version endpoints, large-file behavior, cleanup, observability, and production model loading. Attempt to bypass compatibility/validation gates and confirm unsupported inputs cannot obtain a standard prediction. Compare real API predictions with frozen offline reference outputs before PASS.

# Deployment Acceptance Prompt

> **Run only with Claude Opus 5 or GPT-6 Astra.** From a clean checkout/environment, validate dependency installation, frontend production build, backend startup, artifact loading, environment/secrets configuration, health checks, API connectivity, CORS, upload limits, temporary-file cleanup, logging, timeout behavior, smoke prediction, and rollback/redeployment documentation. Do not accept 'works on my machine' as evidence. PASS requires a reproducible deployment-equivalent run.

# Morning Audit Prompt

> **Run only with Claude Opus 5 or GPT-6 Astra.** Audit the overnight report against Git history, worktree state, commits, diffs, test logs, and current repository state. Verify that every goal marked complete has a recorded high-model verification pass, and reject any goal tested only by a lower-end implementation model. Re-run a risk-based subset of the most important tests plus the full suite if practical. Identify false completion claims, unmerged work, hidden failing tests, scientific regressions, or unsafe changes. Output the corrected project status and the exact next tasks.

# Vercel-Only Deployment Goal Prompts

The following prompts extend the original 45 goals and lock the current deployment target to **Vercel only**.

> **Deployment architecture decision:** Use Vercel for the Next.js web application and the Python/FastAPI ML inference layer. Use a direct-to-storage upload flow for large files, process uploaded data incrementally/chunk-wise, keep inference lightweight enough for the Vercel runtime, and delete temporary raw uploads after prediction unless retention is explicitly required.
>
> **Testing rule remains unchanged:** final testing, verification, deployment acceptance, and merge approval for these goals must be performed **only by Claude Opus 5 or GPT-6 Astra**. Lower-end models may implement, but they may not approve.

---

## Goal 46: Deploy the complete application on Vercel only, with no paid services and no card requirement.

### Implementation prompt

> Read `goals.md`, `model.md`, and `prompts.md` first. Work only on **Goal 46: Deploy the complete application on Vercel only, with no paid services and no card requirement.** Inspect the current repository before changing anything. Design the final production path so the Next.js web application and Python/FastAPI inference layer can run within Vercel's supported runtimes and free-tier constraints. Remove assumptions that require Railway, Render, Oracle Cloud, or another paid/card-verified backend. Keep the architecture modular even though it runs on one platform. Add deployment configuration, environment-variable handling, runtime boundaries, build commands, and documentation required for a clean Vercel deployment. Do not self-certify completion. Finish by reporting changed files, Vercel assumptions, build/deploy commands, runtime limits considered, tests run, and remaining risks.

### High-model testing / acceptance prompt

> **Use Claude Opus 5 or GPT-6 Astra only.** Independently verify Goal 46. From a clean checkout, confirm there is no runtime dependency on Railway, Render, Oracle Cloud, or another external compute host. Run the production build, inspect Vercel configuration, verify all required application paths can execute under the intended Vercel runtimes, and test the deployed or deployment-equivalent application. Confirm the design remains within the intended zero-cost/no-card architecture. Return `FAIL` if any required production feature still depends on another compute host or if deployment only works in local development.

---

## Goal 47: Deploy the Next.js frontend on Vercel.

### Implementation prompt

> Work only on **Goal 47: Deploy the Next.js frontend on Vercel.** Prepare the Next.js application for a real Vercel production build. Configure environment variables, routing, API calls, static assets, charts, upload screens, and production-safe defaults. Remove development-only assumptions such as hard-coded localhost URLs. Ensure frontend code can discover the correct production API route without exposing secrets. Run a clean production build before handing the task to verification.

### High-model testing / acceptance prompt

> **Use Claude Opus 5 or GPT-6 Astra only.** Independently verify Goal 47. Run a clean install and production build, test routing and navigation, inspect environment-variable usage, verify there are no hard-coded local URLs, and test the deployed or deployment-equivalent frontend against the production API path. Check desktop/mobile behavior and core upload-to-result navigation. PASS only with executed production-build evidence.

---

## Goal 48: Run the Python/FastAPI ML inference layer using Vercel's Python runtime.

### Implementation prompt

> Work only on **Goal 48: Run the Python/FastAPI ML inference layer using Vercel's Python runtime.** Adapt the existing Python inference code to Vercel's supported Python runtime without changing validated scientific behavior. Keep FastAPI/API routing thin and separate from preprocessing, feature extraction, HI, model loading, and prediction modules. Minimize cold-start cost and package size, load model artifacts safely, avoid writable-local-disk assumptions beyond temporary runtime use, and ensure repeated requests behave deterministically. Do not change the trained prediction methodology merely to simplify hosting unless a scientifically equivalent refactor is proven.

### High-model testing / acceptance prompt

> **Use Claude Opus 5 or GPT-6 Astra only.** Independently verify Goal 48. Start from a clean environment, build the Python runtime package, load the real approved model artifact, run known inference fixtures through the Vercel-compatible API path, compare outputs with the trusted offline pipeline, test cold-start/repeated-request behavior, and inspect package/runtime assumptions. Reject any solution that changes prediction values without explanation or depends on persistent local filesystem state.

---

## Goal 49: Use direct-to-storage uploads for large datasets instead of sending large files through API request bodies.

### Implementation prompt

> Work only on **Goal 49: Use direct-to-storage uploads for large datasets instead of sending large files through API request bodies.** Implement a direct browser-to-storage upload flow suitable for Vercel, with the API receiving only the storage reference plus validated metadata needed to begin analysis. Do not proxy large raw dataset bodies through the ML prediction function. Add file-type and size validation, safe object naming, upload progress, failure handling, authorization or scoped upload controls where applicable, and cleanup metadata. Keep the storage provider abstracted enough that a compatible Vercel storage mechanism can be used without changing scientific code.

### High-model testing / acceptance prompt

> **Use Claude Opus 5 or GPT-6 Astra only.** Independently verify Goal 49. Test normal, near-limit, oversized, malformed, interrupted, repeated, and maliciously named uploads. Confirm the large raw body does not pass through the ML inference request path. Verify the API accepts only a validated storage reference, cannot access arbitrary storage objects, and handles missing/expired objects safely. Inspect cleanup behavior and ensure failed uploads cannot produce predictions.

---

## Goal 50: Process uploaded vibration datasets incrementally/chunk-wise to control RAM usage.

### Implementation prompt

> Work only on **Goal 50: Process uploaded vibration datasets incrementally/chunk-wise to control RAM usage.** Refactor parsing and preprocessing so large CSV/time-series inputs can be read and processed in bounded chunks wherever scientifically valid. Preserve sample ordering, segmentation logic, feature formulas, FFT requirements, HI construction, and final prediction semantics. Do not introduce chunk boundaries that alter scientific results. Where an operation genuinely requires a complete window or signal segment, buffer only the required amount rather than the entire dataset. Add memory-aware instrumentation or tests.

### High-model testing / acceptance prompt

> **Use Claude Opus 5 or GPT-6 Astra only.** Independently verify Goal 50. Compare chunked-processing outputs with the trusted full/offline pipeline on frozen fixtures, including preprocessing values, features, FFT-derived values, HI, and final RUL. Test multiple chunk sizes and boundary positions. Measure peak memory on representative and large fixtures. Any unexplained numerical divergence or ordering error is a FAIL.

---

## Goal 51: Keep the production ML model lightweight enough for serverless inference.

### Implementation prompt

> Work only on **Goal 51: Keep the production ML model lightweight enough for serverless inference.** Audit the current approved model, artifact size, dependency footprint, feature pipeline, startup time, and inference cost. Optimize packaging and loading before considering any model change. Prefer the existing validated ExtraTrees-style pipeline or another already-approved lightweight model if it meets the project's scientific benchmark. Do not replace the model purely for deployment convenience. If the current artifact cannot fit the runtime safely, produce a measured blocker report before proposing a scientifically revalidated alternative.

### High-model testing / acceptance prompt

> **Use Claude Opus 5 or GPT-6 Astra only.** Independently verify Goal 51. Measure artifact size, dependency size, cold-start loading, memory use, and inference runtime using the real production package. Compare prediction outputs with the reference artifact. Confirm any compression/serialization/packaging change is prediction-equivalent within defined tolerance. Reject any model downgrade that weakens validated accuracy or changes scientific claims without a full benchmark.

---

## Goal 52: Delete temporary raw uploaded datasets after prediction unless explicitly retained.

### Implementation prompt

> Work only on **Goal 52: Delete temporary raw uploaded datasets after prediction unless explicitly retained.** Implement lifecycle management for uploaded raw data. Track upload identifiers, analysis status, and cleanup state. Delete temporary raw files/objects after successful prediction and after terminal failures where safe. Define a bounded cleanup policy for abandoned jobs. Preserve only minimal prediction metadata/history unless explicit retention is required. Never delete shared model artifacts or unrelated objects.

### High-model testing / acceptance prompt

> **Use Claude Opus 5 or GPT-6 Astra only.** Independently verify Goal 52. Test cleanup after success, validation failure, prediction failure, timeout, retry, and abandoned analysis. Confirm prediction/result metadata remains available when intended while raw data is removed. Test object isolation so one job cannot delete another job's upload. Verify no secrets or unrelated artifacts are affected.

---

## Goal 53: Handle timeout, memory-limit, malformed-file, upload-limit, and unsupported-dataset cases properly.

### Implementation prompt

> Work only on **Goal 53: Handle timeout, memory-limit, malformed-file, upload-limit, and unsupported-dataset cases properly.** Add explicit failure handling for serverless runtime constraints and bad inputs. Define machine-readable error codes, user-readable messages, safe cleanup, retryability rules, and frontend states. Fail closed before inference for invalid or unsupported data. Do not convert a timeout, memory error, parser error, or compatibility failure into a partial/fabricated prediction.

### High-model testing / acceptance prompt

> **Use Claude Opus 5 or GPT-6 Astra only.** Independently verify Goal 53. Force malformed CSVs, invalid encodings, missing metadata, unsupported schemas, oversized uploads, artificial timeouts, memory-pressure scenarios where feasible, storage read failures, corrupt model artifacts, and dependency errors. Confirm correct status/error codes, safe cleanup, no stale success UI, no fabricated result, and no retry loop that repeatedly consumes resources.

---

## Goal 54: Verify the full production flow on Vercel: Upload → Validate → Preprocess → Features/FFT → HI → RUL Prediction → Results.

### Implementation prompt

> Work only on **Goal 54: Verify the full production flow on Vercel: Upload → Validate → Preprocess → Features/FFT → HI → RUL Prediction → Results.** Wire every stage into the actual Vercel production path, including direct-to-storage upload, API trigger, dataset retrieval, compatibility validation, chunk-aware preprocessing, feature/FFT extraction, Health Indicator, model inference, result persistence/return, cleanup, and frontend rendering. Use explicit stage states and request/job identifiers. Do not substitute mocked prediction success for the real model path.

### High-model testing / acceptance prompt

> **Use Claude Opus 5 or GPT-6 Astra only.** Independently verify Goal 54 with a true black-box production or deployment-equivalent test. Upload a known supported fixture through the frontend, follow it through storage and the real Python inference path, and compare validation, preprocessing, features, FFT values, HI, model/version, RUL, warnings, cleanup, and rendered result against trusted reference expectations. Repeat with an unsupported fixture and confirm it is blocked before normal inference. PASS only if the real end-to-end path works.

---

## Goal 55: Test the deployed Vercel version using the higher-end testing model only.

### Implementation prompt

> Work only on **Goal 55: Test the deployed Vercel version using the higher-end testing model only.** Add project/automation guardrails so deployment acceptance, production smoke tests, scientific parity checks, and final merge approval cannot be marked complete by a lower-end worker. Record the verifier model used for every deployment test. Lower-end models may run preliminary implementation checks, but they cannot produce the final PASS.

### High-model testing / acceptance prompt

> **Use Claude Opus 5 or GPT-6 Astra only. No other model may issue final acceptance.** Audit the deployment test records and repository automation. Confirm every Vercel deployment goal has executed evidence from a permitted high-end verifier. Re-run a risk-based production smoke suite plus the end-to-end prediction flow. Reject any goal whose only evidence came from Sonnet, Haiku, Luna, Sol, or another lower/default model.

---

# Vercel-Only Final Deployment Acceptance Prompt

> **Run only with Claude Opus 5 or GPT-6 Astra.** Treat the current deployment target as Vercel-only. From a clean checkout, verify the Next.js production build, Vercel Python/FastAPI runtime, direct-to-storage upload path, chunk-wise processing, model artifact loading, feature/FFT correctness, HI, RUL inference, unsupported-dataset rejection, timeout/error behavior, temporary raw-data cleanup, and frontend rendering. Run at least one real supported end-to-end prediction and one unsupported-dataset rejection. Compare production outputs with frozen offline reference outputs. Confirm no required compute path depends on Railway, Render, Oracle Cloud, or another paid/card-verified host. Final output must be `VERCEL DEPLOYMENT PASS` only when executed evidence supports it; otherwise output `VERCEL DEPLOYMENT FAIL`.

# Vercel-Only Overnight Instruction Addendum

> When `prompts.md` is used overnight, treat Goals 46–55 as the authoritative deployment tasks. Earlier generic deployment wording remains historical context, but if it conflicts with Goals 46–55, use the Vercel-only architecture. Implementation can use the normal worker models defined in `model.md`; final testing and acceptance must still use Claude Opus 5 or GPT-6 Astra only.

