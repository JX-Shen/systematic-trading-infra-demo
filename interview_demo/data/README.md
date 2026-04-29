# Brent C1 5-Minute March Data

The demo loader first looks for a local CSV at:

```text
interview_demo/data/brent_c1_5m_march.csv
```

CSV files are ignored by this repo, so the demo also includes a deterministic
Python fixture. That fixture is intentionally hand-shaped to trigger signals,
netting, broker fills, and reconciliation in a short run.

Expected CSV columns:

```text
timestamp,symbol,open,high,low,close,volume
2026-03-02 09:00:00,BRN C1,82.10,82.18,82.02,82.10,1200
```

Accepted timestamp column names: `timestamp`, `datetime`, or `time`.

If the CSV exists, `python3 demo.py full` uses it. If it does not exist, the demo uses the deterministic March fixture.
