# Duelist Ledger v0

A deterministic pre-execution gate for agent tool calls: the agent commits a declaration before reading any untrusted data, the declaration is checked against a blind house envelope, and a small pure gate (`decide()`) enforces it per action. Every transition is hash-chained into a diary the agent cannot read or write, with heads cosigned by a separate witness.

**Caveat.** v0 runs scripted, maximally compliant agents on one Windows account. Mediation between processes is by convention, and signatures are HMAC stand-ins. It demonstrates the gate's semantics and the shape of the security/utility trade-off. It does NOT measure real-world attack success, physical mediation, or non-repudiation.

Any success-rate number in `out/report.md` is measured against the project's own scripted attacks, not real adversaries. Do not quote it without this caveat.

## Status

- **Contract:** `09d26a6` (spec + scenario plan + protocol, after pre-seal amendments A1).
- **Track A sealed:** `6c841b0`. 40 scenarios with hand-derived expectations; seal `sha256:002c24e5…5530455`.
- **Track B implementation:** delivered blind, built from the contract alone. Committed before the reveal.
- **Reveal:** pending.

## Quickstart

```
py -3.14 run.py
```

Or double-click `run.bat`. It runs the unit tests, then the scenarios, and writes `out/report.md`. It needs Python 3.14 and the standard library only. See `docs/TRACK_B_README.md` for every option, including `--reveal`.

## Docs

- `docs/BUILD_SPEC.md` — the contract both blind tracks build against. Authoritative.
- `docs/SCENARIO_PLAN.md` — Track A instructions: scenarios, hand-derived sealed expectations, pre-registered hypotheses.
- `docs/TRACK_SEPARATION_PROTOCOL.md` — chain of custody keeping the two tracks blind.
- `docs/SPEC_AUDIT.md` — pre-seal contradiction pass over the contract.
- `docs/AMENDMENTS.md` — every change to the contract, with the finding it resolves.
- `docs/PROTOCOL_LOG.md` — custody events in the two-track run.
- `docs/TRACK_B_README.md` — Track B's own README for the build (verbatim).
- `docs/IMPLEMENTATION_NOTES.md` — every spec ambiguity Track B resolved, and the reading it chose.

## Method

Two blind tracks, after pilot-001:

1. **Track A** writes the scenarios and derives the expected outcomes by hand from the spec, then seals them. Only the seal (a hash) is committed.
2. **Track B** builds the gate from the spec alone, never seeing the scenarios.
3. **Reveal**: `--reveal` compares. Mismatches are findings. Spec-ambiguity is a classified finding, not a failure, and nobody edits a mismatch away.

See `docs/TRACK_SEPARATION_PROTOCOL.md` before starting either track.

## Layout (built by Track B per spec sec. 1)

`run.py`, `duelist_ledger/`, `config/`, `scenarios/`, `tests/`, `out/`, `sealed/`
