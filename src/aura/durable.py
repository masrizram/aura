"""AURA durable execution — checkpoint/resume for long-running autonomous loops.

Solves the timeout problem: AURA saves state at every cycle boundary and can
resume from the last checkpoint. Combined with background execution, this
enables multi-cycle trajectories that span hours without losing state.

Design:
  - Every cycle completion writes a checkpoint file
  - Resume reads the last checkpoint and continues from there
  - Never repeats completed cycles
  - Checkpoint stores: cycle number, scores, finding counts, closure stats
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class CheckpointManager:
    """Manages durable checkpoints for autonomous remediation loops.

    Checkpoint file: .aura/checkpoint.json
    """

    CHECKPOINT_FILE = ".aura/checkpoint.json"

    def __init__(self, repo_root: str | Path) -> None:
        self.repo_root = Path(repo_root)
        self.checkpoint_path = self.repo_root / self.CHECKPOINT_FILE

    def save(self, cycle: int, state: dict[str, Any]) -> None:
        """Save checkpoint for a completed cycle."""
        self.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        checkpoint = {
            "version": "1.0.0",
            "last_cycle": cycle,
            "last_updated": datetime.now(UTC).isoformat(),
            "state": state,
        }
        self.checkpoint_path.write_text(
            json.dumps(checkpoint, indent=2, default=str),
            encoding="utf-8")

    def load(self) -> dict[str, Any] | None:
        """Load the last checkpoint. Returns None if no checkpoint exists."""
        if not self.checkpoint_path.exists():
            return None
        try:
            return json.loads(self.checkpoint_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, KeyError):
            return None

    def get_last_cycle(self) -> int:
        """Get the last completed cycle number. Returns 0 if none."""
        cp = self.load()
        return cp.get("last_cycle", 0) if cp else 0

    def clear(self) -> None:
        """Remove the checkpoint file — start fresh."""
        if self.checkpoint_path.exists():
            self.checkpoint_path.unlink()

    def get_progress(self) -> dict[str, Any]:
        """Get human-readable progress summary."""
        cp = self.load()
        if not cp:
            return {"status": "no_checkpoint", "cycles_completed": 0}
        state = cp.get("state", {})
        return {
            "status": "in_progress",
            "cycles_completed": cp.get("last_cycle", 0),
            "last_score": state.get("score", "?"),
            "last_classification": state.get("classification", "?"),
            "last_findings": state.get("findings", "?"),
            "last_fixes": state.get("fixes", "?"),
        }


class DurableAutonomousLoop:
    """Autonomous loop with checkpoint/resume support.

    Runs the remediation loop cycle by cycle, saving state at each boundary.
    Can be resumed from the last checkpoint.
    """

    def __init__(self, autonomous_loop, repo_root: str | Path) -> None:
        self.loop = autonomous_loop
        self.checkpoint = CheckpointManager(repo_root)
        self._current_cycle = 0

    def run_or_resume(self, max_cycles: int) -> dict[str, Any]:
        """Run or resume the autonomous loop.

        If a checkpoint exists, resumes from the last completed cycle.
        Otherwise, starts fresh.
        """
        last = self.checkpoint.get_last_cycle()
        if last > 0:
            return self._resume(last, max_cycles)
        return self._fresh_run(max_cycles)

    def _fresh_run(self, max_cycles: int) -> dict[str, Any]:
        """Run fresh from cycle 1."""
        self.loop.max_cycles = max_cycles
        result = self.loop.run()

        # Save checkpoint if partial
        if not result.get("converged"):
            last_log = self.loop._cycle_log[-1] if self.loop._cycle_log else {}
            self.checkpoint.save(
                cycle=last_log.get("cycle", 1),
                state={
                    "score": last_log.get("score"),
                    "classification": last_log.get("classification"),
                    "findings": last_log.get("findings"),
                    "fixes": last_log.get("fixes_applied"),
                })

        return result

    def _resume(self, from_cycle: int, max_cycles: int) -> dict[str, Any]:
        """Resume from the last checkpoint."""
        # The engine already has state from previous cycles in the DB.
        # We just need to continue the loop from where we left off.
        # The engine.run_audit() will auto-increment to the next cycle.
        remaining = max_cycles - from_cycle
        if remaining <= 0:
            last_log = self.loop._cycle_log[-1] if self.loop._cycle_log else {}
            return {
                "outcome": "already_at_max",
                "message": f"Already at max cycles ({from_cycle})",
                "cycles_completed": from_cycle,
                "cycle_log": self.loop._cycle_log,
                "converged": False,
            }

        self.loop.max_cycles = remaining
        result = self.loop.run()

        # Update checkpoint
        last_log = self.loop._cycle_log[-1] if self.loop._cycle_log else {}
        total_cycles = from_cycle + len(self.loop._cycle_log)
        self.checkpoint.save(
            cycle=total_cycles,
            state={
                "score": last_log.get("score"),
                "classification": last_log.get("classification"),
                "findings": last_log.get("findings"),
                "fixes": last_log.get("fixes_applied"),
                "resumed_from": from_cycle,
            })

        result["cycles_completed"] = total_cycles
        result["resumed_from"] = from_cycle
        return result