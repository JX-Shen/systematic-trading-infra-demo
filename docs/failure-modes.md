# Failure Modes

The focused scenarios are small by design. Each isolates one boundary that a
trading infrastructure reviewer should be able to inspect without needing live
services.

## Risk Reject

Run:

```bash
python3 demo.py risk-reject
```

What it shows:

- `RiskGate` evaluates the order intent before provider routing.
- The scenario rejects an order that exceeds configured limits.
- The simulated provider adapter is not called.
- Reconciliation still passes because no provider-confirmed state changed.

What it does not show:

- Operator override flows
- Strategy-level risk policy
- Persistent risk configuration

## Provider Reject

Run:

```bash
python3 demo.py provider-reject
```

What it shows:

- Risk can accept an intent that the provider adapter later rejects.
- The order enters an explicit rejected state.
- Provider rejection does not mutate portfolio position as a confirmed fill.
- The event trace records risk decision, order submission, callback, and reconciliation.

What it does not show:

- Retry policy
- Provider-specific reject codes
- Live connectivity recovery

## Partial Fill

Run:

```bash
python3 demo.py partial-fill
```

What it shows:

- A provider callback can confirm less than the requested quantity.
- The order state becomes `partially_filled`.
- Residual quantity remains explicit on the managed order.
- Reconciliation reports the target-vs-provider difference.

What it does not show:

- Cancel/replace handling
- Residual re-routing
- Time-in-force policy

## Reconciliation Mismatch

Run:

```bash
python3 demo.py reconciliation-mismatch
```

What it shows:

- Internal target state can disagree with provider-confirmed state.
- `ReconciliationReport` includes target, provider state, diff, status, suspected source, and related event ids.
- A provider-state drift or stale callback category is reported when callback state differs from fill-derived state.

What it does not show:

- Automatic repair
- External statement comparison
- Multi-instrument reconciliation

## Trace Replay

Run:

```bash
python3 demo.py trace-replay
```

What it shows:

- The JSONL trace can be loaded after a run.
- Provider-confirmed position can be reconstructed from ordered callback events.
- Trace review does not require the dashboard.

What it does not show:

- Durable production event storage
- Cross-process replay
- Full portfolio reconstruction

## Unexpected Provider State

Run:

```bash
python3 demo.py unexpected-provider-state
```

What it shows:

- The provider adapter can report a callback state the order manager does not treat as a fill.
- The order moves to `unexpected_provider_state`.
- The callback is preserved in the trace with a related reconciliation result.
- Provider-confirmed state can differ from fill-derived state and trigger review.

What it does not show:

- Automatic repair
- Provider-specific state mapping
- Operator escalation workflow
