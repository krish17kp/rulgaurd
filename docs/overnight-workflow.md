# Overnight autonomous-development workflow

This page documents the process used to run unattended, multi-hour development
sessions against this repository ("overnight work"), and the safety
guarantees an operator can rely on. It does not describe or ship any
orchestration tool - the supervisor/scheduler that drives this process is
local-only tooling that lives outside this repository. This page describes
the *process contract* that any such tool (or a human following the same
steps by hand) must uphold, so the guarantees hold regardless of which
tool or model implements them.

Related decisions: `docs/decisions.md` D11 (cached FEMTO-fit HI/RUL models
must never be silently applied to other datasets) applies to overnight work
exactly as it does to interactive work - no exception is made because a
change was made unattended.

## Why this exists

Goals 39-44 ask for a workflow that lets
development continue unattended without an operator watching every step,
while guaranteeing that:

- stable code and trained model artifacts are never damaged or silently
  overwritten,
- every change is checked by tests and by a review step before it is
  considered real work rather than just "code that was written," and
- an operator can reconstruct, the next morning, exactly what happened,
  what passed, what failed, and what still needs a human decision.

The sections below describe each part of that contract.

## One task, one isolated branch/worktree

Every overnight task is scoped to a single, independent unit of work (one
goal, or a small piece of a goal) and is executed in its own Git branch and
worktree, checked out from the same base commit as the other tasks running
that night. This gives each task:

- a private working tree, so two tasks editing unrelated files never race
  or clobber each other's uncommitted state,
- a private branch, so a task's history is reviewable and mergeable on its
  own, independent of how other tasks that night turn out,
- an explicit "owner" (the task itself) for the files it touches, so file
  ownership for a given night's batch is visible from the branch names and
  diffs rather than implicit.

Where two tasks would need to touch clearly overlapping files (for example,
the same API route or the same page component), running them concurrently
in the same night's batch is avoided where possible - the overlap is
resolved by sequencing rather than by letting both tasks race on the same
file.

## Worker / supervisor split

Each task runs in two roles that are never the same actor:

1. **Worker** - implements one task inside its isolated worktree, following
   the constraints handed to it (which files it may touch, which
   dependencies it may not add, which invariants like D11 it must not
   violate). The worker runs the project's tests and linter for its own
   change before handing the task off, but it is explicitly **not allowed
   to mark its own work complete**. A worker that finds the task
   scientifically ambiguous, unsafe, or outside its scope stops and reports
   a blocker instead of improvising or guessing.
2. **Supervisor** - the actor that decides whether a task's result is
   actually accepted. The supervisor is the only actor that is allowed to
   commit, merge, or advance a task past "implemented." It independently
   re-runs verification (see below) rather than trusting the worker's own
   summary of what it did.

This split exists so that "the code compiles and the worker says it's done"
is never sufficient for a change to land - a second, independent pass is
required before anything is treated as finished.

## Local-only commits during the night

While a task is in progress, all commits stay local to that task's
worktree/branch. Nothing is pushed to a shared or remote location during
the night, and the shared main branch is never touched directly by a
worker. This means:

- a task that goes wrong (bad implementation, crashed mid-way, left a dirty
  worktree) is fully contained to its own branch and can be discarded
  without affecting any other task or the main branch,
- there is no window during the night where partially-verified work is
  visible anywhere outside its own isolated worktree,
- if the same night's session is interrupted, every task's state is exactly
  what its own commits say it is - nothing was pushed further than that.

## Verification before a task is marked done

A task is never considered complete because a worker produced code. Before
a task can be marked done, its worktree must pass a fixed verification gate
run from that worktree:

- the full automated test suite,
- the linter,
- a check that the task stayed within its declared scope (for a docs-only
  task like this one, that the tracked application code - `src/`, `tests/`,
  `frontend/` - is unchanged),
- any task-specific checks called for by that task (for example, that a
  generated document contains no private paths or secrets).

Only after this gate passes does the task move to independent review.

## Independent high-model review before integration

The model that implements a task is never the model that gives it final
sign-off. Implementation work may be done by a default/worker-tier model; **final
testing, scientific review, and merge acceptance must be done by a
high-end model**, working from the goal definition and the actual Git diff
rather than from the worker's own summary. The reviewer re-runs the
relevant tests, checks for regressions, unsupported or fabricated claims
(metrics, confidence, sample rates, units, dataset/machine support), data
leakage, and scope creep, and only then returns a pass/fail verdict. A task
whose own worker was also its verifier is not considered reviewed.

If review finds a defect, the fix goes back through the same loop
(implement -> targeted tests -> fix -> targeted tests green) before the
task is reconsidered for integration - review is never skipped just
because a fix looks small.

## One local integration branch, then a full regression run

Only after a task's own verification and independent review both pass does
it get merged - and it is merged into **one local integration branch** that
collects that night's accepted tasks, not directly into `main` and not
pushed anywhere. Tasks are merged into the integration branch in a
deterministic order (declared ahead of time, e.g. by goal number or by
dependency), so the result is reproducible.

After each merge into the integration branch, the tests affected by the
merge (and any conflicts it required resolving) are rerun against the
integration branch, and once the last task of the night is merged, the
**full test suite and linter are run against the integration branch** -
not just the targeted tests exercised along the way. Any regression found
at either stage is treated as a defect in the integration, not in the
individual task: it is fixed (or the offending merge is backed out) and
the full suite is re-run until it is green before the branch is considered
ready to hand to a human for the actual push/merge to `main`. This repository's own history record (`git log`) is the source
of truth for what actually landed; the workflow does not push to `main`
or to any remote on its own.

## Guardrails for autonomous agents

Any agent (worker, supervisor, or a human operating the same process by
hand) that runs part of this workflow must respect the following
guardrails at all times:

- never force-push or reset the main/default branch,
- never discard unrelated work - if something unexpected is found in a
  worktree or branch, set it aside (for example, by moving or committing
  it) rather than deleting it,
- checkpoint (commit) before making a risky change, so the change can be
  inspected or backed out without losing prior progress,
- version model artifacts rather than overwrite them in place, so a
  previous trained model remains recoverable after a new one is produced.

## Final report

At the end of a night's session, a report is produced covering:

- **completed work** - which goals/tasks were implemented, reviewed, and
  merged into the integration branch,
- **failed or blocked tasks** - which tasks stopped short, and why
  (test failure, scope ambiguity, scientific concern, missing artifact,
  etc.),
- **test results** - the exact suites run and their pass/fail outcome, both
  per-task and for the final full-suite run against the integration branch,
- **changed files** - the file-level diff summary for each merged task,
- **branches/worktrees** - which branch and worktree each task ran in, so
  its history can be inspected independently,
- **commits** - the commits produced by each task, in the order they were
  merged into the integration branch,
- **model versions used** - which model implemented and which model
  reviewed each task, consistent with the worker/supervisor split described
  above,
- **failures/fixes** - any defect found during review, the fix applied, and
  the targeted re-verification that followed,
- **remaining work** - what is still open, and what the next task or
  decision should be.

The report never hides a failed attempt; a task that was tried and
abandoned is recorded as such rather than omitted.

## What an operator checks each morning

Before treating an overnight session's output as usable, an operator
should, at minimum:

1. Read the final report first, not the raw diffs, to get the shape of
   what happened.
2. Confirm the integration branch's full test suite and linter run are
   actually green (re-run locally if in doubt - do not trust the report
   alone for anything going toward `main`).
3. Review the diff for each merged task, checking in particular that no
   task exceeded its declared scope, no dependency was added silently, no
   secrets or private paths were committed, and no trained model artifact
   was modified without an explicit, documented decision.
4. Check for any task marked blocked or needing a human decision, and
   resolve those explicitly rather than letting them silently drop.
5. Confirm `main` was not touched directly overnight - only the local
   integration branch should contain the night's merges, still awaiting
   the operator's own push/merge decision.
6. Only after the above, merge the integration branch into `main` (or
   push it) as a deliberate, human-approved action - the workflow itself
   never does this step automatically.
