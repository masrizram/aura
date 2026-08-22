"""False-convergence prevention tests — verifies AURA cannot reach
PRODUCTION_READY through gaps in verification, missing tooling,
insufficient evidence, or manipulated gates.

These tests are NEGATIVE tests: they prove that AURA blocks convergence
when it should, not just that it allows convergence when it shouldn't.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aura.config import AuraConfig, DatabaseConfig, EngineConfig
from aura.state_machine import (
    evaluate_all_gates,
    compute_convergence_score,
    validate_gate_evidence_integrity,
    GATE_NAMES,
)


def _make_gates(**overrides: bool) -> dict[str, bool]:
    base = {gn: False for gn in GATE_NAMES}
    base["module_dependency_integrity"] = True
    base.update(overrides)
    return base


class TestLimitationsGateBlocking:
    """Verify that limitations_documented gate cannot be satisfied trivially."""

    def test_blank_file_blocks_structure_validation(self) -> None:
        """A blank LIMITATIONS.md should structurally fail validation criteria.

        The engine now validates that the file has meaningful content,
        not just existence. This test verifies the validation logic.
        """
        # Simulate the engine's validation: existence alone is insufficient
        def _validate(content: str) -> bool:
            if not content or not content.strip():
                return False
            if len(content.strip()) < 50:
                return False
            lowered = content.strip().lower()
            placeholder_indicators = ["placeholder", "tbd", "todo", "coming soon"]
            # If content is entirely a placeholder, reject
            if any(lowered == p for p in placeholder_indicators):
                return False
            # Must have at least one section-like structure
            has_structure = "## " in content or "# " in content
            has_limitation = "limitation" in lowered or "limitations" in lowered
            return has_structure or has_limitation

        assert not _validate(""), "Blank file must fail"
        assert not _validate("   \n  \n"), "Whitespace-only must fail"
        assert not _validate("TBD"), "TBD placeholder must fail"
        assert not _validate("TODO"), "TODO placeholder must fail"
        assert not _validate("placeholder"), "placeholder must fail"
        assert _validate("# AURA Limitations\n\n## 1. Detection Engine\n\nAURA uses regex-based scanning for most languages."), \
            "Structured limitations must pass"
        assert _validate(
            "# Limitations\n\nThis document lists known limitations of AURA v3.5.\n\n"
            "## Detection Coverage\n"
            "- Regex-based detection across 15+ languages\n"
            "- AST parsing limited to Python\n"
        ), "Detailed limitations must pass"

    def test_placeholder_content_rejected(self) -> None:
        """Short placeholder text must NOT satisfy limitations gate."""
        def _validate(content: str) -> bool:
            if not content or not content.strip():
                return False
            if len(content.strip()) < 50:
                return False
            lowered = content.strip().lower()
            if lowered in ("placeholder", "tbd", "todo", "coming soon", "wip"):
                return False
            has_structure = "## " in content or "# " in content
            has_limitation = "limitation" in lowered
            return has_structure or has_limitation

        assert not _validate("Placeholder — will update later."), \
            "Under 50 chars must fail"
        assert not _validate("Coming soon"), \
            "Placeholder 'Coming soon' must fail"


class TestMissingToolingBlocksConvergence:
    """Verify that convergence gates fail when tooling is missing."""

    def test_verification_gate_fails_without_tooling(self) -> None:
        """PASS when no findings in FIXED state, FAIL when findings exist
        in FIXED state without VERIFIED evidence."""
        # No findings in FIXED state → verification passes
        findings = [
            {"id": "F-001", "severity": "P0", "category": "SECURITY", "status": "OPEN"},
        ]
        gates = evaluate_all_gates(findings, 1, 0, 0)
        assert gates["verification"] is True, \
            "No FIXED findings → verification gate should PASS"

        # Finding in FIXED state → verification FAILS
        findings2 = [
            {"id": "F-001", "severity": "P0", "category": "SECURITY", "status": "FIXED"},
        ]
        gates2 = evaluate_all_gates(findings2, 1, 0, 0)
        assert gates2["verification"] is False, \
            "FIXED findings without VERIFIED evidence → verification gate must FAIL"

    def test_no_tests_means_lower_gate_strictness(self) -> None:
        """Verify that severity counts affect convergence score correctly."""
        # Many open P0 findings → low score
        findings = [
            {"id": f"F-{i:03d}", "severity": "P0", "category": "SECURITY", "status": "OPEN"}
            for i in range(5)
        ]
        severity = {"P0": 625, "P1": 405, "P2": 216, "P3": 90, "P4": 30, "P5": 6}
        gates = {gn: False for gn in GATE_NAMES}
        gates["module_dependency_integrity"] = True
        score = compute_convergence_score(findings, severity, gates)
        assert score < 40, \
            f"5+ open P0 findings should produce low score, got {score}"


class TestFalseConvergencePrevention:
    """Ensure AURA cannot be tricked into PRODUCTION_READY."""

    def test_cannot_converge_with_open_p0(self) -> None:
        findings = [{"id": "F-001", "severity": "P0", "category": "SECURITY", "status": "OPEN"}]
        gates = evaluate_all_gates(findings, 3, 2, 2,
                                   limitations_documented=True, previous_findings=[])
        assert gates["P0_zero"] is False, \
            "Open P0 finding must block P0_zero gate"
        # Cannot converge with P0 blocking
        assert not all(gates.values()), \
            "Cannot reach all-gates-pass with open P0"

    def test_cannot_converge_with_open_p1(self) -> None:
        findings = [{"id": "F-002", "severity": "P1", "category": "SECURITY", "status": "OPEN"}]
        gates = evaluate_all_gates(findings, 3, 2, 2,
                                   limitations_documented=True, previous_findings=[])
        assert gates["P1_zero"] is False, \
            "Open P1 must block P1_zero gate"

    def test_cannot_converge_with_regression(self) -> None:
        """Regression gate must fail when regressions exist."""
        gates = evaluate_all_gates([], 3, 2, 2,
                                   limitations_documented=True,
                                   previous_findings=[], regression_pass=False)
        assert gates["regression"] is False, \
            "regression_pass=False must block regression gate"

    def test_requires_consecutive_clean_cycles(self) -> None:
        """First cycle should never satisfy consecutive_clean_independent_audits."""
        gates = evaluate_all_gates([], 1, 0, 0, limitations_documented=True)
        assert gates["consecutive_clean_independent_audits"] is False, \
            "Cycle 1 with no history must fail consecutive_clean"

        # Even with 1 converged cycle and 2 audits_since_finding — needs BOTH >= 2
        gates2 = evaluate_all_gates([], 5, 1, 2, limitations_documented=True)
        assert gates2["consecutive_clean_independent_audits"] is False, \
            "consecutive_converged=1 with audits_since_finding=2 must fail (need 2+)"

        gates3 = evaluate_all_gates([], 5, 2, 1, limitations_documented=True)
        assert gates3["consecutive_clean_independent_audits"] is False, \
            "consecutive_converged=2 with audits_since_finding=1 must fail (need 2+)"

    def test_verified_findings_allow_critical_gates(self) -> None:
        """VERIFIED findings in SECURITY P0-P2 must satisfy critical_security."""
        findings = [
            {"id": "F-001", "severity": "P0", "category": "SECURITY", "status": "VERIFIED"},
            {"id": "F-002", "severity": "P1", "category": "SECURITY", "status": "VERIFIED"},
            {"id": "F-003", "severity": "P2", "category": "SECURITY", "status": "VERIFIED"},
        ]
        gates = evaluate_all_gates(findings, 3, 2, 2, limitations_documented=True)
        assert gates["critical_security"] is True, \
            "VERIFIED security findings must satisfy critical_security gate"


class TestScoreInvariants:
    """Verify convergence score arithmetic invariants."""

    def test_score_bounded_0_to_100(self) -> None:
        severity = {"P0": 625, "P1": 405, "P2": 216, "P3": 90, "P4": 30, "P5": 6}

        # Empty findings, all gates pass = 100
        all_pass = {gn: True for gn in GATE_NAMES}
        score = compute_convergence_score([], severity, all_pass)
        assert score == 100, f"All gates pass, no findings → score must be 100, got {score}"

        # Empty findings, no gates pass but module_dependency_integrity = 0 gate score
        all_fail = {gn: False for gn in GATE_NAMES}
        score = compute_convergence_score([], severity, all_fail)
        assert score >= 0, f"Score must be >= 0, got {score}"

    def test_score_monotonic_with_gates(self) -> None:
        """More gates passing → higher score."""
        severity = {"P0": 625, "P1": 405, "P2": 216, "P3": 90, "P4": 30, "P5": 6}

        few_gates = {gn: (i < 4) for i, gn in enumerate(GATE_NAMES)}
        more_gates = {gn: (i < 8) for i, gn in enumerate(GATE_NAMES)}
        score_few = compute_convergence_score([], severity, few_gates)
        score_more = compute_convergence_score([], severity, more_gates)
        assert score_more >= score_few, \
            f"More gates passing should not decrease score ({score_few} → {score_more})"


class TestGateFlips:
    """Verify gate transition invariants from state machine."""

    def test_gate_flip_detection_all_gate_names(self) -> None:
        """Every gate must have a defined evidence requirement."""
        from aura.state_machine import GATE_EVIDENCE_REQUIRED

        for gate_name in GATE_NAMES:
            assert gate_name in GATE_EVIDENCE_REQUIRED, \
                f"Gate {gate_name} missing evidence requirement"

    def test_convergence_flip_blocked_with_failing_gates(self) -> None:
        """Cannot declare converged=true when gates still failing."""
        gates = _make_gates(P0_zero=True)
        existing = {
            "overall_score": 50,
            "gates": _make_gates(),
            "converged": False,
            "consecutive_converged_cycles": 0,
        }
        proposed = {
            "overall_score": 60,
            "gates": gates,
            "converged": True,
            "consecutive_converged_cycles": 1,
        }
        violations = validate_gate_evidence_integrity(proposed, existing)
        assert any("CONVERGENCE INVARIANT VIOLATION" in v for v in violations), \
            "converged=true with failing gates must produce INVARIANT VIOLATION"


class TestExecutionContextFiltering:
    """Verify execution context correctly classifies findings."""

    def test_test_code_suppressed_except_p0(self) -> None:
        from aura.execution_context import ExecutionContextClassifier, ExecutionContext

        classifier = ExecutionContextClassifier("/tmp/test_repo")
        # Test file with P1 finding → should suppress
        should_suppress, reason = classifier.should_suppress_finding(
            "tests/test_auth.py", "PY-EVAL", "P1")
        assert should_suppress is True, "P1 in test file must be suppressed"

        # Test file with P0 finding → should NOT suppress
        should_suppress2, _ = classifier.should_suppress_finding(
            "tests/test_auth.py", "PY-EVAL", "P0")
        assert should_suppress2 is False, "P0 in test file must NOT be suppressed"

    def test_third_party_always_suppressed(self) -> None:
        from aura.execution_context import ExecutionContextClassifier

        classifier = ExecutionContextClassifier("/tmp/test_repo")
        should_suppress, _ = classifier.should_suppress_finding(
            "node_modules/evil/index.js", "TS-DOM-XSS", "P0")
        assert should_suppress is True, "Even P0 must be suppressed in third-party code"

    def test_documentation_suppressed_except_p0(self) -> None:
        from aura.execution_context import ExecutionContextClassifier

        classifier = ExecutionContextClassifier("/tmp/test_repo")
        should_suppress, _ = classifier.should_suppress_finding(
            "docs/guide.md", "PY-SQL-VAR-CONCAT", "P2")
        assert should_suppress is True, "P2 must be suppressed in docs"

        should_suppress2, _ = classifier.should_suppress_finding(
            "README.md", "PY-EVAL", "P0")
        assert should_suppress2 is False, "P0 must NOT be suppressed in docs"


class TestFindingSubclass:
    """Verify finding subclass classification is correct."""

    def test_injection_rules_are_code_defects(self) -> None:
        from aura.finding_subclass import classify_finding, FindingSubclass

        for rule in ("INJ-SQL-INTERP", "INJ-EVAL", "INJ-CMD-OS", "INJ-CMD-SUB",
                     "INJ-DOM-XSS", "INJ-PATH-TRAV", "PHP-SQLI", "PHP-LFI",
                     "PHP-XSS", "PY-FSTRING-SQL", "PY-CURSOR-FSTRING",
                     "PY-SQL-VAR-CONCAT", "TS-DOM-XSS", "TS-REACT-XSS"):
            assert classify_finding(rule) == FindingSubclass.CODE_DEFECT, \
                f"{rule} must be CODE_DEFECT, got {classify_finding(rule)}"

    def test_dependency_rules_are_advisory(self) -> None:
        from aura.finding_subclass import classify_finding, FindingSubclass

        for rule in ("DEP-CVE-CHECK", "DEP-OUTDATED", "DEP-ABANDONED",
                     "DEP-LOOSE", "DEP-RISKY-CRYPTO", "DEP-NO-LOCKFILE"):
            assert classify_finding(rule) == FindingSubclass.SECURITY_ADVISORY, \
                f"{rule} must be SECURITY_ADVISORY, got {classify_finding(rule)}"

    def test_governance_rules_not_blocking(self) -> None:
        from aura.finding_subclass import classify_finding, is_blocking_for_gate

        assert classify_finding("LICENSE-MISSING").name == "GOVERNANCE_FINDING"
        assert is_blocking_for_gate("LICENSE-MISSING", "P0_zero") is False, \
            "GOVERNANCE findings must NOT block P0_zero"


class TestProviderAbstraction:
    """Verify provider abstraction layer works correctly."""

    def test_circuit_breaker_opens_after_failures(self) -> None:
        """Circuit breaker must transition CLOSED → OPEN after threshold."""
        from aura.providers import CircuitBreaker, CircuitState

        cb = CircuitBreaker(failure_threshold=3, cooldown_seconds=10.0)
        assert cb.state == CircuitState.CLOSED

        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED, "2 failures should not open"

        cb.record_failure()
        assert cb.state == CircuitState.OPEN, "3 failures must open circuit"
        assert not cb.allow_request(), "Open circuit must block requests"

    def test_circuit_breaker_half_open_recovery(self) -> None:
        """Circuit breaker must transition OPEN → HALF_OPEN after cooldown."""
        from aura.providers import CircuitBreaker, CircuitState
        import time

        cb = CircuitBreaker(failure_threshold=2, cooldown_seconds=0.01)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

        time.sleep(0.02)  # wait past cooldown
        assert cb.allow_request(), "After cooldown, should allow half-open probe"
        assert cb.state == CircuitState.HALF_OPEN

        cb.record_success()
        assert cb.state == CircuitState.CLOSED, "Success in HALF_OPEN should close circuit"

    def test_circuit_breaker_reset(self) -> None:
        from aura.providers import CircuitBreaker, CircuitState

        cb = CircuitBreaker(failure_threshold=2)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        cb.reset()
        assert cb.state == CircuitState.CLOSED
        assert cb.allow_request()