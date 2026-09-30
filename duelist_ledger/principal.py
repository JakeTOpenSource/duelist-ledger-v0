"""The scripted HOLD desk (the human principal), and its rubber-stamp variant.

In plain words: when the gate holds something, this stand-in human decides, following the
scenario's principal_policy exactly: approve once if a matching rule exists and approval is
allowed, otherwise re-pin a value it recognises where repin is offered, otherwise deny. The
rubber stamp approves whatever it is allowed to approve and repins the displayed value where a
HOLD offers repin (H8, attended steps); a no-resolver DENY offers nothing (sec. 6, A4.4).
"""

from .decide import member


def reason_matches(rule_reason, primary):
    """A rule reason is a prefix of the primary code: 'H6' matches 'H6_PERSIST_AFTER_TAINT'."""
    if not isinstance(rule_reason, str) or not isinstance(primary, str):
        return False
    return primary == rule_reason or primary.startswith(rule_reason + "_")


class Principal:
    def __init__(self, policy=None, rubber_stamp=False):
        p = policy or {}
        self.approve_rules = list(p.get("approve_once") or [])
        self.repin_values = list(p.get("repin") or [])
        self.confirm_rules = list(p.get("confirm_t3") or [])
        self.session_policy = p.get("session_holds", "close")
        self.challenge_policy = p.get("challenge", "deny")
        self.monitor_policy = p.get("monitor", "deny")
        self.rubber_stamp = bool(rubber_stamp or p.get("rubber_stamp"))

    def resolve_l0(self, primary, tool, approve_ok, repin_ok, held_value):
        """Returns ('approve_once'|'repin'|'deny', value)."""
        if self.rubber_stamp:
            if approve_ok:
                return "approve_once", None
            if repin_ok:
                return "repin", held_value
            return "deny", None
        if approve_ok:
            for rule in self.approve_rules:
                if reason_matches(rule.get("reason"), primary) and rule.get("tool", tool) == tool:
                    return "approve_once", None
        if repin_ok and held_value is not None and member(held_value, self.repin_values):
            return "repin", held_value
        return "deny", None

    def session_hold(self, code):
        """'resume' or 'close'. PROBE and CONTAIN_LIMIT always close (sec. 5.1)."""
        if code in ("PROBE", "CONTAIN_LIMIT"):
            return "close"
        if self.rubber_stamp:
            return "resume"
        return "resume" if self.session_policy == "resume" else "close"

    def confirm_t3(self, tool, args):
        if self.rubber_stamp:
            return True
        for rule in self.confirm_rules:
            if rule.get("tool", tool) != tool:
                continue
            if all(k == "tool" or member(args.get(k), [v]) for k, v in rule.items()):
                return True
        return False

    def monitor(self):
        return self.rubber_stamp or self.monitor_policy == "approve"

    def challenge(self, request):
        return self.rubber_stamp or self.challenge_policy == "approve"
