"""Policy loading, the policy fingerprint, and destination classes.

In plain words: reads the house rules (config/policy.json) and the tool table
(config/sinks.json), lets a scenario adjust only the knobs it is allowed to adjust, and sorts
any destination into principal / internal / contact / vendor / external.
"""

import copy
import json
import os
from urllib.parse import urlsplit

from .canon import H

OVERRIDABLE = ("budgets", "tier3_money", "fuse", "escrow_window", "asset_flows")


def load_config(config_dir):
    """Return (policy, sinks) from the config folder."""
    with open(os.path.join(config_dir, "policy.json"), encoding="utf-8") as fh:
        policy = json.load(fh)
    with open(os.path.join(config_dir, "sinks.json"), encoding="utf-8") as fh:
        sinks = json.load(fh)
    return policy, sinks


def effective_policy(base, overrides):
    """Apply scenario overrides. Only OVERRIDABLE keys count; dict knobs merge one level deep.

    Returns (policy, ignored_keys).
    """
    policy = copy.deepcopy(base)
    ignored = []
    for key, val in sorted((overrides or {}).items()):
        if key not in OVERRIDABLE:
            ignored.append(key)
            continue
        if isinstance(val, dict) and isinstance(policy.get(key), dict):
            merged = dict(policy[key])
            merged.update(copy.deepcopy(val))
            policy[key] = merged
        else:
            policy[key] = copy.deepcopy(val)
    return policy, ignored


def policy_hash(policy, sinks):
    return H({"policy": policy, "sinks": sinks})


def domain_of(value):
    """The lower-cased domain of an address or URL; None when there is none."""
    if not isinstance(value, str) or not value:
        return None
    if "://" in value:
        host = urlsplit(value).hostname
        return host.lower() if host else None
    if "@" in value:
        return value.rsplit("@", 1)[1].strip().lower() or None
    return None


def dest_class(value, policy, registries):
    """principal, internal, contact, vendor or external (checked in that order)."""
    if value == policy.get("principal"):
        return "principal"
    dom = domain_of(value)
    internal = (policy.get("internal_domain") or "").lower()
    if dom and internal and (dom == internal or dom.endswith("." + internal)):
        return "internal"
    if value in (registries.get("contacts") or []):
        return "contact"
    if value in (registries.get("vendors") or []):
        return "vendor"
    return "external"
