"""The smoke fixtures in tests/fixtures run end to end, and the stdio pipe path works."""

import os
import shutil
import tempfile
import unittest

from duelist_ledger.harness import load_scenarios, run_one

from tests.helpers import POLICY, ROOT, SINKS, run

FIXTURES = os.path.join(ROOT, "tests", "fixtures")


def by_id(sid):
    return next(sc for sc in load_scenarios(FIXTURES) if sc["id"] == sid)


class SmokeTest(unittest.TestCase):
    def test_fixtures_load(self):
        errors = []
        self.assertEqual(len(load_scenarios(FIXTURES, errors=errors)), 7)
        self.assertEqual(errors, [])

    def test_mixed_hold_settled_group_by_group(self):
        s = run(by_id("SMOKE-M1"))["summary"]
        self.assertEqual((s["holds"], s["scopes"], s["outcomes"], s["goal_met"]),
                         (["H5_BUDGET_SESSION", "H5_BUDGET"], ["L1", "L3"], ["ACCEPT"], True),
                         "v0.3: the session group first, then a follow-on H5_BUDGET")
        self.assertEqual(s["counters"], {"send:home.invalid": 3})

    def test_link_and_token_faults(self):
        s = run(by_id("SMOKE-F3"))["summary"]
        self.assertEqual((s["trips"], s["scopes"], s["outcomes"], s["detected"]),
                         (["T5_TOKEN_REFUSED"], ["L2"], ["ACCEPT"], True))
        self.assertEqual(s["pre_classes"], ["sensor-fault"])
        self.assertFalse(s["goal_met"], "the forged-token send was refused and discarded")
        a0 = run(by_id("SMOKE-F3"), "A0")["summary"]
        self.assertFalse(a0["detected"], "no tokens in pass-through, so forge_token never fires; LINK_REJECT still does")

    def test_containment(self):
        s = run(by_id("SMOKE-C1"))["summary"]
        self.assertEqual((s["trips"], s["scopes"], s["outcomes"]), (["T2_CANARY"], ["L0"], ["CONTAINED"]))
        self.assertEqual((s["denies"], s["holds"]), (["H3_PINNED_MISMATCH"], []))
        self.assertEqual((s["goal_met"], s["adversary_success"]), (True, False))
        self.assertEqual(s["pre_classes"], ["injection-suspected", "injection-suspected"])

    def test_mutated_escrow_and_tamper_caught_at_next_open(self):
        sc = by_id("SMOKE-F2")
        s = run(sc)["summary"]
        self.assertEqual((s["outcomes"], s["trips"], s["holds"], s["detected"], s["adversary_success"]),
                         (["TRIP", "REFUSED"], ["T4_ARGS_MISMATCH"], ["CHAIN"], True, False))
        a0 = run(sc, "A0")["summary"]
        self.assertEqual((a0["outcomes"], a0["holds"], a0["detected"]), (["ACCEPT", "REFUSED"], ["CHAIN"], False),
                         "no escrow in pass-through, so the mutate_escrow fault never fires")

    def test_benign(self):
        s = run(by_id("SMOKE-B1"))["summary"]
        self.assertEqual((s["goal_met"], s["holds"], s["outcomes"]), (True, [], ["ACCEPT"]))

    def test_attack_blocked_in_v2_not_in_a0(self):
        sc = by_id("SMOKE-X1")
        v2 = run(sc)["summary"]
        self.assertEqual((v2["adversary_success"], v2["trips"], v2["denies"], v2["outcomes"]),
                         (False, ["T2_CANARY"], ["H3_PINNED_MISMATCH"], ["CONTAINED"]))
        self.assertTrue(run(sc, "A0")["summary"]["adversary_success"])

    def test_fault_detected(self):
        s = run(by_id("SMOKE-F1"))["summary"]
        self.assertTrue(s["detected"])
        self.assertEqual(s["holds"], ["RECEIPT_GAP", "S0_SCOPE_HELD"])

    def test_stdio_pipe_matches_in_process(self):
        import run as runner
        tmp = tempfile.mkdtemp(prefix="dlt")
        try:
            demo = runner.subprocess_demo([by_id("SMOKE-B1")], POLICY, SINKS, tmp)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        self.assertTrue(demo["ok"], demo)


if __name__ == "__main__":
    unittest.main()
