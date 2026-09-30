# Track Separation Protocol (v0.3)

The two-track method only works if the tracks are actually blind. This protocol is the chain of custody. Both tracks read it alongside BUILD_SPEC.md.

v0.3 = v0.2 plus two notes from amendment A4: a build that omits the deferred PAUSE (spec sec. 5.7) declares it as a known nonconformance, and the two-house run of spec sec. 19 is a separate scope with its own custody record. The custody rules are otherwise unchanged. v0.2 = v0.1 plus the custody lessons from the v0.1 run (`docs/PROTOCOL_LOG.md`): known nonconformances are pre-registered, prompts are not contract, helper agents stay inside the track folder, the bridge never edits gate code before a reveal, and Track B runs on another model family where one is available. See amendment A3 in `docs/AMENDMENTS.md`. (v0.1 added the v0 custody lessons and the independence note, amendment A2.)

## The rule

- **Track A** (scenarios + expectations) may read `docs/BUILD_SPEC.md`, `docs/SCENARIO_PLAN.md` and this protocol. Nothing else. Track A completes and seals before Track B starts. The only gate code that exists is the published builds of earlier contract versions, and Track A never opens them.
- **Track B** (gate implementation) may read `docs/BUILD_SPEC.md`, this protocol, and, when the bridge places it in its folder, the previously published build of the gate, which it brings to the current contract. It never reads `scenarios/`, `expectations.json`, the salt, the seal preimage, the scenario plan, or any results or contradiction record. The seal file (`sealed/<version>/expectations.seal.json`, hash only) is opaque, and it is fine to see.
- **The author (Jacob) is the only bridge between tracks.** The author carries no specifics across: no scenario contents to Track B, and no implementation details to Track A. Only operational signals cross ("Track A sealed", "Track B done").
- **A bridge helper session may do the mechanical bridge steps.** For example, the author's main Claude session may carry the opaque seal file, copy the finished Track B build, and run the reveal. Before the reveal it may *hash* Track A's private files to verify the seal, but it never displays or reads their contents.

## Sessions

- **Track A** runs in a fresh session that has never seen any gate implementation discussion.
- **Track B** runs in a fresh session that has never seen the scenarios or expectations. Its prompt carries the spec and this protocol only. It gets no repo checkout **and no web access**: the repo is public and contains the scenario plan.
- **Folder isolation.** Each track works in its own folder, which holds only the files that track may read. The first action of every track session is a working-directory check. If the path is wrong, the session stops *before* listing, reading or hashing anything.
- **Opening a session.** Open each track session by explicitly choosing its folder, never by accepting the app's default project. Before the first message, check the session header shows the track folder.
- **Settings.** Each track folder carries a project settings file that denies web tools and starts the session in ask-before-acting mode. Keep that mode on. Deny any request to read outside the folder.
- **Model-family independence.** Track B **must** run on a different model family from Track A whenever any coding assistant of another family is available to the author, where "available" means able to run under this protocol's controls: its own folder, no web access, ask-before-acting, and a checkable working directory. If none is, the protocol log records why, and the run is reported as single-family evidence. A Track B that patches a build written by another family reports the run as a cross-family patch of a same-family build; only a rebuild from the spec is full cross-family evidence. Two readers from the same family can share blind spots, so their agreement is weaker evidence than agreement across families. This is the same correlated-blind-spot argument the review applies to monitors. Record in the protocol log the model used by each track, by the bridge, and by any verification sessions, and state it in every report's limitations. *(In the v0 run every stage ran on Fable 5.1. In the v0.1 run Track B ran on Opus 5.5 and every other stage on Fable 5.1: different models, one family.)*
- **Helper agents.** A track session may run helper agents or workflows of its own (for example a review of its build), but everything they write must land inside the track folder. Output written anywhere else is discarded unread, and the session says so in its report. A helper read outside the folder is a custody event; it burns the track only if it could have exposed the other track's material.
- **Prompts are not contract.** The bridge's prompt to a track may summarize the contract for convenience, but it carries no authority. Where a prompt and the contract differ, the contract governs, and the track reports the difference. Every prompt is published verbatim under `docs/prompts/<version>/` with that track's commit. *(In the v0.1 run the Track B prompt's summary of sec. 5.1 differed from the spec text; Track B followed the spec and reported it.)*
- **The burn rule.** If a session is ever shown the other track's material (an accidental paste, context bleed, a granted permission), that track's output is burned: discard it, re-run it in a fresh session, and log the burn in the repo. A custody event that exposes nothing, such as a folder guard firing, is logged but is not a burn.

## The seal

- Track A writes its scenarios, `expectations.json` and `salt.txt` under `private/` inside its own track folder, outside the repo. It computes the seal per the spec's canonical JSON and hands over only the seal file. The bridge places it under `sealed/<version>/`; Track A never touches the repo.
- The seal commit is pushed before Track B starts. It is the timestamped prior-art artifact.
- The salt and the expectations stay out of the repo until the reveal.

## Order of publication

1. The contract commit, including any pre-seal amendments.
2. The seal commit, pushed **before Track B starts**.
3. The Track B implementation commit, pushed **before the reveal**, together with the protocol-log entry that lists every known nonconformance Track B declared (see below).
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
- The bridge never edits gate code before the reveal, not even to fix a nonconformance Track B declared: by then the bridge has seen Track A's material. Gate fixes come after the reveal, with lineage, as a new gate version.
- Bridge diagnostics after the reveal (a re-encoded scenario, a reproduction of a declared bug) are labeled as diagnostics in the contradiction record and are never published as runs. A run 2 exists only after an author decision, with lineage.

## Known nonconformances (pre-registration)

- Track B's final report lists every nonconformance it knows of and did not fix, whether found by its own tests, by a helper review, or by reasoning, each with the code path and the predicted effect on the sec. 14 fields.
- The bridge records each one in `docs/PROTOCOL_LOG.md` **before** the implementation is published, and publishes the build as delivered.
- At the reveal, a mismatch traceable to a declared nonconformance is classified gate-bug with the pre-registration cited. A declared nonconformance the suite never exercises is reported as **unexercised**, not as absent, and the plan gains a scenario for it.
- Track A's report lists the spec and plan gaps it found in the same way. Both lists are part of the run's record.
- Items the contract marks **deferred** (in v0.3, PAUSE) are declared the same way when a build omits them. They are expected, not faults, and are reported as unexercised.
