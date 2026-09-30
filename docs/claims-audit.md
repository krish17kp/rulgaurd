# Scientific claims audit (Goal 45)

Documentation-only audit of README.md, every existing docs/*.md page, API docstrings
and frontend page text, with read-only checks of evaluation, profiling, routing and
uncertainty code. No model was trained, no dataset was reprocessed and no serving
behavior was changed. Source locations refer to the edited worktree. Verdicts assess
the original claim or its plausible generalisation; “fixed” means the documentation
now uses the correction. Supported claims still require their stated scope.

No JSON files were available under reports/metrics/ during this audit. Numerical
evidence below is extracted directly from docs/decisions.md, not reconstructed from
generated Markdown or invented. The generated cross-dataset tables remain historical
records whose source JSON must be restored before exact metric revalidation.

The HTTP contract is FEMTO feature input with declared dataset identity, not proof
of machine provenance. Offline adapter support for college, IMS and XJTU-SY does not
authorise cached FEMTO inference on those domains. Applicability is a similarity
heuristic; severity is not fault diagnosis or probability of health. No live feed,
real-time latency guarantee, field safety claim or universal machine support is
established. D28 records methodology qualifications before this audit continued.

| Source file:line | Claim / possible generalisation | Verdict | Evidence | Proposed corrected wording / scope | Disposition |
|---|---|---|---|---|---|
| `README.md:3` | Evidence-grounded retrieval is already delivered | overstated | M7 remains deferred. | Research RUL prototype; retrieval/report generation is deferred. | fixed |
| `README.md:10` | Adapters map every source; RUL always comes with intervals | overstated | D23 known adapters; D27 offline routing; HTTP response has no intervals. | Known-format adapters and offline empirical intervals; HTTP prediction remains FEMTO-only. | fixed |
| `README.md:15` | College evidence does not generalise across bearings | supported | D10 and D26 describe the same college run. | Retain single-trajectory limitation. | retained |
| `README.md:16` | Only ExtraTrees college numbers are real evidence | overstated | D10 oracle identity; D21 systematic overestimation. | Same-trajectory held-out evidence, not demonstrated deployment usefulness. | fixed |
| `README.md:17` | FEMTO transfer only in labelled offline experiments | supported | D11 serving gates; D23-D27 transfer experiments. | No non-FEMTO HTTP prediction; offline experiments do not extend serving support. | retained |
| `README.md:18` | No physical fault diagnosis | supported | D19 severity bands; no fault output in API. | Stages describe severity, not physical cause. | retained |
| `README.md:19` | Sampled review represents all college evidence | overstated | D26 separately describes full-run canonical analysis. | Distinguish sampled legacy review from full-run canonical analysis. | fixed |
| `README.md:20` | Hidden-set improvement is narrow and includes unsafe-direction errors | supported | D20 corrected baseline and unsafe-direction errors; D17 target conflict. | Keep benchmark comparison, narrow margin and overestimation caveat together. | retained with scope |
| `README.md:21` | Observed stage lead time varies across FEMTO bearings | supported | D18-D20 report variable FEMTO behavior. | Observed severity lead times are not guaranteed field warning times. | retained with scope |
| `README.md:8` | First genuinely out-of-sample result | overstated | D20 distinguishes fit independence from design selection. | Independent post-freeze evaluation; LOBO also holds out fitting data. | fixed |
| `docs/PROJECT_HANDOFF.md:40` | Only genuinely out-of-sample result | overstated | D20 design-selection qualification. | Independent post-freeze FEMTO evaluation. | fixed |
| `docs/milestone.md:36` | Only out-of-sample evaluation | overstated | D20; evaluation.py holds out each bearing. | LOBO holds out fitting data, not the whole design process. | fixed |
| `docs/PROJECT_HANDOFF.md:48` | FEMTO-fit models never applied to college anywhere | overstated | D11 versus D23-D26 offline experiments. | Serving is FEMTO-gated; offline experiments explicitly measure transfer failures. | fixed |
| `docs/PROJECT_HANDOFF.md:46` | College evidence remains entirely sampled | overstated | D26 canonical whole-run analysis. | Legacy review sampling and canonical full-run evidence are separate. | fixed |
| `docs/brd.md:36` | Prove valid baseline on lab data | overstated | D10/D21 limit college inference. | Evaluate fold-local models and report failure cases. | fixed |
| `docs/brd.md:76` | Aggregate improvement establishes general validity | overstated | D21 pooled errors differ from fold means; D20 hidden-set comparison is narrow. | State split and aggregation; report per-bearing failures. | fixed |
| `docs/brd.md:77` | College walk-forward demonstrates useful prediction | overstated | D10 oracle; D21 overestimation. | Same-bearing chronological errors, not cross-bearing support. | fixed |
| `docs/brd.md:78` | Legacy selected HI is current validation evidence | overstated | D18-D20 supersede legacy choice and distinguish construction from evidence. | Reference HI replaced legacy choice; selection used development data. | fixed |
| `docs/brd.md:86` | No unsupported claim survives; acceptance met | unsupported | Open UI/API findings below; metric JSON absent. | Scoped audit with unresolved findings; no blanket scientific acceptance. | fixed |
| `docs/prd.md:4` | Cited retrieval is currently implemented | overstated | M7 remains deferred. | Evaluation evidence is documented; retrieval is a deferred requirement. | fixed |
| `docs/prd.md:57` | College must improve over naive oracle | unsupported | D10 terminal-time oracle. | Report chronological errors; oracle comparison is not a skill criterion. | fixed |
| `docs/prd.md:77` | No guaranteed diagnosis implies some diagnosis exists | overstated | D19 defines severity only. | No physical root-cause diagnosis. | fixed |
| `docs/prd.md:24` | No college generalisation or real-time industrial deployment | supported | D10/D26; offline architecture. | Retain explicit non-goals. | retained |
| `docs/architecture.md:30` | Any supported dataset flows to HI/RUL | overstated | D23 adapters, D27 routing, D11 HTTP boundaries. | Implemented adapter enables offline analysis; prediction gates still apply. | fixed |
| `docs/architecture.md:50` | Working report fallback exists without dependencies | unsupported | M7 is deferred; diagram includes planned components. | Fallback is planned, not verified runtime reporting. | fixed |
| `docs/architecture.md:44` | Leakage-safe fitting means independent design evaluation | overstated | evaluation.py uses grouped splits; D20 discloses design selection. | Keep role and fitting guards; disclose learning-set design choices. | fixed |
| `docs/data-contract.md:39` | Hidden-role and chronological fitting guards | supported | evaluation.py role and chronological assertions; D10 naive caveat. | Fitting guards do not make the college oracle deployable. | retained |
| `docs/cross-dataset.md:31` | Profiles ANY folder | unsupported | Profiler recognises patterns and may fail or leave formats unknown. | Attempts structural inspection; unknown formats need an adapter. | fixed |
| `docs/cross-dataset.md:46` | Universal Machine Analysis title | unsupported | D23 known adapters; D24/D27 skill suppression. | Cross-dataset bearing analysis. | doc qualified; UI deferred |
| `docs/cross-dataset.md:88` | All leakage controls imply independent HI design | overstated | D20 learning-set design; D26 post-inspection amplitude-HI choice. | Fold-local fitting controls, with design selection disclosed. | fixed |
| `docs/cross-dataset.md:137` | Conformal guarantee for this method and new rigs | overstated | D28; uncertainty.py uses weighted out-of-fold residuals. | Empirical coverage and width; no established theorem for this procedure or per-case probability. | fixed |
| `docs/cross-dataset.md:125` | HIGH applicability describes similarity rather than accuracy | supported | D27 separates similarity from per-dataset validation skill. | Similarity category, not probability of correctness. | retained with scope |
| `docs/cross-dataset.md:156` | Fails exactly where life time-scale differs | overstated | D24 establishes limitations, not exclusive causality. | Observed failure on evaluated college and IMS cases; time-scale mismatch is a limitation. | fixed |
| `docs/cross-dataset.md:221` | Normalisation cancels arbitrary gain and load changes | overstated | D23 log-ratio construction. | Cancels constant multiplicative scale, not arbitrary sensor response or changing load. | fixed |
| `docs/cross-dataset.md:245` | Every number comes from held-out bearings | overstated | D20/D26 disclose observed data used for HI selection. | RUL split evidence and descriptive HI analysis have different independence limits. | fixed |
| `docs/cross-dataset.md:249` | Heterogeneous support and uncertainty-aware RUL in unseen domains | overstated | D23-D28; API FEMTO gate. | Known-format offline experiments and gated research estimates; no universal machine support. | fixed |
| `docs/cross-dataset.md:261` | No college-internal validation is possible | overstated | D10/D21 chronological evaluation; D26 no independent college bearing. | Same-run walk-forward exists; independent cross-bearing validation does not. | fixed |
| `docs/cross-dataset.md:67` | RUL labels describe time to recorded endpoint | supported | D23 last-recording convention; D25 IMS cutoff. | Time to recorded endpoint under dataset-specific stop rules. | retained with scope |
| `docs/cross-dataset.md:62` | College/IMS vibration units remain unverified | supported | D23 explicitly preserves unknown units. | Keep units unverified; plausible amplitudes do not verify sensor units. | existing non-claim retained |
| `docs/cross-dataset-results.md:3` | All generated tables are newly verified results | overstated | Source cross_dataset.json absent; D24-D27 support qualitative limitations only. | Historical generated snapshot; restore source JSON before exact revalidation. | qualification added; tables retained |
| `docs/dataset-audit.md:14` | Observed temperature proves terminal trigger | overstated | D23/D26 distinguish observed behavior and stop-rule descriptions. | Threshold exceedance is consistent with termination, not proof of trigger. | fixed |
| `docs/dataset-audit.md:16` | Magnitude grows monotonically with degradation | overstated | D26 reports falling vibration over much of college life. | Endpoint samples do not establish monotonic degradation. | fixed |
| `docs/external-datasets.md:60` | Dataset suitability means cached-model support | overstated | D23/D25 label scope; D11 serving restriction. | Research label suitability does not validate the served model. | qualification added |
| `docs/external-datasets.md:148` | External fault labels establish implemented diagnosis | unsupported | API has severity outputs only; D19. | Source dataset labels are provenance, not RULGuard diagnosis support. | qualification added |
| `docs/decisions.md:95` | First truly out-of-sample result and old naive margin | overstated | D20 corrected scoring; D17 target conflict retained. | Post-freeze evaluation; superseded numbers remain historical. | fixed |
| `docs/decisions.md:249` | Learning-set HI design selection is unqualified standard practice | overstated | D20 disclosure; D28 qualification. | Full-procedure independence needs nested selection or independent data. | fixed |
| `docs/decisions.md:432` | Energy growth is generic degradation signature | overstated | D26 reports non-monotonic college behavior and differing HI rankings. | Candidate signature on inspected datasets. | fixed |
| `docs/milestone.md:55` | Actionable severity band | overstated | D20 constructed critical anchor; D26 sensitive early flags. | Experimental offline severity band, not validated maintenance advice. | fixed |
| `docs/milestone.md:128` | Live endpoint test means live sensor monitoring | overstated | Test uses recorded FEMTO fixture through HTTP. | Local HTTP integration test using recorded data. | fixed |
| `docs/vercel-deployment.md:34` | Live deployment remains unverified | supported | Document explicitly states unverified deployment prerequisites. | No demonstrated sensor streaming, latency or field validation. | retained |
| `src/bearing_pdm/api.py:10` | FEMTO dataset gate proves input provenance | overstated | D11; predict_rul checks caller dataset_id, not source or OOD. | FEMTO-only declared-input contract; provenance and compatible extraction remain required. | API deferred |
| `src/bearing_pdm/api.py:322` | All FEMTO inputs validated for prediction | overstated | D11 training domain; D20/D21 held-out errors. | Cached-model training domain is FEMTO; benchmark evaluation is not universal accuracy. | API deferred |
| `src/bearing_pdm/api.py:285` | Aggregate metrics provide per-sample confidence | overstated | Endpoint returns historical JSON; RUL response lacks interval/probability fields. | Historical benchmark evaluation, not confidence for submitted sample. | API deferred |
| `src/bearing_pdm/api.py:292` | College caveat enforced alongside every metric | overstated | Endpoint returns JSON verbatim without requiring/inserting caveat; D10 requires disclosure. | Caveat depends on report contents; do not claim enforced presence. | API contract/wording deferred |
| `src/bearing_pdm/api.py:467` | Minimum rows proves reference health and no overlap | overstated | Boundary accepts reference-only length and scores all rows; health remains assumed. | A reference window is required; its health is not verified and its rows are not independent scored evidence. | API deferred |
| `src/bearing_pdm/api.py:427` | Non-FEMTO HI necessarily exceeds valid numeric range | overstated | D11 domain mismatch may be invalid even with bounded outputs. | Outside calibrated domain; numerical range does not establish validity. | API deferred |
| `src/bearing_pdm/api.py:559` | Inspection does not establish prediction support | supported | Profiler/classifier does not call model inference. | Structural inspection; sampling, units, provenance and applicability remain unverified. | retained |
| `frontend/src/app/page.tsx:74` | Unqualified supported datasets label | overstated | API provides training-domain list; D11. | Prediction training domain: FEMTO benchmark. | frontend deferred |
| `frontend/src/app/page.tsx:84` | Offline, no live/real-time deployment; no fault diagnosis | supported | Recorded inputs, severity response; D19. | Retain explicit offline and no-diagnosis statements. | retained |
| `frontend/src/app/predict/page.tsx:39` | RUL result implies trustworthy remaining operating time | overstated | D20/D21 errors; API supplies point estimate only. | Experimental FEMTO estimate; no per-case confidence or maintenance guarantee. | frontend deferred |
| `frontend/src/app/degradation/page.tsx:47` | A bearing run may be any machine/dataset | overstated | Client hardcodes FEMTO; D11. | FEMTO run with justified early healthy reference; severity is not probability of health. | frontend deferred |
| `frontend/src/app/degradation/page.tsx:50` | Severity is not physical fault diagnosis | supported | D19 and stage response contract. | Retain severity-only statement. | retained |
| `frontend/src/app/evaluation/page.tsx:23` | Model reliability means per-case confidence | overstated | Historical aggregate report; D10/D21/D28. | Benchmark evaluation, with signed errors and split/domain limits. | frontend deferred |
| `frontend/src/app/evaluation/page.tsx:28` | Chronological college evaluation and displayed naive comparison | supported | evaluation.py assertion; D10 caveat rendered if report supplies it. | Same-bearing walk-forward; naive is oracle identity, not skill. | frontend caveat hardening deferred |
| `frontend/src/app/upload/page.tsx:38` | Pipeline compatible / FULLY SUPPORTED badge | overstated | _classify checks structure/numeric quality, not model applicability. | Structurally inspectable; prediction compatibility not established. | frontend deferred |
| `frontend/src/app/upload/page.tsx:85` | Confidence column denotes probability | overstated | Profiler name-match categories are not calibrated probabilities. | Channel-name match strength (heuristic). | frontend deferred |
| `docs/dataset-compatibility.md:41` | FULLY_SUPPORTED means structure only | supported | API classifier plus explicit downstream-gate caveat. | Retain structural versus prediction support distinction. | retained |
| `src/bearing_pdm/dashboard_cross.py:114` | Universal Machine Analysis | unsupported | D23 known adapters; D27 skill-based suppression. | Cross-dataset bearing analysis. | UI deferred |
| `src/bearing_pdm/uncertainty.py:18` | Coverage guarantee for weighted out-of-fold procedure | overstated | D28 unresolved theoretical scope; empirical results are not proof. | Empirical residual-calibrated intervals; no guarantee established for this procedure. | source docstring deferred |

## Numerical evidence read from the decision log

The following historical table is copied programmatically from D20, including the
superseded column so its status cannot be mistaken. It is not a new evaluation.

| | ExtraTrees | naive (corrected) | naive (as originally reported, bugged) |
|---|---|---|---|
| MAE | 4,555.4 s | **5,203.9 s** | 9,459.4 s |
| RMSE | 5,388.0 s | 5,917.9 s | 5,900.3 s (official variant) |
| over-estimates | 8/11 | **4/11** | 11/11 |

D21 records held-out error direction (verbatim):

- **College walk-forward: ExtraTrees over-predicts 3023 of 3023 held-out rows — an
  over-estimate rate of 1.000 in all three folds**, mean signed error +122,442 s (+34.0 h).
  The MAE (122,442 s) was unchanged by this work and had been reported for weeks; nothing
  in it revealed that the error is entirely one-directional, and the unsafe direction.
- FEMTO leave-one-bearing-out is far better behaved: ExtraTrees over-estimates 3916 of 7534
  held-out rows (0.520) with a mean signed error of −1,159 s, i.e. slightly conservative on
  average. Naive over-estimates less often (0.411) but has a worse MAE (7,703 s vs 5,577 s).
  ExtraTrees still loses to naive on 2 of 6 bearings.

## Required later API/UI work

Release wording blockers for a claim of general machine support are the “Universal”
page title, the upload compatibility badge, and unqualified supported-dataset labels.
The table proposes replacements without editing source or frontend files. The
degradation page must state FEMTO and the healthy-reference assumption; prediction
and evaluation pages need domain and uncertainty caveats next to their results.
Channel-mapping confidence must be labelled as a heuristic, not probability.
The evaluation endpoint must not promise an enforced college caveat while returning
report JSON verbatim. These are open findings, not fixes delivered here.

Preserve bearing-grouped and chronological splits, training-only fitted transforms,
exclusion of hidden continuations and survivors from fitting, and causal routing.
Do not retune on hidden results. D20's development-set HI choices and D26's
post-inspection amplitude-HI choice require explicit disclosure; no independent
college-bearing validation follows from them. D17's conflicting hidden target must
remain visible. Keep dataset units and sampling metadata explicit; source-dataset
geometry or external fault labels do not provide a validated diagnosis subsystem.

Database schema and structure pages describe storage/planned tables rather than
additional machine validity. Deployment documentation concerns serving recorded
inputs, not live sensors. External dataset tables are provenance and suitability
notes, not validation of the served model. No source JSON or full raw-data rerun was
available to revalidate their scientific metrics in this task.

## Verification boundary

The existing full pytest suite and Ruff were run for this documentation change.
No test was added, weakened or changed; the suite reported existing skips.
Passing software tests is not new scientific validation of a dataset or machine.
The supervisor still performs independent acceptance. Source, tests and frontend
must remain identical to HEAD; API/UI findings are explicitly deferred above.
