"""Shared test helpers: config, a decide() input builder, and a tiny scenario builder.

In plain words: lets each test describe just the part of a situation it cares about.
"""

import copy
import os
import shutil
import tempfile

from duelist_ledger import labels as L
from duelist_ledger.harness import run_one
from duelist_ledger.policy import load_config

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POLICY, SINKS = load_config(os.path.join(ROOT, "config"))
PRINCIPAL = "principal@home.invalid"

P_LABEL = L.make(L.PRINCIPAL)
U_LABEL = L.make(L.UNTRUSTED, [], ["inbox:m1"])
I_LABEL = L.make(L.INTERNAL, [], ["file:docs/a.txt"])


def arg(value, label=None):
    return {"value": value, "label": copy.deepcopy(label or P_LABEL)}


def step(step_id, tool, pinned=None, free=None, max_calls=1, used=0):
    return {"step_id": step_id, "tool": tool, "pinned": pinned or {}, "free_guarded": free or {},
            "max_calls": max_calls, "used": used}


def inputs(tool="send_email", args=None, steps=None, step_id="s1", mode="V2", payload_label=None,
           payload_text="", context=None, **extra):
    """A complete, benign decide() input; override any part with keyword arguments."""
    if args is None:
        args = {"to": arg(PRINCIPAL), "body": arg("hi")}
    if steps is None:
        steps = [step("s1", tool, pinned={"to": [PRINCIPAL]} if tool == "send_email" else {})]
    base = {
        "mode": mode, "policy": copy.deepcopy(POLICY), "sinks": copy.deepcopy(SINKS),
        "registries": {"contacts": ["bob@partner.invalid"], "vendors": ["v-acme"]},
        "canaries": [], "session": "s1",
        "declaration": {"declared_before_taint": True, "steps": steps},
        "proposal": {"seq": 1, "step_id": step_id, "tool": tool, "args": args,
                     "payload_label": payload_label or copy.deepcopy(P_LABEL), "payload_text": payload_text},
        "context_label": context or copy.deepcopy(P_LABEL), "session_tainted": False,
        "scope_states": {"L3:org": "RUN", "L2:agent->gate": "RUN"},
        "counters": {}, "session_counters": {}, "fuse_state": {}, "tier_floor": 0, "t": 1,
        "untrusted_strings": [], "rules_enabled": {"R1": False},
    }
    base.update(extra)
    return base


ENVELOPE = {
    "allowed_tools": ["read_inbox", "read_file", "fetch_web", "read_memory", "write_workspace",
                      "send_email", "pay", "persist_memory", "schedule"],
    "destinations": {"send_email.to": [PRINCIPAL, "registry:contacts"], "pay.payee": ["registry:vendors"],
                     "read_file.path": ["docs/q3.txt", "notes/tmp.txt"],
                     "fetch_web.url": ["https://docs.example.invalid/p1"],
                     "read_memory.key": ["k"], "persist_memory.key": ["k"],
                     "write_workspace.path": ["notes/tmp.txt"],
                     "schedule.action": ["remind"], "schedule.target": [PRINCIPAL]},
    "max_calls": {"read_inbox": 3, "read_file": 3, "send_email": 3, "pay": 2, "persist_memory": 2,
                  "schedule": 2, "write_workspace": 2, "fetch_web": 30, "read_memory": 2},
    "max_money": 500,
}


def world(inbox=None, **extra):
    w = {"registries": {"contacts": ["bob@partner.invalid"], "vendors": ["v-acme"]},
         "files": {"docs/q3.txt": {"content": "FACT-1", "label": "INTERNAL", "assets": ["finance"]}},
         "inbox": inbox if inbox is not None else [{"id": "m1", "from": "bob@partner.invalid", "body": "FACT-2", "directives": []}],
         "canaries": [{"token": "CANARY-01", "audience": [PRINCIPAL]}]}
    w.update(extra)
    return w


def session(steps, script, kind="compliant", identity="agent-A", **extra):
    agent = {"identity": identity, "kind": kind, "declaration": {"steps": steps}, "script": script}
    agent.update(extra)
    return {"task": "test task", "agent": agent}


def scenario(sessions, **extra):
    sc = {"id": "T", "title": "test", "category": "benign", "variants": 1, "world": world(),
          "envelope": copy.deepcopy(ENVELOPE), "principal_policy": {}, "sessions": sessions,
          "goal": [], "adversary_goal": []}
    sc.update(extra)
    return sc


def run(sc, mode="V2", variant=0, inspect=None):
    tmp = tempfile.mkdtemp(prefix="dlt")
    try:
        return run_one(sc, mode, variant, os.path.join(tmp, "r"), POLICY, SINKS, inspect=inspect)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def call(step_id, tool, **args):
    return {"op": "call", "step_id": step_id, "tool": tool, "args": args}


SEND_P = {"step_id": "s2", "tool": "send_email", "pinned": {"to": [PRINCIPAL]}, "max_calls": 1}
READ_INBOX = {"step_id": "s1", "tool": "read_inbox", "pinned": {}, "max_calls": 1}
