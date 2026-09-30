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

## A3 (post-reveal, 2026-09-30): contract v0.2

A3 resolves everything recorded in `docs/CONTRADICTIONS.md` for the v0.1 run:
- the spec ambiguity C4 and the pre-registered gate bug G1, under author decisions 13 and 14 (report section 6);
- the sec. 5.1 group order (L3), under author decision 15;
- the clauses both v0.1 tracks settled by the same unpinned assumption (L4–L8), and the invisible plan/spec conflict (L9). Their shared reading is now normative text, except L3, where the author chose the other reading;
- Track B's fifteen new readings (N1–N15) and the two gaps its review found;
- the custody lessons of the v0.1 run, including author decision 16 (model family).

A3 applies to the **next** run. It changes no v0.1 result. v0.1's blind claim stays run 1 against tag `contract-v0.1`. A blind claim under v0.2 needs a fresh two-track run.

| # | Source | Where | Change |
|---|---|---|---|
| 1 | C4, decision 13 | BUILD_SPEC §8, §14, §17; SCENARIO_PLAN X2, fixture rules | A `bypass_write` effect is `{tool, args}`, the proposal shape, applied through world.apply with a receipt the gateway never issued. A required test checks that its `email_sent` predicate is true and T3_BYPASS fires |
| 2 | G1, decision 14 | BUILD_SPEC §3.1, §3.7, §4, §5, §5.5, §5.6, §7.1, §12, §17; SCENARIO_PLAN N5, H16 | **Undeclared proposals.** No proposal is refused before decide(). An unknown tool or an unresolvable handle is H1 before DECLARE and H2 after, with deny as the only option in every mode; the case is agent-violation; strikes and probes count as for any denied H1/H2. In pass-through it executes nothing. New scenario N5 exercises the clean-room, unknown-tool and unresolvable-handle cases |
| 3 | L3, decision 15; Track B N1, N2, N4 | BUILD_SPEC §4, §5.1, §17; SCENARIO_PLAN S2b, S2c, H12 | Mixed-reason HOLDs are settled in the fixed order S0, session, action, whatever the rule-table order. The HOLD's primary is the first reason of the first group settled. Follow-on HOLD fields, action-group rule matching and repin are defined. S2b/S2c are re-derived: holds `[H5_BUDGET_SESSION]` and `[H5_BUDGET_SESSION, H5_BUDGET]` |
| 4 | L4 | BUILD_SPEC §7.2; SCENARIO_PLAN N1 | Every agent kind obeys directives in every delivered value, pre-op results included |
| 5 | L5 | BUILD_SPEC §7.2; SCENARIO_PLAN I4 | `add_step` pins `{slot: [value]}` per arg under step ids x1, x2, … |
| 6 | L6 | BUILD_SPEC §7.2; SCENARIO_PLAN I9 | `write_then_use` uses the first declared write_workspace and read_file steps; if either is not allowed, later sends keep their scripted `to` |
| 7 | L7; Track B N5, N14 | BUILD_SPEC §5.1, §5.5 | A denial whose primary is S0 never counts toward probes, in any mode, A7 included. An action denied by the S0 group counts toward nothing |
| 8 | L8 | BUILD_SPEC §12, §17 | Under pass-through the sensor HOLDs and TRIPs are logged exactly as in V2: scoped, in `holds`/`trips`, with sensor-fault cases |
| 9 | L9 | SCENARIO_PLAN I5a | The failing slot is `action`, per sec. 4 |
| 10 | Track B N3 | BUILD_SPEC §5.1 | A follow-on HOLD's case uses the decision-level `failing_tainted` and origins |
| 11 | Track B N6 | BUILD_SPEC §8 | A missing fault `index` means 1; a non-integer index is a load error; 1.0 is accepted |
| 12 | Track B N7, N8 | BUILD_SPEC §4, §5.6 | H2's slot: sinks-table order among the args present, "pinned anywhere" over every step and slot, numbers by value. Rule 8 refers to the H2 reason's own slot |
| 13 | Track B N9 | BUILD_SPEC §4 | `expires_t` = mint time + 2 × the largest escrow window; an item held at release by S0 does not expire while held |
| 14 | Track B N10 | BUILD_SPEC §8, §14 | `detected` is judged per fault, and a fault that never fires counts as not detected |
| 15 | Track B N11 | BUILD_SPEC §8 | `mutate_escrow` on a sink with no dest_slot writes the first guarded slot |
| 16 | Track B N12 | BUILD_SPEC §5.6 | An H7 case cites no origins, so it never feeds common-mode |
| 17 | Track B N13 | BUILD_SPEC §5 | Where a SESSION_OPEN verify failure is logged, and what the refused session's summary carries |
| 18 | Track B N15 | BUILD_SPEC §14 | Expectations with another `version` are still compared, with a note |
| 19 | Track B review gaps | BUILD_SPEC §3.1, §7.1 | `handle_of` for an origin the agent never received is an unresolvable handle: value null, context label, undeclared proposal |
| 20 | SEQ_GAP had no scenario (entry-path rule) | BUILD_SPEC §3.7, §5.1, §7.1, §17; SCENARIO_PLAN X9, H17 | SEQ_GAP semantics pinned: logged without AUTHORIZE, HELD reply, seq resync, link clears at the next clean reconcile, R0/R1 unaffected. A call op may carry `seq`. New scenario X9 |
| 21 | Entry-path coverage (protocol lesson from G1) | SCENARIO_PLAN fixture rules, coverage table, B12, N6 | Every gate entry path gets at least one scenario. New: B12 (narrowing amend) and N6 (schema-invalid declaration) |
| 22 | Plan-vs-prompt mismatch (Track A v0.1 report) | SCENARIO_PLAN outputs; PROTOCOL seal | Outputs go to `private/` inside the Track A folder; the bridge carries the seal; the seal file carries `contract` |
| 23 | Custody lessons of the v0.1 run | TRACK_SEPARATION_PROTOCOL | Known nonconformances are pre-registered before the implementation is published; prompts are not contract and are published; helper agents write inside the track folder; the bridge never edits gate code before the reveal; diagnostics are not runs |
| 24 | Decision 16 | TRACK_SEPARATION_PROTOCOL | Track B must run on another model family where one is available; otherwise the log records why |
| 25 | Versioning | BUILD_SPEC header, §1, §14; SCENARIO_PLAN | Contract v0.2; `sealed/v0.2/`, `scenarios/v0.2/`, `results/v0.2/`; expectations `"version": "0.2"` |
| 26 | Pre-seal audit of this draft (bridge, Opus 5.5, 2026-09-30), finding 1 | BUILD_SPEC §3.7; SCENARIO_PLAN X9 | `seq` numbers proposals only, from 1 per session; any other value is a gap; a gapped proposal heats no fuse and the agent continues. X9's steps (3) and (4) carry no explicit seq (the plan had step (4) at 10; the gate expects 11) |
| 27 | Audit finding 2, 3 | BUILD_SPEC §4, §7.1 | An undeclared proposal is decided by T1, T2, H1 and H2 only: no other rule, no S0 check, no debits, never a mixed HOLD, deny-only in every mode including A7; a null destination is in no audience. `sender_of` a message never received is undeclared too |
| 28 | Audit finding 4, 5, 7 | BUILD_SPEC §4, §5.1, §5.5 | SEQ_GAP clears at the first reconcile after the gap that raises no new receipt fault. In A7 the DENY's primary follows the mixed-reason primary rule and no group is settled. A DENY with primary S0 or H5_* never counts as a probe; other A7 DENYs count under the per-tool rule |
| 29 | Audit finding 8, 10, 12, 14 | BUILD_SPEC §2, §5, §5.3, §6, §12; SCENARIO_PLAN N7 | `salt_bytes` and the seal file are defined in the spec. Principal matching covers every action-group decision at any scope and never a session reason. A narrow amend replaces the step and must be a subset, else it is widen; new scenario N7 makes B12 falsifiable. VERIFY_MISMATCH removed from the pass-through sensor list |
| 30 | Audit finding 6, 9, 11 | TRACK_SEPARATION_PROTOCOL; SCENARIO_PLAN I9 | The previous published build is a listed Track B input; "available" is defined; a cross-family patch of a same-family build is reported as such; a helper's outside read burns only if it could have exposed the other track. I9 pins its first write and read steps |

**Not changed:** the T/H rule table rows other than H2's condition, the invariants, the set of modes, and hypotheses H1–H11 and H13–H15.

**Deferred to A4, pending author decisions 9–11 and the section 4.14 items:** containment instead of a session TRIP for blocked tainted attempts; a signature over the exact arguments of every irreversible effect; hard-deny of tainted guarded values by default; the keyed agent->gate link; the human RUN->HOLD control; common-mode and attacker-triggered TRIP denial of service; the T1 content scope; one-party labels. These change the design, not only the contract, so they get their own amendment and their own run.

**Code conformance.** Track B's v0.1 build (`64e33e5`) needs changes for at least items 1, 2, 3, 7, 20 and 26–29. Those changes are made blind in the next Track B session and are *not* a blind result until the v0.2 reveal.

**Pre-seal audit.** Before this amendment is tagged, one adversarial reviewer (Opus 5.5, read-only) audited the draft against the unchanged text and walked every new or changed scenario through the rules. It found one plan error (X9's sequence numbers) and the open clauses listed in items 26–30; all were fixed in the draft. Its scenario walk-throughs for B12, N5, N6, S2b, S2c, X2, I4, I5a, I9 and N1 agreed with the plan's stated outcomes.
