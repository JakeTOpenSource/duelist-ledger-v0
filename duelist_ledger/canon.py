"""Canonical JSON, fingerprints, the signers, and the effect-token argument digest.

In plain words: every record is turned into one exact byte string (sorted keys, no spaces),
so the same record always gets the same fingerprint. Diary entries and witness heads are
HMAC-SHA256 signed (stand-ins). Effect tokens and foreign labels are signed with Ed25519 when
the optional package (`cryptography` or `pynacl`) is present, else with an HMAC-SHA256
stand-in under the gate key; `SIGNATURE_SCHEME` says which one this process uses, and the
caveat line reports it (spec sec. 0, 2, 4).
"""

import hashlib
import hmac
import json
import secrets

ED25519_BACKEND = None
try:  # optional package 1 of 2 (sec. 0)
    from cryptography.hazmat.primitives import serialization as _ser
    from cryptography.hazmat.primitives.asymmetric import ed25519 as _ed
    ED25519_BACKEND = "cryptography"
except Exception:  # pragma: no cover - depends on the environment
    try:  # optional package 2 of 2
        import nacl.signing as _nacl_signing
        import nacl.exceptions as _nacl_exc
        ED25519_BACKEND = "pynacl"
    except Exception:
        ED25519_BACKEND = None

ED25519_AVAILABLE = ED25519_BACKEND is not None
SIGNATURE_SCHEME = "ed25519" if ED25519_AVAILABLE else "hmac-sha256-standin"


def canonical(obj):
    """The one exact byte form of a JSON-able object (spec sec. 2)."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def H(obj):
    """Fingerprint of an object: 'sha256:' + hex digest of its canonical bytes."""
    return "sha256:" + hashlib.sha256(canonical(obj)).hexdigest()


def H_bytes(data):
    """Fingerprint of raw bytes (used for key digests): 'sha256:' + hex."""
    return "sha256:" + hashlib.sha256(data).hexdigest()


def new_key():
    """A fresh 32-byte random key (gate key, witness key, one session key per session)."""
    return secrets.token_bytes(32)


def sign(key, text):
    """HMAC-SHA256 of a text string, as hex. Stand-in for a signature."""
    return hmac.new(key, text.encode("utf-8"), hashlib.sha256).hexdigest()


def check_sig(key, text, sig):
    """True when sig is the HMAC of text under key (constant-time compare)."""
    if not isinstance(sig, str):
        return False
    return hmac.compare_digest(sign(key, text), sig)


def mac_of(key, message):
    """The agent-link mac (sec. 3.8): HMAC-SHA256 under the session key of the canonical
    message without its `mac` field, as hex."""
    core = {k: v for k, v in message.items() if k != "mac"}
    return hmac.new(key, canonical(core), hashlib.sha256).hexdigest()


def check_mac(key, message):
    if not isinstance(message, dict) or not isinstance(message.get("mac"), str):
        return False
    return hmac.compare_digest(mac_of(key, message), message["mac"])


def dumps_line(obj):
    """One canonical JSON line as text, for the JSONL files."""
    return canonical(obj).decode("utf-8")


def effect_args_hash(args, content_slots):
    """`args_hash` of an effect token (sec. 4): H of the args with guarded values in clear and
    content values as digests. Any slot not known to be guarded is treated as content."""
    shaped = {}
    for slot in sorted(args or {}):
        val = args[slot]
        shaped[slot] = {"$digest": H(val)} if slot in content_slots else val
    return H(shaped)


class Signer:
    """The gateway's signer for effect tokens and foreign labels.

    Ed25519 when the optional package is present (a fresh signing pair per run), else an
    HMAC-SHA256 stand-in under `gate_key`. `verify_key_record()` is what the gateway publishes
    in the SESSION_OPEN body and the run manifest; `verify()` is what a receiver runs with it.
    With the stand-in there is no separable verify key: the receiver is handed the gate key
    by convention, and the published record carries only the scheme and the key's digest.
    """

    def __init__(self, gate_key):
        self.scheme = SIGNATURE_SCHEME
        self._gate_key = gate_key
        self._priv = None
        if ED25519_BACKEND == "cryptography":
            self._priv = _ed.Ed25519PrivateKey.generate()
            pub = self._priv.public_key().public_bytes(_ser.Encoding.Raw, _ser.PublicFormat.Raw)
            self.verify_key = pub.hex()
        elif ED25519_BACKEND == "pynacl":
            self._priv = _nacl_signing.SigningKey.generate()
            self.verify_key = bytes(self._priv.verify_key).hex()
        else:
            self.verify_key = None

    def sign(self, obj):
        """Signature (hex) over the canonical bytes of obj."""
        data = canonical(obj)
        if ED25519_BACKEND == "cryptography":
            return self._priv.sign(data).hex()
        if ED25519_BACKEND == "pynacl":
            return self._priv.sign(data).signature.hex()
        return hmac.new(self._gate_key, data, hashlib.sha256).hexdigest()

    def verify_key_record(self):
        if self.verify_key is not None:
            return {"scheme": self.scheme, "key": self.verify_key}
        return {"scheme": self.scheme, "key_digest": H_bytes(self._gate_key)}

    def receiver_material(self):
        """What a receiver needs to verify: the public key, or (stand-in) the shared gate key."""
        return {"scheme": self.scheme, "key": self.verify_key if self.verify_key is not None else self._gate_key}


def verify_signature(material, obj, sig):
    """A receiver's check of `sig` over canonical(obj) with the material from `Signer`."""
    if not isinstance(sig, str) or not material:
        return False
    data = canonical(obj)
    scheme, key = material.get("scheme"), material.get("key")
    try:
        raw = bytes.fromhex(sig)
    except ValueError:
        return False
    if scheme == "ed25519":
        try:
            if ED25519_BACKEND == "cryptography":
                _ed.Ed25519PublicKey.from_public_bytes(bytes.fromhex(key)).verify(raw, data)
                return True
            if ED25519_BACKEND == "pynacl":
                _nacl_signing.VerifyKey(bytes.fromhex(key)).verify(data, raw)
                return True
        except Exception:
            return False
        return False
    if scheme == "hmac-sha256-standin" and isinstance(key, (bytes, bytearray)):
        return hmac.compare_digest(hmac.new(key, data, hashlib.sha256).digest(), raw)
    return False
