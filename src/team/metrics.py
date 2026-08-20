"""Team productivity metrics for AURA audit workflow.

Tracks MTTR, finding resolution rates, member contributions, and bottleneck analysis.
Integrates with convergence data and finding lifecycle to produce team-level reports.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


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


class TeamMetricsCollector:
    def __init__(self, state_dir: str):
        self.state_dir = Path(state_dir)
        self._findings_file = self.state_dir / "state" / "findings.json"
        self._convergence_file = self.state_dir / "state" / "convergence.json"
        self._assignments_file = self.state_dir / "finding-assignments.json"
        self._reviews_file = self.state_dir / "finding-reviews.json"
        self._archive_dir = self.state_dir / "archive"

    def _load_findings(self) -> List[Dict[str, Any]]:
        if not self._findings_file.exists():
            return []
        try:
            data = json.loads(self._findings_file.read_text(encoding="utf-8"))
            return data.get("findings", [])
        except (json.JSONDecodeError, KeyError, IOError):
            return []

    def _load_convergence(self) -> Dict[str, Any]:
        if not self._convergence_file.exists():
            return {}
        try:
            return json.loads(self._convergence_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, IOError):
            return {}

    def _load_archive_findings(self) -> Dict[int, List[Dict[str, Any]]]:
        cycle_findings: Dict[int, List[Dict[str, Any]]] = {}
        if not self._archive_dir.exists():
            return cycle_findings
        for f in sorted(self._archive_dir.glob("proposed-findings-*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                findings = data.get("findings", [])
                for finding in findings:
                    fid = finding.get("id", "")
                    parts = fid.split("-C")
                    if len(parts) >= 2:
                        try:
                            cycle = int(parts[1].split("-")[0])
                        except (ValueError, IndexError):
                            cycle = 0
                        cycle_findings.setdefault(cycle, []).append(finding)
            except (json.JSONDecodeError, IOError):
                continue
        return cycle_findings

    def _parse_iso_timestamp(self, ts: Optional[str]) -> Optional[datetime]:
        if not ts:
            return None
        try:
            return datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return None

    def _compute_mttr(self, findings: List[Dict[str, Any]]) -> float:
        remediation_times: List[float] = []
        for f in findings:
            status = f.get("status", "")
            if status not in ("FIXED", "VERIFIED", "VERIFYING"):
                continue
            if not f.get("verification"):
                continue
            created = self._extract_creation_time(f)
            resolution = self._extract_resolution_time(f)
            if created and resolution:
                delta = (resolution - created).total_seconds() / 3600.0
                if delta > 0:
                    remediation_times.append(delta)

        if not remediation_times:
            return 0.0
        return round(sum(remediation_times) / len(remediation_times), 2)

    def _extract_creation_time(self, finding: Dict[str, Any]) -> Optional[datetime]:
        fid = finding.get("id", "")
        parts = fid.split("-C")
        if len(parts) >= 2:
            cycle_part = parts[1].split("-")[0]
            try:
                cycle = int(cycle_part)
                return datetime(2025, 1, 1, tzinfo=timezone.utc) + timedelta(hours=cycle)
            except ValueError:
                pass
        return None

    def _extract_resolution_time(self, finding: Dict[str, Any]) -> Optional[datetime]:
        verification = finding.get("verification", "")
        if not isinstance(verification, str):
            return None
        cycles = verification.split("CYCLE-")
        if len(cycles) >= 2:
            try:
                cycle = int(cycles[1].split(":")[0].split(" ")[0].split(".")[0])
                return datetime(2025, 1, 1, tzinfo=timezone.utc) + timedelta(hours=cycle)
            except ValueError:
                pass
        return None

    def _compute_avg_review_time(self) -> float:
        if not self._reviews_file.exists():
            return 0.0
        try:
            data = json.loads(self._reviews_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, IOError):
            return 0.0

        review_deltas: List[float] = []
        findings = {f["id"]: f for f in self._load_findings()}
        for fid, reviews_list in data.items():
            finding = findings.get(fid)
            if not finding:
                continue
            created = self._extract_creation_time(finding)
            if not created:
                continue
            first_review = min(
                (self._parse_iso_timestamp(r.get("reviewed_at")) for r in reviews_list),
                default=None,
            )
            if first_review and created:
                delta = (first_review - created).total_seconds() / 3600.0
                if delta > 0:
                    review_deltas.append(delta)

        if not review_deltas:
            return 0.0
        return round(sum(review_deltas) / len(review_deltas), 2)

    def collect_cycle_metrics(self, cycle: int) -> TeamMetrics:
        all_findings = self._load_findings()
        archive_findings = self._load_archive_findings()

        cycle_findings = archive_findings.get(cycle, [])

        cycle_finding_ids = {f["id"] for f in cycle_findings}

        all_closed_ids = {
            f["id"] for f in all_findings
            if f.get("status") in ("VERIFIED", "FIXED")
        }
        closed_in_cycle = cycle_finding_ids & all_closed_ids

        mttr = self._compute_mttr(all_findings)
        avg_review = self._compute_avg_review_time()

        category_breakdown: Dict[str, int] = {}
        for f in all_findings:
            cat = str(f.get("category", "UNKNOWN"))
            category_breakdown[cat] = category_breakdown.get(cat, 0) + 1

        member_stats = self._compute_member_stats(all_findings)

        return TeamMetrics(
            mttr_hours=mttr,
            findings_opened=len(all_findings),
            findings_closed=len(all_closed_ids),
            avg_review_time_hours=avg_review,
            members=member_stats,
            category_breakdown=category_breakdown,
            cycle_number=cycle,
        )

    def _compute_member_stats(self, findings: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        assignments: Dict[str, str] = {}
        if self._assignments_file.exists():
            try:
                data = json.loads(self._assignments_file.read_text(encoding="utf-8"))
                for fid, entry in data.items():
                    assignments[fid] = entry.get("assigned_to", "unassigned")
            except (json.JSONDecodeError, IOError):
                pass

        member_counts: Dict[str, Dict[str, Any]] = {}
        for f in findings:
            fid = f.get("id", "")
            assigned_to = assignments.get(fid, "unassigned")
            severity = f.get("severity", "P5")
            status = f.get("status", "")

            entry = member_counts.setdefault(assigned_to, {
                "assigned": 0, "open": 0, "closed": 0,
                "p0": 0, "p1": 0, "p2": 0,
            })
            entry["assigned"] += 1
            if status in ("OPEN", "IN_PROGRESS", "FIXED", "VERIFYING"):
                entry["open"] += 1
            if status in ("VERIFIED",):
                entry["closed"] += 1
            if severity == "P0":
                entry["p0"] += 1
            elif severity == "P1":
                entry["p1"] += 1
            elif severity == "P2":
                entry["p2"] += 1

        for mid in member_counts:
            entry = member_counts[mid]
            entry["completion_rate"] = round(
                (entry["closed"] / entry["assigned"] * 100), 1
            ) if entry["assigned"] > 0 else 100.0

        return member_counts

    def get_member_contribution(self, member_id: str) -> Dict[str, Any]:
        findings = self._load_findings()
        stats = self._compute_member_stats(findings)
        member_data = stats.get(member_id, {
            "assigned": 0, "open": 0, "closed": 0,
            "p0": 0, "p1": 0, "p2": 0,
        })

        severity_open = {"P0": 0, "P1": 0, "P2": 0, "P3": 0, "P4": 0, "P5": 0}
        for f in findings:
            fid = f.get("id", "")
            assignments = {}
            if self._assignments_file.exists():
                try:
                    data = json.loads(self._assignments_file.read_text(encoding="utf-8"))
                    assignments = data
                except (json.JSONDecodeError, IOError):
                    pass
            if assignments.get(fid, {}).get("assigned_to") == member_id and f.get("status") in ("OPEN", "IN_PROGRESS"):
                sev = f.get("severity", "P5")
                severity_open[sev] = severity_open.get(sev, 0) + 1

        return {
            "member_id": member_id,
            **member_data,
            "severity_breakdown_open": severity_open,
        }

    def get_mttr_trend(self, cycles: int = 10) -> List[float]:
        archive_findings = self._load_archive_findings()
        trend: List[float] = []
        for c in sorted(archive_findings.keys()):
            trend.append(self._compute_mttr(archive_findings[c]))

        if len(trend) < cycles:
            trend = [0.0] * (cycles - len(trend)) + trend
        elif len(trend) > cycles:
            trend = trend[-cycles:]

        return trend

    def get_bottleneck_analysis(self) -> Dict[str, Any]:
        findings = self._load_findings()

        status_counts: Dict[str, int] = {}
        for f in findings:
            status = f.get("status", "UNKNOWN")
            status_counts[status] = status_counts.get(status, 0) + 1

        bottlenecks: List[Dict[str, Any]] = []
        if status_counts.get("IN_PROGRESS", 0) > status_counts.get("FIXED", 0) * 0.5:
            bottlenecks.append({
                "stage": "remediation",
                "description": f"{status_counts.get('IN_PROGRESS', 0)} findings in progress, only {status_counts.get('FIXED', 0)} fixed",
                "severity": "medium",
            })

        if status_counts.get("VERIFYING", 0) > 3:
            bottlenecks.append({
                "stage": "verification",
                "description": f"{status_counts['VERIFYING']} findings awaiting verification",
                "severity": "high" if status_counts["VERIFYING"] > 8 else "medium",
            })

        if status_counts.get("OPEN", 0) > 10:
            bottlenecks.append({
                "stage": "triage",
                "description": f"{status_counts['OPEN']} untriaged findings",
                "severity": "critical" if status_counts["OPEN"] > 20 else "high",
            })

        return {
            "status_counts": status_counts,
            "bottlenecks": bottlenecks,
            "total_findings": len(findings),
        }

    def export_report(self) -> str:
        conv = self._load_convergence()
        cycle = conv.get("cycle", 0)
        metrics = self.collect_cycle_metrics(cycle)
        bottleneck = self.get_bottleneck_analysis()

        lines = [
            "# Team Productivity Report",
            "",
            f"**Cycle:** {metrics.cycle_number}",
            f"**Generated:** {datetime.now(timezone.utc).isoformat()}",
            "",
            "## Overview",
            "",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| MTTR (hours) | {metrics.mttr_hours} |",
            f"| Findings Opened | {metrics.findings_opened} |",
            f"| Findings Closed | {metrics.findings_closed} |",
            f"| Resolution Rate | {metrics.resolution_rate}% |",
            f"| Avg Review Time (hours) | {metrics.avg_review_time_hours} |",
            "",
            "## Category Breakdown",
            "",
            "| Category | Count |",
            "|----------|-------|",
        ]
        for cat, count in sorted(metrics.category_breakdown.items(), key=lambda x: -x[1]):
            lines.append(f"| {cat} | {count} |")

        lines.extend([
            "",
            "## Member Contributions",
            "",
            "| Member | Assigned | Open | Closed | P0 | P1 | P2 | Completion % |",
            "|--------|----------|------|--------|----|----|----|-------------|",
        ])
        for mid, stats in sorted(metrics.members.items()):
            lines.append(
                f"| {mid} | {stats['assigned']} | {stats['open']} | {stats['closed']} | "
                f"{stats['p0']} | {stats['p1']} | {stats['p2']} | {stats.get('completion_rate', 0)}% |"
            )

        lines.extend([
            "",
            "## Status Distribution",
            "",
            "| Status | Count |",
            "|--------|-------|",
        ])
        for status, count in sorted(bottleneck["status_counts"].items()):
            lines.append(f"| {status} | {count} |")

        if bottleneck["bottlenecks"]:
            lines.extend([
                "",
                "## Bottlenecks",
                "",
            ])
            for b in bottleneck["bottlenecks"]:
                lines.append(f"- **{b['stage']}** [{b['severity'].upper()}]: {b['description']}")

        return "\n".join(lines)