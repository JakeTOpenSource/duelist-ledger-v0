"""The harness: loads scenarios, makes variants, runs every scenario x mode x variant.

In plain words: for each run it builds a fresh "house" (diary, witness, counters, strikes)
shared only by that scenario's sessions, a fresh simulated world, the scripted principal
and monitor, and plays each session's scripted agent against the gateway. It wires in the
fault hooks (dropped receipts, bypass writes, diary tampering, escrow mutation), then
collects the summary fields that the sealed expectations are compared against.
"""

import copy
import hashlib
import json
import os
import random
import re
import shutil

from .agents import Agent, drive
from .gateway import Gateway
from .ledger import tamper_edit, tamper_rehash, verify as verify_ledger
from .monitor import Monitor
from .policy import effective_policy
from .principal import Principal
from .reconcile import verify_receipts
from .replay import replay
from .world import World

MODES = ("V2", "A0", "A1", "A3", "A4", "A5", "A7")
STRICT_INVARIANT_MODES = ("V2", "A1", "A4", "A5", "A7", "R2")
MISSING = "<missing>"


def load_scenarios(directory):
    """Every scenario in *.json files of a folder (a file may hold one scenario or a list)."""
    found = []
    if not directory or not os.path.isdir(directory):
        return found
    for name in sorted(os.listdir(directory)):
        if not name.lower().endswith(".json"):
            continue
        path = os.path.join(directory, name)
        with open(path, encoding="utf-8-sig") as fh:
            data = json.load(fh)
        items = data if isinstance(data, list) else data.get("scenarios", [data]) if isinstance(data, dict) else []
        for sc in items:
            if isinstance(sc, dict) and "id" in sc and "sessions" in sc:
                found.append(sc)
    return found


def modes_for(scenario):
    extra = [m for m in (scenario.get("modes") or []) if m not in MODES]
    return list(MODES) + extra


def variant_count(scenario):
    n = scenario.get("variants", 1)
    return n if isinstance(n, int) and not isinstance(n, bool) and n > 0 else 1


def make_variant(scenario, v):
    """Variant v: '-v{v}' on every canary token everywhere, plus v distractor inbox messages."""
    sid = str(scenario.get("id"))
    listed = sorted({c.get("token") for c in ((scenario.get("world") or {}).get("canaries") or [])
                     if isinstance(c.get("token"), str) and c.get("token")}, key=len, reverse=True)
    alternatives = [re.escape(t) for t in listed] + [r"CANARY-[A-Za-z0-9_]+"]
    pattern = re.compile("(?:%s)(?![A-Za-z0-9_])" % "|".join(alternatives))
    suffix = "-v%d" % v

    def fix(x):
        if isinstance(x, str):
            return pattern.sub(lambda m: m.group(0) + suffix, x)
        if isinstance(x, list):
            return [fix(i) for i in x]
        if isinstance(x, dict):
            return {fix(k): fix(val) for k, val in x.items()}
        return x

    out = fix(copy.deepcopy(scenario))
    out["id"] = scenario.get("id")
    world = out.setdefault("world", {})
    inbox = world.setdefault("inbox", [])
    rng = random.Random(int(hashlib.sha256(sid.encode("utf-8")).hexdigest(), 16) + v)
    for k in range(v):
        pos = rng.randint(0, len(inbox))
        inbox.insert(pos, {"id": "d%d" % k, "from": "news@partner.invalid", "body": "", "directives": []})
    return out


def _num(v):
    return int(v) if isinstance(v, float) and v.is_integer() else v


def _fault_detected(fault, gw):
    kind = fault.get("type")
    codes = {(e["type"], e["code"]) for e in gw.events}
    if kind == "drop_receipt":
        return ("HOLD", "RECEIPT_GAP") in codes
    if kind == "bypass_write":
        return ("TRIP", "T3_BYPASS") in codes
    if kind in ("tamper_ledger", "tamper_ledger_rehash"):
        return gw.chain_held
    if kind == "mutate_escrow":
        return ("TRIP", "T4_ARGS_MISMATCH") in codes
    return False


def run_one(scenario, mode, variant, run_dir, base_policy, sinks, keep=False, driver=None, inspect=None):
    """Run one scenario x mode x variant. Returns a result record (summary + checks).

    driver(gateway, agent_spec) plays one session; the default runs the agent in-process.
    inspect(gateway, world), if given, is called after the run (tests use it).
    """
    driver = driver or (lambda gw, spec: drive(gw, Agent(spec)))
    sc = make_variant(scenario, variant)
    policy, ignored = effective_policy(base_policy, sc.get("policy_overrides"))
    faults = [f for f in (sc.get("faults") or []) if isinstance(f, dict)]
    os.makedirs(run_dir, exist_ok=True)
    world = World(sc.get("world"), run_dir, policy, faults)
    adversary = sc.get("adversary_goal") or []
    goal = sc.get("goal") or []
    tracker = {"ever": False}

    def watch():
        if adversary and not tracker["ever"] and any(world.check(p) for p in adversary):
            tracker["ever"] = True

    world.listeners.append(watch)
    tampers = [f for f in faults if f.get("type") in ("tamper_ledger", "tamper_ledger_rehash")]
    mutations = [f for f in faults if f.get("type") == "mutate_escrow"]
    applied = set()
    escrowed = {"n": 0}

    def after_anchor(gw):
        for i, f in enumerate(tampers):
            seq = f.get("entry_seq")
            if i in applied or not isinstance(seq, int) or gw.last_anchor_seq < seq:
                continue
            applied.add(i)
            if f["type"] == "tamper_ledger":
                tamper_edit(gw.ledger_path, seq)
            else:
                tamper_rehash(gw.ledger_path, seq, gw.gate_key)

    def on_escrow(gw, item):
        escrowed["n"] += 1
        for f in mutations:
            if max(int(f.get("index", 1)), 1) == escrowed["n"]:
                slot = gw.sinks[item["tool"]].get("dest_slot") or "to"
                if slot in item["args"]:
                    item["args"][slot] = dict(item["args"][slot], value="mutated@outside.invalid")

    principal = Principal(sc.get("principal_policy"), rubber_stamp=(mode == "A5"))
    gw = Gateway(run_dir, policy, sinks, world, principal, mode=mode, monitor=Monitor(sc.get("monitor")),
                 hooks={"after_anchor": after_anchor, "on_escrow": on_escrow})
    first_identity = None
    bypass_n = 0
    for i, sess in enumerate(sc.get("sessions") or []):
        spec = sess.get("agent") or {}
        identity = spec.get("identity", "agent")
        first_identity = identity if first_identity is None else first_identity
        envelope = sess.get("envelope", sc.get("envelope"))
        opened = gw.open_session("s%d" % (i + 1), sess.get("task", ""), identity, envelope)
        for f in faults:
            if f.get("type") == "bypass_write" and f.get("session", 0) == i:
                bypass_n += 1
                world.bypass_email(f.get("effect") or {}, "bypass-%d" % bypass_n)
        if opened:
            driver(gw, spec)
    gw.finish_scenario()
    gw.close()
    world.close()

    events = gw.events
    scoped = [e for e in events if e["type"] in ("HOLD", "TRIP")]
    xc = gw.cross_checks
    if "divergent" in xc:
        cross = "divergent"
    elif "consistent" in xc:
        cross = "consistent"
    else:
        cross = "no_narrative"
    summary = {
        "adversary_success": bool(adversary) and any(world.check(p) for p in adversary),
        "goal_met": all(world.check(p) for p in goal),
        "outcomes": list(gw.outcomes),
        "holds": [e["code"] for e in events if e["type"] == "HOLD"],
        "confirms": sum(1 for e in events if e["type"] == "CONFIRM"),
        "denies": [e["code"] for e in events if e["type"] == "DENY"],
        "trips": [e["code"] for e in events if e["type"] == "TRIP"],
        "scopes": [e["level"] for e in scoped],
        "scopes_full": [e["scope"] for e in scoped],
        "pre_classes": [c["pre_class"] for c in gw.cases.cases if c["pre_class"] != "none"],
        "strikes": gw.cases.strikes_of(first_identity),
        "counters": {k: _num(v) for k, v in sorted(gw.state.counters.snapshot().items()) if v},
        "detected": bool(faults) and all(_fault_detected(f, gw) for f in faults),
        "invariants_ok": gw.state.invariants_ok(),
    }
    if mode == "A3":
        summary["cross_check"] = cross
        summary["cross_checks"] = list(xc)
    result = {
        "scenario": scenario.get("id"), "title": scenario.get("title", ""),
        "category": scenario.get("category", ""), "mode": mode, "variant": variant,
        "summary": summary,
        "verify": verify_ledger(gw.ledger_path, gw.heads_path),
        "receipts_ok": verify_receipts(world.receipts_path)["ok"],
        "replay": replay(gw.ledger_path, gw.blobs_path),
        "invariant_violations": list(gw.state.violations),
        "adversary_ever": tracker["ever"],
        "has_adversary": bool(adversary), "has_goal": bool(goal),
        "proposals": gw.proposals, "latencies": gw.latencies,
        "alarms": list(gw.alarms), "ignored_overrides": ignored,
        "chain_detected_seq": gw.chain_detected_seq,
    }
    if inspect is not None:
        inspect(gw, world)
    if not keep:
        shutil.rmtree(run_dir, ignore_errors=True)
    return result


# ---- expectation comparison ------------------------------------------------------------------

def _same(a, b):
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b if isinstance(a, bool) and isinstance(b, bool) else a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return float(a) == float(b)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_same(x, y) for x, y in zip(a, b))
    if isinstance(a, dict) and isinstance(b, dict):
        return set(a) == set(b) and all(_same(a[k], b[k]) for k in a)
    return a == b


def compare(expected, summary):
    """Compare only the fields present in expected. Returns [(field, expected, actual)]."""
    out = []
    for field, exp in (expected or {}).items():
        if field == "scopes" and isinstance(exp, list):
            full = any(isinstance(x, str) and ":" in x for x in exp)
            act = summary.get("scopes_full" if full else "scopes", MISSING)
            ok = _same(exp, act)
        elif field == "counters" and isinstance(exp, dict):
            act = summary.get("counters", {})
            ok = all(_same(v, act.get(k, 0)) for k, v in exp.items())
        elif field == "cross_check":
            act = summary.get("cross_checks" if isinstance(exp, list) else "cross_check", MISSING)
            ok = _same(exp, act)
        else:
            act = summary.get(field, MISSING)
            ok = _same(exp, act)
        if not ok:
            out.append((field, exp, act))
    return out
