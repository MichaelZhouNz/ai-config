# ai-config

My portable AI-agent configuration for **Claude Code** and **OpenAI Codex CLI**. One repo,
one script, identical behaviour on every PC.

## Install

```powershell
git clone https://github.com/MichaelZhouNz/ai-config D:\dev\personal\ai-config
cd D:\dev\personal\ai-config
.\install.ps1 -WhatIfOnly   # preview
.\install.ps1               # apply
```

Then follow the manual steps the script prints (machine-specific settings, Codex `config.toml`,
and the public skills plugin from [MichaelZhouNz/skills](https://github.com/MichaelZhouNz/skills)).

Re-run `install.ps1` after changing anything under `claude/`, `codex/` or `shared/hooks/`.
Changes under `shared/skills`, `shared/commands` and `shared/guidelines` are live via junctions.

## What gets installed where

| Repo path | Claude Code | Codex | Mechanism |
|---|---|---|---|
| `shared/guidelines/*.md` | `~/.claude/guidelines/` (imported by `CLAUDE.md`) | concatenated into `~/.codex/AGENTS.md` | junction / generated |
| `shared/skills/*` | `~/.claude/skills/` | `~/.codex/skills/`, `~/.agents/skills/` | junction |
| `shared/commands/*.md` | `~/.claude/commands/` | – | junction |
| `shared/hooks/*.mjs` | `~/.claude/hooks/` | `~/.codex/hooks/` | copy, `{{HOME}}` substituted |
| `claude/CLAUDE.md`, `ORCHESTRATION.md`, `settings.json`, `keybindings.json` | `~/.claude/` | – | copy, `{{HOME}}` substituted |
| `codex/hooks.json` | – | merged into `~/.codex/hooks.json` (other events kept) | merge |
| `codex/config.shared.toml` | – | apply by hand | manual |

## Guidelines

Loaded into every session of both tools:

- **git-policy** – never commit, push or open a PR without explicit approval each time.
- **orchestration** – act as the orchestrator; delegate implementation to sub-agents. Codex gets the
  generic `shared/guidelines/orchestration.md`; Claude gets `claude/ORCHESTRATION.md`, which adds the
  model-tier routing table (haiku / sonnet / opus / fable → lookup / design / implement skills).
- **KARPATHY** – think before coding, simplicity first, surgical changes, goal-driven execution.
- **RTK** – use the `rtk` token-saving proxy for shell commands.

## Hooks

- **rtk** (Claude only) – rewrites shell commands through `rtk`.
- **check-pr-description** (both) – denies `gh pr create` unless the body has `## TLDR`,
  `## Technical Description`, `## Affected Projects` and a `## Testing` table, and tells the
  agent to use the `generate-pr-description` skill. Fires only when `gh pr create` is in command
  position, so mentioning it in text does not trip it.

## Skills

Private skills here: `design`, `implement`, `lookup` (model-tiered delegation), `dotnet-review`,
`domain-study`, `tech-study`, `fullstack-qa-tester`.

Public skills (`pr-brief`, `generate-pr-description`) live in
[MichaelZhouNz/skills](https://github.com/MichaelZhouNz/skills) and are installed as a plugin.

## Machine-specific, never committed

`~/.claude/settings.local.json` (paths, status line, local marketplaces) – start from
`claude/settings.local.example.json`. `~/.codex/config.toml` holds trust levels and marketplace
paths and is never written by the installer.

## Notes

- The orchestration guideline asks the agent to delegate to sub-agents. On Codex that only
  becomes actionable with `[features] multi_agent = true` in `config.toml` (left commented in
  `config.shared.toml`). The `design` / `implement` / `lookup` skills name Claude model tiers.
- Prerequisites on PATH: `node`, `rtk`, `gh`.
