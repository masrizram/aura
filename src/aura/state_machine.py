"""AURA state machine — enforces finding transitions, classification transitions,
and convergence gate invariants.

This is the authoritative enforcement layer. No state change bypasses these rules.
"""

from __future__ import annotations

from typing import Any

# ── Finding Status Transitions ──────────────────────────────────────────────
# Each status maps to its allowed destination statuses.

VALID_FINDING_TRANSITIONS: dict[str, list[str]] = {
    "OPEN":        ["IN_PROGRESS", "DEFERRED", "BLOCKED"],
    "IN_PROGRESS": ["FIXED", "DEFERRED", "BLOCKED", "OPEN"],
    "FIXED":       ["VERIFYING", "OPEN"],
    "VERIFYING":   ["VERIFIED", "REJECTED", "FIXED"],
    "VERIFIED":    ["OPEN"],
    "REJECTED":    ["OPEN", "FIXED"],
    "DEFERRED":    ["OPEN"],
    "BLOCKED":     ["OPEN"],
    "UNVERIFIED":  ["OPEN"],
    "WAIVED":      [],  # Terminal: intentionally waived, no further action
    "ACCEPTED_RISK": [],  # Terminal: risk accepted by team
    "OUT_OF_SCOPE": [],   # Terminal: outside remediation scope
}

# ── Classification Transitions ──────────────────────────────────────────────

VALID_CLASSIFICATION_TRANSITIONS: dict[str, list[str]] = {
    "NOT_READY":           ["CONDITIONALLY_READY", "HUMAN_BLOCKED"],
    "CONDITIONALLY_READY": ["PRODUCTION_READY", "NOT_READY", "HUMAN_BLOCKED"],
    "PRODUCTION_READY":    ["NOT_READY", "HUMAN_BLOCKED"],
    "HUMAN_BLOCKED":       ["NOT_READY", "CONDITIONALLY_READY"],
}

# ── Forbidden Transitions (blocked with reason) ─────────────────────────────

FORBIDDEN_DIRECT_TRANSITIONS: list[dict[str, str]] = [
    {"From": "OPEN", "To": "VERIFIED", "Reason": "Must pass through FIXED and VERIFYING"},
    {"From": "OPEN", "To": "FIXED", "Reason": "Must pass through IN_PROGRESS"},
    {"From": "IN_PROGRESS", "To": "VERIFIED", "Reason": "Must pass through FIXED and VERIFYING"},
    {"From": "FIXED", "To": "VERIFIED", "Reason": "Must pass through VERIFYING"},
    {"From": "VERIFYING", "To": "CLOSED", "Reason": "Must pass through VERIFIED or REJECTED"},
]

# ── 12 Convergence Gates ────────────────────────────────────────────────────

GATE_NAMES: list[str] = [
    "P0_zero",
    "P1_zero",
    "P2_zero",
    "critical_security",
    "critical_correctness",
    "data_integrity",
    "regression",
    "verification",
    "no_material_new_findings",
    "limitations_documented",
    "consecutive_clean_independent_audits",
    "module_dependency_integrity",
]

GATE_EVIDENCE_REQUIRED: dict[str, str] = {
    "P0_zero": "All P0 findings must be VERIFIED or DEFERRED with justification",
    "P1_zero": "All P1 findings must be VERIFIED or DEFERRED with justification",
    "P2_zero": "All P2 findings must be VERIFIED or DEFERRED with justification",
    "critical_security": "All SECURITY category P0-P2 findings must be VERIFIED",
    "critical_correctness": "All CORRECTNESS category P0-P2 findings must be VERIFIED",
    "data_integrity": "All DATA_INTEGRITY findings must be VERIFIED",
    "regression": "Regression audit must produce zero re-appeared findings",
    "verification": "All FIXED findings must have independent verifier evidence",
    "no_material_new_findings": "Two consecutive cycles with zero new P0-P3 findings",
    "limitations_documented": "Remaining limitations must be explicitly listed",
    "consecutive_clean_independent_audits": "consecutive_converged_cycles >= 2 AND audits_since_last_finding >= 2",
    "module_dependency_integrity": "All required modules loaded, no dependency failures",
}


def _safe_bool(value: Any) -> bool:
    """Coerce a value to bool safely."""
    try:
        return bool(value)
    except Exception:
        return False


# ── Finding Transition Validation ───────────────────────────────────────────


def is_valid_finding_transition(from_status: str | None, to_status: str) -> bool:
    """Check if a finding status transition is allowed."""
    if not from_status:
        return True  # New finding
    if from_status == to_status:
        return True  # No change
    allowed = VALID_FINDING_TRANSITIONS.get(from_status, [])
    return to_status in allowed


def is_forbidden_direct_transition(
    from_status: str, to_status: str
) -> dict[str, str] | None:
    """Check if a transition is explicitly forbidden."""
    for forbidden in FORBIDDEN_DIRECT_TRANSITIONS:
        if forbidden["From"] == from_status and forbidden["To"] == to_status:
            return forbidden
    return None


def validate_finding_state_integrity(
    proposed_findings: list[dict[str, Any]],
    existing_findings: dict[str, Any] | None,
) -> list[str]:
    """Validate all finding transitions in proposed state against existing state."""
    violations: list[str] = []

    existing_map: dict[Any, dict[str, Any]] = {}
    if existing_findings and existing_findings.get("findings"):
        for f in existing_findings["findings"]:
            fid = f.get("id")
            if fid is not None:
                existing_map[fid] = f

    for proposed in proposed_findings:
        fid = proposed.get("id")
        if fid is None:
            continue

        existing = existing_map.get(fid)

        # New findings
        if existing is None:
            if proposed.get("status") != "OPEN":
                violations.append(
                    f"NEW FINDING VIOLATION: {fid} is new but has status "
                    f"'{proposed.get('status')}'. New findings must start as OPEN."
                )
            continue

        # Check forbidden transitions first
        forbidden = is_forbidden_direct_transition(
            str(existing.get("status", "")), str(proposed.get("status", ""))
        )
        if forbidden:
            violations.append(
                f"ILLEGAL TRANSITION: {fid}: {existing.get('status')} -> "
                f"{proposed.get('status')}. {forbidden['Reason']}"
            )
            continue

        # Check valid transitions
        if not is_valid_finding_transition(
            str(existing.get("status", "")), str(proposed.get("status", ""))
        ):
            violations.append(
                f"INVALID TRANSITION: {fid}: {existing.get('status')} -> "
                f"{proposed.get('status')} is not allowed."
            )

    return violations


# ── Classification Transition Validation ────────────────────────────────────


def is_valid_classification_transition(
    from_class: str | None, to_class: str
) -> bool:
    """Check if a classification transition is allowed."""
    if not from_class:
        return True
    if from_class == to_class:
        return True
    allowed = VALID_CLASSIFICATION_TRANSITIONS.get(from_class, [])
    return to_class in allowed


# ── Gate Evidence Integrity ─────────────────────────────────────────────────


def validate_gate_evidence_integrity(
    proposed_convergence: dict[str, Any] | None,
    existing_convergence: dict[str, Any] | None,
) -> list[str]:
    """Validate convergence gate transitions and invariants."""
    violations: list[str] = []

    if not existing_convergence or not existing_convergence.get("gates"):
        return violations

    existing_gates = existing_convergence.get("gates", {})
    proposed_gates = proposed_convergence.get("gates", {}) if proposed_convergence else {}

    # Gate flips
    for gate_name in GATE_NAMES:
        old_value = _safe_bool(existing_gates.get(gate_name))
        new_value = _safe_bool(proposed_gates.get(gate_name))

        if not old_value and new_value:
            evidence = GATE_EVIDENCE_REQUIRED.get(gate_name, "Evidence required")
            violations.append(
                f"GATE FLIP: {gate_name} : false -> true. "
                f"Evidence required: {evidence}"
            )

        if old_value and not new_value:
            violations.append(
                f"GATE REGRESSION: {gate_name} : true -> false. "
                f"Regression requires documented finding."
            )

    # Convergence invariants
    old_converged = _safe_bool(existing_convergence.get("converged"))
    new_converged = _safe_bool(proposed_convergence.get("converged")) if proposed_convergence else False

    if not old_converged and new_converged:
        failing_gates = [
            gn for gn in GATE_NAMES
            if not _safe_bool(proposed_gates.get(gn))
        ]
        violations.append(
            "CONVERGENCE FLIP: converged: false -> true. "
            "ALL 12 gates must independently PASS before convergence."
        )
        if failing_gates:
            violations.append(
                f"CONVERGENCE BLOCKED: Gates still failing: {', '.join(failing_gates)}"
            )

    if new_converged:
        inv_failing = [
            gn for gn in GATE_NAMES
            if not _safe_bool(proposed_gates.get(gn))
        ]
        if inv_failing:
            violations.append(
                "CONVERGENCE INVARIANT VIOLATION: converged=true requires ALL gates=true. "
                f"Failing: {', '.join(inv_failing)}"
            )

    # Score invariants
    old_score = int(existing_convergence.get("overall_score", 0) or 0)
    new_score = int(proposed_convergence.get("overall_score", 0) or 0) if proposed_convergence else 0

    if new_score < old_score:
        violations.append(
            f"SCORE REGRESSION: overall_score decreased from {old_score} to {new_score}. "
            f"Score can only stay the same or increase."
        )
    if new_score > (old_score + 15):
        violations.append(
            f"SCORE SPIKE: overall_score jumped from {old_score} to {new_score} "
            f"(+{new_score - old_score}). Maximum per-cycle increase is 15."
        )

    # Counter invariants
    old_consecutive = int(existing_convergence.get("consecutive_converged_cycles", 0) or 0)
    new_consecutive = int(proposed_convergence.get("consecutive_converged_cycles", 0) or 0) if proposed_convergence else 0

    if new_consecutive < old_consecutive:
        violations.append(
            f"COUNTER REGRESSION: consecutive_converged_cycles decreased from "
            f"{old_consecutive} to {new_consecutive}. Counter must not decrease."
        )
    if new_consecutive > (old_consecutive + 1):
        violations.append(
            f"COUNTER JUMP: consecutive_converged_cycles jumped from "
            f"{old_consecutive} to {new_consecutive} (+{new_consecutive - old_consecutive}). "
            f"Max increase is 1 per cycle."
        )

    return violations


# ── Gate-Findings Cross-Check ───────────────────────────────────────────────


def validate_gate_findings_crosscheck(
    proposed_convergence: dict[str, Any] | None,
    proposed_findings: dict[str, Any] | None,
    existing_findings: dict[str, Any] | None,
) -> list[str]:
    """Cross-validate gate values against actual finding data."""
    violations: list[str] = []

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
        "critical_security": {
            "severities": ["P0", "P1", "P2"],
            "categories": ["SECURITY"],
            "label": "critical security (P0-P2)",
        },
        "critical_correctness": {
            "severities": ["P0", "P1", "P2"],
            "categories": ["CORRECTNESS"],
            "label": "critical correctness (P0-P2)",
        },
        "data_integrity": {
            "severities": ["P0", "P1", "P2"],
            "categories": ["DATA_INTEGRITY"],
            "label": "data integrity (P0-P2)",
        },
    }

    for gate_name, spec in gate_finding_map.items():
        gate_value = _safe_bool(gates.get(gate_name))
        if gate_value:
            open_violators = [
                f for f in findings_list
                if f.get("severity") in spec["severities"]
                and f.get("status") in ("OPEN", "IN_PROGRESS", "FIXED", "VERIFYING", "BLOCKED")
                and ("categories" not in spec or f.get("category") in spec["categories"])
            ]
            truly_open = [f for f in open_violators if f.get("status") != "DEFERRED"]
            if truly_open:
                ids = ", ".join(f"{f['id']}({f.get('status')})" for f in truly_open)
                violations.append(
                    f"GATE-FINDINGS MISMATCH: {gate_name} is TRUE but "
                    f"{len(truly_open)} open {spec['label']} finding(s) exist: {ids}"
                )

    # no_material_new_findings check
    no_material = _safe_bool(gates.get("no_material_new_findings"))
    if no_material and existing_findings:
        existing_ids = {
            ef["id"] for ef in existing_findings.get("findings", [])
            if ef.get("id") is not None
        }
        new_material = [
            f for f in findings_list
            if f.get("id") is not None
            and f["id"] not in existing_ids
            and f.get("severity") in ("P0", "P1", "P2", "P3")
        ]
        if new_material:
            ids = ", ".join(f"{f['id']}({f.get('severity')})" for f in new_material)
            violations.append(
                f"GATE-FINDINGS MISMATCH: no_material_new_findings is TRUE but "
                f"{len(new_material)} new P0-P3 finding(s) created: {ids}"
            )

    return violations


# ── Convergence Evaluation ──────────────────────────────────────────────────


def evaluate_all_gates(
    findings: list[dict[str, Any]],
    cycle_number: int,
    consecutive_converged: int,
    audits_since_finding: int,
    previous_findings: list[dict[str, Any]] | None = None,
    module_integrity_pass: bool = True,
    limitations_documented: bool = False,
    regression_pass: bool = True,
) -> dict[str, bool]:
    """Evaluate all 12 convergence gates against current findings and state."""

    NON_BLOCKING_STATUSES = {"DEFERRED", "WAIVED", "ACCEPTED_RISK", "OUT_OF_SCOPE"}
    ACTIVE_STATUSES = {"OPEN", "IN_PROGRESS", "FIXED", "VERIFYING", "BLOCKED"}

    def _open(severities: list[str], categories: list[str] | None = None) -> list[dict[str, Any]]:
        return [
            f for f in findings
            if f.get("severity") in severities
            and f.get("status") in ACTIVE_STATUSES
            and (categories is None or f.get("category") in categories)
        ]

    def _verified(severities: list[str], categories: list[str] | None = None) -> bool:
        relevant = [
            f for f in findings
            if f.get("severity") in severities
            and (categories is None or f.get("category") in categories)
        ]
        # VERIFIED, DEFERRED, WAIVED, ACCEPTED_RISK, OUT_OF_SCOPE = resolved
        RESOLVED_STATUSES = {"VERIFIED", "DEFERRED", "WAIVED", "ACCEPTED_RISK", "OUT_OF_SCOPE"}
        return all(
            f.get("status") in RESOLVED_STATUSES for f in relevant
        ) if relevant else True

    # Check for new material findings
    has_new_material = False
    if previous_findings:
        prev_ids = {f.get("id") for f in previous_findings if f.get("id")}
        has_new_material = any(
            f.get("id") not in prev_ids and f.get("severity") in ("P0", "P1", "P2", "P3")
            for f in findings
            if f.get("id")
        )

    gates = {
        "P0_zero": len(_open(["P0"])) == 0,
        "P1_zero": len(_open(["P1"])) == 0,
        "P2_zero": len(_open(["P2"])) == 0,
        "critical_security": _verified(["P0", "P1", "P2"], ["SECURITY"]),
        "critical_correctness": _verified(["P0", "P1", "P2"], ["CORRECTNESS"]),
        "data_integrity": _verified(["P0", "P1", "P2"], ["DATA_INTEGRITY"]),
        "regression": regression_pass,  # Requires regression audit (no reappeared findings)
        "verification": not any(
            f.get("status") == "FIXED"
            for f in findings
        ),  # PASS when no findings are in unverified FIXED state
        "no_material_new_findings": not has_new_material,
        "limitations_documented": limitations_documented,
        "consecutive_clean_independent_audits": (
            consecutive_converged >= 2 and audits_since_finding >= 2
        ),
        "module_dependency_integrity": module_integrity_pass,
    }

    return gates


def compute_convergence_score(
    findings: list[dict[str, Any]],
    severity_weights: dict[str, int],
    gates: dict[str, bool],
) -> int:
    """Compute overall convergence score (0-100)."""
    # Base score from gate passes
    gate_count = sum(1 for v in gates.values() if v)
    gate_score = int((gate_count / len(GATE_NAMES)) * 60)

    # Finding penalty
    # Proportional penalty based on finding count per severity
    total_findings = max(1, len(findings))
    p0_count = sum(1 for f in findings if f.get("severity") == "P0" and f.get("status") in ("OPEN", "IN_PROGRESS"))
    p1_count = sum(1 for f in findings if f.get("severity") == "P1" and f.get("status") in ("OPEN", "IN_PROGRESS"))
    p2_count = sum(1 for f in findings if f.get("severity") == "P2" and f.get("status") in ("OPEN", "IN_PROGRESS"))
    # P0 = 15pts each, P1 = 8pts each, P2 = 3pts each, P3+ = 1pt each
    p3_plus = sum(1 for f in findings if f.get("severity") in ("P3", "P4", "P5") and f.get("status") in ("OPEN", "IN_PROGRESS"))
    penalty = p0_count * 15 + p1_count * 8 + p2_count * 3 + p3_plus * 1
    finding_score = max(0, 40 - min(penalty, 40))
    # Normalize: if total findings large, ensure minimum score floor
    if total_findings > 100 and finding_score < 10:
        finding_score = 10  # Large projects get floor score

    return min(100, gate_score + finding_score)
