"""Finding classification sub-types — separates real defects from advisories.

A finding is no longer just P0-P5. Each finding now carries a sub-classification
that determines how gates evaluate it.

SUBCLASS:
    CODE_DEFECT           — real code vulnerability/bug
    SECURITY_ADVISORY     — CVE, dependency warning, informational
    TOOLING_FAILURE       — lint/test/build failure
    ENVIRONMENT_BLOCKER   — git error, missing tooling
    GOVERNANCE_FINDING    — license, documentation, policy
    TEST_QUALITY          — test coverage, test patterns
    CODE_QUALITY          — style, type:ignore, complexity
    INFORMATIONAL         — language stats, metadata
"""

from __future__ import annotations

from enum import StrEnum


class FindingSubclass(StrEnum):
    CODE_DEFECT = "CODE_DEFECT"
    SECURITY_ADVISORY = "SECURITY_ADVISORY"
    TOOLING_FAILURE = "TOOLING_FAILURE"
    ENVIRONMENT_BLOCKER = "ENVIRONMENT_BLOCKER"
    GOVERNANCE_FINDING = "GOVERNANCE_FINDING"
    TEST_QUALITY = "TEST_QUALITY"
    CODE_QUALITY = "CODE_QUALITY"
    INFORMATIONAL = "INFORMATIONAL"


# Which subclasses BLOCK convergence gates
# CODE_DEFECT blocks P0/P1/P2_zero and critical_security gates
# Everything else is informational or resolved-by-documentation
BLOCKING_SUBCLASSES: set[FindingSubclass] = {
    FindingSubclass.CODE_DEFECT,
}

# Subclasses that count as "resolved" for critical_security gate
# (they are checked but don't represent unverified vulnerabilities)
ADVISORY_SUBCLASSES: set[FindingSubclass] = {
    FindingSubclass.SECURITY_ADVISORY,
    FindingSubclass.INFORMATIONAL,
}

# Mapping from rule patterns to subclass
_RULE_TO_SUBCLASS: dict[str, FindingSubclass] = {
    # Security advisories — not code defects
    "DEP-CVE-CHECK": FindingSubclass.SECURITY_ADVISORY,
    "DEP-OUTDATED": FindingSubclass.SECURITY_ADVISORY,
    "DEP-ABANDONED": FindingSubclass.SECURITY_ADVISORY,
    "DEP-LOOSE": FindingSubclass.SECURITY_ADVISORY,
    "DEP-RISKY-CRYPTO": FindingSubclass.SECURITY_ADVISORY,
    "DEP-NO-LOCKFILE": FindingSubclass.SECURITY_ADVISORY,
    # Tooling / environment
    "GIT-ERROR": FindingSubclass.ENVIRONMENT_BLOCKER,
    "GIT-DIRTY": FindingSubclass.ENVIRONMENT_BLOCKER,
    # Governance
    "LICENSE-MISSING": FindingSubclass.GOVERNANCE_FINDING,
    "SECURITY-POLICY-MISSING": FindingSubclass.GOVERNANCE_FINDING,
    # Test quality
    "TEST-COV": FindingSubclass.TEST_QUALITY,
    "PY-ASSERT": FindingSubclass.TEST_QUALITY,
    # Code quality (not defects)
    "PY-TYPE-IGNORE-CODED": FindingSubclass.CODE_QUALITY,
    "PY-TYPE-IGNORE": FindingSubclass.CODE_QUALITY,
    "PY-PRINT": FindingSubclass.CODE_QUALITY,
    "PY-STAR-IMPORT": FindingSubclass.CODE_QUALITY,
    "PY-GLOBAL": FindingSubclass.CODE_QUALITY,
    # Informational
    "LANG-INFO": FindingSubclass.INFORMATIONAL,
    # Code defects (default) — anything not mapped above
    "PATH-TRAVERSAL": FindingSubclass.CODE_DEFECT,
    "INJ-": FindingSubclass.CODE_DEFECT,
    "SEC-": FindingSubclass.CODE_DEFECT,
    "CRYPTO-": FindingSubclass.CODE_DEFECT,
    "DESER-": FindingSubclass.CODE_DEFECT,
    "AUTH-": FindingSubclass.CODE_DEFECT,
    "AUTHZ-": FindingSubclass.CODE_DEFECT,
    "SESS-": FindingSubclass.CODE_DEFECT,
    "INPUT-": FindingSubclass.CODE_DEFECT,
    "CONCURRENCY-": FindingSubclass.CODE_DEFECT,
    "PHP-LFI": FindingSubclass.CODE_DEFECT,
    "PHP-SQLI": FindingSubclass.CODE_DEFECT,
    "PHP-XSS": FindingSubclass.CODE_DEFECT,
}


def classify_finding(rule: str) -> FindingSubclass:
    """Classify a finding by its rule into a subclass.

    Uses prefix matching for rule families (e.g. INJ-* → CODE_DEFECT).
    Falls back to CODE_DEFECT for unrecognized rules.
    """
    # Exact match first
    if rule in _RULE_TO_SUBCLASS:
        return _RULE_TO_SUBCLASS[rule]

    # Prefix match
    for prefix, subclass in _RULE_TO_SUBCLASS.items():
        if prefix.endswith("-") and rule.startswith(prefix):
            return subclass

    # Default: assume it's a real finding
    return FindingSubclass.CODE_DEFECT


def is_blocking_for_gate(rule: str, gate_name: str) -> bool:
    """Check if a finding blocks a specific gate.

    Gates:
      - P0_zero/P1_zero/P2_zero: blocked only by CODE_DEFECT with matching severity
      - critical_security: blocked only by CODE_DEFECT in SECURITY category
      - critical_correctness: blocked only by CODE_DEFECT in CORRECTNESS category
    """
    subclass = classify_finding(rule)
    return subclass in BLOCKING_SUBCLASSES


def get_finding_subtype_counts(
    findings: list[dict],
) -> dict[str, int]:
    """Count findings by subclass for display."""
    import re as _re

    counts: dict[str, int] = {}
    for f in findings:
        rule = f.get("rule", "")
        if not rule:
            # Try to extract from problem field "[RULE] message"
            problem = f.get("problem", "")
            m = _re.search(r"\[([A-Z][A-Z0-9_-]+(?:-[A-Z0-9_-]+)*)\]", problem)
            if m:
                rule = m.group(1)
        sub = classify_finding(rule)
        counts[sub.value] = counts.get(sub.value, 0) + 1
    return counts
