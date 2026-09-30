# Track A: Scenarios and Sealed Expectations (contract v0.1)

Paste this whole file as the first message of a **new** Claude session opened on this folder (`duelist-ledger-v0.1-track-a`). The recommended model is Fable 5.1. Whichever model you use, record it in the report.

---

You are **Track A** in a blind two-track run (the pilot-001 method), under contract v0.1. You write the test scenarios, derive the expected outcomes by hand, and seal them. A separate Track B session will then bring the gate into conformance with the spec. It will never see your scenarios, and you will never see its code.

## Step 0: confirm the folder (before anything else)
Run `pwd`. The path must end in `duelist-ledger-v0.1-track-a`. If it doesn't, **stop immediately**. Don't list, read, or hash anything. Tell Jacob the session is in the wrong folder.

## Contract version
This folder holds tag `contract-v0.1` (commit `aa4b65c226d7d810492c503c1d307ade787cdc0d`) of `JakeTOpenSource/duelist-ledger-v0`. Verify with `sha256sum *.md`:

| file | sha256 |
|---|---|
| BUILD_SPEC.md | `cb50dfa349e23c1ab98673316ea7b6d365a0c73d45b3b206376e9189fd69ac1e` |
| SCENARIO_PLAN.md | `2272b1f0447654839f732e018accf2e0806936502239faece7d4142a5aff2f00` |
| TRACK_SEPARATION_PROTOCOL.md | `fcc493943c0caa9dd6a43e66e274fa027b5f8d6a909d7d3646ab7c6b5afb4258` |

If any checksum differs, stop and tell Jacob.

## Blindness rules
- Read only the three files above. Do not read, list, or search any path outside this folder. Do not use web search or fetch. If you think you need anything else, stop and ask Jacob. Never ask for permission to read elsewhere.
- Derive every expected outcome **by hand** from the spec's rules. Do not write code that simulates or implements the gate. Python is allowed only for computing the seal hash and for arithmetic (e.g. fuse heat).
- Do not commit, push, or touch any git repository.

## Task
Follow `SCENARIO_PLAN.md` exactly, with `BUILD_SPEC.md` as the authority. Put every output in `./private/`:
- `private/scenarios/<id>.json`: one file per scenario (spec sec. 13 schema). Fault indices are 1-based. Predicates use the `{"<name>": {params}}` encoding.
- `private/expectations.json`: `"version": "0.1"`, every scenario × every mode (spec sec. 14), plus top-level `"hypotheses"` (H1–H15) and `"assumptions"`.
- `private/salt.txt`: `secrets.token_hex(16)`, with no trailing newline.
- `private/expectations.seal.json`: `{"commit": "sha256:...", "created": "<ISO time>", "scenario_count": N, "algorithm": "sha256(canonical(expectations)+salt)", "contract": "v0.1"}`, where canonical = `json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")` and the salt is appended as UTF-8 bytes.

## Safety and style
- Fixtures are inert structured records only (spec sec. 7.2). There is no natural-language instruction text anywhere.
- Use reserved `.invalid` domains and `CANARY-*` / `FACT-*` markers.

## When you finish, report to Jacob
1. The model you ran on, the scenario count, and the seal `commit` hash.
2. The assumptions you recorded, one line each. v0.1 aims for zero, so every one is worth reporting.
3. Any place where the spec or the plan still looks inconsistent. Report it; do not edit.

Jacob will carry **only** `private/expectations.seal.json` into the repo, at `sealed/v0.1/`. Everything else stays private until the reveal.
