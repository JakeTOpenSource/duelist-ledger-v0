"""Case records, the deterministic pre-classifier, strikes and common-mode detection.

In plain words: every hold, denial, trip or rejected plan becomes a case with a first-guess
class (sensor fault, probing, agent violation, suspected injection, ...). If the human approved
the held thing anyway, the case is re-labelled "gate-miscalibrated". Agent violations add
strikes to the agent's identity. If the same untrusted source shows up in suspected injections
across several sessions, the whole organisation is held (common-mode).
"""

SENSOR = ("T3", "RECEIPT_GAP", "SEQ_GAP", "SILENCE", "CHAIN", "VERIFY_MISMATCH")
NOT_A_CLASS = ("CHALLENGE", "CONFIRM_T3", "MONITOR")


def _is(code, name):
    return code == name or code.startswith(name + "_")


def pre_classify(primary, failing_tainted=False, session_tainted=False, h2_all_pinned=False):
    """First matching rule of spec sec. 5.6."""
    code = primary or ""
    if any(_is(code, s) for s in SENSOR):
        return "sensor-fault"
    if code == "PROBE":
        return "probing"
    if _is(code, "H0"):
        return "agent-violation"
    if code in NOT_A_CLASS:
        return "none"
    if failing_tainted or ((_is(code, "T1") or _is(code, "T2")) and session_tainted):
        return "injection-suspected"
    if _is(code, "H2") and not session_tainted and h2_all_pinned:
        return "declaration-gap"
    if any(_is(code, c) for c in ("H2", "H3", "T1", "T2")) and not session_tainted:
        return "agent-violation"
    if code.startswith("H5_"):
        return "budget"
    if _is(code, "H6"):
        return "persistence-after-taint"
    return "unresolved"


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
