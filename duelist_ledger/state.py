"""The scope state machine: who may hold, trip, resume or close what.

In plain words: every thing the gate can stop has a scope: one action (L0), one session (L1),
one link (L2: agent->gate, gate->world:<class>) or the whole organisation / a budget key (L3).
A scope is RUN, HOLD, TRIP or CLOSED. A scope is as stopped as its most stopped parent.

Who may change what (spec sec. 10):
  P (probabilistic: monitor)  may only raise RUN -> HOLD, and only within rate limits;
  D (deterministic rule)      may RUN -> HOLD, RUN|HOLD -> TRIP, HOLD -> RUN via a named predicate;
  H (human / operator)        may HOLD -> RUN, HOLD -> CLOSED, HOLD -> TRIP.
Nothing leaves TRIP; CLOSED is final.

This module also keeps the one-way counters and per-session tier floors, and audits itself
so that the invariants can be checked after every run.
"""

from .budget import Counters

RANK = {"RUN": 0, "HOLD": 1, "CLOSED": 2, "TRIP": 3}
TERMINAL = ("TRIP", "CLOSED")
ALLOWED = {
    "P": {("RUN", "HOLD")},
    "D": {("RUN", "HOLD"), ("RUN", "TRIP"), ("HOLD", "TRIP"), ("HOLD", "RUN")},
    "H": {("HOLD", "RUN"), ("HOLD", "CLOSED"), ("HOLD", "TRIP")},
}


def level_of(scope):
    """'L2:gate->world:PAYMENT' -> 'L2'."""
    return scope.split(":", 1)[0] if isinstance(scope, str) else "L0"


def default_parent(scope):
    if scope == "L3:org":
        return None
    if isinstance(scope, str) and scope[:3] in ("L1:", "L2:", "L3:"):
        return "L3:org"
    return None


class State:
    def __init__(self, p_per_session=2, p_per_scenario=5):
        self.scopes = {"L3:org": "RUN"}
        self.parents = {"L3:org": None}
        self.p_limits = (p_per_session, p_per_scenario)
        self.p_session = {}
        self.p_total = 0
        self.p_alarmed = False
        self.transitions = []
        self.violations = []
        self.counters = Counters()
        self.session_counters = {}
        self.tier_floors = {}

    # ---- scopes ----
    def register(self, scope, parent=None):
        if scope not in self.scopes:
            self.scopes[scope] = "RUN"
            self.parents[scope] = parent if parent is not None else default_parent(scope)
        return scope

    def own(self, scope):
        return self.scopes.get(scope, "RUN")

    def effective(self, scope):
        """Most restrictive state of the scope and all its ancestors."""
        worst, seen = "RUN", set()
        while scope is not None and scope not in seen:
            seen.add(scope)
            state = self.own(scope)
            if RANK[state] > RANK[worst]:
                worst = state
            scope = self.parents.get(scope, default_parent(scope))
        return worst

    def apply(self, event, source_class):
        """Request a state change. Returns {applied, kind, alarm}.

        kind is OK, NOOP, REJECTED, or FLAG (a P request over its rate limit: logged, no change).
        """
        scope = event.get("scope")
        target = event.get("to")
        session = event.get("session")
        if not isinstance(scope, str) or target not in RANK or source_class not in ALLOWED:
            return {"applied": False, "kind": "REJECTED", "alarm": None}
        self.register(scope, event.get("parent"))
        before = self.own(scope)
        if before in TERMINAL:
            return {"applied": False, "kind": "REJECTED", "alarm": None}
        if before == target:
            return {"applied": False, "kind": "NOOP", "alarm": None}
        if (before, target) not in ALLOWED[source_class]:
            return {"applied": False, "kind": "REJECTED", "alarm": None}
        if source_class == "D" and before == "HOLD" and target == "RUN" and not event.get("predicate"):
            return {"applied": False, "kind": "REJECTED", "alarm": None}
        if source_class == "P":
            per_session, per_scenario = self.p_limits
            if self.p_session.get(session, 0) >= per_session or self.p_total >= per_scenario:
                alarm = None if self.p_alarmed else "P_BUDGET_EXHAUSTED"
                self.p_alarmed = True
                return {"applied": False, "kind": "FLAG", "alarm": alarm}
            self.p_session[session] = self.p_session.get(session, 0) + 1
            self.p_total += 1
        self.scopes[scope] = target
        self.transitions.append((scope, before, target, source_class))
        self._audit_transition(scope, before, target, source_class)
        return {"applied": True, "kind": "OK", "alarm": None}

    def _audit_transition(self, scope, before, target, source):
        if before in TERMINAL:
            self.violations.append("left terminal state %s on %s" % (before, scope))
        if source == "P" and RANK[target] < RANK[before]:
            self.violations.append("P lowered restriction on %s" % scope)
        if source == "P" and target == "TRIP":
            self.violations.append("TRIP from P on %s" % scope)

    # ---- counters and tier floors (one-way) ----
    def debit(self, key, amount, session=None, counters=("period", "session")):
        """Add a non-negative amount. Negative or non-numeric amounts are refused."""
        if isinstance(amount, bool) or not isinstance(amount, (int, float)) or amount < 0:
            return False
        targets = []
        if "period" in counters:
            targets.append(self.counters)
        if session is not None and ("session" in counters or "step" in counters):
            targets.append(self.session_counters.setdefault(session, Counters()))
        for bag in targets:
            before = bag.get(key)
            bag.add(key, amount)
            if bag.get(key) < before:
                self.violations.append("counter %s decreased" % key)
        return True

    def session_snapshot(self, session):
        bag = self.session_counters.get(session)
        return bag.snapshot() if bag else {}

    def tier_floor(self, session):
        return self.tier_floors.get(session, 0)

    def raise_tier_floor(self, session, by=1):
        if isinstance(by, bool) or not isinstance(by, int) or by <= 0:
            return False
        before = self.tier_floors.get(session, 0)
        self.tier_floors[session] = before + by
        if self.tier_floors[session] < before:
            self.violations.append("tier floor decreased")
        return True

    def invariants_ok(self):
        return not self.violations
