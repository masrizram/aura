"""
Cryptographic signing and verification for evidence chains.
Uses Ed25519 for tamper-evident logging with hash-chain integrity.

Architecture:
    EvidenceSigner  - Key generation, signing, verification (Ed25519 primary, GPG fallback)
    TamperEvidentLog - Append-only hash-chained log with full-chain verification
    EvidenceChainVerifier - Standalone chain integrity checker
"""

import hashlib
import hmac
import json
import os
import struct
import subprocess
import tempfile
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey,
        Ed25519PublicKey,
    )
    from cryptography.hazmat.primitives.serialization import (
        Encoding,
        NoEncryption,
        PrivateFormat,
        PublicFormat,
        BestAvailableEncryption,
        load_pem_private_key,
        load_pem_public_key,
    )
    from cryptography.hazmat.primitives import serialization
    from cryptography.exceptions import InvalidSignature
    _HAS_CRYPTOGRAPHY = True
except ImportError:
    _HAS_CRYPTOGRAPHY = False


@dataclass
class SignedEvidence:
    evidence_id: str
    content_hash: str
    signature: str
    signer: str
    timestamp: str
    public_key_fingerprint: str
    chain_index: int
    previous_hash: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SignedEvidence":
        return cls(**{
            k: data.get(k, "" if k != "chain_index" else 0)
            for k in ["evidence_id", "content_hash", "signature", "signer",
                       "timestamp", "public_key_fingerprint", "chain_index", "previous_hash"]
        })


@dataclass
class TamperReport:
    total_entries: int
    verified_entries: int
    tampered_entries: int
    chain_health_score: float
    violations: List[str]
    detailed_status: Dict[str, Any]


class EvidenceSigner:
    KEY_SIZE = 32

    def __init__(self, engine_root: str, key_path: Optional[str] = None):
        self.engine_root = Path(engine_root)
        self.key_path = Path(key_path) if key_path else self.engine_root / "keys" / "evidence-key.pem"
        self._private_key: Optional[Ed25519PrivateKey] = None
        self._public_key: Optional[Ed25519PublicKey] = None
        self._public_key_pem: Optional[str] = None
        self._fingerprint: Optional[str] = None

        if not _HAS_CRYPTOGRAPHY:
            raise ImportError(
                "cryptography package is required for evidence signing. "
                "Install with: pip install cryptography"
            )

    def generate_keypair(self) -> Tuple[str, str]:
        self.key_path.parent.mkdir(parents=True, exist_ok=True)
        private_key = Ed25519PrivateKey.generate()
        public_key = private_key.public_key()

        passphrase = os.urandom(32).hex()
        encrypted_pem = private_key.private_bytes(
            encoding=Encoding.PEM,
            format=PrivateFormat.PKCS8,
            encryption_algorithm=BestAvailableEncryption(passphrase.encode("utf-8")),
        )

        with open(self.key_path, "wb") as f:
            f.write(encrypted_pem)

        passphrase_path = self.key_path.with_suffix(".passphrase")
        with open(passphrase_path, "w") as f:
            f.write(passphrase)

        self._load_keys()

        public_bytes = public_key.public_bytes(
            encoding=Encoding.Raw, format=PublicFormat.Raw
        )
        public_key_b64 = public_bytes.hex()
        self._fingerprint = hashlib.sha256(public_bytes).hexdigest()[:16]

        return public_key_b64, str(self.key_path)

    def load_keypair(self, passphrase: Optional[str] = None) -> bool:
        if not self.key_path.exists():
            return False
        if passphrase is None:
            passphrase = os.environ.get("AURA_EVIDENCE_KEY_PASSPHRASE")
        if passphrase is None:
            pp_path = self.key_path.with_suffix(".passphrase")
            if pp_path.exists():
                import getpass
                import logging
                _log = logging.getLogger(__name__)
                _log.warning(
                    "Evidence signing key passphrase loaded from plaintext file: %s. "
                    "Set AURA_EVIDENCE_KEY_PASSPHRASE environment variable instead.",
                    pp_path
                )
                passphrase = pp_path.read_text().strip()
        if passphrase is None:
            raise ValueError("No passphrase available for private key. "
                             "Set AURA_EVIDENCE_KEY_PASSPHRASE environment variable.")

        with open(self.key_path, "rb") as f:
            key_data = f.read()

        try:
            if b"ENCRYPTED" in key_data[:100]:
                self._private_key = load_pem_private_key(
                    key_data, password=passphrase.encode("utf-8")
                )
            else:
                self._private_key = load_pem_private_key(key_data, password=None)
            return True
        except Exception:
            return False

    def _load_keys(self) -> None:
        if self._private_key is not None:
            return
        if not self.key_path.exists():
            raise FileNotFoundError(f"Key file not found: {self.key_path}")
        if not self.load_keypair():
            raise ValueError("Failed to load key pair")

    def _ensure_loaded(self) -> None:
        if self._private_key is None:
            self._load_keys()

    def _get_public_key(self) -> Ed25519PublicKey:
        self._ensure_loaded()
        return self._private_key.public_key()

    def sign_evidence(self, evidence: Dict[str, Any], evidence_id: str) -> SignedEvidence:
        self._ensure_loaded()

        serializable = _make_serializable(evidence)
        content_json = json.dumps(serializable, sort_keys=True, separators=(",", ":"))
        content_hash = hashlib.sha256(content_json.encode("utf-8")).hexdigest()

        signing_message = f"{evidence_id}:{content_hash}".encode("utf-8")
        signature_bytes = self._private_key.sign(signing_message)
        signature_hex = signature_bytes.hex()

        pub_key = self._get_public_key()
        raw_pub = pub_key.public_bytes(Encoding.Raw, PublicFormat.Raw)
        fingerprint = hashlib.sha256(raw_pub).hexdigest()[:16]

        return SignedEvidence(
            evidence_id=evidence_id,
            content_hash=content_hash,
            signature=signature_hex,
            signer="aura-evidence-signer",
            timestamp=datetime.now(timezone.utc).isoformat(),
            public_key_fingerprint=fingerprint,
            chain_index=-1,
            previous_hash="",
        )

    def verify_signature(self, signed: SignedEvidence, public_key_hex: Optional[str] = None) -> bool:
        try:
            if public_key_hex:
                pub_bytes = bytes.fromhex(public_key_hex)
            elif signed.public_key_fingerprint and self._public_key_pem:
                pub_key = self._get_public_key()
                pub_bytes = pub_key.public_bytes(Encoding.Raw, PublicFormat.Raw)
                fp = hashlib.sha256(pub_bytes).hexdigest()[:16]
                if fp != signed.public_key_fingerprint:
                    return False
            else:
                pub_key = self._get_public_key()
                pub_bytes = pub_key.public_bytes(Encoding.Raw, PublicFormat.Raw)

            public_key = Ed25519PublicKey.from_public_bytes(pub_bytes)
            signing_message = f"{signed.evidence_id}:{signed.content_hash}".encode("utf-8")
            signature_bytes = bytes.fromhex(signed.signature)
            public_key.verify(signature_bytes, signing_message)
            return True
        except (InvalidSignature, ValueError):
            return False

    def create_hash_chain_entry(
        self, evidence: Dict[str, Any], previous_entry: Optional[SignedEvidence]
    ) -> SignedEvidence:
        self._ensure_loaded()

        serializable = _make_serializable(evidence)
        chain_index = 0
        previous_hash = "0000000000000000000000000000000000000000000000000000000000000000"

        if previous_entry is not None:
            chain_index = previous_entry.chain_index + 1
            previous_hash = previous_entry.content_hash

            if previous_entry.signature:
                previous_hash = hashlib.sha256(
                    f"{previous_entry.content_hash}{previous_entry.signature}".encode("utf-8")
                ).hexdigest()

        evidence_id = f"ev_{hashlib.sha256(json.dumps(serializable, sort_keys=True).encode()).hexdigest()[:12]}"

        content_with_chain = {
            "evidence": serializable,
            "chain_index": chain_index,
            "previous_hash": previous_hash,
        }
        content_json = json.dumps(content_with_chain, sort_keys=True, separators=(",", ":"))
        content_hash = hashlib.sha256(content_json.encode("utf-8")).hexdigest()

        signing_message = f"{evidence_id}:{content_hash}".encode("utf-8")
        signature_bytes = self._private_key.sign(signing_message)

        pub_key = self._get_public_key()
        raw_pub = pub_key.public_bytes(Encoding.Raw, PublicFormat.Raw)
        fingerprint = hashlib.sha256(raw_pub).hexdigest()[:16]

        return SignedEvidence(
            evidence_id=evidence_id,
            content_hash=content_hash,
            signature=signature_bytes.hex(),
            signer="aura-evidence-signer",
            timestamp=datetime.now(timezone.utc).isoformat(),
            public_key_fingerprint=fingerprint,
            chain_index=chain_index,
            previous_hash=previous_hash,
        )

    def verify_chain_integrity(self, chain: List[SignedEvidence]) -> Tuple[bool, List[str]]:
        violations: List[str] = []
        if not chain:
            return True, violations

        for i, entry in enumerate(chain):
            expected_index = i
            if entry.chain_index != expected_index:
                violations.append(
                    f"Entry {i} (id={entry.evidence_id}): chain_index={entry.chain_index}, "
                    f"expected={expected_index} — possible insertion or deletion"
                )

            if i > 0:
                prev = chain[i - 1]
                expected_prev_hash = prev.content_hash
                if prev.signature:
                    expected_prev_hash = hashlib.sha256(
                        f"{prev.content_hash}{prev.signature}".encode("utf-8")
                    ).hexdigest()
                if entry.previous_hash != expected_prev_hash:
                    violations.append(
                        f"Entry {i} (id={entry.evidence_id}): previous_hash mismatch. "
                        f"Expected {expected_prev_hash[:16]}..., got {entry.previous_hash[:16]}..."
                    )

        genesis_prev = "0000000000000000000000000000000000000000000000000000000000000000"
        if chain and chain[0].previous_hash != genesis_prev:
            violations.append(
                f"Genesis entry (id={chain[0].evidence_id}): previous_hash should be "
                f"{genesis_prev[:16]}..., got {chain[0].previous_hash[:16]}..."
            )

        return len(violations) == 0, violations

    def verify_gpg_signature(self, data: bytes, signature: str) -> bool:
        with tempfile.NamedTemporaryFile(suffix=".sig", delete=False) as sig_file:
            sig_file.write(signature.encode("utf-8"))
            sig_path = sig_file.name
        with tempfile.NamedTemporaryFile(suffix=".data", delete=False) as data_file:
            data_file.write(data)
            data_path = data_file.name

        try:
            result = subprocess.run(
                ["gpg", "--verify", sig_path, data_path],
                capture_output=True, text=True, timeout=15,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False
        finally:
            for p in (sig_path, data_path):
                try:
                    os.unlink(p)
                except OSError:
                    pass

    def compute_fingerprint(self) -> str:
        pub_key = self._get_public_key()
        raw_pub = pub_key.public_bytes(Encoding.Raw, PublicFormat.Raw)
        return hashlib.sha256(raw_pub).hexdigest()[:16]

    def export_public_key(self) -> str:
        pub_key = self._get_public_key()
        return pub_key.public_bytes(Encoding.Raw, PublicFormat.Raw).hex()


class TamperEvidentLog:
    GENESIS_HASH = "0000000000000000000000000000000000000000000000000000000000000000"

    def __init__(self, engine_root: str, signer: EvidenceSigner):
        self.engine_root = Path(engine_root)
        self.log_path = self.engine_root / "state" / "evidence-chain.json"
        self.signer = signer
        self._chain: List[SignedEvidence] = []
        self._load_chain()

    def _load_chain(self) -> None:
        if not self.log_path.exists():
            self._chain = []
            return
        try:
            raw = self.log_path.read_text(encoding="utf-8")
            if not raw.strip():
                self._chain = []
                return
            data = json.loads(raw)
            entries = data.get("entries", []) if isinstance(data, dict) else data
            self._chain = [SignedEvidence.from_dict(e) for e in entries]
        except (json.JSONDecodeError, KeyError):
            self._chain = []

    def _save_chain(self) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        chain_data = {
            "version": "2.0.0",
            "created_at": self._chain[0].timestamp if self._chain else datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "total_entries": len(self._chain),
            "last_entry_id": self._chain[-1].evidence_id if self._chain else None,
            "entries": [e.to_dict() for e in self._chain],
        }
        temp_path = self.log_path.with_suffix(f".tmp.{os.urandom(4).hex()}")
        temp_path.write_text(json.dumps(chain_data, indent=2), encoding="utf-8")
        temp_path.replace(self.log_path)

    def append(self, evidence: Dict[str, Any], evidence_type: str) -> SignedEvidence:
        evidence["_type"] = evidence_type
        previous = self._chain[-1] if self._chain else None
        entry = self.signer.create_hash_chain_entry(evidence, previous)
        if previous is None and self._chain:
            previous = self._chain[-1]
        self._chain.append(entry)
        self._save_chain()
        return entry

    def verify(self) -> Tuple[bool, Dict[str, Any]]:
        violations: List[str] = []
        chain_valid, chain_violations = self.signer.verify_chain_integrity(self._chain)
        violations.extend(chain_violations)

        verified = 0
        tampered = 0
        for entry in self._chain:
            sig_valid = self.signer.verify_signature(entry)
            if sig_valid:
                verified += 1
            else:
                tampered += 1
                violations.append(f"Signature verification failed for entry {entry.evidence_id}")

        prev_ts: Optional[datetime] = None
        for entry in self._chain:
            try:
                ts = datetime.fromisoformat(entry.timestamp.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                continue
            if prev_ts and ts < prev_ts:
                violations.append(
                    f"Timestamp non-monotonic at {entry.evidence_id}: "
                    f"{entry.timestamp} before previous {self._chain[self._chain.index(entry) - 1].timestamp}"
                )
            prev_ts = ts

        total = len(self._chain)
        score = 100.0
        if total > 0:
            if tampered > 0:
                score -= (tampered / total) * 70.0
            if not chain_valid:
                score -= 30.0
            score = max(0.0, score)

        is_valid = chain_valid and tampered == 0 and len(violations) == 0

        return is_valid, {
            "violations": violations,
            "verified_entries": verified,
            "tampered_entries": tampered,
            "total_entries": total,
            "chain_health_score": round(score, 1),
            "chain_integrity_valid": chain_valid,
        }

    def get_entries_since(self, timestamp: str) -> List[SignedEvidence]:
        try:
            threshold = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except ValueError:
            return []
        result: List[SignedEvidence] = []
        for entry in self._chain:
            try:
                entry_ts = datetime.fromisoformat(entry.timestamp.replace("Z", "+00:00"))
                if entry_ts >= threshold:
                    result.append(entry)
            except (ValueError, AttributeError):
                continue
        return result

    def export_audit_log(self, output_path: str, format: str = "json") -> str:
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)

        if format == "json":
            chain_data = {
                "version": "2.0.0",
                "exported_at": datetime.now(timezone.utc).isoformat(),
                "total_entries": len(self._chain),
                "entries": [e.to_dict() for e in self._chain],
            }
            output.write_text(json.dumps(chain_data, indent=2), encoding="utf-8")

        elif format == "jsonl":
            lines = [json.dumps(e.to_dict()) for e in self._chain]
            output.write_text("\n".join(lines) + "\n", encoding="utf-8")

        elif format == "csv":
            import csv
            with open(str(output), "w", newline="", encoding="utf-8") as f:
                if self._chain:
                    writer = csv.DictWriter(f, fieldnames=self._chain[0].to_dict().keys())
                    writer.writeheader()
                    for entry in self._chain:
                        writer.writerow(entry.to_dict())
                else:
                    f.write("evidence_id,content_hash,signature,signer,timestamp,public_key_fingerprint,chain_index,previous_hash\n")

        return str(output)

    def get_tamper_report(self) -> TamperReport:
        is_valid, details = self.verify()
        return TamperReport(
            total_entries=details["total_entries"],
            verified_entries=details["verified_entries"],
            tampered_entries=details["tampered_entries"],
            chain_health_score=details["chain_health_score"],
            violations=details["violations"],
            detailed_status=details,
        )

    @property
    def chain(self) -> List[SignedEvidence]:
        return list(self._chain)

    def __len__(self) -> int:
        return len(self._chain)

    def __getitem__(self, index: int) -> SignedEvidence:
        return self._chain[index]


class EvidenceChainVerifier:
    def __init__(self, public_key_hex: str):
        try:
            pub_bytes = bytes.fromhex(public_key_hex)
            self._public_key = Ed25519PublicKey.from_public_bytes(pub_bytes)
            self._fingerprint = hashlib.sha256(pub_bytes).hexdigest()[:16]
        except Exception:
            self._public_key = None
            self._fingerprint = ""

    def verify_entry(self, entry: SignedEvidence) -> bool:
        if self._public_key is None:
            return False
        try:
            signing_message = f"{entry.evidence_id}:{entry.content_hash}".encode("utf-8")
            signature_bytes = bytes.fromhex(entry.signature)
            self._public_key.verify(signature_bytes, signing_message)
            return True
        except (InvalidSignature, ValueError):
            return False

    def verify_chain(self, entries: List[SignedEvidence]) -> Tuple[bool, List[str]]:
        violations: List[str] = []
        for i, entry in enumerate(entries):
            if entry.chain_index != i:
                violations.append(
                    f"Index mismatch at position {i}: expected {i}, got {entry.chain_index}"
                )
            if not self.verify_entry(entry):
                violations.append(f"Signature verification failed for entry {entry.evidence_id}")
            if i > 0:
                prev = entries[i - 1]
                expected_prev = prev.content_hash
                if prev.signature:
                    expected_prev = hashlib.sha256(
                        f"{prev.content_hash}{prev.signature}".encode("utf-8")
                    ).hexdigest()
                if entry.previous_hash != expected_prev:
                    violations.append(
                        f"Hash chain broken at entry {entry.evidence_id}: "
                        f"previous_hash does not match predecessor"
                    )
        return len(violations) == 0, violations


def _make_serializable(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): _make_serializable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_make_serializable(v) for v in obj]
    if isinstance(obj, (datetime,)):
        return obj.isoformat()
    if isinstance(obj, (int, float, str, bool)) or obj is None:
        return obj
    return str(obj)