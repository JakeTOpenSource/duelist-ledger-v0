"""Duelist Ledger v0: a small, deterministic gate between a scripted agent and a simulated world.

In plain words: an agent must say what it plans to do before it reads anything untrusted.
The gate checks every later action against that plan and against a private house envelope,
writes everything to a tamper-evident diary, and lets a scripted human settle anything held.
"""

from .canon import ED25519_AVAILABLE, ED25519_BACKEND, SIGNATURE_SCHEME

CONTRACT = "0.3"  # the contract version this build conforms to (BUILD_SPEC.md, tag contract-v0.3)
CONTRACT_DIR = "v" + CONTRACT  # run artifacts are namespaced by contract version: sealed/v0.3/, scenarios/v0.3/

SIGNATURES_RAN = (
    "Ed25519 (via `%s`)" % ED25519_BACKEND if ED25519_AVAILABLE
    else "HMAC-SHA256 stand-ins (neither `cryptography` nor `pynacl` was available)")

# The caveat line of spec sec. 0 (A4.4). It opens every report and the README; the last sentence
# states which signatures ran in this process, as the spec requires.
CAVEAT = (
    "**Caveat.** v0 runs scripted, maximally compliant agents on one Windows account. "
    "Mediation between processes is by convention, and signatures are Ed25519 only when the "
    "optional package of sec. 0 is present, else HMAC stand-ins; the report states which ran. "
    "It demonstrates the gate's semantics and the shape of the security/utility trade-off. "
    "It does NOT measure real-world attack success, physical mediation, or non-repudiation. "
    "Signatures in this run: %s." % SIGNATURES_RAN
)

__version__ = "0.3.0"
