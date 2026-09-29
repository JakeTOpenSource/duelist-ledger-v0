"""Trust labels and the value store.

In plain words: every piece of data carries a label saying how much we trust it (principal,
internal, untrusted, quarantined), which sensitive asset tags it carries, and where it came
from. Mixing two pieces of data keeps the lower trust and all tags. Anything below INTERNAL
counts as tainted. The agent gets short handles ("h7") that point at stored values.
"""

PRINCIPAL = 3
INTERNAL = 2
ENDORSED = 1
UNTRUSTED = 0
QUARANTINED = -1

NAMES = {PRINCIPAL: "PRINCIPAL", INTERNAL: "INTERNAL", ENDORSED: "ENDORSED",
         UNTRUSTED: "UNTRUSTED", QUARANTINED: "QUARANTINED"}
BY_NAME = {v: k for k, v in NAMES.items()}


def parse_integrity(value, default=INTERNAL):
    """Accept an integer level or a level name such as 'INTERNAL'."""
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        name = value.strip().upper()
        if name in BY_NAME:
            return BY_NAME[name]
        try:
            return int(name)
        except ValueError:
            return default
    return default


def make(integrity, assets=(), origins=()):
    """A label record: {integrity, assets (sorted), origins (sorted)}."""
    return {"integrity": int(integrity),
            "assets": sorted({str(a) for a in assets}),
            "origins": sorted({str(o) for o in origins})}


def top():
    """The starting session label: PRINCIPAL, no assets, no origins."""
    return make(PRINCIPAL)


def join(a, b):
    """Lower trust wins; asset tags and origins are unioned."""
    return make(min(a["integrity"], b["integrity"]),
                list(a.get("assets", [])) + list(b.get("assets", [])),
                list(a.get("origins", [])) + list(b.get("origins", [])))


def join_all(items, start=None):
    out = start if start is not None else top()
    for item in items:
        out = join(out, item)
    return out


def is_tainted(label):
    """Tainted means integrity below INTERNAL (2)."""
    return label.get("integrity", UNTRUSTED) < INTERNAL


def copy(label):
    return make(label["integrity"], label.get("assets", []), label.get("origins", []))


class ValueStore:
    """Session-local store of delivered values, addressed by handles h1, h2, ..."""

    def __init__(self):
        self._values = {}
        self._n = 0

    def put(self, content, label, origin, sender=None, directives=None):
        self._n += 1
        handle = "h%d" % self._n
        self._values[handle] = {"content": content, "label": copy(label), "origin": origin,
                                "sender": sender, "directives": list(directives or [])}
        return handle

    def get(self, handle):
        return self._values.get(handle) if isinstance(handle, str) else None
