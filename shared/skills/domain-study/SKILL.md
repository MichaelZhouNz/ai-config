---
name: domain-study
description: Explore an entire repo and generate DOMAIN-STUDY.md — a study guide explaining purely the business domain encoded in the codebase (what the business does, its concepts, rules, workflows, and calculations), deliberately excluding all technology, frameworks, and design-pattern knowledge. Use when the user wants to "understand the domain", "learn the business logic", "what does this system actually do", or onboard someone on the business rather than the tech stack.
argument-hint: "[path to repo root, defaults to cwd] [--depth quick|deep]"
---

# Domain Study Guide Generator

Produce `DOMAIN-STUDY.md` at the repo root: a self-contained study document that teaches a new team member **what business this system runs and the rules it runs on** — readable by a developer, a product owner, or a business analyst alike. The companion to `/tech-study`, with the filter inverted.

## Core principle: domain, not technique

The guide captures knowledge that would survive a full rewrite in a different language. Apply this filter to everything you write:

- ✅ "An order can only be modified until its cutoff time, which is 3 days before the delivery date; after cutoff it is locked and changes require a credit instead."
- ❌ "OrderService uses MediatR to dispatch a LockOrderCommand…" (technique — exclude)
- ✅ "A customer subscription has four states: Active, Paused, Cancelled, Expired — and only Active subscriptions generate weekly orders."
- ❌ "The state machine is implemented with the Stateless library…" (exclude)

Code is your **evidence**, not your subject. Translate every class, enum, validation, and calculation into plain business English. A non-programmer should be able to read the entire document. Never mention frameworks, libraries, patterns, or architecture — if a sentence contains a technology name, rewrite it.

## Phase 1 — Discover the domain surface

Domain knowledge hides in specific places. Sweep:

1. **Domain/core model folders**: entities, value objects, enums, aggregates — every type name is a business concept; every enum is a business classification.
2. **Validation rules**: validators, guard clauses, constraint attributes, DB constraints — each one is a business rule someone once decided ("quantity must be 1–10" is policy, not code).
3. **Calculations & algorithms with business meaning**: pricing, discounts, scoring, scheduling, allocation, rounding rules, tax/currency handling.
4. **State & lifecycle**: status enums, transition guards, workflow definitions — reconstruct the lifecycle of each major entity.
5. **Time & scheduling logic**: cutoffs, windows, recurrence, deadlines, grace periods — time rules are dense, high-value domain knowledge.
6. **Events & messages**: event names (`OrderPlaced`, `PaymentFailed`) narrate the business processes; consumers reveal what the business does in reaction.
7. **External integrations** — capture only the *business* relationship: "payments are charged through a payment provider; a failed charge triggers a retry the next day, then suspension" (never name the SDK).
8. **Configuration, feature flags & seed/reference data**: business parameters (thresholds, rates, region lists), market/tenant variations, lookup tables.
9. **Tests as specification**: test names and scenarios often state business rules more plainly than the production code ("GivenOrderPastCutoff_WhenCustomerEdits_ThenRejected").
10. **Docs, tickets, and comments**: README sections, ADRs, code comments explaining *why* a rule exists — gold when present.

For large repos (roughly >300 source files), fan out **parallel Explore agents** in a single message, one per area above, each returning plain-English findings: the concept/rule discovered, its exact behavior (numbers, thresholds, ordering), and 2–3 supporting file paths. For small repos, read directly.

## Phase 2 — Reconstruct the business

Synthesize the raw findings into a coherent picture:

- **Ubiquitous language**: collect every domain term the code uses and define it. Flag synonyms/aliases where the code uses two names for one concept, and collisions where one word means two things in different modules.
- **Actors**: who interacts with the system (customers, staff roles, partner systems, schedulers) and what each can do.
- **Entity lifecycles**: for each core entity, the full state diagram — states, allowed transitions, what triggers each, and what each transition causes downstream.
- **End-to-end processes**: the major business journeys (e.g., signup → first order → recurring cycle → payment → fulfillment → delivery → support), stitched from events, handlers, and jobs.
- **Rules with their reasons**: every rule stated precisely (exact numbers, boundaries, tie-breaking, edge cases). Where the code or comments reveal the *why*, include it; where it doesn't, mark it ❓ as a question for a domain expert — do not invent rationale.
- **Implicit rules**: behavior that exists only as code (a hardcoded constant, a silent skip, an ordering assumption) and isn't documented anywhere — these are the highest-risk knowledge, flag them 🔍.

## Phase 3 — Write DOMAIN-STUDY.md

Write for someone joining the team who has never seen this business. Plain English throughout; no code excerpts in the body (file anchors only, as evidence references). Define every term on first use.

Structure:

```markdown
# Domain Study Guide — <repo name>

> What this system does as a business, independent of how it is built.
> Generated <date>. Technology and implementation details are intentionally out of scope.

## 1. The Business in One Page
What the company/system does, who its users are, what value changes hands,
and what this particular codebase's slice of that business is.

## 2. Ubiquitous Language (Glossary)
Every domain term, alphabetized, one short definition each, with the file anchor
where the concept lives. Flag synonyms and ambiguous terms ⚠️.

## 3. Actors & Permissions
Who touches the system and what each actor may do, as the code enforces it.

## 4. Core Concepts & Their Relationships
One subsection per major entity/concept:
- **What it represents** in the real world
- **Key attributes that matter to the business** (not field listings — the ones rules hang off)
- **How it relates** to other concepts (one customer has many subscriptions…)
- **Its lifecycle** — states and transitions, as a mermaid stateDiagram where useful

## 5. Business Processes (End-to-End Journeys)
One subsection per major process, told as a narrative with a numbered flow:
trigger → steps → decisions → outcomes → what happens on failure.
Include the unhappy paths — refunds, cancellations, retries, escalations.

## 6. Business Rules Catalog
The heart of the guide. Grouped by area, each rule stated precisely:
- **Rule**: exact behavior, with real numbers and boundaries
- **Why** (if discoverable) or ❓ ask-a-domain-expert
- **Where enforced**: file anchor(s)
- **Edge cases**: boundaries, exceptions, overrides
Mark code-only undocumented rules 🔍.

## 7. Money, Time & Numbers
Pricing/fee/discount formulas in plain math, rounding and currency rules,
cutoffs and schedules, capacity/limit rules — anywhere precision matters.

## 8. Variations
How behavior differs by market, region, tenant, customer segment, or feature flag —
the business meaning of each variation.

## 9. External Business Relationships
Each third party the business depends on, described purely as a business
arrangement: what is exchanged, when, and what happens when it fails.

## 10. Open Questions for a Domain Expert
Everything marked ❓ and 🔍, collected: rules whose rationale is unknown,
suspected dead rules, ambiguous terms, contradictions found between modules.

## 11. Study Path
An ordered checklist: "trace these journeys / read these areas in this order,
and after each you should understand <business capability>."
```

## Quality bar

- **Anchored**: every rule and concept carries a `path:line` reference as evidence — but the anchor is a citation, not part of the prose.
- **Tech-free prose**: zero framework, library, pattern, or architecture vocabulary in the body. Re-read and scrub before finishing.
- **Precise**: rules state exact values, boundaries, and orderings found in code — "3 days before delivery", not "shortly before delivery".
- **Honest**: never invent business rationale. Unknown whys become ❓ entries; undocumented code-only rules become 🔍 entries; contradictions between modules are reported, not smoothed over.
- **Readable by non-developers**: a product owner should understand every section.
- **Unbounded depth**: there is no size limit — write as much as the domain warrants. Never truncate a section to save space (`--depth quick` ≈ sections 1, 2, 5, 6 + 11 only).

## Wrap-up

After writing the file, give the user a short summary: the business in one sentence, the 3–5 most important processes, the count of rules catalogued, and how many ❓/🔍 items need a domain expert. Suggest section 11 (Study Path) as the starting point.
