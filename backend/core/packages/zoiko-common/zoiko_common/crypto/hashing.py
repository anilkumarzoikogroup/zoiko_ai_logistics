"""
Domain-tagged SHA-256 helper (FR-002).

All hashes in Zoiko use a unique domain prefix to prevent cross-type confusion.
This module centralises the hash function so callers never construct raw SHA-256.

Usage:
  from zoiko_common.crypto.hashing import domain_hash, TAGS

  h = domain_hash(TAGS.INGESTION_INVOICE, canonical_bytes)
  assert len(h) == 32   # raw bytes
  assert len(h.hex()) == 64
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass


@dataclass(frozen=True)
class _Tags:
    INGESTION_INVOICE:       bytes = b"zoiko.ingestion.invoice.v1:"
    CANONICAL_INVOICE:       bytes = b"zoiko.canonical.invoice.v1:"
    EVIDENCE_ITEM:           bytes = b"zoiko.evidence.item.v1:"
    FINDING:                 bytes = b"zoiko.finding.v1:"
    PROPOSAL:                bytes = b"zoiko.proposal.v1:"
    GOVERNANCE_DECISION:     bytes = b"zoiko.governance.decision.v1:"
    TOKEN:                   bytes = b"zoiko.token.v1:"
    EXECUTION_ENVELOPE:      bytes = b"zoiko.execution.envelope.v1:"
    ACR:                     bytes = b"zoiko/v1/acr"


TAGS = _Tags()


def domain_hash(domain_tag: bytes, content: bytes) -> bytes:
    """
    SHA-256(domain_tag + content).
    Returns 32 raw bytes. Use .hex() for the 64-char hex string.
    """
    return hashlib.sha256(domain_tag + content).digest()


def domain_hash_hex(domain_tag: bytes, content: bytes) -> str:
    """SHA-256(domain_tag + content) as a 64-char lowercase hex string."""
    return domain_hash(domain_tag, content).hex()
