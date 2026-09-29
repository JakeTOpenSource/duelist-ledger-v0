# Contract Amendments Log

This log records every change to the v0 contract (`BUILD_SPEC.md`, `SCENARIO_PLAN.md`). It is the changelog bound applied to the spec itself: each entry names the finding, the change, and the reason.

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
