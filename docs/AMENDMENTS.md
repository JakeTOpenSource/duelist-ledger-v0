# Contract Amendments Log

This log records every change to the contract (`BUILD_SPEC.md`, `SCENARIO_PLAN.md`, `TRACK_SEPARATION_PROTOCOL.md`). It is the changelog bound applied to the spec itself: each entry names the finding, the change, and the reason.

**Pre-seal** amendments are legitimate: they happen before Track A seals, so no expected outcome is known yet. **Post-reveal** edits to expectations are not allowed. A corrected expectation becomes a new, separately sealed version, with lineage back to the one it replaces.

## A1 (pre-seal, 2026-09-29): resolves SPEC_AUDIT F1-F6, plus a path cleanup

| # | Finding | File | Change | Reason |
|---|---|---|---|---|
| 1 | F1 | SCENARIO_PLAN | S4b: 12 → 18 consecutive fetches; the heat formula is stated in closed form | At k = 12 the heat is 7.18 < 8, so the fuse could never trip. The first HOLD is at k = 16 |
| 2 | F2 | BUILD_SPEC sec. 5 (Release) | Any HOLD on an escrow item that is resolved by deny, or never cleared by drain, DISCARDs the item with no refund | The item's fate after a denied release was unstated. Scenarios S3 and I6 depend on it |
| 3 | F3 | BUILD_SPEC sec. 4 (inputs) | `untrusted_strings` includes strings found in directive-record fields, not only in content | Without this, H9 may not fire in I3, and hypothesis H11 would test the parser rather than the rule |
| 4 | F4 | SCENARIO_PLAN X7 | Directive target fixed to `x@outside.invalid` | The target was unspecified, and the expected H3 depends on it |
| 5 | F5 | SCENARIO_PLAN I5b | Chose the pre-seeded UNTRUSTED memory design (1 session) | It is simpler, tests the same carried-directive mechanism, and P1 already covers the two-session path |
| 6 | F6 | BUILD_SPEC sec. 13 | Variant seed uses sha256 of the scenario id, never Python's built-in `hash()` | `hash()` is salted per process, so variants were not reproducible |
| 7 | F6 | BUILD_SPEC sec. 5.4 | The challenge counter is session-scoped and informational | Its scope was unspecified |
| 8 | F6 | BUILD_SPEC sec. 3.6(d) | A tool missing from `envelope.max_calls` cannot be declared, as deliberate default-deny | Makes the literal reading explicit |
| 9 | F6 | SCENARIO_PLAN S1 | Outcome fixed to ACCEPT (the budget HOLD is denied; the session is not closed) | Removes an "either/or" hedge from a sealed expectation |
| 10 | cleanup | SCENARIO_PLAN | Machine-specific local paths replaced with a generic private folder outside the repo | Portability and privacy. The plan is public |

**Not changed:** the rule order, the invariants, the mode definitions, the hypotheses.

## A2 (post-reveal, 2026-09-29): contract v0.1

A2 resolves everything recorded in `docs/CONTRADICTIONS.md` for the v0 run:
- the two author decisions (C1, C2);
- the release-time rule behind the expectation error (C3);
- the two latent divergences (L1, L2);
- the clauses both blind tracks flagged. Their shared reading is now normative text.

A2 applies to the **next** run. It changes no v0 result. v0's blind claim stays run 1 against contract `09d26a6`. A blind claim under v0.1 needs a fresh two-track run.

| # | Source | Where | Change |
|---|---|---|---|
| 1 | C1, author decision | BUILD_SPEC §4, §12 | Pass-through (A0/A3) switches off everything that acts on agent proposals or liveness: clean room, decide(), SILENCE, SEQ_GAP, probes, monitor, challenge HOLDs, declaration/amend checks. The pipeline-integrity sensors stay on: receipts, reconcile, CHAIN, refusal after CHAIN |
| 2 | C2, author decision | BUILD_SPEC §4, §5.1, §5.6, §14, §17 | Mixed-reason HOLDs are settled group by group (S0, then session, then action), and the strictest resolver governs. A follow-on HOLD is logged for each remaining group. A per-action approval never lifts a session- or org-scope restriction |
| 3 | C3, the rule Track A missed | BUILD_SPEC §5 (release); SCENARIO_PLAN X8 | A scope held at release logs one S0 HOLD on the item. It is re-checked at every release pass, and if still held at drain the item is DISCARDed and the session ends CLOSED. The new scenario X8 exercises this in V2 |
| 4 | L1, latent divergence | BUILD_SPEC §8, §17; SCENARIO_PLAN X1, X1b | Fault `index` is 1-based and counted across the scenario. `index: 0` is a load error. The new X1b (index 2) tells the two readings apart |
| 5 | L2, latent divergence | BUILD_SPEC §8, §13, §17; SCENARIO_PLAN X5 | `mutate_escrow{index, to}` writes exactly the fixture's `to`. It is pinned by a required unit test, since T4 fires for any value |
| 6 | Pre-classifier gaps, flagged by both tracks | BUILD_SPEC §4, §5.6, §17 | `failing_slot`/`failing_tainted` are defined, including for H2 (the first guarded value not pinned anywhere). New rules: T4 → sensor-fault; COMMON_MODE → new class `common-mode`; tainted H7 → injection-suspected; S0 → none; untainted H1 → agent-violation; H2 with all guarded values pinned → declaration-gap, tainted or not |
| 7 | S0 resolvability, flagged by both | BUILD_SPEC §5.1 | S0 is never principal-resolvable, not even by the rubber stamp |
| 8 | Clean room vs rule order, flagged by Track A | BUILD_SPEC §4, §5 | Before DECLARE, decide() runs with declaration = null, and T-rules fire ahead of H1 |
| 9 | H0 scope, flagged by both | BUILD_SPEC §3.6, §5.5 | H0 is declaration-scoped: a deny rejects only that declaration, approve_once is available, only a *denied* H0 counts as a probe, and one case per H0 |
| 10 | VERIFY vs RECEIPT_GAP, flagged by both | BUILD_SPEC §5 | A receipt missing only from the log is RECEIPT_GAP, never VERIFY_MISMATCH |
| 11 | H6 on schedule, flagged by both | BUILD_SPEC §4 | Stated explicitly: H6 cannot fire for schedule, which has no content slots |
| 12 | Formats, flagged by both | BUILD_SPEC §8, §14 | The predicate encoding `{"<name>": {params}}` is normative. `scopes` = levels. The comparison rules for `counters`, `detected` and `confirms` are defined. `holds` includes follow-on HOLDs. `version` = contract version |
| 13 | Tamper detection timing, Track A's X4 finding | BUILD_SPEC §5, §9; SCENARIO_PLAN X4a | verify() also runs at SESSION_OPEN and at scenario end, and the current session is refused. X4 returns to two sessions |
| 14 | STRIKE hold, Track B note 39 | BUILD_SPEC §5.1 | v0.x raises no mid-session STRIKE HOLD. Strikes only refuse later sessions |
| 15 | Probe counting, Track B note 43 | BUILD_SPEC §5.5 | Exactly which denials count is pinned |
| 16 | Session CLOSED rule, agreed by both | BUILD_SPEC §5 | Only scope-held discards close a session; denied CONFIRM_T3/MONITOR discards leave it ACCEPT |
| 17 | Logical clock, Track A assumption 9 | BUILD_SPEC §5 | Which agent messages advance t |
| 18 | S0 scopes and H5_BUDGET state, Track B notes 23–24 | BUILD_SPEC §4, §5.1 | S0 checks org, then agent link, then sink link. H5_BUDGET sets no scope state |
| 19 | A3 cross-check, agreed by both | BUILD_SPEC §12 | The definition of dest and the multi-session aggregation |
| 20 | Versioning | BUILD_SPEC header, §1, §14 | Contract version stated. Artifacts are namespaced under `sealed/<version>/`, `scenarios/<version>/` and `results/<version>/run<N>/` |
| 21 | Plan slips reported by v0 Track A | SCENARIO_PLAN B9, N2, X4a, I9, X6, I5a | Corrected. A budget-trap rule is added to the fixture rules |
| 22 | S2 masked "no refund" (C2) | SCENARIO_PLAN S2, S2b, S2c | S2 is isolated (`session_share` 2.0). S2b/S2c exercise the mixed-resolver HOLD on purpose |
| 23 | Hypothesis wording (v0 run) | SCENARIO_PLAN | H1 and H5 reworded; H12–H15 added (strictest resolver, fault index base, pass-through, release-time S0) |
| 24 | Custody lessons, and the review's independence note (Ed) | TRACK_SEPARATION_PROTOCOL | Folder isolation, the guard-first rule, and settings. The bridge-helper hashing rule. No web access for Track B. **Model-family independence:** tracks should differ in model family, and the model used is logged and reported. The publication order. Latent divergences are reported. Corrections are versioned, and the blind claim cites run 1 |
| 25 | Principal rule matching, Track B note 46 | BUILD_SPEC §6 | A `reason` matches the code itself or a prefix ending at a `_` boundary. A rule without `tool` matches any tool. Approve rules apply only to a mixed HOLD's action group; its session group is settled by `session_holds` |

**Not changed:** the T/H rule table and its order (item 8 only states the order both tracks already implemented), the invariants, the set of modes, and the substance of hypotheses H2–H4 and H6–H11.

**Code conformance.** Many A2 items pin the readings Track B's v0 build (`b2e592a`) already implements. It is expected to need changes for at least items 4, 5, 6 and 13. This is to be confirmed by a conformance check. Those changes are *not* a blind result.
