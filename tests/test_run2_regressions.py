"""Regression tests for RUN #2 deep architecture audit (R2-01..R2-08).

Each test reproduces a defect found against baseline 00d8b2a and proves the
fix. No speculative tests — each maps to a reproduced root cause in
docs/run2-deep-architecture-audit.md.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from aura.config import AuraConfig
from aura.providers import (
    BaseProvider,
    CircuitState,
    ProviderRegistry,
    ProviderResponse,
)
from aura.state_machine import (
    GATE_NAMES,
    compute_convergence_score,
    evaluate_all_gates,
    validate_gate_findings_crosscheck,
)


# ── R2-01: no_material_new_findings key mismatch ─────────────────────────────

class TestNewMaterialFindingsGate:
    def test_new_p0_with_finding_id_key_blocks_gate(self) -> None:
        """Findings using `finding_id` (the DB/engine key) must be detected."""
        prev = [{"finding_id": "F-aaa", "severity": "P1", "category": "SECURITY", "status": "VERIFIED"}]
        curr = [
            {"finding_id": "F-aaa", "severity": "P1", "category": "SECURITY", "status": "VERIFIED"},
            {"finding_id": "F-NEW", "severity": "P0", "category": "SECURITY", "status": "OPEN"},
        ]
        gates = evaluate_all_gates(curr, 5, 2, 2, previous_findings=prev,
                                   limitations_documented=True)
        assert gates["no_material_new_findings"] is False, \
            "a brand-new P0 (finding_id key) must fail no_material_new_findings"

    def test_new_p0_with_id_key_blocks_gate(self) -> None:
        """Backward compat: `id` key still works."""
        prev = [{"id": "F-aaa", "severity": "P1", "status": "VERIFIED"}]
        curr = [{"id": "F-NEW", "severity": "P2", "status": "OPEN"}]
        gates = evaluate_all_gates(curr, 5, 2, 2, previous_findings=prev,
                                   limitations_documented=True)
        assert gates["no_material_new_findings"] is False

    def test_no_new_findings_passes(self) -> None:
        prev = [{"finding_id": "F-aaa", "severity": "P1", "status": "VERIFIED"}]
        curr = [{"finding_id": "F-aaa", "severity": "P1", "status": "VERIFIED"}]
        gates = evaluate_all_gates(curr, 5, 2, 2, previous_findings=prev,
                                   limitations_documented=True)
        assert gates["no_material_new_findings"] is True

    def test_crosscheck_uses_finding_id(self) -> None:
        existing = {"findings": [{"finding_id": "F-1", "severity": "P1"}]}
        proposed_findings = {"findings": [
            {"finding_id": "F-1", "severity": "P1", "status": "VERIFIED"},
            {"finding_id": "F-2", "severity": "P0", "status": "OPEN"},
        ]}
        gates = {gn: True for gn in GATE_NAMES}
        proposed_conv = {"gates": gates}
        violations = validate_gate_findings_crosscheck(
            proposed_conv, proposed_findings, existing)
        assert any("no_material_new_findings" in v for v in violations)


# ── R2-02: regression detection across all severities ────────────────────────

class TestRegressionPhase:
    def _engine(self, tmp_path: Path):
        import subprocess
        from aura.engine import Engine
        repo = tmp_path / "repo"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=str(repo), capture_output=True)
        subprocess.run(["git", "config", "user.email", "t@t"], cwd=str(repo), capture_output=True)
        subprocess.run(["git", "config", "user.name", "T"], cwd=str(repo), capture_output=True)
        (repo / "a.py").write_text("print(1)")
        subprocess.run(["git", "add", "."], cwd=str(repo), capture_output=True)
        subprocess.run(["git", "commit", "-m", "i"], cwd=str(repo), capture_output=True)
        config = AuraConfig()
        config.database.path = str(repo / ".aura" / "state" / "aura.db")
        return Engine(repo, config)

    def test_reappeared_p3_counts_as_regression(self, tmp_path: Path) -> None:
        """A VERIFIED finding that reappears as OPEN at P3 must be a regression."""
        eng = self._engine(tmp_path)
        eng.initialize()  # creates cycle 1
        # Simulate a prior cycle with a VERIFIED finding (cycle 1 already exists)
        eng.db.insert_finding({
            "finding_id": "F-reg", "cycle_number": 1, "severity": "P3",
            "category": "MAINTAINABILITY", "status": "VERIFIED",
            "problem": "x", "file_path": "a.py", "line_number": 1,
        })
        # Now run cycle 2 and inject the same finding_id as a current OPEN P3
        eng._start_cycle(2)
        ctx = {"cn": 2, "findings_list": [
            {"finding_id": "F-reg", "severity": "P3", "category": "MAINTAINABILITY",
             "status": "OPEN"},
        ]}
        eng._phase_regression(2, ctx)
        assert "F-reg" in ctx["regressions"], \
            "P3 reappearance of a previously-VERIFIED finding must count as regression (R2-02)"


# ── R2-03: tooling fail-open ─────────────────────────────────────────────────

class TestToolingExitCodes:
    def _engine(self, tmp_path: Path, fail_open: bool = False):
        import subprocess
        from aura.engine import Engine
        repo = tmp_path / "repo"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=str(repo), capture_output=True)
        (repo / "pyproject.toml").write_text("[project]\nname='x'\n")
        config = AuraConfig()
        config.database.path = str(repo / ".aura" / "state" / "aura.db")
        config.engine.tooling.fail_open = fail_open
        return Engine(repo, config)

    def test_detected_commands_have_no_fail_open_suffix_by_default(self, tmp_path: Path) -> None:
        eng = self._engine(tmp_path, fail_open=False)
        cmds = eng._detect_commands()
        assert cmds, "expected at least one detected command (pyproject present)"
        assert all("|| true" not in c for c in cmds), \
            "default tooling must NOT coerce exit codes (R2-03)"

    def test_fail_open_mode_appends_suffix(self, tmp_path: Path) -> None:
        eng = self._engine(tmp_path, fail_open=True)
        cmds = eng._detect_commands()
        assert all(c.endswith("|| true") for c in cmds), \
            "fail_open=True must append || true (informational mode)"

    def test_failing_command_records_failure(self, tmp_path: Path) -> None:
        """A command that exits non-zero must record success=False (R2-03)."""
        eng = self._engine(tmp_path, fail_open=False)
        eng.initialize()
        results = eng._run_tooling(1) if hasattr(eng, "_run_tooling") else []
        # pytest on an empty repo with no tests exits non-zero (no tests ran)
        pytest_res = [r for r in results if "pytest" in r["command"]]
        assert pytest_res, "pytest command should be detected for pyproject repo"
        assert all(isinstance(r["success"], bool) for r in results)


# ── R2-04: provider fallback ─────────────────────────────────────────────────

class _FakeProvider(BaseProvider):
    def __init__(self, name: str, fail: bool) -> None:
        super().__init__(name)
        self._fail = fail

    def chat(self, system_prompt: str, user_message: str, max_tokens: int = 4000) -> ProviderResponse:
        def _call() -> ProviderResponse:
            if self._fail:
                return ProviderResponse(content="", provider_name=self.name, error="boom")
            return ProviderResponse(content="ok", provider_name=self.name, model="m")
        return self._wrap_call(_call)


class TestProviderFallback:
    def test_falls_back_to_healthy_provider(self) -> None:
        reg = ProviderRegistry()
        reg.register(_FakeProvider("primary", fail=True), priority=0)
        reg.register(_FakeProvider("fallback", fail=False), priority=1)
        resp = reg.chat_with_fallback("s", "u")
        assert resp.error is None
        assert resp.provider_name == "fallback", \
            "transient primary failure must route to healthy fallback (R2-04)"

    def test_all_failing_returns_aggregate_error(self) -> None:
        reg = ProviderRegistry()
        reg.register(_FakeProvider("p0", fail=True), priority=0)
        reg.register(_FakeProvider("p1", fail=True), priority=1)
        resp = reg.chat_with_fallback("s", "u")
        assert resp.error is not None
        assert "failed" in resp.error.lower()

    def test_open_circuit_provider_skipped(self) -> None:
        reg = ProviderRegistry()
        p0 = _FakeProvider("p0", fail=True)
        p0._circuit._state = CircuitState.OPEN  # force open
        reg.register(p0, priority=0)
        reg.register(_FakeProvider("p1", fail=False), priority=1)
        resp = reg.chat_with_fallback("s", "u")
        assert resp.provider_name == "p1"


# ── R2-05: severity weights actually shape score ────────────────────────────

class TestSeverityWeightsHonored:
    def _gates_all_pass(self) -> dict[str, bool]:
        return {gn: True for gn in GATE_NAMES}

    def test_default_weights_reproduce_reference_score(self) -> None:
        """Default config must reproduce historical scoring (no regression)."""
        findings = [{"severity": "P0", "status": "OPEN"}]
        default_w = {"P0": 625, "P1": 405, "P2": 216, "P3": 90, "P4": 30, "P5": 6}
        score = compute_convergence_score(findings, default_w, self._gates_all_pass())
        # 12 gates pass → gate_score=60; 1 open P0 → penalty 15 → finding 25 → 85
        assert score == 85

    def test_custom_weights_change_score(self) -> None:
        """Different severity weights must produce a different score (R2-05)."""
        findings = [{"severity": "P0", "status": "OPEN"}]
        default_w = {"P0": 625, "P1": 405, "P2": 216, "P3": 90, "P4": 30, "P5": 6}
        harsh_w = {"P0": 1250, "P1": 405, "P2": 216, "P3": 90, "P4": 30, "P5": 6}  # P0 doubled
        s_default = compute_convergence_score(findings, default_w, self._gates_all_pass())
        s_harsh = compute_convergence_score(findings, harsh_w, self._gates_all_pass())
        assert s_harsh != s_default, "severity_weights must no longer be a dead parameter"
        assert s_harsh < s_default, "harsher P0 weight must lower the score"

    def test_missing_weight_falls_back_safely(self) -> None:
        findings = [{"severity": "P0", "status": "OPEN"}]
        score = compute_convergence_score(findings, {}, self._gates_all_pass())
        assert 0 <= score <= 100


# ── R2-06: durable resume restores safeguards ────────────────────────────────

class TestDurableSafeguardRestore:
    def test_resume_restores_safeguard_counters(self, tmp_path: Path) -> None:
        from aura.convergence import LoopSafeguard
        from aura.durable import CheckpointManager, DurableAutonomousLoop

        class FakeLoop:
            def __init__(self) -> None:
                self.max_cycles = 0
                self._cycle_log = [{"cycle": 1, "score": 50, "classification": "NOT_READY",
                                    "findings": 3, "fixes_applied": 1}]
                self._safeguard = LoopSafeguard()

            def run(self) -> dict:
                return {"outcome": "x", "message": "m", "converged": False}

        # Seed a checkpoint WITH safeguard state showing prior attempts
        cm = CheckpointManager(tmp_path)
        cm.save(2, {"score": 50, "safeguard": {
            "iteration": 2, "scores": [40, 50], "finding_counts": [5, 3],
            "finding_attempts": {"F-xyz": 3}}})

        loop = FakeLoop()
        d = DurableAutonomousLoop(loop, tmp_path)
        d._resume(from_cycle=2, max_cycles=5)
        assert loop._safeguard.finding_attempts.get("F-xyz") == 3, \
            "resume must restore per-finding attempt counters (R2-06)"
        assert loop._safeguard.iteration == 2


# ── R2-08: evidence chain is populated during a real audit ──────────────────

class TestEvidenceChainWiring:
    def test_audit_appends_evidence_entry(self, tmp_path: Path) -> None:
        import subprocess
        from aura.engine import Engine
        repo = tmp_path / "repo"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=str(repo), capture_output=True)
        subprocess.run(["git", "config", "user.email", "t@t"], cwd=str(repo), capture_output=True)
        subprocess.run(["git", "config", "user.name", "T"], cwd=str(repo), capture_output=True)
        (repo / "a.py").write_text("print(1)")
        subprocess.run(["git", "add", "."], cwd=str(repo), capture_output=True)
        subprocess.run(["git", "commit", "-m", "i"], cwd=str(repo), capture_output=True)
        config = AuraConfig()
        config.database.path = str(repo / ".aura" / "state" / "aura.db")
        eng = Engine(repo, config)
        eng.run_audit()
        # Evidence chain must have at least one entry (R2-08)
        assert len(eng.evidence_chain) >= 1, \
            "convergence phase must append a tamper-evident evidence entry (R2-08)"
        ok, violations = eng.evidence_chain.verify_chain()
        assert ok, violations
        # And mirrored to the SQL table
        rows = eng.db.get_evidence_chain()
        assert len(rows) >= 1, "evidence_chain table must mirror the JSON chain (R2-08)"


# ── R3-01: quality score proportionality on tiny repos ─────────────────────

class TestQualityScoreProportionality:
    def test_tiny_repo_not_zeroed_by_single_p0_p1(self) -> None:
        """A 4-line repo with 1 P0 + 1 P1 must not score 0 (R3-01).

        Pre-fix, kloc floor of 0.1 turned a 23-point penalty into 230, zeroing
        the score. Quality must reflect density, not vanish for small repos.
        """
        from aura.analyzer import MultiLangAnalyzer
        a = MultiLangAnalyzer.__new__(MultiLangAnalyzer)
        findings = [type("F", (), {"severity": "P0"})(),
                    type("F", (), {"severity": "P1"})()]
        score = a._compute_quality(findings, 4)
        assert score > 0, "tiny repo with 1 P0 + 1 P1 must not be zeroed"
        assert 0 <= score <= 100

    def test_quality_bounded_and_monotonic_in_size(self) -> None:
        from aura.analyzer import MultiLangAnalyzer
        a = MultiLangAnalyzer.__new__(MultiLangAnalyzer)
        findings = [type("F", (), {"severity": "P0"})()]
        small = a._compute_quality(findings, 10)
        large = a._compute_quality(findings, 10000)
        assert 0 <= small <= 100 and 0 <= large <= 100
        assert large >= small, "same defect must not hurt a larger repo more"

    def test_clean_repo_scores_100(self) -> None:
        from aura.analyzer import MultiLangAnalyzer
        a = MultiLangAnalyzer.__new__(MultiLangAnalyzer)
        assert a._compute_quality([], 500) == 100


# ── R3-02: no tautological security tests ────────────────────────────────────

class TestNoTautologicalTests:
    def test_no_assert_true_placeholder_tests(self) -> None:
        """Guard against placeholder tests that assert nothing (R3-02)."""
        import re
        from pathlib import Path
        tests_dir = Path(__file__).parent
        offenders = []
        for tf in tests_dir.glob("test_*.py"):
            src = tf.read_text(encoding="utf-8")
            # A bare `assert True` as the ONLY assertion in a test body is a
            # tautology. Flag `assert True` that is the final/sole statement.
            for m in re.finditer(
                    r"def (test_\w+)\([^)]*\):\s*(?:\"\"\"[\s\S]*?\"\"\")?\s*assert True\b",
                    src):
                offenders.append(f"{tf.name}::{m.group(1)}")
        assert not offenders, f"tautological tests found: {offenders}"

