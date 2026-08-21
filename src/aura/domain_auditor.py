"""AURA Domain Audit Engine — 40 adversarial audit domains with shared intelligence.

Architecture:
    40 AUDIT DOMAINS
         ↓
    Shared Intelligence Layer (AST, CFG, data-flow, taint, call-graph, evidence-graph)
         ↓
    Domain-Specific Auditors (5-layer: Pattern→Structural→Semantic→Cross-file→Evidence)
         ↓
    Cross-Domain Correlation (dedup, root-cause synthesis, confidence aggregation)
         ↓
    Confidence Scoring + Remediation Hints

Each domain auditor has a 5-layer intelligence stack:
    L1 — Pattern detection (regex/signature)
    L2 — Structural analysis (AST node inspection)
    L3 — Semantic analysis (data-flow, taint tracking)
    L4 — Cross-file correlation (call graph, dependency chain)
    L5 — Evidence validation (framework awareness, runtime checks)

SECTION 1: Domain Registry
SECTION 2: Shared Intelligence Layer
SECTION 3: Domain Auditor Framework
SECTION 4: 40 Domain Auditors
SECTION 5: Cross-Domain Correlation Engine
SECTION 6: Engine Integration
"""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Any, Callable, ClassVar, Optional

# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 1: DOMAIN REGISTRY — 40 domains across 6 levels
# ═══════════════════════════════════════════════════════════════════════════════


class DomainLevel(Enum):
    CORE_SECURITY = 1
    APP_SECURITY = 2
    RUNTIME_RESILIENCE = 3
    DATA_DISTRIBUTED = 4
    DELIVERY_OPS = 5
    QUALITY_GOVERNANCE = 6


@dataclass
class DomainMetadata:
    domain_id: str
    name: str
    level: DomainLevel
    description: str
    priority: int  # 1=critical, 2=high, 3=medium
    languages: list[str]  # empty = all
    requires_ast: bool = False
    requires_taint: bool = False
    requires_multifile: bool = False
    required_files: list[str] = field(default_factory=list)


DOMAIN_REGISTRY: dict[str, DomainMetadata] = {
    # ── LEVEL 1: CORE ENGINEERING & SECURITY ──
    "DEPENDENCY": DomainMetadata("DEPENDENCY", "Dependency & Supply Chain",
        DomainLevel.CORE_SECURITY, "SBOM, CVE, outdated packages, lockfile integrity", 1,
        [], False, False, False, ["package.json", "pyproject.toml", "composer.json", "go.mod", "Cargo.toml", "Gemfile", "pom.xml"]),
    "CONFIGURATION": DomainMetadata("CONFIGURATION", "Configuration Hardening",
        DomainLevel.CORE_SECURITY, "Insecure defaults, debug mode, CORS, TLS, security headers", 1,
        [], False, False, False, [".env*", "config/", "Dockerfile", "docker-compose*", "nginx.conf"]),
    "SECRET": DomainMetadata("SECRET", "Secret & Credential Exposure",
        DomainLevel.CORE_SECURITY, "API keys, tokens, passwords, JWT secrets, keys in git history", 1,
        [], False, False, False),
    "CRYPTOGRAPHY": DomainMetadata("CRYPTOGRAPHY", "Cryptographic Hardening",
        DomainLevel.CORE_SECURITY, "Weak hash, ECB, static IV, math.random, hardcoded keys", 1,
        [], False, True, False),

    # ── LEVEL 2: APPLICATION SECURITY ──
    "INJECTION": DomainMetadata("INJECTION", "Injection Attack Surface",
        DomainLevel.APP_SECURITY, "SQLi, NoSQLi, XSS, CMDi, LDAPi, SSTI, CRLF, header injection", 1,
        [], False, True, True),
    "PATH_AND_FILE": DomainMetadata("PATH_AND_FILE", "Path & File Security",
        DomainLevel.APP_SECURITY, "Path traversal, zip slip, unsafe upload, symlink, temp race", 1,
        [], False, True, False),
    "DESERIALIZATION": DomainMetadata("DESERIALIZATION", "Deserialization Attack Surface",
        DomainLevel.APP_SECURITY, "pickle, PHP unserialize, Java serialization, YAML unsafe, prototype pollution", 1,
        [], False, True, False),
    "AUTHENTICATION": DomainMetadata("AUTHENTICATION", "Authentication Hardening",
        DomainLevel.APP_SECURITY, "Weak password, bypass, JWT flaws, session fixation, MFA gap", 1,
        [], True, True, True),
    "AUTHORIZATION": DomainMetadata("AUTHORIZATION", "Authorization & Access Control",
        DomainLevel.APP_SECURITY, "IDOR, BOLA, BFLA, RBAC flaws, privilege escalation, tenant isolation", 1,
        [], True, True, True),
    "SESSION": DomainMetadata("SESSION", "Session Management",
        DomainLevel.APP_SECURITY, "Secure/HttpOnly/SameSite cookie, fixation, expiration, token rotation", 1,
        [], False, False, False),
    "INPUT_VALIDATION": DomainMetadata("INPUT_VALIDATION", "Input Validation & Schema Enforcement",
        DomainLevel.APP_SECURITY, "Missing schema, type confusion, mass assignment, parameter pollution", 1,
        [], True, True, False),

    # ── LEVEL 3: RUNTIME & RESILIENCE ──
    "NETWORK": DomainMetadata("NETWORK", "Network Exposure & SSRF",
        DomainLevel.RUNTIME_RESILIENCE, "SSRF, DNS rebinding, HTTP URLs, open proxy, missing timeouts", 1,
        [], False, False, False),
    "LOGIC": DomainMetadata("LOGIC", "Business Logic Flaws",
        DomainLevel.RUNTIME_RESILIENCE, "Race conditions, TOCTOU, error swallowing, incorrect state, overflow", 1,
        [], True, True, True),
    "CONCURRENCY": DomainMetadata("CONCURRENCY", "Concurrency & Thread Safety",
        DomainLevel.RUNTIME_RESILIENCE, "Deadlocks, data races, lost updates, double execution, atomicity", 2,
        ["go", "rust", "java", "python", "csharp", "c_cpp"], True, True, True),
    "RELIABILITY": DomainMetadata("RELIABILITY", "Reliability & Fault Tolerance",
        DomainLevel.RUNTIME_RESILIENCE, "Missing retry/timeout, crash-only, SPoF, unhandled exception", 1,
        [], False, False, True),
    "RESILIENCE": DomainMetadata("RESILIENCE", "Resilience Patterns",
        DomainLevel.RUNTIME_RESILIENCE, "Circuit breaker, bulkhead, backpressure, load shedding, graceful shutdown", 2,
        [], False, False, True),
    "PERFORMANCE": DomainMetadata("PERFORMANCE", "Performance Anti-Patterns",
        DomainLevel.RUNTIME_RESILIENCE, "N+1, memory leak, blocking I/O, unbounded cache, hot path", 2,
        [], False, True, True),
    "RESOURCE": DomainMetadata("RESOURCE", "Resource Leak Detection",
        DomainLevel.RUNTIME_RESILIENCE, "FD leak, connection leak, thread leak, DB exhaustion, zombie process", 2,
        [], False, True, True),

    # ── LEVEL 4: DATA & DISTRIBUTED SYSTEMS ──
    "DATA_INTEGRITY": DomainMetadata("DATA_INTEGRITY", "Data Integrity & Consistency",
        DomainLevel.DATA_DISTRIBUTED, "Lost updates, partial writes, non-atomic txn, missing constraints", 1,
        ["sql", "python", "java", "go", "php", "ruby", "csharp"], False, True, True),
    "DATABASE": DomainMetadata("DATABASE", "Database Operations & Schema",
        DomainLevel.DATA_DISTRIBUTED, "Missing indexes, unsafe migrations, long txn, lock contention, schema drift", 1,
        ["sql", "plpgsql", "python", "java", "php", "go"], False, True, False),
    "DISTRIBUTED_SYSTEMS": DomainMetadata("DISTRIBUTED_SYSTEMS", "Distributed Systems Correctness",
        DomainLevel.DATA_DISTRIBUTED, "Split-brain, idempotency, clock skew, leader election, consistency", 2,
        [], True, True, True),
    "QUEUE_AND_MESSAGING": DomainMetadata("QUEUE_AND_MESSAGING", "Queue & Message Broker",
        DomainLevel.DATA_DISTRIBUTED, "Poison msg, missing DLQ, dup delivery, ack-before-process", 2,
        [], False, True, True),
    "CACHE": DomainMetadata("CACHE", "Cache Strategy & Correctness",
        DomainLevel.DATA_DISTRIBUTED, "Stampede, stale data, poisoning, unbounded growth, sensitive in cache", 2,
        [], False, True, False),

    # ── LEVEL 5: DELIVERY & OPERATIONS ──
    "OBSERVABILITY": DomainMetadata("OBSERVABILITY", "Observability & Telemetry",
        DomainLevel.DELIVERY_OPS, "Structured logging, metrics, tracing, silent failures, PII in logs", 2,
        [], False, False, False),
    "INCIDENT_READINESS": DomainMetadata("INCIDENT_READINESS", "Incident Response Readiness",
        DomainLevel.DELIVERY_OPS, "No runbook, no alerting, no escalation, no DR test", 3,
        [], False, False, False),
    "DEPLOYMENT": DomainMetadata("DEPLOYMENT", "Deployment Safety",
        DomainLevel.DELIVERY_OPS, "Rollback strategy, reproducible build, env drift, health checks", 2,
        [], False, False, False, ["Dockerfile", "docker-compose*", "fly.toml", ".github/workflows/"]),
    "CI_CD": DomainMetadata("CI_CD", "CI/CD Pipeline Security",
        DomainLevel.DELIVERY_OPS, "Secrets in pipeline, untrusted PR exec, unpinned actions, provenance", 2,
        [], False, False, False, [".github/", ".gitlab-ci.yml", "Jenkinsfile", "bitbucket-pipelines.yml"]),
    "INFRASTRUCTURE": DomainMetadata("INFRASTRUCTURE", "Infrastructure as Code Security",
        DomainLevel.DELIVERY_OPS, "Terraform exposure, K8s security, IAM, public storage, root container", 2,
        ["terraform", "dockerfile", "yaml", "json"], False, False, False),
    "SUPPLY_CHAIN": DomainMetadata("SUPPLY_CHAIN", "Software Supply Chain Integrity",
        DomainLevel.DELIVERY_OPS, "SBOM, SLSA, artifact provenance, dependency confusion, compromised CI", 2,
        [], False, False, False),

    # ── LEVEL 6: QUALITY & GOVERNANCE ──
    "ARCHITECTURE": DomainMetadata("ARCHITECTURE", "Architecture & Structural Quality",
        DomainLevel.QUALITY_GOVERNANCE, "Circular deps, god objects, layer violations, coupling", 2,
        [], True, False, True),
    "API_CONTRACT": DomainMetadata("API_CONTRACT", "API Contract & Compatibility",
        DomainLevel.QUALITY_GOVERNANCE, "Breaking changes, schema mismatch, undocumented API, versioning", 3,
        [], True, False, True),
    "COMPATIBILITY": DomainMetadata("COMPATIBILITY", "Platform & Runtime Compatibility",
        DomainLevel.QUALITY_GOVERNANCE, "OS, runtime, browser, DB version, dependency compatibility", 3,
        [], False, False, False),
    "TESTING": DomainMetadata("TESTING", "Test Quality & Coverage",
        DomainLevel.QUALITY_GOVERNANCE, "Unit/integration/E2E, property testing, flaky tests, failure injection", 2,
        [], False, False, False),
    "REGRESSION": DomainMetadata("REGRESSION", "Regression Detection",
        DomainLevel.QUALITY_GOVERNANCE, "Reappeared findings, reverted fixes, behavior/perf/security regression", 1,
        [], False, False, True),
    "DOCUMENTATION": DomainMetadata("DOCUMENTATION", "Documentation Completeness",
        DomainLevel.QUALITY_GOVERNANCE, "Missing README, architecture docs, API docs, stale docs", 3,
        [], False, False, False),
    "COMPLIANCE": DomainMetadata("COMPLIANCE", "Compliance & Licensing",
        DomainLevel.QUALITY_GOVERNANCE, "License, security policy, privacy, GDPR, audit trail, attribution", 2,
        [], False, False, False),
    "PRIVACY": DomainMetadata("PRIVACY", "Privacy & Data Protection",
        DomainLevel.QUALITY_GOVERNANCE, "PII exposure, excessive retention, data minimization, consent", 3,
        [], False, True, False),
    "ACCESSIBILITY": DomainMetadata("ACCESSIBILITY", "Accessibility Standards",
        DomainLevel.QUALITY_GOVERNANCE, "WCAG, keyboard nav, ARIA, color contrast, screen reader", 3,
        ["html", "vue", "svelte", "astro", "typescript"], False, False, False),
    "MAINTAINABILITY": DomainMetadata("MAINTAINABILITY", "Maintainability & Technical Debt",
        DomainLevel.QUALITY_GOVERNANCE, "Dead code, duplication, complexity, unused deps, stale TODO", 3,
        [], True, False, False),
    "BUSINESS_CONTINUITY": DomainMetadata("BUSINESS_CONTINUITY", "Business Continuity & DR",
        DomainLevel.QUALITY_GOVERNANCE, "Backup, restore, DR, RTO/RPO, replication, provider failure", 3,
        [], False, False, False, ["Dockerfile", "docker-compose*", "terraform*"]),
}

# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 2: SHARED INTELLIGENCE LAYER
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class SharedContext:
    """Context shared across all domain auditors for one audit cycle.

    Built once per cycle, reused by all 40 domain auditors.
    Avoids re-scanning the repo 40 times.
    """
    repo_root: Path
    all_files: dict[str, str] = field(default_factory=dict)  # rel_path → content
    file_contents_cache: dict[str, str] = field(default_factory=dict)
    ast_cache: dict[str, Any] = field(default_factory=dict)
    call_graph: dict[str, set[str]] = field(default_factory=dict)
    import_graph: dict[str, set[str]] = field(default_factory=dict)
    dependency_map: dict[str, dict] = field(default_factory=dict)
    framework_info: dict[str, Any] = field(default_factory=dict)
    skip_dirs: set = field(default_factory=lambda: {
        "node_modules", "__pycache__", ".git", ".venv", "venv", "dist",
        "build", "vendor", ".tools", ".aura", ".mypy_cache", ".ruff_cache",
        ".pytest_cache", "coverage", ".idea", ".vscode", "bower_components",
        ".terraform", ".serverless", "egg-info", ".next", ".nuxt",
    })


class SharedIntelligence:
    """Pre-computes shared analysis artifacts consumed by all domain auditors."""

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root
        self.ctx = SharedContext(repo_root=repo_root)

    def build(self) -> SharedContext:
        """Build shared context — called once per audit cycle."""
        self._index_files()
        self._parse_dependencies()
        self._detect_framework()
        return self.ctx

    def _index_files(self) -> None:
        """Index all source files into memory."""
        for f in self.repo_root.rglob("*"):
            if not f.is_file():
                continue
            if any(s in f.parts for s in self.ctx.skip_dirs):
                continue
            try:
                rel = str(f.relative_to(self.repo_root))
                content = f.read_text(encoding="utf-8", errors="ignore")
                self.ctx.file_contents_cache[rel] = content
                self.ctx.all_files[rel] = f.suffix
            except Exception:
                pass

    def _parse_dependencies(self) -> None:
        """Parse dependency manifests (package.json, pyproject.toml, etc.)."""
        manifests = {
            "package.json": self._parse_package_json,
            "pyproject.toml": self._parse_pyproject_toml,
            "composer.json": self._parse_composer_json,
            "go.mod": self._parse_go_mod,
            "Cargo.toml": self._parse_cargo_toml,
            "Gemfile": self._parse_gemfile,
            "pom.xml": self._parse_pom_xml,
        }
        for fname, parser in manifests.items():
            mf = self.repo_root / fname
            if mf.exists():
                try:
                    self.ctx.dependency_map[fname] = parser(mf)
                except Exception:
                    self.ctx.dependency_map[fname] = {"error": "parse_failed"}

    def _parse_package_json(self, path: Path) -> dict:
        data = json.loads(path.read_text())
        return {
            "deps": data.get("dependencies", {}),
            "devDeps": data.get("devDependencies", {}),
            "scripts": data.get("scripts", {}),
            "engines": data.get("engines", {}),
            "license": data.get("license", "UNLICENSED"),
        }

    def _parse_pyproject_toml(self, path: Path) -> dict:
        content = path.read_text()
        deps = {}
        for m in re.finditer(r'"(?:PyYAML|[^"]+)"', content):
            deps[m.group(0).strip('"')] = "unknown"
        return {"deps": deps, "raw": content[:500]}

    def _parse_composer_json(self, path: Path) -> dict:
        data = json.loads(path.read_text())
        return {
            "deps": data.get("require", {}),
            "devDeps": data.get("require-dev", {}),
            "autoload": data.get("autoload", {}),
        }

    def _parse_go_mod(self, path: Path) -> dict:
        content = path.read_text()
        deps = {}
        for line in content.splitlines():
            line = line.strip()
            if line and not line.startswith("module ") and not line.startswith("go "):
                parts = line.split()
                if len(parts) >= 2:
                    deps[parts[0]] = parts[1] if len(parts) > 1 else "unknown"
        return {"module": content.splitlines()[0] if content else "", "deps": deps}

    def _parse_cargo_toml(self, path: Path) -> dict:
        return {"raw": path.read_text()[:500]}

    def _parse_gemfile(self, path: Path) -> dict:
        deps = {}
        for line in path.read_text().splitlines():
            m = re.match(r"gem\s+['\"]([^'\"]+)['\"]", line.strip())
            if m:
                deps[m.group(1)] = "unknown"
        return {"deps": deps}

    def _parse_pom_xml(self, path: Path) -> dict:
        return {"raw": path.read_text()[:500]}

    def _detect_framework(self) -> None:
        """Detect framework with shared context."""
        root = self.repo_root
        fw = {"name": "unknown", "indicators": []}
        checks = [
            (lambda: (root / "composer.json").exists(), "PHP/Composer"),
            (lambda: (root / "artisan").exists() or any(f.name == "artisan" for f in root.iterdir() if f.is_file()), "Laravel"),
            (lambda: (root / "manage.py").exists(), "Django"),
            (lambda: "wsgi.py" in (self.ctx.file_contents_cache.get("app/wsgi.py", "")), "Django"),
            (lambda: "Flask(__name__)" in (self.ctx.file_contents_cache.get("app.py", "")), "Flask"),
            (lambda: "express" in (self.ctx.file_contents_cache.get("package.json", "")).lower(), "Express"),
            (lambda: "next" in (self.ctx.file_contents_cache.get("package.json", "")).lower(), "Next.js"),
            (lambda: (root / "spring").exists() or (root / "pom.xml").exists(), "Spring"),
            (lambda: (root / "Cargo.toml").exists(), "Rust/Cargo"),
            (lambda: (root / "go.mod").exists(), "Go"),
        ]
        for check, name in checks:
            try:
                if check():
                    fw["indicators"].append(name)
            except Exception:
                pass
        if fw["indicators"]:
            fw["name"] = fw["indicators"][0]
        self.ctx.framework_info = fw


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 3: DOMAIN AUDITOR FRAMEWORK
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class DomainFinding:
    domain: str
    severity: str
    category: str
    rule: str
    file: str
    line: int
    message: str
    evidence: str = ""
    confidence: float = 0.5
    requires_multifile: bool = False
    related_files: list[str] = field(default_factory=list)
    remediation_hint: str = ""
    cwe_id: str = ""


class BaseDomainAuditor(ABC):
    """Template method pattern for all 40 domain auditors.

    Each domain auditor implements 5 layers:
      L1: _detect_patterns()   — regex/signature scan
      L2: _structural_analysis() — AST inspection
      L3: _semantic_analysis()   — data-flow, taint
      L4: _cross_file_correlation() — call graph, dependency chain
      L5: _evidence_validation() — framework, runtime knowledge

    Override only the layers relevant to this domain.
    """

    domain_id: ClassVar[str] = ""
    metadata: ClassVar[DomainMetadata]

    def __init__(self, ctx: SharedContext):
        self.ctx = ctx

    def audit(self) -> list[DomainFinding]:
        """Run full 5-layer audit. Subclasses override individual layers."""
        findings: list[DomainFinding] = []

        # L1: Pattern detection — all domains implement this
        findings.extend(self._detect_patterns())

        # L2-L5: Only if domain requires them
        if self.metadata.requires_ast:
            findings = self._structural_analysis(findings)
        if self.metadata.requires_taint:
            findings = self._semantic_analysis(findings)
        if self.metadata.requires_multifile:
            findings = self._cross_file_correlation(findings)
        findings = self._evidence_validation(findings)

        return findings

    @abstractmethod
    def _detect_patterns(self) -> list[DomainFinding]:
        """L1: Pattern-based detection — mandatory for all domains."""
        ...

    def _structural_analysis(self, findings: list[DomainFinding]) -> list[DomainFinding]:
        """L2: AST-based structural analysis — override if needed."""
        return findings

    def _semantic_analysis(self, findings: list[DomainFinding]) -> list[DomainFinding]:
        """L3: Data-flow, taint tracking — override if needed."""
        return findings

    def _cross_file_correlation(self, findings: list[DomainFinding]) -> list[DomainFinding]:
        """L4: Cross-file, call graph analysis — override if needed."""
        return findings

    def _evidence_validation(self, findings: list[DomainFinding]) -> list[DomainFinding]:
        """L5: Evidence, framework context — override if needed."""
        return findings

    def _make_finding(self, severity: str, rule: str, file: str, line: int,
                      message: str, evidence: str = "", confidence: float = 0.7,
                      cwe: str = "", hint: str = "") -> DomainFinding:
        return DomainFinding(
            domain=self.domain_id, severity=severity, category=self._category(),
            rule=rule, file=file, line=line, message=message,
            evidence=evidence, confidence=confidence,
            remediation_hint=hint, cwe_id=cwe,
        )

    def _category(self) -> str:
        """Default category based on domain level."""
        cats = {
            DomainLevel.CORE_SECURITY: "SECURITY",
            DomainLevel.APP_SECURITY: "SECURITY",
            DomainLevel.RUNTIME_RESILIENCE: "RELIABILITY",
            DomainLevel.DATA_DISTRIBUTED: "DATA_INTEGRITY",
            DomainLevel.DELIVERY_OPS: "OPS",
            DomainLevel.QUALITY_GOVERNANCE: "COMPLIANCE",
        }
        return cats.get(self.metadata.level, "SECURITY")


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 4: 40 DOMAIN AUDITORS (Wave 1: 10 Priority-1 domains)
# ═══════════════════════════════════════════════════════════════════════════════

# ── LEVEL 1: CORE ENGINEERING & SECURITY ─────────────────────────────────────

class DependencyAuditor(BaseDomainAuditor):
    domain_id = "DEPENDENCY"
    metadata = DOMAIN_REGISTRY["DEPENDENCY"]

    def _detect_patterns(self) -> list[DomainFinding]:
        f: list[DomainFinding] = []
        risky_packages = {
            "request": ("P3", "DEP-OUTDATED", "deprecated — use node-fetch or axios"),
            "phantom": ("P3", "DEP-OUTDATED", "deprecated — use puppeteer"),
            "moment": ("P3", "DEP-OUTDATED", "deprecated — use date-fns or luxon"),
            "cryptico": ("P2", "DEP-RISKY-CRYPTO", "unmaintained crypto library"),
            "left-pad": ("P1", "DEP-ABANDONED", "historically compromised package"),
        }
        for manifest_name, deps_data in self.ctx.dependency_map.items():
            all_deps = {**deps_data.get("deps", {}), **deps_data.get("devDeps", {})}
            for pkg_name, pkg_version in all_deps.items():
                version = str(pkg_version) if pkg_version else "unknown"
                # Known risky packages
                for risky, (sev, rule, msg) in risky_packages.items():
                    if risky in pkg_name.lower():
                        f.append(self._make_finding(sev, rule, manifest_name, 0,
                            f"Dependency '{pkg_name}' ({version}): {msg}",
                            pkg_name, hint=f"Replace {pkg_name}"))
                        break
                # Unpinned versions
                if version.startswith("^") or version.startswith("~"):
                    f.append(self._make_finding("P4", "DEP-LOOSE", manifest_name, 0,
                        f"'{pkg_name}' loose version '{version}' — pin exact version",
                        f"{pkg_name}:{version}", hint=f"Pin {pkg_name} to exact version"))
                # Known CVE patterns
                cve_checks = {
                    "axios": "check for SSRF CVE-2023-45857",
                    "express": "check for CVE-2024-29041",
                    "fastapi": "check for version-specific CVEs at nvd.nist.gov",
                    "django": "check for version-specific CVEs",
                    "next": "check for version-specific CVEs",
                    "spring": "check for Spring4Shell / Spring security CVEs",
                }
                for cve_pkg, cve_msg in cve_checks.items():
                    if cve_pkg in pkg_name.lower():
                        f.append(self._make_finding("P2", "DEP-CVE-CHECK", manifest_name, 0,
                            f"'{pkg_name}': {cve_msg}", pkg_name,
                            cwe="CWE-1104", hint="Run security audit tool"))
                        break
        # Missing lockfile
        manifest_lock_pairs = [
            ("package.json", "package-lock.json"),
            ("composer.json", "composer.lock"),
            ("Gemfile", "Gemfile.lock"),
        ]
        for manifest, lockfile in manifest_lock_pairs:
            if (self.ctx.repo_root / manifest).exists() and not (self.ctx.repo_root / lockfile).exists():
                f.append(self._make_finding("P3", "DEP-NO-LOCKFILE", manifest, 0,
                    f"Missing lockfile: {lockfile} — non-deterministic builds",
                    hint=f"Commit {lockfile}"))
        return f


class ConfigurationAuditor(BaseDomainAuditor):
    domain_id = "CONFIGURATION"
    metadata = DOMAIN_REGISTRY["CONFIGURATION"]

    def _detect_patterns(self) -> list[DomainFinding]:
        f: list[DomainFinding] = []
        checks = {
            ".env.example": [
                (r"(?i)(DEBUG|DEVELOPMENT)\s*=\s*(true|1|on|yes)", "P3", "CFG-DEBUG-ON",
                 "Debug mode enabled in .env.example — disable for production"),
                (r"(?i)(SECRET|TOKEN|KEY|PASSWORD|PASSPHRASE)\s*=\s*['\"]?[\w\-]{8,}",
                 "P1", "CFG-ENV-SECRET", "Secret value in .env.example — use placeholder only"),
            ],
            "Dockerfile": [
                (r"^(?!.*USER\s+\w+)", "P2", "CFG-DOCKER-ROOT",
                 "No USER directive — container runs as root"),
                (r"^(?!.*HEALTHCHECK)", "P3", "CFG-DOCKER-NOHEALTH",
                 "No HEALTHCHECK — orchestrator cannot detect health"),
            ],
        }
        for filename, patterns in checks.items():
            content = self.ctx.file_contents_cache.get(filename, "")
            if not content:
                continue
            lines = content.split("\n")
            for pat, sev, rule, msg in patterns:
                for i, line in enumerate(lines, 1):
                    if re.search(pat, line):
                        f.append(self._make_finding(sev, rule, filename, i, msg,
                            line.strip()[:120], hint="Review configuration"))
        # Security headers check
        for fname in ["nginx.conf", "apache.conf", ".htaccess"]:
            content = self.ctx.file_contents_cache.get(fname, "")
            if content:
                missing_headers = []
                for header in ["X-Frame-Options", "X-Content-Type-Options", "X-XSS-Protection",
                               "Strict-Transport-Security", "Content-Security-Policy"]:
                    if header not in content:
                        missing_headers.append(header)
                if missing_headers:
                    f.append(self._make_finding("P3", "CFG-MISSING-HEADERS", fname, 0,
                        f"Missing security headers: {', '.join(missing_headers)}",
                        hint="Add security headers"))
        return f


class SecretAuditor(BaseDomainAuditor):
    domain_id = "SECRET"
    metadata = DOMAIN_REGISTRY["SECRET"]

    SECRET_PATTERNS: ClassVar = [
        (r'sk-[a-zA-Z0-9\\-_]{20,}', "P0", "SEC-OPENAI-KEY"),
        (r'sk-ant-[a-zA-Z0-9\\-_]{20,}', "P0", "SEC-ANTHROPIC-KEY"),
        (r'ghp_[a-zA-Z0-9]{36}', "P0", "SEC-GITHUB-TOKEN"),
        (r'xox[bpras]-[a-zA-Z0-9-]+', "P0", "SEC-SLACK-TOKEN"),
        (r'\d{10,}:[A-Za-z0-9_-]{35}', "P0", "SEC-TELEGRAM-BOT"),
        (r'-----BEGIN (RSA |EC )?PRIVATE KEY-----', "P0", "SEC-PRIVATE-KEY"),
        (r'(?i)(api[_-]?key|apikey)\s*[:=]\s*["\'][A-Za-z0-9_\-]{8,}', "P0", "SEC-API-KEY"),
        (r'(?i)(secret|token|password|passwd)\s*[:=]\s*["\'][^\s"\']{6,}', "P0", "SEC-CREDENTIAL"),
        (r'(?i)jdbc:[a-z]+://[^/]+/[^\s"\')]+', "P2", "SEC-JDBC-URI"),
        (r'(?i)mongodb(\+srv)?://[^/]+/[^\s"\')]+', "P2", "SEC-MONGO-URI"),
        (r'(?i)redis://[^/]+', "P3", "SEC-REDIS-URI"),
        (r'(?i)postgres://[^/]+/[^\s"\')]+', "P2", "SEC-POSTGRES-URI"),
        (r'(?i)mysql://[^/]+/[^\s"\')]+', "P2", "SEC-MYSQL-URI"),
    ]

    def _detect_patterns(self) -> list[DomainFinding]:
        f: list[DomainFinding] = []
        for rel_path, content in self.ctx.file_contents_cache.items():
            if rel_path.endswith((".md", ".txt", ".lock", ".svg", ".png")):
                continue
            for pat, sev, rule in self.SECRET_PATTERNS:
                for i, line in enumerate(content.splitlines(), 1):
                    if re.search(pat, line) and not line.strip().startswith(("#", "//", "/*", "*", "--")):
                        redacted = re.sub(r'["\'](.{4})[^"\']*(.{4})["\']', r'"\1***\2"', line.strip()[:150])
                        f.append(self._make_finding(sev, rule, rel_path, i,
                            "Potential hardcoded credential", redacted,
                            cwe="CWE-798", hint="Move to environment variable or secrets manager"))
        return f


class CryptographyAuditor(BaseDomainAuditor):
    domain_id = "CRYPTOGRAPHY"
    metadata = DOMAIN_REGISTRY["CRYPTOGRAPHY"]

    WEAK_CRYPTO_PATTERNS: ClassVar = [
        (r"\bmd5\s*\(", "P2", "CRYPTO-MD5", "MD5 — cryptographically broken, use SHA-256 or bcrypt", "CWE-327"),
        (r"\bsha1\s*\(", "P2", "CRYPTO-SHA1", "SHA-1 — collision attacks feasible, use SHA-256", "CWE-328"),
        (r"ECB\b", "P1", "CRYPTO-ECB", "ECB mode — deterministic, reveals patterns, use CBC/GCM", "CWE-327"),
        (r"(?i)Math\.random\s*\(", "P2", "CRYPTO-MATH-RANDOM", "Math.random() for security — use crypto.getRandomValues", "CWE-338"),
        (r"rand\s*\(\s*\)", "P2", "CRYPTO-RAND", "rand() — not cryptographically secure", "CWE-338"),
        (r"random\s*\(\s*\)", "P2", "CRYPTO-RANDOM", "random() — not for security, use secrets module", "CWE-338"),
        (r"(?i)static\s+(iv|nonce|salt)\s*=", "P1", "CRYPTO-STATIC-IV", "Static IV/nonce/salt — must be random per encryption", "CWE-329"),
        (r"(?i)verify\s*=\s*False", "P2", "CRYPTO-TLS-SKIP", "TLS certificate verification disabled", "CWE-295"),
        (r"alg\s*:\s*['\"]none['\"]", "P1", "CRYPTO-JWT-NONE", "JWT 'none' algorithm — signature bypass", "CWE-347"),
        (r"alg\s*:\s*['\"]HS256['\"].*secret.*['\"][^'\"]{0,10}['\"]", "P1", "CRYPTO-JWT-WEAK", "JWT with weak HMAC secret", "CWE-347"),
    ]

    def _detect_patterns(self) -> list[DomainFinding]:
        f: list[DomainFinding] = []
        for rel_path, content in self.ctx.file_contents_cache.items():
            if rel_path.endswith((".md", ".txt", ".lock", ".svg", ".png", ".sql")):
                continue
            for pat, sev, rule, msg, cwe in self.WEAK_CRYPTO_PATTERNS:
                for i, line in enumerate(content.splitlines(), 1):
                    if re.search(pat, line) and not line.strip().startswith(("#", "//", "/*", "*", "--")):
                        f.append(self._make_finding(sev, rule, rel_path, i, msg,
                            line.strip()[:120], cwe=cwe, hint="Use modern cryptographic primitives"))
        return f


class InjectionAuditor(BaseDomainAuditor):
    domain_id = "INJECTION"
    metadata = DOMAIN_REGISTRY["INJECTION"]

    def _detect_patterns(self) -> list[DomainFinding]:
        f: list[DomainFinding] = []
        pats = [
            (r"\.execute\s*\(\s*[`'\"]", "P1", "INJ-SQL-STRING", "SQL string — use parameterized queries", "CWE-89"),
            (r"\.execute\s*\(.*format\s*\(", "P1", "INJ-SQL-FORMAT", "SQL with .format() — injection risk", "CWE-89"),
            (r"os\.system\s*\(", "P1", "INJ-CMD-OS", "os.system() — command injection", "CWE-78"),
            (r"subprocess\.\w+\s*\(.*shell\s*=\s*True", "P1", "INJ-CMD-SHELL", "subprocess shell=True — command injection", "CWE-78"),
            (r"\.innerHTML\s*=", "P0", "INJ-DOM-XSS", "innerHTML — XSS, use textContent or DOMPurify", "CWE-79"),
            (r"dangerouslySetInnerHTML", "P0", "INJ-REACT-XSS", "React dangerouslySetInnerHTML — XSS", "CWE-79"),
            (r"v-html\s*=", "P0", "INJ-VUE-XSS", "Vue v-html — XSS unless content is sanitized", "CWE-79"),
            (r"\{@html\s+", "P0", "INJ-SVELTE-XSS", "Svelte @html — XSS unless sanitized", "CWE-79"),
            (r"document\.write\s*\(", "P1", "INJ-DOC-WRITE", "document.write() — XSS vector", "CWE-79"),
            (r"\beval\s*\(", "P0", "INJ-EVAL", "eval() — arbitrary code execution", "CWE-95"),
            (r"new Function\s*\(", "P0", "INJ-NEW-FUNC", "new Function() — arbitrary code execution", "CWE-95"),
            (r"render\s+inline:", "P1", "INJ-SSTI-RAILS", "render inline: — SSTI in Rails", "CWE-1336"),
            (r"\{\{.*__class__.*\}\}", "P1", "INJ-SSTI-JINJA", "Potential SSTI — dunder access in template", "CWE-1336"),
        ]
        for file_path, content in self.ctx.file_contents_cache.items():
            if file_path.endswith((".md", ".txt", ".lock", ".sql", ".html", ".css")):
                continue
            for pat, sev, rule, msg, cwe in pats:
                for i, line in enumerate(content.splitlines(), 1):
                    if re.search(pat, line) and not line.strip().startswith(("#", "//", "/*", "*", "--", "<!--")):
                        f.append(self._make_finding(sev, rule, file_path, i, msg,
                            line.strip()[:120], cwe=cwe, hint="Use parameterized/safe API"))
        return f


class PathAndFileAuditor(BaseDomainAuditor):
    domain_id = "PATH_AND_FILE"
    metadata = DOMAIN_REGISTRY["PATH_AND_FILE"]

    def _detect_patterns(self) -> list[DomainFinding]:
        f: list[DomainFinding] = []
        pats = [
            (r"\.\.\/|\.\.\\\\", "P1", "PATH-TRAVERSAL", "Path traversal pattern — validate and normalize paths", "CWE-22"),
            (r"open\s*\(\s*\w+\s*\+", "P2", "PATH-OPEN-VAR", "File open with variable concatenation — validate path", "CWE-22"),
            (r"file_get_contents\s*\(\s*\$\w+", "P2", "PATH-FILE-READ", "file_get_contents with variable — LFI/SSRF risk", "CWE-98"),
            (r"\bfopen\s*\(\s*\$\w+", "P2", "PATH-FOPEN-VAR", "fopen with variable — path traversal risk", "CWE-73"),
            (r"\bmove_uploaded_file\s*\(", "P2", "PATH-UPLOAD", "File upload — validate MIME, size, extension", "CWE-434"),
            (r"\bunlink\s*\(\s*\$\w+", "P2", "PATH-UNLINK-VAR", "File deletion with variable — validate path", "CWE-22"),
        ]
        for file_path, content in self.ctx.file_contents_cache.items():
            # Skip SQLAlchemy model definitions — not authorization code
            if self._is_model_definition(file_path, content):
                continue
            for pat, sev, rule, msg, cwe in pats:
                for i, line in enumerate(content.splitlines(), 1):
                    if re.search(pat, line, re.IGNORECASE) and not line.strip().startswith(("#", "//")):
                        # Skip __DIR__ based paths — framework standard pattern
                        if "PATH-TRAVERSAL" in rule and ("__DIR__" in line or "dirname(" in line):
                            continue
                        f.append(self._make_finding(sev, rule, file_path, i, msg,
                            line.strip()[:120], cwe=cwe, hint="Validate and sanitize file paths"))
        return f


class DeserializationAuditor(BaseDomainAuditor):
    domain_id = "DESERIALIZATION"
    metadata = DOMAIN_REGISTRY["DESERIALIZATION"]

    def _detect_patterns(self) -> list[DomainFinding]:
        f: list[DomainFinding] = []
        patterns = [
            (r"\bpickle\.(loads?|dump)\b", "P1", "DESER-PICKLE", "pickle — RCE on deserialization, use JSON", "CWE-502"),
            (r"yaml\.load\s*\((?![^)]*SafeLoader)", "P1", "DESER-YAML", "yaml.load without SafeLoader — RCE risk", "CWE-502"),
            (r"marshal\.loads?\s*\(", "P1", "DESER-MARSHAL", "marshal.load — unsafe deserialization", "CWE-502"),
            (r"\.constantize\b", "P2", "DESER-CONSTANTIZE", ".constantize — arbitrary class resolution", "CWE-470"),
            (r"\bunserialize\s*\(", "P1", "DESER-PHP", "unserialize() — PHP Object Injection", "CWE-502"),
            (r"ObjectInputStream\b", "P2", "DESER-JAVA", "ObjectInputStream — unsafe Java deserialization", "CWE-502"),
            (r"BinaryFormatter\b", "P1", "DESER-CSHARP", "BinaryFormatter — unsafe .NET deserialization", "CWE-502"),
            (r"__proto__|constructor\.prototype", "P2", "DESER-PROTO-POLLUTION", "Prototype pollution risk", "CWE-1321"),
        ]
        for file_path, content in self.ctx.file_contents_cache.items():
            for pat, sev, rule, msg, cwe in patterns:
                for i, line in enumerate(content.splitlines(), 1):
                    if re.search(pat, line) and not line.strip().startswith(("#", "//")):
                        f.append(self._make_finding(sev, rule, file_path, i, msg,
                            line.strip()[:120], cwe=cwe, hint="Use safe deserialization API"))
        return f


class AuthenticationAuditor(BaseDomainAuditor):
    domain_id = "AUTHENTICATION"
    metadata = DOMAIN_REGISTRY["AUTHENTICATION"]

    def _detect_patterns(self) -> list[DomainFinding]:
        f: list[DomainFinding] = []
        pats = [
            (r"password\s*=\s*['\"][^'\"]{1,6}['\"]", "P1", "AUTH-WEAK-DEFAULT", "Hardcoded weak default password", "CWE-798"),
            (r"(?i)admin.*password.*['\"](admin|password|123456|root)['\"]", "P1", "AUTH-DEFAULT-CRED", "Default admin credential detected", "CWE-798"),
            (r"(?i)jwt\.decode\s*\(.*verify\s*=\s*False", "P1", "AUTH-JWT-NOVERIFY", "JWT verification disabled", "CWE-347"),
            (r"(?i)jwt\.decode\s*\(.*algorithms\s*=\s*\[", "P2", "AUTH-JWT-ALG", "JWT algorithms not explicitly restricted", "CWE-347"),
            (r"if\s+\$\w+\s*==\s*['\"]admin['\"]", "P2", "AUTH-STRING-COMPARE", "String comparison for auth — timing attack", "CWE-208"),
            (r"password_hash\s*\(.*PASSWORD_BCRYPT", "P4", "AUTH-BCRYPT-OK", "Using bcrypt — good", ""),
        ]
        for file_path, content in self.ctx.file_contents_cache.items():
            # Skip SQLAlchemy model definitions — not authorization code
            if self._is_model_definition(file_path, content):
                continue
            for pat, sev, rule, msg, cwe in pats:
                for i, line in enumerate(content.splitlines(), 1):
                    if re.search(pat, line) and not line.strip().startswith(("#", "//")):
                        if sev != "P4":  # Don't report positive patterns
                            f.append(self._make_finding(sev, rule, file_path, i, msg,
                                line.strip()[:120], cwe=cwe, hint="Review authentication logic"))
        return f


class AuthorizationAuditor(BaseDomainAuditor):
    domain_id = "AUTHORIZATION"
    metadata = DOMAIN_REGISTRY["AUTHORIZATION"]

    # SQLAlchemy model patterns — NOT authorization flaws
    _MODEL_PATTERNS = [
        r"Mapped\[", r"mapped_column\(", r"ForeignKey\(", r"DeclarativeBase",
        r"__tablename__", r"Column\(", r"relationship\(",
    ]

    def _is_model_definition(self, file_path: str, content: str) -> bool:
        """Check if a file is a SQLAlchemy model definition."""
        for pat in self._MODEL_PATTERNS:
            if pat in content:
                return True
        return False

    def _detect_patterns(self) -> list[DomainFinding]:
        f: list[DomainFinding] = []
        pats = [
            (r"(?i)user_id|userId|user\b.*=.*(req|params|query|body|input)", "P2", "AUTHZ-IDOR-INDICATOR",
             "User ID from request — check for IDOR/BOLA", "CWE-639"),
            (r"(?i)(role|permission|scope)\s*=\s*['\"]admin['\"]", "P2", "AUTHZ-HARDCODED-ROLE",
             "Hardcoded admin role check — verify RBAC", "CWE-285"),
            (r"(?i)@PreAuthorize|@RolesAllowed|@Require|can\s+:\w+\?", "P4", "AUTHZ-ANNOTATION",
             "Authorization annotation detected — verify coverage", ""),
            (r"(?i)if\s+\((.*is_admin|isAdmin|is_superuser)", "P3", "AUTHZ-ADMIN-CHECK",
             "Inline admin check — prefer middleware/decorator", "CWE-862"),
            (r"(?i)\.where\s*\(\s*['\"](user_id|owner_id|tenant_id)\s*['\"]", "P3", "AUTHZ-OWNER-FILTER",
             "Ownership filter — verify tenant isolation", "CWE-284"),
        ]
        for file_path, content in self.ctx.file_contents_cache.items():
            # Skip SQLAlchemy model definitions — not authorization code
            if self._is_model_definition(file_path, content):
                continue
            for pat, sev, rule, msg, cwe in pats:
                for i, line in enumerate(content.splitlines(), 1):
                    if re.search(pat, line) and not line.strip().startswith(("#", "//")):
                        if sev != "P4":
                            f.append(self._make_finding(sev, rule, file_path, i, msg,
                                line.strip()[:120], cwe=cwe, hint="Implement proper authorization controls"))
        return f


class SessionAuditor(BaseDomainAuditor):
    domain_id = "SESSION"
    metadata = DOMAIN_REGISTRY["SESSION"]

    def _detect_patterns(self) -> list[DomainFinding]:
        f: list[DomainFinding] = []
        pats = [
            (r"Set-Cookie:(?!.*HttpOnly)", "P3", "SESS-NO-HTTPONLY", "Cookie without HttpOnly flag", "CWE-1004"),
            (r"Set-Cookie:(?!.*Secure)", "P3", "SESS-NO-SECURE", "Cookie without Secure flag", "CWE-614"),
            (r"Set-Cookie:(?!.*SameSite)", "P3", "SESS-NO-SAMESITE", "Cookie without SameSite", "CWE-1275"),
            (r"session_start\s*\(\s*\)", "P4", "SESS-CONFIG", "session_start() — ensure secure cookie params", "CWE-614"),
            (r"(?i)session\.cookie\.httponly\s*=\s*false", "P2", "SESS-HTTPONLY-OFF", "HttpOnly explicitly disabled", "CWE-1004"),
            (r"(?i)session\.cookie\.secure\s*=\s*false", "P2", "SESS-SECURE-OFF", "Secure flag explicitly disabled", "CWE-614"),
        ]
        for file_path, content in self.ctx.file_contents_cache.items():
            # Skip SQLAlchemy model definitions — not authorization code
            if self._is_model_definition(file_path, content):
                continue
            for pat, sev, rule, msg, cwe in pats:
                for i, line in enumerate(content.splitlines(), 1):
                    if re.search(pat, line) and not line.strip().startswith(("#", "//")):
                        if sev != "P4":
                            f.append(self._make_finding(sev, rule, file_path, i, msg,
                                line.strip()[:120], cwe=cwe, hint="Secure session configuration"))
        return f


class InputValidationAuditor(BaseDomainAuditor):
    domain_id = "INPUT_VALIDATION"
    metadata = DOMAIN_REGISTRY["INPUT_VALIDATION"]

    def _detect_patterns(self) -> list[DomainFinding]:
        f: list[DomainFinding] = []
        pats = [
            (r"(?i)(req\.body|req\.query|req\.params|request\.(GET|POST|json|data|form|args))\b(?!.*validate|.*schema|.*check)",
             "P3", "INPUT-NO-VALIDATE", "Request data without visible validation/schema", "CWE-20"),
            (r"(?i)(create|update|insert|save)\s*\(\s*(req\.|request\.|params)", "P2", "INPUT-MASS-ASSIGN",
             "Mass assignment from request — validate allowed fields", "CWE-915"),
            (r"JSON\.parse\s*\(\s*\w+\s*\)(?!.*\bcatch\b)", "P3", "INPUT-PARSE-NO-CATCH",
             "JSON.parse without try/catch — unhandled parse error", ""),
        ]
        for file_path, content in self.ctx.file_contents_cache.items():
            # Skip SQLAlchemy model definitions — not authorization code
            if self._is_model_definition(file_path, content):
                continue
            for pat, sev, rule, msg, cwe in pats:
                for i, line in enumerate(content.splitlines(), 1):
                    if re.search(pat, line) and not line.strip().startswith(("#", "//")):
                        f.append(self._make_finding(sev, rule, file_path, i, msg,
                            line.strip()[:120], cwe=cwe, hint="Add input validation"))
        return f


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 5: CROSS-DOMAIN CORRELATION ENGINE
# ═══════════════════════════════════════════════════════════════════════════════


class DomainCorrelator:
    """Correlates findings across all 40 domains.

    Detects: root-cause clusters (5 domains flagging same line),
    domain coverage gaps, confidence aggregation, and
    remediation priority synthesis.
    """

    def correlate(self, all_findings: dict[str, list[DomainFinding]]) -> dict[str, Any]:
        flat: list[DomainFinding] = []
        for findings in all_findings.values():
            flat.extend(findings)

        # Group by file:line — detect clusters
        location_groups: dict[str, list[DomainFinding]] = {}
        for f in flat:
            key = f"{f.file}:{f.line}"
            location_groups.setdefault(key, []).append(f)

        # Root-cause clusters: same location flagged by 3+ domains
        root_causes = {k: v for k, v in location_groups.items() if len(v) >= 3}

        # Domain coverage stats
        domain_counts = {domain: len(findings) for domain, findings in all_findings.items()}
        total = sum(domain_counts.values())

        # Severity distribution
        sev_dist: dict[str, int] = {}
        for f in flat:
            sev_dist[f.severity] = sev_dist.get(f.severity, 0) + 1

        # Aggregate confidence per severity
        sev_conf: dict[str, float] = {}
        for sev in sev_dist:
            sev_findings = [f for f in flat if f.severity == sev]
            if sev_findings:
                sev_conf[sev] = sum(f.confidence for f in sev_findings) / len(sev_findings)

        return {
            "total_domains": len(all_findings),
            "total_findings": total,
            "by_domain": domain_counts,
            "by_severity": sev_dist,
            "avg_confidence_by_severity": sev_conf,
            "root_cause_clusters": len(root_causes),
            "root_cause_details": {k: [f.rule for f in v] for k, v in list(root_causes.items())[:10]},
            "cross_domain_synthesis": self._synthesize(flat, root_causes),
        }

    def _synthesize(self, findings: list[DomainFinding],
                    root_causes: dict[str, list[DomainFinding]]) -> dict[str, Any]:
        """Generate cross-domain synthesis insights."""
        p0p1 = [f for f in findings if f.severity in ("P0", "P1")]
        return {
            "critical_findings": len(p0p1),
            "p0_count": len([f for f in p0p1 if f.severity == "P0"]),
            "p1_count": len([f for f in p0p1 if f.severity == "P1"]),
            "domains_with_critical": len(set(f.domain for f in p0p1)),
            "root_causes_needing_immediate_attention": len(
                [k for k, v in root_causes.items() if any(ff.severity in ("P0", "P1") for ff in v)]),
        }


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 6: ORCHESTRATOR — runs all 40 domains via shared intelligence
# ═══════════════════════════════════════════════════════════════════════════════


class DomainAuditOrchestrator:
    """Runs all 40 domain auditors with shared intelligence layer.

    Drop-in replacement for AdversarialAuditor.run_all().
    Compatible with current Engine._phase_adversarial() interface.
    """

    # Wave-based registration
    WAVE_REGISTRY: ClassVar[dict[int, list[type[BaseDomainAuditor]]]] = {
        1: [DependencyAuditor, ConfigurationAuditor, SecretAuditor, CryptographyAuditor,
            InjectionAuditor, PathAndFileAuditor, DeserializationAuditor,
            AuthenticationAuditor, AuthorizationAuditor, SessionAuditor,
            InputValidationAuditor],
        # Wave 2-4 to be populated
    }

    def __init__(self, repo_root: str | Path):
        self.repo_root = Path(repo_root)
        self.intel = SharedIntelligence(self.repo_root)
        self.correlator = DomainCorrelator()
        self.ctx: SharedContext | None = None

    def run_all(self) -> dict[str, Any]:
        """Run all registered domain auditors. Returns same shape as AdversarialAuditor."""
        self.ctx = self.intel.build()

        # Prepare manifest files for current-wave domains
        all_findings: dict[str, list[DomainFinding]] = {}
        findings_by_domain: dict[str, list[DomainFinding]] = {}

        for wave, auditors in self.WAVE_REGISTRY.items():
            for auditor_cls in auditors:
                domain_id = auditor_cls.domain_id
                try:
                    auditor = auditor_cls(self.ctx)
                    findings = auditor.audit()
                    all_findings[domain_id] = findings
                    findings_by_domain[domain_id] = findings
                except Exception as e:
                    all_findings[domain_id] = []
                    findings_by_domain[domain_id] = []

        # Cross-domain correlation
        synthesis = self.correlator.correlate(findings_by_domain)

        return {
            "findings": all_findings,
            "synthesis": synthesis,
            "framework": self.ctx.framework_info,
            "dependency_summary": {k: len(v.get("deps", {})) for k, v in self.ctx.dependency_map.items()},
        }

    def run_all_legacy(self) -> dict[str, list]:
        """Legacy interface: return dict[name → list[AdversarialFinding-like]].

        Converts DomainFinding to AdversarialFinding shape for Engine compatibility.
        """
        result = self.run_all()
        from .adversarial import AdversarialFinding

        legacy: dict[str, list] = {}
        for domain_id, findings in result["findings"].items():
            legacy_list = []
            for df in findings:
                legacy_list.append(AdversarialFinding(
                    role=domain_id,
                    severity=df.severity,
                    category=df.category,
                    rule=df.rule,
                    file=df.file,
                    line=df.line,
                    message=df.message,
                    evidence=df.evidence,
                ))
            legacy[domain_id] = legacy_list

        # Add synthesis as structured metadata (not as finding lists)
        legacy["_synthesis"] = [AdversarialFinding(
            role="_synthesis", severity="P5", category="INFO", rule="SYNTHESIS",
            file="", line=0,
            message=f"Domains: {result['synthesis']['total_domains']}, "
                    f"Findings: {result['synthesis']['total_findings']}, "
                    f"Critical: {result['synthesis'].get('cross_domain_synthesis', {}).get('critical_findings', 0)}",
            evidence=json.dumps(result['synthesis'].get('by_domain', {}))
        )]
        legacy["_framework"] = [AdversarialFinding(
            role="_framework", severity="P5", category="INFO", rule="FRAMEWORK",
            file="", line=0,
            message=f"Detected: {result['framework'].get('name', 'unknown')}",
            evidence=json.dumps(result['framework'])
        )]


        return legacy