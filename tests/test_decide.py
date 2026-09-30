"""decide(): one test per rule code, mode effects, tier, rule order, and determinism."""

import copy
import json
import random
import unittest

from duelist_ledger import labels as L
from duelist_ledger.canon import canonical
from duelist_ledger.decide import decide

from tests.helpers import I_LABEL, P_LABEL, PRINCIPAL, U_LABEL, arg, inputs, step


def pay_inputs(amount=50, payee="v-acme", **kw):
    args = {"payee": arg(payee), "amount": arg(amount), "memo": arg("m")}
    steps = [step("s1", "pay", free={"payee": "vendors", "amount": {"max": 500}})]
    return inputs("pay", args=args, steps=steps, **kw)


class RuleTableTest(unittest.TestCase):
    def test_allow_and_escrow(self):
        self.assertEqual(decide(inputs())["outcome"], "ESCROW")
        d = decide(inputs("read_inbox", args={}, steps=[step("s1", "read_inbox")]))
        self.assertEqual(d["outcome"], "ALLOW")

    def test_T1_house(self):
        args = {"to": arg(PRINCIPAL), "attach": arg("house/ledger.jsonl")}
        d = decide(inputs(args=args, declaration=None))
        self.assertEqual((d["outcome"], d["primary"], d["scope"]), ("TRIP", "T1_HOUSE", "L1"))
        d = decide(inputs("read_file", args={"path": arg("config/policy.json")}, steps=[step("s1", "read_file", {"path": ["x"]})]))
        self.assertEqual(d["primary"], "T1_HOUSE")

    def test_T2_canary(self):
        can = [{"token": "CANARY-01", "audience": [PRINCIPAL]}]
        args = {"to": arg("bob@partner.invalid"), "body": arg("x CANARY-01 y")}
        steps = [step("s1", "send_email", free={"to": "contacts"})]
        d = decide(inputs(args=args, steps=steps, payload_text="x CANARY-01 y", canaries=can))
        self.assertEqual((d["outcome"], d["primary"]), ("TRIP", "T2_CANARY"))
        d = decide(inputs(payload_text="x CANARY-01 y", canaries=can))
        self.assertEqual(d["outcome"], "ESCROW")
        d = decide(inputs(args=args, steps=steps, payload_text="CANARY-010", canaries=can))
        self.assertEqual(d["outcome"], "ESCROW", "a longer token is not this canary")

    def test_H1_no_declaration(self):
        d = decide(inputs(declaration=None))
        self.assertEqual((d["outcome"], d["primary"], d["scope"]), ("HOLD", "H1_NO_DECLARATION", "L0"))

    def test_H2_not_declared(self):
        self.assertEqual(decide(inputs(step_id="zz"))["primary"], "H2_NOT_DECLARED")
        self.assertEqual(decide(inputs(step_id=None))["primary"], "H2_NOT_DECLARED")
        wrong_tool = inputs(steps=[step("s1", "read_inbox")])
        self.assertEqual(decide(wrong_tool)["primary"], "H2_NOT_DECLARED")
        used_up = inputs(steps=[step("s1", "send_email", {"to": [PRINCIPAL]}, max_calls=1, used=1)])
        self.assertEqual(decide(used_up)["primary"], "H2_NOT_DECLARED")

    def test_S0_scope_held(self):
        d = decide(inputs(scope_states={"L3:org": "RUN", "L2:gate->world:EXTERNAL_SEND": "HOLD"}))
        self.assertEqual((d["primary"], d["scope"], d["held_scope"]), ("S0_SCOPE_HELD", "L2", "L2:gate->world:EXTERNAL_SEND"))
        d = decide(inputs(scope_states={"L3:org": "HOLD", "L2:gate->world:EXTERNAL_SEND": "HOLD"}))
        self.assertEqual(d["scope"], "L3")
        read = inputs("read_inbox", args={}, steps=[step("s1", "read_inbox")], scope_states={"L3:org": "HOLD"})
        self.assertEqual(decide(read)["outcome"], "ALLOW", "R0 actions continue")

    def test_H3_pinned_mismatch(self):
        d = decide(inputs(args={"to": arg("bob@partner.invalid")}))
        self.assertEqual((d["primary"], d["failing_slot"], d["failing_tainted"]), ("H3_PINNED_MISMATCH", "to", False))
        d = decide(inputs(args={"to": arg("zed@partner.invalid")}, steps=[step("s1", "send_email", free={"to": "contacts"})]))
        self.assertEqual(d["primary"], "H3_PINNED_MISMATCH")
        d = decide(inputs(args={"to": arg("zed@partner.invalid", U_LABEL)}))
        self.assertEqual((d["primary"], d["failing_tainted"]), ("H3_PINNED_MISMATCH", True))

    def test_H4_tainted_guarded(self):
        free = [step("s1", "send_email", free={"to": "contacts"})]
        d = decide(inputs(args={"to": arg("x@outside.invalid", U_LABEL)}, steps=free))
        self.assertEqual((d["outcome"], d["primary"], d["failing_tainted"]), ("DENY", "H4_TAINTED_GUARDED", True),
                         "v0.3: a tainted H4 on an unattended step is a no-resolver DENY")
        attended = [step("s1", "send_email", free={"to": "contacts"}, attended=True)]
        d = decide(inputs(args={"to": arg("x@outside.invalid", U_LABEL)}, steps=attended))
        self.assertEqual((d["outcome"], d["primary"]), ("HOLD", "H4_TAINTED_GUARDED"), "attended: a HOLD")
        d = decide(inputs(args={"to": arg("x@outside.invalid", U_LABEL)}, steps=free, mode="A1"))
        self.assertEqual(d["outcome"], "ESCROW", "A1 disables H4")
        d = decide(pay_inputs(amount=600, context=U_LABEL))
        self.assertEqual((d["outcome"], d["primary"]), ("HOLD", "H5_BUDGET_SESSION"),
                         "600 is over the session share too; the session group's reason is the primary")
        self.assertIn("H3_PINNED_MISMATCH", d["reasons"], "the literal carries its own (P) label in the helper: H3, untainted")

    def test_H9_verbatim_selection(self):
        free = [step("s1", "send_email", free={"to": "contacts"})]
        strings = [{"origin": "inbox:m3", "sender": "a@partner.invalid", "strings": ["bob@partner.invalid"]}]
        base = dict(args={"to": arg("bob@partner.invalid", U_LABEL)}, steps=free, untrusted_strings=strings)
        self.assertEqual(decide(inputs(**base))["outcome"], "ESCROW", "R1 off")
        d = decide(inputs(rules_enabled={"R1": True}, **base))
        self.assertEqual(d["primary"], "H9_VERBATIM_SELECTION")
        same = [{"origin": "inbox:m3", "sender": "bob@partner.invalid", "strings": ["bob@partner.invalid"]}]
        base["untrusted_strings"] = same
        self.assertEqual(decide(inputs(rules_enabled={"R1": True}, **base))["outcome"], "ESCROW")

    def test_H5_budget(self):
        d = decide(inputs(counters={"send:home.invalid": 5}))
        self.assertEqual((d["primary"], d["scope"], d["held_scope"]), ("H5_BUDGET", "L3", "L3:budget:send:home.invalid"))
        self.assertEqual(decide(inputs(counters={"send:home.invalid": 5}, mode="A4"))["outcome"], "ESCROW")
        self.assertEqual(decide(pay_inputs(amount=100, counters={"money": 950}))["primary"], "H5_BUDGET")

    def test_H5_budget_session(self):
        d = decide(inputs(session_counters={"send:home.invalid": 1}))
        self.assertEqual(d["outcome"], "ESCROW", "2 <= 0.5 x 5")
        d = decide(inputs(session_counters={"send:home.invalid": 2}))
        self.assertEqual((d["primary"], d["scope"]), ("H5_BUDGET_SESSION", "L1"))

    def test_H5_fuse(self):
        read = dict(args={}, steps=[step("s1", "read_inbox", max_calls=99)])
        self.assertEqual(decide(inputs("read_inbox", fuse_state={"READ_EXTERNAL": {"heat": 8.0, "t_last": 1}}, **read))["outcome"], "ALLOW")
        d = decide(inputs("read_inbox", fuse_state={"READ_EXTERNAL": {"heat": 8.5, "t_last": 1}}, **read))
        self.assertEqual((d["primary"], d["scope"]), ("H5_FUSE", "L1"))
        self.assertEqual(decide(inputs("read_inbox", mode="A4", fuse_state={"READ_EXTERNAL": {"heat": 99, "t_last": 1}}, **read))["outcome"], "ALLOW")

    def test_H6_persist_after_taint(self):
        args = {"key": arg("k"), "content": arg("c", U_LABEL)}
        steps = [step("s1", "persist_memory", {"key": ["k"]})]
        d = decide(inputs("persist_memory", args=args, steps=steps, payload_label=U_LABEL))
        self.assertEqual(d["primary"], "H6_PERSIST_AFTER_TAINT")
        d = decide(inputs("persist_memory", args=args, steps=steps, payload_label=P_LABEL))
        self.assertEqual(d["outcome"], "ESCROW")

    def test_H8_flow(self):
        secret = L.make(2, ["secret"], ["file:s"])
        free = [step("s1", "send_email", free={"to": "contacts"})]
        d = decide(inputs(args={"to": arg("bob@partner.invalid")}, steps=free, payload_label=secret))
        self.assertEqual((d["primary"], d["failing_slot"]), ("H8_FLOW", "to"))
        self.assertEqual(decide(inputs(payload_label=secret))["outcome"], "ESCROW", "secret may go to principal")
        other = L.make(2, ["unlisted"], [])
        self.assertEqual(decide(inputs(args={"to": arg("bob@partner.invalid")}, steps=free, payload_label=other))["outcome"],
                         "ESCROW", "an asset with no flow entry may flow anywhere")

    def test_A7_attended(self):
        free = [step("s1", "send_email", free={"to": "contacts"})]
        d = decide(inputs(args={"to": arg("x@outside.invalid", U_LABEL)}, steps=free, mode="A7"))
        self.assertEqual((d["outcome"], d["primary"]), ("HOLD", "H4_TAINTED_GUARDED"),
                         "A7 treats every step as attended: a HOLD (repin only), the v0.2 default")
        for mode in ("V2", "A1", "A4", "A5", "R2"):
            d = decide(inputs(args={"to": arg("zed@partner.invalid", U_LABEL)}, mode=mode))
            self.assertEqual(d["outcome"], "DENY", "tainted pinned mismatch is hard-denied in %s" % mode)
        d = decide(inputs(args={"to": arg("bob@x.invalid")}, mode="A7"))
        self.assertEqual(d["outcome"], "HOLD", "untainted H3 stays a HOLD in A7")

    def test_hard_deny_primary_follows_group_order(self):
        held = {"L3:org": "HOLD", "L2:agent->gate": "RUN"}
        d = decide(inputs(args={"to": arg("zed@partner.invalid", U_LABEL)}, scope_states=held))
        self.assertEqual((d["outcome"], d["primary"], d["scope"]), ("DENY", "S0_SCOPE_HELD", "L3"),
                         "[S0, tainted H3] gives a DENY with primary S0 (sec. 4)")
        self.assertEqual(d["reasons"], ["S0_SCOPE_HELD", "H3_PINNED_MISMATCH"])

    def test_tier(self):
        self.assertEqual(decide(pay_inputs(amount=50))["tier"], 2)
        self.assertEqual(decide(pay_inputs(amount=150))["tier"], 3)
        self.assertEqual(decide(pay_inputs(amount=50, counters={"money": 60}))["tier"], 3, "cumulative band")
        self.assertEqual(decide(pay_inputs(amount=150, mode="A4"))["tier"], 2)
        self.assertEqual(decide(inputs(tier_floor=2))["tier"], 2)
        args = {"key": arg("k"), "content": arg("c")}
        self.assertEqual(decide(inputs("persist_memory", args=args, steps=[step("s1", "persist_memory", {"key": ["k"]})]))["tier"], 2)

    def test_rule_order(self):
        args = {"key": arg("zz"), "content": arg("c", U_LABEL)}
        d = decide(inputs("persist_memory", args=args, step_id="nope", steps=[step("s1", "persist_memory", {"key": ["k"]})],
                          payload_label=U_LABEL))
        self.assertEqual(d["reasons"], ["H2_NOT_DECLARED", "H6_PERSIST_AFTER_TAINT"])
        args = {"to": arg("bob@partner.invalid"), "attach": arg("house/x")}
        d = decide(inputs(args=args, payload_text="CANARY-01", canaries=[{"token": "CANARY-01", "audience": []}]))
        self.assertEqual(d["primary"], "T1_HOUSE", "first T-rule wins")

    def test_T1_scans_path_typed_values_only(self):
        # sec. 3.3, 17: a house prefix in a text-typed value (body) never trips; in a path-typed value it does
        d = decide(inputs(args={"to": arg(PRINCIPAL), "body": arg("see house/ledger.jsonl")}))
        self.assertEqual(d["outcome"], "ESCROW")
        d = decide(inputs(args={"to": arg(PRINCIPAL), "body": arg("x"), "attach": arg("config/policy.json")}))
        self.assertEqual((d["outcome"], d["primary"]), ("TRIP", "T1_HOUSE"))
        d = decide(inputs(args={"to": arg("witness/heads.jsonl")}))
        self.assertNotEqual(d["primary"], "T1_HOUSE", "an address-typed slot is not scanned")
        d = decide(inputs("write_workspace", args={"path": arg("notes/a.txt"), "content": arg("house/x")},
                          steps=[step("s1", "write_workspace", {"path": ["notes/a.txt"]})]))
        self.assertEqual(d["outcome"], "ALLOW", "content is text-typed")
        d = decide(inputs("write_workspace", args={"path": arg("house/x"), "content": arg("c")},
                          steps=[step("s1", "write_workspace", {"path": ["house/x"]})]))
        self.assertEqual(d["primary"], "T1_HOUSE")

    def test_derived_slot(self):
        steps = [step("s1", "read_inbox"), step("s2", "send_email", derived={"to": {"sender_of": "s1"}})]
        senders = {"s1": ["bob@partner.invalid", "carol@partner.invalid"]}
        d = decide(inputs(args={"to": arg("carol@partner.invalid", U_LABEL)}, steps=steps, step_id="s2",
                          delivered_senders=senders))
        self.assertEqual(d["outcome"], "ESCROW", "equals a recorded sender of the named read step")
        d = decide(inputs(args={"to": arg("eve@outside.invalid", U_LABEL)}, steps=steps, step_id="s2",
                          delivered_senders=senders))
        self.assertEqual((d["outcome"], d["primary"], d["failing_slot"], d["failing_tainted"]),
                         ("DENY", "H3_PINNED_MISMATCH", "to", True), "otherwise H3 with the argument's taint")
        d = decide(inputs(args={"to": arg("eve@outside.invalid")}, steps=steps, step_id="s2", delivered_senders=senders))
        self.assertEqual((d["outcome"], d["primary"], d["failing_tainted"]), ("HOLD", "H3_PINNED_MISMATCH", False))
        d = decide(inputs(args={"to": arg("carol@partner.invalid", U_LABEL)}, steps=steps, step_id="s2",
                          delivered_senders={"s1": ["bob@partner.invalid"]}))
        self.assertEqual(d["primary"], "H3_PINNED_MISMATCH", "a sender another step delivered does not count")

    def test_undeclared_proposals(self):
        # an unknown tool: H1 before DECLARE, H2 after; tier 0, no debits, no slot
        d = decide(inputs("bogus", args={"x": arg("v")}, declaration=None))
        self.assertEqual((d["outcome"], d["primary"], d["tier"], d["debits"], d["failing_slot"]),
                         ("HOLD", "H1_NO_DECLARATION", 0, [], None))
        self.assertTrue(d["undeclared"])
        d = decide(inputs("bogus", args={"x": arg("v")}))
        self.assertEqual((d["outcome"], d["reasons"]), ("HOLD", ["H2_NOT_DECLARED"]))
        # an unresolvable handle: H2 names the first guarded slot (sinks order) whose handle is unresolvable
        bad = {"value": None, "label": copy.deepcopy(P_LABEL), "handle": "h9", "unresolvable": True}
        d = decide(inputs(args={"to": bad, "body": arg("x")}, scope_states={"L3:org": "HOLD"},
                          counters={"send:home.invalid": 9}))
        self.assertEqual((d["reasons"], d["failing_slot"], d["failing_tainted"]), (["H2_NOT_DECLARED"], "to", False),
                         "no other rule runs: no S0, no H5")
        tainted_bad = dict(bad, label=copy.deepcopy(U_LABEL))  # the gateway gives it the (tainted) context label
        d = decide(inputs(args={"to": tainted_bad, "body": arg("x")}, context=U_LABEL))
        self.assertEqual(d["failing_tainted"], True, "the null value carries the context label")
        # T1 over the literal values and T2 over the literal content still fire first
        d = decide(inputs(args={"to": bad, "attach": arg("house/ledger.jsonl")}))
        self.assertEqual(d["primary"], "T1_HOUSE")
        can = [{"token": "CANARY-01", "audience": [PRINCIPAL]}]
        d = decide(inputs(args={"to": bad, "body": arg("CANARY-01")}, canaries=can))
        self.assertEqual(d["primary"], "T2_CANARY", "a null destination is in no audience")
        d = decide(inputs("bogus", args={"x": arg("house/x")}, declaration=None))
        self.assertEqual(d["primary"], "T1_HOUSE", "unknown tool: every literal value is scanned")

    def test_debits(self):
        d = decide(pay_inputs(amount=80))
        self.assertIn({"key": "money", "amount": 80, "counters": ["period", "session"]}, d["debits"])
        self.assertIn({"key": "step:s1", "amount": 1, "counters": ["step"]}, d["debits"])


def random_inputs(rng):
    tool = rng.choice(["read_inbox", "read_file", "fetch_web", "send_email", "pay", "persist_memory",
                       "schedule", "write_workspace", "read_memory", "bogus"])
    lab = lambda: rng.choice([P_LABEL, I_LABEL, U_LABEL, L.make(2, ["secret"], ["file:x"])])
    vals = ["principal@home.invalid", "bob@partner.invalid", "x@outside.invalid", "house/l", "v-acme",
            "k", 50, 150, "docs/q3.txt", "CANARY-01 hi"]
    args = {s: arg(rng.choice(vals), lab()) for s in rng.sample(["to", "body", "payee", "amount", "key",
                                                                  "content", "path", "target", "action"], 3)}
    steps = [step("s1", rng.choice(["send_email", "pay", tool]),
                  pinned={"to": [PRINCIPAL]} if rng.random() < 0.5 else {},
                  free={"payee": "vendors", "amount": {"max": 100}, "to": "contacts"},
                  used=rng.randint(0, 1), attended=rng.random() < 0.3,
                  derived={"to": {"sender_of": "s0"}} if rng.random() < 0.2 else None)]
    if rng.random() < 0.15:
        args[rng.choice(list(args))] = {"value": None, "label": lab(), "handle": "h9", "unresolvable": True}
    return inputs(tool, args=args, steps=steps, step_id=rng.choice(["s1", None, "s9"]),
                  delivered_senders={"s0": ["a@partner.invalid"]} if rng.random() < 0.5 else {},
                  mode=rng.choice(["V2", "A1", "A4", "A5", "A7", "R2"]),
                  payload_label=lab(), payload_text=rng.choice(["", "CANARY-01", "FACT-1"]),
                  canaries=[{"token": "CANARY-01", "audience": [PRINCIPAL]}],
                  declaration=None if rng.random() < 0.1 else {"declared_before_taint": True, "steps": steps},
                  counters={"money": rng.randint(0, 1100), "send:partner.invalid": rng.randint(0, 6)},
                  session_counters={"money": rng.randint(0, 600)},
                  fuse_state={"READ_EXTERNAL": {"heat": rng.random() * 12, "t_last": 3}},
                  tier_floor=rng.randint(0, 2),
                  scope_states={"L3:org": rng.choice(["RUN", "RUN", "HOLD"]), "L2:gate->world:PAYMENT": "RUN"},
                  untrusted_strings=[{"origin": "inbox:m1", "sender": "a@partner.invalid", "strings": ["bob@partner.invalid"]}],
                  rules_enabled={"R1": rng.random() < 0.5})


class DeterminismTest(unittest.TestCase):
    def test_1000_random_inputs_twice(self):
        rng = random.Random(20260929)
        for _ in range(1000):
            inp = random_inputs(rng)
            first = decide(copy.deepcopy(inp))
            second = decide(copy.deepcopy(inp))
            roundtrip = decide(json.loads(canonical(inp)))
            self.assertEqual(canonical(first), canonical(second))
            self.assertEqual(canonical(first), canonical(roundtrip), "same answer after a JSON round trip")

    def test_decide_does_not_mutate_inputs(self):
        inp = random_inputs(random.Random(1))
        before = canonical(inp)
        decide(inp)
        self.assertEqual(before, canonical(inp))


if __name__ == "__main__":
    unittest.main()
