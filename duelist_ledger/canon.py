"""Canonical JSON, fingerprints and the stand-in signer.

In plain words: every record is turned into one exact byte string (sorted keys, no spaces),
so the same record always gets the same fingerprint. Signatures here are HMAC stand-ins,
not real digital signatures.
"""

import hashlib
import hmac
import json
import secrets


def canonical(obj):
    """The one exact byte form of a JSON-able object (spec sec. 2)."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def H(obj):
    """Fingerprint of an object: 'sha256:' + hex digest of its canonical bytes."""
    return "sha256:" + hashlib.sha256(canonical(obj)).hexdigest()


def new_key():
    """A fresh 32-byte random signing key (one per run for the gate, one for the witness)."""
    return secrets.token_bytes(32)


def sign(key, text):
    """HMAC-SHA256 of a text string, as hex. Stand-in for a signature."""
    return hmac.new(key, text.encode("utf-8"), hashlib.sha256).hexdigest()


def check_sig(key, text, sig):
    """True when sig is the HMAC of text under key (constant-time compare)."""
    if not isinstance(sig, str):
        return False
    return hmac.compare_digest(sign(key, text), sig)


def dumps_line(obj):
    """One canonical JSON line as text, for the JSONL files."""
    return canonical(obj).decode("utf-8")
