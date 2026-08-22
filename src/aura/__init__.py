"""AURA v3.5 — Autonomous Software Reliability Engine.

Semantic Code Intelligence: 51 language groups (17 with active rules), AST + data-flow + taint,
framework awareness, confidence classification, CWE/OWASP/CVSS,
12-gate convergence model with 7 safeguards, repository memory.
"""

from .adversarial import AdversarialAuditor, SelfTestCampaigns
from .analyzer import MultiLangAnalyzer, TrendAnalyzer
from .config import AuraConfig, ConfigError
from .convergence import ConvergenceJudge, FindingIdentityTracker, LoopSafeguard
from .db import Database
from .domain_auditor import DOMAIN_REGISTRY, DomainAuditOrchestrator, SharedIntelligence
from .engine import AncillaryFinding, CodeIssueBridge, Engine
from .errors import AuraError
from .llm import AutonomousLoop, LLMClient
from .logging import log
from .semantic import ConfidenceLevel, RepositoryMemory, SemanticAuditor, TaintAnalyzer
from .state_machine import (
    GATE_EVIDENCE_REQUIRED,
    GATE_NAMES,
    compute_convergence_score,
    evaluate_all_gates,
    is_valid_finding_transition,
    validate_finding_state_integrity,
    validate_gate_evidence_integrity,
    validate_gate_findings_crosscheck,
)

__version__ = "3.5.3"

# Public API surface — re-exports for `from aura import X` consumers.
# Declared explicitly to satisfy F401 (unused-import) for intentional re-exports.
__all__ = [
    "DOMAIN_REGISTRY",
    "GATE_EVIDENCE_REQUIRED",
    "GATE_NAMES",
    "AdversarialAuditor",
    "AncillaryFinding",
    "AuraConfig",
    "AuraError",
    "AutonomousLoop",
    "CodeIssueBridge",
    "ConfigError",
    "ConfidenceLevel",
    "ConvergenceJudge",
    "Database",
    "DomainAuditOrchestrator",
    "Engine",
    "FindingIdentityTracker",
    "LLMClient",
    "LoopSafeguard",
    "MultiLangAnalyzer",
    "RepositoryMemory",
    "SelfTestCampaigns",
    "SemanticAuditor",
    "SharedIntelligence",
    "TaintAnalyzer",
    "TrendAnalyzer",
    "__version__",
    "compute_convergence_score",
    "evaluate_all_gates",
    "is_valid_finding_transition",
    "log",
    "validate_finding_state_integrity",
    "validate_gate_evidence_integrity",
    "validate_gate_findings_crosscheck",
]
