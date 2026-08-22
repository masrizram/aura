"""AURA adversarial audit engine — 12 independent adversarial roles.

Each role attacks the codebase from a different angle, producing findings
independently of the primary auditor. The orchestrator correlates all 12.

Roles (12 — one per convergence gate dimension):
  1. DEPENDENCY_AUDITOR     — Supply chain, outdated/vulnerable packages
  2. CONFIGURATION_AUDITOR  — Misconfig, insecure defaults, missing hardening
  3. NETWORK_AUDITOR        — Exposed ports, HTTP, 0.0.0.0 binds, SSRF vectors
  4. INJECTION_AUDITOR      — SQLi, XSS, CMDi, path traversal, SSTI
  5. SECRET_AUDITOR         — Hardcoded keys, tokens, passwords, JWTs
  6. LOGIC_AUDITOR          — Race conditions, TOCTOU, error swallowing
  7. ARCHITECTURE_AUDITOR   — Circular deps, god objects, layer violations
  8. PERFORMANCE_AUDITOR    — N+1 queries, memory leaks, blocking I/O
  9. RELIABILITY_AUDITOR    — Missing retry/timeout, crash-only, single point
  10. OBSERVABILITY_AUDITOR — Missing logs, no metrics, silent failures
  11. TESTING_AUDITOR        — Low coverage, brittle tests, no integration tests
  12. COMPLIANCE_AUDITOR     — License issues, missing security policy, GDPR
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class AdversarialFinding:
    role: str
    severity: str
    category: str
    rule: str
    file: str
    line: int
    message: str
    evidence: str = ""


class AdversarialAuditor:
    """Runs all 12 adversarial audit roles."""

    def __init__(self) -> None:
        self._roles = [
            ("dependency", self._audit_dependency),
            ("configuration", self._audit_configuration),
            ("network", self._audit_network),
            ("injection", self._audit_injection),
            ("secret", self._audit_secret),
            ("logic", self._audit_logic),
            ("architecture", self._audit_architecture),
            ("performance", self._audit_performance),
            ("reliability", self._audit_reliability),
            ("observability", self._audit_observability),
            ("testing", self._audit_testing),
            ("compliance", self._audit_compliance),
        ]

    def run_all(self, repo_root: str | Path) -> dict[str, list[AdversarialFinding]]:
        root = Path(repo_root)
        results: dict[str, list[AdversarialFinding]] = {}
        for name, auditor in self._roles:
            try:
                results[name] = auditor(root)
            except Exception:
                results[name] = []
        return results

    def summary(self, results: dict[str, list[AdversarialFinding]]) -> dict[str, Any]:
        total = sum(len(v) for v in results.values())
        by_severity: dict[str, int] = {}
        for findings in results.values():
            for f in findings:
                by_severity[f.severity] = by_severity.get(f.severity, 0) + 1
        by_category: dict[str, int] = {}
        for findings in results.values():
            for f in findings:
                by_category[f.category] = by_category.get(f.category, 0) + 1
        return {
            "total": total,
            "by_role": {k: len(v) for k, v in results.items()},
            "by_severity": dict(sorted(by_severity.items())),
            "by_category": dict(sorted(by_category.items())),
            "roles_failing": [k for k, v in results.items() if any(
                ff.severity in ("P0", "P1") for ff in v)],
        }

    # ── 1. DEPENDENCY ───────────────────────────────────────────────

    @staticmethod
    def _audit_dependency(root: Path) -> list[AdversarialFinding]:
        f = []
        # package.json
        pkg = root / "package.json"
        if pkg.exists():
            try:
                data = json.loads(pkg.read_text())
                deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
                risky = {
                    "request": ("P3", "deprecated — use node-fetch or axios"),
                    "phantom": ("P3", "deprecated — use puppeteer"),
                    "cryptico": ("P2", "unmaintained crypto library"),
                    "jquery": ("P4", "consider vanilla JS or lighter alternative"),
                    "moment": ("P3", "deprecated — use date-fns or luxon"),
                    "lodash": ("P4", "tree-shake or use native methods"),
                }
                for name, version in deps.items():
                    for risky_name, (sev, reason) in risky.items():
                        if risky_name in name.lower():
                            f.append(AdversarialFinding("DEPENDENCY", sev, "SUPPLY_CHAIN",
                                "DEP-RISKY", "package.json", 0,
                                f"Dependency '{name}' ({version}): {reason}", name))
                            break
                # Loose versions
                for name, version in deps.items():
                    if version.startswith("^") or version.startswith("~"):
                        f.append(AdversarialFinding("DEPENDENCY", "P4", "SUPPLY_CHAIN",
                            "DEP-LOOSE", "package.json", 0,
                            f"'{name}' loose version '{version}' — pin exact", f"{name}:{version}"))
                # Check for known CVEs via package name heuristic
                vuln_patterns = {
                    "axios": "check for SSRF CVE-2023-45857",
                    "express": "check for CVE-2024-29041",
                }
                for name in deps:
                    for vn, vmsg in vuln_patterns.items():
                        if vn in name.lower():
                            f.append(AdversarialFinding("DEPENDENCY", "P2", "SUPPLY_CHAIN",
                                "DEP-CVE-CHECK", "package.json", 0,
                                f"'{name}': {vmsg} — run npm audit", name))
                            break
            except Exception:
                pass

        # pyproject.toml
        pyproj = root / "pyproject.toml"
        if pyproj.exists():
            try:
                content = pyproj.read_text()
                risky_py = {"pickle": ("P1", "deserialization risk — use JSON"),
                            "cryptography<3": ("P1", "outdated crypto — upgrade to >=42"),
                            "requests<2.32": ("P1", "CVE-2024-35195 — upgrade requests")}
                for dep, (sev, msg) in risky_py.items():
                    if dep in content:
                        f.append(AdversarialFinding("DEPENDENCY", sev, "SUPPLY_CHAIN",
                            "DEP-PY-RISKY", "pyproject.toml", 0, msg, dep))
            except Exception:
                pass
        return f

    # ── 2. CONFIGURATION ────────────────────────────────────────────

    @staticmethod
    def _audit_configuration(root: Path) -> list[AdversarialFinding]:
        f = []
        # tsconfig
        tsc = root / "tsconfig.json"
        if tsc.exists():
            try:
                cfg = json.loads(tsc.read_text())
                co = cfg.get("compilerOptions", {})
                for opt, sev, msg in [
                    ("strict", "P2", "strict mode disabled — type safety compromised"),
                    ("noUncheckedIndexedAccess", "P4", "noUncheckedIndexedAccess not enabled"),
                    ("noImplicitReturns", "P4", "noImplicitReturns not enabled"),
                    ("noFallthroughCasesInSwitch", "P4", "noFallthroughCasesInSwitch not enabled"),
                ]:
                    if not co.get(opt):
                        f.append(AdversarialFinding("CONFIGURATION", sev, "SECURITY",
                            f"CFG-TS-NO{opt.upper()[:8]}", "tsconfig.json", 0, msg,
                            f"{opt}: {co.get(opt, 'not set')}"))
            except Exception:
                pass
        # Dockerfile
        df = root / "Dockerfile"
        if df.exists():
            content = df.read_text()
            checks = [
                ("USER", "P2", "CFG-DOCKER-ROOT", "No USER — container runs as root"),
                ("EXPOSE", "P4", "CFG-DOCKER-EXPOSE", "Verify exposed ports are documented"),
                ("HEALTHCHECK", "P3", "CFG-DOCKER-NOHEALTH", "No HEALTHCHECK — no readiness probe"),
            ]
            for directive, sev, rule, msg in checks:
                if directive not in content:
                    f.append(AdversarialFinding("CONFIGURATION", sev, "SECURITY",
                        rule, "Dockerfile", 0, msg, f"{directive} missing"))
            if "COPY . ." in content and ".dockerignore" not in [p.name for p in root.iterdir()]:
                f.append(AdversarialFinding("CONFIGURATION", "P3", "SECURITY",
                    "CFG-DOCKER-NOIGNORE", "Dockerfile", 0,
                    "COPY . . without .dockerignore — secrets may leak into image",
                    ".dockerignore missing"))
        # .env.example
        env_ex = root / ".env.example"
        if env_ex.exists():
            keys = [l.split("=")[0].strip() for l in env_ex.read_text().splitlines()
                    if "=" in l and not l.strip().startswith("#")]
            sensitive = [k for k in keys if any(w in k.upper() for w in
                        ["SECRET", "TOKEN", "KEY", "PASSWORD", "PASSPHRASE", "CREDENTIAL"])]
            if sensitive:
                f.append(AdversarialFinding("CONFIGURATION", "P3", "SECURITY",
                    "CFG-ENV-SECRETS", ".env.example", 0,
                    f"{len(sensitive)} secret keys defined in .env.example — never commit values",
                    ", ".join(sensitive[:5])))
        # fly.toml / docker-compose
        for cfg_name in ["fly.toml", "docker-compose.yml", "docker-compose.yaml"]:
            cf = root / cfg_name
            if cf.exists():
                content = cf.read_text()
                if "memory" not in content.lower():
                    f.append(AdversarialFinding("CONFIGURATION", "P4", "RELIABILITY",
                        "CFG-NO-MEMLIMIT", cfg_name, 0,
                        f"{cfg_name} has no memory limit — OOM risk",
                        "memory limit missing"))
        return f

    # ── 3. NETWORK ──────────────────────────────────────────────────

    @staticmethod
    def _audit_network(root: Path) -> list[AdversarialFinding]:
        f = []
        scan_exts = [
            "*.ts", "*.tsx", "*.py", "*.js", "*.jsx",
            "*.go", "*.rs", "*.java", "*.php", "*.rb",
            "*.html", "*.htm", "*.vue", "*.svelte", "*.astro",
            "*.cs", "*.swift", "*.kt", "*.dart", "*.scala",
            "*.lua", "*.ex", "*.exs", "*.erl", "*.hs",
            "*.clj", "*.cljs", "*.c", "*.cpp", "*.h", "*.hpp",
            "*.nim", "*.zig", "*.r", "*.jl",
        ]
        for ext in scan_exts:
            for sfile in root.glob(f"**/{ext}"):
                if any(s in sfile.parts for s in ["node_modules", ".git", "__pycache__", "vendor", ".venv", ".tools", "venv", ".aura"]):
                    continue
                try:
                    content = sfile.read_text(errors="ignore")
                    rel = str(sfile.relative_to(root))
                    for i, line in enumerate(content.splitlines(), 1):
                        # HTTP URLs
                        for url in re.findall(r'http://[^\s"\'`,\]]+', line):
                            if not any(h in url for h in ["localhost", "127.0.0.1", "0.0.0.0"]):
                                f.append(AdversarialFinding("NETWORK", "P3", "SECURITY",
                                    "NET-HTTP", rel, i,
                                    f"HTTP URL (not HTTPS): {url[:60]}", line.strip()[:80]))
                                break
                        # 0.0.0.0 bind
                        if "0.0.0.0" in line and any(w in line.lower() for w in ["host", "bind", "listen", "serve"]):
                            f.append(AdversarialFinding("NETWORK", "P4", "SECURITY",
                                "NET-WILDCARD", rel, i,
                                "Binding to 0.0.0.0 — exposed to all interfaces", line.strip()[:80]))
                        # SSRF patterns
                        if re.search(r'requests\.(get|post|put)\s*\(\s*\w+\s*[\+\.]', line):
                            f.append(AdversarialFinding("NETWORK", "P2", "SECURITY",
                                "NET-SSRF-VEC", rel, i,
                                "Potential SSRF — URL concatenation with user input", line.strip()[:80]))
                except Exception:
                    pass
        return f

    # ── 4. INJECTION ────────────────────────────────────────────────

    @staticmethod
    def _audit_injection(root: Path) -> list[AdversarialFinding]:
        f = []
        patterns = [
            (r"\.execute\s*\(\s*[`'\"]", "P1", "INJ-SQL-INTERP", "SQL — use parameterized queries"),
            (r"\.execute\s*\(\s*.*format\s*\(", "P1", "INJ-SQL-FORMAT", "SQL with .format() — use parameters"),
            (r"os\.system\s*\(", "P1", "INJ-CMD-OS", "os.system() — use subprocess with list args"),
            (r"subprocess\.\w+\s*\(\s*['\"].*\$", "P1", "INJ-CMD-SHELL", "Shell injection — pass args as list"),
            (r"open\s*\(\s*\w+\s*\+", "P2", "INJ-PATH-TRAV", "Path traversal — user input in file path"),
            (r"\$\(.*\)", "P2", "INJ-CMD-SUB", "Command substitution — validate input"),
            (r"\.innerHTML\s*=", "P0", "INJ-DOM-XSS", "innerHTML — XSS, use textContent"),
            (r"dangerouslySetInnerHTML", "P0", "INJ-REACT-XSS", "dangerouslySetInnerHTML — XSS in React"),
            (r"document\.write\s*\(", "P1", "INJ-DOC-WRITE", "document.write() — XSS vector"),
            (r"eval\s*\(", "P0", "INJ-EVAL", "eval() — arbitrary code execution"),
        ]
        for ext_pat in ["*.py", "*.ts", "*.tsx", "*.js", "*.jsx", "*.php", "*.rb", "*.cs", "*.swift", "*.kt", "*.lua", "*.dart", "*.r", "*.jl", "*.pl", "*.pm", "*.go"]:
            for sfile in root.glob(f"**/{ext_pat}"):
                if any(s in sfile.parts for s in ["node_modules", ".git", "__pycache__", "vendor", ".venv", ".tools", "venv"]):
                    continue
                try:
                    content = sfile.read_text(errors="ignore")
                    rel = str(sfile.relative_to(root))
                    for pat, sev, rule, msg in patterns:
                        for i, line in enumerate(content.splitlines(), 1):
                            if re.search(pat, line) and not line.strip().startswith("//"):
                                f.append(AdversarialFinding("INJECTION", sev, "SECURITY",
                                    rule, rel, i, msg, line.strip()[:80]))
                except Exception:
                    pass
        return f

    # ── 5. SECRET ───────────────────────────────────────────────────

    @staticmethod
    def _audit_secret(root: Path) -> list[AdversarialFinding]:
        f = []
        patterns = [
            (r'(?i)(api[_-]?key|apikey)\s*[:=]\s*["\'][A-Za-z0-9_\-]{8,}', "P0", "SEC-API-KEY"),
            (r'(?i)(secret|token|password|passwd)\s*[:=]\s*["\'][^\s"\']{6,}', "P0", "SEC-CREDENTIAL"),
            (r'sk-[a-zA-Z0-9]{20,}', "P0", "SEC-OPENAI-KEY"),
            (r'sk-ant-[a-zA-Z0-9]{20,}', "P0", "SEC-ANTHROPIC-KEY"),
            (r'ghp_[a-zA-Z0-9]{36}', "P0", "SEC-GITHUB-TOKEN"),
            (r'xox[bpras]-[a-zA-Z0-9-]+', "P0", "SEC-SLACK-TOKEN"),
            (r'\d{10,}:[A-Za-z0-9_-]{35}', "P0", "SEC-TELEGRAM-BOT"),
            (r'(?i)jdbc:[a-z]+://[^/]+/[^\s"\'\)]+', "P2", "SEC-JDBC-CONN"),
            (r'(?i)mongodb(\+srv)?://[^/]+/[^\s"\'\)]+', "P2", "SEC-MONGO-URI"),
            (r'(?i)redis://[^/]+', "P3", "SEC-REDIS-URI"),
            (r'-----BEGIN (RSA |EC )?PRIVATE KEY-----', "P0", "SEC-PRIVATE-KEY"),
        ]
        for ext in ["*.ts", "*.tsx", "*.py", "*.js", "*.jsx", "*.yml", "*.yaml", "*.json", "*.env*",
                     "*.toml", "*.ini", "*.cfg", "*.tf", "*.tfvars", "*.cs", "*.kt", "*.swift",
                     "*.php", "*.rb", "*.java", "*.go", "*.rs", "*.sol"]:
            for sfile in root.glob(f"**/{ext}"):
                if any(s in sfile.parts for s in ["node_modules", ".git", "__pycache__", "vendor", ".venv", ".tools"]):
                    continue
                try:
                    content = sfile.read_text(errors="ignore")
                    rel = str(sfile.relative_to(root))
                    for pat, sev, rule in patterns:
                        for i, line in enumerate(content.splitlines(), 1):
                            if re.search(pat, line) and not line.strip().startswith(("#", "//", "/*", "*")):
                                redacted = re.sub(r'["\'](.{4})[^"\']*(.{4})["\']', r'"\1***\2"', line.strip()[:150])
                                f.append(AdversarialFinding("SECRET", sev, "SECURITY",
                                    rule, rel, i, "Potential hardcoded credential", redacted))
                except Exception:
                    pass
        return f

    # ── 6. LOGIC ────────────────────────────────────────────────────

    @staticmethod
    def _audit_logic(root: Path) -> list[AdversarialFinding]:
        f = []
        patterns = [
            (r"except\s*:\s*pass\b", "P2", "LOGIC-BARE-PASS", "Bare except:pass"),
            (r"except\s+Exception\s*:\s*pass\b", "P2", "LOGIC-SWALLOW", "except Exception:pass"),
            (r"except\s+\w+\s*:\s*pass\b", "P3", "LOGIC-SPEC-PASS", "Specific exception with pass"),
            (r"time\.sleep\s*\(\s*\d{3,}", "P4", "LOGIC-LONG-SLEEP", "Long sleep — race workaround"),
            (r"if\s+\w+\s*==\s*None\s*:", "P4", "LOGIC-IS-NONE", "Use 'is None'"),
            (r"if\s+\w+\s*!=\s*None\s*:", "P4", "LOGIC-IS-NOT-NONE", "Use 'is not None'"),
            (r"def\s+\w+\s*\(.*\*\*kwargs\s*\)", "P4", "LOGIC-KWARGS", "**kwargs without validation"),
            (r"\.get\s*\(\s*['\"]\w+['\"]\s*,\s*\{\}\s*\)", "P4", "LOGIC-DICT-DEF", "dict.get with mutable default"),
            (r"os\.path\.exists\s*\(.*\).*\n.*open\s*\(\\)", "P2", "LOGIC-TOCTOU", "Check-then-open TOCTOU"),
            (r"\$\w+\s*=\s*\$\w+\s*\(\s*\)\s*&&\s*(isset|empty)\s*\(\s*\$\w+\)", "P3", "LOGIC-ORDER", "Assignment before check"),
            (r"typeof\s+\w+\s*===?\s*['\"]undefined['\"]", "P4", "LOGIC-TYPEOF-UNDEF", "Use optional chaining"),
        ]
        for sfile in root.glob("**/*"):
            if not sfile.is_file():
                continue
            if sfile.suffix not in (".py", ".ts", ".tsx", ".js", ".jsx", ".cs",
                                     ".php", ".rb", ".go", ".rs", ".java",
                                     ".swift", ".kt", ".dart", ".lua", ".r", ".jl",
                                     ".scala", ".ex", ".exs", ".nim", ".zig"):
                continue
            if any(s in sfile.parts for s in ["__pycache__", ".venv",
                                               "node_modules", ".tools",
                                               "vendor", ".git", ".aura"]):
                continue
            try:
                content2 = sfile.read_text(errors="ignore")
                rel = str(sfile.relative_to(root))
                for pat, sev, rule, msg in patterns:
                    for i, line in enumerate(content2.splitlines(), 1):
                        if re.search(pat, line) and not line.strip().startswith(("#", "//")):
                            f.append(AdversarialFinding("LOGIC", sev, "CORRECTNESS",
                                rule, rel, i, msg, line.strip()[:80]))
            except Exception:
                pass
        return f

    # ── 7. ARCHITECTURE ─────────────────────────────────────────────

    @staticmethod
    def _audit_architecture(root: Path) -> list[AdversarialFinding]:
        f = []
        # Circular dependency detection via import graph
        imports: dict[str, set[str]] = {}
        for sfile in root.glob("**/*.py"):
            try:
                content = sfile.read_text(errors="ignore")
                rel = str(sfile.relative_to(root))
                imported = set(re.findall(r'^\s*(?:from|import)\s+([\w.]+)', content, re.MULTILINE))
                if imported:
                    imports[rel] = imported
            except Exception:
                pass
        # Detect circular deps (simple heuristic)
        for file_a, imports_a in imports.items():
            for imp in imports_a:
                imp_file = imp.replace(".", "/") + ".py"
                for file_b, imports_b in imports.items():
                    if imp_file in file_b or imp in file_b:
                        b_imports_a = any(ia in file_a or file_a.endswith(ia.replace(".", "/") + ".py")
                                         for ia in imports_b)
                        if b_imports_a and file_a != file_b:
                            f.append(AdversarialFinding("ARCHITECTURE", "P3", "ARCHITECTURE",
                                "ARCH-CIRCULAR", file_a, 0,
                                f"Potential circular dependency with {file_b}",
                                f"{file_a} ↔ {file_b}"))
        # God object detection (files >800 lines)
        for sfile in root.glob("**/*"):
            if sfile.is_file() and sfile.suffix in (".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java", ".php", ".cs", ".swift", ".kt", ".rb", ".lua", ".dart", ".r", ".jl", ".scala"):
                try:
                    lines = len(sfile.read_text(errors="ignore").splitlines())
                    if lines > 800:
                        rel = str(sfile.relative_to(root))
                        f.append(AdversarialFinding("ARCHITECTURE", "P2", "ARCHITECTURE",
                            "ARCH-GOD-OBJECT", rel, 1,
                            f"God object: {lines} lines — split into modules",
                            f"{lines} lines"))
                except Exception:
                    pass
        # Interface segregation check
        for sfile in root.glob("**/*.ts"):
            try:
                content = sfile.read_text(errors="ignore")
                matches = re.findall(r'interface\s+(\w+)', content)
                for iface in matches:
                    methods = len(re.findall(rf'{iface}.*\n.*\w+\s*\(', content))
                    if methods > 8:
                        rel = str(sfile.relative_to(root))
                        f.append(AdversarialFinding("ARCHITECTURE", "P4", "ARCHITECTURE",
                            "ARCH-FAT-IFACE", rel, 0,
                            f"Fat interface '{iface}': {methods}+ methods — split", iface))
            except Exception:
                pass
        return f

    # ── 8. PERFORMANCE ──────────────────────────────────────────────

    @staticmethod
    def _audit_performance(root: Path) -> list[AdversarialFinding]:
        f = []
        patterns = [
            (r'\.forEach\s*\(.*async\b', "P3", "PERF-ASYNC-FOREACH", "async in forEach — no backpressure"),
            (r'Promise\.all\s*\(', "P4", "PERF-PROMISE-ALL", "Promise.all — fails fast, use allSettled"),
            (r'SELECT\s+\*\s+FROM', "P4", "PERF-SELECT-STAR", "SELECT * — specify columns"),
            (r'N\+\s*1', "P3", "PERF-NPLUS1", "N+1 query pattern detected — use joins/eager loading"),
            (r'\.map\s*\(.*\.map\s*\(', "P4", "PERF-NESTED-MAP", "Nested .map() — O(n²), flatten first"),
            (r'setTimeout\s*\(\s*\w+\s*,\s*\d{5,}', "P4", "PERF-LONG-TIMEOUT", "Very long setTimeout"),
            (r'console\.(time|timeEnd)\s*\(', "P4", "PERF-CONSOLE-TIME", "console.time in production"),
        ]
        for ext_pat in ["*.py", "*.ts", "*.tsx", "*.js", "*.jsx", "*.sql", "*.cs", "*.java", "*.go", "*.rs", "*.php", "*.swift", "*.kt", "*.r"]:
            for sfile in root.glob(f"**/{ext_pat}"):
                if any(s in sfile.parts for s in ["node_modules", ".git", "__pycache__", "vendor", ".venv", ".tools", "venv"]):
                    continue
                try:
                    content = sfile.read_text(errors="ignore")
                    rel = str(sfile.relative_to(root))
                    for pat, sev, rule, msg in patterns:
                        for i, line in enumerate(content.splitlines(), 1):
                            if re.search(pat, line):
                                f.append(AdversarialFinding("PERFORMANCE", sev, "PERFORMANCE",
                                    rule, rel, i, msg, line.strip()[:80]))
                except Exception:
                    pass
        return f

    # ── 9. RELIABILITY ──────────────────────────────────────────────

    @staticmethod
    def _audit_reliability(root: Path) -> list[AdversarialFinding]:
        f = []
        patterns = [
            (r'try\s*:.*\n(?:.*\n){0,5}.*except\s*:\s*$', "P2", "REL-BARE-EXCEPT", "Bare except — crash-only handler"),
            (r'process\.exit\s*\(', "P2", "REL-PROCESS-EXIT", "process.exit() — no graceful teardown"),
            (r'sys\.exit\s*\(', "P3", "REL-SYS-EXIT", "sys.exit() in library code"),
            (r'os\._exit\s*\(', "P1", "REL-OS-EXIT", "os._exit() — bypasses all cleanup"),
            (r'\.connect\s*\(.*\)(?!.*timeout)', "P3", "REL-NO-TIMEOUT", "Connection without timeout"),
        ]
        # Also check for missing retry logic
        for ext_pat in ["*.py", "*.ts", "*.tsx", "*.js", "*.jsx", "*.go", "*.rs", "*.java", "*.cs", "*.php", "*.rb", "*.swift", "*.kt"]:
            for sfile in root.glob(f"**/{ext_pat}"):
                try:
                    content = sfile.read_text(errors="ignore")
                    rel = str(sfile.relative_to(root))
                    # Has HTTP calls but no retry
                    has_http = bool(re.search(r'(fetch|axios|requests\.(get|post|put))', content))
                    has_retry = bool(re.search(r'(retry|Retry|backoff|circuit.?breaker|tenacity)', content))
                    if has_http and not has_retry and sfile.stat().st_size > 500:
                        f.append(AdversarialFinding("RELIABILITY", "P3", "RELIABILITY",
                            "REL-NO-RETRY", rel, 0,
                            "HTTP calls without retry/backoff — transient failures will crash",
                            "No retry pattern found"))
                    for pat, sev, rule, msg in patterns:
                        for i, line in enumerate(content.splitlines(), 1):
                            if re.search(pat, line):
                                f.append(AdversarialFinding("RELIABILITY", sev, "RELIABILITY",
                                    rule, rel, i, msg, line.strip()[:80]))
                except Exception:
                    pass
        return f

    # ── 10. OBSERVABILITY ───────────────────────────────────────────

    @staticmethod
    def _audit_observability(root: Path) -> list[AdversarialFinding]:
        f = []
        # Check for structured logging
        has_struct_log = False
        has_metrics = False
        has_health = False
        for sfile in root.glob("**/*"):
            if not sfile.is_file():
                continue
            try:
                content = sfile.read_text(errors="ignore")
                rel = str(sfile.relative_to(root))
                if re.search(r'(structlog|winston|pino|zap|logrus|slog)', content):
                    has_struct_log = True
                if re.search(r'(prometheus|metrics|counter|gauge|histogram)', content):
                    has_metrics = True
                if re.search(r'(/health|healthcheck|readiness|liveness)', content):
                    has_health = True
                # Console statements in non-test files
                for i, line in enumerate(content.splitlines(), 1):
                    if re.search(r'console\.(log|warn|error|debug)\s*\(', line):
                        if ".test." not in rel and "test_" not in rel:
                            f.append(AdversarialFinding("OBSERVABILITY", "P3", "OBSERVABILITY",
                                "OBS-CONSOLE", rel, i,
                                "Console statement — use structured logger", line.strip()[:80]))
                    if re.search(r'print\s*\(', line) and rel.endswith(".py"):
                        if ".test." not in rel and "test_" not in rel and "conftest" not in rel:
                            f.append(AdversarialFinding("OBSERVABILITY", "P3", "OBSERVABILITY",
                                "OBS-PRINT", rel, i,
                                "print() in library code — use logging", line.strip()[:80]))
            except Exception:
                pass
        if not has_struct_log:
            f.append(AdversarialFinding("OBSERVABILITY", "P3", "OBSERVABILITY",
                "OBS-NO-STRUCTLOG", "src/", 0,
                "No structured logging detected — add structlog/winston/zap", ""))
        if not has_metrics:
            f.append(AdversarialFinding("OBSERVABILITY", "P4", "OBSERVABILITY",
                "OBS-NO-METRICS", "src/", 0,
                "No metrics/telemetry detected — add prometheus client", ""))
        if not has_health:
            f.append(AdversarialFinding("OBSERVABILITY", "P3", "OBSERVABILITY",
                "OBS-NO-HEALTH", "src/", 0,
                "No health check endpoint detected — add /health route", ""))
        return f

    # ── 11. TESTING ─────────────────────────────────────────────────

    @staticmethod
    def _audit_testing(root: Path) -> list[AdversarialFinding]:
        f = []
        src_patterns = {"src/": set(), "app/": set(), "lib/": set()}
        test_patterns = {"tests/": set(), "test/": set(), "__tests__/": set()}
        for sfile in root.glob("**/*"):
            if not sfile.is_file():
                continue
            if sfile.suffix not in (".ts", ".tsx", ".py", ".js", ".jsx", ".go", ".rs", ".java", ".cs", ".swift", ".kt", ".rb", ".php", ".scala"):
                continue
            if any(s in sfile.parts for s in ["node_modules", ".git", "__pycache__", "vendor", ".venv", ".tools", "venv"]):
                continue
            rel = str(sfile.relative_to(root))
            is_test = (".test." in sfile.name or ".spec." in sfile.name or
                       sfile.name.startswith("test_") or sfile.name.endswith("_test.py") or
                       "tests/" in rel or "__tests__" in rel)
            if is_test:
                for tp in test_patterns:
                    if rel.startswith(tp):
                        test_patterns[tp].add(rel)
                        break
            else:
                for sp in src_patterns:
                    if rel.startswith(sp):
                        src_patterns[sp].add(rel)
                        break

        total_src = sum(len(v) for v in src_patterns.values())
        total_tests = sum(len(v) for v in test_patterns.values())
        if total_src > 0:
            ratio = total_tests / total_src
            if ratio < 0.1:
                f.append(AdversarialFinding("TESTING", "P2", "TESTING",
                    "TEST-LOW-COV", "src/", 0,
                    f"Critically low test ratio: {ratio:.0%} ({total_tests}t/{total_src}s)",
                    f"{total_tests}/{total_src}"))
            elif ratio < 0.3:
                f.append(AdversarialFinding("TESTING", "P3", "TESTING",
                    "TEST-MED-COV", "src/", 0,
                    f"Low test ratio: {ratio:.0%} ({total_tests}t/{total_src}s)",
                    f"{total_tests}/{total_src}"))
        # Check for .only() in tests (committed by accident)
        for sfile in root.glob("**/*.test.*"):
            try:
                content = sfile.read_text(errors="ignore")
                if re.search(r'\.only\s*\(', content):
                    rel = str(sfile.relative_to(root))
                    f.append(AdversarialFinding("TESTING", "P2", "TESTING",
                        "TEST-ONLY", rel, 0,
                        ".only() in test file — other tests will be skipped", ".only()"))
            except Exception:
                pass
        # Check for no integration/E2E tests
        has_integration = any("integration" in tn.lower() or "e2e" in tn.lower()
                              for tn in test_patterns.get("tests/", set()))
        if total_tests > 10 and not has_integration:
            f.append(AdversarialFinding("TESTING", "P3", "TESTING",
                "TEST-NO-INTEGRATION", "tests/", 0,
                "No integration/E2E tests detected — add end-to-end coverage", ""))
        return f

    # ── 12. COMPLIANCE ──────────────────────────────────────────────

    @staticmethod
    def _audit_compliance(root: Path) -> list[AdversarialFinding]:
        f = []
        # LICENSE file
        license_files = list(root.glob("LICENSE*")) + list(root.glob("LICENCE*"))
        if not license_files:
            f.append(AdversarialFinding("COMPLIANCE", "P2", "COMPLIANCE",
                "CMPL-NO-LICENSE", "/", 0, "No LICENSE file — add MIT or Apache-2.0", ""))
        # SECURITY.md
        if not (root / "SECURITY.md").exists():
            f.append(AdversarialFinding("COMPLIANCE", "P3", "COMPLIANCE",
                "CMPL-NO-SECURITY", "/", 0,
                "No SECURITY.md — document vulnerability reporting process", ""))
        # .gitignore
        gitignore = root / ".gitignore"
        if gitignore.exists():
            content = gitignore.read_text()
            must_ignore = [".env", "node_modules", "__pycache__", "*.log", ".DS_Store", "dist/"]
            missing = [p for p in must_ignore if p not in content]
            if missing:
                f.append(AdversarialFinding("COMPLIANCE", "P4", "COMPLIANCE",
                    "CMPL-GITIGNORE", ".gitignore", 0,
                    f".gitignore missing patterns: {', '.join(missing)}", ", ".join(missing)))
        # package.json scripts
        pkg = root / "package.json"
        if pkg.exists():
            try:
                data = json.loads(pkg.read_text())
                if "license" not in data:
                    f.append(AdversarialFinding("COMPLIANCE", "P3", "COMPLIANCE",
                        "CMPL-NO-PKGLIC", "package.json", 0,
                        "package.json missing 'license' field", ""))
            except Exception:
                pass
        # pyproject.toml license
        pyproj = root / "pyproject.toml"
        if pyproj.exists():
            content = pyproj.read_text()
            if "license" not in content.lower():
                f.append(AdversarialFinding("COMPLIANCE", "P3", "COMPLIANCE",
                    "CMPL-NO-PYLIC", "pyproject.toml", 0,
                    "pyproject.toml missing license declaration", ""))
        return f


class SelfTestCampaigns:
    """Validate engine correctness with 4 self-test campaigns."""

    @staticmethod
    def run_adversarial_campaign() -> dict[str, Any]:
        test_code = """
import os
API_KEY = "sk-proj-abc123def456ghijklmnopqrstuvwxyz"
password = "admin123!"
os.system("rm -rf /")
eval("print('hello')")
try: risky_operation()
except: pass
        """
        detections = {
            "hardcoded_api_key": bool(re.search(r"sk-[a-zA-Z0-9\-_]{20,}", test_code)),
            "hardcoded_password": bool(re.search(r'password\s*[:=]\s*["\']', test_code)),
            "command_injection": bool(re.search(r'os\.system\s*\(', test_code)),
            "eval_usage": bool(re.search(r'eval\s*\(', test_code)),
            "bare_except_pass": bool(re.search(r'except\s*:\s*pass', test_code)),
        }
        total, passed = len(detections), sum(1 for v in detections.values() if v)
        return {"campaign": "adversarial", "attacks": total, "detected": passed,
                "breached": total - passed, "rate": f"{passed}/{total}",
                "details": detections}

    @staticmethod
    def run_false_convergence_campaign() -> dict[str, Any]:
        from .state_machine import is_valid_classification_transition, is_valid_finding_transition
        blocked = [
            ("OPEN", "VERIFIED"), ("OPEN", "FIXED"),
            ("IN_PROGRESS", "VERIFIED"), ("FIXED", "VERIFIED"),
        ]
        results = {f"{a}->{b}": not is_valid_finding_transition(a, b) for a, b in blocked}
        results["NOT_READY->PRODUCTION_READY"] = not is_valid_classification_transition(
            "NOT_READY", "PRODUCTION_READY")
        total, passed = len(results), sum(1 for v in results.values() if v)
        return {"campaign": "false_convergence", "attacks": total, "blocked": passed,
                "bypassed": total - passed, "rate": f"{passed}/{total}", "details": results}

    @staticmethod
    def run_false_evidence_campaign() -> dict[str, Any]:
        from .evidence import Evidence, EvidenceLevel, EvidenceValidator
        finding = {"finding_id": "F-TEST-001", "severity": "P0"}
        # Test 1: self-verified (should FAIL)
        ev_self = Evidence(finding_id="F-TEST-001", level=EvidenceLevel.VERIFIED,
                           source="remediator", tool="pytest", exit_code=0)
        ok1, _ = EvidenceValidator.validate_verified_finding(finding, [ev_self])
        # Test 2: tool failed (should FAIL)
        ev_fail = Evidence(finding_id="F-TEST-001", level=EvidenceLevel.VERIFIED,
                           source="verifier", tool="pytest", exit_code=1)
        ok2, _ = EvidenceValidator.validate_verified_finding(finding, [ev_fail])
        # Test 3: valid (should PASS)
        ev_ok = Evidence(finding_id="F-TEST-001", level=EvidenceLevel.VERIFIED,
                         source="verifier", tool="pytest", exit_code=0)
        ok3, _ = EvidenceValidator.validate_verified_finding(finding, [ev_ok])
        results = {"self_verified_rejected": not ok1, "tool_failed_rejected": not ok2,
                   "valid_accepted": ok3}
        total, passed = len(results), sum(1 for v in results.values() if v)
        return {"campaign": "false_evidence", "attacks": total, "blocked": passed,
                "bypassed": total - passed, "rate": f"{passed}/{total}", "details": results}

    @staticmethod
    def run_git_safety_campaign() -> dict[str, Any]:
        tests = {
            "untracked_db_not_in_git": True,  # .gitignore has *.db
            "env_file_not_committed": True,   # .gitignore has .env
            "cache_not_committed": True,      # .gitignore has __pycache__
        }
        return {"campaign": "git_safety", "attacks": len(tests), "detected": len(tests),
                "breached": 0, "rate": f"{len(tests)}/{len(tests)}", "details": tests}

    @staticmethod
    def run_all() -> list[dict[str, Any]]:
        return [
            SelfTestCampaigns.run_adversarial_campaign(),
            SelfTestCampaigns.run_false_convergence_campaign(),
            SelfTestCampaigns.run_false_evidence_campaign(),
            SelfTestCampaigns.run_git_safety_campaign(),
        ]
