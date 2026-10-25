# START_CAPSTONE_OVERNIGHT.md

## Purpose

This file starts the **actual capstone implementation run** after the overnight orchestration/watchdog system has been configured.

The separate master overnight-system prompt remains authoritative for:
- Junior/orchestrator setup
- Claude -> Codex failover
- watchdog/provider-state handling
- worktree isolation
- checkpoints and persistent state
- safety rules
- crash recovery
- reporting

**Do not rewrite or replace that master orchestration design from this file.**

For this capstone project, the implementation source of truth is:

1. `goals.md` — what must be achieved
2. `prompts.md` — how each goal must be implemented and verified
3. `model.md` — which AI/coding/scientific model must be used for each type of task
4. the repository itself — the truth about what is already implemented

---

# START EXECUTION NOW

You are now responsible for **continuing and completing this capstone project**, not merely reviewing it.

Do not wait for me to manually assign each goal.

Read the files below completely before modifying code:

```text
goals.md
prompts.md
model.md
```

Then inspect:

```text
git status
git branch
git log --oneline --decorate -30
repository structure
tests
current application
current Streamlit implementation
model artifacts
dataset adapters
preprocessing code
feature extraction
Health Indicator code
RUL prediction code
frontend/backend code
deployment configuration
TODO/FIXME items
documentation
```

Reconstruct the real project state from code and Git history.

Do **not** assume a goal is complete because documentation says so.

---

# 1. BUILD THE TASK QUEUE

Match the current repository against every goal in `goals.md`.

For every goal assign exactly one state:

```text
DONE
PARTIAL
NOT_STARTED
BLOCKED
```

A goal may be `DONE` only when there is implementation **and executed verification evidence**.

Create/update the persistent task state used by the overnight system.

The task queue must prioritize:

1. broken or incomplete scientific core
2. end-to-end dataset -> prediction pipeline
3. dataset compatibility/adapters
4. backend/API
5. Next.js frontend
6. Vercel-only deployment work
7. automated tests
8. production hardening
9. lower-priority polish/documentation

Respect dependencies. Do not build UI for an output that the backend cannot actually produce.

---

# 2. IMPORTANT DEPLOYMENT DECISION

The current deployment target is **Vercel-only**.

The authoritative deployment goals are the later Vercel goals in `goals.md` and `prompts.md`.

Use:

```text
Next.js frontend
        |
        v
Vercel
        |
        +--> Python/FastAPI inference runtime
        |
        +--> direct-to-storage dataset upload
        |
        +--> chunk-wise/incremental processing
        |
        +--> lightweight production inference
```

Where older project text conflicts with the newer Vercel-only goals, the **newer Vercel-only goals win**.

Do not introduce Railway, Render, Oracle Cloud, or another paid/card-required compute dependency.

---

# 3. SCIENTIFIC NON-NEGOTIABLES

This project must never pretend it can accurately predict from literally any arbitrary CSV or machine.

The correct product behavior is:

```text
uploaded dataset
    -> inspect
    -> identify/map sensors
    -> determine required metadata
    -> compatibility check
    -> validate
    -> preprocess
    -> extract features / FFT
    -> calculate Health Indicator
    -> choose compatible trained model
    -> predict
    -> diagnostics/explanation
    -> visual result
```

Datasets must be classified into states such as:

```text
FULLY_SUPPORTED
ADAPTER_REQUIRED
RETRAIN_REQUIRED
UNSUPPORTED
INVALID_INPUT
```

Unsupported data must **fail closed**.

Never:
- guess sampling frequency
- guess units
- fabricate RUL
- fabricate confidence
- silently map ambiguous sensors
- send an incompatible dataset to a trained model
- use an LLM itself as the numerical RUL predictor
- change validated scientific logic simply to make deployment easier
- introduce train/test leakage

The existing validated ML pipeline remains the numerical source of truth.

LLM/RAG, if present, is for grounded explanation and maintenance context after numerical analysis.

---

# 4. MODEL ROUTING

`model.md` is authoritative.

For implementation:
- use the worker model specified by `model.md`
- normal coding may use the normal/default worker
- cheap models may only handle tasks explicitly allowed by `model.md`

For **testing, scientific verification, acceptance, and merge approval**:

```text
Claude Opus 5
OR
GPT-6 Astra
```

ONLY.

A lower-end implementation model may run preliminary tests, but it must **never issue final PASS**.

The implementation agent must not self-certify completion.

---

# 5. CLAUDE / CODEX EXECUTION POLICY

Claude Code is the primary executor.

Codex CLI is the fallback executor controlled by the existing watchdog/failover system.

If Claude becomes unavailable because of quota/rate-limit/crash:

1. checkpoint current state
2. persist exact current task
3. persist Git status and diff
4. persist tests already run
5. persist remaining work
6. let the watchdog classify the provider failure
7. hand the SAME task to Codex
8. instruct Codex to inspect current state before editing
9. continue rather than restart blindly

Do not allow Claude and Codex to edit the same worktree simultaneously.

Do not bounce an active Codex task back to Claude merely because Claude becomes available again.

---

# 6. WORKTREE RULE

Never perform overnight implementation directly in the stable/main working tree.

For each independent task, use the orchestrator's worktree/branch mechanism.

Conceptually:

```text
overnight/capstone/goal-XX-short-name
```

Before editing:
- verify expected Git state
- identify files likely to change
- avoid parallel tasks with heavy file overlap

Before task completion:
- inspect diff
- run required tests
- run high-model verification
- checkpoint
- commit only the validated task branch

Never:
- force push
- rewrite shared history
- discard unrelated user changes
- clean untracked user files
- merge directly to main without the configured integration gate

---

# 7. EXECUTION LOOP FOR EVERY GOAL

For each queued goal:

```text
READ goal
  ->
READ its exact implementation prompt in prompts.md
  ->
READ model.md routing
  ->
inspect current implementation
  ->
define DONE criteria
  ->
implement in isolated worktree
  ->
run targeted preliminary tests
  ->
checkpoint
  ->
invoke exact high-model testing/acceptance prompt
  ->
if FAIL:
      fix verified defects
      rerun targeted tests
      send back to high-model verifier
  ->
if PASS:
      checkpoint
      commit task
      mark goal DONE
      move to next dependency-safe goal
```

Do not skip the high-model acceptance stage.

Do not mark a task complete because code was written.

---

# 8. REPAIR LIMITS

Follow the overnight system's bounded repair rules.

If the same task repeatedly fails:

- do not loop indefinitely
- record exact failure
- write a complete handoff
- mark `BLOCKED` when repair limit is reached
- move to another independent goal when safe

Scientific uncertainty is a reason to stop and document, not to guess.

---

# 9. CHECKPOINT CONTENT

At every meaningful checkpoint, persist enough information that Codex could continue if Claude disappeared immediately.

Include:

```text
goal/task ID
goal text
executor
current phase
branch/worktree
files changed
important decisions
what has been implemented
what remains
commands run
latest test results
known failures
Git status
relevant diff/commit
exact recommended next action
```

The test is:

> If Claude disappears right now, can Codex safely determine what happened and continue?

If no, the checkpoint is insufficient.

---

# 10. FRONTEND EXPECTATION

The final application must be a polished **Next.js predictive-maintenance website**, not Streamlit.

The UI should be built around real backend outputs and include, where supported:

- dataset upload/analysis
- dataset compatibility status
- machine/dataset summary
- machine health
- Health Indicator
- degradation trend
- RUL result
- model/version information
- FFT/signal analysis
- extracted features
- diagnostics
- reliability/validation information where scientifically defensible
- unsupported/retrain/adapter-required states
- prediction history where implemented
- clear loading/progress/error states
- responsive desktop/mobile UI

Never populate production screens with fake values just to make them look complete.

---

# 11. LARGE DATASET / VERCEL RULES

The production path must be designed around serverless constraints.

Use:
- direct-to-storage upload for large raw datasets
- storage references instead of large API request bodies
- incremental/chunk-wise parsing where scientifically valid
- bounded memory use
- explicit timeouts/failure handling
- temporary data cleanup
- lightweight model loading

Chunk-wise processing must produce scientifically equivalent outputs to the trusted reference pipeline.

If an operation needs a complete signal window, buffer only the required window rather than blindly loading everything.

---

# 12. TESTING PRIORITY

Testing is not a final afterthought.

Maintain and expand tests throughout implementation.

Critical verification areas include:

```text
dataset inspection
schema mapping
sensor identification
sampling-rate handling
compatibility gate
validation
preprocessing parity
feature extraction
FFT correctness
Health Indicator
model routing
RUL inference
unsupported input rejection
API contracts
large-file handling
storage lifecycle
frontend/backend integration
Vercel production build
deployment inference parity
end-to-end upload -> RUL result
```

Final verification is always performed by the high-end verifier defined above.

---

# 13. STARTING PRIORITY

After reconstructing project status, immediately begin the highest-priority unfinished dependency-safe goal.

Do not spend the night only writing plans.

Do not ask me to choose among routine implementation tasks.

Ask me only if:
- authentication is required
- destructive/system-level action needs approval
- a scientifically important choice cannot be resolved from project evidence
- the overnight-system safety policy explicitly requires approval
- a required external credential/service choice is unavoidable

Otherwise proceed.

---

# 14. FIRST EXECUTION RESPONSE

Your first response for this project run should be short.

Use:

```text
Capstone overnight execution started.

Reading goals.md, prompts.md, and model.md, then reconstructing the current repository state and building the executable task queue. I will begin the highest-priority unfinished goal in an isolated worktree and use the configured Claude -> Codex failover automatically.
```

Then begin inspection and coding.

Do not return a giant theoretical explanation before starting.

---

# 15. END-OF-NIGHT REQUIREMENT

At the end of the run, produce the normal overnight report required by the master orchestration system.

For this capstone specifically include:

```text
CAPSTONE OVERNIGHT REPORT

Goals attempted
Goals completed
Goals partially completed
Goals blocked

For every goal:
- goal number
- implementation executor
- verification model
- worktree/branch
- commit SHA
- files changed
- tests run
- verification result
- remaining issues

Scientific pipeline status:
- upload
- dataset inspection
- compatibility
- validation
- preprocessing
- features/FFT
- HI
- model routing
- RUL
- diagnostics

Frontend status
Backend/API status
Vercel deployment status
End-to-end production test status

Claude provider events
Codex fallback events

Full test-suite result
Unresolved blockers
Exact next recommended goals
```

Never hide failed tasks or failed verification.

---

# FINAL COMMAND

**Begin the capstone execution now. Read `goals.md`, `prompts.md`, and `model.md`, inspect the repository, build the real task queue from evidence, create the first isolated worktree, and start implementing the highest-priority unfinished goal. Continue goal-by-goal under the existing overnight supervisor until the nightly runtime ends, a safety/approval boundary is reached, or all currently executable goals are complete.**
