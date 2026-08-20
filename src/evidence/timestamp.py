"""
RFC 3161 timestamp client for evidence notarization.
Requests verifiable timestamps from trusted timestamp authorities.

Also provides ImmutableStorage: content-addressable evidence storage
(like git objects) that makes modification detectable by hash mismatch.
"""

import hashlib
import json
import os
import struct
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .signing import SignedEvidence


class TimestampClient:
    DEFAULT_TSA_URLS = [
        "http://timestamp.digicert.com",
        "http://timestamp.globalsign.com",
        "http://timestamp.sectigo.com",
    ]

    def __init__(self, tsa_urls: Optional[List[str]] = None):
        self.tsa_urls = tsa_urls or self.DEFAULT_TSA_URLS

    def timestamp(self, data: bytes) -> Optional[Dict[str, Any]]:
        ts_query = self._build_rfc3161_query(data)
        for url in self.tsa_urls:
            result = self._send_rfc3161_request(url, ts_query)
            if result is not None:
                return result
        return None

    def verify_timestamp(self, data: bytes, ts_token: bytes) -> bool:
        try:
            data_hash = hashlib.sha256(data).digest()
            extracted_hash = self._extract_hash_from_token(ts_token)
            return extracted_hash == data_hash
        except Exception:
            return False

    def timestamp_evidence(self, evidence: SignedEvidence) -> SignedEvidence:
        data = json.dumps(evidence.to_dict(), sort_keys=True).encode("utf-8")
        ts_result = self.timestamp(data)
        if ts_result:
            evidence.timestamp = ts_result["timestamp"]
        return evidence

    def _build_rfc3161_query(self, data: bytes) -> bytes:
        data_hash = hashlib.sha256(data).digest()
        nonce = struct.pack(">Q", int(time.time() * 1_000_000))
        request = (
            self._encode_asn1_length(0x30, 0)
            + self._encode_asn1_sequence(
                self._encode_asn1_integer(1)
                + self._encode_asn1_sequence(
                    self._encode_asn1_oid("2.16.840.1.101.3.4.2.1")
                    + self._encode_asn1_null()
                )
                + self._encode_asn1_octet_string(data_hash)
                + self._encode_asn1_integer(int.from_bytes(nonce, "big"), signed=False)
            )
        )
        total_len = len(request) - 4
        header = bytes([0x30]) + self._encode_asn1_length_value(total_len)
        return header + request[4:]

    @staticmethod
    def _encode_asn1_length(tag: int, length: int) -> bytes:
        return bytes([tag]) + TimestampClient._encode_asn1_length_value(length)

    @staticmethod
    def _encode_asn1_length_value(length: int) -> bytes:
        if length < 128:
            return bytes([length])
        length_bytes = []
        remaining = length
        while remaining > 0:
            length_bytes.insert(0, remaining & 0xFF)
            remaining >>= 8
        return bytes([0x80 | len(length_bytes)] + length_bytes)

    @staticmethod
    def _encode_asn1_integer(value: int, signed: bool = True) -> bytes:
        if value == 0:
            return b"\x02\x01\x00"
        raw = []
        remaining = abs(value)
        while remaining > 0:
            raw.insert(0, remaining & 0xFF)
            remaining >>= 8
        if signed and (raw[0] & 0x80):
            raw.insert(0, 0)
        content = bytes(raw)
        return bytes([0x02]) + TimestampClient._encode_asn1_length_value(len(content)) + content

    @staticmethod
    def _encode_asn1_sequence(content: bytes) -> bytes:
        return bytes([0x30]) + TimestampClient._encode_asn1_length_value(len(content)) + content

    @staticmethod
    def _encode_asn1_oid(oid_str: str) -> bytes:
        parts = [int(x) for x in oid_str.split(".")]
        encoded = bytes([40 * parts[0] + parts[1]])
        for part in parts[2:]:
            chunks = []
            while part > 0:
                chunks.insert(0, part & 0x7F)
                part >>= 7
            for i, chunk in enumerate(chunks):
                if i < len(chunks) - 1:
                    chunks[i] |= 0x80
            encoded += bytes(chunks)
        return bytes([0x06]) + TimestampClient._encode_asn1_length_value(len(encoded)) + encoded

    @staticmethod
    def _encode_asn1_null() -> bytes:
        return b"\x05\x00"

    @staticmethod
    def _encode_asn1_octet_string(data: bytes) -> bytes:
        return bytes([0x04]) + TimestampClient._encode_asn1_length_value(len(data)) + data

    def _send_rfc3161_request(self, tsa_url: str, ts_query: bytes) -> Optional[Dict[str, Any]]:
        try:
            import urllib.request
            req = urllib.request.Request(
                tsa_url,
                data=ts_query,
                headers={"Content-Type": "application/timestamp-query"},
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                ts_token = resp.read()
                return {
                    "token": ts_token.hex(),
                    "token_raw": ts_token,
                    "tsa_url": tsa_url,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "status": "received",
                }
        except Exception:
            return None

    @staticmethod
    def _extract_hash_from_token(token: bytes) -> Optional[bytes]:
        try:
            idx = 0
            while idx < len(token):
                if token[idx] == 0x04:
                    length = token[idx + 1]
                    if length > 0x80:
                        num_length_bytes = length - 0x80
                        length = int.from_bytes(token[idx + 2:idx + 2 + num_length_bytes], "big")
                        idx += num_length_bytes + 2
                    else:
                        idx += 2
                    candidate = token[idx:idx + length]
                    if len(candidate) == 32:
                        return candidate
                    idx += length
                else:
                    idx += 1
            return None
        except (IndexError, ValueError):
            return None


class ImmutableStorage:
    def __init__(self, storage_root: str):
        self.storage_root = Path(storage_root)
        self.objects_dir = self.storage_root / "objects"

    def store(self, evidence: Dict[str, Any]) -> str:
        from .signing import _make_serializable
        data = _make_serializable(evidence)
        content_json = json.dumps(data, sort_keys=True, separators=(",", ":"))
        content_hash = hashlib.sha256(content_json.encode("utf-8")).hexdigest()

        prefix = content_hash[:2]
        suffix = content_hash[2:]
        obj_dir = self.objects_dir / prefix
        obj_dir.mkdir(parents=True, exist_ok=True)
        obj_path = obj_dir / suffix

        if not obj_path.exists():
            stored = {
                "content_hash": content_hash,
                "stored_at": datetime.now(timezone.utc).isoformat(),
                "storage_version": "1.0.0",
                "data": data,
            }
            temp_path = obj_path.with_suffix(f".tmp.{os.urandom(4).hex()}")
            temp_path.write_text(json.dumps(stored, indent=2), encoding="utf-8")
            temp_path.replace(obj_path)

        return content_hash

    def retrieve(self, content_hash: str) -> Optional[Dict[str, Any]]:
        if len(content_hash) < 4:
            return None
        prefix = content_hash[:2]
        suffix = content_hash[2:]
        obj_path = self.objects_dir / prefix / suffix
        if not obj_path.exists():
            return None
        try:
            stored = json.loads(obj_path.read_text(encoding="utf-8"))
            return stored.get("data", stored)
        except (json.JSONDecodeError, KeyError):
            return None

    def exists(self, content_hash: str) -> bool:
        if len(content_hash) < 4:
            return False
        return (self.objects_dir / content_hash[:2] / content_hash[2:]).exists()

    def verify_integrity(self, content_hash: str) -> bool:
        if len(content_hash) < 4:
            return False
        obj_path = self.objects_dir / content_hash[:2] / content_hash[2:]
        if not obj_path.exists():
            return False
        try:
            stored = json.loads(obj_path.read_text(encoding="utf-8"))
            data = stored.get("data", stored)
            content_json = json.dumps(data, sort_keys=True, separators=(",", ":"))
            computed = hashlib.sha256(content_json.encode("utf-8")).hexdigest()
            return computed == content_hash
        except (json.JSONDecodeError, KeyError):
            return False

    def list_objects(self) -> List[str]:
        hashes: List[str] = []
        if not self.objects_dir.exists():
            return hashes
        for prefix_dir in self.objects_dir.iterdir():
            if prefix_dir.is_dir() and len(prefix_dir.name) == 2:
                for obj_file in prefix_dir.iterdir():
                    if obj_file.is_file():
                        hashes.append(prefix_dir.name + obj_file.name)
        return hashes

    def gc(self) -> int:
        removed = 0
        if not self.objects_dir.exists():
            return removed
        for prefix_dir in self.objects_dir.iterdir():
            if not prefix_dir.is_dir():
                continue
            for obj_file in prefix_dir.iterdir():
                if obj_file.is_file():
                    content_hash = prefix_dir.name + obj_file.name
                    try:
                        stored = json.loads(obj_file.read_text(encoding="utf-8"))
                        data = stored.get("data", stored)
                        content_json = json.dumps(data, sort_keys=True, separators=(",", ":"))
                        computed = hashlib.sha256(content_json.encode("utf-8")).hexdigest()
                        if computed != content_hash:
                            obj_file.unlink()
                            removed += 1
                    except (json.JSONDecodeError, OSError):
                        obj_file.unlink()
                        removed += 1
            try:
                remaining = list(prefix_dir.iterdir())
                if not remaining:
                    prefix_dir.rmdir()
            except OSError:
                pass
        return removed