---
name: tech-study
description: Explore an entire repo and generate TECH-STUDY.md — a study guide for a junior developer covering the technologies, design patterns, and engineering techniques the repo uses (how things work), deliberately excluding business/domain logic. Use when the user wants to "study this repo", "learn the tech in this codebase", "generate a tech study guide", or onboard someone on techniques rather than the domain.
argument-hint: "[path to repo root, defaults to cwd] [--depth quick|deep]"
---

# Tech Study Guide Generator

Produce `TECH-STUDY.md` at the repo root: a self-contained study document that teaches a junior developer **how this repo works as a piece of engineering** — the stack, the patterns, the techniques, the infrastructure — so they can recognize and reuse these techniques anywhere.

## Core principle: technique, not domain

The guide explains the **transferable knowledge** a developer carries to their next job. Apply this filter to everything you write:

- ✅ "This repo uses MediatR to implement CQRS — every request is a class, handled by a single handler, decorated by pipeline behaviors for validation and logging. Here's how the dispatch works…"
- ❌ "The OrderService calculates delivery windows for meal-kit subscriptions…" (domain — exclude)
- ✅ Use domain code as the *example* when illustrating a technique (real code beats invented code), but explain the *mechanism*, never the business rule.

When a file mixes both, extract only the technique: "ignore what it computes; notice *how* it's structured."

## Phase 1 — Inventory (broad scan)

Establish the ground truth before writing anything. Look at:

1. **Manifests & lockfiles**: `*.csproj`, `Directory.Packages.props`, `package.json`, `pyproject.toml`, `go.mod`, `Cargo.toml`, `pom.xml`, `Gemfile`, etc. Extract every significant dependency and its role.
2. **Solution/workspace layout**: project/module structure, naming conventions, layering (e.g., `*.Api` / `*.Application` / `*.Domain` / `*.Infrastructure`).
3. **Configuration & composition roots**: `Program.cs` / `Startup.cs` / `main.ts` / `app.py` / DI container registrations, middleware pipelines, module wiring.
4. **Infrastructure as code & CI/CD**: Dockerfiles, docker-compose, Kubernetes/Helm, Terraform/Bicep, GitHub Actions / Azure Pipelines / Jenkins files.
5. **Quality tooling**: test projects and frameworks, linters, formatters, analyzers, pre-commit hooks, code coverage config.
6. **Data layer**: ORM configs, migrations folders, raw SQL, message broker / queue configs, caching layers.
7. **Cross-cutting**: auth setup, logging/telemetry config, feature flags, error handling conventions, retry/resilience policies.

For large repos (roughly >300 source files), fan out **parallel Explore agents** in a single message, one per area above, each returning a structured summary (technology found, where it's wired up, 2–3 representative file paths). For small repos, read directly. Never paste large file dumps into the guide — distill.

## Phase 2 — Pattern & technique detection

For each area, identify the *named* patterns and techniques in play. Hunt for evidence, don't guess from folder names. Typical catalog to check against (non-exhaustive — add what you actually find):

- **Architecture**: layered/clean/hexagonal/onion, vertical slice, modular monolith, microservices, event-driven, plugin architecture.
- **Application patterns**: CQRS, mediator, repository + unit of work, specification, domain events, outbox, saga/process manager, strategy, factory, decorator, options pattern, result/either types vs exceptions.
- **API techniques**: REST conventions, versioning, pagination, validation pipelines, middleware/filters/interceptors, minimal APIs vs controllers, GraphQL resolvers, gRPC, OpenAPI generation.
- **Data techniques**: migrations strategy, ORM mapping styles, query projection, connection/transaction scoping, N+1 avoidance, caching strategy (where, what, invalidation), idempotency.
- **Async & messaging**: background jobs, queues/topics, consumer patterns, retry/backoff, dead-lettering, concurrency primitives used.
- **Frontend (if present)**: state management approach, component patterns, data fetching strategy, routing, styling system, build tooling.
- **Testing**: test pyramid shape, fixture/builder patterns, mocking strategy, integration test harness (testcontainers, WebApplicationFactory, etc.), snapshot tests.
- **DevOps**: build pipeline stages, environments/promotion, secrets management, observability stack (logs/metrics/traces), deployment strategy.
- **Code conventions**: error-handling philosophy, nullability stance, DI lifetimes used, folder-by-feature vs folder-by-type, anything enforced by analyzers/lint rules.

For every pattern claimed, record **one concrete anchor**: `file_path:line` of where it's implemented or wired up. No anchor → don't claim it.

## Phase 3 — Write TECH-STUDY.md

Write for a junior developer: assume they can code but haven't seen most of these patterns in production. Define each term the first time it appears. Explain *why* the pattern exists (what problem it solves) before *how* this repo applies it.

Structure:

```markdown
# Tech Study Guide — <repo name>

> What this repo can teach you, independent of what the product does.
> Generated <date>. Domain/business logic is intentionally out of scope.

## 1. TL;DR Stack Card
One table: Language(s) & versions | Frameworks | Data stores | Messaging | Frontend | Testing | CI/CD | Infra. One line each.

## 2. The 10-Minute Mental Model
How a request/message/job flows through the system end to end, told as a story
("an HTTP request lands in X middleware, gets dispatched via Y, hits handler Z,
which talks to the DB through W"). One mermaid diagram if it genuinely helps.

## 3. Technologies — What & Why
One subsection per significant technology:
- **What it is** (2–3 sentences, plain English)
- **Why projects use it** (the problem it solves; what you'd have to hand-roll without it)
- **How THIS repo uses it** (the specific configuration/style choices, with file anchors)
- **Study pointers** (official docs link + the one concept to master first)

## 4. Design Patterns & Techniques — The Heart of the Guide
One subsection per detected pattern, ordered from most foundational to most advanced:
- **The problem** it solves (start here — patterns without problems are noise)
- **The mechanism** — how it works conceptually
- **In this repo** — a short real code excerpt (≤15 lines) with the file anchor,
  walked through line by line, business meaning stripped ("a request class…", "an entity…")
- **Recognize it elsewhere** — how to spot this pattern in any codebase
- **Trade-offs** — when you'd choose it, when it's overkill

## 5. Cross-Cutting Engineering
Error handling, logging/observability, configuration, auth, resilience, performance
techniques — same problem/mechanism/in-this-repo treatment, briefer.

## 6. Testing & Quality Techniques
How tests are structured and the techniques used (not what they assert).

## 7. Build, CI/CD & Infrastructure
Pipeline walkthrough as a learning artifact: what each stage does and the
general technique it represents.

## 8. Conventions Worth Copying
Codified house style that reflects broader industry practice — and anything
unusual, flagged as "this repo's quirk, not an industry norm".

## 9. Study Path
An ordered checklist: "read these 10–15 files in this order, and after each,
you should understand <technique>". This turns the repo into a curriculum.

## 10. Glossary
Every acronym and pattern name used above, one line each.
```

## Quality bar

- **Anchored**: every claim about the repo carries a `path:line` reference.
- **Honest**: if the repo does something non-standard or arguably badly, say so neutrally — juniors must not absorb anti-patterns as gospel. Mark with ⚠️.
- **Self-contained**: readable without the repo open, but richer with it.
- **Proportionate**: depth follows what the repo actually exercises. Don't pad with patterns that aren't there; do go deep on the 5–8 patterns that define the codebase.
- **Unbounded depth**: there is no size limit — write as much as the repo's techniques warrant. Never truncate or summarize a section to save space (`--depth quick` ≈ sections 1–4 + 9 only).

## Wrap-up

After writing the file, give the user a short summary: the stack in one line, the 5 most instructive patterns found, and any ⚠️ anti-patterns flagged. Suggest section 9 (Study Path) as the starting point for the junior developer.
