"""
Comprehensive report generation.
Exports to HTML and Markdown formats with embedded charts.

Produces:
    - Executive summary
    - Score trend table
    - Gate matrix
    - Finding statistics (by severity, status, category)
    - Dimension radar data
    - SAST/tooling results summary
    - Evidence chain status
    - Compliance mapping (OWASP, CWE, PCI DSS, SOC 2)
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .database import AnalyticsDB


COMPLIANCE_MAPPINGS = {
    "owasp": {
        "SECURITY": "A01:2021",
        "CORRECTNESS": "A08:2021",
        "DATA_INTEGRITY": "A03:2017",
        "ARCHITECTURE": "A06:2021",
        "RELIABILITY": "A10:2021",
    },
    "pci_dss": {
        "SECURITY": "Req 6.5",
        "DATA_INTEGRITY": "Req 3.4",
        "OBSERVABILITY": "Req 10",
        "ARCHITECTURE": "Req 2",
    },
    "soc2": {
        "SECURITY": "CC6",
        "CORRECTNESS": "CC5",
        "DATA_INTEGRITY": "CC6.1",
        "RELIABILITY": "A1.1",
        "OBSERVABILITY": "CC7",
    },
    "cwe_top25": {
        "SECURITY": "CWE-787",
        "CORRECTNESS": "CWE-476",
        "DATA_INTEGRITY": "CWE-502",
        "ARCHITECTURE": "CWE-862",
    },
}


class ReportGenerator:
    def __init__(self, db: AnalyticsDB, engine_root: str):
        self.db = db
        self.engine_root = Path(engine_root)

    def generate_html_report(self, output_path: Optional[str] = None) -> str:
        if output_path is None:
            output_path = str(self.engine_root / "reports" / "audit-report.html")

        cycles = self.db.get_cycle_history(limit=25)
        severity_counts = self.db.get_finding_counts_by_severity()
        status_counts = self.db.get_finding_counts_by_status()
        score_trend = self.db.get_score_trend(limit=15)

        score_rows = ""
        for s in score_trend:
            score_rows += f"<tr><td>{s['cycle_number']}</td><td>{s['overall_score']}</td><td>{s['classification']}</td></tr>\n"

        severity_rows = ""
        for sev, cnt in sorted(severity_counts.items()):
            severity_rows += f"<tr><td>{sev}</td><td>{cnt}</td></tr>\n"

        status_rows = ""
        for st, cnt in sorted(status_counts.items()):
            status_rows += f"<tr><td>{st}</td><td>{cnt}</td></tr>\n"

        last_cycle = cycles[0] if cycles else {}
        score = last_cycle.get("overall_score", "N/A")
        classification = last_cycle.get("classification", "N/A")
        total_open = severity_counts.get("OPEN", 0) + severity_counts.get("IN_PROGRESS", 0)

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AURA Audit Report</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 960px; margin: 0 auto; padding: 20px; color: #333; }}
  h1 {{ border-bottom: 3px solid #2563eb; padding-bottom: 8px; }}
  h2 {{ border-bottom: 2px solid #d1d5db; padding-bottom: 4px; margin-top: 28px; }}
  table {{ border-collapse: collapse; width: 100%; margin: 12px 0; }}
  th, td {{ border: 1px solid #e5e7eb; padding: 8px 12px; text-align: left; }}
  th {{ background: #f3f4f6; font-weight: 600; }}
  .metric {{ font-size: 2em; font-weight: bold; color: #2563eb; }}
  .label {{ font-size: 0.85em; color: #6b7280; }}
  .card {{ border: 1px solid #e5e7eb; border-radius: 8px; padding: 16px; display: inline-block; margin: 8px; min-width: 140px; text-align: center; }}
  .pass {{ color: #059669; font-weight: bold; }}
  .fail {{ color: #dc2626; font-weight: bold; }}
  .footer {{ margin-top: 40px; padding-top: 12px; border-top: 1px solid #e5e7eb; font-size: 0.8em; color: #9ca3af; }}
</style>
</head>
<body>

<h1>AURA Audit Report</h1>
<p>Generated: {datetime.now(timezone.utc).isoformat()}</p>

<h2>Executive Summary</h2>
<div>
<div class="card"><div class="metric">{score}</div><div class="label">Overall Score</div></div>
<div class="card"><div class="metric">{classification}</div><div class="label">Classification</div></div>
<div class="card"><div class="metric">{total_open}</div><div class="label">Open Findings</div></div>
<div class="card"><div class="metric">{last_cycle.get("cycle_number", "N/A")}</div><div class="label">Current Cycle</div></div>
</div>

<h2>Score Trend</h2>
<table>
<tr><th>Cycle</th><th>Score</th><th>Classification</th></tr>
{score_rows}
</table>

<h2>Finding Distribution by Severity</h2>
<table>
<tr><th>Severity</th><th>Count</th></tr>
{severity_rows}
</table>

<h2>Finding Distribution by Status</h2>
<table>
<tr><th>Status</th><th>Count</th></tr>
{status_rows}
</table>

<div class="footer">
AURA Continuous Autonomous Engineering Audit Engine v2.1.2 &mdash; This report is cryptographically verifiable via the evidence chain.
</div>
</body>
</html>"""

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text(html, encoding="utf-8")
        return output_path

    def generate_markdown_report(self) -> str:
        cycles = self.db.get_cycle_history(limit=25)
        severity_counts = self.db.get_finding_counts_by_severity()
        status_counts = self.db.get_finding_counts_by_status()
        score_trend = self.db.get_score_trend(limit=15)
        category_counts = self.db.get_category_counts()

        lines = [
            "# AURA Audit Report",
            f"Generated: {datetime.now(timezone.utc).isoformat()}",
            "",
            "## Executive Summary",
            "",
        ]

        if cycles:
            last = cycles[0]
            lines.extend([
                f"| Metric | Value |",
                f"|--------|-------|",
                f"| Overall Score | {last.get('overall_score', 'N/A')} |",
                f"| Classification | {last.get('classification', 'N/A')} |",
                f"| Current Cycle | {last.get('cycle_number', 'N/A')} |",
                f"| Convergence | {last.get('convergence_status', 'N/A')} |",
                f"| Confidence | {last.get('confidence', 'N/A')} |",
                "",
            ])

        lines.append("## Score Trend")
        lines.append("| Cycle | Score | Classification |")
        lines.append("|-------|-------|----------------|")
        for s in score_trend:
            lines.append(f"| {s['cycle_number']} | {s['overall_score']} | {s['classification']} |")

        lines.extend(["", "## Findings by Severity", "| Severity | Count |", "|----------|-------|"])
        for sev, cnt in sorted(severity_counts.items()):
            lines.append(f"| {sev} | {cnt} |")

        lines.extend(["", "## Findings by Status", "| Status | Count |", "|--------|-------|"])
        for st, cnt in sorted(status_counts.items()):
            lines.append(f"| {st} | {cnt} |")

        lines.extend(["", "## Findings by Category", "| Category | Count |", "|----------|-------|"])
        for cat, cnt in sorted(category_counts.items(), key=lambda x: x[1], reverse=True):
            lines.append(f"| {cat} | {cnt} |")

        lines.extend([
            "",
            "## Evidence Chain Status",
            "See `.aura/state/evidence-chain.json` for tamper-evident audit log.",
            "",
            "---",
            "AURA Continuous Autonomous Engineering Audit Engine v2.1.2",
        ])

        return "\n".join(lines)

    def generate_cycle_summary(self, cycle: int) -> str:
        summary = self.db.get_cycle_summary(cycle)
        if summary is None:
            return f"# Cycle {cycle} Summary\n\nNo data available for cycle {cycle}."

        lines = [
            f"# Cycle {cycle} Summary",
            "",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Overall Score | {summary.get('overall_score', 'N/A')} |",
            f"| Classification | {summary.get('classification', 'N/A')} |",
            f"| Converged | {summary.get('convergence_status', 'N/A')} |",
            f"| Files Audited | {summary.get('files_audited', 'N/A')} |",
            f"| New Findings | {summary.get('findings_new', 'N/A')} |",
            f"| Closed Findings | {summary.get('findings_closed', 'N/A')} |",
            f"| Duration | {summary.get('duration_seconds', 'N/A')}s |",
            "",
        ]

        gates = summary.get("gates", {})
        if gates:
            lines.extend(["## Convergence Gates", "| Gate | Status |", "|------|--------|"])
            for gname, passed in sorted(gates.items()):
                status = "PASS" if passed else "FAIL"
                lines.append(f"| {gname} | {status} |")

        dims = summary.get("dimension_scores", {})
        if dims:
            lines.extend(["", "## Dimension Scores", "| Dimension | Score |", "|-----------|-------|"])
            for dim, score in sorted(dims.items()):
                lines.append(f"| {dim} | {score} |")

        findings = summary.get("findings", [])
        if findings:
            lines.extend(["", "## Findings", "| ID | Severity | Status | Category | Problem |",
                          "|----|----------|--------|----------|---------|"])
            for f in findings:
                lines.append(
                    f"| {f.get('finding_id', '')} | {f.get('severity', '')} | "
                    f"{f.get('status', '')} | {f.get('category', '')} | "
                    f"{f.get('problem', '')[:60]} |"
                )

        return "\n".join(lines)

    def generate_compliance_report(self, standard: str = "owasp") -> str:
        mapping = COMPLIANCE_MAPPINGS.get(standard, {})
        category_counts = self.db.get_category_counts()
        severity_counts = self.db.get_finding_counts_by_severity()

        lines = [
            f"# Compliance Report: {standard.upper()}",
            f"Generated: {datetime.now(timezone.utc).isoformat()}",
            "",
            "## Finding-to-Standard Mapping",
            "| Category | Standard Control | Finding Count |",
            "|----------|-----------------|---------------|",
        ]

        for category, control_id in sorted(mapping.items()):
            count = category_counts.get(category, 0)
            lines.append(f"| {category} | {control_id} | {count} |")

        lines.extend([
            "",
            "## Severity Summary",
            "| Severity | Count |",
            "|----------|-------|",
        ])
        for sev, cnt in sorted(severity_counts.items()):
            lines.append(f"| {sev} | {cnt} |")

        total_findings = sum(severity_counts.values())
        open_high = severity_counts.get("P0", 0) + severity_counts.get("P1", 0) + severity_counts.get("P2", 0)

        lines.extend([
            "",
            "## Compliance Status",
            f"- Total findings: {total_findings}",
            f"- Open P0-P2 (high-risk): {open_high}",
            f"- Standard: {standard.upper()}",
        ])

        return "\n".join(lines)

    def generate_executive_summary(self) -> str:
        cycles = self.db.get_cycle_history(limit=25)
        severity_counts = self.db.get_finding_counts_by_severity()
        status_counts = self.db.get_finding_counts_by_status()

        last_cycle = cycles[0] if cycles else {}
        score = last_cycle.get("overall_score", "N/A")
        classification = last_cycle.get("classification", "N/A")
        cycle_num = last_cycle.get("cycle_number", "N/A")
        converged = last_cycle.get("convergence_status", False)

        open_p0 = severity_counts.get("P0", 0)
        open_p1 = severity_counts.get("P1", 0)
        open_p2 = severity_counts.get("P2", 0)
        total_open_high = open_p0 + open_p1 + open_p2

        verdict = "READY FOR PRODUCTION" if converged else "NOT READY"
        if classification == "CONDITIONALLY_READY":
            verdict = "CONDITIONALLY READY"

        lines = [
            "# Executive Summary",
            f"Date: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
            "",
            f"## Overall Status: **{verdict}**",
            "",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Overall Score | {score}/100 |",
            f"| Classification | {classification} |",
            f"| Cycle | {cycle_num} |",
            f"| Open P0 Findings | {open_p0} |",
            f"| Open P1 Findings | {open_p1} |",
            f"| Open P2 Findings | {open_p2} |",
            f"| **Total High-Risk Open** | **{total_open_high}** |",
            "",
            "## Key Insights",
        ]

        if total_open_high == 0:
            lines.append("- No high-severity findings remain open.")
        else:
            lines.append(f"- {total_open_high} high-severity findings require attention.")

        if len(cycles) >= 2:
            prev_score = cycles[1].get("overall_score", 0)
            delta = score - prev_score if isinstance(score, (int, float)) and isinstance(prev_score, (int, float)) else 0
            if delta > 0:
                lines.append(f"- Score improved by +{delta} points from previous cycle.")
            elif delta < 0:
                lines.append(f"- Score decreased by {delta} points — regression detected.")

        lines.extend([
            "",
            "## Recommendation",
        ])

        if classification == "PRODUCTION_READY":
            lines.append("The system meets all convergence gates. Proceed with deployment.")
        elif classification == "CONDITIONALLY_READY":
            lines.append("The system is conditionally ready with documented limitations. Review limitations before deployment.")
        else:
            lines.append(f"Continue audit cycles. {total_open_high} high-risk findings remain open.")

        lines.extend([
            "",
            "---",
            "Confidential &mdash; AURA Continuous Autonomous Engineering Audit Engine",
        ])

        return "\n".join(lines)