"""
Plugin registry for AURA audit engine.
Manages discovery, loading, and lifecycle of plugins.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Callable, Any, Type, Tuple
from enum import Enum
import json
import sys
import importlib
import importlib.util
from pathlib import Path


class PluginType(Enum):
    AUDIT_RULE = "audit_rule"
    SEVERITY_SCALE = "severity_scale"
    DIMENSION_WEIGHT = "dimension_weight"
    CONVERGENCE_GATE = "convergence_gate"
    EVIDENCE_COLLECTOR = "evidence_collector"
    REPORTER = "reporter"
    NOTIFIER = "notifier"
    REMEDIATOR = "remediator"


class PluginLifecycle(Enum):
    PER_CYCLE = "per_cycle"
    PER_FINDING = "per_finding"
    ON_DEMAND = "on_demand"
    STARTUP = "startup"


@dataclass
class PluginMetadata:
    name: str
    version: str
    plugin_type: PluginType
    lifecycle: PluginLifecycle
    author: str = ""
    description: str = ""
    dependencies: List[str] = field(default_factory=list)
    priority: int = 100
    enabled: bool = True


class BasePlugin(ABC):
    """Base plugin interface that all AURA plugins must implement."""

    _metadata: Optional[PluginMetadata] = None

    def get_metadata(self) -> PluginMetadata:
        if self._metadata is None:
            raise NotImplementedError(
                "Plugin must set _metadata in __init__ or override get_metadata()"
            )
        return self._metadata

    def on_init(self, engine_config: Dict) -> None:
        pass

    def on_cycle_start(self, cycle: int) -> None:
        pass

    def on_cycle_end(self, cycle: int) -> None:
        pass

    def validate(self) -> List[str]:
        errors: List[str] = []
        meta = self.get_metadata()
        if not meta.name or not meta.name.strip():
            errors.append("Plugin name is required")
        if not meta.version or not meta.version.strip():
            errors.append("Plugin version is required")
        return errors


class AuditRulePlugin(BasePlugin):
    """Plugin that adds custom audit rules."""

    @abstractmethod
    def get_rules(self) -> List[Dict]:
        pass

    @abstractmethod
    def check_file(self, filepath: str, content: str) -> List[Dict]:
        pass


class SeverityScalePlugin(BasePlugin):
    """Plugin that adds custom severity scales for specific domains."""

    @abstractmethod
    def get_scales(self) -> Dict[str, Dict]:
        pass


class DimensionWeightPlugin(BasePlugin):
    """Plugin that provides custom dimension weights."""

    @abstractmethod
    def get_weights(self) -> Dict[str, float]:
        pass


class ConvergenceGatePlugin(BasePlugin):
    """Plugin that adds custom convergence gates."""

    @abstractmethod
    def get_gates(self) -> List[Dict]:
        pass

    @abstractmethod
    def evaluate_gate(self, gate_id: str, state: Dict) -> Tuple[bool, str]:
        pass


class EvidenceCollectorPlugin(BasePlugin):
    """Plugin that gathers tooling evidence from external sources."""

    @abstractmethod
    def collect(self, context: Dict) -> Dict:
        pass


class ReporterPlugin(BasePlugin):
    """Plugin that generates custom report formats."""

    @abstractmethod
    def generate_report(self, findings: List[Dict], state: Dict) -> str:
        pass


class NotifierPlugin(BasePlugin):
    """Plugin that sends notifications to external channels."""

    @abstractmethod
    def notify(self, event: str, payload: Dict) -> bool:
        pass


class RemediatorPlugin(BasePlugin):
    """Plugin that provides automated fixes for specific finding categories."""

    @abstractmethod
    def can_remediate(self, finding: Dict) -> bool:
        pass

    @abstractmethod
    def remediate(self, finding: Dict) -> Dict:
        pass


class PluginRegistry:
    def __init__(self, plugins_dir: Optional[str] = None):
        self._plugins: Dict[str, BasePlugin] = {}
        self._by_type: Dict[PluginType, List[BasePlugin]] = {pt: [] for pt in PluginType}
        self._disabled: List[str] = []
        self._errors: Dict[str, str] = {}
        self._plugins_dir = plugins_dir
        self._config: Dict = {}

    def configure(self, config: Dict) -> None:
        self._config = config
        disabled_list = config.get("disabled_plugins", [])
        if isinstance(disabled_list, list):
            self._disabled = disabled_list

    def discover_plugins(self, directories: List[str]) -> int:
        count = 0
        for directory in directories:
            dir_path = Path(directory)
            if not dir_path.is_dir():
                continue
            for item in sorted(dir_path.iterdir()):
                if item.suffix.lower() in (".yml", ".yaml"):
                    if self.load_yaml_plugin(str(item)):
                        count += 1
        return count

    def load_plugin(self, plugin_path: str) -> bool:
        path = Path(plugin_path)
        if not path.exists():
            self._errors[plugin_path] = "Plugin path not found"
            return False
        if path.suffix.lower() in (".yml", ".yaml"):
            return self.load_yaml_plugin(plugin_path)
        if path.suffix.lower() == ".py":
            return self._load_python_plugin(plugin_path)
        if path.is_dir() and (path / "__init__.py").exists():
            return self._load_python_plugin(str(path))
        self._errors[plugin_path] = f"Unsupported plugin format: {path.suffix}"
        return False

    def load_yaml_plugin(self, config_path: str) -> bool:
        try:
            import yaml
        except ImportError:
            self._errors[config_path] = "PyYAML is required for YAML plugin loading"
            return False

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
        except Exception as e:
            self._errors[config_path] = f"Failed to read plugin config: {e}"
            return False

        if not isinstance(config, dict):
            self._errors[config_path] = "Invalid plugin config: must be a mapping"
            return False

        name = config.get("name")
        if not name:
            self._errors[config_path] = "Plugin name is required"
            return False

        if name in self._disabled:
            self._errors[name] = "Plugin is disabled by configuration"
            return False

        plugin_type = self._parse_plugin_type(config.get("plugin_type"))
        lifecycle = self._parse_lifecycle(config.get("lifecycle"))

        version = config.get("version", "0.0.0")
        if not isinstance(version, str):
            version = str(version)

        metadata = PluginMetadata(
            name=name,
            version=version,
            plugin_type=plugin_type,
            lifecycle=lifecycle,
            author=config.get("author", ""),
            description=config.get("description", ""),
            dependencies=config.get("dependencies", []),
            priority=config.get("priority", 100),
            enabled=config.get("enabled", True),
        )

        plugin_instance = self._build_yaml_plugin(metadata, config, config_path)
        if plugin_instance is None:
            return False

        self._plugins[name] = plugin_instance
        self._by_type[plugin_type].append(plugin_instance)
        return True

    def _build_yaml_plugin(
        self, metadata: PluginMetadata, config: Dict, config_path: str
    ) -> Optional[BasePlugin]:
        if metadata.plugin_type == PluginType.AUDIT_RULE:
            return _YamlAuditRulePlugin(metadata, config)
        if metadata.plugin_type == PluginType.SEVERITY_SCALE:
            return _YamlSeverityScalePlugin(metadata, config)
        if metadata.plugin_type == PluginType.DIMENSION_WEIGHT:
            return _YamlDimensionWeightPlugin(metadata, config)
        if metadata.plugin_type == PluginType.CONVERGENCE_GATE:
            return _YamlConvergenceGatePlugin(metadata, config)
        self._errors[metadata.name] = (
            f"Plugin type {metadata.plugin_type.value} requires a Python module, "
            "not a YAML config"
        )
        return None

    def _load_python_plugin(self, plugin_path: str) -> bool:
        path = Path(plugin_path)
        try:
            if path.is_dir():
                module_name = path.name
                spec = importlib.util.spec_from_file_location(
                    module_name, str(path / "__init__.py")
                )
            else:
                module_name = path.stem
                spec = importlib.util.spec_from_file_location(
                    module_name, str(path)
                )
        except Exception as e:
            self._errors[plugin_path] = f"Failed to create module spec: {e}"
            return False

        if spec is None or spec.loader is None:
            self._errors[plugin_path] = "Could not create module spec"
            return False

        try:
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
        except Exception as e:
            self._errors[plugin_path] = f"Failed to load module: {e}"
            return False

        plugin_class = None
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (
                isinstance(attr, type)
                and issubclass(attr, BasePlugin)
                and attr is not BasePlugin
                and attr is not AuditRulePlugin
                and attr is not SeverityScalePlugin
                and attr is not DimensionWeightPlugin
                and attr is not ConvergenceGatePlugin
                and attr is not EvidenceCollectorPlugin
                and attr is not ReporterPlugin
                and attr is not NotifierPlugin
                and attr is not RemediatorPlugin
            ):
                plugin_class = attr
                break

        if plugin_class is None:
            self._errors[plugin_path] = "No BasePlugin subclass found in module"
            return False

        try:
            instance = plugin_class()
        except Exception as e:
            self._errors[plugin_path] = f"Failed to instantiate plugin: {e}"
            return False

        metadata = instance.get_metadata()
        if metadata.name in self._disabled:
            self._errors[metadata.name] = "Plugin is disabled by configuration"
            return False

        self._plugins[metadata.name] = instance
        self._by_type[metadata.plugin_type].append(instance)
        return True

    def load_from_package(self, package_name: str) -> int:
        try:
            pkg = importlib.import_module(package_name)
        except ImportError as e:
            self._errors[package_name] = f"Package not found: {e}"
            return 0

        count = 0
        if hasattr(pkg, "__path__"):
            for pkg_path in pkg.__path__:
                p = Path(pkg_path)
                if not p.is_dir():
                    continue
                for item in sorted(p.iterdir()):
                    if item.suffix.lower() in (".yml", ".yaml"):
                        if self.load_yaml_plugin(str(item)):
                            count += 1
        return count

    def get_plugins_by_type(self, plugin_type: PluginType) -> List[BasePlugin]:
        return sorted(
            self._by_type.get(plugin_type, []),
            key=lambda p: p.get_metadata().priority,
        )

    def run_lifecycle_hooks(self, lifecycle: PluginLifecycle, **kwargs: Any) -> None:
        for plugin in self._plugins.values():
            if plugin.get_metadata().lifecycle != lifecycle:
                continue
            if lifecycle == PluginLifecycle.STARTUP:
                plugin.on_init(kwargs.get("engine_config", {}))
            elif lifecycle == PluginLifecycle.PER_CYCLE:
                cycle = kwargs.get("cycle")
                if cycle is not None:
                    plugin.on_cycle_start(cycle)
            elif lifecycle == PluginLifecycle.ON_DEMAND:
                pass

    def run_phase_hooks(
        self, phase: str, lifecycle: PluginLifecycle, **kwargs: Any
    ) -> None:
        for plugin in self._plugins.values():
            if plugin.get_metadata().lifecycle != lifecycle:
                continue
            method_name = f"on_{phase.lower()}"
            hook = getattr(plugin, method_name, None)
            if callable(hook):
                hook(**kwargs)

    def get_all_audit_rules(self) -> List[Dict]:
        rules: List[Dict] = []
        for plugin in self.get_plugins_by_type(PluginType.AUDIT_RULE):
            try:
                plugin_rules = plugin.get_rules()
                if isinstance(plugin_rules, list):
                    rules.extend(plugin_rules)
            except Exception as e:
                meta = plugin.get_metadata()
                self._errors[meta.name] = f"Failed to get rules: {e}"
        return rules

    def get_severity_scales(self) -> Dict[str, Dict]:
        scales: Dict[str, Dict] = {}
        for plugin in self.get_plugins_by_type(PluginType.SEVERITY_SCALE):
            try:
                plugin_scales = plugin.get_scales()
                if isinstance(plugin_scales, dict):
                    scales.update(plugin_scales)
            except Exception as e:
                meta = plugin.get_metadata()
                self._errors[meta.name] = f"Failed to get scales: {e}"
        return scales

    def get_dimension_weights(self) -> Dict[str, float]:
        weights: Dict[str, float] = {}
        for plugin in self.get_plugins_by_type(PluginType.DIMENSION_WEIGHT):
            try:
                plugin_weights = plugin.get_weights()
                if isinstance(plugin_weights, dict):
                    weights.update(plugin_weights)
            except Exception as e:
                meta = plugin.get_metadata()
                self._errors[meta.name] = f"Failed to get weights: {e}"
        return weights

    def validate_all(self) -> Dict[str, List[str]]:
        result: Dict[str, List[str]] = {}
        for name, plugin in self._plugins.items():
            try:
                errors = plugin.validate()
                if errors:
                    result[name] = errors
            except Exception as e:
                result[name] = [f"Validation raised: {e}"]
        for name, err in self._errors.items():
            result[name] = [err]
        return result

    def status(self) -> Dict:
        by_type_counts = {
            pt.value: len(plugins) for pt, plugins in self._by_type.items()
        }
        return {
            "loaded_count": len(self._plugins),
            "by_type": by_type_counts,
            "errors": dict(self._errors),
            "disabled": list(self._disabled),
            "plugin_names": sorted(self._plugins.keys()),
        }

    @staticmethod
    def _parse_plugin_type(raw: Optional[str]) -> PluginType:
        if not raw:
            return PluginType.AUDIT_RULE
        try:
            return PluginType(raw.lower())
        except ValueError:
            return PluginType.AUDIT_RULE

    @staticmethod
    def _parse_lifecycle(raw: Optional[str]) -> PluginLifecycle:
        if not raw:
            return PluginLifecycle.PER_CYCLE
        try:
            return PluginLifecycle(raw.lower())
        except ValueError:
            return PluginLifecycle.PER_CYCLE


class _YamlAuditRulePlugin(AuditRulePlugin):
    def __init__(self, metadata: PluginMetadata, config: Dict) -> None:
        self._metadata = metadata
        self._rules: List[Dict] = config.get("rules", [])
        self._severity_scale: Dict[str, Dict] = config.get("severity_scale", {})
        self._compile_patterns()

    def _compile_patterns(self) -> None:
        import re
        for rule in self._rules:
            patterns = []
            raw_pattern = rule.get("pattern")
            if raw_pattern:
                patterns.append(raw_pattern)
            raw_patterns = rule.get("patterns", [])
            if isinstance(raw_patterns, list):
                patterns.extend(raw_patterns)
            compiled = []
            for p in patterns:
                try:
                    compiled.append(re.compile(p, re.IGNORECASE | re.MULTILINE))
                except re.error:
                    compiled.append(None)
            rule["_compiled_patterns"] = compiled

    def get_rules(self) -> List[Dict]:
        result = []
        for rule in self._rules:
            copy = {k: v for k, v in rule.items() if not k.startswith("_")}
            result.append(copy)
        return result

    def check_file(self, filepath: str, content: str) -> List[Dict]:
        findings: List[Dict] = []
        for rule in self._rules:
            compiled = rule.get("_compiled_patterns", [])
            for i, pattern in enumerate(compiled):
                if pattern is None:
                    continue
                for match in pattern.finditer(content):
                    findings.append({
                        "rule_id": rule.get("id", "UNKNOWN"),
                        "name": rule.get("name", rule.get("id", "Unnamed")),
                        "severity": rule.get("severity", "P3"),
                        "category": rule.get("category", "UNCATEGORIZED"),
                        "file": filepath,
                        "line": content[: match.start()].count("\n") + 1,
                        "match": match.group(0),
                        "description": rule.get("description", ""),
                        "plugin": self._metadata.name,
                    })
        return findings

    def get_scales(self) -> Dict[str, Dict]:
        return self._severity_scale


class _YamlSeverityScalePlugin(SeverityScalePlugin):
    def __init__(self, metadata: PluginMetadata, config: Dict) -> None:
        self._metadata = metadata
        self._scales: Dict[str, Dict] = config.get("severity_scale", {})

    def get_scales(self) -> Dict[str, Dict]:
        return self._scales


class _YamlDimensionWeightPlugin(DimensionWeightPlugin):
    def __init__(self, metadata: PluginMetadata, config: Dict) -> None:
        self._metadata = metadata
        self._weights: Dict[str, float] = config.get("dimension_weights", {})

    def get_weights(self) -> Dict[str, float]:
        return self._weights


class _YamlConvergenceGatePlugin(ConvergenceGatePlugin):
    def __init__(self, metadata: PluginMetadata, config: Dict) -> None:
        self._metadata = metadata
        self._gates: List[Dict] = config.get("gates", [])

    def get_gates(self) -> List[Dict]:
        return [
            {k: v for k, v in gate.items() if k != "check_script"}
            for gate in self._gates
        ]

    def evaluate_gate(self, gate_id: str, state: Dict) -> Tuple[bool, str]:
        for gate in self._gates:
            if gate.get("id") == gate_id:
                script = gate.get("check_script")
                if script:
                    try:
                        result = eval(script, {"state": state, "__builtins__": {}})
                        if result:
                            return True, gate.get("pass_message", "PASS")
                        return False, gate.get("fail_message", "FAIL")
                    except Exception as e:
                        return False, f"Gate evaluation error: {e}"
                return False, "No check script defined"
        return False, f"Gate '{gate_id}' not found"