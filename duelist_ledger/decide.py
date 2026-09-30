"""decide(): the only authorizer. Pure, deterministic, replayable.

In plain words: given one proposed action and a snapshot of everything relevant (the plan the
agent committed to, trust labels, counters, scope states), decide() says ALLOW, ESCROW, HOLD,
DENY or TRIP, with the reason codes. It reads no files, no clock and no randomness, so anyone
can re-run it later on the logged inputs and must get the same answer.

Rule order (spec sec. 4): the first TRIP rule found is final, before DECLARE too (then the
declaration is null, so T1/T2 fire ahead of H1). Otherwise every HOLD reason is collected and
the first one in RULE_ORDER is the primary. No reasons -> ALLOW (R0/R1) or ESCROW (R2/R3).

failing_slot is the slot named by the first reason, in rule order, that names one: H2 names the
first guarded slot whose value is pinned nowhere in the declaration; H3, H4 and H9 name their
guarded slot; H8 names the dest_slot; T1, T2, H1, S0, H5_* and H6 name none.
"""

import re

from .budget import compute_tier
from .policy import dest_class, domain_of

RULE_ORDER = (
    "H1_NO_DECLARATION", "H2_NOT_DECLARED", "S0_SCOPE_HELD", "H3_PINNED_MISMATCH",
    "H4_TAINTED_GUARDED", "H9_VERBATIM_SELECTION", "H5_BUDGET", "H5_BUDGET_SESSION",
    "H5_FUSE", "H6_PERSIST_AFTER_TAINT", "H8_FLOW",
)
STRICT_CODES = ("H3_PINNED_MISMATCH", "H4_TAINTED_GUARDED", "H8_FLOW")
SESSION_CODES = ("H5_BUDGET_SESSION", "H5_FUSE")
ESCROW_REVS = ("R2", "R3")


# ---- small pure helpers (also used by the gateway at release time) -------------------------

def integrity(label):
    if isinstance(label, dict):
        val = label.get("integrity", 0)
        if isinstance(val, int) and not isinstance(val, bool):
            return val
    return 0


def is_tainted(label):
    return integrity(label) < 2


def strings_in(value):
    """Every string inside a value (lists and dicts walked in a fixed order)."""
    if isinstance(value, str):
        return [value]
    out = []
    if isinstance(value, (list, tuple)):
        for item in value:
            out.extend(strings_in(item))
    elif isinstance(value, dict):
        for key in sorted(value, key=str):
            out.extend(strings_in(value[key]))
    return out


def normalize_path(text):
    text = text.replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    return text.lstrip("/")


def as_number(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        try:
            num = float(value.strip())
        except ValueError:
            return None
        return int(num) if num.is_integer() else num
    return None


def member(value, allowed):
    """value is in allowed (numbers compare by value, so 250 == 250.0 == "250")."""
    if not isinstance(allowed, (list, tuple)):
        allowed = [allowed]
    num = as_number(value)
    for item in allowed:
        if item == value:
            return True
        other = as_number(item)
        if num is not None and other is not None and num == other:
            return True
    return False


def canary_hits(text, canaries):
    """The canary records whose token appears in text (token must end at a word boundary)."""
    if not isinstance(text, str) or not text:
        return []
    hits = []
    for canary in sorted(canaries or [], key=lambda c: str(c.get("token"))):
        token = canary.get("token")
        if isinstance(token, str) and token and re.search(re.escape(token) + r"(?![A-Za-z0-9_])", text):
            hits.append(canary)
    return hits


def destination(sink, args):
    """Where an action sends data: the dest_slot value, or memory:<key> for persist_memory."""
    if not sink:
        return None
    if sink.get("sink_class") == "PERSIST_MEMORY":
        key = (args.get("key") or {}).get("value")
        return "memory:%s" % key
    slot = sink.get("dest_slot")
    if slot and slot in args:
        val = args[slot].get("value")
        return val if isinstance(val, str) else str(val)
    return None


def canary_violation(sink, args, payload_text, canaries):
    """First canary found in the payload whose audience does not include the destination."""
    dest = destination(sink, args)
    if dest is None:
        return None
    for canary in canary_hits(payload_text, canaries):
        if dest not in (canary.get("audience") or []):
            return canary.get("token")
    return None


def compute_debits(sink, args, step_id=None):
    """What an ALLOW/ESCROW of this action adds to the counters (never reversed)."""
    debits = []
    cls = sink.get("sink_class") if sink else None
    if cls == "EXTERNAL_SEND":
        to = (args.get("to") or {}).get("value")
        debits.append({"key": "send:%s" % (domain_of(to) or str(to)), "amount": 1,
                       "counters": ["period", "session"]})
    elif cls == "PAYMENT":
        amt = as_number((args.get("amount") or {}).get("value"))
        amt = amt if amt is not None and amt >= 0 else 0
        debits.append({"key": "money", "amount": amt, "counters": ["period", "session"]})
    if step_id is not None:
        debits.append({"key": "step:%s" % step_id, "amount": 1, "counters": ["step"]})
    return debits


def _ceiling(key, budgets):
    if key == "money":
        return budgets.get("money_per_period")
    if key.startswith("send:"):
        return budgets.get("send_per_domain_per_period")
    return None


# ---- decide ---------------------------------------------------------------------------------

def decide(inputs):
    """The decision for one proposal. See module docstring; inputs are listed in spec sec. 4."""
    mode = inputs.get("mode") or "V2"
    policy = inputs.get("policy") or {}
    sinks = inputs.get("sinks") or {}
    registries = inputs.get("registries") or {}
    prop = inputs.get("proposal") or {}
    tool = prop.get("tool")
    sink = sinks.get(tool) if isinstance(tool, str) else None
    args = prop.get("args") or {}
    ctx = inputs.get("context_label") or {"integrity": 0, "assets": [], "origins": []}
    payload_label = prop.get("payload_label") or {"integrity": 3, "assets": [], "origins": []}
    payload_text = prop.get("payload_text") or ""
    rules = inputs.get("rules_enabled") or {}
    session_scope = "L1:session:%s" % (inputs.get("session") or "")

    def value(slot):
        arg = args.get(slot)
        return arg.get("value") if isinstance(arg, dict) else None

    def label(slot):
        arg = args.get(slot)
        return arg.get("label") if isinstance(arg, dict) and arg.get("label") else ctx

    decl = inputs.get("declaration")
    step = None
    if isinstance(decl, dict) and prop.get("step_id") is not None:
        for candidate in decl.get("steps") or []:
            if candidate.get("step_id") == prop.get("step_id"):
                step = candidate
                break
    step_ok = step is not None and step.get("tool") == tool

    debits = compute_debits(sink, args, step.get("step_id") if step_ok else None)
    counters = inputs.get("counters") or {}
    session_counters = inputs.get("session_counters") or {}
    amount = None
    if sink and sink.get("sink_class") == "PAYMENT":
        amount = next((d["amount"] for d in debits if d["key"] == "money"), 0)
    tier = compute_tier(sink.get("base_tier", 0) if sink else 0,
                        bool(sink and sink.get("persistent")), amount, counters.get("money", 0),
                        policy.get("tier3_money"), inputs.get("tier_floor", 0),
                        money_band=(mode != "A4"))

    def result(outcome, details):
        codes = []
        for d in details:
            if d["code"] not in codes:
                codes.append(d["code"])
        first = details[0] if details else None
        slotted = next((d for d in details if d.get("slot")), None)
        return {
            "outcome": outcome, "reasons": codes,
            "primary": first["code"] if first else None,
            "scope": first["scope"] if first else "L0",
            "held_scope": first["held"] if first else None,
            "tier": tier,
            "failing_slot": slotted["slot"] if slotted else None,
            "failing_tainted": bool(slotted["tainted"]) if slotted else False,
            "debits": debits,
            "details": details,
        }

    # ---- T-rules: the first one found is final. T1 and T2 name no slot. ----
    prefixes = policy.get("house_prefixes") or []
    for slot in sorted(args):
        for text in strings_in(value(slot)):
            norm = normalize_path(text)
            if any(norm.startswith(p) for p in prefixes):
                return result("TRIP", [{"code": "T1_HOUSE", "scope": "L1", "held": session_scope,
                                        "slot": None, "tainted": False, "arg": slot}])
    token = canary_violation(sink, args, payload_text, inputs.get("canaries") or [])
    if token is not None:
        return result("TRIP", [{"code": "T2_CANARY", "scope": "L1", "held": session_scope,
                                "slot": None, "tainted": False, "token": token}])

    # ---- H-rules: collect all ----
    found = []

    def add(code, scope, held, slot=None, tainted=False):
        found.append({"code": code, "scope": scope, "held": held, "slot": slot, "tainted": bool(tainted)})

    item_scope = "L0:item"
    if not isinstance(decl, dict):
        add("H1_NO_DECLARATION", "L0", item_scope)
    elif not step_ok or step.get("used", 0) >= step.get("max_calls", 1):
        pinned_anywhere = []
        for candidate in decl.get("steps") or []:
            for vals in (candidate.get("pinned") or {}).values():
                pinned_anywhere.extend(vals if isinstance(vals, (list, tuple)) else [vals])
        h2_slot = next((sl for sl in ((sink or {}).get("guarded") or [])
                        if sl in args and not member(value(sl), pinned_anywhere)), None)
        add("H2_NOT_DECLARED", "L0", item_scope, h2_slot, is_tainted(label(h2_slot)) if h2_slot else False)

    rev = sink.get("rev") if sink else None
    if rev in ESCROW_REVS:
        states = inputs.get("scope_states") or {}
        for name in ("L3:org", "L2:agent->gate", "L2:gate->world:%s" % sink.get("sink_class")):
            if states.get(name, "RUN") != "RUN":
                add("S0_SCOPE_HELD", name.split(":", 1)[0], name)
                break

    if step_ok and sink:
        pinned = step.get("pinned") or {}
        free = step.get("free_guarded") or {}
        for slot in sink.get("guarded") or []:
            val, tainted = value(slot), is_tainted(label(slot))
            if slot in pinned:
                if not member(val, pinned[slot]):
                    add("H3_PINNED_MISMATCH", "L0", item_scope, slot, tainted)
                continue
            if slot not in free:
                continue
            spec = free[slot]
            if isinstance(spec, dict):
                limit, num = as_number(spec.get("max")), as_number(val)
                ok = limit is not None and num is not None and num <= limit
                registry = None
            else:
                registry = registries.get(spec) or []
                ok = member(val, registry)
            if not ok:
                if not tainted:
                    add("H3_PINNED_MISMATCH", "L0", item_scope, slot, False)
                elif mode != "A1":
                    add("H4_TAINTED_GUARDED", "L0", item_scope, slot, True)
            elif registry is not None and rules.get("R1"):
                for entry in inputs.get("untrusted_strings") or []:
                    if val in (entry.get("strings") or []) and val != entry.get("sender"):
                        add("H9_VERBATIM_SELECTION", "L0", item_scope, slot, tainted)
                        break

    if mode != "A4" and sink:
        budgets = policy.get("budgets") or {}
        share = budgets.get("session_share", 1)
        for debit in debits:
            ceiling = _ceiling(debit["key"], budgets)
            if ceiling is None:
                continue
            if counters.get(debit["key"], 0) + debit["amount"] > ceiling:
                add("H5_BUDGET", "L3", "L3:budget:%s" % debit["key"])
        for debit in debits:
            ceiling = _ceiling(debit["key"], budgets)
            if ceiling is None:
                continue
            if session_counters.get(debit["key"], 0) + debit["amount"] > share * ceiling:
                add("H5_BUDGET_SESSION", "L1", session_scope)
                break
        fuse_cfg = (policy.get("fuse") or {}).get(sink.get("sink_class"))
        if fuse_cfg:
            heat = ((inputs.get("fuse_state") or {}).get(sink.get("sink_class")) or {}).get("heat", 0)
            if heat > fuse_cfg.get("threshold", float("inf")):
                add("H5_FUSE", "L1", session_scope)

    if sink and sink.get("persistent") and is_tainted(payload_label):
        add("H6_PERSIST_AFTER_TAINT", "L0", item_scope)

    dest_slot = sink.get("dest_slot") if sink else None
    if dest_slot and dest_slot in args:
        flows = policy.get("asset_flows") or {}
        klass = dest_class(value(dest_slot), policy, registries)
        for asset in payload_label.get("assets") or []:
            if asset in flows and klass not in flows[asset]:
                add("H8_FLOW", "L0", item_scope, dest_slot, is_tainted(label(dest_slot)))
                break

    if not found:
        return result("ESCROW" if rev in ESCROW_REVS else "ALLOW", [])

    found.sort(key=lambda d: RULE_ORDER.index(d["code"]))
    decision = result("HOLD", found)
    if mode == "A7" and decision["failing_tainted"] and any(c in STRICT_CODES for c in decision["reasons"]):
        decision["outcome"] = "DENY"
    return decision
