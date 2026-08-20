from typing import Any, Dict, List, Optional


VALID_FINDING_TRANSITIONS: Dict[str, List[str]] = {
    "OPEN":        ["IN_PROGRESS", "DEFERRED", "BLOCKED"],
    "IN_PROGRESS": ["FIXED", "DEFERRED", "BLOCKED", "OPEN"],
    "FIXED":       ["VERIFYING", "OPEN"],
    "VERIFYING":   ["VERIFIED", "REJECTED", "FIXED"],
    "VERIFIED":    ["OPEN"],
    "REJECTED":    ["OPEN", "FIXED"],
    "DEFERRED":    ["OPEN"],
    "BLOCKED":     ["OPEN"],
    "UNVERIFIED":  ["OPEN"],
}

VALID_CLASSIFICATION_TRANSITIONS: Dict[str, List[str]] = {
    "NOT_READY":           ["CONDITIONALLY_READY", "HUMAN_BLOCKED"],
    "CONDITIONALLY_READY": ["PRODUCTION_READY", "NOT_READY", "HUMAN_BLOCKED"],
    "PRODUCTION_READY":    ["NOT_READY", "HUMAN_BLOCKED"],
    "HUMAN_BLOCKED":       ["NOT_READY", "CONDITIONALLY_READY"],
}

FORBIDDEN_DIRECT_TRANSITIONS: List[Dict[str, str]] = [
    {"From": "OPEN", "To": "VERIFIED", "Reason": "Must pass through FIXED and VERIFYING"},
    {"From": "OPEN", "To": "FIXED", "Reason": "Must pass through IN_PROGRESS"},
    {"From": "IN_PROGRESS", "To": "VERIFIED", "Reason": "Must pass through FIXED and VERIFYING"},
    {"From": "FIXED", "To": "VERIFIED", "Reason": "Must pass through VERIFYING"},
    {"From": "VERIFYING", "To": "CLOSED", "Reason": "Must pass through VERIFIED or REJECTED"},
]

GATE_NAMES = [
    "P0_zero", "P1_zero", "P2_zero", "critical_security", "critical_correctness",
    "data_integrity", "regression", "verification", "no_material_new_findings",
    "limitations_documented", "consecutive_clean_independent_audits", "module_dependency_integrity",
]

GATE_EVIDENCE_REQUIRED: Dict[str, str] = {
    "P0_zero": "All P0 findings must be VERIFIED or DEFERRED with justification",
    "P1_zero": "All P1 findings must be VERIFIED or DEFERRED with justification",
    "P2_zero": "All P2 findings must be VERIFIED or DEFERRED with justification",
    "critical_security": "All SECURITY category P0-P2 findings must be VERIFIED",
    "critical_correctness": "All CORRECTNESS category P0-P2 findings must be VERIFIED",
    "data_integrity": "All DATA_INTEGRITY findings must be VERIFIED",
    "regression": "Regression audit must produce zero re-appeared findings",
    "verification": "All FIXED findings must have verifier evidence (not self-verified)",
    "no_material_new_findings": "Two consecutive cycles must produce zero new P0-P3 findings",
    "limitations_documented": "Remaining limitations must be explicitly listed in reports",
    "consecutive_clean_independent_audits": "consecutive_converged_cycles >= 2 AND audits_since_last_finding >= 2",
    "module_dependency_integrity": "All required modules exist, loaded, and no required-module dependency failures",
}


def _safe_bool(value: Any) -> bool:
    try:
        return bool(value)
    except Exception:
        return False


def test_valid_finding_transition(from_status: Optional[str], to_status: str) -> bool:
    if not from_status:
        return True
    if from_status == to_status:
        return True
    allowed = VALID_FINDING_TRANSITIONS.get(from_status, [])
    return to_status in allowed


def test_forbidden_direct_transition(from_status: str, to_status: str) -> Optional[dict]:
    for forbidden in FORBIDDEN_DIRECT_TRANSITIONS:
        if forbidden["From"] == from_status and forbidden["To"] == to_status:
            return forbidden
    return None


def test_valid_classification_transition(from_class: Optional[str], to_class: str) -> bool:
    if not from_class:
        return True
    if from_class == to_class:
        return True
    allowed = VALID_CLASSIFICATION_TRANSITIONS.get(from_class, [])
    return to_class in allowed


def validate_finding_state_integrity(proposed_findings_list: List[dict],
                                      existing_findings: Optional[dict]) -> List[str]:
    violations = []
    existing_map: Dict[Any, dict] = {}
    if existing_findings and existing_findings.get("findings"):
        for f in existing_findings["findings"]:
            fid = f.get("id")
            if fid is not None:
                existing_map[fid] = f

    for proposed in proposed_findings_list:
        fid = proposed.get("id")
        if fid is None:
            continue

        existing = existing_map.get(fid)
        if existing is None:
            if proposed.get("status") != "OPEN":
                violations.append(
                    "NEW FINDING VIOLATION: {} is a new finding but has status '{}'. New findings must start as OPEN.".format(
                        fid, proposed.get("status")
                    )
                )
            continue

        forbidden = test_forbidden_direct_transition(
            str(existing.get("status", "")), str(proposed.get("status", ""))
        )
        if forbidden:
            violations.append(
                "ILLEGAL TRANSITION: {}: {} -> {}. {}".format(
                    fid, existing.get("status"), proposed.get("status"), forbidden["Reason"]
                )
            )
            continue

        if not test_valid_finding_transition(
            str(existing.get("status", "")), str(proposed.get("status", ""))
        ):
            violations.append(
                "INVALID TRANSITION: {}: {} -> {} is not an allowed transition.".format(
                    fid, existing.get("status"), proposed.get("status")
                )
            )

    return violations


def validate_gate_evidence_integrity(proposed_convergence: Optional[dict],
                                      existing_convergence: Optional[dict]) -> List[str]:
    violations = []
    if not existing_convergence or not existing_convergence.get("gates"):
        return violations

    existing_gates = existing_convergence.get("gates", {})
    proposed_gates = proposed_convergence.get("gates", {}) if proposed_convergence else {}

    for gate_name in GATE_NAMES:
        old_value = _safe_bool(existing_gates.get(gate_name))
        new_value = _safe_bool(proposed_gates.get(gate_name))

        if not old_value and new_value:
            evidence = GATE_EVIDENCE_REQUIRED.get(gate_name, "Evidence required")
            violations.append("GATE FLIP: {} : false -> true. Evidence required: {}".format(gate_name, evidence))

        if old_value and not new_value:
            violations.append("GATE REGRESSION: {} : true -> false. Regression requires documented finding.".format(gate_name))

    old_converged = _safe_bool(existing_convergence.get("converged"))
    new_converged = _safe_bool(proposed_convergence.get("converged")) if proposed_convergence else False

    if not old_converged and new_converged:
        violations.append("CONVERGENCE FLIP: converged: false -> true. ALL 12 gates must independently PASS before convergence.")
        failing_gates = []
        for gn in GATE_NAMES:
            try:
                gv = _safe_bool(proposed_gates.get(gn))
                if not gv:
                    failing_gates.append(gn)
            except Exception:
                failing_gates.append("{} (missing)".format(gn))
        if failing_gates:
            violations.append("CONVERGENCE BLOCKED: Cannot converge with gates still false/missing: {}".format(", ".join(failing_gates)))

    if new_converged:
        inv_failing = []
        for gn in GATE_NAMES:
            try:
                gv = _safe_bool(proposed_gates.get(gn))
                if not gv:
                    inv_failing.append(gn)
            except Exception:
                inv_failing.append("{} (missing)".format(gn))
        if inv_failing:
            violations.append("CONVERGENCE INVARIANT VIOLATION: converged=true requires ALL gates=true. Failing: {}".format(", ".join(inv_failing)))

    old_score = int(existing_convergence.get("overall_score", 0) or 0)
    new_score = int(proposed_convergence.get("overall_score", 0) or 0) if proposed_convergence else 0
    if new_score < old_score:
        violations.append("SCORE REGRESSION: overall_score decreased from {} to {}. Score can only stay the same or increase.".format(old_score, new_score))
    if new_score > (old_score + 15):
        violations.append("SCORE SPIKE: overall_score jumped from {} to {} (+{}). Maximum per-cycle increase is 15. Requires extraordinary evidence.".format(old_score, new_score, new_score - old_score))

    old_consecutive = int(existing_convergence.get("consecutive_converged_cycles", 0) or 0)
    new_consecutive = int(proposed_convergence.get("consecutive_converged_cycles", 0) or 0) if proposed_convergence else 0
    if new_consecutive < old_consecutive:
        violations.append("COUNTER REGRESSION: consecutive_converged_cycles decreased from {} to {}. Counter must not decrease.".format(old_consecutive, new_consecutive))
    if new_consecutive > (old_consecutive + 1):
        violations.append("COUNTER JUMP: consecutive_converged_cycles jumped from {} to {} (+{}). Max increase is 1 per cycle.".format(old_consecutive, new_consecutive, new_consecutive - old_consecutive))

    return violations


def validate_gate_findings_crosscheck(proposed_convergence: Optional[dict],
                                       proposed_findings: Optional[dict],
                                       existing_findings: Optional[dict]) -> List[str]:
    violations = []
    if not proposed_convergence or not proposed_convergence.get("gates"):
        return violations
    if not proposed_findings or not proposed_findings.get("findings"):
        return violations

    gates = proposed_convergence.get("gates", {})
    findings_list = proposed_findings.get("findings", [])

    gate_finding_map = {
        "P0_zero": {"severities": ["P0"], "label": "P0"},
        "P1_zero": {"severities": ["P1"], "label": "P1"},
        "P2_zero": {"severities": ["P2"], "label": "P2"},
        "critical_security": {"severities": ["P0", "P1", "P2"], "categories": ["SECURITY"], "label": "critical security (P0-P2)"},
        "critical_correctness": {"severities": ["P0", "P1", "P2"], "categories": ["CORRECTNESS"], "label": "critical correctness (P0-P2)"},
        "data_integrity": {"severities": ["P0", "P1", "P2"], "categories": ["DATA_INTEGRITY"], "label": "data integrity (P0-P2)"},
    }

    for gate_name, spec in gate_finding_map.items():
        gate_value = _safe_bool(gates.get(gate_name))
        if gate_value:
            open_violators = []
            for f in findings_list:
                if (f.get("severity") in spec["severities"] and
                    f.get("status") in ("OPEN", "IN_PROGRESS", "FIXED", "VERIFYING", "DEFERRED", "BLOCKED")):
                    if "categories" not in spec or f.get("category") in spec["categories"]:
                        open_violators.append(f)
            truly_open = [f for f in open_violators if f.get("status") != "DEFERRED"]
            if truly_open:
                ids = ", ".join("{}({})".format(f["id"], f.get("status")) for f in truly_open)
                violations.append("GATE-FINDINGS MISMATCH: {} is TRUE but {} open {} finding(s) exist: {}".format(gate_name, len(truly_open), spec["label"], ids))

    no_material = _safe_bool(gates.get("no_material_new_findings"))
    if no_material and existing_findings:
        existing_ids = set()
        for ef in existing_findings.get("findings", []):
            if ef.get("id") is not None:
                existing_ids.add(ef["id"])
        new_material = [f for f in findings_list
                        if f.get("id") is not None and f["id"] not in existing_ids
                        and f.get("severity") in ("P0", "P1", "P2", "P3")]
        if new_material:
            ids = ", ".join("{}({})".format(f["id"], f.get("severity")) for f in new_material)
            violations.append("GATE-FINDINGS MISMATCH: no_material_new_findings is TRUE but {} new P0-P3 finding(s) created this cycle: {}".format(len(new_material), ids))

    return violations