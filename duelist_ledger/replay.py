"""Replay: recompute every AUTHORIZE decision from its logged inputs.

In plain words: the diary stores, for every authorization, the full input snapshot and the
answer decide() gave. Replay feeds each snapshot back into decide() and checks the answer is
identical. Content was logged as fingerprints; the matching content is fetched from the
house blob file so the recomputation sees exactly what the gate saw.
"""

import json
import os

from .canon import canonical
from .decide import decide
from .ledger import read_entries


def load_blobs(path):
    blobs = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    row = json.loads(line)
                    blobs[row["digest"]] = row["value"]
    return blobs


def rehydrate(obj, blobs):
    if isinstance(obj, dict):
        if set(obj) == {"$blob"}:
            return blobs.get(obj["$blob"])
        return {k: rehydrate(v, blobs) for k, v in obj.items()}
    if isinstance(obj, list):
        return [rehydrate(v, blobs) for v in obj]
    return obj


def replay(ledger_path, blobs_path):
    """Returns {total, matched, mismatched_seqs}."""
    blobs = load_blobs(blobs_path)
    total, matched, bad = 0, 0, []
    for entry in read_entries(ledger_path):
        if not isinstance(entry, dict) or entry.get("kind") != "AUTHORIZE":
            continue
        total += 1
        body = entry.get("body") or {}
        try:
            again = decide(rehydrate(body.get("inputs"), blobs))
        except Exception:  # a crash on logged inputs is a replay mismatch, not a harness failure
            again = None
        if again is not None and canonical(again) == canonical(body.get("decision")):
            matched += 1
        else:
            bad.append(entry.get("seq"))
    return {"total": total, "matched": matched, "mismatched_seqs": bad}
