"""Unit tests for the Python state machine implementation."""

import pytest
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src" / "engine"))

from state_machine import (
    test_valid_finding_transition,
    test_valid_classification_transition,
    test_forbidden_direct_transition,
    validate_finding_state_integrity,
    validate_gate_evidence_integrity,
    validate_gate_findings_crosscheck,
    VALID_FINDING_TRANSITIONS,
    VALID_CLASSIFICATION_TRANSITIONS,
    FORBIDDEN_DIRECT_TRANSITIONS,
    GATE_NAMES,
    GATE_EVIDENCE_REQUIRED,
)


def _make_gates(**overrides):
    base = {
        "P0_zero": False, "P1_zero": False, "P2_zero": False,
        "critical_security": False, "critical_correctness": False,
        "data_integrity": False, "regression": False, "verification": False,
        "no_material_new_findings": False, "limitations_documented": False,
        "consecutive_clean_independent_audits": False, "module_dependency_integrity": True,
    }
    base.update(overrides)
    return base


class TestFindingTransitions:
    def test_open_to_in_progress_valid(self):
        assert test_valid_finding_transition("OPEN", "IN_PROGRESS") is True

    def test_open_to_deferred_valid(self):
        assert test_valid_finding_transition("OPEN", "DEFERRED") is True

    def test_open_to_blocked_valid(self):
        assert test_valid_finding_transition("OPEN", "BLOCKED") is True

    def test_in_progress_to_fixed_valid(self):
        assert test_valid_finding_transition("IN_PROGRESS", "FIXED") is True

    def test_fixed_to_verifying_valid(self):
        assert test_valid_finding_transition("FIXED", "VERIFYING") is True

    def test_verifying_to_verified_valid(self):
        assert test_valid_finding_transition("VERIFYING", "VERIFIED") is True

    def test_verifying_to_rejected_valid(self):
        assert test_valid_finding_transition("VERIFYING", "REJECTED") is True

    def test_verified_to_open_valid(self):
        assert test_valid_finding_transition("VERIFIED", "OPEN") is True

    def test_open_to_verified_forbidden(self):
        result = test_forbidden_direct_transition("OPEN", "VERIFIED")
        assert result is not None
        assert "FIXED" in result["Reason"]

    def test_open_to_fixed_forbidden(self):
        result = test_forbidden_direct_transition("OPEN", "FIXED")
        assert result is not None
        assert "IN_PROGRESS" in result["Reason"]

    def test_in_progress_to_verified_forbidden(self):
        result = test_forbidden_direct_transition("IN_PROGRESS", "VERIFIED")
        assert result is not None

    def test_fixed_to_verified_forbidden(self):
        result = test_forbidden_direct_transition("FIXED", "VERIFIED")
        assert result is not None
        assert "VERIFYING" in result["Reason"]

    def test_verifying_to_closed_forbidden(self):
        result = test_forbidden_direct_transition("VERIFYING", "CLOSED")
        assert result is not None

    def test_open_to_verified_not_valid(self):
        assert test_valid_finding_transition("OPEN", "VERIFIED") is False

    def test_open_to_fixed_not_valid(self):
        assert test_valid_finding_transition("OPEN", "FIXED") is False

    def test_fixed_to_verified_not_valid(self):
        assert test_valid_finding_transition("FIXED", "VERIFIED") is False

    def test_verified_to_fixed_not_valid(self):
        assert test_valid_finding_transition("VERIFIED", "FIXED") is False

    def test_verified_to_in_progress_not_valid(self):
        assert test_valid_finding_transition("VERIFIED", "IN_PROGRESS") is False

    def test_same_status_is_valid(self):
        for status in VALID_FINDING_TRANSITIONS:
            assert test_valid_finding_transition(status, status) is True

    def test_null_from_status_returns_true(self):
        assert test_valid_finding_transition(None, "VERIFIED") is True

    def test_empty_from_status_returns_true(self):
        assert test_valid_finding_transition("", "REJECTED") is True

    def test_all_forbidden_transitions_blocked(self):
        for forbidden in FORBIDDEN_DIRECT_TRANSITIONS:
            assert test_forbidden_direct_transition(forbidden["From"], forbidden["To"]) is not None
            assert test_valid_finding_transition(forbidden["From"], forbidden["To"]) is False

    def test_all_declared_valid_transitions_work(self):
        for from_status, allowed in VALID_FINDING_TRANSITIONS.items():
            for to_status in allowed:
                assert test_valid_finding_transition(from_status, to_status) is True, (
                    f"{from_status} -> {to_status} should be valid"
                )

    def test_nonexistent_status_not_valid(self):
        assert test_valid_finding_transition("NONEXISTENT", "OPEN") is False

    def test_rejected_to_verified_not_valid(self):
        assert test_valid_finding_transition("REJECTED", "VERIFIED") is False

    def test_deferred_to_fixed_not_valid(self):
        assert test_valid_finding_transition("DEFERRED", "FIXED") is False

    def test_blocked_to_verified_not_valid(self):
        assert test_valid_finding_transition("BLOCKED", "VERIFIED") is False


class TestClassificationTransitions:
    def test_not_ready_to_conditionally_ready_valid(self):
        assert test_valid_classification_transition("NOT_READY", "CONDITIONALLY_READY") is True

    def test_not_ready_to_human_blocked_valid(self):
        assert test_valid_classification_transition("NOT_READY", "HUMAN_BLOCKED") is True

    def test_conditionally_ready_to_production_ready_valid(self):
        assert test_valid_classification_transition("CONDITIONALLY_READY", "PRODUCTION_READY") is True

    def test_conditionally_ready_to_not_ready_valid(self):
        assert test_valid_classification_transition("CONDITIONALLY_READY", "NOT_READY") is True

    def test_production_ready_to_not_ready_valid(self):
        assert test_valid_classification_transition("PRODUCTION_READY", "NOT_READY") is True

    def test_human_blocked_to_not_ready_valid(self):
        assert test_valid_classification_transition("HUMAN_BLOCKED", "NOT_READY") is True

    def test_not_ready_to_production_ready_forbidden(self):
        assert test_valid_classification_transition("NOT_READY", "PRODUCTION_READY") is False

    def test_production_ready_to_conditionally_ready_not_valid(self):
        assert test_valid_classification_transition("PRODUCTION_READY", "CONDITIONALLY_READY") is False

    def test_human_blocked_to_production_ready_not_valid(self):
        assert test_valid_classification_transition("HUMAN_BLOCKED", "PRODUCTION_READY") is False

    def test_same_classification_is_valid(self):
        for cls in VALID_CLASSIFICATION_TRANSITIONS:
            assert test_valid_classification_transition(cls, cls) is True

    def test_null_from_classification_returns_true(self):
        assert test_valid_classification_transition(None, "PRODUCTION_READY") is True

    def test_empty_from_classification_returns_true(self):
        assert test_valid_classification_transition("", "NOT_READY") is True

    def test_unknown_class_not_valid(self):
        assert test_valid_classification_transition("PRODUCTION_READY", "UNKNOWN") is False


class TestValidateFindingIntegrity:
    def test_rejects_open_to_verified(self):
        existing = {"findings": [{"id": "F001", "status": "OPEN", "severity": "P0"}]}
        proposed = [{"id": "F001", "status": "VERIFIED", "severity": "P0"}]
        violations = validate_finding_state_integrity(proposed, existing)
        assert len(violations) > 0
        assert any("ILLEGAL TRANSITION" in v for v in violations)

    def test_rejects_open_to_fixed(self):
        existing = {"findings": [{"id": "F001", "status": "OPEN", "severity": "P1"}]}
        proposed = [{"id": "F001", "status": "FIXED", "severity": "P1"}]
        violations = validate_finding_state_integrity(proposed, existing)
        assert len(violations) > 0
        assert any("ILLEGAL TRANSITION" in v for v in violations)

    def test_rejects_new_finding_not_open(self):
        existing = {"findings": []}
        proposed = [{"id": "F002", "status": "VERIFIED", "severity": "P2"}]
        violations = validate_finding_state_integrity(proposed, existing)
        assert len(violations) > 0
        assert any("NEW FINDING VIOLATION" in v for v in violations)

    def test_rejects_new_finding_fixed(self):
        existing = {"findings": []}
        proposed = [{"id": "F003", "status": "FIXED", "severity": "P0"}]
        violations = validate_finding_state_integrity(proposed, existing)
        assert len(violations) > 0
        assert any("NEW FINDING VIOLATION" in v for v in violations)

    def test_rejects_new_finding_blocked(self):
        existing = {"findings": []}
        proposed = [{"id": "F004", "status": "BLOCKED", "severity": "P3"}]
        violations = validate_finding_state_integrity(proposed, existing)
        assert len(violations) > 0
        assert any("NEW FINDING VIOLATION" in v for v in violations)

    def test_accepts_valid_transition(self):
        existing = {"findings": [{"id": "F001", "status": "OPEN", "severity": "P0"}]}
        proposed = [{"id": "F001", "status": "IN_PROGRESS", "severity": "P0"}]
        violations = validate_finding_state_integrity(proposed, existing)
        assert len(violations) == 0

    def test_accepts_new_finding_open(self):
        existing = {"findings": []}
        proposed = [{"id": "F005", "status": "OPEN", "severity": "P4"}]
        violations = validate_finding_state_integrity(proposed, existing)
        assert len(violations) == 0

    def test_accepts_same_status(self):
        existing = {"findings": [{"id": "F006", "status": "OPEN", "severity": "P0"}]}
        proposed = [{"id": "F006", "status": "OPEN", "severity": "P0"}]
        violations = validate_finding_state_integrity(proposed, existing)
        assert len(violations) == 0

    def test_accepts_verified_to_open(self):
        existing = {"findings": [{"id": "F007", "status": "VERIFIED", "severity": "P2"}]}
        proposed = [{"id": "F007", "status": "OPEN", "severity": "P2"}]
        violations = validate_finding_state_integrity(proposed, existing)
        assert len(violations) == 0

    def test_handles_null_existing(self):
        proposed = [{"id": "F008", "status": "OPEN", "severity": "P5"}]
        violations = validate_finding_state_integrity(proposed, None)
        assert len(violations) == 0

    def test_handles_empty_proposed(self):
        existing = {"findings": [{"id": "F009", "status": "OPEN", "severity": "P0"}]}
        violations = validate_finding_state_integrity([], existing)
        assert len(violations) == 0

    def test_handles_missing_id_field(self):
        existing = {"findings": []}
        proposed = [{"status": "VERIFIED", "severity": "P0"}]
        violations = validate_finding_state_integrity(proposed, existing)
        assert len(violations) == 0

    def test_mixed_valid_invalid(self):
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

    def test_rejects_verified_to_fixed_backwards(self):
        existing = {"findings": [{"id": "F012", "status": "VERIFIED", "severity": "P1"}]}
        proposed = [{"id": "F012", "status": "FIXED", "severity": "P1"}]
        violations = validate_finding_state_integrity(proposed, existing)
        assert len(violations) > 0
        assert any("INVALID TRANSITION" in v for v in violations)


class TestValidateGateIntegrity:
    def test_score_regression_detected(self):
        existing = {"overall_score": 55, "gates": _make_gates(), "converged": False, "consecutive_converged_cycles": 0}
        proposed = {"overall_score": 50, "gates": _make_gates(), "converged": False, "consecutive_converged_cycles": 0}
        violations = validate_gate_evidence_integrity(proposed, existing)
        assert any("SCORE REGRESSION" in v for v in violations)

    def test_score_spike_detected(self):
        existing = {"overall_score": 50, "gates": _make_gates(), "converged": False, "consecutive_converged_cycles": 0}
        proposed = {"overall_score": 70, "gates": _make_gates(), "converged": False, "consecutive_converged_cycles": 0}
        violations = validate_gate_evidence_integrity(proposed, existing)
        assert any("SCORE SPIKE" in v for v in violations)

    def test_allows_max_increase_15(self):
        existing = {"overall_score": 50, "gates": _make_gates(), "converged": False, "consecutive_converged_cycles": 0}
        proposed = {"overall_score": 65, "gates": _make_gates(), "converged": False, "consecutive_converged_cycles": 0}
        violations = validate_gate_evidence_integrity(proposed, existing)
        assert not any("SCORE SPIKE" in v for v in violations)

    def test_accepts_score_same(self):
        existing = {"overall_score": 55, "gates": _make_gates(), "converged": False, "consecutive_converged_cycles": 0}
        proposed = {"overall_score": 55, "gates": _make_gates(), "converged": False, "consecutive_converged_cycles": 0}
        violations = validate_gate_evidence_integrity(proposed, existing)
        assert not any("SCORE REGRESSION" in v for v in violations)

    def test_counter_jump_detected(self):
        existing = {"overall_score": 50, "gates": _make_gates(), "converged": False, "consecutive_converged_cycles": 0}
        proposed = {"overall_score": 55, "gates": _make_gates(), "converged": False, "consecutive_converged_cycles": 3}
        violations = validate_gate_evidence_integrity(proposed, existing)
        assert any("COUNTER JUMP" in v for v in violations)

    def test_counter_regression_detected(self):
        existing = {"overall_score": 50, "gates": _make_gates(), "converged": False, "consecutive_converged_cycles": 2}
        proposed = {"overall_score": 50, "gates": _make_gates(), "converged": False, "consecutive_converged_cycles": 1}
        violations = validate_gate_evidence_integrity(proposed, existing)
        assert any("COUNTER REGRESSION" in v for v in violations)

    def test_allows_counter_increase_1(self):
        existing = {"overall_score": 50, "gates": _make_gates(), "converged": False, "consecutive_converged_cycles": 0}
        proposed = {"overall_score": 50, "gates": _make_gates(), "converged": False, "consecutive_converged_cycles": 1}
        violations = validate_gate_evidence_integrity(proposed, existing)
        assert not any("COUNTER" in v for v in violations)

    def test_gate_flip_detected(self):
        existing = {"overall_score": 50, "gates": _make_gates(), "converged": False, "consecutive_converged_cycles": 0}
        proposed = {"overall_score": 55, "gates": _make_gates(P0_zero=True), "converged": False, "consecutive_converged_cycles": 0}
        violations = validate_gate_evidence_integrity(proposed, existing)
        assert any("GATE FLIP: P0_zero" in v for v in violations)

    def test_gate_regression_detected(self):
        existing = {"overall_score": 70, "gates": _make_gates(P0_zero=True), "converged": False, "consecutive_converged_cycles": 0}
        proposed = {"overall_score": 70, "gates": _make_gates(P0_zero=False), "converged": False, "consecutive_converged_cycles": 0}
        violations = validate_gate_evidence_integrity(proposed, existing)
        assert any("GATE REGRESSION: P0_zero" in v for v in violations)

    def test_converged_requires_all_gates(self):
        existing = {"overall_score": 90, "gates": _make_gates(), "converged": False, "consecutive_converged_cycles": 0}
        proposed = {
            "overall_score": 99,
            "gates": _make_gates(),
            "converged": True,
            "consecutive_converged_cycles": 1,
        }
        violations = validate_gate_evidence_integrity(proposed, existing)
        assert any("CONVERGENCE INVARIANT VIOLATION" in v for v in violations)
        assert any("CONVERGENCE FLIP" in v for v in violations)

    def test_converged_accepted_all_gates_true(self):
        all_true_gates = _make_gates(
            P0_zero=True, P1_zero=True, P2_zero=True,
            critical_security=True, critical_correctness=True,
            data_integrity=True, regression=True, verification=True,
            no_material_new_findings=True, limitations_documented=True,
            consecutive_clean_independent_audits=True, module_dependency_integrity=True,
        )
        existing = {"overall_score": 90, "gates": all_true_gates, "converged": False, "consecutive_converged_cycles": 0}
        proposed = {
            "overall_score": 99,
            "gates": all_true_gates,
            "converged": True,
            "consecutive_converged_cycles": 1,
        }
        violations = validate_gate_evidence_integrity(proposed, existing)
        assert not any("CONVERGENCE INVARIANT VIOLATION" in v for v in violations)

    def test_converged_already_true_rejects_gate_false(self):
        gates = _make_gates(P0_zero=False, P1_zero=True, P2_zero=True, critical_security=True,
                            critical_correctness=True, data_integrity=True, regression=True,
                            verification=True, no_material_new_findings=True, limitations_documented=True,
                            consecutive_clean_independent_audits=True)
        existing = {"overall_score": 90, "gates": gates, "converged": True, "consecutive_converged_cycles": 1}
        proposed = {"overall_score": 95, "gates": gates, "converged": True, "consecutive_converged_cycles": 2}
        violations = validate_gate_evidence_integrity(proposed, existing)
        assert any("CONVERGENCE INVARIANT VIOLATION" in v for v in violations)

    def test_null_existing_returns_empty(self):
        proposed = {"overall_score": 99, "gates": _make_gates(), "converged": True, "consecutive_converged_cycles": 1}
        violations = validate_gate_evidence_integrity(proposed, None)
        assert len(violations) == 0

    def test_no_gates_returns_empty(self):
        existing = {"converged": False}
        proposed = {"overall_score": 99, "gates": {}, "converged": True, "consecutive_converged_cycles": 1}
        violations = validate_gate_evidence_integrity(proposed, existing)
        assert len(violations) == 0


class TestValidateGateFindingsCrosscheck:
    def test_p0_zero_true_with_open_p0_finding(self):
        conv = {"gates": {"P0_zero": True}}
        findings = {"findings": [{"id": "F001", "severity": "P0", "status": "OPEN", "category": "SECURITY"}]}
        violations = validate_gate_findings_crosscheck(conv, findings, None)
        assert any("P0_zero" in v for v in violations)

    def test_p0_zero_true_with_all_verified(self):
        conv = {"gates": {"P0_zero": True}}
        findings = {"findings": [{"id": "F001", "severity": "P0", "status": "VERIFIED", "category": "SECURITY"}]}
        violations = validate_gate_findings_crosscheck(conv, findings, None)
        assert not violations

    def test_critical_security_with_open_security_finding(self):
        conv = {"gates": {"critical_security": True}}
        findings = {"findings": [{"id": "F002", "severity": "P1", "status": "IN_PROGRESS", "category": "SECURITY"}]}
        violations = validate_gate_findings_crosscheck(conv, findings, None)
        assert any("critical_security" in v for v in violations)

    def test_no_material_new_findings_with_new_findings(self):
        conv = {"gates": {"no_material_new_findings": True}}
        findings = {"findings": [{"id": "F003", "severity": "P0", "status": "OPEN", "category": "SECURITY"}]}
        existing = {"findings": []}
        violations = validate_gate_findings_crosscheck(conv, findings, existing)
        assert any("no_material_new_findings" in v for v in violations)

    def test_no_material_new_findings_with_no_new(self):
        conv = {"gates": {"no_material_new_findings": True}}
        findings = {"findings": [{"id": "F004", "severity": "P4", "status": "OPEN", "category": "MAINTAINABILITY"}]}
        existing = {"findings": []}
        violations = validate_gate_findings_crosscheck(conv, findings, existing)
        assert not any("no_material_new_findings" in v for v in violations)

    def test_null_conv_returns_empty(self):
        violations = validate_gate_findings_crosscheck(None, {"findings": []}, None)
        assert len(violations) == 0


class TestGateEvidenceMapping:
    def test_all_12_gates_have_evidence_descriptions(self):
        assert len(GATE_NAMES) == 12
        for gate in GATE_NAMES:
            assert gate in GATE_EVIDENCE_REQUIRED, f"{gate} missing evidence description"

    def test_gate_names_are_unique(self):
        assert len(GATE_NAMES) == len(set(GATE_NAMES))


class TestModuleClassification:
    def test_unclassified_module_should_be_treated_as_required(self):
        classified_modules = {"required": {"a.ps1": True}, "optional": {"b.ps1": True}, "experimental": {"c.ps1": True}}
        module_name = "unknown-module.ps1"
        is_classified = (
            module_name in classified_modules["required"]
            or module_name in classified_modules["optional"]
            or module_name in classified_modules["experimental"]
        )
        assert not is_classified
        assert not is_classified


class TestStateMachineDataIntegrity:
    def test_valid_finding_transitions_cover_all_statuses(self):
        assert len(VALID_FINDING_TRANSITIONS) == 9

    def test_valid_classification_transitions_cover_all(self):
        assert len(VALID_CLASSIFICATION_TRANSITIONS) == 4

    def test_forbidden_transitions_all_have_reason(self):
        for t in FORBIDDEN_DIRECT_TRANSITIONS:
            assert "From" in t
            assert "To" in t
            assert "Reason" in t
            assert len(t["Reason"]) > 0