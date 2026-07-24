# BRD - RULGuard: Bearing Health Monitoring and Remaining Useful Life Prediction

Business Requirements Document. Companion to `docs/prd.md` (product behaviour). This document is the *business* framing: the problem, who cares, why it matters, what success looks like. It deliberately avoids implementation detail - that lives in the PRD, `docs/architecture.md`, and the code.

## 1. Business problem

Rolling-element bearings are one of the most common failure points in rotating machinery (motors, pumps, fans, gearboxes, spindles). When a bearing fails without warning it can stop a production line, damage the machine it sits in, and create a safety hazard. The two traditional maintenance strategies both waste money:

- **Run-to-failure (reactive):** cheapest per-part, but the unplanned downtime and collateral damage are expensive and unpredictable.
- **Fixed-interval (preventive):** parts are replaced on a calendar whether they need it or not - throwing away remaining useful life and still missing early failures.

**Predictive / condition-based maintenance** aims to replace the part *just before* it fails, using sensor evidence of the bearing's actual condition. The core quantitative question it must answer is: *given the vibration signature so far, how much useful life is left (RUL)?* RULGuard is a research capstone that builds and honestly evaluates that RUL-estimation capability end to end, and adds an evidence-grounded explanation layer so a decision is never a black-box number.

## 2. Stakeholders

| Stakeholder | Interest in the project |
|---|---|
| Student researcher (project owner) | Deliver a defensible, reproducible capstone; demonstrate the full ML + data-engineering pipeline. |
| Faculty evaluators (review 2026-07-25) | Assess scientific validity, honesty of claims, and engineering quality. Primary audience for this review. |
| Maintenance engineer (illustrative persona) | *Would* consume RUL estimates and evidence to schedule interventions - used to shape dashboard/report UX only; **not** a validated production user. |
| Dataset providers | IEEE PHM 2012 challenge (FEMTO/PRONOSTIA); the college lab that collected the run-to-failure recording. Cited, terms respected. |

## 3. Business need and value

Unplanned bearing failure drives a large share of rotating-machinery downtime. A working RUL estimate has clear value:

- **Avoided downtime:** schedule the swap into a planned window instead of a line-stop.
- **Extended part life:** run bearings closer to their real end of life instead of a conservative calendar.
- **Safety and collateral-damage reduction:** intervene before catastrophic failure.
- **Trust / auditability:** an explanation layer that cites measured evidence (not an unexplained score) is what makes a predictive-maintenance recommendation actionable in a real plant.

For this capstone the value delivered is **academic and methodological**: a leakage-safe, reproducible, honestly-scoped demonstration that the RUL-estimation pipeline works on real data - not a deployed cost saving.

## 4. Objectives (business-level)

1. Prove a valid, leakage-safe RUL baseline on a recognised benchmark (FEMTO) and on original lab data (college run).
2. Show the full path from raw sensor data to an explainable decision surface (dashboard).
3. Keep every claim defensible: no fabricated labels, no fault-type claims without geometry, no numeric prediction from the LLM.
4. Ship review-ready by 2026-07-25 with real evidence for each completed milestone.

## 5. Scope

**In scope (review MVP):** dual-dataset ingestion (FEMTO + college), feature engineering, health-indicator construction and comparison, RUL regression baselines with leakage-safe evaluation, a Streamlit dashboard demonstrating the full path, and full documentation/evidence.

**In scope (post-review capstone):** degradation-stage classification (M5), optional 1D-CNN experiment (M6), RAG + local-LLM explanation layer (M7), full 129-file college processing, hidden-set (`Full_Test_Set`) scoring, final reproducibility audit (M9).

**Out of scope (explicit non-goals):** production deployment, real-time plant integration, safety certification, physical fault-type diagnosis (inner/outer race, ball, lubrication), and any cross-bearing generalization claim from the single college trajectory.

## 6. Assumptions

- The FEMTO archive roles (learning / censored test / hidden continuation) and hidden-RUL derivation are as independently verified in `docs/dataset-audit.md`.
- The college run is a single complete NSK 6205 run-to-failure (128 hours, 129 hourly files) at 25.6 kHz - confirmed against `context/Description.txt` and direct file inspection.
- Local-first compute is sufficient; no cloud dependency is required for the review build.
- Sensor NaN dropouts in the college data are genuine missing values to preserve, not corruption to reject (D6).

## 7. Constraints

- **Time:** accelerated review track, hard deadline 2026-07-25.
- **Compute/storage:** single workstation, tight disk (~19-21 GB free after publishing both datasets via Git LFS); bounded-memory processing is mandatory - a full college CSV (~143 MB, ~2M rows) is never loaded whole.
- **Data honesty rules (non-negotiable, `CLAUDE.md`):** dataset adapters stay separate; no leakage; no fabricated labels; no fault claims without verified geometry; LLM never alters the numeric prediction; raw high-frequency samples never enter the database.
- **Publication:** commit locally only; the user pushes to GitHub manually; no secrets or private absolute paths in history.

## 8. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Data leakage inflates results | Invalidates the whole scientific claim | Leave-one-bearing-out (FEMTO) + chronological walk-forward (college); runtime leakage assertions; hidden set frozen until after freeze. |
| Single college trajectory over-interpreted | Overstated generalization | Explicit non-claim in PRD/README; no cross-bearing claim made. |
| Circular / trivial baselines mistaken for skill | Misleading "0 error" | College naive MAE=0.0 documented as an identity (D10), never quoted as a result. |
| Applying FEMTO-fit models to college data | Silently wrong dashboard output | Dashboard gates on `dataset_id` and shows a domain-mismatch message (D11). |
| Scope creep vs. deadline | Miss review | MVP (M0-M4 + minimal M8) frozen; M5-M7/M9 explicitly deferred. |
| Disk / memory exhaustion | Failed runs | Bounded-memory chunked reads; 1-in-5 college sample for the review run. |

## 9. Expected outcomes / benefits (delivered)

- A benchmark-validated RUL baseline: FEMTO leave-one-bearing-out mean MAE **5,061 s** (ExtraTrees) vs **6,585 s** naive - the tree model beats naive on the grouped metric.
- A leakage-safe college walk-forward result (ExtraTrees MAE ~117k-132k s, i.e. ~33-37 h on a ~128 h run) with the trivial naive identity honestly flagged.
- A quantitatively-compared health indicator (transparent HI selected, mean trend corr **-0.53** vs PCA **-0.46**).
- A working dashboard demonstrating raw signal -> FFT -> features -> HI -> RUL -> metrics -> limitations.
- A documented trail of 11 real findings/bugs caught by checking against real data (`docs/decisions.md`) - evidence of a working verification process.

## 10. Success criteria (business acceptance)

- Review MVP complete and defensible by 2026-07-25 with real-data evidence per milestone. **Met.**
- Naive RUL baseline beaten by a tree model on FEMTO grouped MAE. **Met.**
- Every headline claim traceable to a generated metric or an inspected file; no unsupported claim survives. **Met.**
- All committed parser/feature tests pass on fixtures; dashboard starts from cached artifacts without training on load. **Met.**
- Full capstone (M5-M7, M9, full college run, hidden-set scoring) scoped and tracked for post-review. **Planned, not yet delivered.**

## 11. Relationship to the PRD

The PRD (`docs/prd.md`) specifies *what the product does* - functional/non-functional requirements, user stories, acceptance criteria, explicit non-claims. This BRD specifies *why the project exists and what business/academic outcome defines success*. Where they overlap (scope, non-goals, success), the PRD is the finer-grained, testable version and this BRD is the intent behind it.
