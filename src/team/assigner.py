"""Intelligent finding assignment engine.

Auto-assigns findings to team members based on expertise, workload, and severity.
Respects AURA finding lifecycle and convergence gate requirements.
P0 findings are routed to experienced members; P1-P2 distributed by workload.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .models import (
    FindingAssignment,
    TeamConfig,
    TeamMember,
    TeamRole,
    _FINDING_CATEGORIES,
    _SEVERITY_WEIGHTS,
)


class FindingAssigner:
    def __init__(self, team_config: TeamConfig, state_dir: str):
        self.config = team_config
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self._assignments_file = self.state_dir / "finding-assignments.json"
        self._assignments: Dict[str, FindingAssignment] = {}
        self._load_assignments()

    def _load_assignments(self) -> None:
        if not self._assignments_file.exists():
            return
        try:
            data = json.loads(self._assignments_file.read_text(encoding="utf-8"))
            for fid, entry in data.items():
                self._assignments[fid] = FindingAssignment(
                    finding_id=entry["finding_id"],
                    assigned_to=entry["assigned_to"],
                    assigned_by=entry["assigned_by"],
                    assigned_at=entry["assigned_at"],
                    due_date=entry.get("due_date"),
                    priority=entry.get("priority", "normal"),
                    notes=entry.get("notes", ""),
                )
        except (json.JSONDecodeError, KeyError, IOError):
            self._assignments = {}

    def _save_assignments(self) -> None:
        data = {fid: a.to_dict() for fid, a in self._assignments.items()}
        self._assignments_file.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _build_findings_map(self, findings: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        return {f["id"]: f for f in findings if "id" in f}

    def _compute_member_score(self, member: TeamMember, finding: Dict[str, Any],
                               workload_map: Dict[str, int]) -> float:
        category = str(finding.get("category", "")).upper()
        severity = str(finding.get("severity", "P5"))
        risk_score = float(finding.get("risk_score", 0))

        expertise = member.expertise_match(category)
        workload = workload_map.get(member.id, 0)
        workload_penalty = min(workload * 0.15, 0.45)

        severity_weight = _SEVERITY_WEIGHTS.get(severity, 6) / 625.0
        severity_bonus = 0.0
        if severity in ("P0", "P1"):
            severity_bonus = 0.2 if expertise > 0.5 else -0.3
            if severity == "P0" and expertise < 0.3:
                return -1.0

        if member.has_role(TeamRole.AUDITOR) and category == "SECURITY":
            expertise += 0.2
        if member.has_role(TeamRole.REMEDIATOR) and severity in ("P2", "P3", "P4", "P5"):
            expertise += 0.1

        score = (expertise * 0.55) + (severity_weight * (1.0 - workload_penalty) * 0.35) + severity_bonus
        return round(score, 4)

    def auto_assign(self, findings: List[Dict[str, Any]], cycle: int) -> Dict[str, str]:
        if not self.config.auto_assign:
            return {}

        existing_assignments = set(self._assignments.keys())
        unassigned = [
            f for f in findings
            if f.get("id") and f["id"] not in existing_assignments
            and f.get("status", "OPEN") in ("OPEN", "IN_PROGRESS")
        ]

        if not unassigned:
            return {}

        findings_map = self._build_findings_map(findings)
        workload_map: Dict[str, int] = {}
        for mid in self.config.members:
            workload_map[mid] = self.config.members[mid].active_finding_count(findings_map)

        unassigned.sort(
            key=lambda f: (-_SEVERITY_WEIGHTS.get(str(f.get("severity", "P5")), 6), f.get("id", "")),
        )

        results: Dict[str, str] = {}
        for finding in unassigned:
            fid = finding["id"]
            candidate = self._pick_best_member(finding, workload_map)
            if candidate:
                self._assignments[fid] = FindingAssignment(
                    finding_id=fid,
                    assigned_to=candidate,
                    assigned_by="auto-assigner",
                    assigned_at=datetime.now(timezone.utc).isoformat(),
                    priority="critical" if finding.get("severity") in ("P0", "P1") else "normal",
                )
                workload_map[candidate] = workload_map.get(candidate, 0) + 1
                results[fid] = candidate

        self._save_assignments()
        return results

    def _pick_best_member(self, finding: Dict[str, Any],
                           workload_map: Dict[str, int]) -> Optional[str]:
        scores: List[Tuple[str, float]] = []
        for mid in self.config.members:
            member = self.config.members[mid]
            if member.has_role(TeamRole.VIEWER) and not member.has_any_role([
                TeamRole.AUDITOR, TeamRole.REMEDIATOR, TeamRole.REVIEWER, TeamRole.ADMIN
            ]):
                continue
            score = self._compute_member_score(member, finding, workload_map)
            if score > -0.5:
                scores.append((mid, score))

        if not scores:
            admins = self.config.get_members_by_role(TeamRole.ADMIN)
            if admins:
                return admins[0].id
            return None

        scores.sort(key=lambda x: (-x[1], workload_map.get(x[0], 0)))
        return scores[0][0]

    def assign_to_member(self, finding_id: str, member_id: str,
                          assigned_by: str = "manual",
                          priority: str = "normal",
                          notes: str = "") -> FindingAssignment:
        ok, err = self.config.validate_member(member_id)
        if not ok:
            raise ValueError(err)

        assignment = FindingAssignment(
            finding_id=finding_id,
            assigned_to=member_id,
            assigned_by=assigned_by,
            assigned_at=datetime.now(timezone.utc).isoformat(),
            priority=priority,
            notes=notes,
        )
        self._assignments[finding_id] = assignment
        self.config.members[member_id].assigned_findings.append(finding_id)
        self._save_assignments()
        return assignment

    def unassign(self, finding_id: str) -> Optional[FindingAssignment]:
        assignment = self._assignments.pop(finding_id, None)
        if assignment:
            member = self.config.members.get(assignment.assigned_to)
            if member and finding_id in member.assigned_findings:
                member.assigned_findings.remove(finding_id)
            self._save_assignments()
        return assignment

    def get_member_workload(self, member_id: str) -> Dict[str, Any]:
        findings_data = self._load_current_findings()
        findings_map = self._build_findings_map(findings_data)
        member = self.config.members.get(member_id)
        if not member:
            return {"error": f"Member '{member_id}' not found"}

        return {
            "member_id": member_id,
            "member_name": member.name,
            "assigned_total": len(member.assigned_findings),
            "open_count": sum(
                1 for fid in member.assigned_findings
                if findings_map.get(fid, {}).get("status") in ("OPEN", "IN_PROGRESS")
            ),
            "p0_count": member.p0_count(findings_map),
            "p1_count": member.p1_count(findings_map),
            "recently_assigned": sum(
                1 for fid in member.assigned_findings
                if fid in self._assignments
            ),
        }

    def _load_current_findings(self) -> List[Dict[str, Any]]:
        findings_path = self.state_dir.parent / "state" / "findings.json"
        if not findings_path.exists():
            return []
        try:
            data = json.loads(findings_path.read_text(encoding="utf-8"))
            return data.get("findings", [])
        except (json.JSONDecodeError, KeyError, IOError):
            return []

    def rebalance(self) -> List[FindingAssignment]:
        findings = self._load_current_findings()
        findings_map = self._build_findings_map(findings)
        workload: Dict[str, int] = {}
        for mid in self.config.members:
            workload[mid] = self.config.members[mid].active_finding_count(findings_map)

        avg = sum(workload.values()) / max(len(workload), 1)
        overloaded = {mid: cnt for mid, cnt in workload.items() if cnt > avg + 1}
        underloaded = {mid: cnt for mid, cnt in workload.items() if cnt < avg}

        new_assignments: List[FindingAssignment] = []
        for over_id, over_cnt in overloaded.items():
            excess = over_cnt - int(avg)
            over_member = self.config.members[over_id]
            candidates = [
                fid for fid in over_member.assigned_findings
                if findings_map.get(fid, {}).get("severity") not in ("P0",)
                and findings_map.get(fid, {}).get("status") in ("OPEN",)
            ]
            for candidate_fid in candidates[:excess]:
                if not underloaded:
                    break
                target_id = min(underloaded, key=underloaded.get)
                assignment = self.assign_to_member(
                    candidate_fid, target_id,
                    assigned_by="rebalance",
                    priority="normal",
                    notes=f"Rebalanced from {over_id}",
                )
                new_assignments.append(assignment)
                underloaded[target_id] += 1
                if underloaded[target_id] >= avg:
                    del underloaded[target_id]

        return new_assignments

    def get_unassigned(self) -> List[str]:
        findings = self._load_current_findings()
        assigned_ids = set(self._assignments.keys())
        return [
            f["id"] for f in findings
            if f.get("id") and f["id"] not in assigned_ids
            and f.get("status", "OPEN") in ("OPEN", "IN_PROGRESS")
        ]

    def suggest_assignee(self, finding: Dict[str, Any]) -> List[Tuple[str, float]]:
        findings = self._load_current_findings()
        findings_map = self._build_findings_map(findings)
        workload_map: Dict[str, int] = {}
        for mid in self.config.members:
            workload_map[mid] = self.config.members[mid].active_finding_count(findings_map)

        scores: List[Tuple[str, float]] = []
        for mid in self.config.members:
            score = self._compute_member_score(self.config.members[mid], finding, workload_map)
            scores.append((mid, round(score, 4)))

        scores.sort(key=lambda x: -x[1])
        return [(mid, s) for mid, s in scores if s > -1.0]

    def get_assignment(self, finding_id: str) -> Optional[FindingAssignment]:
        return self._assignments.get(finding_id)

    def get_all_assignments(self) -> Dict[str, FindingAssignment]:
        return dict(self._assignments)

    def workload_summary(self) -> Dict[str, Any]:
        findings = self._load_current_findings()
        findings_map = self._build_findings_map(findings)
        members_workload = {}
        for mid, member in self.config.members.items():
            members_workload[mid] = self.get_member_workload(mid)

        return {
            "members": members_workload,
            "total_assigned": len(self._assignments),
            "total_unassigned": len(self.get_unassigned()),
            "auto_assign_active": self.config.auto_assign,
        }