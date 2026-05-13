# Reconciliation

Reconciliation is treated as a first-class workflow in this artifact because
monitoring alone is not enough.

Monitoring answers:

```text
Is the process alive, and what is it doing now?
```

Reconciliation answers:

```text
Does the recorded target state agree with provider-confirmed state?
```

## Target vs Provider State

The portfolio layer owns internal target state. The provider adapter owns
provider-confirmed callbacks. Those are intentionally separate.

`ReconciliationReport` compares:

- `target_position`: the internal aggregate target
- `provider_state_position`: the provider-confirmed position used for review
- `diff`: target minus provider state
- `status`: `match` or `mismatch`
- `suspected_source`: a public-safe category for investigation
- `related_event_ids`: trace ids that help review the path

## Why This Matters

An order submission is only intent. It may be rejected, partially filled, or
reported with unexpected provider state. If the portfolio layer assumes that
submission equals execution, the internal target can look correct while
provider-confirmed state says something else.

The artifact keeps those states apart so the mismatch is visible.

## Trace-Backed Review

Every focused failure scenario writes `artifacts/latest-run/events.jsonl`.
Because event ids are ordered, a reviewer can inspect:

1. The market or manual fixture event that started the path
2. The emitted signal
3. The portfolio intent
4. The risk decision
5. The order submission when routing occurred
6. The provider callback when one occurred
7. The reconciliation result

The `trace-replay` scenario demonstrates one narrow replay: reconstructing final
provider-confirmed position from callback events. It does not rebuild the whole
portfolio. That limit is intentional and matches the code.

## Implemented Suspected Sources

The current report categorizes mismatches as:

- `none`
- `portfolio_state_mutation_or_missing_fill`
- `provider_state_drift_or_stale_callback`

These are review categories, not automated diagnoses. The artifact reports what
to inspect next without pretending to repair the state.
