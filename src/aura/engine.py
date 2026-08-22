"""AURA engine core — full 13-phase autonomous audit-remediate-verify engine.

Integrates: multi-lang code analysis, 12 adversarial roles,
semantic intelligence (AST, taint, confidence, memory),
evidence chain with cryptographic validation, SAST tooling,
LLM-powered autonomous audit loop, push approval, trend tracking,
and self-test campaigns.

Core principles:
  - LLM output = UNTRUSTED CLAIM until validated by evidence
  - Tool execution = OBSERVABLE EVIDENCE (exit codes, output)
  - Semantic analysis = REDUCES FALSE POSITIVES (AST + taint + framework)
  - Framework awareness = CONTEXT-AWARE SCORING
  - Repository memory = LEARNS ACROSS CYCLES
  - Independent verification = CROSS-CHECK (not self-verified)
  - State machine = ENFORCED (no shortcut transitions)
  - Convergence = ALL 12 gates + evidence integrity + consecutive clean audits
  - Semantic score = RISK-BASED (not finding-count-based)"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .finding_subclass import classify_finding, is_blocking_for_gate, FindingSubclass, get_finding_subtype_counts

from .adversarial import AdversarialAuditor, SelfTestCampaigns
from .domain_auditor import DomainAuditOrchestrator
from .analyzer import MultiLangAnalyzer, TrendAnalyzer
from .semantic import SemanticAuditor, ConfidenceLevel, FindingEvidence
from .execution_context import ExecutionContextClassifier, ExecutionContext
from .config import AuraConfig
from .db import Database
from .evidence import Evidence, EvidenceChain, EvidenceLevel, EvidenceValidator
from .llm import AutonomousLoop, LLMClient
from .logging import log
from .state_machine import (
    compute_convergence_score,
    evaluate_all_gates,
)


class Engine:
    """Full AURA audit engine — 13 phases with LLM-powered autonomous loop."""

    PHASES = [
        "DISCOVER", "MODEL", "AUDIT", "ADVERSARIAL_AUDIT", "CORRELATE",
        "PRIORITIZE", "REMEDIATE", "TEST", "VERIFY", "REGRESSION",
        "UPDATE_STATE", "CONVERGENCE", "PUSH_APPROVAL",
    ]

    @staticmethod
    def _stable_finding_id(file: str, line: int, rule: str, prefix: str = "F") -> str:
        """Generate a stable finding ID from content, NOT timestamp.

        Stable IDs ensure regression detection works across cycles:
        same file:line:rule always produces the same ID.
        """
        content = f"{file}:{line}:{rule}"
        digest = hashlib.sha256(content.encode()).hexdigest()[:12]
        return f"{prefix}-{digest}"

    def __init__(self, repo_root: str | Path, config: AuraConfig | None = None,
                 llm_client: LLMClient | None = None) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.config = config or AuraConfig.from_env_or_file(self.repo_root)
        self.db = Database(self.config.database)
        self.analyzer = MultiLangAnalyzer(self.repo_root)
        self.adversarial = AdversarialAuditor()
        self.evidence_chain = EvidenceChain()
        self.llm = llm_client
        self.autonomous = AutonomousLoop(self.llm, str(self.repo_root)) if self.llm else None
        self._log = log.bind(repo_root=str(self.repo_root))
        self.semantic = SemanticAuditor(self.repo_root)
        self.domain_orch = DomainAuditOrchestrator(self.repo_root)
        self.context = ExecutionContextClassifier(self.repo_root)
        self._module_integrity = self._check_module_integrity()

    @staticmethod
    def _check_module_integrity() -> bool:
        """Verify required engine modules are importable (fail-closed gate input).

        Replaces the previous hardcoded `module_integrity_pass=True` (IMP-02).
        """
        required = (
            "aura.analyzer", "aura.adversarial", "aura.domain_auditor",
            "aura.semantic", "aura.execution_context", "aura.finding_subclass",
            "aura.state_machine", "aura.convergence", "aura.evidence",
            "aura.config", "aura.db", "aura.errors", "aura.llm",
            "aura.providers", "aura.logging",
        )
        import importlib
        for name in required:
            try:
                importlib.import_module(name)
            except Exception as e:
                log.warning("ModuleIntegrity failed", module=name, error=str(e))
                return False
        return True

    # ── Lifecycle ───────────────────────────────────────────────────────

    def initialize(self) -> None:
        self.db.initialize()
        if not self.db.get_latest_cycle():
            self._init_cycle_1()

    def _init_cycle_1(self) -> None:
        self.db.insert_cycle(cycle_number=1, phase="INIT", status="RUNNING",
                             classification="NOT_READY")
        self.db.upsert_convergence(cycle_number=1, classification="NOT_READY",
                                   converged=0, overall_score=0,
                                   consecutive_converged_cycles=0,
                                   audits_since_last_finding=0,
                                   reason="Cycle 1 — initial state.")
        gates = [
            ("P0_zero", True), ("P1_zero", True), ("P2_zero", True),
            ("critical_security", True), ("critical_correctness", True),
            ("data_integrity", True), ("regression", True),
            ("verification", True), ("no_material_new_findings", True),
            ("limitations_documented", False),
            ("consecutive_clean_independent_audits", False),
            ("module_dependency_integrity", True),
        ]
        for gn, pv in gates:
            self.db.upsert_gate(1, gn, pv, "Clean start" if pv else "Needs runtime")

    def run_audit(self) -> dict[str, Any]:
        self.initialize()
        latest = self.db.get_latest_cycle()
        if not latest:
            raise RuntimeError("Not initialized")
        cn = latest["cycle_number"] + 1
        self._start_cycle(cn)

        # Observability (IMP-09): unique cycle ID bound to all logs this run,
        # per-phase durations recorded to the audit log.
        import time as _time
        import uuid as _uuid
        cycle_id = _uuid.uuid4().hex[:12]
        cycle_log = self._log.bind(cycle_id=cycle_id, cycle=cn)
        phase_durations: dict[str, float] = {}

        # Phase map
        phases = {
            1: ("DISCOVER", self._phase_discover),
            2: ("MODEL", self._phase_model),
            3: ("AUDIT", self._phase_audit),
            4: ("ADVERSARIAL_AUDIT", self._phase_adversarial),
            5: ("CORRELATE", self._phase_correlate),
            6: ("PRIORITIZE", self._phase_prioritize),
            7: ("REMEDIATE", self._phase_remediate),
            8: ("TEST", self._phase_test),
            9: ("VERIFY", self._phase_verify),
            10: ("REGRESSION", self._phase_regression),
            11: ("UPDATE_STATE", self._phase_update_state),
            12: ("CONVERGENCE", self._phase_convergence),
            13: ("PUSH_APPROVAL", self._phase_push_approval),
        }

        ctx: dict[str, Any] = {"cn": cn, "cycle_id": cycle_id}
        for order in sorted(phases):
            name, handler = phases[order]
            cycle_log.info("Phase", phase=name)
            self.db.update_cycle(cn, phase=name)
            _t0 = _time.perf_counter()
            handler(cn, ctx)
            phase_durations[name] = round(_time.perf_counter() - _t0, 3)

        self.db.insert_audit_log(
            "CYCLE_OBSERVABILITY",
            f"cycle_id={cycle_id} phase_durations={phase_durations}",
            cn,
            metadata={"cycle_id": cycle_id, "phase_durations_s": phase_durations},
        )
        return self._complete_cycle(cn, ctx)

    def _start_cycle(self, cn: int) -> None:
        self.db.insert_cycle(cycle_number=cn, phase="DISCOVER",
                             status="RUNNING", classification="NOT_READY")
        self.db.upsert_convergence(cycle_number=cn, classification="NOT_READY",
                                   converged=0, overall_score=0,
                                   consecutive_converged_cycles=0,
                                   audits_since_last_finding=0,
                                   reason=f"Cycle {cn} — starting.")

    # ── Phase Implementations (13 phases) ──────────────────────────────

    def _phase_discover(self, cn: int, ctx: dict) -> None:
        ctx["git"] = self._get_git_context()
        ctx["languages"] = self._detect_languages()
        log_msg = (f"Repo: {ctx['git'].get('FileCount', 0)} files, "
                   f"{len(ctx['languages'])} langs, "
                   f"branch={ctx['git'].get('Branch', '?')}")
        self.db.insert_audit_log("DISCOVER", log_msg, cn)

    def _phase_model(self, cn: int, ctx: dict) -> None:
        """Build architecture model of the repository."""
        lang_list = sorted(ctx["languages"].items(), key=lambda x: -x[1])
        ctx["model"] = {
            "project_type": self._detect_project_type(),
            "languages": [{"ext": e, "count": c} for e, c in lang_list],
            "file_count": ctx["git"].get("FileCount", 0),
            "branch": ctx["git"].get("Branch", "?"),
        }
        self.db.insert_audit_log("MODEL",
            f"Project: {ctx['model']['project_type']}, "
            f"{len(lang_list)} language(s)", cn)

    def _phase_audit(self, cn: int, ctx: dict) -> None:
        code_audit = self.analyzer.analyze()
        ctx["code_audit"] = code_audit
        self.db.insert_audit_log("AUDIT",
            f"Analyzed {code_audit.files_analyzed} files, "
            f"{code_audit.total_lines} lines, "
            f"{len(code_audit.findings)} issues, "
            f"quality={code_audit.quality_score}", cn)

    def _phase_adversarial(self, cn: int, ctx: dict) -> None:
        # Try domain orchestrator first (40 domains), fall back to legacy 12 roles
        try:
            adv_results = self.domain_orch.run_all_legacy()
            self._log.info("DomainAudit", domains=len(adv_results))
        except Exception:
            adv_results = self.adversarial.run_all(self.repo_root)
        # Filter out metadata keys from domain auditor results
        ctx["adversarial"] = {k: v for k, v in adv_results.items()
                              if not k.startswith("_")}
        adv_filtered = ctx["adversarial"]  # already filtered by _ prefix
        total_adv = sum(len(v) for v in adv_filtered.values())
        roles_summary = ", ".join(f"{k}={len(v)}" for k, v in adv_filtered.items())
        self.db.insert_audit_log("ADVERSARIAL",
            f"{len(adv_results)} roles: {total_adv} findings ({roles_summary})", cn)

    def _phase_correlate(self, cn: int, ctx: dict) -> None:
        """Correlate primary + adversarial findings, deduplicate.

        Computes:
          - Primary raw record count
          - Adversarial raw record count
          - Intra-source duplicates (within primary, within adversarial)
          - Cross-source overlap (same finding found by both)
          - Total unique findings after deduplication

        Invariant: combined_raw - intra_dupes - cross_overlap = unique
        """
        primary = ctx.get("code_audit")
        adv = ctx.get("adversarial", {})

        primary_count = len(primary.findings) if primary else 0
        adv_count = sum(len(v) for v in adv.values())

        # ── CROSS-RULE NORMALIZATION ───────────────────────────────────────
        # Some domains flag the same vulnerability as the primary analyzer
        # with a different rule name (e.g. PY-EVAL vs INJ-EVAL on same eval()).
        # These must be deduplicated at the file:line level using a canonical key.
        #
        # Map domain rule → set of equivalent primary rules
        _DOMAIN_TO_PRIMARY: dict[str, set[str]] = {
            "INJ-EVAL": {"PY-EVAL", "TS-EVAL", "PHP-EVAL", "RB-EVAL",
                         "GO-OS-EXEC", "RS-UNSAFE"},
            "INJ-CMD-OS": {"PY-OS-SYSTEM", "PY-OS-POPEN", "PY-SHELL-TRUE"},
            "INJ-CMD-SUB": {"PY-SHELL-STR"},
            "INJ-DOM-XSS": {"TS-DOM-XSS", "PHP-DOM-XSS", "TS-REACT-XSS"},
            "INJ-SQL-INTERP": {"PY-FSTRING-SQL", "PY-CURSOR-FSTRING",
                               "PY-SQL-VAR-CONCAT", "PHP-SQL-STRING",
                               "PHP-SQLI-INTERP"},
            "INJ-PATH-TRAV": {"PY-CONCAT-PATH", "PHP-LFI-FUNC",
                              "PHP-LFI-ONCE"},
        }

        # Reverse: primary rule → set of domain rules that overlap
        _PRIMARY_TO_DOMAIN: dict[str, set[str]] = {}
        for dom_rule, prim_rules in _DOMAIN_TO_PRIMARY.items():
            for pr in prim_rules:
                _PRIMARY_TO_DOMAIN.setdefault(pr, set()).add(dom_rule)

        # Build map: file:line → canonical rule for normalization
        # A primary finding at file:line serves as the canonical
        canonical_map: dict[str, str] = {}  # file:line → canonical_key
        if primary:
            for f in primary.findings:
                loc = f"{f.file}:{f.line}"
                domain_overlaps = _PRIMARY_TO_DOMAIN.get(f.rule, set())
                common_key = f"{loc}:{f.rule}"  # primary key is canonical
                canonical_map[loc] = common_key

        def _norm_key(f: Any) -> str:
            """Normalize key: if a domain rule overlaps with a primary rule at same
            file:line, use the primary rule's key for dedup."""
            loc = f"{f.file}:{f.line}"
            # Check if there's a canonical primary at this location
            if loc in canonical_map:
                dom_rule = f.rule
                # Is this a domain rule that overlaps with the primary?
                for dom_set in _DOMAIN_TO_PRIMARY.values():
                    if dom_rule in dom_set or dom_rule in _DOMAIN_TO_PRIMARY:
                        return canonical_map[loc]
                # If this IS a primary rule, keep its own key
                if dom_rule in _PRIMARY_TO_DOMAIN:
                    return canonical_map.get(loc, f"{f.file}:{f.line}:{f.rule}")
            return f"{f.file}:{f.line}:{f.rule}"

        # Build key sets for each source to detect duplicates
        primary_keys: set[str] = set()
        primary_dupe_keys: set[str] = set()
        if primary:
            for f in primary.findings:
                key = _norm_key(f)
                if key in primary_keys:
                    primary_dupe_keys.add(key)
                else:
                    primary_keys.add(key)

        adv_keys_all: list[str] = []
        adv_dupe_keys: set[str] = set()
        adv_unique_keys: set[str] = set()
        for findings in adv.values():
            for af in findings:
                key = _norm_key(af)
                adv_keys_all.append(key)
                if key in adv_unique_keys:
                    adv_dupe_keys.add(key)
                else:
                    adv_unique_keys.add(key)

        # Intra-source duplicates
        intra_primary_dupes = len(primary_dupe_keys)
        intra_adv_dupes = len(adv_keys_all) - len(adv_unique_keys)

        # Cross-source overlap: same key in both primary and adversarial
        cross_overlap = len(primary_keys & adv_unique_keys)

        # Build combined list for global deduplication
        all_findings = list(primary.findings) if primary else []
        for role_name, findings in adv.items():
            for af in findings:
                all_findings.append(CodeIssueBridge(af))

        # Global deduplication
        seen: set[str] = set()
        deduped = []
        for f in all_findings:
            key = _norm_key(f)
            if key not in seen:
                seen.add(key)
                deduped.append(f)

        total_raw = len(all_findings)
        total_unique = len(deduped)
        total_duplicates = total_raw - total_unique
        intra_total = intra_primary_dupes + intra_adv_dupes

        ctx["correlated"] = deduped
        ctx["correlation_stats"] = {
            "primary_raw": primary_count,
            "adversarial_raw": adv_count,
            "combined_raw": total_raw,
            "intra_primary_dupes": intra_primary_dupes,
            "intra_adversarial_dupes": intra_adv_dupes,
            "intra_total_dupes": intra_total,
            "cross_source_overlap": cross_overlap,
            "total_duplicates_removed": total_duplicates,
            "total_unique": total_unique,
        }

        # Ancillary metadata findings (git, language, test coverage)
        # Tracked separately — not subject to deduplication
        ancillary = []
        gi = ctx.get("git", {})
        if gi.get("GitError"):
            ancillary.append(AncillaryFinding(
                "P2","OPS","GIT-ERROR",
                f"Git operations failed: {gi.get('Error','')}",
                "Install git"))
        rs = gi.get("Status","") or ""
        if rs.strip():
            na = [l for l in rs.splitlines() if ".aura" not in l]
            if na:
                ancillary.append(AncillaryFinding(
                    "P4","OPS","GIT-DIRTY",
                    f"Working tree: {len(na)} uncommitted changes",
                    "Commit or stash"))
        ll = sorted(ctx.get("languages",{}).items(), key=lambda x: -x[1])
        ls = ", ".join(f"{e}({c})" for e,c in ll[:6]) if ll else "none"
        ancillary.append(AncillaryFinding(
            "P5","INFO","LANG-INFO",
            f"Language: {ls} ({gi.get('FileCount',0)} files)",
            "Informational"))
        from .analyzer import LANG_EXTS as LE
        _sd = [d for d in [self.repo_root/"src", self.repo_root/"app",
                           self.repo_root/"lib", self.repo_root/"includes",
                           self.repo_root/"modules"] if d.is_dir()]
        _td = [d for d in [self.repo_root/"tests", self.repo_root/"test"] if d.is_dir()]
        tf = sum(1 for d in _td + _sd
                 for f in d.rglob("*") if f.is_file()
                 and (".test." in f.name or ".spec." in f.name
                      or f.name.startswith("test_") or f.name.endswith("_test.py")
                      or "Test.php" in f.name) and f.suffix in LE)
        sf = sum(1 for d in _sd
                 for f in d.rglob("*") if f.is_file() and f.suffix in LE
                 and ".test." not in f.name and ".spec." not in f.name
                 and not f.name.startswith("test_") and not f.name.endswith("_test.py")
                 and "Test.php" not in f.name)
        # NOTE: Test coverage is computed in _to_finding_dicts, not re-added here.
        # This prevents double-counting in lineage (36+4=41 bug).
        ctx["ancillary_findings"] = ancillary
        ctx["correlation_stats"]["ancillary_count"] = len(ancillary)

        # ── EXECUTION CONTEXT FILTERING ────────────────────────────────
        # Suppress findings in docs/tests/migrations/generated code
        # unless they are P0 severity
        context_suppressed = 0
        filtered_findings = []
        for f in deduped:
            file_path = getattr(f, 'file', '') or getattr(f, 'file_path', '')
            should_suppress, reason = self.context.should_suppress_finding(
                file_path, getattr(f, 'rule', ''), getattr(f, 'severity', 'P5'))
            if should_suppress:
                context_suppressed += 1
            else:
                filtered_findings.append(f)
        if context_suppressed > 0:
            self._log.info("ContextSuppress", suppressed=context_suppressed,
                           remaining=len(filtered_findings))
        deduped = filtered_findings
        ctx["correlated"] = deduped  # update ctx with filtered list
        ctx["correlation_stats"]["context_suppressed"] = context_suppressed

        # Build traceable lineage string
        lineage = (
            f"Primary: {primary_count} + Adversarial: {adv_count} = {total_raw} combined\n"
            f"  Intra-dupes: primary={intra_primary_dupes} + adversarial={intra_adv_dupes} = {intra_total}\n"
            f"  Cross-overlap: {cross_overlap}\n"
            f"  Total removed: {total_duplicates} → {total_unique} unique"
        )
        self.db.insert_audit_log("CORRELATE", lineage, cn)

        # ── SEMANTIC INTELLIGENCE ──────────────────────────────────────
        # Run semantic enrichment on all correlated findings
        try:
            raw_dicts = [{
                            "finding_id": Engine._stable_finding_id(f.file, f.line, f.rule),
                            "file": f.file,
                            "line": f.line,
                            "rule": f.rule,
                            "severity": f.severity,
                            "category": f.category,
                "message": f.message,
            } for i, f in enumerate(deduped)]
            enriched = self.semantic.enrich_findings(raw_dicts)
            ctx["semantic_enriched"] = enriched
            ctx["semantic_summary"] = self.semantic.classification_summary(enriched)
            self._log.info("Semantic", enriched_count=len(enriched))
        except Exception as e:
            self._log.warning("Semantic analysis failed", error=str(e))
            ctx["semantic_enriched"] = []

    def _phase_prioritize(self, cn: int, ctx: dict) -> None:
        correlated = ctx.get("correlated", [])
        # Sort: severity (P0 first), then category
        sev_order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3, "P4": 4, "P5": 5}
        ctx["prioritized"] = sorted(correlated,
            key=lambda f: (sev_order.get(f.severity, 9), f.category))
        ctx["findings_list"] = self._to_finding_dicts(cn, ctx)
        self.db.insert_audit_log("PRIORITIZE",
            f"{len(ctx['prioritized'])} findings prioritized", cn)

    def _phase_remediate(self, cn: int, ctx: dict) -> None:
            """Log remediation plan — actual fixes are applied externally."""
            findings = ctx.get("findings_list", [])
            ancillary = ctx.get("ancillary_findings", [])
            # Insert all findings (correlated + ancillary)
            for f in findings:
                self.db.insert_finding(f)
            # Insert ancillary findings with IDs stable across cycles
            for i, af in enumerate(ancillary):
                anc_id = Engine._stable_finding_id(
                    af.rule or "ancillary", 0, af.rule or "ancillary", prefix="A")
                self.db.insert_finding({
                    "finding_id": anc_id,
                    "cycle_number": cn,
                    "severity": af.severity,
                    "category": af.category,
                    "status": "OPEN",
                    "problem": f"[{af.rule}] {af.message}",
                    "remediation": af.evidence,
                    "file_path": "",
                    "line_number": 0,
                })
            total = len(findings) + len(ancillary)
            ctx["total_findings_count"] = total
            self.db.insert_audit_log("REMEDIATE",
                f"{total} findings logged ({len(findings)} code + {len(ancillary)} ancillary)", cn)

    def _phase_test(self, cn: int, ctx: dict) -> None:
        results = self._run_tooling(cn)
        ctx["tooling_results"] = results
        passed = sum(1 for r in results if r.get("success"))
        self.db.insert_audit_log("TEST",
            f"{passed}/{len(results)} tooling commands passed", cn)

    def _phase_verify(self, cn: int, ctx: dict) -> None:
        """Record per-finding verification status. Tooling passing globally
        does NOT auto-verify individual findings — each finding requires
        its own independent evidence from the remediation loop or re-audit."""
        findings = ctx.get("findings_list", [])
        tooling = ctx.get("tooling_results", [])
        tooling_passed = all(r.get("success") for r in tooling) if tooling else True

        # Track which findings have been independently verified
        # (from remediation loop with explicit tool output)
        verified_count = ctx.get("remediation_verified_count", 0)

        # P0-P2 findings are NOT auto-verified just because tooling passed globally.
        # Verification requires: patch applied → tooling exit code captured → re-audit confirms absence.
        # The remediation loop handles this — not the VERIFY phase.

        ctx["verified_count"] = verified_count
        self.db.insert_audit_log("VERIFY",
            f"Tooling: {'PASS' if tooling_passed else 'FAIL'}. "
            f"{verified_count}/{len(findings)} findings have independent verification evidence "
            f"(from remediation loop)", cn)

    def _phase_regression(self, cn: int, ctx: dict) -> None:
        """Check for regressions — findings from previous cycles that reappeared."""
        prev_findings = []
        if cn > 1:
            for pc in range(1, cn):
                pf = self.db.get_findings(cycle_number=pc)
                prev_findings.extend(pf)

        # R2-02: regression = a previously-RESOLVED (VERIFIED/FIXED) finding that
        # reappears in the current cycle — at ANY severity. The old code filtered
        # current findings to P0-P2, so a finding that regressed but was
        # re-classified to P3 became invisible to the intersection (false pass).
        prev_ids = {f.get("finding_id") for f in prev_findings
                     if f.get("status") in ("VERIFIED", "FIXED")}

        current_ids = {f.get("finding_id") for f in ctx.get("findings_list", [])}

        regressions = current_ids & prev_ids
        ctx["regressions"] = list(regressions)
        self.db.insert_audit_log("REGRESSION",
            f"{len(regressions)} regressions detected" if regressions else
            "No regressions detected", cn)

    def _phase_update_state(self, cn: int, ctx: dict) -> None:
        """Update engine state with cycle results."""
        code_audit = ctx.get("code_audit")
        findings = ctx.get("findings_list", [])
        tooling = ctx.get("tooling_results", [])

        # Compute severity counts
        sev_counts: dict[str, int] = {}
        for f in findings:
            sev_counts[f.get("severity", "?")] = sev_counts.get(f.get("severity", "?"), 0) + 1

        state_update = {
            "findings_total": len(findings),
            "findings_by_severity": sev_counts,
            "code_quality": code_audit.quality_score if code_audit else 0,
            "files_analyzed": code_audit.files_analyzed if code_audit else 0,
            "tooling_passed": sum(1 for r in tooling if r.get("success")),
            "tooling_total": len(tooling),
            "regressions": len(ctx.get("regressions", [])),
        }
        ctx["state_update"] = state_update
        self.db.insert_audit_log("UPDATE_STATE",
            f"State updated: {len(findings)} findings, "
            f"quality={state_update['code_quality']}", cn)

    def _validate_limitations_file(self) -> tuple[bool, str]:
        """Validate LIMITATIONS.md has meaningful content.

        Returns (pass, reason). A trivially passing file (empty, placeholder, or
        lacking structured sections) is treated as a gate FAILURE.

        Checks performed:
          1. File must exist
          2. File must be >= 50 characters (not empty/token)
          3. File must not contain ONLY placeholder text ("placeholder", "TBD",
             "TODO", "N/A", "none")
          4. File must contain at least one structured section header (## ...)
             with at least one bullet-point limitation description following it
        """
        limitations_path = self.repo_root / "LIMITATIONS.md"

        # Check 1: Existence
        if not limitations_path.exists():
            return False, "LIMITATIONS.md is missing"

        # Check 2: Non-trivial content length
        try:
            content = limitations_path.read_text(encoding="utf-8").strip()
        except Exception:
            return False, "LIMITATIONS.md exists but could not be read"

        if len(content) < 50:
            return False, (
                f"LIMITATIONS.md is too short ({len(content)} chars, minimum 50). "
                f"File appears empty or token."
            )

        # Check 3: No placeholder-only content
        content_lower = content.lower()
        placeholder_patterns = [
            r"^\s*placeholder\s*$",
            r"^\s*tbd\s*$",
            r"^\s*todo\s*$",
            r"^\s*n/?a\s*$",
            r"^\s*none\s*$",
        ]
        import re as _re
        for pattern in placeholder_patterns:
            if _re.match(pattern, content_lower):
                return False, (
                    f"LIMITATIONS.md contains only placeholder text "
                    f"(\"{content[:30].strip()}...\"). "
                    f"Must document real limitations."
                )

        # Also check multi-line: if every non-empty line is just a placeholder word
        lines = [line.strip().rstrip(".,;:") for line in content.splitlines()
                 if line.strip()]
        placeholder_words = {"placeholder", "tbd", "todo", "n/a", "none", "wip"}
        if lines and all(
            word.lower() in placeholder_words for word in lines
        ):
            return False, (
                f"LIMITATIONS.md contains only placeholder lines "
                f"({', '.join(lines[:3])}...). "
                f"Must document real limitations."
            )

        # Check 4: At least one structured section with a limitation description
        # A section is a line starting with "## " followed by at least one
        # bullet point ("- " or "* ") or numbered item within that section
        sections = _re.split(r"^##\s+", content, flags=_re.MULTILINE)
        # First split element is text before any ## section, ignore it
        sections = sections[1:] if len(sections) > 1 else []

        if not sections:
            return False, (
                "LIMITATIONS.md has no structured sections (## Section Name). "
                "Each limitation must be under a ## heading."
            )

        valid_sections = 0
        for section in sections:
            section = section.strip()
            bullet_lines = [
                line.strip() for line in section.splitlines()
                if line.strip().startswith(("- ", "* ", "+ ", "1.", "2.", "3."))
            ]
            if bullet_lines:
                valid_sections += 1

        if valid_sections == 0:
            return False, (
                "LIMITATIONS.md has section headers but no bullet-point "
                "limitation descriptions under any section. Each section "
                "must list specific limitations as bullet points (- item)."
            )

        return True, (
            f"LIMITATIONS.md validated: {valid_sections} structured "
            f"section(s) with limitation descriptions."
        )

    def _phase_convergence(self, cn: int, ctx: dict) -> None:
        """Evaluate all 12 convergence gates."""
        code_audit = ctx.get("code_audit")
        tooling = ctx.get("tooling_results", [])
        findings = ctx.get("findings_list", [])

        prev_cycle = self.db.get_cycle(cn - 1) if cn > 1 else None
        prev_findings = (self.db.get_findings(cycle_number=cn - 1)
                        if prev_cycle else None)
        latest_conv = self.db.get_convergence(cn - 1) if cn > 1 else {"consecutive_converged_cycles": 0, "audits_since_last_finding": 0}
        consecutive = latest_conv["consecutive_converged_cycles"] if latest_conv else 0
        audits_sf = latest_conv["audits_since_last_finding"] if latest_conv else 0
        tooling_passed = all(r.get("success") for r in tooling) if tooling else True

        limitations_documented, limitations_reason = self._validate_limitations_file()
        if not limitations_documented:
            self.db.insert_audit_log("CONVERGENCE",
                f"limitations_documented gate FAIL: {limitations_reason}", cn)

        # Filter out semantically mitigated findings before gate evaluation
        enriched = ctx.get("semantic_enriched", [])
        mitigated_ids = set()
        if enriched:
            for ef in enriched:
                if ef.confidence_level.name in ("MITIGATED", "FALSE_POSITIVE"):
                    mitigated_ids.add(ef.finding_id)
        active_findings = [f for f in findings
                                   if f.get("finding_id") not in mitigated_ids]

        # Inject rule key into each finding for subclass evaluation
        for f in active_findings:
            if "rule" not in f:
                problem = f.get("problem", "")
                m = re.search(r"\[([A-Z][A-Z0-9_-]+(?:-[A-Z0-9_-]+)*)\]", problem)
                f["rule"] = m.group(1) if m else ""

        gates = evaluate_all_gates(
                    findings=active_findings, cycle_number=cn,
                    consecutive_converged=consecutive,
                    audits_since_finding=audits_sf,
                    previous_findings=prev_findings,
                    module_integrity_pass=self._module_integrity,
                    limitations_documented=limitations_documented,
                    regression_pass=len(ctx.get("regressions", [])) == 0,
                )
        if not tooling_passed:
            gates["verification"] = False

        for gn, pv in gates.items():
            self.db.upsert_gate(cn, gn, pv, "")

        severity_weights = {k: v.weight for k, v in self.config.severity.items()}
        score = compute_convergence_score(active_findings, severity_weights, gates)
        code_quality = code_audit.quality_score if code_audit else 100
        if enriched:
            score = self.semantic.compute_enriched_score(enriched, score)
            code_quality += 5
        blended = min(100, int(score * 0.6 + code_quality * 0.4))

        # ── SUBCLASS-AWARE GATE EVALUATION ─────────────────────────────
        # Some findings are advisories, not defects. Re-evaluate gates.
        subtype_counts = get_finding_subtype_counts(active_findings)
        actual_p2_defects = [f for f in active_findings
                             if f.get("severity") == "P2"
                             and f.get("status") in ("OPEN", "IN_PROGRESS")
                             and is_blocking_for_gate(f.get("rule", ""), "P2_zero")]
        actual_security_defects = [f for f in active_findings
                                   if f.get("severity") in ("P0", "P1", "P2")
                                   and f.get("category") == "SECURITY"
                                   and f.get("status") in ("OPEN", "IN_PROGRESS")
                           and is_blocking_for_gate(f.get("rule", ""), "critical_security")]

        # Override P2_zero: only CODE_DEFECT findings count
        gates["P2_zero"] = len(actual_p2_defects) == 0

        # Override critical_security: only CODE_DEFECT SECURITY findings count
        gates["critical_security"] = len(actual_security_defects) == 0

        # Re-evaluate gates in DB
        for gn, pv in gates.items():
            self.db.upsert_gate(cn, gn, pv, f"subclass={subtype_counts}")

        open_p0 = len([f for f in active_findings if f.get("severity") == "P0" and f.get("status") in ("OPEN", "IN_PROGRESS")
                       and is_blocking_for_gate(f.get("rule", ""), "P0_zero")])
        open_p1 = len([f for f in active_findings if f.get("severity") == "P1" and f.get("status") in ("OPEN", "IN_PROGRESS")
                       and is_blocking_for_gate(f.get("rule", ""), "P1_zero")])

        all_pass = all(gates.values())
        if all_pass:
            classification, converged = "PRODUCTION_READY", True
            reason = "All 12 convergence gates pass."
        elif open_p0 == 0 and open_p1 == 0:
            classification, converged = "CONDITIONALLY_READY", False
            reason = f"Non-blocking findings remain. Score: {blended}/100."
        else:
            classification, converged = "NOT_READY", False
            failing = [g for g, v in gates.items() if not v]
            reason = f"Blocking gates: {', '.join(failing)}. Score: {blended}/100."

        self.db.upsert_convergence(
            cycle_number=cn, converged=int(converged),
            classification=classification, overall_score=blended,
            reason=reason,
            consecutive_converged_cycles=consecutive + (1 if (converged or classification == "CONDITIONALLY_READY") else 0),
            audits_since_last_finding=audits_sf + 1,
        )

        ctx["convergence"] = {
            "converged": converged, "classification": classification,
            "overall_score": blended, "gates": gates, "reason": reason,
        }
        self.db.insert_audit_log("CONVERGENCE",
            f"Classification: {classification} (score: {blended}, "
            f"{sum(1 for v in gates.values() if v)}/12 gates)", cn)

        # R2-08: record a tamper-evident evidence entry for this cycle's
        # convergence decision into the hash-linked chain, and mirror it to
        # the evidence_chain SQL table so the schema is live end-to-end.
        try:
            ev = Evidence(
                finding_id=f"cycle-{cn}",
                level=EvidenceLevel.CONVERGED if converged else EvidenceLevel.ASSERTED,
                source="convergence-judge",
                tool="engine",
                exit_code=0,
                output=f"classification={classification} score={blended} "
                       f"gates={sum(1 for v in gates.values() if v)}/12",
            )
            ev_hash = self.evidence_chain.append(ev)
            self.db.insert_evidence_entry(
                evidence_id=ev.hash, content_hash=ev_hash,
                chain_index=ev.chain_index, previous_hash=ev.previous_hash,
                payload=json.dumps(ev.to_dict(), default=str)[:4000],
            )
        except Exception as _e:
            self._log.warning("Evidence chain append failed", error=str(_e))

    def _phase_push_approval(self, cn: int, ctx: dict) -> None:
        """Prepare push approval data. Actual push requires explicit -Approve."""
        conv = ctx.get("convergence", {})
        # Store semantic memory for next cycle
        try:
            if ctx.get("semantic_enriched"):
                self.semantic.store_cycle_memory()
        except Exception:
            pass
        if conv.get("converged"):
            self.db.insert_audit_log("PUSH_APPROVAL",
                "Converged — ready for push approval", cn)
        else:
            self.db.insert_audit_log("PUSH_APPROVAL",
                f"Not converged — {conv.get('classification')}", cn)

    # ── Completion ──────────────────────────────────────────────────────

    def _complete_cycle(self, cn: int, ctx: dict) -> dict[str, Any]:
        conv = ctx.get("convergence", {})
        state = ctx.get("state_update", {})
        code_audit = ctx.get("code_audit")
        tooling = ctx.get("tooling_results", [])

        self.db.update_cycle(cn, phase="COMPLETE",
            status="COMPLETED" if conv.get("converged") else "RUNNING",
            classification=conv.get("classification", "NOT_READY"),
            overall_score=conv.get("overall_score", 0),
            completed_at=datetime.now(UTC).isoformat())

        passed = sum(1 for r in tooling if r.get("success"))
        self.db.insert_audit_log("CYCLE_COMPLETE",
            f"Cycle {cn}: {conv.get('classification')} "
            f"(score: {conv.get('overall_score', 0)}, "
            f"quality={code_audit.quality_score if code_audit else '?'}, "
            f"tooling={passed}/{len(tooling)})", cn)

        result = {
            "cycle_number": cn,
            "converged": conv.get("converged", False),
            "classification": conv.get("classification", "?"),
            "overall_score": conv.get("overall_score", 0),
            "gates": conv.get("gates", {}),
            "reason": conv.get("reason", "?"),
            "code_quality": code_audit.quality_score if code_audit else 0,
            "files_analyzed": code_audit.files_analyzed if code_audit else 0,
            "total_lines": code_audit.total_lines if code_audit else 0,
            "code_issues": len(code_audit.findings) if code_audit else 0,
            "findings_count": ctx.get("total_findings_count", len(ctx.get("findings_list", []))),
            "adversarial_count": sum(len(v) for v in ctx.get("adversarial", {}).values()),
            "correlated_count": len(ctx.get("correlated", [])),
            "tooling_passed": f"{passed}/{len(tooling)}" if tooling else "0/0",
            "verified_count": ctx.get("verified_count", 0),
            "regressions": len(ctx.get("regressions", [])),
        }
        # Add severity counts for CLI display (use semantically filtered)
        enriched = ctx.get("semantic_enriched", [])
        mitigated_ids = set()
        if enriched:
            for ef in enriched:
                if ef.confidence_level.name in ("MITIGATED", "FALSE_POSITIVE"):
                    mitigated_ids.add(ef.finding_id)
        findings_list = ctx.get("findings_list", [])
        for sev in ("P0", "P1", "P2", "P3", "P4", "P5"):
            result[f"open_{sev.lower()}"] = len([f for f in findings_list
                if f.get("severity") == sev and f.get("status") in ("OPEN", "IN_PROGRESS")
                and f.get("finding_id") not in mitigated_ids])
        self._log.info("Audit complete", **{k: v for k, v in result.items()
                        if isinstance(v, (str, int, float, bool))})
        return result

    # ── Git & Language ──────────────────────────────────────────────────

    def _get_git_context(self) -> dict[str, Any]:
        ctx: dict = {"GitError": False}
        try:
            subprocess.run(["git", "--version"], capture_output=True, check=True)
        except Exception:
            ctx["Error"] = "git not found"; ctx["GitError"] = True; return ctx

        def _git(args):
            try:
                r = subprocess.run(["git"] + args, capture_output=True, text=True,
                                   cwd=str(self.repo_root), timeout=30)
                if r.returncode != 0: ctx["GitError"] = True; return ""
                return r.stdout.strip()
            except Exception: ctx["GitError"] = True; return ""

        ctx.update(Branch=_git(["branch", "--show-current"]),
                   RecentCommits=_git(["log", "--oneline", "-5"]),
                   Status=_git(["status", "--short"]),
                   LastCommitHash=_git(["log", "-1", "--format=%H"]),
                   LastCommitMsg=_git(["log", "-1", "--format=%s"]))
        try:
            r = subprocess.run(["git", "ls-files"], capture_output=True, text=True,
                               cwd=str(self.repo_root), timeout=30)
            ctx["FileCount"] = len([l for l in r.stdout.splitlines() if l.strip()]) if r.returncode == 0 else 0
        except Exception: ctx["FileCount"] = 0
        return ctx

    def _detect_languages(self) -> dict[str, int]:
        lang: dict = {}
        # Reuse git ls-files via subprocess (called once per cycle from _phase_discover)
        try:
            r = subprocess.run(["git", "ls-files"], capture_output=True, text=True,
                               cwd=str(self.repo_root), timeout=30)
            if r.returncode == 0:
                for line in r.stdout.splitlines():
                    ext = Path(line).suffix.lower()
                    if ext and ext not in (".md", ".txt", ".lock",
                                           ".gitignore", ".svg", ".png",
                                           ".jpg", ".jpeg", ".gif",
                                           ".ico", ".woff", ".woff2",
                                           ".ttf", ".eot", ".pdf", ".zip",
                                           ".gz", ".tar", ".mp3", ".mp4"):
                        lang[ext] = lang.get(ext, 0) + 1
            else:
                # Fallback: count files directly on disk
                for f in self.repo_root.rglob("*"):
                    if f.is_file() and ".git" not in f.parts and ".aura" not in f.parts:
                        ext = f.suffix.lower()
                        if ext and ext not in (".md", ".txt", ".lock", ".svg", ".png",
                                               ".jpg", ".jpeg", ".gif", ".ico",
                                               ".woff", ".woff2", ".ttf", ".eot", ".pdf"):
                            lang[ext] = lang.get(ext, 0) + 1
        except Exception:
            # Final fallback
            try:
                for f in self.repo_root.rglob("*"):
                    if f.is_file() and ".git" not in f.parts and ".aura" not in f.parts:
                        ext = f.suffix.lower()
                        if ext:
                            lang[ext] = lang.get(ext, 0) + 1
            except Exception:
                pass
        return lang

    def _detect_project_type(self) -> str:
        r = self.repo_root
        # Priority order: check primary ecosystem first
        if (r/"composer.json").exists(): return "PHP (Composer)"
        if (r/"index.php").exists() and not (r/"package.json").exists(): return "PHP"
        if (r/"pyproject.toml").exists() or (r/"setup.py").exists(): return "Python"
        if (r/"go.mod").exists(): return "Go"
        if (r/"Cargo.toml").exists(): return "Rust"
        if (r/"package.json").exists(): return "Node.js/TypeScript"
        if (r/"Gemfile").exists(): return "Ruby"
        if (r/"pom.xml").exists() or (r/"build.gradle").exists(): return "Java/Kotlin"
        if (r/"index.php").exists(): return "PHP"
        if (r/"pubspec.yaml").exists(): return "Dart/Flutter"
        if (r/"mix.exs").exists(): return "Elixir"
        if (r/"stack.yaml").exists() or (r/"*.cabal").exists(): return "Haskell"
        if (r/"CMakeLists.txt").exists(): return "C/C++ (CMake)"
        if (r/"Dockerfile").exists(): return "Docker"
        return "unknown"

    # ── Tooling & SAST ──────────────────────────────────────────────────

    def _run_tooling(self, cn: int) -> list[dict[str, Any]]:
        results = []
        # Merge auto-detected + config-required commands
        commands = self._detect_commands()
        required = self.config.engine.tooling.required_pass_commands if hasattr(self.config, "engine") else []
        for rc in required:
            if rc not in commands:
                commands.append(rc)
        for cmd in commands:
            try:
                kwargs = dict(capture_output=True, text=True, timeout=300)
                if os.name == "nt":
                    r = subprocess.run(["cmd", "/c", cmd], cwd=str(self.repo_root), shell=False, **kwargs)
                else:
                    r = subprocess.run(["sh", "-c", cmd], cwd=str(self.repo_root), **kwargs)
                ok = r.returncode == 0
                self.db.insert_tooling_evidence(cn, cmd, r.returncode, ok, (r.stdout+r.stderr)[:2000])
                results.append({"command": cmd, "exit_code": r.returncode, "success": ok})
            except subprocess.TimeoutExpired:
                self.db.insert_tooling_evidence(cn, cmd, -1, False, "TIMEOUT")
                results.append({"command": cmd, "exit_code": -1, "success": False})
            except Exception as e:
                self.db.insert_tooling_evidence(cn, cmd, -1, False, str(e))
                results.append({"command": cmd, "exit_code": -1, "success": False})
        return results

    def _detect_commands(self) -> list[str]:
        cmds = []
        r = self.repo_root
        # R2-03: real exit codes by default. `|| true` is appended ONLY when
        # the operator explicitly opts into informational (fail-open) tooling
        # via engine.tooling.fail_open=true — never for convergence decisions.
        fail_open = getattr(self.config.engine.tooling, "fail_open", False)
        sfx = " 2>&1 || true" if fail_open else ""
        # SAST tools (auto-detected)
        if shutil.which("semgrep"): cmds.append(f"semgrep scan --config=auto --quiet{sfx}")
        if shutil.which("bandit") and (r/"pyproject.toml").exists(): cmds.append(f"bandit -r src/ -ll{sfx}")
        if shutil.which("gitleaks"): cmds.append(f"gitleaks detect --no-git{sfx}")
        # Language tooling
        if (r/"tsconfig.json").exists(): cmds.append(f"npx tsc --noEmit{sfx}")
        if (r/"pyproject.toml").exists(): cmds.append(f"python -m pytest --tb=short{sfx}")
        if (r/"package.json").exists():
            try:
                pkg = json.loads((r/"package.json").read_text())
                for k in ("test","lint","build"):
                    if pkg.get("scripts",{}).get(k): cmds.append(f"npm run {k}{sfx}")
            except Exception: pass
        if (r/"Makefile").exists(): cmds.append(f"make test{sfx}")
        if (r/"go.mod").exists(): cmds.append(f"go test ./...{sfx}")
        if (r/"Cargo.toml").exists(): cmds.append(f"cargo test{sfx}")
        return cmds

    # ── Finding conversion ──────────────────────────────────────────────

    def _to_finding_dicts(self, cn: int, ctx: dict) -> list[dict[str, Any]]:
        """Convert correlated CodeIssues into DB-ready findings with metadata.

        Does NOT create new findings. All findings originate from CORRELATE.
        """
        from .analyzer import LANG_EXTS as _LE

        findings: list[dict] = []

        # Code issues from audit + adversarial (already deduplicated)
        correlated = ctx.get("correlated", [])
        for issue in correlated:
                findings.append({
                    "finding_id": Engine._stable_finding_id(issue.file, issue.line, issue.rule),
                    "cycle_number": cn,
                    "severity": issue.severity,
                    "category": issue.category,
                    "status": "OPEN",
                    "problem": f"[{issue.rule}] {issue.message}",
                    "remediation": f"Fix {issue.rule} at {issue.file}:{issue.line}",
                    "file_path": issue.file,
                    "line_number": issue.line,
                    "evidence": issue.evidence,
                })

        # Test coverage — scan entire repo (project-aware)
        src_dirs = [d for d in [self.repo_root/"src", self.repo_root/"app",
                                    self.repo_root/"lib", self.repo_root/"includes",
                                    self.repo_root/"modules", self.repo_root/"routes"]
                        if d.is_dir()]
        test_dirs = [d for d in [self.repo_root/"tests", self.repo_root/"test",
                                      self.repo_root/"__tests__", self.repo_root/"spec"]
                         if d.is_dir()]
        src_files = sum(1 for d in src_dirs for f in d.rglob("*")
                            if f.is_file() and f.suffix in _LE
                            and ".test." not in f.name and ".spec." not in f.name
                            and not f.name.startswith("test_") and not f.name.endswith("_test.py")
                            and "Test.php" not in f.name and "TestCase" not in f.name)
        test_files = sum(1 for d in test_dirs + src_dirs for f in d.rglob("*")
                             if f.is_file()
                     and (".test." in f.name or ".spec." in f.name
                          or f.name.startswith("test_") or f.name.endswith("_test.py")
                          or "Test.php" in f.name or "TestCase" in f.name
                          or "Test" in f.parent.name)
                     and f.suffix in _LE)
        if src_files > 0:
                ratio = test_files / max(src_files, 1)
                if test_files == 0:
                    findings.append(_fd("P2", "TESTING",
                        "TEST-NO-TESTS",
                        f"No tests ({src_files} sources, 0 tests)",
                        "Add unit tests", str(src_files)))
                elif ratio < 0.3:
                    findings.append(_fd("P3", "TESTING",
                        "TEST-LOW-COVERAGE",
                        f"Low coverage: {ratio:.0%} ({test_files}t/{src_files}s)",
                        "Increase coverage", f"{test_files}/{src_files}"))
                else:
                    findings.append(_fd("P5", "INFO",
                        "TEST-COVERAGE-OK",
                        f"Coverage: {ratio:.0%} ({test_files}t/{src_files}s)",
                        "Maintain coverage", f"{test_files}/{src_files}"))

        return findings

    # ── Trend ───────────────────────────────────────────────────────────

    def get_trend(self) -> dict | None:
        cycles = []
        for cn in range(1, 100):
            conv = self.db.get_convergence(cn); cyc = self.db.get_cycle(cn)
            if not conv or not cyc: break
            findings = self.db.get_findings(cycle_number=cn)
            cycles.append(dict(cycle=cn, score=conv.get("overall_score",0),
                classification=conv.get("classification","?"),
                findings=len(findings), converged=conv.get("converged",0),
                gates_passed=sum(1 for v in self.db.get_gates(cn).values() if v),
                phase=cyc.get("phase","?")))
        if len(cycles) < 2: return None
        prev_gates = self.db.get_gates(cycles[-2]["cycle"])
        curr_gates = self.db.get_gates(cycles[-1]["cycle"])
        trend = TrendAnalyzer.compute_trend(
            {"overall_score": cycles[-2]["score"], "findings_count": cycles[-2]["findings"],
             "gates": prev_gates},
            {"overall_score": cycles[-1]["score"], "findings_count": cycles[-1]["findings"],
             "gates": curr_gates})
        return dict(current=cycles[-1], previous=cycles[-2], trend=trend, all_cycles=cycles)

    def generate_report(self) -> str:
        self.initialize()
        latest = self.db.get_latest_cycle()
        if not latest: return "# AURA Report\n\nNot initialized.\n"
        cn = latest["cycle_number"]
        conv = self.db.get_convergence(cn) or {}
        findings = self.db.get_findings(cycle_number=cn)
        gates = self.db.get_gates(cn)
        tooling = self.db.get_tooling_evidence(cn)
        log_entries = self.db.get_audit_log(cycle_number=cn)

        lines = [f"# AURA Audit Report — Cycle {cn}", "",
            f"**Generated:** {datetime.now(UTC):%Y-%m-%d %H:%M:%S UTC}",
            f"**Classification:** {conv.get('classification','?')}",
            f"**Score:** {conv.get('overall_score',0)}/100", "",
            "## Gates", "| Gate | Status |", "|---|---|"]
        for gn in ["P0_zero","P1_zero","P2_zero","critical_security",
                    "critical_correctness","data_integrity","regression",
                    "verification","no_material_new_findings",
                    "limitations_documented","consecutive_clean_independent_audits",
                    "module_dependency_integrity"]:
            lines.append(f"| {gn} | {'✅' if gates.get(gn) else '❌'} |")
        lines += ["", "## Findings", "| ID | Sev | Category | Problem |", "|---|---|---|---|"]
        for f in findings:
            lines.append(f"| {f.get('finding_id','?')} | {f.get('severity','?')} | "
                         f"{f.get('category','?')} | {(f.get('problem','') or '')[:60]} |")
        lines += ["", "## Tooling", "| Command | Exit | Result |", "|---|---|---|"]
        for t in tooling:
            lines.append(f"| `{(t.get('command','') or '')[:40]}` | {t.get('exit_code','?')} | "
                         f"{'✅' if t.get('success') else '❌'} |")
        lines += ["", f"*Generated by AURA v3.5 — Semantic Code Intelligence*"]
        return "\n".join(lines)

    def get_status(self) -> dict[str, Any]:
        try: self.db.initialize()
        except Exception: return {"status":"NOT_INITIALIZED"}
        latest = self.db.get_latest_cycle()
        if not latest: return {"status":"NOT_INITIALIZED"}
        findings = self.db.get_findings(cycle_number=latest["cycle_number"])
        open_f = [f for f in findings if f.get("status") in ("OPEN","IN_PROGRESS")]
        gates = self.db.get_gates(latest["cycle_number"])
        # Note: open_p0/p1/p2 may include semantically mitigated; CLI display accounts for this
        return dict(cycle=latest["cycle_number"], phase=latest["phase"],
            status=latest["status"], classification=latest["classification"],
            overall_score=latest["overall_score"], open_findings=len(open_f),
            open_p0=len([f for f in open_f if f.get("severity")=="P0"]),
            open_p1=len([f for f in open_f if f.get("severity")=="P1"]),
            open_p2=len([f for f in open_f if f.get("severity")=="P2"]),
            gates=gates, db_path=str(self.config.database.path))


class AncillaryFinding:
    """Lightweight finding for metadata (git context, language info, etc)."""
    def __init__(self, severity: str, category: str, rule: str,
                 message: str, evidence: str) -> None:
        self.severity = severity
        self.category = category
        self.rule = rule
        self.message = message
        self.evidence = evidence
        self.file = ""
        self.line = 0


class CodeIssueBridge:
    """Bridge AdversarialFinding to CodeIssue interface."""
    def __init__(self, af) -> None:
        self.file = af.file
        self.line = af.line if hasattr(af, 'line') else 0
        self.severity = af.severity
        self.category = af.category
        self.rule = af.rule
        self.message = af.message
        self.evidence = getattr(af, 'evidence', '')


def _fd(sev, cat, rule, problem, remediation, evidence, file_path=None):
    """Generate a finding dict with a stable, content-based ID."""
    key = f"{rule}:{problem}"
    digest = hashlib.sha256(key.encode()).hexdigest()[:12]
    return {
        "finding_id": f"F-{digest}",
        "severity": sev, "category": cat, "rule": rule,
        "status": "OPEN", "problem": problem, "remediation": remediation,
        "evidence": evidence, "file_path": file_path,
    }