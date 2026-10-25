\# Nightshift — Parent-Session Survival and Credential-Gate Hardening

This task belongs to Nightshift, not the capstone implementation branch.

Do not rebuild Nightshift from scratch. Preserve existing queue, sandbox, checkpoint, verification, failover, and resume behavior.

\#\# A. Parent-session survival

Make Nightshift independent of the outer Claude Code session.

Use an appropriate user-level persistent mechanism, preferably systemd \--user if it fits the machine and architecture.

Prove:  
\- terminal closes → Nightshift continues  
\- parent Claude Code exits → Nightshift continues  
\- worker SUCCESS → next queued task starts automatically  
\- Claude quota/failure → same task continues with Codex  
\- supervisor/service restarts → persisted queue resumes  
\- start/stop/status/logs/report remain simple

Do not enable risky boot behavior until tests pass.

\#\# B. Credential-gate false positive

Reproduce the prior benign credential-gate event without exposing credential values.

Fix overly broad needle collection while preserving fail-closed real-secret detection.

Regression tests:  
\- real secret → BLOCK  
\- actual known credential value → BLOCK  
\- benign long metadata/config string → ALLOW  
\- credential-like staged diff → correct classification without printing value

\#\# C. Supervisor concurrency

Prevent two independent supervisors from managing the same repo concurrently unless explicit safe support exists. Use a durable repo/run lock or equivalent.

\#\# Final survival test

Queue Task A, Task B, Task C. Start Nightshift through the persistent mechanism. After Task A begins, terminate the parent interactive Claude/session shell.

Expected:  
\- Nightshift remains alive  
\- task state remains intact  
\- Task A completes or safely resumes  
\- Task B starts  
\- Task C starts  
\- final report is produced  
\- no human interaction

Do not modify capstone main.