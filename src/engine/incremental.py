"""
Incremental audit engine for Python orchestrator.
Determines optimal audit scope per cycle to balance thoroughness vs efficiency.

This module implements the heuristics described in the incremental-audit.ps1 module
and complements the smart-prioritization.ps1 rotation planning.

Design goals:
  - Minimize duplicate full-spectrum audits
  - Focus each cycle on files most likely to harbor defects
  - Maintain full-codebase coverage over rolling windows
  - React to dependency-graph propagation
"""

import hashlib
import json
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime as _dt
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple


class AuditTier(Enum):
    TIER_1 = "tier_1"   # Score >= 70: must audit this cycle
    TIER_2 = "tier_2"   # Score 40-69: rotate through
    TIER_3 = "tier_3"   # Score < 40: low priority


class AuditMode(Enum):
    FULL = "full"
    DIFFERENTIAL = "differential"


@dataclass
class FilePriority:
    path: str
    churn_score: float = 0.0       # 0-100
    criticality_score: float = 0.0  # 0-100
    bug_density_score: float = 0.0  # 0-100
    combined_score: float = 0.0     # 0-100
    tier: AuditTier = AuditTier.TIER_3
    reason: str = ""


@dataclass
class AuditPlan:
    mode: AuditMode
    rationale: str
    cycle: int
    total_repo_files: int = 0
    changed_count: int = 0
    audit_files: List[FilePriority] = field(default_factory=list)
    force_full: bool = False
    has_prior_audit: bool = False


@dataclass
class SmartAuditPlan:
    cycle: int
    plan: List[FilePriority] = field(default_factory=list)
    total_planned: int = 0
    max_per_cycle: int = 50
    tier_1_count: int = 0
    tier_2_count: int = 0
    tier_3_count: int = 0
    dependency_affected: int = 0
    hotspot_included: int = 0
    tier_2_pool_size: int = 0
    tier_3_pool_size: int = 0


class IncrementalAuditEngine:
    """Primary engine for computing differential audit scope and file priorities."""

    _ENTRY_POINT_DIRS = {
        "controller", "route", "handler", "middleware", "service",
        "resolver", "endpoint", "api",
    }
    _CONFIG_DIRS = {"config", "settings", "env", "secrets"}
    _TEST_DIRS = {"test", "spec", "__tests__", "t/", "spec/"}
    _MANIFEST_NAMES = {
        "composer.json", "package.json", "pyproject.toml",
        "Cargo.toml", "go.mod", "Makefile", "Dockerfile",
        "docker-compose",
    }
    _LOW_RISK_EXTS = {".md", ".txt", ".rst", ".adoc"}

    def __init__(
        self,
        repo_path: str,
        engine_root: str,
        config: Optional[dict] = None,
    ):
        self.repo_path = Path(repo_path).resolve()
        self.engine_root = Path(engine_root).resolve()
        self.config = config or self._default_config()

    @staticmethod
    def _default_config() -> dict:
        return {
            "enabled": True,
            "mode": "auto",
            "full_audit_every_n_cycles": 5,
            "max_differential_pct": 20,
            "churn_window_days": 90,
            "tier_1_threshold": 70,
            "tier_2_threshold": 40,
            "tier_2_rotation_pct": 30,
            "tier_3_rotation_pct": 10,
            "prioritization": {
                "churn_weight": 0.35,
                "criticality_weight": 0.40,
                "bug_density_weight": 0.15,
                "author_bug_rate_weight": 0.10,
            },
        }

    # -----------------------------------------------------------------
    # GIT HELPERS
    # -----------------------------------------------------------------

    def _git(self, *args: str, cwd: Optional[Path] = None) -> Tuple[int, str]:
        target = cwd or self.repo_path
        try:
            result = subprocess.run(
                ["git", *args],
                cwd=str(target),
                capture_output=True,
                text=True,
                timeout=30,
            )
            return result.returncode, result.stdout
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
            return -1, str(exc)

    def _git_lines(self, *args: str) -> List[str]:
        rc, out = self._git(*args)
        if rc != 0:
            return []
        return [line.strip() for line in out.splitlines() if line.strip()]

    # -----------------------------------------------------------------
    # CHANGE DETECTION
    # -----------------------------------------------------------------

    def get_changed_files(self, base_commit: Optional[str] = None) -> List[Dict[str, str]]:
        """Returns files changed since a base commit (or HEAD~1)."""
        changed: List[Dict[str, str]] = []

        if base_commit:
            rc, out = self._git("diff", "--name-status", base_commit, "HEAD")
        else:
            rc, out = self._git("diff", "--name-status", "HEAD~1", "HEAD")

        if rc != 0:
            rc2, out2 = self._git("ls-files")
            if rc2 == 0:
                for f in out2.splitlines():
                    f = f.strip()
                    if f:
                        changed.append({"file": f, "status": "initial"})
            return changed

        for line in out.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split(None, 1)
            if len(parts) >= 2:
                changed.append({"file": parts[1], "status": parts[0]})

        return changed

    def get_file_change_type(self, filepath: str, base_commit: str) -> str:
        """Returns 'added', 'modified', 'deleted', 'renamed', 'unchanged' or 'unknown'."""
        rc, out = self._git("diff", "--name-status", base_commit, "HEAD", "--", filepath)
        if rc != 0:
            rc2, out2 = self._git("diff", "--name-status", "HEAD~1", "HEAD", "--", filepath)
            if rc2 != 0:
                return "unknown"
            out = out2

        trimmed = out.strip()
        if not trimmed:
            return "unchanged"

        first = trimmed[0]
        mapping = {
            "A": "added", "M": "modified", "D": "deleted",
            "R": "renamed", "C": "copied", "T": "type-changed",
        }
        return mapping.get(first, "modified")

    def get_total_tracked_files(self) -> int:
        rc, out = self._git("ls-files")
        if rc != 0:
            return 0
        return len([l for l in out.splitlines() if l.strip()])

    # -----------------------------------------------------------------
    # SCORING FUNCTIONS
    # -----------------------------------------------------------------

    def compute_file_churn(self, filepath: str, window_days: int = 90) -> float:
        """Churn score (0-100) based on commit frequency in window."""
        since = (_dt.datetime.now() - _dt.timedelta(days=window_days)).strftime("%Y-%m-%d")

        rc, out = self._git("log", "--oneline", f"--since={since}", "--", filepath)
        commit_count = len([l for l in out.splitlines() if l.strip()]) if rc == 0 else 0

        if commit_count == 0:
            return 0.0

        total_commits = len(self._git_lines("log", "--oneline"))
        if total_commits == 0:
            return 0.0

        max_churn_per_file = max(1, round(total_commits * 0.1))
        score = min(100.0, (commit_count / max_churn_per_file) * 100)
        return max(5.0, score)

    def compute_file_criticality(self, filepath: str, graph_data: Optional[dict] = None) -> float:
        """Criticality score (0-100) based on architectural role and dependencies."""
        normalized = filepath.replace("\\", "/").lstrip("/")
        fname = Path(normalized).name.lower()
        parent_dir = Path(normalized).parent.as_posix().lower() if Path(normalized).parent.as_posix() else "."

        score = 30.0

        entry_names = {"index", "main", "app", "server", "bootstrap", "startup", "kernel", "init", "run"}
        if any(fname.startswith(n) for n in entry_names):
            score += 35.0
        elif any(d in parent_dir for d in self._ENTRY_POINT_DIRS):
            score += 25.0

        if any(d in parent_dir for d in self._CONFIG_DIRS):
            score += 20.0
        if any(p in fname for p in ("config", "settings", "env", "secret", ".env.", ".config.")):
            score += 20.0

        if fname in self._MANIFEST_NAMES:
            score += 30.0

        if any(d in parent_dir for d in self._TEST_DIRS) or any(
            p in fname for p in ("test", "spec", ".test.", ".spec.", "_test.")
        ):
            score -= 25.0

        ext = Path(normalized).suffix.lower()
        if ext in self._LOW_RISK_EXTS:
            score -= 20.0

        if graph_data:
            dep_graph = graph_data.get("dependency_graph", {})
            dependents = 0
            for dep_file, deps in dep_graph.items():
                if not deps:
                    continue
                for d in deps:
                    d_file = d.get("file", "") if isinstance(d, dict) else ""
                    if d_file and fname in d_file:
                        dependents += 1
            if dependents >= 10:
                score += 25.0
            elif dependents >= 5:
                score += 15.0
            elif dependents >= 2:
                score += 8.0

        full_path = self.repo_path / normalized
        if full_path.exists():
            try:
                content = full_path.read_text(encoding="utf-8", errors="ignore")
                entry_patterns = [
                    "def main", "if __name__ == '__main__'", 'if __name__ == "__main__"',
                    "public static void main", "func main(",
                    "entry_point", "console_command", "handle()",
                ]
                if any(p in content for p in entry_patterns):
                    score += 10.0
            except OSError:
                pass

        return max(5.0, min(100.0, score))

    def compute_bug_density(self, filepath: str, cycle: int) -> float:
        """Bug density score (0-100) based on prior findings in findings.json."""
        normalised = filepath.replace("\\", "/").lstrip("/")
        score = 0.0

        findings_path = self.engine_root / "state" / "findings.json"
        if not findings_path.exists():
            return 0.0

        try:
            findings_data = json.loads(findings_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return 0.0

        all_findings = findings_data.get("findings", [])
        file_findings = [f for f in all_findings if f.get("file", "") and normalised in str(f["file"])]

        severity_weights = {"P0": 30, "P1": 20, "P2": 12, "P3": 6, "P4": 3, "P5": 1}
        for f in file_findings:
            score += severity_weights.get(f.get("severity", ""), 0)

        recent = [f for f in file_findings if f.get("cycle_number") and (cycle - int(f["cycle_number"])) <= 3]
        if recent:
            score = min(100.0, score + len(recent) * 8)

        old = [f for f in file_findings if f.get("cycle_number") and (cycle - int(f["cycle_number"])) > 5]
        if old:
            score = max(0.0, score - len(old) * 5)

        return max(0.0, min(100.0, score))

    def get_author_bug_rates(self) -> Dict[str, float]:
        """Computes per-author bug rate (0-1) from git commit messages."""
        author_stats: Dict[str, Dict[str, int]] = {}
        lines = self._git_lines("log", "--format=%ae|%s", "--max-count=2000")
        if not lines:
            return {}

        bug_patterns_lower = [
            "fix", "bug", "hotfix", "patch", "vuln", "security",
            "cve", "crash", "segfault", "null", "oob", "overflow",
            "inject", "race", "deadlock",
        ]
        non_bug_patterns_lower = [
            "refactor", "docs", "style", "chore", "typo", "format",
            "lint", "cleanup", "spelling", "comment", "readme",
        ]

        for line in lines:
            parts = line.split("|", 1)
            if len(parts) < 2:
                continue
            email = parts[0].strip().lower()
            subject = parts[1].lower()

            if email not in author_stats:
                author_stats[email] = {"total": 0, "bug_commits": 0, "non_bug": 0}

            author_stats[email]["total"] += 1

            is_bug = any(p in subject for p in bug_patterns_lower)
            is_non_bug = any(p in subject for p in non_bug_patterns_lower)

            if is_bug and not is_non_bug:
                author_stats[email]["bug_commits"] += 1
            elif is_non_bug and not is_bug:
                author_stats[email]["non_bug"] += 1

        result: Dict[str, float] = {}
        for email, stats in author_stats.items():
            if stats["total"] < 5:
                continue
            rated = stats["bug_commits"] + stats["non_bug"]
            if rated == 0:
                continue
            result[email] = round(stats["bug_commits"] / rated, 3)

        return result

    # -----------------------------------------------------------------
    # PRIORITY COMPUTATION
    # -----------------------------------------------------------------

    def compute_priority(
        self,
        filepath: str,
        cycle: int,
        graph_data: Optional[dict] = None,
    ) -> FilePriority:
        """Computes the combined priority score for a single file."""
        w = self.config.get("prioritization", self._default_config()["prioritization"])

        churn = self.compute_file_churn(filepath)
        criticality = self.compute_file_criticality(filepath, graph_data)
        bug_density = self.compute_bug_density(filepath, cycle)

        author_bug = 0.0
        try:
            rates = self.get_author_bug_rates()
            lines = self._git_lines("log", "-1", "--format=%ae", "--", filepath)
            if lines:
                email = lines[0]
                if email in rates:
                    author_bug = round(rates[email] * 100, 1)
        except Exception:
            pass

        combined = round(
            (churn * w.get("churn_weight", 0.35))
            + (criticality * w.get("criticality_weight", 0.40))
            + (bug_density * w.get("bug_density_weight", 0.15))
            + (author_bug * w.get("author_bug_rate_weight", 0.10)),
            1,
        )

        if combined >= self.config.get("tier_1_threshold", 70):
            tier = AuditTier.TIER_1
            reason = f"High priority: combined score >= {self.config.get('tier_1_threshold', 70)}"
        elif combined >= self.config.get("tier_2_threshold", 40):
            tier = AuditTier.TIER_2
            reason = f"Medium priority: combined score {self.config.get('tier_2_threshold', 40)}-69"
        else:
            tier = AuditTier.TIER_3
            reason = f"Low priority: combined score < {self.config.get('tier_2_threshold', 40)}"

        return FilePriority(
            path=filepath,
            churn_score=churn,
            criticality_score=criticality,
            bug_density_score=bug_density,
            combined_score=combined,
            tier=tier,
            reason=reason,
        )

    def compute_priorities(
        self,
        files: List[str],
        cycle: int,
        graph_data: Optional[dict] = None,
    ) -> List[FilePriority]:
        """Computes priorities for a list of files, returning them sorted descending."""
        results = [self.compute_priority(f, cycle, graph_data) for f in files]
        results.sort(key=lambda p: p.combined_score, reverse=True)
        return results

    # -----------------------------------------------------------------
    # AUDIT SCOPE PLANNING
    # -----------------------------------------------------------------

    def should_full_audit(self, cycle: int) -> bool:
        """Determines if a full audit is needed this cycle."""
        config = self.config
        full_every = config.get("full_audit_every_n_cycles", 5)
        if cycle % full_every == 0:
            return True

        cache = self.load_audit_cache()
        if not cache or not cache.get("commit"):
            return True  # no prior audit

        changed = self.get_changed_files(cache.get("commit"))
        total = self.get_total_tracked_files()

        if total == 0:
            return True

        changed_pct = (len(changed) / total) * 100
        max_pct = config.get("max_differential_pct", 20)

        return changed_pct >= max_pct

    def get_audit_plan(
        self,
        cycle: int,
        graph_data: Optional[dict] = None,
        max_files: int = 50,
    ) -> AuditPlan:
        """Returns the optimal audit plan for this cycle."""
        total = self.get_total_tracked_files()
        cache = self.load_audit_cache()
        last_commit = cache.get("commit") if cache else None
        force_full = (cycle % self.config.get("full_audit_every_n_cycles", 5) == 0)
        has_prior = bool(last_commit)

        changed = self.get_changed_files(last_commit) if last_commit else []
        if not last_commit:
            rc, out = self._git("ls-files")
            if rc == 0:
                changed = [{"file": f.strip(), "status": "initial"} for f in out.splitlines() if f.strip()]

        if not has_prior:
            mode = AuditMode.FULL
            rationale = "No prior audit commit recorded — performing full audit."
        elif force_full:
            mode = AuditMode.FULL
            rationale = f"Cycle {cycle} is a scheduled full audit (every {self.config.get('full_audit_every_n_cycles', 5)} cycles)."
        else:
            changed_pct = (len(changed) / total * 100) if total > 0 else 100
            max_pct = self.config.get("max_differential_pct", 20)
            if changed_pct < max_pct:
                mode = AuditMode.DIFFERENTIAL
                rationale = f"Only {changed_pct:.1f}% of files changed (< {max_pct}% threshold) — differential audit."
            else:
                mode = AuditMode.FULL
                rationale = f"{changed_pct:.1f}% of files changed (>= {max_pct}% threshold) — full audit required."

        if mode == AuditMode.DIFFERENTIAL:
            existing = [c["file"] for c in changed if c["status"] != "D" and (self.repo_path / c["file"]).exists()]
            priorities = self.compute_priorities(existing, cycle, graph_data)
            tier1 = [p for p in priorities if p.tier == AuditTier.TIER_1]

            audit_files: List[FilePriority] = list(tier1)

            all_files = self._collect_repo_files()
            all_priorities = self.compute_priorities(all_files, cycle, graph_data)
            tier2_3 = [p for p in all_priorities if p.tier != AuditTier.TIER_1]
            tier1_set = {p.path for p in tier1}
            audit_files.extend([p for p in tier2_3 if p.path not in tier1_set][:15])
        else:
            all_files = self._collect_repo_files()
            audit_files = self.compute_priorities(all_files, cycle, graph_data)

        return AuditPlan(
            mode=mode,
            rationale=rationale,
            cycle=cycle,
            total_repo_files=total,
            changed_count=len(changed),
            audit_files=audit_files[:max_files],
            force_full=force_full,
            has_prior_audit=has_prior,
        )

    # -----------------------------------------------------------------
    # CACHE PERSISTENCE
    # -----------------------------------------------------------------

    def _cache_path(self) -> Path:
        return self.engine_root / "state" / "audit-cache.json"

    def load_audit_cache(self) -> Optional[dict]:
        path = self._cache_path()
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    def save_audit_cache(self, commit_hash: str, audited_files: Optional[List[str]] = None):
        path = self._cache_path()
        path.parent.mkdir(parents=True, exist_ok=True)

        existing = self.load_audit_cache() or {}
        cache: Dict[str, Any] = {
            "version": "1.0.0",
            "commit": commit_hash,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "repo_path": str(self.repo_path),
            "previous_commit": existing.get("commit"),
            "previous_timestamp": existing.get("timestamp"),
            "total_cycles": int(existing.get("total_cycles", 0)) + 1,
            "files": existing.get("files", {}),
        }

        if audited_files:
            for f in audited_files:
                full = self.repo_path / f
                if full.exists():
                    cache["files"][f] = self._file_hash(full)

        path.write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8")

    @staticmethod
    def _file_hash(filepath: Path) -> Dict[str, Any]:
        """Fast hash based on path + size + mtime (not full content)."""
        try:
            st = filepath.stat()
            raw = f"{filepath}|{st.st_size}|{st.st_mtime}".encode("utf-8")
            digest = hashlib.sha256(raw).hexdigest()
            return {"hash": digest, "last_audited_cycle": 0, "last_audited_at": ""}
        except OSError:
            return {"hash": "", "last_audited_cycle": 0, "last_audited_at": ""}

    # -----------------------------------------------------------------
    # HELPERS
    # -----------------------------------------------------------------

    def _collect_repo_files(self) -> List[str]:
        """Collects all tracked source files excluding git/aura/node_modules/vendor."""
        lines = self._git_lines("ls-files")
        if not lines:
            return []

        exclude = {".git/", ".aura/", "node_modules/", "vendor/", "__pycache__/"}
        result = []
        for f in lines:
            if any(f.replace("\\", "/").startswith(e) for e in exclude):
                continue
            result.append(f)
        return result

    def get_dependency_impact(
        self,
        changed_files: List[str],
        graph_data: Optional[dict] = None,
    ) -> List[str]:
        """Finds files whose importers/dependents would be affected by changes."""
        if not graph_data:
            return []

        dep_graph = graph_data.get("dependency_graph", {})
        if not dep_graph:
            return []

        changed_norm: Set[str] = set()
        for f in changed_files:
            n = f.replace("\\", "/").lstrip("/")
            changed_norm.add(n)
            changed_norm.add(Path(n).name)

        impacted = []
        seen: Set[str] = set()

        for dep_file, deps in dep_graph.items():
            if not deps:
                continue
            for d in deps:
                d_file = d.get("file", "") if isinstance(d, dict) else ""
                d_file = d_file.replace("\\", "/").lstrip("/")

                if d_file and d_file in changed_norm:
                    if dep_file not in seen:
                        seen.add(dep_file)
                        impacted.append(dep_file)
                    break

        return impacted


def create_incremental_engine(
    repo_path: str,
    engine_root: str,
    config: Optional[dict] = None,
) -> IncrementalAuditEngine:
    """Factory function for the IncrementalAuditEngine."""
    return IncrementalAuditEngine(repo_path, engine_root, config)