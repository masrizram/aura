"""Tests for the state machine — finding transitions, classification transitions,
gate evidence integrity, and gate-findings cross-checks."""

from __future__ import annotations

from aura.state_machine import (
    FORBIDDEN_DIRECT_TRANSITIONS,
    GATE_EVIDENCE_REQUIRED,
    GATE_NAMES,
    VALID_CLASSIFICATION_TRANSITIONS,
    VALID_FINDING_TRANSITIONS,
    compute_convergence_score,
    evaluate_all_gates,
    is_forbidden_direct_transition,
    is_valid_classification_transition,
    is_valid_finding_transition,
    validate_finding_state_integrity,
    validate_gate_evidence_integrity,
    validate_gate_findings_crosscheck,
)


def _make_gates(**overrides: bool) -> dict[str, bool]:
    base = {
        "P0_zero": False, "P1_zero": False, "P2_zero": False,
        "critical_security": False, "critical_correctness": False,
        "data_integrity": False, "regression": False, "verification": False,
        "no_material_new_findings": False, "limitations_documented": False,
        "consecutive_clean_independent_audits": False, "module_dependency_integrity": True,
    }
    base.update(overrides)
    return base


# ── Finding Transitions ─────────────────────────────────────────────────────


class TestFindingTransitions:
    def test_open_to_in_progress_valid(self) -> None:
        assert is_valid_finding_transition("OPEN", "IN_PROGRESS") is True

    def test_open_to_deferred_valid(self) -> None:
        assert is_valid_finding_transition("OPEN", "DEFERRED") is True

    def test_open_to_blocked_valid(self) -> None:
        assert is_valid_finding_transition("OPEN", "BLOCKED") is True

    def test_open_to_verified_forbidden(self) -> None:
        result = is_forbidden_direct_transition("OPEN", "VERIFIED")
        assert result is not None
        assert "FIXED" in result["Reason"]

    def test_open_to_verified_not_valid(self) -> None:
        assert is_valid_finding_transition("OPEN", "VERIFIED") is False

    def test_open_to_fixed_forbidden(self) -> None:
        result = is_forbidden_direct_transition("OPEN", "FIXED")
        assert result is not None
        assert "IN_PROGRESS" in result["Reason"]

    def test_open_to_fixed_not_valid(self) -> None:
        assert is_valid_finding_transition("OPEN", "FIXED") is False

    def test_fixed_to_verified_forbidden(self) -> None:
        result = is_forbidden_direct_transition("FIXED", "VERIFIED")
        assert result is not None
        assert "VERIFYING" in result["Reason"]

    def test_verifying_to_closed_forbidden(self) -> None:
        result = is_forbidden_direct_transition("VERIFYING", "CLOSED")
        assert result is not None

    def test_same_status_is_valid(self) -> None:
        for status in VALID_FINDING_TRANSITIONS:
            assert is_valid_finding_transition(status, status) is True

    def test_null_from_returns_true(self) -> None:
        assert is_valid_finding_transition(None, "VERIFIED") is True

    def test_empty_from_returns_true(self) -> None:
        assert is_valid_finding_transition("", "REJECTED") is True

    def test_all_forbidden_blocked(self) -> None:
        for forbidden in FORBIDDEN_DIRECT_TRANSITIONS:
            assert is_forbidden_direct_transition(forbidden["From"], forbidden["To"]) is not None
            assert is_valid_finding_transition(forbidden["From"], forbidden["To"]) is False

    def test_all_declared_valid_work(self) -> None:
        for from_status, allowed in VALID_FINDING_TRANSITIONS.items():
            for to_status in allowed:
                assert is_valid_finding_transition(from_status, to_status) is True, (
                    f"{from_status} -> {to_status} should be valid"
                )

    def test_in_progress_to_fixed_valid(self) -> None:
        assert is_valid_finding_transition("IN_PROGRESS", "FIXED") is True

    def test_fixed_to_verifying_valid(self) -> None:
        assert is_valid_finding_transition("FIXED", "VERIFYING") is True

    def test_verifying_to_verified_valid(self) -> None:
        assert is_valid_finding_transition("VERIFYING", "VERIFIED") is True

    def test_verified_to_open_valid(self) -> None:
        assert is_valid_finding_transition("VERIFIED", "OPEN") is True


# ── Classification Transitions ──────────────────────────────────────────────


class TestClassificationTransitions:
    def test_not_ready_to_conditionally_ready_valid(self) -> None:
        assert is_valid_classification_transition("NOT_READY", "CONDITIONALLY_READY") is True

    def test_not_ready_to_human_blocked_valid(self) -> None:
        assert is_valid_classification_transition("NOT_READY", "HUMAN_BLOCKED") is True

    def test_conditionally_ready_to_production_ready_valid(self) -> None:
        assert is_valid_classification_transition("CONDITIONALLY_READY", "PRODUCTION_READY") is True

    def test_not_ready_to_production_ready_forbidden(self) -> None:
        assert is_valid_classification_transition("NOT_READY", "PRODUCTION_READY") is False

    def test_production_ready_to_conditionally_ready_invalid(self) -> None:
        assert is_valid_classification_transition("PRODUCTION_READY", "CONDITIONALLY_READY") is False

    def test_same_classification_valid(self) -> None:
        for cls in VALID_CLASSIFICATION_TRANSITIONS:
            assert is_valid_classification_transition(cls, cls) is True

    def test_null_from_returns_true(self) -> None:
        assert is_valid_classification_transition(None, "PRODUCTION_READY") is True

    def test_production_ready_to_not_ready_valid(self) -> None:
        assert is_valid_classification_transition("PRODUCTION_READY", "NOT_READY") is True


# ── Finding State Integrity ─────────────────────────────────────────────────


class TestValidateFindingIntegrity:
    def test_rejects_open_to_verified(self) -> None:
        existing = {"findings": [{"id": "F001", "status": "OPEN", "severity": "P0"}]}
        proposed = [{"id": "F001", "status": "VERIFIED", "severity": "P0"}]
        violations = validate_finding_state_integrity(proposed, existing)
        assert len(violations) > 0
        assert any("ILLEGAL TRANSITION" in v for v in violations)

    def test_rejects_open_to_fixed(self) -> None:
        existing = {"findings": [{"id": "F001", "status": "OPEN", "severity": "P1"}]}
        proposed = [{"id": "F001", "status": "FIXED", "severity": "P1"}]
        violations = validate_finding_state_integrity(proposed, existing)
        assert len(violations) > 0
        assert any("ILLEGAL TRANSITION" in v for v in violations)

    def test_rejects_new_finding_not_open(self) -> None:
        existing = {"findings": []}
        proposed = [{"id": "F002", "status": "VERIFIED", "severity": "P2"}]
        violations = validate_finding_state_integrity(proposed, existing)
        assert len(violations) > 0
        assert any("NEW FINDING VIOLATION" in v for v in violations)

    def test_accepts_valid_transition(self) -> None:
        existing = {"findings": [{"id": "F001", "status": "OPEN", "severity": "P0"}]}
        proposed = [{"id": "F001", "status": "IN_PROGRESS", "severity": "P0"}]
        violations = validate_finding_state_integrity(proposed, existing)
        assert len(violations) == 0

    def test_accepts_new_finding_open(self) -> None:
        existing = {"findings": []}
        proposed = [{"id": "F005", "status": "OPEN", "severity": "P4"}]
        violations = validate_finding_state_integrity(proposed, existing)
        assert len(violations) == 0

    def test_accepts_same_status(self) -> None:
        existing = {"findings": [{"id": "F006", "status": "OPEN", "severity": "P0"}]}
        proposed = [{"id": "F006", "status": "OPEN", "severity": "P0"}]
        violations = validate_finding_state_integrity(proposed, existing)
        assert len(violations) == 0

    def test_accepts_verified_to_open_recurrence(self) -> None:
        existing = {"findings": [{"id": "F007", "status": "VERIFIED", "severity": "P2"}]}
        proposed = [{"id": "F007", "status": "OPEN", "severity": "P2"}]
        violations = validate_finding_state_integrity(proposed, existing)
        assert len(violations) == 0

    def test_handles_null_existing(self) -> None:
        proposed = [{"id": "F008", "status": "OPEN", "severity": "P5"}]
        violations = validate_finding_state_integrity(proposed, None)
        assert len(violations) == 0

    def test_handles_empty_proposed(self) -> None:
        existing = {"findings": [{"id": "F009", "status": "OPEN", "severity": "P0"}]}
        violations = validate_finding_state_integrity([], existing)
        assert len(violations) == 0

    def test_mixed_valid_invalid_correct_count(self) -> None:
        existing = {
            "findings": [
                {"id": "F010", "status": "OPEN", "severity": "P0"},
                {"id": "F011", "status": "IN_PROGRESS", "severity": "P1"},
            ]
        }
        proposed = [
            {"id": "F010", "status": "VERIFIED", "severity": "P0"},
            {"id": "F011", "status": "FIXED", "severity": "P1"},
        ]
        violations = validate_finding_state_integrity(proposed, existing)
        assert len(violations) == 1
        assert "F010" in violations[0]


# ── Gate Evidence Integrity ─────────────────────────────────────────────────


class TestValidateGateIntegrity:
    def test_score_decrease_is_not_a_violation(self) -> None:
        """IMP-03: score regression invariant removed.

        A cycle that discovers NEW real findings legitimately lowers the
        score. Flagging that as a violation would reward hiding findings.
        Score changes (up or down) are NOT integrity violations.
        """
        existing = {"overall_score": 55, "gates": _make_gates(), "converged": False, "consecutive_converged_cycles": 0}
        proposed = {"overall_score": 50, "gates": _make_gates(), "converged": False, "consecutive_converged_cycles": 0}
        violations = validate_gate_evidence_integrity(proposed, existing)
        assert not any("SCORE REGRESSION" in v for v in violations)

    def test_score_spike_is_not_a_violation(self) -> None:
        """IMP-03: score spike invariant removed — large legitimate jumps allowed."""
        existing = {"overall_score": 50, "gates": _make_gates(), "converged": False, "consecutive_converged_cycles": 0}
        proposed = {"overall_score": 70, "gates": _make_gates(), "converged": False, "consecutive_converged_cycles": 0}
        violations = validate_gate_evidence_integrity(proposed, existing)
        assert not any("SCORE SPIKE" in v for v in violations)

    def test_counter_jump_detected(self) -> None:
        existing = {"overall_score": 50, "gates": _make_gates(), "converged": False, "consecutive_converged_cycles": 0}
        proposed = {"overall_score": 55, "gates": _make_gates(), "converged": False, "consecutive_converged_cycles": 3}
        violations = validate_gate_evidence_integrity(proposed, existing)
        assert any("COUNTER JUMP" in v for v in violations)

    def test_counter_regression_detected(self) -> None:
        existing = {"overall_score": 50, "gates": _make_gates(), "converged": False, "consecutive_converged_cycles": 2}
        proposed = {"overall_score": 50, "gates": _make_gates(), "converged": False, "consecutive_converged_cycles": 1}
        violations = validate_gate_evidence_integrity(proposed, existing)
        assert any("COUNTER REGRESSION" in v for v in violations)

    def test_gate_flip_detected(self) -> None:
        existing = {"overall_score": 50, "gates": _make_gates(), "converged": False, "consecutive_converged_cycles": 0}
        proposed = {"overall_score": 55, "gates": _make_gates(P0_zero=True), "converged": False, "consecutive_converged_cycles": 0}
        violations = validate_gate_evidence_integrity(proposed, existing)
        assert any("GATE FLIP: P0_zero" in v for v in violations)

    def test_converged_requires_all_gates(self) -> None:
        existing = {"overall_score": 90, "gates": _make_gates(), "converged": False, "consecutive_converged_cycles": 0}
        proposed = {
            "overall_score": 99, "gates": _make_gates(), "converged": True,
            "consecutive_converged_cycles": 1,
        }
        violations = validate_gate_evidence_integrity(proposed, existing)
        assert any("CONVERGENCE INVARIANT VIOLATION" in v for v in violations)

    def test_converged_accepted_all_true(self) -> None:
        all_true = _make_gates(
            P0_zero=True, P1_zero=True, P2_zero=True,
            critical_security=True, critical_correctness=True,
            data_integrity=True, regression=True, verification=True,
            no_material_new_findings=True, limitations_documented=True,
            consecutive_clean_independent_audits=True, module_dependency_integrity=True,
        )
        existing = {"overall_score": 90, "gates": all_true, "converged": False, "consecutive_converged_cycles": 0}
        proposed = {"overall_score": 99, "gates": all_true, "converged": True, "consecutive_converged_cycles": 1}
        violations = validate_gate_evidence_integrity(proposed, existing)
        assert not any("CONVERGENCE INVARIANT VIOLATION" in v for v in violations)


# ── Gate-Findings Cross-Check ───────────────────────────────────────────────


class TestValidateGateFindingsCrosscheck:
    def test_p0_zero_true_with_open_p0(self) -> None:
        conv = {"gates": {"P0_zero": True}}
        findings = {"findings": [{"id": "F001", "severity": "P0", "status": "OPEN", "category": "SECURITY"}]}
        violations = validate_gate_findings_crosscheck(conv, findings, None)
        assert any("P0_zero" in v for v in violations)

    def test_p0_zero_true_all_verified(self) -> None:
        conv = {"gates": {"P0_zero": True}}
        findings = {"findings": [{"id": "F001", "severity": "P0", "status": "VERIFIED", "category": "SECURITY"}]}
        violations = validate_gate_findings_crosscheck(conv, findings, None)
        assert not violations

    def test_critical_security_with_open(self) -> None:
        conv = {"gates": {"critical_security": True}}
        findings = {"findings": [{"id": "F002", "severity": "P1", "status": "IN_PROGRESS", "category": "SECURITY"}]}
        violations = validate_gate_findings_crosscheck(conv, findings, None)
        assert any("critical_security" in v for v in violations)

    def test_no_material_new_with_new(self) -> None:
        conv = {"gates": {"no_material_new_findings": True}}
        findings = {"findings": [{"id": "F003", "severity": "P0", "status": "OPEN", "category": "SECURITY"}]}
        existing = {"findings": []}
        violations = validate_gate_findings_crosscheck(conv, findings, existing)
        assert any("no_material_new_findings" in v for v in violations)

    def test_no_material_new_with_none_new(self) -> None:
        conv = {"gates": {"no_material_new_findings": True}}
        findings = {"findings": [{"id": "F004", "severity": "P4", "status": "OPEN", "category": "MAINTAINABILITY"}]}
        existing = {"findings": []}
        violations = validate_gate_findings_crosscheck(conv, findings, existing)
        assert not any("no_material_new_findings" in v for v in violations)


# ── Convergence Evaluation ──────────────────────────────────────────────────


class TestEvaluateAllGates:
    def test_empty_findings_all_pass(self) -> None:
        gates = evaluate_all_gates([], 1, 2, 2, limitations_documented=True)
        assert all(gates.values()), f"All gates should pass with no findings. Failing: {[k for k, v in gates.items() if not v]}"

    def test_p0_opened_blocks_p0_zero(self) -> None:
        findings = [{"id": "F001", "severity": "P0", "category": "SECURITY", "status": "OPEN"}]
        gates = evaluate_all_gates(findings, 1, 0, 0)
        assert gates["P0_zero"] is False

    def test_new_material_blocks_no_material_new(self) -> None:
        findings = [{"id": "F-NEW", "severity": "P0", "category": "SECURITY", "status": "OPEN"}]
        previous = [{"id": "F-OLD", "severity": "P1", "category": "SECURITY", "status": "VERIFIED"}]
        gates = evaluate_all_gates(findings, 1, 0, 0, previous_findings=previous)
        assert gates["no_material_new_findings"] is False

    def test_consecutive_clean_requires_both(self) -> None:
        gates_1 = evaluate_all_gates([], 1, 1, 1)
        assert gates_1["consecutive_clean_independent_audits"] is False

        gates_2 = evaluate_all_gates([], 2, 2, 2)
        assert gates_2["consecutive_clean_independent_audits"] is True

    def test_verified_security_allows_critical_security(self) -> None:
        findings = [
            {"id": "F001", "severity": "P0", "category": "SECURITY", "status": "VERIFIED"},
            {"id": "F002", "severity": "P1", "category": "SECURITY", "status": "VERIFIED"},
        ]
        gates = evaluate_all_gates(findings, 1, 0, 0)
        assert gates["critical_security"] is True


# ── Convergence Score ───────────────────────────────────────────────────────


class TestComputeConvergenceScore:
    def test_full_pass_returns_100(self) -> None:
        gates = dict.fromkeys(GATE_NAMES, True)
        severity = {"P0": 625, "P1": 405, "P2": 216, "P3": 90, "P4": 30, "P5": 6}
        score = compute_convergence_score([], severity, gates)
        assert score == 100

    def test_all_gates_fail_returns_low(self) -> None:
        gates = dict.fromkeys(GATE_NAMES, False)
        severity = {"P0": 625, "P1": 405, "P2": 216, "P3": 90, "P4": 30, "P5": 6}
        findings = [{"id": "F001", "severity": "P0", "status": "OPEN"}]
        score = compute_convergence_score(findings, severity, gates)
        assert score < 40

    def test_half_gates_pass(self) -> None:
        gates = {gn: (i % 2 == 0) for i, gn in enumerate(GATE_NAMES)}
        severity = {"P0": 625, "P1": 405, "P2": 216, "P3": 90, "P4": 30, "P5": 6}
        score = compute_convergence_score([], severity, gates)
        assert 25 <= score <= 75


# ── Data Integrity ──────────────────────────────────────────────────────────


class TestStateMachineDataIntegrity:
    def test_12_gates_defined(self) -> None:
        assert len(GATE_NAMES) == 12

    def test_all_gates_have_evidence(self) -> None:
        for gate in GATE_NAMES:
            assert gate in GATE_EVIDENCE_REQUIRED, f"{gate} missing evidence description"

    def test_gate_names_unique(self) -> None:
        assert len(GATE_NAMES) == len(set(GATE_NAMES))

    def test_9_finding_statuses_defined(self) -> None:
        assert len(VALID_FINDING_TRANSITIONS) == 12  # 9 original + 3 terminal (WAIVED, ACCEPTED_RISK, OUT_OF_SCOPE)

    def test_4_classifications_defined(self) -> None:
        assert len(VALID_CLASSIFICATION_TRANSITIONS) == 4

    def test_all_forbidden_have_reason(self) -> None:
        for t in FORBIDDEN_DIRECT_TRANSITIONS:
            assert "From" in t, "Forbidden transition missing 'From'"
            assert "To" in t, "Forbidden transition missing 'To'"
            assert "Reason" in t, "Forbidden transition missing 'Reason'"
            assert len(t["Reason"]) > 0, "Forbidden transition reason is empty"

    def test_not_ready_to_production_ready_blocked_everywhere(self) -> None:
        # NOT_READY → PRODUCTION_READY is forbidden
        assert "PRODUCTION_READY" not in VALID_CLASSIFICATION_TRANSITIONS.get("NOT_READY", [])
        assert is_valid_classification_transition("NOT_READY", "PRODUCTION_READY") is False
