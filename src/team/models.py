"""Team data models for AURA multi-user workflow system.

Models map to the AURA finding lifecycle: OPEN → IN_PROGRESS → FIXED → VERIFYING → VERIFIED.
Team members operate within RBAC roles aligned to the 13 engine phases (DISCOVER through PUSH_APPROVAL).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

_SEVERITY_WEIGHTS: Dict[str, int] = {
    "P0": 625,
    "P1": 405,
    "P2": 216,
    "P3": 90,
    "P4": 30,
    "P5": 6,
}

_FINDING_STATUSES: Tuple[str, ...] = (
    "OPEN", "IN_PROGRESS", "FIXED", "VERIFYING",
    "VERIFIED", "REJECTED", "DEFERRED", "BLOCKED", "UNVERIFIED",
)

_FINDING_CATEGORIES: Tuple[str, ...] = (
    "SECURITY", "CORRECTNESS", "ARCHITECTURE", "RELIABILITY",
    "PERFORMANCE", "TESTING", "OBSERVABILITY", "OPERATIONS",
    "MAINTAINABILITY", "DOCUMENTATION", "DATA_INTEGRITY",
)


class TeamRole(Enum):
    AUDITOR = "auditor"
    REVIEWER = "reviewer"
    REMEDIATOR = "remediator"
    APPROVER = "approver"
    ADMIN = "admin"
    VIEWER = "viewer"


class FindingResolution(Enum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    NEEDS_MORE_INFO = "needs_more_info"
    DEFERRED = "deferred"


@dataclass
class TeamMember:
    id: str
    name: str
    email: str
    roles: List[TeamRole]
    expertise: List[str] = field(default_factory=list)
    assigned_findings: List[str] = field(default_factory=list)
    joined_at: str = ""

    def has_role(self, role: TeamRole) -> bool:
        return role in self.roles

    def has_any_role(self, roles: List[TeamRole]) -> bool:
        return any(r in self.roles for r in roles)

    def expertise_match(self, category: str) -> float:
        category_lower = category.lower().strip()
        for domain in self.expertise:
            domain_lower = domain.lower().strip()
            if domain_lower == category_lower:
                return 1.0
            if domain_lower in category_lower or category_lower in domain_lower:
                return 0.6
        return 0.0

    def active_finding_count(self, findings_map: Dict[str, Dict]) -> int:
        count = 0
        for fid in self.assigned_findings:
            f = findings_map.get(fid, {})
            if f.get("status", "") in ("OPEN", "IN_PROGRESS", "FIXED", "VERIFYING"):
                count += 1
        return count

    def p0_count(self, findings_map: Dict[str, Dict]) -> int:
        return sum(
            1 for fid in self.assigned_findings
            if findings_map.get(fid, {}).get("severity") == "P0"
            and findings_map.get(fid, {}).get("status", "") not in ("VERIFIED", "DEFERRED")
        )

    def p1_count(self, findings_map: Dict[str, Dict]) -> int:
        return sum(
            1 for fid in self.assigned_findings
            if findings_map.get(fid, {}).get("severity") == "P1"
            and findings_map.get(fid, {}).get("status", "") not in ("VERIFIED", "DEFERRED")
        )


@dataclass
class FindingAssignment:
    finding_id: str
    assigned_to: str
    assigned_by: str
    assigned_at: str
    due_date: Optional[str] = None
    priority: str = "normal"
    notes: str = ""

    def is_overdue(self) -> bool:
        if not self.due_date:
            return False
        try:
            due = datetime.fromisoformat(self.due_date.replace("Z", "+00:00"))
            return datetime.now(timezone.utc) > due
        except (ValueError, TypeError):
            return False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "assigned_to": self.assigned_to,
            "assigned_by": self.assigned_by,
            "assigned_at": self.assigned_at,
            "due_date": self.due_date,
            "priority": self.priority,
            "notes": self.notes,
            "is_overdue": self.is_overdue(),
        }


@dataclass
class FindingReview:
    finding_id: str
    reviewer_id: str
    resolution: FindingResolution
    comments: str
    reviewed_at: str
    verification_evidence: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "reviewer_id": self.reviewer_id,
            "resolution": self.resolution.value,
            "comments": self.comments,
            "reviewed_at": self.reviewed_at,
            "verification_evidence": self.verification_evidence,
        }


@dataclass
class ApprovalChain:
    finding_id: str
    approvals: List[Dict[str, Any]] = field(default_factory=list)
    required_approvals: int = 1
    is_complete: bool = False

    def add_approval(self, approver_id: str, status: str) -> bool:
        timestamp = datetime.now(timezone.utc).isoformat()
        self.approvals.append({
            "approver_id": approver_id,
            "status": status,
            "timestamp": timestamp,
        })
        approved_count = sum(1 for a in self.approvals if a["status"] == "approved")
        self.is_complete = approved_count >= self.required_approvals
        return self.is_complete

    def approvers(self) -> List[str]:
        return [a["approver_id"] for a in self.approvals]

    def rejected_by(self) -> List[str]:
        return [a["approver_id"] for a in self.approvals if a["status"] == "rejected"]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "approvals": self.approvals,
            "required_approvals": self.required_approvals,
            "is_complete": self.is_complete,
        }


@dataclass
class TeamConfig:
    members: Dict[str, TeamMember] = field(default_factory=dict)
    auto_assign: bool = True
    assignment_rules: Dict[str, str] = field(default_factory=dict)
    approval_chain: Dict[str, int] = field(default_factory=lambda: {"P0": 2, "P1": 1, "P2": 1})
    require_review_for_p0_p2: bool = True
    require_approval_for_push: bool = True
    notification_on_assignment: bool = True

    def get_member(self, member_id: str) -> Optional[TeamMember]:
        return self.members.get(member_id)

    def get_member_by_email(self, email: str) -> Optional[TeamMember]:
        email_lower = email.lower().strip()
        for m in self.members.values():
            if m.email.lower().strip() == email_lower:
                return m
        return None

    def get_members_by_role(self, role: TeamRole) -> List[TeamMember]:
        return [m for m in self.members.values() if m.has_role(role)]

    def get_role_for_category(self, category: str) -> TeamRole:
        role_name = self.assignment_rules.get(category.upper(), "remediator")
        try:
            return TeamRole(role_name)
        except ValueError:
            return TeamRole.REMEDIATOR

    def required_approvals_for_severity(self, severity: str) -> int:
        return self.approval_chain.get(severity, 1)

    def validate_member(self, member_id: str) -> Tuple[bool, str]:
        if member_id not in self.members:
            return False, f"Member '{member_id}' not found in team configuration"
        return True, ""

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TeamConfig":
        members: Dict[str, TeamMember] = {}
        raw_members = data.get("members", {})
        for mid, mdata in raw_members.items():
            roles = [TeamRole(r) for r in mdata.get("roles", ["viewer"])]
            members[mid] = TeamMember(
                id=mid,
                name=mdata.get("name", mid),
                email=mdata.get("email", ""),
                roles=roles,
                expertise=mdata.get("expertise", []),
                assigned_findings=mdata.get("assigned_findings", []),
                joined_at=mdata.get("joined_at", ""),
            )

        return cls(
            members=members,
            auto_assign=data.get("auto_assign", True),
            assignment_rules=data.get("assignment_rules", {}),
            approval_chain=data.get("approval_chain", {"P0": 2, "P1": 1, "P2": 1}),
            require_review_for_p0_p2=data.get("require_review_for_p0_p2", True),
            require_approval_for_push=data.get("require_approval_for_push", True),
            notification_on_assignment=data.get("notification_on_assignment", True),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "members": {
                mid: {
                    "name": m.name,
                    "email": m.email,
                    "roles": [r.value for r in m.roles],
                    "expertise": m.expertise,
                    "assigned_findings": m.assigned_findings,
                    "joined_at": m.joined_at,
                }
                for mid, m in self.members.items()
            },
            "auto_assign": self.auto_assign,
            "assignment_rules": self.assignment_rules,
            "approval_chain": self.approval_chain,
            "require_review_for_p0_p2": self.require_review_for_p0_p2,
            "require_approval_for_push": self.require_approval_for_push,
            "notification_on_assignment": self.notification_on_assignment,
        }


@dataclass
class TeamMetrics:
    mttr_hours: float
    findings_opened: int
    findings_closed: int
    avg_review_time_hours: float
    members: Dict[str, Dict[str, Any]]
    category_breakdown: Dict[str, int]
    cycle_number: int

    @property
    def resolution_rate(self) -> float:
        if self.findings_opened == 0:
            return 100.0
        return round((self.findings_closed / self.findings_opened) * 100, 1)

    @property
    def open_count(self) -> int:
        return self.findings_opened - self.findings_closed

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mttr_hours": self.mttr_hours,
            "findings_opened": self.findings_opened,
            "findings_closed": self.findings_closed,
            "resolution_rate_pct": self.resolution_rate,
            "open_count": self.open_count,
            "avg_review_time_hours": self.avg_review_time_hours,
            "members": self.members,
            "category_breakdown": self.category_breakdown,
            "cycle_number": self.cycle_number,
        }