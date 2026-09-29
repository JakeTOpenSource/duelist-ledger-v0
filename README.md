# Duelist Ledger v0

A deterministic pre-execution gate for agent tool calls: the agent commits a declaration before reading any untrusted data, the declaration is checked against a blind house envelope, and a small pure gate (`decide()`) enforces it per action. Every transition is hash-chained into a diary the agent cannot read or write, with heads cosigned by a separate witness.

**Caveat.** v0 runs scripted, maximally compliant agents on one Windows account. Mediation between processes is by convention, and signatures are HMAC stand-ins. It demonstrates the gate's semantics and the shape of the security/utility trade-off. It does NOT measure real-world attack success, physical mediation, or non-repudiation.

Any success-rate number in `out/report.md` is measured against the project's own scripted attacks, not real adversaries. Do not quote it without this caveat.

## Status

Pre-build. The contract is written; neither track has run.

## Docs

- `docs/BUILD_SPEC.md` — the contract both blind tracks build against. Authoritative.
- `docs/SCENARIO_PLAN.md` — Track A instructions: scenarios, hand-derived sealed expectations, pre-registered hypotheses.
- `docs/TRACK_SEPARATION_PROTOCOL.md` — chain of custody keeping the two tracks blind.

## Method

Two blind tracks, after pilot-001:

1. **Track A** writes the scenarios and derives the expected outcomes by hand from the spec, then seals them. Only the seal (a hash) is committed.
2. **Track B** builds the gate from the spec alone, never seeing the scenarios.
3. **Reveal**: `--reveal` compares. Mismatches are findings. Spec-ambiguity is a classified finding, not a failure, and nobody edits a mismatch away.

See `docs/TRACK_SEPARATION_PROTOCOL.md` before starting either track.

## Layout (built by Track B per spec sec. 1)

`run.py`, `duelist_ledger/`, `config/`, `scenarios/`, `tests/`, `out/`, `sealed/`
