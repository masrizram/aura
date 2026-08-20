"""
Plugin system core for AURA audit engine.
Provides the extensibility layer for audit rules, severity scales,
dimension weights, convergence gates, evidence collectors, reporters,
notifiers, and remediators.

Usage:
    from src.plugins import PluginRegistry, PluginLoader
    registry = PluginRegistry()
    loader = PluginLoader(registry)
    loader.load_from_directory(".aura/plugins")
"""

from src.plugins.registry import (
    PluginType,
    PluginLifecycle,
    PluginMetadata,
    BasePlugin,
    AuditRulePlugin,
    SeverityScalePlugin,
    DimensionWeightPlugin,
    ConvergenceGatePlugin,
    EvidenceCollectorPlugin,
    ReporterPlugin,
    NotifierPlugin,
    RemediatorPlugin,
    PluginRegistry,
)

from src.plugins.loader import PluginLoader
from src.plugins.community_registry import CommunityRegistry

__all__ = [
    "PluginType",
    "PluginLifecycle",
    "PluginMetadata",
    "BasePlugin",
    "AuditRulePlugin",
    "SeverityScalePlugin",
    "DimensionWeightPlugin",
    "ConvergenceGatePlugin",
    "EvidenceCollectorPlugin",
    "ReporterPlugin",
    "NotifierPlugin",
    "RemediatorPlugin",
    "PluginRegistry",
    "PluginLoader",
    "CommunityRegistry",
]