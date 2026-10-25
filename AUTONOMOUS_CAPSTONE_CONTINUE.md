# AUTONOMOUS_CAPSTONE_CONTINUE.md

## Purpose

This prompt is for the **actual unattended overnight execution** of the capstone after the earlier session stopped too early.

You are **not** being asked to do one task and then hand control back to the user.

You are being asked to operate as a **continuous autonomous executor** over the capstone task queue until:

1. the configured nightly runtime expires,
2. every currently executable task is complete,
3. a genuine safety/authentication boundary blocks *all* remaining work,
4. or the external overnight supervisor terminates the run.

A single blocked task is **not** a reason to stop the night.

A missing deployment credential is **not** a reason to stop the night.

A question that can be answered from `goals.md`, `prompts.md`, `model.md`, Git history, tests, repository state, or a safe engineering default is **not** a reason to ask the user.

---

# 0. IMPORTANT: DO NOT END WITH A HANDOFF AFTER ONE MILESTONE

The previous session stopped after producing a handoff.

That is not acceptable for an unattended overnight run.

A handoff/checkpoint is something you WRITE DURING THE RUN so another executor can continue.

It is **not** the end of the run.

After every completed, blocked, or failed task:

```text
checkpoint
-> update task state
-> select the next dependency-safe task
-> continue immediately
```

Do not end the session merely because:
- one goal was completed,
- one goal was blocked,
- a commit was created,
- a test suite passed,
- a test suite failed,
- a deploy cannot be performed yet,
- a new dependency is needed,
- a branch is ready for review,
- you think "the user should decide what is next."

The user has already decided:

> Continue autonomously through the project goals.

---

# 1. SOURCE OF TRUTH

Read these files completely before continuing:

```text
goals.md
prompts.md
model.md
START_CAPSTONE_OVERNIGHT.md
```

Also read the latest session handoff if present.

Repository code + Git history + executed tests are the truth about implementation status.

Documentation alone is not proof of completion.

---

# 2. CURRENT SESSION STATE TO RESUME FROM

The previous session created substantial M11 work.

Current known branch chain:

```text
cross-dataset (base)
  -> overnight/capstone/goal-01-fastapi-backend
  -> overnight/capstone/goal-02-nextjs-frontend
```

Current known tip from the handoff:

```text
074bd54
```

Known completed work includes:
- FastAPI service
- `/health`
- `/models/info`
- `/predict/rul`
- `/predict/hi`
- `/dataset/inspect`
- `/predictions/history`
- `/models/evaluation`
- request logging
- request IDs
- upload-size rejection
- Next.js frontend scaffold
- `/upload`
- `/degradation`
- `/evaluation`
- shared navigation
- Vercel entry/configuration
- API e2e test
- milestone/TODO updates

Known last reported verification:
- `233 passed`
- `ruff check .` clean
- frontend build/lint previously clean

Do not blindly trust those claims.

Re-run enough checks to establish the actual current state before continuing.

---

# 3. PREVIOUS SESSION GAPS THAT MUST NOT CAUSE ANOTHER STOP

The previous handoff explicitly reported these unfinished areas:

- no real Vercel deployment
- production model artifact delivery unresolved
- raw CSV -> features -> RUL API flow incomplete
- `/dataset/inspect` too shallow
- no proper sampling-rate/unit handling
- incomplete compatibility states
- no direct-to-storage upload path
- no chunk-wise raw processing
- prediction history not persistent
- no auth/rate limiting/request timeout handling
- no frontend automated test stack
- no proven Streamlit parity
- stale `.claude/rules/dashboard.md`
- stale root `CLAUDE.md`
- no Claude -> Codex watchdog/failover actually implemented
- no real worktree orchestration
- no verified Vercel production run

These are **work items**, not reasons to stop.

---

# 4. DECISIONS ARE ALREADY MADE

Do NOT ask the user again about these:

## Architecture

The project is deliberately pivoting to:

```text
Next.js
+
Python/FastAPI
+
Vercel-only production target
```

The older "no FastAPI / no JS frontend" instruction is stale for this branch.

Where a local project rule contradicts the explicit newer project goals, update or retire the stale local rule carefully and document the change.

Do not revert the project back to Streamlit as the production application.

Streamlit may remain temporarily for parity/reference until the replacement is proven.

## Merge policy

Do **not** merge to `main` automatically.

Continue implementation on isolated overnight branches/worktrees.

A missing decision about merging to main must never stop the run.

## Deployment credentials

If Vercel login/authentication is unavailable:

```text
mark actual deployment step = BLOCKED_AUTH
continue every task that can be completed locally
```

Do not stop the night just because Vercel cannot be contacted.

## Frontend testing dependencies

Project-local dev dependencies are allowed when low-risk and justified.

If Vitest or Playwright is appropriate, install/configure it locally in the project and continue.

Do not stop to ask whether a normal test dependency may be added.

## Model-verifier naming

If `model.md` names a verifier model that is not actually available in the current environment:

- use the strongest actually available allowed verifier,
- prefer real Claude `opus` for Claude-side verification,
- or the strongest available Codex/OpenAI verifier,
- record the substitution,
- continue.

Do not stop because a marketing/model alias differs from the local CLI name.

---

# 5. FIRST ACTION: VERIFY THE OVERNIGHT SUPERVISOR EXISTS

The previous session reported:

> no Claude -> Codex watchdog/failover system; no worktree orchestration

This means the overnight system was not actually complete.

Before assuming unattended execution is reliable, inspect the nightshift/orchestrator installation and answer internally:

```text
Can the supervisor detect Claude exit/quota/stall?
Can it checkpoint state?
Can it start Codex on the SAME task?
Can it continue the task queue after normal task completion?
Can it survive terminal closure?
Can it persist state?
Can it create isolated worktrees?
```

If the answer to any critical item is NO:

**finish the supervisor/watchdog setup first**, following the separate master overnight-system prompt.

Do not merely describe what is missing.

Implement it.

Run the required dry-run and simulated-quota tests.

Only after the supervisor actually works should you trust it for a full unattended capstone run.

---

# 6. CONTINUOUS EXECUTION LOOP

Once the supervisor is proven, enter this loop and remain in it:

```text
while nightly_runtime_remaining:

    load durable task state

    if current task exists:
        resume it
    else:
        select highest-priority dependency-safe unfinished goal

    create/use isolated worktree

    inspect current code before editing

    execute implementation prompt from prompts.md

    run preliminary targeted tests

    checkpoint durable state

    run required HIGH-MODEL verification

    if verification == PASS:
        commit
        mark goal/task DONE
        checkpoint
        select next task
        continue

    if verification == FAIL and repair attempts remain:
        fix only verified defects
        rerun tests
        reverify
        continue

    if repair attempts exhausted:
        mark BLOCKED
        write exact handoff
        checkpoint
        select another independent task
        continue
```

There is no `return to user` inside this loop.

---

# 7. TASK-SELECTION POLICY

Prefer tasks in this order unless dependencies require otherwise:

1. scientific correctness/blockers
2. end-to-end raw dataset -> RUL path
3. dataset inspection + compatibility + metadata
4. preprocessing/features/FFT/HI parity
5. model routing/artifact loading
6. backend/API completeness
7. large-file/direct-storage/chunking
8. frontend integration
9. frontend automated tests
10. production/runtime hardening
11. Vercel-specific build/deploy preparation
12. real Vercel deployment when credentials exist
13. documentation/polish

Do not spend the whole night on visual polish while the scientific pipeline is incomplete.

---

# 8. WHAT TO DO WHEN A TASK IS BLOCKED

A blocked task must be handled like this:

```text
1. classify the blocker
2. persist it
3. state the exact missing dependency
4. mark the task BLOCKED
5. inspect queue
6. immediately continue another independent task
```

Examples:

### Vercel auth missing

```text
BLOCKED: production deployment
CONTINUE:
- local production build
- deployment-equivalent tests
- API work
- upload work
- frontend tests
- model packaging
```

### Model artifact storage decision unresolved

Do not violate existing artifact policy blindly.

Implement:
- storage abstraction
- artifact manifest
- loader interface
- checksum/version validation
- local/dev implementation
- Vercel-compatible delivery path where possible

If actual remote artifact provisioning requires credentials:

```text
block only provisioning
continue implementation/tests
```

### One failing test cannot be solved

After bounded repair attempts:

```text
mark that task BLOCKED
save evidence
continue a different task
```

---

# 9. RAW DATA PIPELINE IS A PRIORITY

The production app should not require users to manually pre-extract features.

Build toward:

```text
raw uploaded dataset
-> inspect
-> validate metadata
-> map schema
-> preprocess
-> feature extraction
-> FFT where valid
-> HI
-> model routing
-> RUL
-> diagnostics
-> frontend result
```

The API must not pretend raw-CSV support exists until this path is real.

---

# 10. COMPATIBILITY MUST BE EXPLICIT

Implement and preserve distinct states:

```text
FULLY_SUPPORTED
ADAPTER_REQUIRED
RETRAIN_REQUIRED
UNSUPPORTED
INVALID_INPUT
```

Do not collapse scientifically different states just to simplify the API.

Parsing successfully does not mean the model is valid for that machine/dataset.

---

# 11. LARGE-FILE / SERVERLESS POLICY

For the Vercel-only target:

- do not proxy large raw files through a normal small request body
- use direct-to-storage upload where supported
- pass storage reference + metadata to analysis
- read/process incrementally where scientifically valid
- keep memory bounded
- clean temporary raw data
- preserve complete windows when required for FFT/features
- compare chunked results against trusted reference outputs

If actual storage provisioning requires auth, implement the code and tests locally and block only the remote provisioning step.

---

# 12. PRODUCTION MODEL ARTIFACT POLICY

Do not casually commit large ignored model artifacts only to make deployment easy.

First inspect:
- artifact sizes
- current policy
- loader expectations
- Vercel bundle limits
- available Vercel-compatible storage path

Implement a versioned artifact manifest containing at least:

```text
model name
model version
feature schema version
preprocessing version
expected checksum
expected filename/object
supported adapter/domain
```

The loader must fail clearly on:
- missing artifact
- corrupt artifact
- checksum mismatch
- version mismatch

If remote artifact delivery cannot be provisioned without credentials, block only that final provisioning action.

---

# 13. FRONTEND TESTING

Do not leave the new Next.js application with no automated frontend tests.

Add an appropriate project-local testing stack.

At minimum cover:
- upload form
- validation/error state
- unsupported dataset state
- RUL result rendering
- HI/degradation rendering
- API failure
- loading/progress state
- navigation
- no fake fallback values

Add browser/E2E tests where practical.

Final acceptance still requires the configured high-end verifier.

---

# 14. STALE RULES / DOCS

The handoff reported stale architecture instructions.

Reconcile them carefully.

Do not leave active local agent instructions that say:

```text
NO FastAPI
NO REST
NO JavaScript frontend
```

while the explicit project goal is now Next.js + FastAPI.

Update the relevant agent instructions so future Claude/Codex sessions do not fight the current architecture.

Preserve history where useful, but current instructions must be unambiguous.

---

# 15. CLAUDE -> CODEX FAILOVER

This must be an external supervisor behavior, not wishful prompting.

When Claude exits because of:
- quota
- rate limit
- crash
- stall
- network failure

the supervisor must:

```text
checkpoint
classify failure
freeze Claude launches when appropriate
load task state
inspect Git status/diff
launch Codex
tell Codex this is continuation
continue SAME task
verify
commit if passed
continue task queue
```

Codex must not restart the task blindly.

If Codex itself fails:

```text
checkpoint
classify failure
retry according to policy
or mark blocked and continue another task
```

---

# 16. NORMAL TASK COMPLETION MUST NOT END THE PROCESS

If Claude completes one task normally:

```text
DO NOT EXIT
DO NOT PRINT FINAL HANDOFF AND STOP
```

Instead:

```text
checkpoint
commit if accepted
select next task
continue
```

Provider failover is for failure/unavailability.

Task progression is independent of provider failover.

---

# 17. CONTEXT-LIMIT HANDLING

Do not wait until context is exhausted.

Checkpoint frequently.

If the CLI/supervisor supports starting a fresh executor session for the next task or after a checkpoint, use it.

Durable state must contain enough context that a fresh Claude or Codex session can resume without relying on the previous conversation.

The repository + state files + Git + tests are memory.

---

# 18. CHECKPOINT FREQUENCY

Checkpoint at least:
- task start
- plan established
- after a meaningful implementation milestone
- after tests
- after verifier result
- after commit
- when blocking issue discovered
- before provider handoff

For long tasks, also checkpoint periodically.

Never depend on a final message for state preservation.

---

# 19. HIGH-MODEL VERIFICATION

Every meaningful goal requires independent verification.

Implementation model may not self-approve.

Use the strongest actually available verifier required by `model.md`.

On this Claude environment, if the real high-end available model is exposed as:

```text
opus
```

use that.

Record:
- verifier
- tests run
- result
- defects found
- fixes
- re-verification result

A commit without required verification is not DONE.

---

# 20. DO NOT STOP FOR THESE QUESTIONS

Do not ask:

- "Should I continue?"
- "Which goal next?"
- "Should I add frontend tests?"
- "Should I create another branch?"
- "Should I keep working?"
- "Should I merge to main?"
- "Should I deploy now?"
- "Should I update stale docs?"
- "Should I fix this failing test?"

Defaults:

```text
continue
choose next dependency-safe goal
add required tests
use isolated branch/worktree
never auto-merge main
deploy only when credentials exist
update stale architecture docs/rules
fix failing tests within repair limit
```

---

# 21. ASK THE USER ONLY FOR TRUE HUMAN-ONLY BLOCKERS

Interrupt only for:
- interactive authentication that cannot be completed non-interactively
- destructive/system-level approval
- payment/card requirement
- secret/credential creation
- irreversible external action
- scientifically material ambiguity that cannot be resolved from evidence
- a conflict where two user-approved requirements are impossible to satisfy simultaneously

Even then:

```text
checkpoint the blocked task
continue other independent work first
```

Only stop the entire run if **all remaining tasks** require a human-only action.

---

# 22. END-OF-NIGHT CONDITIONS

The run may finish only when one of these is true:

### A. Nightly runtime expired

Generate morning report.

### B. All executable goals complete

Generate morning report.

### C. All remaining goals blocked by genuine human-only dependencies

Generate morning report explaining each blocker.

### D. External supervisor explicitly stops the run

Checkpoint first if possible, then generate/recover report.

Do not invent a fifth reason.

---

# 23. MORNING REPORT

Produce one concise report containing:

```text
run start/end/duration

goals attempted
goals completed
goals blocked
goals still queued

for every attempted goal:
- executor
- verifier
- branch/worktree
- commit
- tests
- result
- blocker if any

Claude provider events
Codex provider events
handoffs

full test status
frontend build/lint/test status
scientific parity status
raw-upload pipeline status
Vercel readiness/deployment status

unmerged branches
uncommitted files
attention required
exact next actions
```

Do not hide failures.

---

# 24. IMMEDIATE RESUME INSTRUCTION

Start now.

1. Inspect the current repository and verify the handoff state.
2. Inspect the actual overnight supervisor/watchdog implementation.
3. If the watchdog/failover is not complete, finish and dry-run it first.
4. Re-run baseline tests on the current capstone branch.
5. Rebuild the unfinished goal queue from `goals.md` and `prompts.md`.
6. Resume the highest-priority unfinished goal.
7. Continue task after task without waiting for the user.
8. If Claude becomes unavailable, let the supervisor hand the same task to Codex.
9. If one task blocks, move to another.
10. Keep running until an allowed end-of-night condition occurs.

Your first response must be only:

`Resuming autonomous capstone execution. I will not stop after individual tasks; blocked tasks will be checkpointed and skipped while the next executable goal continues. First I am verifying the watchdog/failover system, then I will resume the capstone queue.`

Then begin executing.
