import json
import os
import shutil
import sys
import time
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

if sys.platform == "win32":
    import msvcrt
else:
    import fcntl


@contextmanager
def file_lock(lock_path: str, timeout: float = 30.0):
    """Advisory file lock for concurrency-safe state operations."""
    lock_file = None
    deadline = time.monotonic() + timeout
    try:
        lock_file = open(lock_path, "w")
        while True:
            try:
                if sys.platform == "win32":
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except (IOError, OSError):
                if time.monotonic() >= deadline:
                    raise TimeoutError("Could not acquire state file lock within {}s".format(timeout))
                time.sleep(0.05)
        yield
    finally:
        if lock_file is not None:
            try:
                if sys.platform == "win32":
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
            except Exception:
                pass
            lock_file.close()


def safe_int(value: Any, fallback: int = 0) -> int:
    if value is None:
        return fallback
    try:
        return int(value)
    except (ValueError, TypeError):
        return fallback


def sanitize_prompt_string(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    sanitized = ""
    for ch in text:
        cp = ord(ch)
        if cp in range(0x00, 0x09) or cp in range(0x0B, 0x0D) or cp in range(0x0E, 0x20) or cp == 0x7F:
            continue
        if cp in range(0x202A, 0x202F) or cp in range(0x2066, 0x206A):
            continue
        sanitized += ch
    sanitized = sanitized.replace("`", "'")
    if len(sanitized) > 4000:
        sanitized = sanitized[:4000]
        if sanitized and ord(sanitized[-1]) in range(0xD800, 0xDC00):
            sanitized = sanitized[:-1]
        elif sanitized and ord(sanitized[-1]) in range(0xDC00, 0xE000):
            sanitized = sanitized[:-1]
        sanitized += "\n... [TRUNCATED]"
    return sanitized


def write_text_file(path: str, content: str):
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")


def write_json_file(path: str, data: Any):
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = file_path.parent / f"{file_path.name}.tmp.{uuid.uuid4().hex[:8]}"
    try:
        json_text = json.dumps(data, indent=2, ensure_ascii=False, default=str)
        temp_path.write_text(json_text, encoding="utf-8")
        shutil.move(str(temp_path), str(file_path))
    except Exception:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)
        raise


def read_json_file(path: str) -> Optional[Any]:
    file_path = Path(path)
    if not file_path.exists():
        return None
    try:
        raw = file_path.read_text(encoding="utf-8")
        if not raw.strip():
            return None
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def read_text_file(path: str) -> Optional[str]:
    file_path = Path(path)
    if not file_path.exists():
        return None
    return file_path.read_text(encoding="utf-8")


class StateManager:
    def __init__(self, engine_root: str):
        self.engine_root = Path(engine_root)
        self.state_dir = self.engine_root / "state"
        self.reports_dir = self.engine_root / "reports"
        self.cycle_file = self.state_dir / "cycle.json"
        self.findings_file = self.state_dir / "findings.json"
        self.convergence_file = self.state_dir / "convergence.json"
        self.proposed_cycle_file = self.state_dir / "proposed-cycle.json"
        self.proposed_findings_file = self.state_dir / "proposed-findings.json"
        self.proposed_convergence_file = self.state_dir / "proposed-convergence.json"
        self.tooling_evidence_file = self.state_dir / "tooling-evidence.json"
        self._lock_file = self.state_dir / ".state.lock"
        self._timeout = 30.0

    def ensure_dirs(self):
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.reports_dir.mkdir(parents=True, exist_ok=True)

    def read_cycle(self) -> Optional[dict]:
        return read_json_file(str(self.cycle_file))

    def read_findings(self) -> Optional[dict]:
        return read_json_file(str(self.findings_file))

    def read_convergence(self) -> Optional[dict]:
        return read_json_file(str(self.convergence_file))

    def read_proposed_cycle(self) -> Optional[dict]:
        return read_json_file(str(self.proposed_cycle_file))

    def read_proposed_findings(self) -> Optional[dict]:
        return read_json_file(str(self.proposed_findings_file))

    def read_proposed_convergence(self) -> Optional[dict]:
        return read_json_file(str(self.proposed_convergence_file))

    def read_tooling_evidence(self) -> Optional[dict]:
        return read_json_file(str(self.tooling_evidence_file))

    def write_cycle(self, data: dict):
        with file_lock(str(self._lock_file), self._timeout):
            write_json_file(str(self.cycle_file), data)

    def write_findings(self, data: dict):
        with file_lock(str(self._lock_file), self._timeout):
            write_json_file(str(self.findings_file), data)

    def write_convergence(self, data: dict):
        with file_lock(str(self._lock_file), self._timeout):
            write_json_file(str(self.convergence_file), data)

    def write_proposed_cycle(self, data: dict):
        with file_lock(str(self._lock_file), self._timeout):
            write_json_file(str(self.proposed_cycle_file), data)

    def write_proposed_findings(self, data: dict):
        with file_lock(str(self._lock_file), self._timeout):
            write_json_file(str(self.proposed_findings_file), data)

    def write_proposed_convergence(self, data: dict):
        with file_lock(str(self._lock_file), self._timeout):
            write_json_file(str(self.proposed_convergence_file), data)

    def write_tooling_evidence(self, data: dict):
        with file_lock(str(self._lock_file), self._timeout):
            write_json_file(str(self.tooling_evidence_file), data)

    def has_proposed_files(self) -> bool:
        return any([
            self.proposed_findings_file.exists(),
            self.proposed_convergence_file.exists(),
            self.proposed_cycle_file.exists(),
        ])

    def get_proposed_files_list(self) -> List[str]:
        found = []
        if self.proposed_findings_file.exists():
            found.append(str(self.proposed_findings_file))
        if self.proposed_convergence_file.exists():
            found.append(str(self.proposed_convergence_file))
        if self.proposed_cycle_file.exists():
            found.append(str(self.proposed_cycle_file))
        return found

    def initialize_state(self, module_integrity_pass: bool = False,
                         mod_required_failures: Optional[List[str]] = None,
                         mod_optional_failures: Optional[List[str]] = None,
                         mod_experimental_failures: Optional[List[str]] = None,
                         mod_load_count: int = 0,
                         mod_total_expected: int = 0):
        now = datetime.now().isoformat()
        cycle_data = {
            "engine_name": "Continuous Autonomous Engineering Audit Engine",
            "version": "2.1.2",
            "started_at": now,
            "current_cycle": 0,
            "current_phase": "INIT",
            "status": "RUNNING",
            "classification": "NOT_READY",
            "cycles_completed": 0,
            "cycles_without_progress": 0,
            "consecutive_converged_cycles": 0,
            "last_change_hash": None,
        }
        self.write_cycle(cycle_data)

        findings_data = {"findings": [], "next_id": 1}
        self.write_findings(findings_data)

        conv_data = {
            "cycle": 0,
            "converged": False,
            "consecutive_converged_cycles": 0,
            "audits_since_last_finding": 0,
            "gates": {
                "P0_zero": False, "P1_zero": False, "P2_zero": False,
                "critical_security": False, "critical_correctness": False,
                "data_integrity": False, "regression": False, "verification": False,
                "no_material_new_findings": False, "limitations_documented": False,
                "consecutive_clean_independent_audits": False,
                "module_dependency_integrity": module_integrity_pass,
            },
            "module_status": {
                "integrity_pass": module_integrity_pass,
                "required_failures": mod_required_failures or [],
                "optional_failures": mod_optional_failures or [],
                "experimental_failures": mod_experimental_failures or [],
                "total_loaded": mod_load_count,
                "total_expected": mod_total_expected,
            },
            "classification": "NOT_READY",
            "reason": "Cycle 0 - not yet started.",
        }
        self.write_convergence(conv_data)

    def reset_engine(self):
        archive_dir = self.engine_root / "archive" / datetime.now().strftime("%Y%m%d_%H%M%S")
        archive_dir.mkdir(parents=True, exist_ok=True)

        if self.state_dir.exists():
            for f in self.state_dir.iterdir():
                if f.is_file():
                    shutil.copy2(str(f), str(archive_dir / f.name))

        if self.reports_dir.exists():
            for f in self.reports_dir.iterdir():
                if f.is_file():
                    shutil.copy2(str(f), str(archive_dir / f.name))

        analytics_db_path = self.state_dir / "analytics.db"
        if analytics_db_path.exists():
            shutil.copy2(str(analytics_db_path), str(archive_dir / "analytics.db"))
            analytics_db_path.unlink()

        env_file = self.engine_root / "last-cycle.env"
        if env_file.exists():
            shutil.copy2(str(env_file), str(archive_dir / "last-cycle.env"))
            env_file.unlink()

        prompt_file = self.engine_root / "generated-cycle-prompt.md"
        if prompt_file.exists():
            shutil.copy2(str(prompt_file), str(archive_dir / "generated-cycle-prompt.md"))
            prompt_file.unlink()

        proposed_files = [
            self.proposed_findings_file, self.proposed_convergence_file,
            self.proposed_cycle_file, self.tooling_evidence_file,
        ]
        for pf in proposed_files:
            if pf.exists():
                shutil.copy2(str(pf), str(archive_dir / pf.name))
                pf.unlink()

        self.initialize_state()

        ledger_template = "# Audit Ledger\n\n"
        ledger_template += "| Cycle | Started | Classification | Score | Confidence | P0 | P1 | P2 | P3 | P4 | P5 | Total Open | Converged |\n"
        ledger_template += "|-------|---------|---------------|-------|------------|----|----|----|----|----|----|------------|-----------|\n"
        ledger_template += "| - | - | - | - | - | - | - | - | - | - | - | - | - |\n\n"
        ledger_template += "---\n## Finding History\n*No findings yet.*\n"
        write_text_file(str(self.reports_dir / "audit-ledger.md"), ledger_template)
        write_text_file(str(self.reports_dir / "architecture-map.md"), "# Architecture Map\n\n*Not yet modeled.*")
        write_text_file(str(self.reports_dir / "risk-register.md"), "# Risk Register\n\n*No risks recorded.*")
        write_text_file(str(self.reports_dir / "verification-matrix.md"), "# Verification Matrix\n\n*No runs yet.*")
        write_text_file(str(self.reports_dir / "remediation-log.md"), "# Remediation Log\n\n*No remediations yet.*")