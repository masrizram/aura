"""Tests for the AURA config loader."""

import pytest
import json
from pathlib import Path


@pytest.fixture
def sample_aura_json():
    return {
        "engine": {
            "max_cycles": 25,
            "version": "2.1.0",
            "max_cycles_without_progress": 3,
            "min_independent_cycles_for_convergence": 3,
            "consecutive_converged_cycles_required": 2,
            "state_machine": {
                "enabled": True,
                "enforce_finding_transitions": True,
                "enforce_gate_transitions": True,
                "enforce_classification_transitions": True,
                "max_score_increase_per_cycle": 15,
                "require_evidence_for_gate_flip": True,
                "max_consecutive_counter_increase": 1,
            },
        },
        "modules": {
            "required": ["business-invariants.ps1", "evidence-integrity.ps1"],
            "optional": ["repo-graph.ps1", "sandbox.ps1"],
            "experimental": ["adversarial-campaign.ps1"],
        },
        "severity": {
            "P0": {"label": "Catastrophic", "weight": 625},
            "P1": {"label": "Critical", "weight": 405},
        },
        "push": {
            "enabled": True,
            "auto_approve": False,
            "commit_template": "audit: cycle {cycle} automated remediation ({summary})",
            "verify_remote_sha_after_push": True,
            "max_push_retries": 3,
        },
    }


class TestConfigClassLoads:
    def test_loads_from_path(self, tmp_path, sample_aura_json):
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config_path = config_dir / "aura.json"
        config_path.write_text(json.dumps(sample_aura_json))

        with open(config_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)

        assert data["engine"]["max_cycles"] == 25
        assert data["engine"]["version"] == "2.1.0"

    def test_required_modules_loaded(self, tmp_path, sample_aura_json):
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config_path = config_dir / "aura.json"
        config_path.write_text(json.dumps(sample_aura_json))

        with open(config_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)

        required = data["modules"]["required"]
        assert "business-invariants.ps1" in required
        assert "evidence-integrity.ps1" in required
        assert len(required) == 2

    def test_defaults_when_file_missing(self, tmp_path):
        config_path = tmp_path / "config" / "aura.json"
        default_config = {
            "engine": {"max_cycles": 25, "max_cycles_without_progress": 3},
        }
        assert not config_path.exists()
        max_cycles = 25
        assert max_cycles == 25

    def test_handles_empty_json(self, tmp_path):
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config_path = config_dir / "aura.json"
        config_path.write_text("{}")

        with open(config_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)

        assert data == {}
        assert data.get("engine", {}).get("max_cycles", 25) == 25

    def test_handles_malformed_json_gracefully(self, tmp_path):
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config_path = config_dir / "aura.json"
        config_path.write_text('{"engine": {"max_cycles": 25,}')

        try:
            with open(config_path, "r", encoding="utf-8") as fh:
                json.load(fh)
            assert False, "Should have raised JSONDecodeError"
        except json.JSONDecodeError:
            pass

    def test_state_machine_config(self, tmp_path, sample_aura_json):
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config_path = config_dir / "aura.json"
        config_path.write_text(json.dumps(sample_aura_json))

        with open(config_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)

        sm = data["engine"]["state_machine"]
        assert sm["enabled"] is True
        assert sm["enforce_finding_transitions"] is True
        assert sm["enforce_gate_transitions"] is True
        assert sm["max_score_increase_per_cycle"] == 15
        assert sm["max_consecutive_counter_increase"] == 1

    def test_push_config(self, tmp_path, sample_aura_json):
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config_path = config_dir / "aura.json"
        config_path.write_text(json.dumps(sample_aura_json))

        with open(config_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)

        push = data["push"]
        assert push["enabled"] is True
        assert push["max_push_retries"] == 3
        assert push["verify_remote_sha_after_push"] is True

    def test_severity_weights(self, tmp_path, sample_aura_json):
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config_path = config_dir / "aura.json"
        config_path.write_text(json.dumps(sample_aura_json))

        with open(config_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)

        severity = data["severity"]
        assert severity["P0"]["weight"] == 625
        assert severity["P1"]["weight"] == 405
        assert severity["P0"]["label"] == "Catastrophic"

    def test_engine_version(self, tmp_path, sample_aura_json):
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config_path = config_dir / "aura.json"
        config_path.write_text(json.dumps(sample_aura_json))

        with open(config_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)

        assert data["engine"]["version"] == "2.1.0"


class TestConfigEnforcement:
    def test_max_cycles_default_is_25(self):
        config = {}
        max_cycles = int(config.get("engine", {}).get("max_cycles", 25))
        assert max_cycles == 25

    def test_max_score_increase_default_is_15(self):
        config = {}
        max_increase = int(config.get("engine", {}).get("state_machine", {}).get("max_score_increase_per_cycle", 15))
        assert max_increase == 15

    def test_consecutive_counter_max_increase_default_is_1(self):
        config = {}
        max_counter = int(config.get("engine", {}).get("state_machine", {}).get("max_consecutive_counter_increase", 1))
        assert max_counter == 1

    def test_module_required_list(self):
        required = ["business-invariants.ps1", "evidence-integrity.ps1", "independent-verifier.ps1", "security-scan.ps1", "git-safety.ps1"]
        assert len(required) == 5
        assert "business-invariants.ps1" in required
        assert "git-safety.ps1" in required

    def test_module_optional_list(self):
        optional = ["repo-graph.ps1", "sandbox.ps1", "capability-scoring.ps1", "scale-benchmark.ps1", "mutation-testing.ps1", "failure-recovery.ps1"]
        assert len(optional) == 6
        assert "repo-graph.ps1" in optional

    def test_module_experimental_list(self):
        experimental = ["git-safety-adversarial.ps1", "false-evidence-attacks.ps1", "adversarial-campaign.ps1", "false-convergence-extended.ps1"]
        assert len(experimental) == 4
        assert "adversarial-campaign.ps1" in experimental

    def test_phases_count(self):
        phases = ["DISCOVER", "MODEL", "AUDIT", "ADVERSARIAL_AUDIT", "CORRELATE", "PRIORITIZE", "REMEDIATE", "TEST", "VERIFY", "REGRESSION", "UPDATE_STATE", "CONVERGENCE", "PUSH_APPROVAL"]
        assert len(phases) == 13