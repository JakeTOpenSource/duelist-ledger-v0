# Track B: Bring the Gate to Contract v0.3

Paste this whole file as the first message of a **new** session opened on this folder (`duelist-ledger-v0.3-track-b`). **Start only after Jacob confirms that Track A's v0.3 seal is committed and pushed.** The protocol requires a **different model family** from Track A (which runs on Claude Fable 5.1) whenever one is available. Whatever you are, record the model and its vendor in the report; if you are a Claude model, say which one.

---

You are **Track B** in a blind two-track run (the pilot-001 method), under contract v0.3. A separate Track A session has already written test scenarios and sealed their expected outcomes. You must never see them.

## Step 0: confirm the folder (before anything else)
Run `pwd`. The path must end in `duelist-ledger-v0.3-track-b`. If it doesn't, **stop immediately**. Don't list, read, or hash anything. Tell Jacob the session is in the wrong folder.

## Contract version
This folder holds tag `contract-v0.3` (commit `431a14a360371479e77658cbf9d6adcd7315d104`) of `JakeTOpenSource/duelist-ledger-v0`. Verify with `sha256sum BUILD_SPEC.md TRACK_SEPARATION_PROTOCOL.md`:

| file | sha256 |
|---|---|
| BUILD_SPEC.md | `e48af7c67509a8882ccd61aae01057060cf6cf2cecb08419b4cee61eff8eed77` |
| TRACK_SEPARATION_PROTOCOL.md | `c4d4f90c5a2f9a547e202594327012b3fd198552634b4a77afe4c1b9c539ff71` |

If either checksum differs, stop and tell Jacob.

## This prompt is not contract
It tells you where things are and what to hand back. Where anything in it differs from `BUILD_SPEC.md`, follow the spec and report the difference.

## Blindness rules
- Read only the files in this folder. Do not read, list, or search any path outside it. Do not use web search or fetch, and do not clone or open the GitHub repo. If a step would need anything outside this folder, stop and ask Jacob. Never request permission to read elsewhere.
- Never try to guess or reconstruct Track A's scenarios. Write your own test fixtures from the spec.
- Any helper agent, script or workflow you run must read and write only inside this folder. Output that lands anywhere else must be left unread, and your report must say so.

## Starting point
This folder holds the **published v0.1 build** (repo commit `64e33e5`): `run.py`, `duelist_ledger/`, `config/`, `tests/`, `docs/IMPLEMENTATION_NOTES.md` and its README. An earlier Track B session built it blind from contract v0.1; no build was ever made for v0.2. Your job is to bring it into **full conformance with contract v0.3**. Read the whole BUILD_SPEC first. The spec is the authority; the old code and notes are not.

Two amendments separate this build from the spec. Amendment A3 (v0.2) touched sections 2, 3.1, 3.7, 4, 5, 5.1, 5.3, 5.5, 5.6, 6, 7.1, 7.2, 8, 12, 14 and 17. Amendment A4 (v0.3) touched sections 0, 2, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, the new 3.8, 4, 5, 5.1, 5.2, 5.5, 5.6, the new 5.7, 6, 7, 8, 9, 10, 12, 14, 17, 18 and the new 19. This list says where to look, not what the text means. Read the text.

## Requirements
- Python 3.14, standard library, plus at most one optional package for Ed25519 as sec. 0 allows (`cryptography` or `pynacl`). Without it, sign with the HMAC stand-in the spec describes and say so. No network, no API keys, no LLM calls. If `py -3.14` is not available to you, stop and tell Jacob.
- `decide()` stays pure. `decide.py` + `state.py` stay under 1,500 lines combined.
- Every sec. 17 test exists and passes, the new ones included; the ones the spec marks deferred (PAUSE) and the two-house tests (sec. 19) are not required. Update your own fixtures where v0.3 invalidates them.
- `run.py` supports `--scenarios`, `--reveal`, `--salt` and `--seal <path>`. Its defaults are `scenarios/v0.3/` and `sealed/v0.3/expectations.seal.json`. The bridge will pass `--seal sealed/v0.3/expectations.seal.json`.
- Update `docs/IMPLEMENTATION_NOTES.md`. Mark every earlier reading that v0.3 now pins (as `pinned by v0.3`) or overrides (as `changed by v0.3`, and say what changed). Add any **new** ambiguity you hit. v0.3 aims for zero, so each one matters.
- The README opens with the caveat line as sec. 0 now words it and says "contract v0.3".
- Per-run working files go under `tempfile.gettempdir()` in short subfolders.

Before reporting, run both of these and make them pass:
```
py -3.14 -m unittest discover -s tests
py -3.14 run.py --scenarios tests/fixtures
```

## When you finish, report to Jacob
Include:
- the model you ran on, and its vendor or family;
- whether the Ed25519 package was available, and which signatures the build uses;
- the changes you made, grouped by spec section;
- the test results;
- the `decide.py` + `state.py` line count;
- the list of new ambiguities;
- **known nonconformances:** every place you know the build still departs from the spec and did not fix, whether found by your tests, by a helper review, or by reasoning, each with the code path and the predicted effect on the sec. 14 fields. PAUSE, if omitted, goes on this list as deferred. If there is nothing else, write "none known". The bridge logs this list before your build is published, and the build is published as delivered;
- anything written outside this folder during the session (it should be nothing).

Do not commit, push, or touch any git repository. Jacob carries your folder into the repo.
