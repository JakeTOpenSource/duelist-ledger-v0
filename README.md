# Duelist Ledger v0

A deterministic pre-execution gate for agent tool calls: the agent commits a declaration before reading any untrusted data, the declaration is checked against a blind house envelope, and a small pure gate (`decide()`) enforces it per action. Every transition is hash-chained into a diary the agent cannot read or write, with heads cosigned by a separate witness.

**Caveat.** v0 runs scripted, maximally compliant agents on one Windows account. Mediation between processes is by convention, and signatures are HMAC stand-ins. It demonstrates the gate's semantics and the shape of the security/utility trade-off. It does NOT measure real-world attack success, physical mediation, or non-repudiation.

Any success-rate number in `out/report.md` is measured against the project's own scripted attacks, not real adversaries. Do not quote it without this caveat.

## Status

- **Contract:** `09d26a6` (spec + scenario plan + protocol, after pre-seal amendments A1).
- **Track A sealed:** `6c841b0`. 40 scenarios with hand-derived expectations; seal `sha256:002c24e5…5530455`.
- **Track B implementation:** `b2e592a`, delivered blind and built from the contract alone. It was committed before the reveal.
- **Reveal (run 1, blind):** `122b9c9`, published unedited in `results/run1/`.
  - Seal verified.
  - 1,410 runs, 3,255/3,255 decisions replayed, 0 invariant violations.
  - **10,165 / 10,335 expected fields matched (98.4%).**
- **Classification:** 0 gate bugs, 1 expectation error, 2 spec ambiguities. See `docs/CONTRADICTIONS.md`.
- **Run 2:** the same code against corrected expectations v2, with lineage. 10,185 / 10,335; the rest await contract v0.1.
- **Contract v0.1** (amendment A2, post-reveal): resolves every v0 contradiction and latent divergence, and pins the clauses both tracks flagged. It adds model-family independence and the custody lessons to the protocol. Tag `contract-v0.1` (`aa4b65c`).
- **Track A v0.1 sealed:** `b2547db`. 44 scenarios with hand-derived expectations, on Fable 5.1; seal `sha256:0275440e…882bec`.
- **Track B v0.1 implementation:** `64e33e5`, delivered blind on Opus 5.5 and built from the contract at `contract-v0.1` alone. Committed before the reveal. Track B declared one known nonconformance before publication and it is published unfixed, so the reveal can test that prediction (see `docs/PROTOCOL_LOG.md`).
- **Reveal v0.1 (run 1, blind):** published unedited in `results/v0.1/run1/`.
  - Seal verified.
  - 1,550 runs, 3,445/3,445 decisions replayed, 0 invariant violations.
  - **10,920 / 10,955 expected fields matched (99.7%).** All 35 mismatches are one field of one scenario (X2 `adversary_success`, every mode and variant).
- **Classification v0.1:** 1 spec ambiguity (C4: the `bypass_write` effect schema, which explains all 35 mismatches), 0 expectation errors, 0 scenario bugs, and 1 pre-registered gate bug (G1) that the suite never exercised. Six clauses matched only because both tracks assumed the same unpinned reading. See `docs/CONTRADICTIONS.md`. Author decisions for v0.2 are listed there.
- **Contract v0.2** (amendment A3, post-reveal): resolves every v0.1 finding, pins Track B's readings, adds five plan scenarios and an entry-path coverage rule, and strengthens the protocol (known-nonconformance pre-registration, prompts are not contract, cross-family Track B). Audited pre-seal. Tag `contract-v0.2` (`4cb7354`). No run was sealed under v0.2.
- **Contract v0.3** (amendment A4, design): the keyed agent link, receiver-verified Ed25519 effect tokens, typed slots, containment instead of session death for tainted trips, hard deny of tainted destinations with a declaration-time allowlist (A7 becomes the attended ablation), PAUSE (deferred), the attacker-triggered-restriction residual, and house-local labels with a cross-house interface. Eight new plan scenarios. Tag `contract-v0.3` (`431a14a`). The next blind two-track run is on v0.3.
- **Track A v0.3 sealed:** 57 scenarios with hand-derived expectations, on Fable 5.1; seal `sha256:8bc27754…77b37e2`, published before Track B starts.
- **Track B v0.3 implementation:** `f27c5bd`, built blind from the contract at `contract-v0.3` on Fable 5.1 (the same model as Track A, so same-model evidence; no other-family assistant was available). Committed before the reveal, with four nonconformances pre-registered in `docs/PROTOCOL_LOG.md`. Signatures are HMAC stand-ins in this build.
- **Reveal v0.3 (run 1, blind, same-model):** published unedited in `results/v0.3/run1/`.
  - Seal verified.
  - 2,005 runs, 4,410/4,410 decisions replayed, 0 invariant violations.
  - **18,150 / 18,155 expected fields matched (99.97%).** 5 mismatches.
- **Classification v0.3:** 1 expectation error (C5: the class of an H1 raised in a tainted context, which the spec leaves to its catch-all), 0 spec ambiguities, 0 scenario bugs, and 2 pre-registered gate bugs the suite never exercised (G2, G3). Four shared-assumption matches. All 22 hypotheses hold. Containment raised utility under attack from 36% to 57%, and the hard-block share from 56% to 82%. One model throughout, so this run measures consistency, not independence. See `docs/CONTRADICTIONS.md`.

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
- `docs/prompts/` — the prompts each track received, verbatim, per contract version.

## Method

Two blind tracks, after pilot-001:

1. **Track A** writes the scenarios and derives the expected outcomes by hand from the spec, then seals them. Only the seal (a hash) is committed.
2. **Track B** builds the gate from the spec alone, never seeing the scenarios.
3. **Reveal**: `--reveal` compares. Mismatches are findings. Spec-ambiguity is a classified finding, not a failure, and nobody edits a mismatch away.

See `docs/TRACK_SEPARATION_PROTOCOL.md` before starting either track.

## Layout (built by Track B per spec sec. 1)

`run.py`, `duelist_ledger/`, `config/`, `scenarios/`, `tests/`, `out/`, `sealed/`
