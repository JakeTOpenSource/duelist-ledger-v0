"""State machine: transition rules, rate limits, and the 10,000-sequence property test."""

import random
import unittest

from duelist_ledger.state import RANK, State


class TransitionTest(unittest.TestCase):
    def test_source_rules(self):
        st = State()
        s = "L1:session:s1"
        self.assertFalse(st.apply({"scope": s, "to": "TRIP"}, "P")["applied"], "P cannot trip")
        self.assertTrue(st.apply({"scope": s, "to": "HOLD", "session": "s1"}, "P")["applied"])
        self.assertFalse(st.apply({"scope": s, "to": "RUN"}, "P")["applied"], "P cannot lower")
        self.assertFalse(st.apply({"scope": s, "to": "RUN"}, "D")["applied"], "D needs a predicate")
        self.assertTrue(st.apply({"scope": s, "to": "RUN", "predicate": "reconcile_ok"}, "D")["applied"])
        st.apply({"scope": s, "to": "HOLD"}, "D")
        self.assertTrue(st.apply({"scope": s, "to": "CLOSED"}, "H")["applied"])
        self.assertFalse(st.apply({"scope": s, "to": "RUN"}, "H")["applied"], "CLOSED is terminal")
        st.apply({"scope": "L2:x", "to": "TRIP"}, "D")
        for src in "PDH":
            for to in RANK:
                self.assertFalse(st.apply({"scope": "L2:x", "to": to, "predicate": "p"}, src)["applied"],
                                 "nothing leaves TRIP")

    def test_effective_state_inherits(self):
        st = State()
        st.register("L1:session:s1")
        st.register("L0:s1:p1", "L1:session:s1")
        st.apply({"scope": "L3:org", "to": "HOLD"}, "D")
        self.assertEqual(st.effective("L0:s1:p1"), "HOLD")
        self.assertEqual(st.effective("L2:gate->world:PAYMENT"), "HOLD")

    def test_p_rate_limits(self):
        st = State(p_per_session=2, p_per_scenario=3)
        kinds = [st.apply({"scope": "L0:%d" % i, "to": "HOLD", "session": "s1"}, "P")["kind"] for i in range(4)]
        self.assertEqual(kinds, ["OK", "OK", "FLAG", "FLAG"])
        r = st.apply({"scope": "L0:x", "to": "HOLD", "session": "s2"}, "P")
        self.assertEqual(r["kind"], "OK")
        r = st.apply({"scope": "L0:y", "to": "HOLD", "session": "s3"}, "P")
        self.assertEqual(r["kind"], "FLAG")

    def test_first_exhaustion_alarms_once(self):
        st = State(p_per_session=0, p_per_scenario=0)
        a = st.apply({"scope": "L0:1", "to": "HOLD", "session": "s"}, "P")
        b = st.apply({"scope": "L0:2", "to": "HOLD", "session": "s"}, "P")
        self.assertEqual((a["alarm"], b["alarm"]), ("P_BUDGET_EXHAUSTED", None))

    def test_counters_and_floor_one_way(self):
        st = State()
        self.assertTrue(st.debit("money", 50, "s1"))
        self.assertFalse(st.debit("money", -10, "s1"))
        self.assertFalse(st.debit("money", True, "s1"))
        self.assertEqual(st.counters.get("money"), 50)
        self.assertFalse(st.raise_tier_floor("s1", -1))
        self.assertTrue(st.raise_tier_floor("s1"))
        self.assertEqual(st.tier_floor("s1"), 1)


class PropertyTest(unittest.TestCase):
    def test_10000_random_event_sequences(self):
        rng = random.Random(1729)
        scopes = ["L3:org", "L1:session:s1", "L1:session:s2", "L2:agent->gate",
                  "L2:gate->world:PAYMENT", "L0:s1:p1", "L0:s2:p1", "L3:budget:money"]
        for _ in range(10000):
            st = State(p_per_session=rng.randint(0, 3), p_per_scenario=rng.randint(0, 5))
            st.register("L0:s1:p1", "L1:session:s1")
            st.register("L0:s2:p1", "L1:session:s2")
            for _ in range(rng.randint(1, 12)):
                op = rng.random()
                c_before = st.counters.snapshot()
                f_before = dict(st.tier_floors)
                if op < 0.7:
                    scope = rng.choice(scopes)
                    src = rng.choice("PDH")
                    before = st.own(scope)
                    event = {"scope": scope, "to": rng.choice(list(RANK)), "session": rng.choice(["s1", "s2"])}
                    if rng.random() < 0.5:
                        event["predicate"] = "reconcile_ok"
                    res = st.apply(event, src)
                    after = st.own(scope)
                    if src == "P":
                        self.assertGreaterEqual(RANK[after], RANK[before], "P never lowers restriction")
                        self.assertNotEqual((before != "TRIP", after), (True, "TRIP"), "no TRIP from P")
                    if before in ("TRIP", "CLOSED"):
                        self.assertEqual(after, before, "terminal states stay")
                    if not res["applied"]:
                        self.assertEqual(after, before)
                elif op < 0.85:
                    st.debit(rng.choice(["money", "send:x"]), rng.choice([-5, 0, 1, 2.5, 10, True, "3"]),
                             rng.choice(["s1", "s2", None]))
                else:
                    st.raise_tier_floor(rng.choice(["s1", "s2"]), rng.choice([-1, 0, 1, 2]))
                c_after = st.counters.snapshot()
                for k, v in c_before.items():
                    self.assertGreaterEqual(c_after.get(k, 0), v, "counters never decrease")
                for k, v in f_before.items():
                    self.assertGreaterEqual(st.tier_floors.get(k, 0), v, "tier floor never decreases")
            self.assertTrue(st.invariants_ok(), st.violations)
            for scope, before, after, src in st.transitions:
                self.assertFalse(src == "P" and after == "TRIP")
                self.assertFalse(src == "P" and RANK[after] < RANK[before])


if __name__ == "__main__":
    unittest.main()
