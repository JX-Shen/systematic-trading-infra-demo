# Trading Infrastructure Proof Artifact Plan

This repository is being packaged as a public, anonymized trading infrastructure
proof artifact. It should demonstrate judgment about state ownership, execution
boundaries, risk decisions, provider-confirmed truth, reconciliation, operator
visibility, and trace review.

It should not read as a role-specific or time-boxed demo, and it should not be
linked from another public site as part of this cleanup pass.

## Objective

Upgrade the repository into:

```text
public, anonymized trading infrastructure proof artifact
```

The artifact should prove:

- strategy intent is separated from trading consequences
- portfolio target state, provider-confirmed state, and operator view are separate layers
- risk rejection and provider rejection are separate failure paths
- reconciliation is a first-class workflow, not an end-of-run checkbox
- system behavior can be inspected through structured events and replayable traces

The artifact should not prove:

- profitable strategy design
- proprietary execution details
- specific provider integrations
- specific middleware, database, vendor, or proprietary architecture
- a directly reusable production trading stack

## Public Disclosure Rules

Use public-safe, generic language:

- `service provider`
- `message middleware`
- `provider adapter`
- `local market fixture`
- `provider-confirmed state`
- `operator console`

Do not publish:

- vendor names
- specific production service names
- real symbol lists, asset coverage, capacity, performance-envelope, or scale claims
- real incident details
- credentials, environment names, account structures, or deployment topology
- reusable production integration code

## Phase 1: Public-Safe Repositioning

Goal: remove role-specific residue and make the repo safe to inspect publicly.

Completed or expected:

- Public labels use provider-neutral terminology.
- Runtime concepts use simulated provider and provider-confirmed state language.
- Public symbol/data-source language uses fixture terminology.
- README first screen states this is a proof artifact for system design, not alpha.

## Phase 2: Proof Density

Goal: add enough implemented behavior that the repo proves judgment, not just a
happy-path workflow.

Implemented components:

- `RiskGate`
  - max aggregate position
  - max order size
  - enabled symbol set
  - session enabled/disabled
  - explicit risk reject result
- `EventLog`
  - ordered structured events
  - JSONL output under `artifacts/latest-run/events.jsonl`
  - replay helper for provider-confirmed position
- `ReconciliationReport`
  - internal target
  - provider-confirmed position
  - diff
  - status
  - suspected source category
  - related event ids
- Provider lifecycle simulation
  - filled
  - rejected
  - partial fill
  - unexpected provider state path

Focused scenarios:

- `risk-reject`
- `provider-reject`
- `partial-fill`
- `reconciliation-mismatch`
- `trace-replay`
- `unexpected-provider-state`

## Phase 3: Public Artifact Packaging

Goal: make the repo feel like a polished proof object without inventing maturity,
production readiness, or hidden capabilities.

Docs:

- `README.md`
- `docs/architecture.md`
- `docs/failure-modes.md`
- `docs/reconciliation.md`
- `docs/public-disclosure.md`

Compatibility notes:

- Historical notes under `interview/` may remain as public-safe pointers so
  parent validation commands can scan stable paths.
- Generated artifacts remain ignored by git.

## Validation

Run:

```bash
python3 -m unittest discover -s tests
python3 demo.py full
python3 demo.py risk-reject
python3 demo.py provider-reject
python3 demo.py partial-fill
python3 demo.py reconciliation-mismatch
python3 demo.py trace-replay
python3 demo.py unexpected-provider-state
```

Disclosure scan:

```bash
rg -n "CQG|Redis|WebAPI|broker|Broker|Brent|BZ=F|SizeConsole|TradingConsole|market_load|signal_data|symbol_resolve" README.md PLAN.md docs interview interview_demo tests demo.py
```

Expected disclosure scan result: no matches except this literal validation
command if the command remains in this file.

## Release Gate

Do not push or link externally during this cleanup pass.

Before any future public release:

- tests pass
- focused scenarios run
- public docs are disclosure-safe
- runtime labels are provider-neutral
- generated artifacts are ignored
- README and docs describe only implemented behavior
- disclosure scan is clean except for the literal validation command above
