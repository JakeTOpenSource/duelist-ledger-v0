"""Sealing and reveal checks.

In plain words: a seal is a fingerprint of a record mixed with a secret salt. Publishing the
seal commits you to the record without showing it. At reveal time we recompute the seal from
the revealed record and salt; if it differs, the record was changed after sealing.
"""

import hashlib
import hmac
import json

from .canon import canonical


def commit(obj, salt):
    """Seal = 'sha256:' + sha256(canonical(obj) + salt_bytes)."""
    if isinstance(salt, str):
        salt = salt.encode("utf-8")
    return "sha256:" + hashlib.sha256(canonical(obj) + salt).hexdigest()


def verify_reveal(obj, salt, sealed):
    """True when the revealed object and salt reproduce the sealed commit."""
    if not isinstance(sealed, str):
        return False
    return hmac.compare_digest(commit(obj, salt), sealed)


def salt_candidates(raw):
    """Readings of a salt file, most literal first: exact bytes, then without BOM/edge whitespace."""
    out = [("exact-bytes", raw)]
    body = raw[3:] if raw.startswith(b"\xef\xbb\xbf") else raw
    for name, val in (("no-bom", body), ("stripped", body.strip())):
        if all(val != v for _, v in out):
            out.append((name, val))
    return out


def find_commit(seal_obj):
    """Pull the commit string out of a seal file: a bare string, or the first 'sha256:' value."""
    if isinstance(seal_obj, str):
        return seal_obj.strip()
    if isinstance(seal_obj, dict):
        for key in ("commit", "seal", "hash", "expectations_commit", "sha256"):
            val = seal_obj.get(key)
            if isinstance(val, str) and val.startswith("sha256:"):
                return val
        for key in sorted(seal_obj):
            found = find_commit(seal_obj[key])
            if isinstance(found, str) and found.startswith("sha256:"):
                return found
    if isinstance(seal_obj, list):
        for item in seal_obj:
            found = find_commit(item)
            if isinstance(found, str) and found.startswith("sha256:"):
                return found
    return None


def check_reveal_files(seal_path, expectations_path, salt_path):
    """Verify the seal file against the revealed expectations and salt.

    Returns {ok, commit, computed, salt_reading, expectations, error}.
    """
    result = {"ok": False, "commit": None, "computed": None, "salt_reading": None,
              "expectations": None, "error": None}
    try:
        with open(seal_path, encoding="utf-8-sig") as fh:
            text = fh.read()
        try:
            seal_obj = json.loads(text)
        except ValueError:
            seal_obj = text.strip()
        result["commit"] = find_commit(seal_obj)
        with open(expectations_path, encoding="utf-8-sig") as fh:
            expectations = json.load(fh)
        with open(salt_path, "rb") as fh:
            raw_salt = fh.read()
    except OSError as exc:
        result["error"] = "could not read reveal files: %s" % exc
        return result
    except ValueError as exc:
        result["error"] = "expectations file is not valid JSON: %s" % exc
        return result
    result["expectations"] = expectations
    if not result["commit"]:
        result["error"] = "no sha256 commit found in the seal file"
        return result
    for name, salt in salt_candidates(raw_salt):
        computed = commit(expectations, salt)
        if verify_reveal(expectations, salt, result["commit"]):
            result.update(ok=True, computed=computed, salt_reading=name)
            return result
        if result["computed"] is None:
            result["computed"] = computed
    result["error"] = "seal mismatch: the revealed expectations/salt do not reproduce the sealed commit"
    return result
