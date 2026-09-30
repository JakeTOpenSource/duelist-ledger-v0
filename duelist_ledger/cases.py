"""Case records, the deterministic pre-classifier, strikes and common-mode detection.

In plain words: every hold, no-resolver denial, trip or rejected plan becomes a case with a
first-guess class (sensor fault, probing, agent violation, suspected injection, ...). If the
human approved the held thing anyway, the case is re-labelled "gate-miscalibrated". Agent
violations add strikes to the agent's identity. If the same untrusted source shows up in
suspected injections across several sessions, the whole organisation is held (common-mode).
"""

SENSOR = ("T3_BYPASS", "T4_ARGS_MISMATCH", "T5_TOKEN_REFUSED", "RECEIPT_GAP", "SEQ_GAP", "SILENCE",
          "CHAIN", "VERIFY_MISMATCH")
NOT_A_CLASS = ("CHALLENGE", "CONFIRM_T3", "MONITOR", "PAUSE")
T_RULES = ("T1_HOUSE", "T2_CANARY")
UNTAINTED_VIOLATIONS = ("H1_NO_DECLARATION", "H2_NOT_DECLARED", "H3_PINNED_MISMATCH", "T1_HOUSE", "T2_CANARY")


def pre_classify(primary, failing_tainted=False, session_tainted=False, h2_no_slot=False, undeclared=False):
    """First matching rule of spec sec. 5.6 (the v0.3 numbering, A4.3).

    failing_tainted is the decision's (sec. 4), so it may come from a non-primary reason.
    h2_no_slot: the H2 reason named no slot (every guarded value is pinned somewhere).
    undeclared: the H1/H2 was raised by an undeclared proposal (rule 5).
    """
    code = primary or ""
    if code in SENSOR:
        return "sensor-fault"                                                   # 1
    if code == "PROBE":
        return "probing"                                                        # 2
    if code == "CONTAIN_LIMIT":
        return "injection-suspected"                                            # 3
    if code == "COMMON_MODE":
        return "common-mode"                                                    # 4
    if code == "H0_ENVELOPE" or (undeclared and code in ("H1_NO_DECLARATION", "H2_NOT_DECLARED")):
        return "agent-violation"                                                # 5
    if code in NOT_A_CLASS:
        return "none"                                                           # 6
    if failing_tainted or (code in T_RULES and session_tainted) or (code == "H7_AMEND_WIDEN" and session_tainted):
        return "injection-suspected"                                            # 7
    if code == "S0_SCOPE_HELD":
        return "none"                                                           # 8
    if (code == "H2_NOT_DECLARED" and h2_no_slot) or (code == "H7_AMEND_WIDEN" and not session_tainted):
        return "declaration-gap"                                                # 9
    if code in UNTAINTED_VIOLATIONS and not session_tainted:
        return "agent-violation"                                                # 10
    if code.startswith("H5_"):
        return "budget"                                                         # 11
    if code == "H6_PERSIST_AFTER_TAINT":
        return "persistence-after-taint"                                        # 12
    return "unresolved"                                                         # 13


class Cases:
    def __init__(self, strike_hold=3, common_mode_sessions=3):
        self.cases = []
        self.strikes = {}
        self.strike_hold = strike_hold
        self.common_mode_sessions = common_mode_sessions
        self.origin_sessions = {}

    def open(self, *, session, identity, ref, primary, reasons, pre_class, origins=()):
        case = {"case_id": "c%d" % (len(self.cases) + 1), "session": session, "identity": identity,
                "ref": ref, "primary": primary, "reasons": list(reasons), "pre_class": pre_class,
                "final_class": None, "origins": sorted(set(origins))}
        self.cases.append(case)
        return case

    def finalize(self, case, resolution=None):
        """Set final_class; add a strike for a final agent-violation. Returns final_class."""
        if case["final_class"] is not None:
            return case["final_class"]
        if resolution in ("approve_once", "repin"):
            case["final_class"] = "gate-miscalibrated"
        else:
            case["final_class"] = case["pre_class"]
        if case["final_class"] == "agent-violation" and case["identity"] is not None:
            self.strikes[case["identity"]] = self.strikes.get(case["identity"], 0) + 1
        return case["final_class"]

    def note_injection(self, case):
        """Count each cited origin once per session. Returns origins that just hit the threshold."""
        hit = []
        for origin in case["origins"]:
            sessions = self.origin_sessions.setdefault(origin, set())
            if case["session"] in sessions:
                continue
            sessions.add(case["session"])
            if len(sessions) == self.common_mode_sessions:
                hit.append(origin)
        return hit

    def strikes_of(self, identity):
        return self.strikes.get(identity, 0)
