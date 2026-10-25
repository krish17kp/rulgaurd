\# M12 — Parallel Capstone Completion

You are the MAIN ORCHESTRATOR for the capstone M12 phase.

Read fully before assigning work:  
\- goals.md  
\- prompts.md  
\- model.md  
\- latest capstone handoff  
\- latest Nightshift handoff  
\- current Git status/log  
\- current test results

\#\# Final M12 target

Raw dataset  
→ inspection  
→ metadata  
→ compatibility  
→ validation  
→ preprocessing  
→ segmentation  
→ time/frequency features  
→ FFT where valid  
→ Health Indicator  
→ model routing  
→ RUL  
→ diagnostics  
→ polished Next.js results  
→ Vercel-ready production path

\#\# Parallel execution

Use separate Git worktrees and separate implementation subagents.

MAX\_PARALLEL\_MODIFYING\_AGENTS=3.

Never allow two agents to modify the same worktree.

Every modifying task must declare:  
\- TASK  
\- WORKTREE  
\- BRANCH  
\- FILES/DIRECTORIES EXPECTED TO CHANGE  
\- TESTS IT WILL RUN

If two tasks need the same high-risk shared file, serialize them instead of racing them.

\#\# Verification rule

The implementation agent cannot self-approve.

For every task:  
1\. implement in isolated worktree  
2\. run targeted tests  
3\. checkpoint  
4\. commit candidate work  
5\. launch a fresh strongest-available verifier allowed by model.md  
6\. verifier independently reads the goal and diff  
7\. if NEEDS\_FIX, repair verified defects  
8\. re-run tests and re-verify  
9\. mark ACCEPTED only after evidence

\#\# Parallel waves

Wave 1:  
\- 01\_COMPATIBILITY\_ADAPTERS.md  
\- 04\_MODEL\_ARTIFACTS.md  
\- 05\_FRONTEND\_COMPLETE.md

Wave 2:  
\- 02\_RAW\_DATA\_TO\_RUL.md  
\- 03\_LARGE\_DATA\_VERCEL.md  
\- 06\_FRONTEND\_TESTING.md

Wave 3:  
\- 07\_API\_HARDENING.md  
\- 08\_SCIENTIFIC\_E2E.md  
\- 09\_VERCEL\_DEPLOYMENT.md

Wave 4:  
\- 10\_FINAL\_INTEGRATION.md

11\_NIGHTSHIFT\_RESILIENCE.md belongs to the Nightshift tool and may run independently.

A completed task does not end M12.  
ACCEPTED → checkpoint → record commit → queue next task → continue.  
BLOCKED → checkpoint → mark blocker → continue another independent task.

Begin by reconstructing the current integration state from Git and executed tests, then launch Wave 1\.