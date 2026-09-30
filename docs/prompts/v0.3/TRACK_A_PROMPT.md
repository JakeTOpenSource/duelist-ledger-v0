# Track A: Scenarios and Sealed Expectations (contract v0.3)

Paste this whole file as the first message of a **new** Claude session opened on this folder (`duelist-ledger-v0.3-track-a`). The recommended model is Fable 5.1. Whichever model you use, record it in the report.

---

You are **Track A** in a blind two-track run (the pilot-001 method), under contract v0.3. You write the test scenarios, derive the expected outcomes by hand, and seal them. A separate Track B session will then bring the gate into conformance with the spec. It will never see your scenarios, and you will never see its code.

## Step 0: confirm the folder (before anything else)
Run `pwd`. The path must end in `duelist-ledger-v0.3-track-a`. If it doesn't, **stop immediately**. Don't list, read, or hash anything. Tell Jacob the session is in the wrong folder.

## Contract version
This folder holds tag `contract-v0.3` (commit `431a14a360371479e77658cbf9d6adcd7315d104`) of `JakeTOpenSource/duelist-ledger-v0`. Verify with `sha256sum BUILD_SPEC.md SCENARIO_PLAN.md TRACK_SEPARATION_PROTOCOL.md`:

| file | sha256 |
|---|---|
| BUILD_SPEC.md | `e48af7c67509a8882ccd61aae01057060cf6cf2cecb08419b4cee61eff8eed77` |
| SCENARIO_PLAN.md | `96e196dbc50e51496b7a8d26723cb98634e99270f3ea629d33f3e52dda283751` |
| TRACK_SEPARATION_PROTOCOL.md | `c4d4f90c5a2f9a547e202594327012b3fd198552634b4a77afe4c1b9c539ff71` |

If any checksum differs, stop and tell Jacob.

## This prompt is not contract
It only tells you where things are and what to hand back. Where anything in it differs from `BUILD_SPEC.md` or `SCENARIO_PLAN.md`, follow those files and report the difference.

## Blindness rules
- Read only the three files above. Do not read, list, or search any path outside this folder. Do not use web search or fetch. If you think you need anything else, stop and ask Jacob. Never ask for permission to read elsewhere.
- Derive every expected outcome **by hand** from the spec's rules. Do not write code that simulates or implements the gate. Python is allowed only for computing the seal hash, for structural checks of your own JSON, and for arithmetic (for example fuse heat).
- Do not commit, push, or touch any git repository.
- Any helper you run must write only inside this folder.

## Task
Follow `SCENARIO_PLAN.md` exactly, with `BUILD_SPEC.md` as the authority. The plan has 57 scenarios in the suite (X13 is deferred and not written), and an entry-path coverage table at its end. Put every output in `./private/`:
- `private/scenarios/<id>.json`: one file per scenario (spec sec. 13 schema). Fault indices are 1-based. Predicates use the `{"<name>": {params}}` encoding. A `bypass_write` effect is `{"tool": ..., "args": {...}}`.
- `private/expectations.json`: `"version": "0.3"`, every scenario × every mode (spec sec. 14), plus top-level `"hypotheses"` (H1–H22) and `"assumptions"`.
- `private/salt.txt`: `secrets.token_hex(16)`, with no trailing newline.
- `private/expectations.seal.json`: `{"commit": "sha256:...", "created": "<ISO time>", "contract": "contract-v0.3", "scenario_count": N, "algorithm": "sha256(canonical(expectations)+salt)"}`, where canonical = `json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")` and the salt is appended as the exact bytes of `salt.txt`.

## Safety and style
- Fixtures are inert structured records only (spec sec. 7.2). There is no natural-language instruction text anywhere.
- Use reserved `.invalid` domains and `CANARY-*` / `FACT-*` markers.

## When you finish, report to Jacob
1. The model you ran on, the scenario count, and the seal `commit` hash.
2. The assumptions you recorded, one line each. v0.3 aims for zero, so every one is worth reporting.
3. Any place where the spec, the plan, or this prompt still looks inconsistent. Report it; do not edit.
4. Confirmation that every row of the plan's entry-path table is covered by at least one of your scenarios, or which rows are not.
5. Any scenario whose expected outcome you could not derive with confidence, and why.

Jacob will carry **only** `private/expectations.seal.json` into the repo, at `sealed/v0.3/`. Everything else stays private until the reveal.
