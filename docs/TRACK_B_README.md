**Caveat.** v0 runs scripted, maximally compliant agents on one Windows account. Mediation between processes is by convention, and signatures are HMAC stand-ins. It demonstrates the gate's semantics and the shape of the security/utility trade-off. It does NOT measure real-world attack success, physical mediation, or non-repudiation.

# Duelist Ledger v0 (Track B build, contract v0.1)

This build conforms to **contract v0.1**: `BUILD_SPEC.md` and `TRACK_SEPARATION_PROTOCOL.md` at tag `contract-v0.1` (commit `aa4b65c226d7d810492c503c1d307ade787cdc0d`). It was built blind: Track B never saw Track A's scenarios or expectations.

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
- Every decision goes into a hash-chained diary. A separate witness keeps signed copies of its fingerprints, and replay re-computes every decision from the logged inputs. The diary is checked at every anchor, at every session start (a failure refuses that session), and once more at the end.
- A simulated world keeps its own receipts. The gate reconciles against them, so bypasses and missing receipts are caught.

## Other ways to run

| command | what it does |
|---|---|
| `py -3.14 run.py --scenarios <dir>` | run the scenarios in another folder |
| `py -3.14 run.py --scenarios <dir> --reveal <expectations.json> --salt <salt.txt>` | verify the seal first (stops with exit code 3 on a mismatch), then compare every sealed expectation |
| `py -3.14 run.py ... --seal sealed/v0.1/expectations.seal.json` | choose the seal file (this path is the default) |
| `py -3.14 run.py --subprocess` | also play one demo session with the agent in a separate process over a stdio pipe |
| `py -3.14 -m unittest discover -s tests` | unit tests only |
| `--skip-tests`, `--keep`, `--out <dir>` | skip tests, keep per-run temp folders, change the output folder |

With no `--scenarios`, `run.py` uses `scenarios/v0.1/` if it has scenario files, else `scenarios/`, else the three smoke fixtures in `tests/fixtures/`. A relative `--scenarios`, `--seal`, `--reveal` or `--salt` path is taken from the current folder, or from this build's folder when it is not found there.

A scenario that breaks a load rule of the spec (a fault `index` below 1, or a `mutate_escrow` without `to`) is skipped and listed as a load error in the console and the report. Its expectations then show up as mismatches.

Exit code: 0 = fine. 1 = unit tests failed, or an invariant broke in V2/A1/A4/A5/A7/R2. 2 = bad arguments. 3 = the seal did not verify. Expectation mismatches are findings, not failures. They are listed in the report as `UNCLASSIFIED`.

## Layout

- `config/`: house policy and the tool (sink) table.
- `duelist_ledger/`: the package. `decide.py` + `state.py` are the trusted core. Every module opens with a plain-language description.
- `scenarios/v0.1/`: Track A's scenarios go here at the reveal (absent in this build).
- `sealed/v0.1/expectations.seal.json`: Track A's seal (hash only), placed by the bridge.
- `tests/`: Track B's own unit tests and smoke fixtures. They never read `scenarios/`.
- `docs/IMPLEMENTATION_NOTES.md`: every spec ambiguity and the reading chosen, marked against contract v0.1.
- `out/`: generated summaries. Per-run working files go to short folders under the system temp directory and are deleted afterwards (keep them with `--keep`).

## Out of scope for v0.x

LLM agents, and the LLM monitor/duelist; cross-org operation; attestation, TEEs, DPUs; real OS sandboxing; an external witness; Cedar/SMT; a human UI; the random-audit floor; natural-language content of any kind.
