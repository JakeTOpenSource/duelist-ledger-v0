"""The house diary: a hash-chained, signed JSONL log, plus its checker.

In plain words: every gate event is one line. Each line carries the fingerprint of the line
before it, so removing, reordering or editing a line breaks the chain. The witness keeps
copies of some fingerprints, so even a full rewrite with the gate's own key is caught.
This module also holds the four tamper helpers that the fault hooks and tests use.
"""

import json
import os

from .canon import H, check_sig, dumps_line, sign
from .witness import read_heads

GENESIS = "sha256:" + "0" * 64


class Ledger:
    """Append-only diary at <run>/house/ledger.jsonl."""

    def __init__(self, path, gate_key):
        self.path = path
        self._key = gate_key
        self.seq = 0
        self.head = GENESIS
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self._fh = open(path, "a+b")

    def close(self):
        if not self._fh.closed:
            self._fh.close()

    def read_text(self):
        """The diary file as it is on disk now, read through the open handle."""
        self._fh.flush()
        self._fh.seek(0)
        data = self._fh.read()
        self._fh.seek(0, 2)
        return data.decode("utf-8")

    def append(self, *, t, session, scope, kind, actor, ref, body, reasons, policy_hash):
        entry = {
            "v": 1, "seq": self.seq + 1, "prev": self.head, "t": t, "session": session,
            "scope": scope, "kind": kind, "actor": actor, "ref": ref, "body": body,
            "reasons": list(reasons), "policy_hash": policy_hash,
        }
        digest = H(entry)
        entry["hash"] = digest
        entry["sig"] = sign(self._key, digest)
        self._fh.write((dumps_line(entry) + "\n").encode("utf-8"))
        self._fh.flush()
        self.seq += 1
        self.head = digest
        return entry


def parse_entries(text):
    """Diary text -> parsed lines. Unparseable lines come back as None."""
    out = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            out.append(json.loads(line))
        except ValueError:
            out.append(None)
    return out


def read_entries(path):
    """All diary lines of a file, parsed."""
    with open(path, encoding="utf-8") as fh:
        return parse_entries(fh.read())


def verify(ledger_path, heads_path, gate_key=None, witness_key=None, ledger_text=None, heads_text=None):
    """Recompute the chain and check every witness head. Returns {ok, first_bad_seq, why}.

    ledger_text / heads_text let a caller that already holds the files open pass their
    current contents instead of re-opening them (same check, fewer file opens).
    """
    bad = []
    hashes = {}
    prev = GENESIS
    expected = 1
    entries = parse_entries(ledger_text) if ledger_text is not None else read_entries(ledger_path)
    for entry in entries:
        if not isinstance(entry, dict):
            bad.append((expected, "unparseable line"))
            break
        seq = entry.get("seq")
        core = {k: v for k, v in entry.items() if k not in ("hash", "sig")}
        if seq != expected:
            bad.append((expected, "sequence break"))
            break
        if entry.get("prev") != prev:
            bad.append((seq, "prev link broken"))
            break
        if H(core) != entry.get("hash"):
            bad.append((seq, "hash mismatch"))
            break
        if gate_key is not None and not check_sig(gate_key, entry.get("hash", ""), entry.get("sig")):
            bad.append((seq, "bad signature"))
            break
        hashes[seq] = entry["hash"]
        prev = entry["hash"]
        expected += 1
    for head in read_heads(heads_path, witness_key, text=heads_text):
        seq = head.get("seq")
        if not head.get("sig_ok"):
            bad.append((seq if isinstance(seq, int) else 0, "bad witness signature"))
        elif hashes.get(seq) != head.get("head_hash"):
            bad.append((seq, "witness head mismatch"))
    if not bad:
        return {"ok": True, "first_bad_seq": None, "why": None}
    seq, why = min(bad, key=lambda b: b[0])
    return {"ok": False, "first_bad_seq": seq, "why": why}


# ---- tamper helpers (fault hooks and tests) ------------------------------------------------

def _write_all(path, entries):
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        for e in entries:
            fh.write(dumps_line(e) + "\n")


def tamper_edit(path, seq):
    """Edit the body of entry `seq` in place; hashes are left alone."""
    entries = read_entries(path)
    for e in entries:
        if e.get("seq") == seq:
            e["body"] = dict(e.get("body") or {}, tampered=True)
            _write_all(path, entries)
            return True
    return False


def rehash_from(entries, start_index, gate_key):
    """Recompute prev/hash/sig for every entry from start_index on (what a key-holder could do)."""
    prev = entries[start_index - 1]["hash"] if start_index > 0 else GENESIS
    for e in entries[start_index:]:
        e["prev"] = prev
        core = {k: v for k, v in e.items() if k not in ("hash", "sig")}
        e["hash"] = H(core)
        e["sig"] = sign(gate_key, e["hash"])
        prev = e["hash"]
    return entries


def tamper_rehash(path, seq, gate_key):
    """Edit entry `seq` and then re-sign every later entry with the gate key."""
    entries = read_entries(path)
    for i, e in enumerate(entries):
        if e.get("seq") == seq:
            e["body"] = dict(e.get("body") or {}, tampered=True)
            _write_all(path, rehash_from(entries, i, gate_key))
            return True
    return False


def tamper_delete(path, seq, gate_key=None):
    """Delete entry `seq`. With a gate key, also renumber and re-sign the rest."""
    entries = read_entries(path)
    idx = next((i for i, e in enumerate(entries) if e.get("seq") == seq), None)
    if idx is None:
        return False
    del entries[idx]
    if gate_key is not None:
        for e in entries[idx:]:
            e["seq"] -= 1
        rehash_from(entries, idx, gate_key)
    _write_all(path, entries)
    return True


def tamper_reorder(path, seq):
    """Swap entry `seq` with the entry after it."""
    entries = read_entries(path)
    idx = next((i for i, e in enumerate(entries) if e.get("seq") == seq), None)
    if idx is None or idx + 1 >= len(entries):
        return False
    entries[idx], entries[idx + 1] = entries[idx + 1], entries[idx]
    _write_all(path, entries)
    return True
