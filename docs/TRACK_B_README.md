**Caveat.** v0 runs scripted, maximally compliant agents on one Windows account. Mediation between processes is by convention, and signatures are HMAC stand-ins. It demonstrates the gate's semantics and the shape of the security/utility trade-off. It does NOT measure real-world attack success, physical mediation, or non-repudiation.

# Duelist Ledger v0 (Track B build)

## Quickstart

```
py -3.14 run.py
```

Or double-click `run.bat`. It runs the unit tests, then every scenario, and writes `out/report.md` and `out/results.json`.
It uses Python 3.14 and the standard library only: no installs, no network, no keys.

## What it does, in plain words

An AI agent is about to act for you. Before it reads anything untrusted, it has to write down its plan (the declaration). The house keeps its own private limits (the envelope), which the agent never sees. A small deterministic gate then checks every action against both:

- Actions outside the plan or the limits are held for a scripted human, denied, or (for house files and secrets) tripped.
- Risky actions (email, payments, persistent memory, schedules) wait in an outbox and are re-checked before release.
- Every decision goes into a hash-chained diary. A separate witness keeps signed copies of its fingerprints, and replay re-computes every decision from the logged inputs.
- A simulated world keeps its own receipts. The gate reconciles against them, so bypasses and missing receipts are caught.

## Other ways to run

| command | what it does |
|---|---|
| `py -3.14 run.py --scenarios <dir>` | run the scenarios in another folder |
| `py -3.14 run.py --scenarios <dir> --reveal <expectations.json> --salt <salt.txt>` | verify `sealed/expectations.seal.json` first (stops with exit code 3 on a mismatch), then compare every sealed expectation |
| `py -3.14 run.py --subprocess` | also play one demo session with the agent in a separate process over a stdio pipe |
| `py -3.14 -m unittest discover -s tests` | unit tests only |
| `--skip-tests`, `--keep`, `--out <dir>`, `--seal <path>` | skip tests, keep per-run temp folders, change the output folder, use another seal file |

With no `--scenarios`, `run.py` uses `scenarios/` if it has scenario files. Otherwise it uses the three smoke fixtures in `tests/fixtures/`.

Exit code: 0 = fine. 1 = unit tests failed, or an invariant broke in V2/A1/A4/A5/A7/R2. 3 = the seal did not verify. Expectation mismatches are findings, not failures. They are listed in the report as `UNCLASSIFIED`.

## Layout

- `config/`: house policy and the tool (sink) table.
- `duelist_ledger/`: the package. `decide.py` + `state.py` are the trusted core. Every module opens with a plain-language description.
- `scenarios/`: Track A's scenarios go here (empty in this build).
- `tests/`: Track B's own unit tests and smoke fixtures. They never read `scenarios/`.
- `docs/IMPLEMENTATION_NOTES.md`: every spec ambiguity and the reading chosen.
- `out/`: generated summaries. Per-run working files go to short folders under the system temp directory and are deleted afterwards (keep them with `--keep`).

## Out of scope for v0

LLM agents, and the LLM monitor/duelist; cross-org operation; attestation, TEEs, DPUs; real OS sandboxing; an external witness; Cedar/SMT; a human UI; the random-audit floor; natural-language content of any kind.
