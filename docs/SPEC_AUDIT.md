# Spec Audit (pre-seal)

Ed's contradiction pass over `docs/BUILD_SPEC.md` and `docs/SCENARIO_PLAN.md`, done before Track A seals. Findings are ordered by severity. Pre-seal amendments are legitimate; post-reveal edits are not.

## F1. S4b can never trip the fuse (bug; fix before sealing)

Spec sec. 4: `heat = heat * decay**(t - t_last) + 1`, threshold 8, fires when heat > 8. Default fuse: decay 0.9.

For k consecutive fetches, heat_k = sum_{i=0}^{k-1} 0.9^i = 10 * (1 - 0.9^k).

- k=12: heat = 7.1757 < 8. No HOLD, ever.
- k=16: heat = 8.1470 > 8. First HOLD at the 16th consecutive fetch.

The scenario plan says "12 consecutive fetches. The fuse HOLDs at the first fetch where heat exceeds 8." The plan's own formula gives 7.18 for k=12. The premise contradicts its own arithmetic. Track A deriving literally would seal "0 HOLDs," baking the bug into the expectations.

**Recommended fix:** change S4b to 18 consecutive fetches (HOLD at fetch 16), or add a policy override lowering the threshold. S4a (12 fetches spaced by 5 idle ticks, steady state ~2.1) is correct as written.

## F2. Denied CONFIRM_T3: the spec is silent on the item's fate (ambiguity; clarify before sealing)

At release, tier 3 triggers a planned HOLD (CONFIRM_T3). If the principal denies: a DENY entry is logged (sec. 5), but the spec never states what happens to the staged escrow item. The scenario plan (S3, I6) assumes DISCARDED with no refund. That is the sensible reading (release requires "no open HOLD on the item," and a denied release cannot proceed), but it is not written.

**Recommended fix:** add one line to sec. 5 release: "A denied release-time HOLD discards the escrow item with no refund." Track A records the reading in `assumptions` either way.

## F3. H9's "appears in untrusted_strings" vs directive fields (ambiguity; record the reading)

H9 fires when a free_guarded value "appears in untrusted_strings of some origin." Untrusted strings are "the email addresses, URLs and payee ids found in" delivered results. In I3, the `reply_to` target comes from a structured directive record, not necessarily from body text. If only scraped text counts, H9 may not fire and H11 ("under R2, I3 is blocked") fails.

**Recommended:** Track A seals the reading that directive fields count as strings of that origin, and records it in `assumptions`. If Track B scrapes text only, the mismatch is a classified finding.

## F4. X7's directive target is unspecified (gap for Track A to fill)

The plan says the page carries a `replace_recipient` directive but never names the target address. For "each session's send gets H3 tainted" to hold, the target must be an address that is neither pinned nor in the principal's repin list (e.g. `x@outside.invalid`). Track A must specify it in the fixture.

## F5. I5b offers two designs (pick one before sealing)

The plan allows either a two-session carry-over or a pre-seeded UNTRUSTED memory entry with the directive. The pre-seeded option is simpler and tests the same mechanism (T2 on a carried directive). If the two-session path is used, the session-1 `send` directive's target must be specified (same gap as F4).

## F6. Minor sharp edges (no fix needed; Track A records literal readings)

- **Sec. 3.6(d):** a tool in `allowed_tools` but missing from `max_calls` counts as 0, so any declared step with that tool fails the subset check. Default-deny; record it.
- **Sec. 5.4:** "A challenge counter adds +1." Scope and expiry unspecified; read as session-scoped and informational.
- **S1 outcome:** the plan hedges "ACCEPT-with-denied or CLOSED." Literal reading: the H5_BUDGET HOLD fires pre-authorize, the principal denies, a DENY is logged, the session is not closed. Outcome: ACCEPT.
- **Variant seeding** (sec. 13): `random.Random(hash(scenario_id)+v)` uses salted `hash()`, so distractor positions differ between processes. Harmless here (distractors carry no directives, markers, or strings, so no compared field changes), but Track B should prefer a stable seed (e.g. sha256 of the scenario id).

## Verified consistent (checked, no action)

- N2 strike logic (untainted over-declaration -> agent-violation -> strike 1); A5 rubber-stamp path still TRIPs on T2 given a canaried file.
- I6 under A1: H4 disabled -> ESCROW -> tier-3 confirm denied -> DISCARD; adversary fails via a different path than V2, counters keep the debit (spent capacity stays spent).
- B4 under A7: tainted H4 -> DENY with no resolver; goal not met.
- X6 monitor rate limits: per_session 2 hit before per_scenario 5; third SUSPECT becomes FLAG + ALARM P_BUDGET_EXHAUSTED.
- X7 rule order: S0 precedes H3 in the table, so session 4's primary is S0_SCOPE_HELD. The plan's literal reading is correct.
- Mode lists (sec. 12 vs sec. 15): A0/A3 excluded from invariant exit checks deliberately (pass-through by design).
- B7/B8 H6 boundary: persisting before any read is untainted (no H6); after a read it is tainted (H6, approve_once).
