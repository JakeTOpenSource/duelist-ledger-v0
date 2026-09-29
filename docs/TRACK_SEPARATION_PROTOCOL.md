# Track Separation Protocol (v0.1)

The two-track method only works if the tracks are actually blind. This protocol is the chain of custody. Both tracks read it alongside BUILD_SPEC.md.

v0.1 = v0 plus the custody lessons from the v0 run (`docs/PROTOCOL_LOG.md`) and the review's independence note. See amendment A2 in `docs/AMENDMENTS.md`.

## The rule

- **Track A** (scenarios + expectations) may read `docs/BUILD_SPEC.md`, `docs/SCENARIO_PLAN.md` and this protocol. Nothing else. Track A completes and seals before Track B starts, so gate code does not exist yet. Keep it that way.
- **Track B** (gate implementation) may read `docs/BUILD_SPEC.md` and this protocol. It never reads `scenarios/`, `expectations.json`, the salt, or the seal preimage. The seal file (`sealed/<version>/expectations.seal.json`, hash only) is opaque, and it is fine to see.
- **The author (Jacob) is the only bridge between tracks.** The author carries no specifics across: no scenario contents to Track B, and no implementation details to Track A. Only operational signals cross ("Track A sealed", "Track B done").
- **A bridge helper session may do the mechanical bridge steps.** For example, the author's main Claude session may carry the opaque seal file, copy the finished Track B build, and run the reveal. Before the reveal it may *hash* Track A's private files to verify the seal, but it never displays or reads their contents.

## Sessions

- **Track A** runs in a fresh session that has never seen any gate implementation discussion.
- **Track B** runs in a fresh session that has never seen the scenarios or expectations. Its prompt carries the spec and this protocol only. It gets no repo checkout **and no web access**: the repo is public and contains the scenario plan.
- **Folder isolation.** Each track works in its own folder, which holds only the files that track may read. The first action of every track session is a working-directory check. If the path is wrong, the session stops *before* listing, reading or hashing anything.
- **Opening a session.** Open each track session by explicitly choosing its folder, never by accepting the app's default project. Before the first message, check the session header shows the track folder.
- **Settings.** Each track folder carries a project settings file that denies web tools and starts the session in ask-before-acting mode. Keep that mode on. Deny any request to read outside the folder.
- **Model-family independence.** Tracks A and B **should** run on different model families where one is available. Two readers from the same family can share blind spots, so their agreement is weaker evidence than agreement across families. This is the same correlated-blind-spot argument the review applies to monitors. Record in the protocol log the model used by each track, by the bridge, and by any verification sessions, and state it in every report's limitations. *(In the v0 run, every stage ran on one model, Fable 5.1: the spec, the review, both tracks, the bridge, and the verification.)*
- **The burn rule.** If a session is ever shown the other track's material (an accidental paste, context bleed, a granted permission), that track's output is burned: discard it, re-run it in a fresh session, and log the burn in the repo. A custody event that exposes nothing, such as a folder guard firing, is logged but is not a burn.

## The seal

- Track A writes `expectations.json` and `salt.txt` outside the repo, computes the seal per the spec's canonical JSON, and hands over only the seal file. The seal lives under `sealed/<version>/`.
- The seal commit is pushed before Track B starts. It is the timestamped prior-art artifact.
- The salt and the expectations stay out of the repo until the reveal.

## Order of publication

1. The contract commit, including any pre-seal amendments.
2. The seal commit, pushed **before Track B starts**.
3. The Track B implementation commit, pushed **before the reveal**.
4. The reveal commit: scenarios, expectations, salt, Track A's report, and the run-1 output **exactly as generated**.
5. The classification commit: `docs/CONTRADICTIONS.md`, plus any corrections.

GitHub's commit timestamps then prove the order independently of anyone's account of it.

## The reveal

- After Track B's implementation passes its own unit tests (spec sec. 17), run with `--reveal`.
- Run 1 is published unedited before any classification or fix.
- Mismatches are classified per the spec: gate-bug, expectation-error, spec-ambiguity or scenario-bug. Spec-ambiguity is a finding, not a failure.
- If the two tracks' recorded readings of a clause differ but the suite never exercises the difference, the agreement is reported as a **latent divergence**, not as a match.
- Neither track edits the other to resolve a mismatch. Ever.
- A post-reveal correction never edits a sealed file. It creates a new expectations version, with lineage, sealed separately. **The blind claim always cites run 1.**
