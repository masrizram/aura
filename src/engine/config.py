import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional


class AuraConfig:
    def __init__(self, repo_root: str):
        self.repo_root = Path(repo_root).resolve()
        self.config_path = self.repo_root / "config" / "aura.json"
        self._data: Dict[str, Any] = {}
        self.load()

    def load(self):
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as fh:
                    self._data = json.load(fh)
            except json.JSONDecodeError:
                self._data = {}
        else:
            self._data = {}

    def get(self, *keys: str, default: Any = None) -> Any:
        node: Any = self._data
        for k in keys:
            if isinstance(node, dict):
                node = node.get(k)
            else:
                return default
            if node is None:
                return default
        return node

    @property
    def engine(self) -> dict:
        return self._data.get("engine", {})

    @property
    def modules(self) -> dict:
        return self._data.get("modules", {})

    @property
    def required_modules(self) -> List[str]:
        return self.modules.get("required", [])

    @property
    def optional_modules(self) -> List[str]:
        return self.modules.get("optional", [])

    @property
    def experimental_modules(self) -> List[str]:
        return self.modules.get("experimental", [])

    @property
    def max_cycles(self) -> int:
        return int(self.engine.get("max_cycles", 25))

    @property
    def max_cycles_without_progress(self) -> int:
        return int(self.engine.get("max_cycles_without_progress", 3))

    @property
    def min_independent_cycles_for_convergence(self) -> int:
        return int(self.engine.get("min_independent_cycles_for_convergence", 3))

    @property
    def consecutive_converged_cycles_required(self) -> int:
        return int(self.engine.get("consecutive_converged_cycles_required", 2))

    @property
    def state_machine(self) -> dict:
        return self.engine.get("state_machine", {})

    @property
    def state_machine_enabled(self) -> bool:
        return self.state_machine.get("enabled", True)

    @property
    def enforce_finding_transitions(self) -> bool:
        return self.state_machine.get("enforce_finding_transitions", True)

    @property
    def enforce_gate_transitions(self) -> bool:
        return self.state_machine.get("enforce_gate_transitions", True)

    @property
    def enforce_classification_transitions(self) -> bool:
        return self.state_machine.get("enforce_classification_transitions", True)

    @property
    def max_score_increase_per_cycle(self) -> int:
        return int(self.state_machine.get("max_score_increase_per_cycle", 15))

    @property
    def require_evidence_for_gate_flip(self) -> bool:
        return self.state_machine.get("require_evidence_for_gate_flip", True)

    @property
    def max_consecutive_counter_increase(self) -> int:
        return int(self.state_machine.get("max_consecutive_counter_increase", 1))

    @property
    def forbidden_direct_transitions(self) -> List[dict]:
        return self.state_machine.get("forbidden_direct_transitions", [])

    @property
    def convergence_gate(self) -> dict:
        return self.engine.get("convergence_gate", {})

    @property
    def convergence_gate_requires(self) -> List[str]:
        return self.convergence_gate.get("require", [])

    @property
    def severity(self) -> dict:
        return self._data.get("severity", {})

    @property
    def dimensions(self) -> dict:
        return self._data.get("dimensions", {})

    @property
    def phases(self) -> List[str]:
        return self._data.get("phases", [])

    @property
    def push(self) -> dict:
        return self._data.get("push", {})

    @property
    def push_enabled(self) -> bool:
        return self.push.get("enabled", True)

    @property
    def push_auto_approve(self) -> bool:
        return self.push.get("auto_approve", False)

    @property
    def push_commit_template(self) -> str:
        return self.push.get("commit_template", "audit: cycle {cycle} automated remediation ({summary})")

    @property
    def push_verify_remote_sha(self) -> bool:
        return self.push.get("verify_remote_sha_after_push", True)

    @property
    def push_max_retries(self) -> int:
        return int(self.push.get("max_push_retries", 3))

    @property
    def scale_warn_file_count(self) -> int:
        return int(self.engine.get("scale", {}).get("warn_file_count", 500))

    @property
    def scale_chunked_above(self) -> int:
        return int(self.engine.get("scale", {}).get("require_chunked_audit_above", 2000))

    @property
    def scale_prioritized_above(self) -> int:
        return int(self.engine.get("scale", {}).get("require_prioritized_audit_above", 5000))

    @property
    def tooling_execute_before_verification(self) -> bool:
        return self.engine.get("tooling", {}).get("execute_before_verification", True)

    @property
    def scope_validate_audit_scope(self) -> bool:
        return self.engine.get("scope", {}).get("validate_audit_scope", True)

    @property
    def scope_min_audit_pct(self) -> int:
        return int(self.engine.get("scope", {}).get("min_audit_pct_for_convergence", 80))

    @property
    def scope_warn_below_pct(self) -> int:
        return int(self.engine.get("scope", {}).get("warn_below_pct", 50))

    @property
    def state_files(self) -> dict:
        return self._data.get("state_files", {
            "cycle": "state/cycle.json",
            "findings": "state/findings.json",
            "convergence": "state/convergence.json",
        })

    @property
    def reports(self) -> dict:
        return self._data.get("reports", {})

    @property
    def prompts(self) -> dict:
        return self._data.get("prompts", {})

    @property
    def locale(self) -> dict:
        return self._data.get("locale", {})

    @property
    def default_language(self) -> str:
        return self.engine.get("default_language", "en")

    @property
    def languages(self) -> dict:
        return self.engine.get("languages", {"en": "English"})


_config_cache: Optional[AuraConfig] = None


def get_config(repo_root: Optional[str] = None) -> AuraConfig:
    global _config_cache
    if repo_root is None:
        raise ValueError("repo_root must be provided on first call")
    if _config_cache is None or str(_config_cache.repo_root) != str(Path(repo_root).resolve()):
        _config_cache = AuraConfig(str(repo_root))
    return _config_cache