**Caveat.** v0 runs scripted, maximally compliant agents on one Windows account. Mediation between processes is by convention, and signatures are Ed25519 only when the optional package of sec. 0 is present, else HMAC stand-ins; the report states which ran. It demonstrates the gate's semantics and the shape of the security/utility trade-off. It does NOT measure real-world attack success, physical mediation, or non-repudiation. Signatures in this build's environment: HMAC-SHA256 stand-ins (neither `cryptography` nor `pynacl` was installed); each run's report states which ran.

# Duelist Ledger v0 (Track B build, contract v0.3)

This build conforms to **contract v0.3**: `BUILD_SPEC.md` and `TRACK_SEPARATION_PROTOCOL.md` at tag `contract-v0.3` (commit `431a14a360371479e77658cbf9d6adcd7315d104`). It was built blind: Track B never saw Track A's scenarios or expectations. It updates the published v0.1 build to amendments A3 (v0.2) and A4 (v0.3).

## Quickstart

```
py -3.14 run.py
```

Or double-click `run.bat`. It runs the unit tests, then every scenario, and writes `out/report.md` and `out/results.json`.
It uses Python 3.14 and the standard library. If `cryptography` or `pynacl` is installed, effect tokens are signed with Ed25519; otherwise with an HMAC-SHA256 stand-in, and the caveat line and report say so. No network, no keys, no LLM calls.

## What it does, in plain words

An AI agent is about to act for you. Before it reads anything untrusted, it has to write down its plan (the declaration). The house keeps its own private limits (the envelope), which the agent never sees. A small deterministic gate then checks every action against both:

- Every message from the agent must arrive over the one link bound when the session opened and carry a mac under that session's key; anything else is rejected and nothing happens.
- Actions outside the plan or the limits are held for a scripted human, denied, or (for house files and secrets) tripped. A tainted value in a guarded slot (an address or payee the agent got from untrusted data) is denied outright, with no human able to approve it, unless the plan marked that step as attended (then the human may re-type the value) or declared the slot as "reply to the sender".
- When a trip is caused by something the agent read (a canary in injected content, say), the gate contains it: that one item is stopped, everything that came from the same source is quarantined, and the session goes on. Three containments close the session.
- Risky actions (email, payments, persistent memory, schedules) wait in an outbox and are re-checked before release. Every executed effect carries a signed token that the simulated world verifies before applying anything; a bad token is refused with a receipt, and the gate treats an altered argument as a session trip and any other refusal as a fault on that link.
- Every decision goes into a hash-chained diary. A separate witness keeps signed copies of its fingerprints, and replay re-computes every decision from the logged inputs. The diary is checked at every anchor, at every session start (a failure refuses that session), and once more at the end.
- The world keeps its own receipts. The gate reconciles against them, so bypasses and missing receipts are caught.

## Other ways to run

| command | what it does |
|---|---|
| `py -3.14 run.py --scenarios <dir>` | run the scenarios in another folder |
| `py -3.14 run.py --scenarios <dir> --reveal <expectations.json> --salt <salt.txt>` | verify the seal first (stops with exit code 3 on a mismatch), then compare every sealed expectation |
| `py -3.14 run.py ... --seal sealed/v0.3/expectations.seal.json` | choose the seal file (this path is the default) |
| `py -3.14 run.py --subprocess` | also play one demo session with the agent in a separate process over a stdio pipe (the session key goes down the pipe once) |
| `py -3.14 -m unittest discover -s tests` | unit tests only |
| `--skip-tests`, `--keep`, `--out <dir>` | skip tests, keep per-run temp folders, change the output folder |

With no `--scenarios`, `run.py` uses `scenarios/v0.3/` if it has scenario files, else `scenarios/`, else the smoke fixtures in `tests/fixtures/`. A relative `--scenarios`, `--seal`, `--reveal` or `--salt` path is taken from the current folder, or from this build's folder when it is not found there.

A scenario that breaks a load rule of the spec (a fault `index` below 1, a `mutate_escrow` without `to`, a `forge_token` with an unknown `field`, a `forge_message` without an integer `after_seq`) is skipped and listed as a load error in the console and the report. Its expectations then show up as mismatches.

Exit code: 0 = fine. 1 = unit tests failed, or an invariant broke in V2/A1/A4/A5/A7/R2. 2 = bad arguments. 3 = the seal did not verify. Expectation mismatches are findings, not failures. They are listed in the report as `UNCLASSIFIED`.

## Layout

- `config/`: house policy (with `contain_limit`) and the tool (sink) table with its slot types.
- `duelist_ledger/`: the package. `decide.py` + `state.py` are the trusted core (under 1,500 lines together). Every module opens with a plain-language description.
- `scenarios/v0.3/`: Track A's scenarios go here at the reveal (absent in this build).
- `sealed/v0.3/expectations.seal.json`: Track A's seal (hash only), placed by the bridge.
- `tests/`: Track B's own unit tests and smoke fixtures. They never read `scenarios/`.
- `docs/IMPLEMENTATION_NOTES.md`: every spec ambiguity and the reading chosen, marked against contract v0.3.
- `out/`: generated summaries. Per-run working files (the diary, witness heads, blobs, the run manifest with the gateway's verify key, and the world's receipts) go to short folders under the system temp directory and are deleted afterwards (keep them with `--keep`).

## Not in this build

PAUSE (spec sec. 5.7) is deferred by the contract and not implemented. The cross-house interface of sec. 19 (handshake, a second house's receiver, the two-house tests) is not built; only the pieces the single house needs are (token audience, the published verify key, the foreign-label entry rule). Both are declared as known nonconformances in Track B's report.

## Out of scope for v0.x

LLM agents, and the LLM monitor/duelist; cross-house operation beyond the sec. 19 interface; attestation, TEEs, DPUs; real OS sandboxing (process isolation is by convention); an external witness; Cedar/SMT; a human UI; the random-audit floor; natural-language content of any kind.
