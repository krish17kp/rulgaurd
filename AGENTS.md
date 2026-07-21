# AGENTS.md

## Model classes actually available
- Cheapest: Haiku-class (via Claude Code model routing).
- General: Sonnet 5 (this session's default).
- Highest reasoning: Opus-class, invoked only for audits/hard blockers.

## Local LLM (Ollama, installed and verified 2026-07-21)
- `llama3.1:8b` - report generation candidate.
- `nomic-embed-text` - embeddings for RAG (preferred over adding sentence-transformers).
- `deepseek-r1:1.5b` - available, not used by default.

## Agent roles (installed subagents used as-is; no project-specific agents created - none needed yet)
- Discovery/inventory/manifest work: `general-purpose` or direct tool use (cheap, no agent overhead for this session).
- Code review after non-trivial diffs: `code-reviewer`.
- Security-sensitive code (none yet - no auth/payments/user-input surface in this project): `security-reviewer` if it arises.
- Build failures: `build-error-resolver` / `python-reviewer` as needed.

## Plugin/skill selection policy
Use only tools whose presence was verified this session (see `docs/tooling-inventory.md`). Do not invoke unverified plugin commands.

## Reviewer independence
Any subagent reviewing code must not be the same call that wrote it. For solo-session work, self-review via `ruff check` + `pytest` + a fresh read-through stands in; escalate to `code-reviewer` agent for milestone gates.

## Worktree policy
Not used yet - all M0/M1 work is small and sequential in one working tree. Reserve worktrees for FEMTO-adapter-vs-college-adapter parallel work if that becomes a bottleneck later.

## Ponytail policy
Ponytail plugin not detected as installed in this Claude Code instance during discovery. Its reduction ladder (does this need to exist / stdlib / native / installed dep / minimum diff) is applied manually per `command.md` section 7.4 since the plugin itself isn't available.

## Caveman policy
Caveman mode is active at the harness level (user global config) for prose only. Per `command.md` 7.5, code, formulas, schemas, data contracts, test failures, and methodology are never compressed - this file and all `docs/` are written in full language regardless of harness caveman setting.

## Escalation rules
Third failed implementation attempt on a task -> stop, mark `BLOCKED_TECHNICAL`, escalate to highest-reasoning model. Any leakage/methodology ambiguity -> stop and record in `docs/decisions.md` before continuing.
