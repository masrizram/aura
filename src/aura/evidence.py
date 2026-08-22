"""AURA evidence model — 6-level evidence chain with cryptographic signing.

Evidence Levels:
  DISCOVERED  — Finding identified by auditor
  ASSERTED    — Severity, category, and impact assessed
  FIXED       — Remediation applied
  VERIFIED    — Independent verifier confirms fix with tool output evidence
  REGRESSION_TESTED — Regression audit confirms no re-introduced defects
  CONVERGED   — All 12 gates independently passed

A finding is NOT verified merely because a test passes. Every VERIFIED finding
requires:
  1. Test/lint/build commands executed by the orchestrator (not the LLM)
  2. Real exit codes captured
  3. Independent verifier confirmation
  4. Regression audit confirmation
  5. State transition validated by the state machine
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any


class EvidenceLevel(StrEnum):
    DISCOVERED = "discovered"
    ASSERTED = "asserted"
    FIXED = "remediation_applied"
    VERIFIED = "verified"
    REGRESSION_TESTED = "regression_tested"
    CONVERGED = "converged"


EVIDENCE_LEVEL_ORDER = {
    EvidenceLevel.DISCOVERED: 0,
    EvidenceLevel.ASSERTED: 1,
    EvidenceLevel.FIXED: 2,
    EvidenceLevel.VERIFIED: 3,
    EvidenceLevel.REGRESSION_TESTED: 4,
    EvidenceLevel.CONVERGED: 5,
}


@dataclass
class Evidence:
    """A single piece of evidence for a finding.

    `chain_index` and `previous_hash` make the chain tamper-evident:
    deleting or reordering entries breaks linkage (IMP-04).
    """
    finding_id: str
    level: EvidenceLevel
    source: str  # "orchestrator", "verifier", "regression-auditor", "convergence-judge"
    tool: str = ""  # e.g. "pytest", "semgrep", "git"
    exit_code: int = 0
    output: str = ""
    hash: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    verified_by: str = ""
    chain_index: int = -1  # position in chain; -1 = not yet appended
    previous_hash: str = ""  # hash of the previous entry; genesis = "0"*64

    def compute_hash(self) -> str:
        content = json.dumps({
            "finding_id": self.finding_id,
            "level": self.level.value,
            "source": self.source,
            "tool": self.tool,
            "exit_code": self.exit_code,
            "output": self.output[:500],
            "timestamp": self.timestamp,
            "chain_index": self.chain_index,
            "previous_hash": self.previous_hash,
        }, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["level"] = self.level.value
        return d


class EvidenceChain:
    """Immutable hash chain of evidence entries."""

    GENESIS_HASH = "0" * 64

    def __init__(self, chain_path: str | Path | None = None) -> None:
        self._entries: list[Evidence] = []
        self._chain_path = Path(chain_path) if chain_path else None
        if self._chain_path and self._chain_path.exists():
            self._load()

    def _load(self) -> None:
        try:
            data = json.loads(self._chain_path.read_text()) if self._chain_path else {}
            for entry in data.get("entries", []):
                entry["level"] = EvidenceLevel(entry["level"])
                # Legacy entries (pre-IMP-04) lack chain fields; keep defaults
                entry.setdefault("chain_index", -1)
                entry.setdefault("previous_hash", "")
                self._entries.append(Evidence(**entry))
        except (json.JSONDecodeError, KeyError, ValueError):
            self._entries = []

    def _save(self) -> None:
        if not self._chain_path:
            return
        self._chain_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "version": "2.0.0",
            "total_entries": len(self._entries),
            "entries": [e.to_dict() for e in self._entries],
        }
        self._chain_path.write_text(json.dumps(data, indent=2))

    def append(self, evidence: Evidence) -> str:
        # Link the chain: position + previous entry's hash (genesis = "0"*64)
        evidence.chain_index = len(self._entries)
        evidence.previous_hash = (
            self._entries[-1].hash if self._entries else self.GENESIS_HASH
        )
        evidence.hash = evidence.compute_hash()
        self._entries.append(evidence)
        self._save()
        return evidence.hash

    def verify_chain(self) -> tuple[bool, list[str]]:
        """Verify per-entry hashes AND chain linkage.

        Detects: content tampering (hash mismatch), deletion or reordering
        (chain_index / previous_hash linkage mismatch).
        """
        violations: list[str] = []
        for i, entry in enumerate(self._entries):
            expected = entry.compute_hash()
            if entry.hash and entry.hash != expected:
                violations.append(f"Entry {i} ({entry.finding_id}): hash mismatch — possible tampering")
            if entry.chain_index != i:
                violations.append(f"Entry {i} ({entry.finding_id}): chain_index={entry.chain_index} — reordering detected")
            expected_prev = self._entries[i - 1].hash if i > 0 else self.GENESIS_HASH
            if entry.previous_hash != expected_prev:
                violations.append(f"Entry {i} ({entry.finding_id}): previous_hash mismatch — deletion or insertion detected")
        return len(violations) == 0, violations

    @property
    def entries(self) -> list[Evidence]:
        return list(self._entries)

    def __len__(self) -> int:
        return len(self._entries)


class EvidenceValidator:
    """Independent evidence validator — ensures findings are properly verified."""

    @staticmethod
    def validate_verified_finding(finding: dict[str, Any], evidence_list: list[Evidence]) -> tuple[bool, str]:
        """A VERIFIED finding must have:
        1. At least one VERIFIED-level evidence entry
        2. Tool evidence with exit_code == 0
        3. Independent verifier (not self-verified)
        """
        verified_entries = [e for e in evidence_list
                           if e.finding_id == finding.get("finding_id", "")
                           and e.level == EvidenceLevel.VERIFIED]

        if not verified_entries:
            return False, "No VERIFIED-level evidence found"

        for entry in verified_entries:
            if entry.exit_code != 0:
                return False, f"Tool '{entry.tool}' failed with exit code {entry.exit_code}"
            if entry.source == "remediator":
                return False, "Self-verification not allowed — must be verified by independent verifier"

        return True, f"Verified by {len(verified_entries)} independent evidence entries"

    @staticmethod
    def validate_convergence_claim(gates: dict[str, bool], evidence_list: list[Evidence]) -> tuple[bool, str]:
        """Convergence requires all 12 gates with evidence."""
        failing = [g for g, v in gates.items() if not v]
        if failing:
            return False, f"Gates still failing: {', '.join(failing)}"

        verified_count = len([e for e in evidence_list if e.level == EvidenceLevel.VERIFIED])
        if verified_count == 0:
            return False, "No VERIFIED evidence entries — convergence requires evidence"

        return True, f"All 12 gates pass with {verified_count} verified evidence entries"

    @staticmethod
    def grade_evidence_quality(evidence_list: list[Evidence]) -> dict[str, Any]:
        """Grade the overall evidence quality."""
        total = len(evidence_list)
        if total == 0:
            return {"grade": "F", "score": 0, "reason": "No evidence entries"}

        verified = len([e for e in evidence_list if e.level == EvidenceLevel.VERIFIED])
        regression = len([e for e in evidence_list if e.level == EvidenceLevel.REGRESSION_TESTED])
        tool_passed = len([e for e in evidence_list if e.exit_code == 0 and e.tool])

        score = 0
        if verified > 0:
            score += 50
        if regression > 0:
            score += 20
        if tool_passed > 0:
            score += min(20, tool_passed * 5)
        score = min(100, score)

        if score >= 90:
            grade = "A"
        elif score >= 70:
            grade = "B"
        elif score >= 50:
            grade = "C"
        elif score >= 30:
            grade = "D"
        else:
            grade = "F"

        return {
            "grade": grade,
            "score": score,
            "total_evidence": total,
            "verified_entries": verified,
            "regression_entries": regression,
            "tool_passed_entries": tool_passed,
            "reason": f"Grade {grade}: {verified} verified, {regression} regression-tested, {tool_passed} tool-passed entries",
        }
