"""AURA v3.5 — Autonomous Software Reliability Engine.

Semantic Code Intelligence: 51 language groups (17 with active rules), AST + data-flow + taint,
framework awareness, confidence classification, CWE/OWASP/CVSS,
12-gate convergence model with 7 safeguards, repository memory.
"""

from .engine import Engine, AncillaryFinding, CodeIssueBridge
from .analyzer import MultiLangAnalyzer, TrendAnalyzer
from .adversarial import AdversarialAuditor, SelfTestCampaigns
from .domain_auditor import DomainAuditOrchestrator, SharedIntelligence, DOMAIN_REGISTRY
from .semantic import SemanticAuditor, ConfidenceLevel, TaintAnalyzer, RepositoryMemory
from .state_machine import (
    evaluate_all_gates, compute_convergence_score,
    is_valid_finding_transition, validate_gate_evidence_integrity,
    GATE_NAMES, GATE_EVIDENCE_REQUIRED,
)
from .convergence import ConvergenceJudge, LoopSafeguard, FindingIdentityTracker
from .config import AuraConfig, ConfigError
from .db import Database
from .errors import AuraError
from .llm import LLMClient, AutonomousLoop
from .logging import log

__version__ = "3.5.0"