# Track Separation Protocol (v0)

The two-track method only works if the tracks are actually blind. This protocol is the chain of custody. It is read by both tracks alongside BUILD_SPEC.md.

## The rule

- **Track A** (scenarios + expectations) may read: `docs/BUILD_SPEC.md`, `docs/SCENARIO_PLAN.md`, this protocol. Nothing else. Track A completes and seals before Track B starts, so gate code does not exist yet. Keep it that way.
- **Track B** (gate implementation) may read: `docs/BUILD_SPEC.md`, this protocol. Never `scenarios/`, never `expectations.json`, never the salt, never the seal preimage. The seal file (`sealed/expectations.seal.json`, hash only) is opaque and fine to see.
- The author (Jacob) is the only bridge between tracks. He carries no specifics across: no scenario contents to Track B, no implementation details to Track A. Operational signals only ("Track A sealed", "Track B done").

## Sessions

- Track A runs in a fresh session that has never seen any gate implementation discussion.
- Track B runs in a fresh session that has never seen the scenarios or expectations. Its prompt carries the spec and this protocol only. It does not get the repo checked out.
- If a session is ever shown the other track's material (an accidental paste, context bleed), that track's output is burned: discard it, re-run in a fresh session, and log the burn in the repo.

## The seal

- Track A writes `expectations.json` and `salt.txt` outside the repo, computes the seal per the spec's canonical JSON, and commits ONLY the seal file to the repo.
- The seal commit is pushed before Track B starts. It is the timestamped prior-art artifact.
- The salt and the expectations stay out of the repo until reveal.

## The reveal

- After Track B's implementation passes its own unit tests (spec sec. 17), run with `--reveal`.
- Mismatches are classified per the spec. Spec-ambiguity is a finding, not a failure.
- Neither track edits the other to resolve a mismatch. Ever.
