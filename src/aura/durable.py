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
        """Save checkpoint for a completed cycle.

        Includes a SHA-256 integrity hash over the canonical state payload
        so corruption or hand-editing is detected on load (IMP-07).
        """
        self.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        state_hash = self._hash_state(state)
        checkpoint = {
            "version": "1.1.0",
            "last_cycle": cycle,
            "last_updated": datetime.now(UTC).isoformat(),
            "state": state,
            "state_hash": state_hash,
        }
        self.checkpoint_path.write_text(
            json.dumps(checkpoint, indent=2, default=str),
            encoding="utf-8")

    @staticmethod
    def _hash_state(state: dict[str, Any]) -> str:
        import hashlib
        canonical = json.dumps(state, sort_keys=True, default=str)
        return hashlib.sha256(canonical.encode()).hexdigest()

    def load(self) -> dict[str, Any] | None:
        """Load the last checkpoint. Returns None if missing or corrupt.

        Integrity check (IMP-07): if the file carries a state_hash, it must
        match the recomputed hash of `state`. Legacy checkpoints (version
        1.0.0, no hash) are accepted but flagged via `_integrity` key.
        """
        if not self.checkpoint_path.exists():
            return None
        try:
            cp = json.loads(self.checkpoint_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        if not isinstance(cp, dict) or "state" not in cp:
            return None
        stored_hash = cp.get("state_hash")
        if stored_hash is not None:
            if stored_hash != self._hash_state(cp["state"]):
                # Corrupted or tampered checkpoint — refuse to resume
                return None
            cp["_integrity"] = "verified"
        else:
            cp["_integrity"] = "legacy-unverified"
        return cp

    def get_last_cycle(self) -> int:
        """Get the last completed cycle number. Returns 0 if none."""
        cp = self.load()
        return int(cp.get("last_cycle", 0)) if cp else 0

    def clear(self) -> None:
        """Remove the checkpoint file — start fresh."""
        if self.checkpoint_path.exists():
            self.checkpoint_path.unlink()

    def get_progress(self) -> dict[str, Any]:
        """Get human-readable progress summary."""
        cp = self.load()
        if not cp:
            return {"status": "no_checkpoint", "cycles_completed": 0}
        state: dict[str, Any] = cp.get("state", {})
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

    def __init__(self, autonomous_loop: Any, repo_root: str | Path) -> None:
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
        result: dict[str, Any] = self.loop.run()

        # Save checkpoint if partial — include loop-safeguard state (R2-06)
        if not result.get("converged"):
            last_log = self.loop._cycle_log[-1] if self.loop._cycle_log else {}
            self.checkpoint.save(
                cycle=last_log.get("cycle", 1),
                state={
                    "score": last_log.get("score"),
                    "classification": last_log.get("classification"),
                    "findings": last_log.get("findings"),
                    "fixes": last_log.get("fixes_applied"),
                    "safeguard": self._snapshot_safeguard(),
                })

        return result

    def _snapshot_safeguard(self) -> dict[str, Any]:
        """Capture LoopSafeguard counters so resume restores them (R2-06)."""
        sg = getattr(self.loop, "_safeguard", None)
        if sg is None:
            return {}
        return {
            "iteration": getattr(sg, "iteration", 0),
            "scores": list(getattr(sg, "scores", [])),
            "finding_counts": list(getattr(sg, "finding_counts", [])),
            "finding_attempts": dict(getattr(sg, "finding_attempts", {})),
        }

    def _restore_safeguard(self, state: dict[str, Any]) -> None:
        """Restore LoopSafeguard counters from checkpoint state (R2-06).

        Without this, resuming resets MAX_SAME_FINDING_ATTEMPTS and
        NO_PROGRESS_CYCLES to zero, defeating the safeguards.
        """
        sg = getattr(self.loop, "_safeguard", None)
        snap = state.get("safeguard") or {}
        if sg is None or not snap:
            return
        sg.iteration = int(snap.get("iteration", sg.iteration))
        sg.scores = list(snap.get("scores", sg.scores))
        sg.finding_counts = list(snap.get("finding_counts", sg.finding_counts))
        sg.finding_attempts = dict(snap.get("finding_attempts", sg.finding_attempts))

    def _resume(self, from_cycle: int, max_cycles: int) -> dict[str, Any]:
        """Resume from the last checkpoint."""
        # The engine already has state from previous cycles in the DB.
        # We just need to continue the loop from where we left off.
        # The engine.run_audit() will auto-increment to the next cycle.
        cp = self.checkpoint.load() or {}
        self._restore_safeguard(cp.get("state", {}))  # R2-06
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
        result: dict[str, Any] = self.loop.run()

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
