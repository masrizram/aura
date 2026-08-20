"""
AURA Evidence Integrity & Historical Analytics Package.

Exports:
    EvidenceSigner, TamperEvidentLog, SignedEvidence, EvidenceChainVerifier
    ImmutableStorage, TimestampClient

Package structure:
    signing    - Tamper-evident logging with Ed25519/GPG signing and hash chains
    timestamp  - RFC 3161 timestamping and content-addressable storage
"""

from .signing import (
    EvidenceSigner,
    TamperEvidentLog,
    SignedEvidence,
    EvidenceChainVerifier,
    TamperReport,
)
from .timestamp import TimestampClient, ImmutableStorage

__all__ = [
    "EvidenceSigner",
    "TamperEvidentLog",
    "SignedEvidence",
    "EvidenceChainVerifier",
    "TamperReport",
    "TimestampClient",
    "ImmutableStorage",
]