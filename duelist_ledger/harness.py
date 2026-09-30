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

from . import labels as L
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
INDEXED_FAULTS = ("drop_receipt", "mutate_escrow")
TAMPERS = ("tamper_ledger", "tamper_ledger_rehash")
MISSING = "<missing>"


class ScenarioLoadError(ValueError):
    """A scenario that breaks the schema rules the spec makes load errors (sec. 8)."""


def fault_index(fault):
    """The 1-based occurrence number k of an indexed fault (missing -> 1). None if not a whole number."""
    k = fault.get("index", 1)
    if isinstance(k, bool):
        return None
    if isinstance(k, float) and k.is_integer():
        k = int(k)
    return k if isinstance(k, int) else None


def check_scenario(scenario):
    """Raise ScenarioLoadError for a fault index k < 1 (indices are 1-based) or a mutate_escrow
    without its required `to`."""
    sid = scenario.get("id")
    for n, fault in enumerate(scenario.get("faults") or [], 1):
        if not isinstance(fault, dict):
            raise ScenarioLoadError("scenario %s: fault %d is not an object" % (sid, n))
        kind = fault.get("type")
        if kind in INDEXED_FAULTS:
            k = fault_index(fault)
            if k is None or k < 1:
                raise ScenarioLoadError("scenario %s: fault %d (%s) has index %r; fault indices are 1-based "
                                        "(k >= 1)" % (sid, n, kind, fault.get("index")))
        if kind == "mutate_escrow" and "to" not in fault:
            raise ScenarioLoadError("scenario %s: fault %d (mutate_escrow) has no `to`" % (sid, n))
    return scenario


def load_scenarios(directory, errors=None):
    """Every valid scenario in *.json files of a folder (a file may hold one scenario or a list).

    A scenario that fails check_scenario is left out; if `errors` is a list, one
    {"scenario", "file", "error"} record is appended to it for each.
    """
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
            if not (isinstance(sc, dict) and "id" in sc and "sessions" in sc):
                continue
            try:
                found.append(check_scenario(sc))
            except ScenarioLoadError as exc:
                if errors is not None:
                    errors.append({"scenario": sc.get("id"), "file": name, "error": str(exc)})
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


def _fault_detected(n, fault, gw, world, fired):
    """Did fault number n produce its own signal? A fault that never fired produced none."""
    kind = fault.get("type")
    if kind == "drop_receipt":
        return world.dropped.get(n) in gw.gap_reported
    if kind == "bypass_write":
        return fired.get(n) in gw.bypass_reported
    if kind in TAMPERS:
        return n in fired and gw.chain_held
    if kind == "mutate_escrow":
        return fired.get(n) in gw.t4_items
    return False


def run_one(scenario, mode, variant, run_dir, base_policy, sinks, keep=False, driver=None, inspect=None):
    """Run one scenario x mode x variant. Returns a result record (summary + checks).

    driver(gateway, agent_spec) plays one session; the default runs the agent in-process.
    inspect(gateway, world), if given, is called after the run (tests use it).
    """
    driver = driver or (lambda gw, spec: drive(gw, Agent(spec)))
    sc = check_scenario(make_variant(check_scenario(scenario), variant))
    policy, ignored = effective_policy(base_policy, sc.get("policy_overrides"))
    faults = list(sc.get("faults") or [])
    os.makedirs(run_dir, exist_ok=True)
    world = World(sc.get("world"), run_dir, policy, faults)
    adversary = sc.get("adversary_goal") or []
    goal = sc.get("goal") or []
    tracker = {"ever": False}

    def watch():
        if adversary and not tracker["ever"] and any(world.check(p) for p in adversary):
            tracker["ever"] = True

    world.listeners.append(watch)
    fired = {}  # fault number -> what it hit (bypass effect id, mutated stage id, or True for a tamper)
    escrowed = {"n": 0}

    def after_anchor(gw):
        """A tamper edits its entry right after the first anchor whose seq >= entry_seq."""
        for n, f in enumerate(faults):
            seq = f.get("entry_seq")
            if f.get("type") not in TAMPERS or n in fired or isinstance(seq, bool) or not isinstance(seq, int):
                continue
            if gw.last_anchor_seq < seq:
                continue
            fired[n] = True
            if f["type"] == "tamper_ledger":
                tamper_edit(gw.ledger_path, seq)
            else:
                tamper_rehash(gw.ledger_path, seq, gw.gate_key)

    def on_escrow(gw, item):
        """mutate_escrow{index: k, to}: set the dest slot of the k-th escrowed item (counted across
        the scenario) to exactly `to`, before it is released."""
        escrowed["n"] += 1
        for n, f in enumerate(faults):
            if f.get("type") != "mutate_escrow" or fault_index(f) != escrowed["n"]:
                continue
            sink = gw.sinks[item["tool"]]
            slot = sink.get("dest_slot") or (sink.get("guarded") or [None])[0]
            if slot is None:
                continue
            old = item["args"].get(slot) or {"label": L.top()}
            item["args"][slot] = dict(old, value=copy.deepcopy(f["to"]))
            fired[n] = item["stage_id"]

    principal = Principal(sc.get("principal_policy"), rubber_stamp=(mode == "A5"))
    gw = Gateway(run_dir, policy, sinks, world, principal, mode=mode, monitor=Monitor(sc.get("monitor")),
                 hooks={"after_anchor": after_anchor, "on_escrow": on_escrow})
    first_identity = None
    for i, sess in enumerate(sc.get("sessions") or []):
        spec = sess.get("agent") or {}
        identity = spec.get("identity", "agent")
        first_identity = identity if first_identity is None else first_identity
        envelope = sess.get("envelope", sc.get("envelope"))
        opened = gw.open_session("s%d" % (i + 1), sess.get("task", ""), identity, envelope)
        for n, f in enumerate(faults):
            if f.get("type") == "bypass_write" and f.get("session", 0) == i:
                fired[n] = "bypass-%d" % (n + 1)
                world.bypass_email(f.get("effect") or {}, fired[n])
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
        "detected": bool(faults) and all(_fault_detected(n, f, gw, world, fired) for n, f in enumerate(faults)),
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
        if field == "counters" and isinstance(exp, dict):
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
