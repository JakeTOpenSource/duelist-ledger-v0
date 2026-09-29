"""Duelist Ledger v0: a small, deterministic gate between a scripted agent and a simulated world.

In plain words: an agent must say what it plans to do before it reads anything untrusted.
The gate checks every later action against that plan and against a private house envelope,
writes everything to a tamper-evident diary, and lets a scripted human settle anything held.
"""

CAVEAT = (
    "**Caveat.** v0 runs scripted, maximally compliant agents on one Windows account. "
    "Mediation between processes is by convention, and signatures are HMAC stand-ins. "
    "It demonstrates the gate's semantics and the shape of the security/utility trade-off. "
    "It does NOT measure real-world attack success, physical mediation, or non-repudiation."
)

__version__ = "0.1.0"
