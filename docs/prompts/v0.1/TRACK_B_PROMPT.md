# Track B: Bring the Gate to Contract v0.1

Paste this whole file as the first message of a **new** Claude session opened on this folder (`duelist-ledger-v0.1-track-b`). **Start only after Jacob confirms that Track A's v0.1 seal is committed and pushed.** If possible, use a **different model family** from Track A (protocol v0.1, "Sessions"). If that isn't available, use a different model than Track A's, for example Opus 5.5. Record the model you use.

---

You are **Track B** in a blind two-track run (the pilot-001 method), under contract v0.1. A separate Track A session has already written test scenarios and sealed their expected outcomes. You must never see them.

## Step 0: confirm the folder (before anything else)
Run `pwd`. The path must end in `duelist-ledger-v0.1-track-b`. If it doesn't, **stop immediately**. Don't list, read, or hash anything. Tell Jacob the session is in the wrong folder.

## Contract version
This folder holds tag `contract-v0.1` (commit `aa4b65c226d7d810492c503c1d307ade787cdc0d`) of `JakeTOpenSource/duelist-ledger-v0`. Verify with `sha256sum BUILD_SPEC.md TRACK_SEPARATION_PROTOCOL.md`:

| file | sha256 |
|---|---|
| BUILD_SPEC.md | `cb50dfa349e23c1ab98673316ea7b6d365a0c73d45b3b206376e9189fd69ac1e` |
| TRACK_SEPARATION_PROTOCOL.md | `fcc493943c0caa9dd6a43e66e274fa027b5f8d6a909d7d3646ab7c6b5afb4258` |

If either checksum differs, stop and tell Jacob.

## Blindness rules
- Read only the files in this folder. Do not read, list, or search any path outside it. Do not use web search or fetch, and do not clone or open the GitHub repo. If a step would need anything outside this folder, stop and ask Jacob. Never request permission to read elsewhere.
- Never try to guess or reconstruct Track A's scenarios. Write your own test fixtures from the spec.

## Starting point
This folder already holds the **v0 build**: `run.py`, `duelist_ledger/`, `config/`, `tests/`, and `docs/IMPLEMENTATION_NOTES.md`. An earlier Track B session built it blind from contract v0. Your job is to bring it into **full conformance with contract v0.1**. Read the whole BUILD_SPEC first. The spec is the authority; the old code and notes are not.

What changed in the spec from v0 to v0.1. This list covers contract changes only; use the spec's own text for details:
1. **Pass-through (A0/A3), sec. 12.** Everything that acts on agent proposals or liveness is off, including SILENCE, SEQ_GAP, probes, the monitor and challenge HOLDs. The pipeline-integrity sensors stay on.
2. **Mixed-reason HOLDs, sec. 5.1.** They are settled group by group: S0, then session, then action. The strictest resolver governs, and a follow-on HOLD is logged for each remaining group.
3. **Release-time scope HOLD, sec. 5.** One S0 HOLD is logged on the item, re-checked at every release pass, and the item is discarded at drain. The session then ends CLOSED.
4. **Fault indices, sec. 8.** They are 1-based and counted across the scenario. `index: 0` is a load error.
5. **`mutate_escrow{index, to}`, sec. 8.** It writes exactly `to`.
6. **`failing_slot` / `failing_tainted`, sec. 4.** They are now defined, including for H2.
7. **Pre-classifier, sec. 5.6.** It has a new rule list, including T4 → sensor-fault, COMMON_MODE → common-mode (a new class), tainted H7 → injection-suspected, S0 → none, and untainted H1 → agent-violation.
8. **S0 is never principal-resolvable,** including by the rubber stamp.
9. **Before DECLARE,** decide() runs with declaration = null, and T-rules fire ahead of H1.
10. **The H0 HOLD is declaration-scoped** (sec. 3.6). Only a *denied* H0 counts as a probe.
11. **verify() also runs at every SESSION_OPEN and at scenario end,** and a failure refuses the current session.
12. **Probe counting (sec. 5.5), the session CLOSED rule (sec. 5), which messages advance the clock (sec. 5), S0's scope order (sec. 4), and H5_BUDGET setting no scope state** are all pinned.
13. **Formats (sec. 8, sec. 14):** the predicate encoding, `scopes` as levels, `holds` including follow-on HOLDs, and the definitions of `counters`, `detected` and `confirms`. Expectations carry `"version": "0.1"`.
14. **Principal rule matching (sec. 6):** a prefix match ends at a `_` boundary. Approve rules apply only to a mixed HOLD's action group.
15. **Required tests (sec. 17):** the list gained new required tests.

## Requirements
- Python 3.14, **standard library only**: no pip, no network, no API keys, no LLM calls.
- `decide()` stays pure. `decide.py` + `state.py` stay under 1,500 lines combined.
- Every sec. 17 test exists and passes, the new ones included. Update your own fixtures if v0.1 invalidates them (for example, a fault with `index: 0`).
- `run.py` supports `--scenarios`, `--reveal`, `--salt` and `--seal <path>`. The bridge will pass `--seal sealed/v0.1/expectations.seal.json`.
- Update `docs/IMPLEMENTATION_NOTES.md`. Mark every v0 reading that v0.1 now pins (as `pinned by v0.1`) or overrides (as `changed by v0.1`, and say what changed). Add any **new** ambiguity you hit. v0.1 aims for zero, so each one matters.
- The README opens with the caveat line and says "contract v0.1".
- Per-run working files go under `tempfile.gettempdir()` in short subfolders.

Before reporting, run both of these and make them pass:
```
py -3.14 -m unittest discover -s tests
py -3.14 run.py --scenarios tests/fixtures
```

## When you finish, report to Jacob
Include:
- the model you ran on;
- the changes you made, grouped by spec section;
- the test results;
- the `decide.py` + `state.py` line count;
- the list of new ambiguities.

Do not commit, push, or touch any git repository. Jacob carries your folder into the repo.
