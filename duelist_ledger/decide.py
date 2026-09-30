"""decide(): the only authorizer. Pure, deterministic, replayable (contract v0.3, spec sec. 4).

In plain words: given one proposed action and a snapshot of everything relevant (the plan the
agent committed to, trust labels, counters, scope states), decide() says ALLOW, ESCROW, HOLD,
DENY or TRIP, with the reason codes. It reads no files, no clock and no randomness, so anyone
can re-run it later on the logged inputs and must get the same answer.

Rule order: the first T-rule found is final, before DECLARE too (then the declaration is null,
so T1/T2 fire ahead of H1). Otherwise every H-reason is collected. If the reasons include H3 or
H4 with failing_tainted true and the step is not attended (every step is attended in A7), the
outcome is DENY with no resolver (the hard deny). Otherwise HOLD. The primary is the first
reason, in rule-table order, of the first group present in the fixed order S0, session, action
(sec. 5.1). No reasons -> ALLOW (R0/R1) or ESCROW (R2/R3).

Typed slots (sec. 3.3): T1 scans path-typed values only, never text. `{"max": m}` applies to
amount-typed slots only. Path-typed pinned values compare as strings.

Undeclared proposals (an unknown tool, or an unresolvable handle; sec. 3.7): only four rules run,
T1 over the literal argument values, T2 over the literal content (a null destination is in no
audience), then H1 before DECLARE or H2 after it. Tier 0, no debits, never a mixed-reason HOLD.

Derived slots (sec. 3.5): the value passes when it equals the sender recorded by the world for a
value that a call of the named read step delivered to this session; otherwise H3, with
failing_tainted from the argument.

failing_slot is the slot named by the first reason, in rule-table order, that names one: H2
names the first guarded slot whose value is pinned nowhere in the declaration (for an undeclared
proposal, the first slot whose handle is unresolvable, and none for an unknown tool); H3, H4 and
H9 name their guarded slot; H8 names the dest_slot; T1, T2, H1, S0, H5_* and H6 name none.
"""

import re

from .budget import compute_tier
from .policy import dest_class, domain_of, numeric_slots, slot_type

RULE_ORDER = (
    "H1_NO_DECLARATION", "H2_NOT_DECLARED", "S0_SCOPE_HELD", "H3_PINNED_MISMATCH",
    "H4_TAINTED_GUARDED", "H9_VERBATIM_SELECTION", "H5_BUDGET", "H5_BUDGET_SESSION",
    "H5_FUSE", "H6_PERSIST_AFTER_TAINT", "H8_FLOW",
)
HARD_DENY_CODES = ("H3_PINNED_MISMATCH", "H4_TAINTED_GUARDED")
SESSION_CODES = ("H5_BUDGET_SESSION", "H5_FUSE")
S0 = "S0_SCOPE_HELD"
ESCROW_REVS = ("R2", "R3")


def group_of(code):
    """The resolver group of a reason (sec. 5.1): S0, session or action."""
    if code == S0:
        return "S0"
    return "session" if code in SESSION_CODES else "action"


GROUP_RANK = {"S0": 0, "session": 1, "action": 2}


# ---- small pure helpers (also used by the gateway and the world) ----------------------------

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


def is_house_path(text, prefixes):
    return isinstance(text, str) and any(normalize_path(text).startswith(p) for p in prefixes or [])


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


def pinned_member(value, allowed, stype):
    """Membership in a pinned list: path-typed values compare as strings (sec. 3.3)."""
    if stype == "path":
        allowed = allowed if isinstance(allowed, (list, tuple)) else [allowed]
        return value is not None and any(v is not None and str(value) == str(v) for v in allowed)
    return member(value, allowed)


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
        return None if key is None else "memory:%s" % key
    slot = sink.get("dest_slot")
    if slot and slot in args:
        val = args[slot].get("value")
        return None if val is None else (val if isinstance(val, str) else str(val))
    return None


def canary_violation(sink, args, payload_text, canaries, dest=None, dest_known=False):
    """First canary in the payload whose audience does not include the destination.

    With no dest_slot (write_workspace, reads) there is no destination and T2 is not checked.
    A null destination (the dest slot missing, or an undeclared proposal whose dest slot is not a
    literal) is in no audience (sec. 4). Callers that already know the destination pass
    dest_known=True with `dest`.
    """
    if not dest_known:
        if not sink or not (sink.get("dest_slot") or sink.get("sink_class") == "PERSIST_MEMORY"):
            return None
        dest = destination(sink, args)
    for canary in canary_hits(payload_text, canaries):
        if dest is None or dest not in (canary.get("audience") or []):
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


def step_attended(step, mode):
    """attended: true on the step, or every step in mode A7 (sec. 3.5, 12)."""
    return mode == "A7" or bool(isinstance(step, dict) and step.get("attended") is True)


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
    canaries = inputs.get("canaries") or []
    session_scope = "L1:session:%s" % (inputs.get("session") or "")
    prefixes = policy.get("house_prefixes") or []

    def value(slot):
        arg = args.get(slot)
        return arg.get("value") if isinstance(arg, dict) else None

    def label(slot):
        arg = args.get(slot)
        return arg.get("label") if isinstance(arg, dict) and arg.get("label") else ctx

    def is_literal(slot):
        arg = args.get(slot)
        return isinstance(arg, dict) and "handle" not in arg

    decl = inputs.get("declaration")
    declared = isinstance(decl, dict)
    step = None
    if declared and prop.get("step_id") is not None:
        for candidate in decl.get("steps") or []:
            if candidate.get("step_id") == prop.get("step_id"):
                step = candidate
                break
    step_ok = step is not None and step.get("tool") == tool
    undeclared = sink is None or any(isinstance(a, dict) and a.get("unresolvable") for a in args.values())

    debits = [] if undeclared else compute_debits(sink, args, step.get("step_id") if step_ok else None)
    counters = inputs.get("counters") or {}
    session_counters = inputs.get("session_counters") or {}
    if undeclared:
        tier = 0
    else:
        amount = None
        if sink.get("sink_class") == "PAYMENT":
            amount = next((d["amount"] for d in debits if d["key"] == "money"), 0)
        tier = compute_tier(sink.get("base_tier", 0), bool(sink.get("persistent")), amount,
                            counters.get("money", 0), policy.get("tier3_money"), inputs.get("tier_floor", 0),
                            money_band=(mode != "A4"))

    def result(outcome, details):
        codes = []
        for d in details:
            if d["code"] not in codes:
                codes.append(d["code"])
        # primary: the first reason, in rule-table order, of the first group in the order S0,
        # session, action (sec. 4, 5.1). details arrive sorted in rule-table order.
        first = min(details, key=lambda d: GROUP_RANK[group_of(d["code"])]) if details else None
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
            "undeclared": undeclared,
        }

    def trip(code, arg=None, token=None):
        d = {"code": code, "scope": "L1", "held": session_scope, "slot": None, "tainted": False}
        if arg is not None:
            d["arg"] = arg
        if token is not None:
            d["token"] = token
        return result("TRIP", [d])

    # ---- undeclared proposals (sec. 3.7, 4): four rules only ----
    if undeclared:
        literal_slots = [s for s in sorted(args) if is_literal(s)]
        for slot in literal_slots:
            if sink is not None and slot_type(sink, slot) != "path":
                continue
            if any(is_house_path(text, prefixes) for text in strings_in(value(slot))):
                return trip("T1_HOUSE", arg=slot)
        content_slots = [s for s in literal_slots if sink is None or s in (sink.get("content") or [])]
        text = "\n".join(v if isinstance(v, str) else str(v) for v in
                         (value(s) for s in content_slots) if v is not None)
        dest, has_dest = None, True
        if sink is not None:
            dslot = "key" if sink.get("sink_class") == "PERSIST_MEMORY" else sink.get("dest_slot")
            has_dest = bool(dslot)  # a sink with no destination (write_workspace, reads) is not scanned
            if dslot and dslot in args and is_literal(dslot):
                dest = destination(sink, args)
        token = canary_violation(sink, args, text, canaries, dest=dest, dest_known=True) if has_dest else None
        if token is not None:
            return trip("T2_CANARY", token=token)
        if not declared:
            return result("HOLD", [{"code": "H1_NO_DECLARATION", "scope": "L0", "held": "L0:item",
                                    "slot": None, "tainted": False}])
        h2_slot = None
        if sink is not None:
            h2_slot = next((s for s in (sink.get("guarded") or [])
                            if isinstance(args.get(s), dict) and args[s].get("unresolvable")), None)
        return result("HOLD", [{"code": "H2_NOT_DECLARED", "scope": "L0", "held": "L0:item",
                                "slot": h2_slot, "tainted": is_tainted(label(h2_slot)) if h2_slot else False}])

    # ---- T-rules: the first one found is final. T1 and T2 name no slot. ----
    for slot in sorted(args):
        if slot_type(sink, slot) != "path":
            continue  # text-typed values are never scanned (sec. 3.3, A4.4)
        if any(is_house_path(text, prefixes) for text in strings_in(value(slot))):
            return trip("T1_HOUSE", arg=slot)
    token = canary_violation(sink, args, payload_text, canaries)
    if token is not None:
        return trip("T2_CANARY", token=token)

    # ---- H-rules: collect all ----
    found = []

    def add(code, scope, held, slot=None, tainted=False):
        found.append({"code": code, "scope": scope, "held": held, "slot": slot, "tainted": bool(tainted)})

    item_scope = "L0:item"
    if not declared:
        add("H1_NO_DECLARATION", "L0", item_scope)
    elif not step_ok or step.get("used", 0) >= step.get("max_calls", 1):
        pinned_anywhere = []
        for candidate in decl.get("steps") or []:
            for vals in (candidate.get("pinned") or {}).values():
                pinned_anywhere.extend(vals if isinstance(vals, (list, tuple)) else [vals])
        h2_slot = next((sl for sl in (sink.get("guarded") or [])
                        if sl in args and not member(value(sl), pinned_anywhere)), None)
        add("H2_NOT_DECLARED", "L0", item_scope, h2_slot, is_tainted(label(h2_slot)) if h2_slot else False)

    rev = sink.get("rev")
    if rev in ESCROW_REVS:
        states = inputs.get("scope_states") or {}
        for name in ("L3:org", "L2:agent->gate", "L2:gate->world:%s" % sink.get("sink_class")):
            if states.get(name, "RUN") != "RUN":
                add(S0, name.split(":", 1)[0], name)
                break

    if step_ok:
        pinned = step.get("pinned") or {}
        free = step.get("free_guarded") or {}
        derived = step.get("derived") or {}
        senders = inputs.get("delivered_senders") or {}
        for slot in sink.get("guarded") or []:
            val, tainted = value(slot), is_tainted(label(slot))
            if slot in pinned:
                if not pinned_member(val, pinned[slot], slot_type(sink, slot)):
                    add("H3_PINNED_MISMATCH", "L0", item_scope, slot, tainted)
                continue
            if slot in derived:
                spec = derived[slot] if isinstance(derived[slot], dict) else {}
                known = senders.get(str(spec.get("sender_of"))) or []
                if not (isinstance(val, str) and val in known):
                    add("H3_PINNED_MISMATCH", "L0", item_scope, slot, tainted)
                continue
            if slot not in free:
                continue
            spec = free[slot]
            if isinstance(spec, dict):
                limit, num = as_number(spec.get("max")), as_number(val)
                ok = slot in numeric_slots(sink) and limit is not None and num is not None and num <= limit
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

    if mode != "A4":
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

    if sink.get("persistent") and is_tainted(payload_label):
        add("H6_PERSIST_AFTER_TAINT", "L0", item_scope)

    dest_slot = sink.get("dest_slot")
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
    # The hard deny (sec. 4): a tainted H3/H4 on an unattended step has no resolver, in every
    # gated mode. A7 treats every step as attended, so there it stays a HOLD (repin only).
    if tainted_guard(found) and not step_attended(step if step_ok else None, mode):
        decision["outcome"] = "DENY"
    return decision


def tainted_guard(details):
    """True when the reasons include an H3 or H4 whose own argument is tainted (an H4 always is).
    This is the 'H3 or H4 with failing_tainted true' of sec. 4 and 5.1, read per reason."""
    return any(d["code"] in HARD_DENY_CODES and d.get("tainted") for d in details)
