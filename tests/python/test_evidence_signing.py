"""Tests for evidence signing and hash chain integrity."""

import json
import os
import tempfile
from pathlib import Path

import pytest

from src.evidence.signing import (
    EvidenceSigner,
    TamperEvidentLog,
    SignedEvidence,
    EvidenceChainVerifier,
)

try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
    _HAS_CRYPTO = True
except ImportError:
    _HAS_CRYPTO = False


@pytest.fixture
def temp_engine_root(tmp_path):
    root = tmp_path / "engine"
    root.mkdir()
    (root / "keys").mkdir()
    (root / "state").mkdir()
    return root


@pytest.fixture
def signer(temp_engine_root):
    return EvidenceSigner(str(temp_engine_root))


class TestEvidenceSigner:
    @pytest.mark.skipif(not _HAS_CRYPTO, reason="cryptography not installed")
    def test_generate_keypair(self, signer, temp_engine_root):
        pub_key, priv_path = signer.generate_keypair()
        assert len(pub_key) == 64
        assert Path(priv_path).exists()
        assert (temp_engine_root / "keys" / "evidence-key.pem").exists()
        assert (temp_engine_root / "keys" / "evidence-key.passphrase").exists()

    @pytest.mark.skipif(not _HAS_CRYPTO, reason="cryptography not installed")
    def test_sign_and_verify(self, signer):
        pub_key, _ = signer.generate_keypair()
        evidence = {"finding_id": "F001", "status": "VERIFIED", "severity": "P0"}
        signed = signer.sign_evidence(evidence, "ev_001")
        assert signed.evidence_id == "ev_001"
        assert signed.signature
        assert signed.content_hash
        assert signer.verify_signature(signed, pub_key) is True

    @pytest.mark.skipif(not _HAS_CRYPTO, reason="cryptography not installed")
    def test_tampered_evidence_detected(self, signer):
        pub_key, _ = signer.generate_keypair()
        evidence = {"finding_id": "F001", "status": "VERIFIED"}
        signed = signer.sign_evidence(evidence, "ev_001")
        signed.content_hash = "0" * 64
        assert signer.verify_signature(signed, pub_key) is False

    @pytest.mark.skipif(not _HAS_CRYPTO, reason="cryptography not installed")
    def test_signature_is_deterministic_for_same_input(self, signer):
        signer.generate_keypair()
        evidence = {"finding_id": "F002"}
        s1 = signer.sign_evidence(dict(evidence), "ev_001")
        s2 = signer.sign_evidence(dict(evidence), "ev_001")
        assert s1.content_hash == s2.content_hash

    @pytest.mark.skipif(not _HAS_CRYPTO, reason="cryptography not installed")
    def test_fingerprint_consistent(self, signer):
        pub_key, _ = signer.generate_keypair()
        fp1 = signer.compute_fingerprint()
        fp2 = signer.compute_fingerprint()
        assert fp1 == fp2
        assert len(fp1) == 16

    @pytest.mark.skipif(not _HAS_CRYPTO, reason="cryptography not installed")
    def test_export_public_key(self, signer):
        pub_key, _ = signer.generate_keypair()
        exported = signer.export_public_key()
        assert exported == pub_key


class TestHashChain:
    @pytest.mark.skipif(not _HAS_CRYPTO, reason="cryptography not installed")
    def test_chain_integrity_three_entries(self, signer, temp_engine_root):
        signer.generate_keypair()
        log = TamperEvidentLog(str(temp_engine_root), signer)
        e1 = log.append({"data": "entry1"}, "test")
        e2 = log.append({"data": "entry2"}, "test")
        e3 = log.append({"data": "entry3"}, "test")
        assert len(log) == 3
        valid, details = log.verify()
        assert valid is True
        assert details["tampered_entries"] == 0
        assert details["total_entries"] == 3

    @pytest.mark.skipif(not _HAS_CRYPTO, reason="cryptography not installed")
    def test_chain_insertion_detected(self, signer, temp_engine_root):
        signer.generate_keypair()
        log = TamperEvidentLog(str(temp_engine_root), signer)
        e1 = log.append({"data": "entry1"}, "test")
        e3 = log.append({"data": "entry3"}, "test")

        fake = SignedEvidence(
            evidence_id="fake_entry",
            content_hash="a" * 64,
            signature="b" * 128,
            signer="attacker",
            timestamp="2024-01-01T00:00:00",
            public_key_fingerprint="c" * 16,
            chain_index=1,
            previous_hash=e1.content_hash,
        )

        chain = list(log.chain)
        chain.insert(1, fake)
        valid, violations = signer.verify_chain_integrity(chain)
        assert valid is False
        assert len(violations) > 0

    @pytest.mark.skipif(not _HAS_CRYPTO, reason="cryptography not installed")
    def test_chain_deletion_detected(self, signer, temp_engine_root):
        signer.generate_keypair()
        log = TamperEvidentLog(str(temp_engine_root), signer)
        log.append({"data": "entry1"}, "test")
        e2 = log.append({"data": "entry2"}, "test")
        log.append({"data": "entry3"}, "test")

        chain = [log.chain[0], log.chain[2]]
        valid, violations = signer.verify_chain_integrity(chain)
        assert valid is False

    @pytest.mark.skipif(not _HAS_CRYPTO, reason="cryptography not installed")
    def test_chain_reordering_detected(self, signer, temp_engine_root):
        signer.generate_keypair()
        log = TamperEvidentLog(str(temp_engine_root), signer)
        log.append({"data": "A"}, "test")
        log.append({"data": "B"}, "test")

        chain = [log.chain[1], log.chain[0]]
        valid, violations = signer.verify_chain_integrity(chain)
        assert valid is False

    @pytest.mark.skipif(not _HAS_CRYPTO, reason="cryptography not installed")
    def test_genesis_previous_hash(self, signer, temp_engine_root):
        signer.generate_keypair()
        log = TamperEvidentLog(str(temp_engine_root), signer)
        e1 = log.append({"data": "first"}, "test")
        assert e1.previous_hash == TamperEvidentLog.GENESIS_HASH
        assert e1.chain_index == 0

    @pytest.mark.skipif(not _HAS_CRYPTO, reason="cryptography not installed")
    def test_chain_references_previous(self, signer, temp_engine_root):
        signer.generate_keypair()
        log = TamperEvidentLog(str(temp_engine_root), signer)
        e1 = log.append({"data": "1"}, "test")
        e2 = log.append({"data": "2"}, "test")
        e3 = log.append({"data": "3"}, "test")

        expected_prev = hashlib_for_test(
            f"{e1.content_hash}{e1.signature}".encode()
        ).hexdigest()
        assert e2.previous_hash == expected_prev

        expected_prev2 = hashlib_for_test(
            f"{e2.content_hash}{e2.signature}".encode()
        ).hexdigest()
        assert e3.previous_hash == expected_prev2


import hashlib as _hashlib_mod


def hashlib_for_test(data):
    return _hashlib_mod.sha256(data)


class TestTamperEvidentLog:
    @pytest.mark.skipif(not _HAS_CRYPTO, reason="cryptography not installed")
    def test_append_and_verify(self, signer, temp_engine_root):
        signer.generate_keypair()
        log = TamperEvidentLog(str(temp_engine_root), signer)
        for i in range(5):
            log.append({"step": i, "action": f"test_{i}"}, "test")
        valid, details = log.verify()
        assert valid is True
        assert details["total_entries"] == 5

    @pytest.mark.skipif(not _HAS_CRYPTO, reason="cryptography not installed")
    def test_get_entries_since(self, signer, temp_engine_root):
        signer.generate_keypair()
        log = TamperEvidentLog(str(temp_engine_root), signer)
        e1 = log.append({"step": 1}, "test")
        e2 = log.append({"step": 2}, "test")
        since = log.get_entries_since(e2.timestamp)
        assert len(since) >= 1

    @pytest.mark.skipif(not _HAS_CRYPTO, reason="cryptography not installed")
    def test_tamper_report(self, signer, temp_engine_root):
        signer.generate_keypair()
        log = TamperEvidentLog(str(temp_engine_root), signer)
        log.append({"step": 1}, "test")
        report = log.get_tamper_report()
        assert report.total_entries == 1
        assert report.verified_entries == 1
        assert report.tampered_entries == 0
        assert report.chain_health_score == 100.0

    @pytest.mark.skipif(not _HAS_CRYPTO, reason="cryptography not installed")
    def test_export_json(self, signer, temp_engine_root):
        signer.generate_keypair()
        log = TamperEvidentLog(str(temp_engine_root), signer)
        log.append({"step": 1}, "test")
        log.append({"step": 2}, "test")
        output = temp_engine_root / "export.json"
        path = log.export_audit_log(str(output), "json")
        assert Path(path).exists()
        data = json.loads(Path(path).read_text())
        assert len(data["entries"]) == 2

    @pytest.mark.skipif(not _HAS_CRYPTO, reason="cryptography not installed")
    def test_export_jsonl(self, signer, temp_engine_root):
        signer.generate_keypair()
        log = TamperEvidentLog(str(temp_engine_root), signer)
        log.append({"step": 1}, "test")
        output = temp_engine_root / "export.jsonl"
        path = log.export_audit_log(str(output), "jsonl")
        assert Path(path).exists()
        lines = Path(path).read_text().strip().split("\n")
        assert len(lines) == 1

    @pytest.mark.skipif(not _HAS_CRYPTO, reason="cryptography not installed")
    def test_empty_chain_is_valid(self, signer, temp_engine_root):
        signer.generate_keypair()
        log = TamperEvidentLog(str(temp_engine_root), signer)
        valid, details = log.verify()
        assert valid is True
        assert details["total_entries"] == 0

    @pytest.mark.skipif(not _HAS_CRYPTO, reason="cryptography not installed")
    def test_verify_chain_with_wrong_signature(self, signer, temp_engine_root):
        signer.generate_keypair()
        log = TamperEvidentLog(str(temp_engine_root), signer)
        e1 = log.append({"data": "real"}, "test")
        e1.signature = "0" * 128
        log._chain[0] = e1
        log._save_chain()
        valid, details = log.verify()
        assert valid is False
        assert details["tampered_entries"] >= 1


class TestEvidenceChainVerifier:
    @pytest.mark.skipif(not _HAS_CRYPTO, reason="cryptography not installed")
    def test_verify_entry(self, signer, temp_engine_root):
        signer.generate_keypair()
        pub_key_hex = signer.export_public_key()
        signed = signer.sign_evidence({"data": "test"}, "ev_test")
        verifier = EvidenceChainVerifier(pub_key_hex)
        assert verifier.verify_entry(signed) is True

    @pytest.mark.skipif(not _HAS_CRYPTO, reason="cryptography not installed")
    def test_verify_chain(self, signer, temp_engine_root):
        signer.generate_keypair()
        pub_key_hex = signer.export_public_key()
        log = TamperEvidentLog(str(temp_engine_root), signer)
        log.append({"d": 1}, "t")
        log.append({"d": 2}, "t")
        log.append({"d": 3}, "t")
        verifier = EvidenceChainVerifier(pub_key_hex)
        valid, violations = verifier.verify_chain(list(log.chain))
        assert valid is True
        assert len(violations) == 0

    @pytest.mark.skipif(not _HAS_CRYPTO, reason="cryptography not installed")
    def test_verify_chain_detects_tampering(self, signer, temp_engine_root):
        signer.generate_keypair()
        pub_key_hex = signer.export_public_key()
        verifier = EvidenceChainVerifier(pub_key_hex)
        signed = signer.sign_evidence({"data": "test"}, "ev_test")
        signed.signature = "0" * 128
        assert verifier.verify_entry(signed) is False