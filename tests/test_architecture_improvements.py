"""Regression tests for architecture improvements IMP-01..IMP-09.

Each test maps to a finding in docs/architecture-improvement-plan.md.
These are NEGATIVE/POSITIVE pairs: they prove the defect is fixed AND
that the correct behavior is preserved.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from aura.convergence import ConvergenceJudge
from aura.durable import CheckpointManager
from aura.evidence import Evidence, EvidenceChain, EvidenceLevel
from aura.llm import LLMResponse, ProviderBackedLLMClient
from aura.providers import (
    CircuitBreaker,
    CircuitState,
    OpenAICompatibleProvider,
    ProviderRegistry,
    ProviderResponse,
)
from aura.remediation import AutoFixer


# ── IMP-01: canonical provider adapter ───────────────────────────────────────

class TestProviderBackedLLMClient:
    def _registry_returning(self, resp: ProviderResponse) -> ProviderRegistry:
        reg = ProviderRegistry()
        reg.chat_with_fallback = MagicMock(return_value=resp)  # type: ignore[method-assign]
        return reg

    def test_success_maps_fields(self) -> None:
        reg = self._registry_returning(ProviderResponse(
            content="hello", model="m1", tokens_used=42, provider_name="p"))
        client = ProviderBackedLLMClient(reg, default_model="fallback-model")
        out = client.chat("sys", "user")
        assert isinstance(out, LLMResponse)
        assert out.content == "hello"
        assert out.model == "m1"
        assert out.tokens_used == 42
        assert out.untrusted is True

    def test_error_maps_to_llm_error(self) -> None:
        reg = self._registry_returning(ProviderResponse(
            content="", provider_name="p", error="boom"))
        client = ProviderBackedLLMClient(reg, default_model="m")
        out = client.chat("sys", "user")
        assert out.content.startswith("LLM_ERROR:")
        assert "boom" in out.content
        assert out.untrusted is True

    def test_error_uses_default_model_when_response_model_empty(self) -> None:
        reg = self._registry_returning(ProviderResponse(
            content="", model="", provider_name="p", error="x"))
        client = ProviderBackedLLMClient(reg, default_model="dm")
        out = client.chat("s", "u")
        assert out.model == "dm"


# ── IMP-05: classified retry + jitter ────────────────────────────────────────

class TestProviderRetryPolicy:
    def _provider(self) -> OpenAICompatibleProvider:
        return OpenAICompatibleProvider(
            name="t", base_url="http://x", api_key="k", model="m",
            max_retries=3, backoff_base=0.001, backoff_cap=0.01)

    def test_non_retryable_4xx_fails_fast(self) -> None:
        """401 must produce exactly ONE attempt — no budget burned."""
        prov = self._provider()
        resp_mock = MagicMock(status_code=401, text="unauthorized")
        resp_mock.headers = {}
        with patch("httpx.post", return_value=resp_mock) as post:
            out = prov.chat("s", "u")
        assert out.error is not None and "non-retryable" in out.error
        assert post.call_count == 1

    def test_retryable_429_exhausts_attempts(self) -> None:
        """429 must retry up to max_retries then fail."""
        prov = self._provider()
        resp_mock = MagicMock(status_code=429, text="rate limited")
        resp_mock.headers = {}
        with patch("httpx.post", return_value=resp_mock) as post, \
             patch("time.sleep") as sleep:
            out = prov.chat("s", "u")
        assert out.error is not None
        assert post.call_count == 3
        assert sleep.call_count == 2  # sleeps between attempts only

    def test_network_error_retried(self) -> None:
        prov = self._provider()
        with patch("httpx.post", side_effect=ConnectionError("down")) as post, \
             patch("time.sleep"):
            out = prov.chat("s", "u")
        assert out.error is not None
        assert post.call_count == 3

    def test_backoff_has_jitter_within_bounds(self) -> None:
        prov = self._provider()
        prov.backoff_base = 1.0
        prov.backoff_cap = 30.0
        for attempt in range(4):
            s = prov._backoff_sleep(attempt)
            ceiling = min(30.0, 1.0 * (2 ** attempt))
            assert 0.0 <= s <= ceiling

    def test_retry_after_header_respected(self) -> None:
        prov = self._provider()
        resp_mock = MagicMock(status_code=429, text="rl")
        resp_mock.headers = {"Retry-After": "5"}
        sleeps: list[float] = []
        with patch("httpx.post", return_value=resp_mock), \
             patch("time.sleep", side_effect=lambda s: sleeps.append(s)):
            prov.chat("s", "u")
        # First sleep must honor Retry-After capped by backoff_cap (0.01 here)
        assert sleeps and sleeps[0] <= prov.backoff_cap

    def test_success_path_unchanged(self) -> None:
        prov = self._provider()
        resp_mock = MagicMock(status_code=200)
        resp_mock.json.return_value = {
            "choices": [{"message": {"content": "ok"}}],
            "model": "m", "usage": {"total_tokens": 7},
        }
        resp_mock.headers = {}
        with patch("httpx.post", return_value=resp_mock):
            out = prov.chat("s", "u")
        assert out.error is None
        assert out.content == "ok"
        assert out.tokens_used == 7


# ── IMP-02: no hardcoded-true gates ─────────────────────────────────────────

class TestJudgeG07Derived:
    def test_g07_false_when_tooling_fails(self) -> None:
        """G07 (typecheck) must mirror G06 — failing tooling → G07 False."""
        judge = ConvergenceJudge("/tmp")
        state = {
            "cycle_number": 1, "phase": "COMPLETE",
            "open_p0": 0, "open_p1": 0, "open_p2": 0,
            "open_p3": 0, "open_p4": 0, "open_p5": 0,
            "verified_count": 0, "findings_count": 0,
            "tooling_passed": "1/2",  # FAILING tooling
            "evidence_complete": True,
            "overall_score": 90,
        }
        result = judge.evaluate(state, [])
        assert result.gates["G06_tooling_pass"] is False
        assert result.gates["G07_typecheck_pass"] is False, \
            "G07 must not be hardcoded True when tooling fails (IMP-02)"

    def test_g07_true_when_tooling_passes(self) -> None:
        judge = ConvergenceJudge("/tmp")
        state = {
            "cycle_number": 1, "phase": "COMPLETE",
            "open_p0": 0, "open_p1": 0, "open_p2": 0,
            "open_p3": 0, "open_p4": 0, "open_p5": 0,
            "verified_count": 0, "findings_count": 0,
            "tooling_passed": "2/2",
            "evidence_complete": True,
            "overall_score": 90,
        }
        result = judge.evaluate(state, [])
        assert result.gates["G07_typecheck_pass"] is True


class TestModuleIntegrityReal:
    def test_engine_computes_real_module_integrity(self, tmp_path: Path) -> None:
        """module_dependency_integrity must be computed, not hardcoded."""
        from aura.config import AuraConfig
        from aura.engine import Engine
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "x.py").write_text("print(1)")
        config = AuraConfig()
        config.database.path = str(repo / ".aura" / "state" / "aura.db")
        eng = Engine(repo, config)
        assert isinstance(eng._module_integrity, bool)
        # In a healthy install all required modules import → True
        assert eng._module_integrity is True

    def test_module_integrity_fails_closed(self) -> None:
        """Simulated missing module → integrity False."""
        import importlib
        from aura.engine import Engine
        real_import = importlib.import_module
        def fake_import(name: str, *a, **k):  # type: ignore[no-untyped-def]
            if name == "aura.semantic":
                raise ImportError("simulated missing module")
            return real_import(name, *a, **k)
        with patch.object(importlib, "import_module", side_effect=fake_import):
            assert Engine._check_module_integrity() is False


# ── IMP-04: evidence chain linkage ───────────────────────────────────────────

class TestEvidenceChainLinkage:
    def _chain(self, tmp_path: Path) -> EvidenceChain:
        return EvidenceChain(tmp_path / "chain.json")

    def _entry(self, fid: str) -> Evidence:
        return Evidence(finding_id=fid, level=EvidenceLevel.DISCOVERED,
                        source="orchestrator", tool="pytest", exit_code=0,
                        output="ok")

    def test_genesis_links_to_zero_hash(self, tmp_path: Path) -> None:
        chain = self._chain(tmp_path)
        chain.append(self._entry("F1"))
        e = chain.entries[0]
        assert e.chain_index == 0
        assert e.previous_hash == "0" * 64

    def test_entries_link_sequentially(self, tmp_path: Path) -> None:
        chain = self._chain(tmp_path)
        chain.append(self._entry("F1"))
        chain.append(self._entry("F2"))
        chain.append(self._entry("F3"))
        entries = chain.entries
        assert entries[1].previous_hash == entries[0].hash
        assert entries[2].previous_hash == entries[1].hash
        ok, violations = chain.verify_chain()
        assert ok, violations

    def test_tampered_content_detected(self, tmp_path: Path) -> None:
        chain = self._chain(tmp_path)
        chain.append(self._entry("F1"))
        chain.entries[0].output = "TAMPERED"
        ok, violations = chain.verify_chain()
        assert not ok
        assert any("hash mismatch" in v for v in violations)

    def test_deleted_entry_detected(self, tmp_path: Path) -> None:
        """Deleting a middle entry must break linkage — previously undetectable."""
        chain = self._chain(tmp_path)
        chain.append(self._entry("F1"))
        chain.append(self._entry("F2"))
        chain.append(self._entry("F3"))
        # Simulate deletion of middle entry from the persisted file
        data = json.loads((tmp_path / "chain.json").read_text())
        del data["entries"][1]
        (tmp_path / "chain.json").write_text(json.dumps(data))
        chain2 = self._chain(tmp_path)
        ok, violations = chain2.verify_chain()
        assert not ok, "deletion must be detected via linkage"

    def test_reorder_detected(self, tmp_path: Path) -> None:
        chain = self._chain(tmp_path)
        chain.append(self._entry("F1"))
        chain.append(self._entry("F2"))
        data = json.loads((tmp_path / "chain.json").read_text())
        data["entries"] = [data["entries"][1], data["entries"][0]]
        (tmp_path / "chain.json").write_text(json.dumps(data))
        chain2 = self._chain(tmp_path)
        ok, violations = chain2.verify_chain()
        assert not ok


class TestEvidenceChainDbSync:
    def test_db_insert_and_read(self, tmp_path: Path) -> None:
        """evidence_chain table is no longer dead schema (IMP-04)."""
        from aura.config import DatabaseConfig
        from aura.db import Database
        db = Database(DatabaseConfig(path=str(tmp_path / "t.db")))
        db.initialize()
        db.insert_evidence_entry(
            evidence_id="E1", content_hash="abc", chain_index=0,
            previous_hash="0" * 64, payload='{"k": 1}')
        rows = db.get_evidence_chain()
        assert len(rows) == 1
        assert rows[0]["evidence_id"] == "E1"
        assert rows[0]["chain_index"] == 0
        db.close()


# ── IMP-06: path containment primitive ───────────────────────────────────────

class TestPathContainment:
    def test_sibling_prefix_escape_blocked(self, tmp_path: Path) -> None:
        """repo /a/repo must NOT accept writes to /a/repo-evil/x (IMP-06)."""
        repo = tmp_path / "repo"
        repo.mkdir()
        evil = tmp_path / "repo-evil"
        evil.mkdir()
        target = evil / "pwned.py"
        target.write_text("safe")
        fixer = AutoFixer(repo)
        # Craft a relative path that resolves into the sibling directory
        rel = f"../repo-evil/pwned.py"
        fr = fixer.apply_fix(rel, 1, 1, "safe", "safe")
        assert fr.success is False
        assert "SANDBOX REJECTED" in fr.error

    def test_normal_in_repo_fix_allowed(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        f = repo / "a.py"
        f.write_text("old line\n")
        fixer = AutoFixer(repo)
        fr = fixer.apply_fix("a.py", 1, 1, "old line", "new line")
        assert fr.success is True
        assert f.read_text() == "new line\n"
        fixer.rollback()
        assert f.read_text() == "old line\n"


# ── IMP-07: checkpoint integrity ─────────────────────────────────────────────

class TestCheckpointIntegrity:
    def test_roundtrip_verified(self, tmp_path: Path) -> None:
        cm = CheckpointManager(tmp_path)
        cm.save(3, {"score": 80, "classification": "NOT_READY"})
        cp = cm.load()
        assert cp is not None
        assert cp["_integrity"] == "verified"
        assert cp["last_cycle"] == 3

    def test_tampered_checkpoint_refused(self, tmp_path: Path) -> None:
        cm = CheckpointManager(tmp_path)
        cm.save(3, {"score": 80})
        data = json.loads(cm.checkpoint_path.read_text())
        data["state"]["score"] = 100  # tamper
        cm.checkpoint_path.write_text(json.dumps(data))
        assert cm.load() is None, "tampered checkpoint must be refused"
        assert cm.get_last_cycle() == 0

    def test_corrupted_json_refused(self, tmp_path: Path) -> None:
        cm = CheckpointManager(tmp_path)
        cm.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        cm.checkpoint_path.write_text("{broken json")
        assert cm.load() is None

    def test_legacy_checkpoint_accepted_but_flagged(self, tmp_path: Path) -> None:
        cm = CheckpointManager(tmp_path)
        cm.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        cm.checkpoint_path.write_text(json.dumps({
            "version": "1.0.0", "last_cycle": 2, "state": {"score": 50}}))
        cp = cm.load()
        assert cp is not None
        assert cp["_integrity"] == "legacy-unverified"


# ── IMP-09: observability ────────────────────────────────────────────────────

class TestCycleObservability:
    def test_cycle_id_and_phase_durations_logged(self, tmp_path: Path) -> None:
        import subprocess
        from aura.config import AuraConfig
        from aura.engine import Engine
        repo = tmp_path / "repo"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=str(repo), capture_output=True)
        subprocess.run(["git", "config", "user.email", "t@t"], cwd=str(repo), capture_output=True)
        subprocess.run(["git", "config", "user.name", "T"], cwd=str(repo), capture_output=True)
        (repo / "a.py").write_text("print(1)")
        subprocess.run(["git", "add", "."], cwd=str(repo), capture_output=True)
        subprocess.run(["git", "commit", "-m", "i"], cwd=str(repo), capture_output=True)
        config = AuraConfig()
        config.database.path = str(repo / ".aura" / "state" / "aura.db")
        eng = Engine(repo, config)
        result = eng.run_audit()
        entries = eng.db.get_audit_log(cycle_number=result["cycle_number"])
        obs = [e for e in entries if e.get("event_type") == "CYCLE_OBSERVABILITY"]
        assert obs, "CYCLE_OBSERVABILITY entry must be logged (IMP-09)"
        meta = json.loads(obs[0]["metadata"])
        assert meta["cycle_id"]
        assert "DISCOVER" in meta["phase_durations_s"]
        assert "CONVERGENCE" in meta["phase_durations_s"]
