"""
Python-based SAST scanner abstraction layer.
Integrates external tools and normalizes results to AURA finding format.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from enum import Enum
import subprocess
import json
import os
from pathlib import Path
import shutil
import re
from datetime import datetime, timezone


class SASTSeverity(Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


SEVERITY_TO_AURA = {
    "CRITICAL": "P0",
    "HIGH": "P1",
    "MEDIUM": "P2",
    "MODERATE": "P2",
    "LOW": "P4",
    "INFO": "P5",
    "WARNING": "P4",
    "ERROR": "P1",
}

CVSS_TO_AURA = [
    (9.0, "P0"),
    (7.0, "P1"),
    (4.0, "P2"),
    (0.1, "P4"),
    (0.0, "P5"),
]

TOOL_SEVERITY_MAPS = {
    "semgrep": {
        "ERROR": "P0",
        "WARNING": "P2",
        "INFO": "P4",
    },
    "codeql": {
        "error": "P1",
        "warning": "P2",
        "recommendation": "P4",
        "note": "P5",
    },
    "bandit": {
        "HIGH": "P1",
        "MEDIUM": "P2",
        "LOW": "P4",
    },
    "eslint": {
        "error": "P1",
        "warning": "P4",
    },
    "gitleaks": {
        "CRITICAL": "P0",
    },
}


@dataclass
class SASTFinding:
    tool: str
    rule_id: str
    message: str
    severity: str
    file: str
    line: int = 0
    column: int = 0
    mapped_severity: str = "P4"
    mapped_category: str = "SAST"
    confidence: str = "MEDIUM"
    evidence: str = ""


@dataclass
class DependencyVulnerability:
    package: str
    cve: str
    severity: str
    mapped_severity: str = "P4"
    description: str = ""
    category: str = "VULNERABLE_DEPENDENCY"
    confidence: str = "HIGH"
    fix_available: bool = False
    evidence: str = ""


class SASTScanner:
    def __init__(self, project_path: str, engine_root: str):
        self.project_path = Path(project_path).resolve()
        self.engine_root = Path(engine_root).resolve()
        self.available_tools: Dict[str, bool] = {}
        self._detect_tools()

    def _detect_tools(self) -> None:
        self.available_tools = {
            "semgrep": shutil.which("semgrep") is not None,
            "codeql": shutil.which("codeql") is not None,
            "bandit": shutil.which("bandit") is not None,
            "eslint": shutil.which("eslint") is not None,
            "gitleaks": shutil.which("gitleaks") is not None,
            "trufflehog": shutil.which("trufflehog") is not None,
            "syft": shutil.which("syft") is not None,
            "npm": shutil.which("npm") is not None,
            "pip_audit": shutil.which("pip-audit") is not None,
            "dependency_check": (
                shutil.which("dependency-check") is not None
                or shutil.which("dependency-check.bat") is not None
            ),
        }

    def run_semgrep(self, extra_args: List[str] = None) -> List[SASTFinding]:
        if not self.available_tools.get("semgrep"):
            print("[SAST/Python] Semgrep not installed. Skipping.")
            return []

        findings: List[SASTFinding] = []
        output_file = (
            Path(os.environ.get("TEMP", "/tmp"))
            / f"aura-semgrep-{os.urandom(4).hex()}.json"
        )

        try:
            args = [
                "semgrep", "scan", "--json",
                "--output", str(output_file),
                "--config=auto", "--quiet",
            ]
            if extra_args:
                args.extend(extra_args)
            args.append(".")

            result = subprocess.run(
                args, cwd=str(self.project_path),
                capture_output=True, text=True, timeout=300,
            )

            if output_file.exists():
                data = json.loads(output_file.read_text(encoding="utf-8"))
                for item in data.get("results", []):
                    path = item.get("path", "")
                    start = item.get("start", {})
                    extra = item.get("extra", {})

                    findings.append(SASTFinding(
                        tool="semgrep",
                        rule_id=item.get("check_id", "unknown"),
                        message=extra.get("message", ""),
                        severity=extra.get("severity", "WARNING"),
                        file=path,
                        line=start.get("line", 0),
                        column=start.get("col", 0),
                        mapped_severity=self._map_severity(
                            "semgrep", extra.get("severity", "WARNING")
                        ),
                        confidence="HIGH",
                        evidence=str(extra.get("lines", "")),
                    ))
        except subprocess.TimeoutExpired:
            print("[SAST/Python] Semgrep timed out.")
        except Exception as e:
            print(f"[SAST/Python] Semgrep error: {e}")
        finally:
            if output_file.exists():
                output_file.unlink(missing_ok=True)

        print(f"[SAST/Python] Semgrep: {len(findings)} finding(s)")
        return findings

    def run_bandit(self) -> List[SASTFinding]:
        if not self.available_tools.get("bandit"):
            print("[SAST/Python] Bandit not installed. Skipping.")
            return []

        findings: List[SASTFinding] = []
        output_file = (
            Path(os.environ.get("TEMP", "/tmp"))
            / f"aura-bandit-{os.urandom(4).hex()}.json"
        )

        try:
            args = ["bandit", "-r", ".", "-f", "json", "-o", str(output_file), "-ll"]
            subprocess.run(
                args, cwd=str(self.project_path),
                capture_output=True, text=True, timeout=300,
            )

            if output_file.exists():
                data = json.loads(output_file.read_text(encoding="utf-8"))
                for item in data.get("results", []):
                    severity_raw = item.get("issue_severity", "LOW")
                    findings.append(SASTFinding(
                        tool="bandit",
                        rule_id=item.get("test_id", "unknown"),
                        message=item.get("issue_text", ""),
                        severity=severity_raw,
                        file=item.get("filename", ""),
                        line=item.get("line_number", 0),
                        column=item.get("col_offset", 0),
                        mapped_severity=self._map_severity("bandit", severity_raw),
                        mapped_category="SAST_PYTHON",
                        confidence=item.get("issue_confidence", "MEDIUM"),
                        evidence=(item.get("code") or "").strip(),
                    ))
        except subprocess.TimeoutExpired:
            print("[SAST/Python] Bandit timed out.")
        except Exception as e:
            print(f"[SAST/Python] Bandit error: {e}")
        finally:
            if output_file.exists():
                output_file.unlink(missing_ok=True)

        print(f"[SAST/Python] Bandit: {len(findings)} finding(s)")
        return findings

    def run_gitleaks(self) -> List[SASTFinding]:
        if not self.available_tools.get("gitleaks"):
            print("[SAST/Python] Gitleaks not installed. Skipping.")
            return []

        findings: List[SASTFinding] = []
        output_file = (
            Path(os.environ.get("TEMP", "/tmp"))
            / f"aura-gitleaks-{os.urandom(4).hex()}.json"
        )

        try:
            args = [
                "gitleaks", "detect",
                "--source", str(self.project_path),
                "--report-format", "json",
                "--report-path", str(output_file),
            ]
            subprocess.run(
                args, cwd=str(self.project_path),
                capture_output=True, text=True, timeout=300,
            )

            if output_file.exists():
                data = json.loads(output_file.read_text(encoding="utf-8"))
                for leak in (data if isinstance(data, list) else []):
                    secret = leak.get("Secret", "")
                    evidence = secret[:20] + "..." if len(secret) > 20 else secret
                    findings.append(SASTFinding(
                        tool="gitleaks",
                        rule_id=leak.get("RuleID", "unknown"),
                        message=leak.get("Description", "Hardcoded secret detected"),
                        severity="CRITICAL",
                        file=leak.get("File", ""),
                        line=leak.get("StartLine", 0),
                        mapped_severity="P0",
                        mapped_category="HARDCODED_SECRET",
                        confidence="HIGH",
                        evidence=f"Match: *** (rule: {leak.get('RuleID', '')})",
                    ))
        except subprocess.TimeoutExpired:
            print("[SAST/Python] Gitleaks timed out.")
        except Exception as e:
            print(f"[SAST/Python] Gitleaks error: {e}")
        finally:
            if output_file.exists():
                output_file.unlink(missing_ok=True)

        print(f"[SAST/Python] Gitleaks: {len(findings)} finding(s)")
        return findings

    def run_trufflehog(self) -> List[SASTFinding]:
        if not self.available_tools.get("trufflehog"):
            print("[SAST/Python] TruffleHog not installed. Skipping.")
            return []

        findings: List[SASTFinding] = []
        try:
            args = [
                "trufflehog", "filesystem", str(self.project_path),
                "--json", "--no-update",
            ]
            result = subprocess.run(
                args, cwd=str(self.project_path),
                capture_output=True, text=True, timeout=600,
            )

            for line in result.stdout.strip().split("\n"):
                if not line:
                    continue
                try:
                    parsed = json.loads(line)
                    detector = parsed.get("DetectorName", "unknown")
                    source_meta = parsed.get("SourceMetadata", {})
                    fs_data = source_meta.get("Data", {}).get("Filesystem", {})

                    raw_val = parsed.get("Raw", "")
                    evidence = raw_val[:20] + "..." if len(raw_val) > 20 else raw_val

                    findings.append(SASTFinding(
                        tool="trufflehog",
                        rule_id=detector,
                        message=f"Secret detected by {detector}",
                        severity="CRITICAL",
                        file=fs_data.get("file", ""),
                        line=fs_data.get("line", 0),
                        mapped_severity="P0",
                        mapped_category="HARDCODED_SECRET_ENTROPY",
                        confidence="HIGH" if parsed.get("Verified") else "MEDIUM",
                        evidence=evidence,
                    ))
                except (json.JSONDecodeError, KeyError):
                    pass
        except subprocess.TimeoutExpired:
            print("[SAST/Python] TruffleHog timed out.")
        except Exception as e:
            print(f"[SAST/Python] TruffleHog error: {e}")

        print(f"[SAST/Python] TruffleHog: {len(findings)} finding(s)")
        return findings

    def run_npm_audit(self) -> List[DependencyVulnerability]:
        if not self.available_tools.get("npm"):
            print("[SAST/Python] npm not installed. Skipping.")
            return []

        pkg_lock = self.project_path / "package-lock.json"
        pkg_json = self.project_path / "package.json"
        if not pkg_lock.exists() or not pkg_json.exists():
            print("[SAST/Python] No package-lock.json/package.json found. Skipping npm audit.")
            return []

        vulns: List[DependencyVulnerability] = []
        try:
            result = subprocess.run(
                ["npm", "audit", "--json"],
                cwd=str(self.project_path),
                capture_output=True, text=True, timeout=300,
            )

            if result.stdout.strip():
                try:
                    data = json.loads(result.stdout)
                except json.JSONDecodeError:
                    return vulns

                for key, vuln in data.get("vulnerabilities", {}).items():
                    if not vuln:
                        continue
                    severity_raw = (vuln.get("severity") or "low").upper()
                    name = vuln.get("name", key)
                    for via in (vuln.get("via") or []):
                        if isinstance(via, str):
                            continue
                        if not via:
                            continue
                        cve_id = via.get("source", "unknown")

                        vulns.append(DependencyVulnerability(
                            package=name,
                            cve=cve_id,
                            severity=severity_raw,
                            mapped_severity=self._map_vuln_severity(
                                severity=severity_raw
                            ),
                            description=via.get("title", f"Vulnerability in {name}"),
                            category="VULNERABLE_NPM_PACKAGE",
                            fix_available=bool(via.get("fixAvailable")),
                            evidence=via.get("url", ""),
                        ))
        except subprocess.TimeoutExpired:
            print("[SAST/Python] npm audit timed out.")
        except Exception as e:
            print(f"[SAST/Python] npm audit error: {e}")

        print(f"[SAST/Python] npm audit: {len(vulns)} vulnerability/vulnerabilities")
        return vulns

    def run_pip_audit(self) -> List[DependencyVulnerability]:
        if not self.available_tools.get("pip_audit"):
            print("[SAST/Python] pip-audit not installed. Skipping.")
            return []

        req_file = self.project_path / "requirements.txt"
        pyproject = self.project_path / "pyproject.toml"
        if not req_file.exists() and not pyproject.exists():
            print("[SAST/Python] No requirements.txt/pyproject.toml found.")
            return []

        vulns: List[DependencyVulnerability] = []
        output_file = (
            Path(os.environ.get("TEMP", "/tmp"))
            / f"aura-pipaudit-{os.urandom(4).hex()}.json"
        )

        try:
            args = ["pip-audit", "--format=json", "-o", str(output_file)]
            result = subprocess.run(
                args, cwd=str(self.project_path),
                capture_output=True, text=True, timeout=300,
            )

            if output_file.exists():
                data = json.loads(output_file.read_text(encoding="utf-8"))
                for item in (data if isinstance(data, list) else []):
                    severity_raw = (item.get("severity") or "MEDIUM").upper()
                    vulns.append(DependencyVulnerability(
                        package=item.get("name", "unknown"),
                        cve=item.get("id", "unknown"),
                        severity=severity_raw,
                        mapped_severity=self._map_vuln_severity(
                            severity=severity_raw
                        ),
                        description=item.get("description", ""),
                        category="VULNERABLE_PYTHON_PACKAGE",
                        evidence=(
                            f"Fix: {', '.join(item.get('fix_versions', []))}"
                            if item.get("fix_versions")
                            else ""
                        ),
                    ))
        except subprocess.TimeoutExpired:
            print("[SAST/Python] pip-audit timed out.")
        except Exception as e:
            print(f"[SAST/Python] pip-audit error: {e}")
        finally:
            if output_file.exists():
                output_file.unlink(missing_ok=True)

        print(f"[SAST/Python] pip-audit: {len(vulns)} vulnerability/vulnerabilities")
        return vulns

    def run_all(self) -> Dict[str, List[SASTFinding]]:
        results: Dict[str, List[SASTFinding]] = {}
        tool_runners = [
            ("semgrep", self.run_semgrep),
            ("bandit", self.run_bandit),
            ("gitleaks", self.run_gitleaks),
            ("trufflehog", self.run_trufflehog),
        ]

        for name, runner in tool_runners:
            if self.available_tools.get(name):
                try:
                    results[name] = runner()
                except Exception as e:
                    print(f"[SAST/Python] {name} failed: {e}")
                    results[name] = []
            else:
                results[name] = []

        return results

    def run_all_dependency_scans(
        self,
    ) -> Tuple[Dict[str, List[SASTFinding]], Dict[str, List[DependencyVulnerability]]]:
        sast_results = self.run_all()
        dep_results: Dict[str, List[DependencyVulnerability]] = {}

        if self.available_tools.get("npm"):
            try:
                dep_results["npm_audit"] = self.run_npm_audit()
            except Exception as e:
                print(f"[SAST/Python] npm_audit failed: {e}")
                dep_results["npm_audit"] = []

        if self.available_tools.get("pip_audit"):
            try:
                dep_results["pip_audit"] = self.run_pip_audit()
            except Exception as e:
                print(f"[SAST/Python] pip_audit failed: {e}")
                dep_results["pip_audit"] = []

        return sast_results, dep_results

    @staticmethod
    def _map_severity(tool: str, severity: str) -> str:
        if not severity:
            return "P4"
        tool_map = TOOL_SEVERITY_MAPS.get(tool, {})
        if tool_map:
            return tool_map.get(
                severity.upper(), SEVERITY_TO_AURA.get(severity.upper(), "P4")
            )
        return SEVERITY_TO_AURA.get(severity.upper(), "P4")

    @staticmethod
    def _map_vuln_severity(
        cvss_score: float = 0.0, severity: str = ""
    ) -> str:
        if cvss_score > 0:
            for threshold, aura_level in CVSS_TO_AURA:
                if cvss_score >= threshold:
                    return aura_level
            return "P5"

        if severity:
            normalized = severity.upper()
            if normalized in SEVERITY_TO_AURA:
                return SEVERITY_TO_AURA[normalized]
            return "P4"

        return "P4"

    def to_aura_findings(
        self, sast_findings: List[SASTFinding], cycle: int
    ) -> List[Dict]:
        weights = {"P0": 625, "P1": 405, "P2": 216, "P3": 90, "P4": 30, "P5": 6}
        results = []

        for f in sast_findings:
            results.append({
                "id": (
                    f"SAST-{f.tool}-"
                    f"{os.urandom(4).hex().upper()}"
                ),
                "severity": f.mapped_severity,
                "category": f.mapped_category,
                "status": "OPEN",
                "problem": f.message or f"SAST finding: {f.rule_id}",
                "evidence": f.evidence or "",
                "file": f.file,
                "line": f.line,
                "column": f.column,
                "tool": f.tool,
                "rule_id": f.rule_id,
                "confidence": f.confidence,
                "cycle": cycle,
                "discovered_at": datetime.now(timezone.utc).isoformat(),
                "risk_score": weights.get(f.mapped_severity, 30),
            })

        return results

    def to_aura_findings_from_vulns(
        self, vulns: List[DependencyVulnerability], cycle: int
    ) -> List[Dict]:
        weights = {"P0": 625, "P1": 405, "P2": 216, "P3": 90, "P4": 30, "P5": 6}
        results = []

        for v in vulns:
            results.append({
                "id": (
                    f"DEP-{v.package[:20]}-"
                    f"{os.urandom(4).hex().upper()}"
                ),
                "severity": v.mapped_severity,
                "category": v.category,
                "status": "OPEN",
                "problem": f"{v.package}: {v.cve} - {v.description}",
                "evidence": v.evidence or f"CVE: {v.cve}",
                "file": "",
                "line": 0,
                "column": 0,
                "tool": "dependency-scan",
                "rule_id": v.cve,
                "confidence": v.confidence,
                "cycle": cycle,
                "discovered_at": datetime.now(timezone.utc).isoformat(),
                "risk_score": weights.get(v.mapped_severity, 30),
                "fix_available": v.fix_available,
            })

        return results

    @staticmethod
    def merge_with_existing(
        sast_findings: List[Dict], existing_findings: Dict
    ) -> Dict:
        if not existing_findings:
            existing_findings = {"findings": [], "next_id": 1}

        existing = existing_findings.get("findings", [])
        existing_rules = set()
        for f in existing:
            key = (f.get("file", ""), f.get("rule_id", ""), f.get("line", 0))
            existing_rules.add(key)

        for sf in sast_findings:
            key = (sf.get("file", ""), sf.get("rule_id", ""), sf.get("line", 0))
            if key in existing_rules:
                continue

            sf["id"] = f"SAST-{existing_findings['next_id']:04d}"
            existing_findings["next_id"] += 1
            existing.append(sf)

        existing_findings["findings"] = existing
        return existing_findings

    @staticmethod
    def filter_critical(findings: List[Dict]) -> List[Dict]:
        return [f for f in findings if f.get("severity") in ("P0", "P1", "P2")]

    def print_summary(
        self,
        sast_results: Dict[str, List[SASTFinding]],
        dep_results: Dict[str, List[DependencyVulnerability]] = None,
    ) -> None:
        total_sast = sum(len(v) for v in sast_results.values())
        total_dep = 0
        if dep_results:
            total_dep = sum(len(v) for v in dep_results.values())

        print(f"\n[SAST/Python] SAST findings: {total_sast}")
        for tool, findings in sast_results.items():
            print(f"  {tool}: {len(findings)}")

        if dep_results:
            print(f"[SAST/Python] Dependency findings: {total_dep}")
            for tool, vulns in dep_results.items():
                print(f"  {tool}: {len(vulns)}")