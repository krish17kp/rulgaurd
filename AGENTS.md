# AGENTS.md

## Model classes actually available
- Cheapest: Haiku-class (via Claude Code model routing).
- General: Sonnet 5 (this session's default).
- Highest reasoning: Opus-class, invoked only for audits/hard blockers.

## Local LLM (Ollama)
Not installed on the current (Linux) machine — `ollama` and `faiss-cpu` remain uninstalled and M7 (RAG/local-LLM report generation) is deliberately deferred, not blocked on this. `llama3.1:8b` (generation) and `nomic-embed-text` (embeddings) were verified on the original Windows machine, but that install did not carry over the migration — re-verify before starting M7.

## Agent roles
Project-specific subagents exist under the capstone root's `.claude/agents/`: `explorer` (Haiku, read-only recon), `implementer` (Sonnet), `debugger` (Sonnet), `ml-architect` (Opus, scientific validity), `code-reviewer` (Sonnet, read-only), `security-reviewer` (Opus, read-only), `verifier` (Sonnet, read-only). Use these instead of generic `general-purpose` calls where one fits.

## Plugin/skill selection policy
Ponytail (YAGNI/over-engineering audits — `ponytail-audit`, `ponytail-debt`, etc.) is installed and active. Use only tools whose presence is actually verified this session; do not invoke unverified plugin commands.

## Reviewer independence
Any subagent reviewing code must not be the same call that wrote it. For solo-session work, self-review via `ruff check` + `pytest` + a fresh read-through stands in; escalate to `code-reviewer` agent for milestone gates.

## Worktree policy
Not used — all work through M5 has stayed in one working tree; project size doesn't currently justify isolation.

## Caveman policy
Caveman mode is active at the harness level (user global config) for prose only. Per `command.md` 7.5, code, formulas, schemas, data contracts, test failures, and methodology are never compressed - this file and all `docs/` are written in full language regardless of harness caveman setting.

## Escalation rules
Third failed implementation attempt on a task -> stop, mark `BLOCKED_TECHNICAL`, escalate to highest-reasoning model. Any leakage/methodology ambiguity -> stop and record in `docs/decisions.md` before continuing.
