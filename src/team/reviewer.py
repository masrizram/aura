"""Finding review workflow for AURA team collaboration.

Enforces AURA state machine: OPEN→IN_PROGRESS→FIXED→VERIFYING→VERIFIED.
Human reviewers must approve remediation before findings close.
Aligns with convergence gate validation (independent-verifier evidence).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .models import (
    FindingResolution,
    FindingReview,
    ApprovalChain,
    TeamConfig,
    TeamMember,
    TeamRole,
)


class ReviewWorkflow:
    def __init__(self, team_config: TeamConfig, state_dir: str):
        self.config = team_config
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self._reviews_file = self.state_dir / "finding-reviews.json"
        self._approval_chains_file = self.state_dir / "approval-chains.json"
        self._reviews: Dict[str, List[FindingReview]] = {}
        self._approval_chains: Dict[str, ApprovalChain] = {}
        self._load()

    def _load(self) -> None:
        self._load_reviews()
        self._load_approval_chains()

    def _load_reviews(self) -> None:
        if not self._reviews_file.exists():
            return
        try:
            data = json.loads(self._reviews_file.read_text(encoding="utf-8"))
            for fid, reviews_list in data.items():
                self._reviews[fid] = [
                    FindingReview(
                        finding_id=r["finding_id"],
                        reviewer_id=r["reviewer_id"],
                        resolution=FindingResolution(r["resolution"]),
                        comments=r["comments"],
                        reviewed_at=r["reviewed_at"],
                        verification_evidence=r.get("verification_evidence"),
                    )
                    for r in reviews_list
                ]
        except (json.JSONDecodeError, KeyError, IOError, ValueError):
            self._reviews = {}

    def _load_approval_chains(self) -> None:
        if not self._approval_chains_file.exists():
            return
        try:
            data = json.loads(self._approval_chains_file.read_text(encoding="utf-8"))
            for fid, chain_data in data.items():
                self._approval_chains[fid] = ApprovalChain(
                    finding_id=chain_data["finding_id"],
                    approvals=chain_data.get("approvals", []),
                    required_approvals=chain_data.get("required_approvals", 1),
                    is_complete=chain_data.get("is_complete", False),
                )
        except (json.JSONDecodeError, KeyError, IOError):
            self._approval_chains = {}

    def _save_reviews(self) -> None:
        data = {
            fid: [r.to_dict() for r in reviews]
            for fid, reviews in self._reviews.items()
        }
        self._reviews_file.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _save_approval_chains(self) -> None:
        data = {fid: c.to_dict() for fid, c in self._approval_chains.items()}
        self._approval_chains_file.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _load_current_findings(self) -> Dict[str, Dict[str, Any]]:
        findings_path = self.state_dir.parent / "state" / "findings.json"
        if not findings_path.exists():
            return {}
        try:
            data = json.loads(findings_path.read_text(encoding="utf-8"))
            return {f["id"]: f for f in data.get("findings", [])}
        except (json.JSONDecodeError, KeyError, IOError):
            return {}

    def submit_for_review(self, finding_id: str, submitter_id: str) -> bool:
        if not self.config.validate_member(submitter_id)[0]:
            raise ValueError(f"Submitter '{submitter_id}' not in team")

        findings = self._load_current_findings()
        finding = findings.get(finding_id)
        if not finding:
            raise ValueError(f"Finding '{finding_id}' not found")

        status = finding.get("status", "")
        if status not in ("FIXED", "VERIFYING"):
            raise ValueError(
                f"Finding '{finding_id}' has status '{status}'. "
                f"Only FIXED or VERIFYING findings can be submitted for review."
            )

        severity = finding.get("severity", "P5")
        required = self.config.required_approvals_for_severity(severity)
        chain = ApprovalChain(
            finding_id=finding_id,
            required_approvals=required,
        )
        self._approval_chains[finding_id] = chain
        self._save_approval_chains()
        return True

    def approve(self, finding_id: str, reviewer_id: str,
                 comments: str = "",
                 evidence: Optional[Dict[str, Any]] = None) -> FindingReview:
        self._authorize_reviewer(reviewer_id)

        review = FindingReview(
            finding_id=finding_id,
            reviewer_id=reviewer_id,
            resolution=FindingResolution.ACCEPTED,
            comments=comments,
            reviewed_at=datetime.now(timezone.utc).isoformat(),
            verification_evidence=evidence,
        )

        self._reviews.setdefault(finding_id, []).append(review)
        self._save_reviews()

        chain = self._approval_chains.get(finding_id)
        if chain:
            chain.add_approval(reviewer_id, "approved")
            self._save_approval_chains()

        return review

    def reject(self, finding_id: str, reviewer_id: str,
                reason: str) -> FindingReview:
        self._authorize_reviewer(reviewer_id)

        review = FindingReview(
            finding_id=finding_id,
            reviewer_id=reviewer_id,
            resolution=FindingResolution.REJECTED,
            comments=reason,
            reviewed_at=datetime.now(timezone.utc).isoformat(),
        )

        self._reviews.setdefault(finding_id, []).append(review)
        self._save_reviews()

        chain = self._approval_chains.get(finding_id)
        if chain:
            chain.add_approval(reviewer_id, "rejected")
            self._save_approval_chains()

        return review

    def request_more_info(self, finding_id: str, reviewer_id: str,
                           questions: str) -> FindingReview:
        self._authorize_reviewer(reviewer_id)

        review = FindingReview(
            finding_id=finding_id,
            reviewer_id=reviewer_id,
            resolution=FindingResolution.NEEDS_MORE_INFO,
            comments=questions,
            reviewed_at=datetime.now(timezone.utc).isoformat(),
        )
        self._reviews.setdefault(finding_id, []).append(review)
        self._save_reviews()
        return review

    def defer(self, finding_id: str, reviewer_id: str,
               reason: str) -> FindingReview:
        self._authorize_reviewer(reviewer_id)

        review = FindingReview(
            finding_id=finding_id,
            reviewer_id=reviewer_id,
            resolution=FindingResolution.DEFERRED,
            comments=reason,
            reviewed_at=datetime.now(timezone.utc).isoformat(),
        )
        self._reviews.setdefault(finding_id, []).append(review)
        self._save_reviews()
        return review

    def _authorize_reviewer(self, reviewer_id: str) -> None:
        ok, err = self.config.validate_member(reviewer_id)
        if not ok:
            raise ValueError(err)
        member = self.config.members[reviewer_id]
        if not member.has_any_role([TeamRole.REVIEWER, TeamRole.APPROVER, TeamRole.ADMIN]):
            raise PermissionError(
                f"Member '{reviewer_id}' lacks review permissions. "
                f"Required: REVIEWER, APPROVER, or ADMIN."
            )

    def needs_review(self, finding: Dict[str, Any]) -> bool:
        if not self.config.require_review_for_p0_p2:
            return False

        severity = str(finding.get("severity", "P5"))
        status = str(finding.get("status", ""))

        if severity not in ("P0", "P1", "P2"):
            return False
        if status in ("VERIFIED", "DEFERRED", "REJECTED"):
            return False
        if status in ("FIXED", "VERIFYING"):
            chain = self._approval_chains.get(finding["id"])
            if chain and chain.is_complete:
                return False
            return True

        return False

    def get_pending_reviews(self) -> List[Dict[str, Any]]:
        findings = self._load_current_findings()
        pending: List[Dict[str, Any]] = []
        for fid, finding in findings.items():
            if self.needs_review(finding):
                chain = self._approval_chains.get(fid)
                pending.append({
                    "finding_id": fid,
                    "severity": finding.get("severity"),
                    "category": finding.get("category"),
                    "status": finding.get("status"),
                    "problem": finding.get("problem", ""),
                    "current_approvals": len(chain.approvals) if chain else 0,
                    "required_approvals": chain.required_approvals if chain else self.config.required_approvals_for_severity(finding.get("severity", "P5")),
                    "approvers": chain.approvers() if chain else [],
                    "rejected_by": chain.rejected_by() if chain else [],
                })
        return pending

    def is_approval_complete(self, finding_id: str) -> bool:
        chain = self._approval_chains.get(finding_id)
        if chain:
            return chain.is_complete
        return False

    def can_close(self, finding_id: str) -> bool:
        chain = self._approval_chains.get(finding_id)
        if not chain:
            findings = self._load_current_findings()
            finding = findings.get(finding_id)
            if not finding:
                return False
            severity = finding.get("severity", "P5")
            required = self.config.required_approvals_for_severity(severity)
            if required == 0:
                return True
            return False

        if not chain.is_complete:
            return False

        if chain.rejected_by():
            return False

        findings = self._load_current_findings()
        finding = findings.get(finding_id)
        if not finding:
            return False

        if finding.get("verification") is None and finding.get("status") in ("FIXED", "VERIFYING"):
            return False

        if finding.get("implemented_fix") is None and finding.get("status") != "DEFERRED":
            return False

        return True

    def get_review_history(self, finding_id: str) -> List[FindingReview]:
        return self._reviews.get(finding_id, [])

    def get_member_reviews(self, member_id: str) -> List[FindingReview]:
        result: List[FindingReview] = []
        for reviews in self._reviews.values():
            for r in reviews:
                if r.reviewer_id == member_id:
                    result.append(r)
        return result

    def review_summary(self) -> Dict[str, Any]:
        pending = self.get_pending_reviews()
        findings = self._load_current_findings()
        total_p0_p2 = sum(
            1 for f in findings.values()
            if f.get("severity") in ("P0", "P1", "P2")
            and f.get("status") not in ("VERIFIED", "DEFERRED")
        )
        return {
            "pending_reviews": len(pending),
            "pending_by_severity": {
                s: sum(1 for p in pending if p["severity"] == s)
                for s in ("P0", "P1", "P2")
            },
            "total_p0_p2_open": total_p0_p2,
            "approval_chains_active": len(self._approval_chains),
            "approval_chains_complete": sum(
                1 for c in self._approval_chains.values() if c.is_complete
            ),
            "pending_items": pending,
        }