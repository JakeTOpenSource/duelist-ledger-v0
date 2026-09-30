"""Diary chain + witness tamper detection, and seal commit/verify (spec sec. 17)."""

import os
import shutil
import tempfile
import unittest

from duelist_ledger.canon import H, canonical, dumps_line, new_key
from duelist_ledger.ledger import (Ledger, read_entries, rehash_from, tamper_delete, tamper_edit, tamper_rehash,
                                   tamper_reorder, verify)
from duelist_ledger.seal import check_reveal_files, commit, verify_reveal
from duelist_ledger.witness import Witness


class ChainTamperTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="dlt")
        self.key = new_key()
        self.lp = os.path.join(self.dir, "house", "ledger.jsonl")
        self.hp = os.path.join(self.dir, "witness", "heads.jsonl")
        led = Ledger(self.lp, self.key)
        wit = Witness(self.hp, new_key())
        for i in range(30):
            led.append(t=i, session="s1", scope="L0", kind="PROPOSE", actor="agent", ref="r%d" % i,
                       body={"i": i}, reasons=[], policy_hash="sha256:x")
            if led.seq % 10 == 0:
                wit.record(led.seq, led.head)
        led.close()
        wit.close()

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_clean_chain_verifies(self):
        self.assertEqual(verify(self.lp, self.hp, gate_key=self.key), {"ok": True, "first_bad_seq": None, "why": None})

    def test_edit_detected(self):
        tamper_edit(self.lp, 5)
        res = verify(self.lp, self.hp)
        self.assertFalse(res["ok"])
        self.assertEqual(res["first_bad_seq"], 5)

    def test_delete_detected(self):
        tamper_delete(self.lp, 7)
        self.assertFalse(verify(self.lp, self.hp)["ok"])

    def test_delete_and_resign_detected_by_witness(self):
        tamper_delete(self.lp, 7, gate_key=self.key)
        self.assertTrue(verify(self.lp, os.path.join(self.dir, "none.jsonl"))["ok"], "chain alone looks fine")
        res = verify(self.lp, self.hp)
        self.assertFalse(res["ok"])
        self.assertEqual(res["why"], "witness head mismatch")

    def test_reorder_detected(self):
        tamper_reorder(self.lp, 12)
        self.assertFalse(verify(self.lp, self.hp)["ok"])

    def test_reorder_and_resign_detected_by_witness(self):
        entries = read_entries(self.lp)
        entries[11], entries[12] = entries[12], entries[11]
        for n, e in enumerate(entries, 1):
            e["seq"] = n
        rehash_from(entries, 11, self.key)
        with open(self.lp, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("".join(dumps_line(e) + "\n" for e in entries))
        self.assertTrue(verify(self.lp, os.path.join(self.dir, "none.jsonl"), gate_key=self.key)["ok"],
                        "the re-signed chain alone looks fine")
        res = verify(self.lp, self.hp, gate_key=self.key)
        self.assertEqual((res["ok"], res["why"]), (False, "witness head mismatch"))

    def test_rehash_with_gate_key_detected_only_by_witness(self):
        tamper_rehash(self.lp, 5, self.key)
        self.assertTrue(verify(self.lp, os.path.join(self.dir, "none.jsonl"), gate_key=self.key)["ok"])
        res = verify(self.lp, self.hp, gate_key=self.key)
        self.assertFalse(res["ok"])
        self.assertEqual(res["first_bad_seq"], 10)
        self.assertEqual(res["why"], "witness head mismatch")


class SealTest(unittest.TestCase):
    def test_commit_formula(self):
        obj = {"b": 1, "a": [1, "x"]}
        import hashlib
        expect = "sha256:" + hashlib.sha256(canonical(obj) + b"salt").hexdigest()
        self.assertEqual(commit(obj, b"salt"), expect)
        self.assertEqual(H(obj), "sha256:" + hashlib.sha256(b'{"a":[1,"x"],"b":1}').hexdigest())

    def test_verify_reveal(self):
        obj = {"version": 1, "scenarios": {}}
        c = commit(obj, b"pepper")
        self.assertTrue(verify_reveal(obj, b"pepper", c))
        self.assertFalse(verify_reveal(obj, b"pepper2", c))
        self.assertFalse(verify_reveal({"version": 2, "scenarios": {}}, b"pepper", c))

    def test_reveal_files(self):
        d = tempfile.mkdtemp(prefix="dlt")
        try:
            import json
            obj = {"version": 1, "author": "test", "scenarios": {"X": {"V2": {"goal_met": True}}}}
            with open(os.path.join(d, "exp.json"), "w", encoding="utf-8") as fh:
                json.dump(obj, fh)
            with open(os.path.join(d, "salt.txt"), "w", encoding="utf-8") as fh:
                fh.write("s3cret\n")
            with open(os.path.join(d, "seal.json"), "w", encoding="utf-8") as fh:
                json.dump({"commit": commit(obj, b"s3cret")}, fh)
            ok = check_reveal_files(os.path.join(d, "seal.json"), os.path.join(d, "exp.json"), os.path.join(d, "salt.txt"))
            self.assertTrue(ok["ok"])
            with open(os.path.join(d, "seal.json"), "w", encoding="utf-8") as fh:
                json.dump({"commit": commit(obj, b"other")}, fh)
            bad = check_reveal_files(os.path.join(d, "seal.json"), os.path.join(d, "exp.json"), os.path.join(d, "salt.txt"))
            self.assertFalse(bad["ok"])
        finally:
            shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
