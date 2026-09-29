"""Double-entry reconciliation: what the world says happened vs what the gate says it did.

In plain words: the world keeps its own receipt book. After every executed action, the gate
compares the two books. A receipt the gate never issued means something went around the gate
(bypass). An action the gate issued with no receipt means the world's report went missing (gap).
"""

import json
import os

from .canon import H

GENESIS = "sha256:" + "0" * 64


def reconcile(effects, receipts):
    """effects: {effect_id: sink_class}; receipts: list of receipt dicts.

    Returns {"bypass": [receipts with no gateway effect], "gaps": [(effect_id, sink_class)]}.
    """
    seen = {r.get("effect_id") for r in receipts}
    bypass = [r for r in receipts if r.get("effect_id") not in effects]
    gaps = [(eid, cls) for eid, cls in effects.items() if eid not in seen]
    return {"bypass": bypass, "gaps": gaps}


def verify_receipts(path):
    """Check the world's own receipt chain. Returns {ok, first_bad}."""
    if not os.path.exists(path):
        return {"ok": True, "first_bad": None}
    prev = GENESIS
    with open(path, encoding="utf-8") as fh:
        for n, line in enumerate(fh, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except ValueError:
                return {"ok": False, "first_bad": n}
            core = {k: v for k, v in row.items() if k != "hash"}
            if row.get("prev") != prev or H(core) != row.get("hash"):
                return {"ok": False, "first_bad": row.get("rcpt_seq", n)}
            prev = row["hash"]
    return {"ok": True, "first_bad": None}
