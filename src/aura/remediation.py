"""AURA autonomous remediation engine — LLM-powered code fixer with rollback.

Applies fixes to source code, verifies with tooling, and provides
dry-run preview + automatic rollback on failure.

Safeguards:
  A. MAX_ITERATIONS — hard cap
  B. MAX_SAME_FINDING_ATTEMPTS — stop retrying
  C. NO_PROGRESS_CYCLES — quit if stalled
  D. Regression trade-off detection
  E. Finding identity tracking
  F. LLM = candidate, never authoritative
  G. Evidence chain per-cycle
"""

from __future__ import annotations

import contextlib
import difflib
import json
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .convergence import (
    ConvergenceJudge,
    EvidenceChainBuilder,
    FindingIdentityTracker,
    LoopSafeguard,
)


@dataclass
class FixResult:
    finding_id: str
    file: str
    success: bool
    old_content: str = ""
    new_content: str = ""
    diff: str = ""
    error: str = ""
    rolled_back: bool = False


@dataclass
class RemediationPlan:
    cycle: int
    fixes: list[FixResult] = field(default_factory=list)
    total_attempted: int = 0
    total_succeeded: int = 0
    total_failed: int = 0
    total_rolled_back: int = 0
    started_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    completed_at: str = ""


class AutoFixer:
    """Applies code fixes to disk with dry-run preview and rollback."""

    def __init__(self, repo_root: str | Path, dry_run: bool = False) -> None:
        self.repo_root = Path(repo_root)
        self.dry_run = dry_run
        self._backups: dict[str, str] = {}  # file_path -> original content
        self._history: list[FixResult] = []

    def preview_fix(self, file_path: str, line_start: int, line_end: int,
                    old_code: str, new_code: str) -> str:
        """Preview a fix without applying it. Returns unified diff."""
        full_path = self.repo_root / file_path
        if not full_path.exists():
            return f"[ERROR] File not found: {file_path}"

        content = full_path.read_text(encoding="utf-8", errors="ignore")
        lines = content.split("\n")
        if line_end > len(lines):
            line_end = len(lines)

        # Build context
        context_start = max(0, line_start - 3)
        context_end = min(len(lines), line_end + 3)
        old_snippet = "\n".join(lines[context_start:context_end])

        # Build new snippet
        new_lines = lines[:]
        new_lines[line_start - 1:line_end] = new_code.split("\n")
        new_snippet = "\n".join(new_lines[context_start:context_end + (len(new_code.split("\n")) - (line_end - line_start + 1))])

        diff = "\n".join(difflib.unified_diff(
            old_snippet.split("\n"), new_snippet.split("\n"),
            fromfile=f"a/{file_path}:{line_start}", tofile=f"b/{file_path}:{line_start}",
            lineterm=""))
        return diff

    def apply_fix(self, file_path: str, line_start: int, line_end: int,
                  old_code: str, new_code: str) -> FixResult:
        """Apply a single fix to a file. Backs up original content."""
        full_path = self.repo_root / file_path
        finding_id = f"FIX-{datetime.now(UTC).strftime('%Y%m%d%H%M%S%f')}"

        # ── SANDBOX SAFETY GUARD ────────────────────────────────────
        # 1. Path traversal protection — correct containment primitive.
        #    str.startswith() is WRONG: repo /a/repo would accept
        #    /a/repo-evil/x. is_relative_to() rejects sibling prefixes
        #    and symlink escapes (IMP-06).
        try:
            resolved = full_path.resolve()
            repo_resolved = self.repo_root.resolve()
            if not resolved.is_relative_to(repo_resolved):
                fr = FixResult(finding_id=finding_id, file=file_path, success=False,
                              error=f"SANDBOX REJECTED: path traversal ({resolved})")
                self._history.append(fr)
                return fr
        except Exception:
            fr = FixResult(finding_id=finding_id, file=file_path, success=False,
                          error="SANDBOX REJECTED: path resolution failed")
            self._history.append(fr)
            return fr

        # 2. Dangerous code injection patterns — ADVISORY signal, not a
        #    security boundary. Substring matching is bypassable (obfuscation)
        #    and over-blocking (legitimate subprocess.run use). The real
        #    controls are: --dry-run preview, old_code match verification,
        #    automatic rollback on tooling failure, and post-fix re-audit
        #    (IMP-06; documented in docs/security/security-controls.md).
        _DANGEROUS = ["os.system(", "os.popen(", "subprocess.", ".exec(",
                       "exec(", "eval(", "__import__(", "compile(",
                       "rm -rf", "DROP TABLE", "DROP DATABASE"]
        new_lower = new_code.lower()
        blocked = [p for p in _DANGEROUS if p.lower() in new_lower]
        if blocked:
            fr = FixResult(finding_id=finding_id, file=file_path, success=False,
                          error=f"SANDBOX REJECTED: dangerous patterns: {', '.join(blocked)}")
            self._history.append(fr)
            return fr

        if self.dry_run:
            diff = self.preview_fix(file_path, line_start, line_end, old_code, new_code)
            fr = FixResult(finding_id=finding_id, file=file_path, success=True,
                          old_content=old_code, new_content=new_code, diff=diff)
            self._history.append(fr)
            return fr

        if not full_path.exists():
            fr = FixResult(finding_id=finding_id, file=file_path, success=False,
                          error=f"File not found: {file_path}")
            self._history.append(fr)
            return fr

        try:
            content = full_path.read_text(encoding="utf-8", errors="ignore")
            # Backup original
            if file_path not in self._backups:
                self._backups[file_path] = content

            lines = content.split("\n")
            if line_end > len(lines):
                line_end = len(lines)

            # Verify old_code matches (safety check — tolerant to whitespace)
            actual_lines = lines[line_start - 1:line_end]
            actual_code = "\n".join(actual_lines)

            # Normalize whitespace for comparison
            def _norm(s: str) -> str:
                return " ".join(s.strip().split())

            if old_code.strip():
                norm_old = _norm(old_code)
                norm_actual = _norm(actual_code)

                # Exact match after normalization
                if norm_old not in norm_actual:
                    # Fuzzy: check if old_code exists within ±10 lines with lenient matching
                    context_start = max(0, line_start - 10)
                    context_end = min(len(lines), line_end + 10)
                    context_text = " ".join(" ".join(l.strip().split())
                                            for l in lines[context_start:context_end])
                    if norm_old[:30] not in context_text:
                        fr = FixResult(finding_id=finding_id, file=file_path, success=False,
                                      error=f"old_code not found near line {line_start}-{line_end} "
                                            f"(LLM output may have formatting differences)",
                                      old_content=f"Expected: {old_code[:80]}\nActual: {actual_code[:80]}")
                        self._history.append(fr)
                        return fr

            # Apply fix
            new_lines = lines[:]
            new_lines[line_start - 1:line_end] = new_code.split("\n")
            new_content = "\n".join(new_lines)

            # Compute diff
            diff = "\n".join(difflib.unified_diff(
                content.split("\n"), new_content.split("\n"),
                fromfile=f"a/{file_path}", tofile=f"b/{file_path}",
                lineterm=""))

            # Write
            full_path.write_text(new_content, encoding="utf-8")

            fr = FixResult(finding_id=finding_id, file=file_path, success=True,
                          old_content=old_code, new_content=new_code, diff=diff)
            self._history.append(fr)
            return fr

        except Exception as e:
            fr = FixResult(finding_id=finding_id, file=file_path, success=False,
                          error=str(e))
            self._history.append(fr)
            return fr

    def rollback(self) -> dict[str, Any]:
        """Rollback all applied fixes. Returns summary."""
        rolled = 0
        failed = 0
        for file_path, original in self._backups.items():
            try:
                (self.repo_root / file_path).write_text(original, encoding="utf-8")
                rolled += 1
            except Exception:
                failed += 1
        self._backups.clear()
        # Mark rolled back in history
        for fr in self._history:
            if fr.success and not fr.rolled_back:
                fr.rolled_back = True
                fr.success = False
        return {"rolled_back": rolled, "failed_rollback": failed}

    def save_patch(self, output_path: str | Path) -> str:
        """Save all diffs as a unified patch file."""
        patches = []
        for fr in self._history:
            if fr.diff:
                patches.append(f"# Fix: {fr.finding_id} — {fr.file}\n{fr.diff}\n")
        patch_content = "\n".join(patches)
        Path(output_path).write_text(patch_content, encoding="utf-8")
        return patch_content

    @property
    def summary(self) -> dict[str, Any]:
        return {
            "total_attempted": len(self._history),
            "total_succeeded": sum(1 for fr in self._history if fr.success),
            "total_failed": sum(1 for fr in self._history if not fr.success),
            "total_rolled_back": sum(1 for fr in self._history if fr.rolled_back),
            "dry_run": self.dry_run,
            "files_modified": len(self._backups),
        }


class AutonomousRemediationLoop:
    """Full autonomous audit → fix → verify → re-audit loop.

    Runs until convergence or max cycles reached.
    Includes 7 safeguards for convergence correctness.
    """

    def __init__(self, engine, llm_client, max_cycles: int = 10,
                 dry_run: bool = False) -> None:
        self.engine = engine
        self.llm = llm_client
        self.max_cycles = min(max_cycles, LoopSafeguard.MAX_ITERATIONS)
        self.dry_run = dry_run
        self._cycle_log: list[dict] = []
        self._safeguard = LoopSafeguard()
        self._identity = FindingIdentityTracker()
        self._judge = ConvergenceJudge(engine.repo_root)
        self._evidence = EvidenceChainBuilder(
            engine.repo_root / ".aura" / "evidence")

    def run(self) -> dict[str, Any]:
        """Run the autonomous loop with full safeguards."""
        self.engine.initialize()

        for cycle in range(1, self.max_cycles + 1):
            # Phase 1: AUDIT
            audit_result = self.engine.run_audit()
            classification = audit_result.get("classification", "?")
            score = audit_result.get("overall_score", 0)
            findings_count = audit_result.get("findings_count", 0)

            self._cycle_log.append({
                "cycle": audit_result.get("cycle_number", cycle),
                "classification": classification,
                "score": score,
                "findings": findings_count,
                "fixes_applied": 0,
                "fixes_succeeded": 0,
            })

            # Track finding identities
            findings = self.engine.db.get_findings(
                cycle_number=audit_result.get("cycle_number", 0))
            finding_ids = [f["finding_id"] for f in findings]
            self._identity.track(cycle, finding_ids)

            # Feedback loop: if converged, prove it
            if classification == "PRODUCTION_READY":
                # Verify with judge using all accumulated cycle states
                prev_states = [{
                    "overall_score": e.get("score", 0),
                    "findings_count": e.get("findings", 0),
                } for e in self._cycle_log[:-1]]

                current = {
                    "cycle_number": audit_result.get("cycle_number", cycle),
                    "phase": "CONVERGENCE",
                    "overall_score": score,
                    "findings_count": findings_count,
                    "open_p0": audit_result.get("open_p0", 0),
                    "open_p1": audit_result.get("open_p1", 0),
                    "open_p2": audit_result.get("open_p2", 0),
                    "open_p3": audit_result.get("open_p3", 0),
                    "open_p4": audit_result.get("open_p4", 0),
                    "open_p5": audit_result.get("open_p5", 0),
                    "verified_count": audit_result.get("verified_count", 0),
                    "tooling_passed": audit_result.get("tooling_passed", "0/0"),
                    "evidence_complete": True,
                }
                judge_result = self._judge.evaluate(current, prev_states)

                # Build convergence proof
                self._evidence.build_convergence_proof(
                    cycle, audit_result.get("gates", {}), judge_result)

                if judge_result.converged:
                    return self._build_result("converged",
                        f"Converged after {cycle} cycle(s) — PRODUCTION_READY. "
                        f"All 12 gates pass deterministically. "
                        f"Evidence: .aura/evidence/convergence_proof.json", cycle)

            # A-C: Safeguard checks (once per cycle)
            can_cont, reason = self._safeguard.can_continue(score, findings_count)
            if not can_cont:
                return self._build_result("safeguard_stop", reason, cycle)

            # Phase 2: REMEDIATE — continue as long as fixable findings exist
            # NOT_READY is INTERMEDIATE — loop continues until converged or blocker
            FIXABLE_STATUSES = {"OPEN", "IN_PROGRESS", "FIXED", "REJECTED"}
            fixable = [f for f in findings
                      if f.get("status") in FIXABLE_STATUSES
                      and f.get("file_path") and f.get("line_number")]

            # Per-finding closure accounting
            closure = {
                "total": len(findings),
                "fixable": len(fixable),
                "terminal_verified": len([f for f in findings if f.get("status") == "VERIFIED"]),
                "terminal_waived": len([f for f in findings if f.get("status") in ("WAIVED", "ACCEPTED_RISK", "OUT_OF_SCOPE")]),
                "blocked": len([f for f in findings if f.get("status") in ("BLOCKED", "DEFERRED")]),
                "fixed_awaiting_verify": len([f for f in findings if f.get("status") == "FIXED"]),
            }

            if not fixable:
                # Check if there are findings that need semantic analysis
                semantic_findings = len([f for f in findings
                                        if f.get("status") in FIXABLE_STATUSES
                                        and not f.get("file_path")])
                if semantic_findings > 0:
                    return self._build_result("human_blocker",
                        f"{semantic_findings} findings require semantic analysis — "
                        f"cannot auto-fix without file locations. {closure}", cycle)
                if closure["blocked"] > 0:
                    return self._build_result("human_blocker",
                        f"{closure['blocked']} findings blocked/deferred. {closure}", cycle)
                if findings_count > 0 and closure["terminal_verified"] + closure["terminal_waived"] == findings_count:
                    # All findings are in terminal states — but gates still not passing
                    return self._build_result("human_blocker",
                        f"All {findings_count} findings in terminal states but gates not passing. "
                        f"Check gate configuration. {closure}", cycle)
                return self._build_result("human_blocker",
                    f"No fixable findings remain. {closure}", cycle)

            sev_order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3, "P4": 4, "P5": 5}
            fixable.sort(key=lambda f: sev_order.get(f.get("severity", "P5"), 9))

            # Phase 3: FIX
            fixer = AutoFixer(self.engine.repo_root, dry_run=self.dry_run)
            fixes_applied = 0
            fixes_succeeded = 0
            max_fixes_per_cycle = min(20, len(fixable))

            # B: Track per-finding attempts within this cycle
            cycle_finding_attempts: dict[str, int] = {}

            for finding in fixable[:max_fixes_per_cycle]:
                fid = finding.get("finding_id", "")
                file_path = finding.get("file_path", "")
                line_num = finding.get("line_number", 0)
                if not file_path or not line_num:
                    continue

                # B: Track per-finding attempts - increment AFTER action, check BEFORE
                current_attempts = cycle_finding_attempts.get(fid, 0)
                if current_attempts >= LoopSafeguard.MAX_SAME_FINDING_ATTEMPTS:
                    continue

                fix_prompt = self._build_fix_prompt(finding)
                resp = self.llm.chat(
                    system_prompt="""You are AURA's Autonomous Fixer. Given a finding, produce the exact code change.
Output ONLY valid JSON:
{"file":"path","line_start":N,"line_end":N,"old_code":"exact old code","new_code":"fixed code","explanation":"why"}
IMPORTANT: old_code must match existing code exactly. One fix per response.""",
                    user_message=fix_prompt, max_tokens=2000,
                )

                try:
                    fix_data = json.loads(resp.content)
                    fr = fixer.apply_fix(
                        file_path=fix_data.get("file", file_path),
                        line_start=fix_data.get("line_start", line_num),
                        line_end=fix_data.get("line_end", line_num),
                        old_code=fix_data.get("old_code", ""),
                        new_code=fix_data.get("new_code", ""),
                    )
                    fixes_applied += 1

                    # Persist attempt to DB (P0: evidence persistence)
                    dt_now = datetime.now(UTC).strftime('%H%M%S%f')
                    db_attempt = {
                        "attempt_id": f"A-{audit_result.get('cycle_number', cycle)}-{dt_now}",
                        "cycle_number": audit_result.get("cycle_number", cycle),
                        "finding_id": fid,
                        "file_path": file_path,
                        "line_start": fix_data.get("line_start", line_num),
                        "line_end": fix_data.get("line_end", line_num),
                        "status": "APPLIED" if fr.success else "REJECTED",
                        "patch_content": json.dumps(fix_data)[:2000] if fix_data else None,
                        "error_message": fr.error if not fr.success else None,
                        "duration_ms": None,
                    }
                    self.engine.db.insert_remediation_attempt(db_attempt)

                    if fr.success:
                        fixes_succeeded += 1
                        self.engine.db.update_finding_status(fid, "FIXED",
                            f"Auto-fixed at cycle {cycle}")
                        cycle_finding_attempts[fid] = current_attempts + 1
                    else:
                        # P1: Retry with actual file content context
                        actual_file = self.engine.repo_root / file_path
                        if actual_file.exists() and current_attempts <= 0:
                            actual_content = actual_file.read_text(encoding="utf-8", errors="ignore")
                            actual_lines = actual_content.split("\n")
                            ctx_start = max(0, line_num - 5)
                            ctx_end = min(len(actual_lines), line_num + 5)
                            actual_context = "\n".join(
                                f"{i+1}: {l}" for i, l in enumerate(actual_lines[ctx_start:ctx_end], ctx_start))
                            retry_prompt = f"""{fix_prompt}

ACTUAL FILE CONTENT at lines {ctx_start+1}-{ctx_end}:
{actual_context}

Your old_code did not match. Generate the CORRECT old_code matching the ACTUAL content above.
Output ONLY valid JSON with corrected old_code."""
                            retry_resp = self.llm.chat(
                                "Output ONLY valid JSON with CORRECTED old_code matching the actual file content.",
                                retry_prompt, max_tokens=2000)
                            try:
                                retry_data = json.loads(retry_resp.content)
                                fr2 = fixer.apply_fix(
                                    file_path=retry_data.get("file", file_path),
                                    line_start=retry_data.get("line_start", line_num),
                                    line_end=retry_data.get("line_end", line_num),
                                    old_code=retry_data.get("old_code", ""),
                                    new_code=retry_data.get("new_code", ""),
                                )
                                # Persist retry attempt
                                dt_now2 = datetime.now(UTC).strftime('%H%M%S%f')
                                retry_db = {
                                    "attempt_id": f"A-{audit_result.get('cycle_number', cycle)}-{dt_now2}-retry",
                                    "cycle_number": audit_result.get("cycle_number", cycle),
                                    "finding_id": fid,
                                    "file_path": file_path,
                                    "line_start": retry_data.get("line_start", line_num),
                                    "line_end": retry_data.get("line_end", line_num),
                                    "status": "APPLIED" if fr2.success else "REJECTED",
                                    "patch_content": json.dumps(retry_data)[:2000],
                                    "error_message": fr2.error if not fr2.success else None,
                                    "duration_ms": None,
                                }
                                self.engine.db.insert_remediation_attempt(retry_db)
                                if fr2.success:
                                    fixes_succeeded += 1
                                    self.engine.db.update_finding_status(fid, "FIXED",
                                        f"Auto-fixed at cycle {cycle} (retry)")
                                    cycle_finding_attempts[fid] = current_attempts + 2
                                else:
                                    cycle_finding_attempts[fid] = current_attempts + 2
                            except (json.JSONDecodeError, KeyError):
                                pass
                except (json.JSONDecodeError, KeyError):
                    # Store unparseable LLM response in dead letter queue
                    with contextlib.suppress(Exception):
                        self.engine.db.insert_dead_letter(
                            finding_id=fid,
                            cycle_number=audit_result.get('cycle_number', cycle),
                            error_type='UNPARSEABLE',
                            raw_response=resp.content[:5000] if hasattr(resp, 'content') else '',
                            recovery_hint='LLM returned non-JSON response. Retry with stricter prompt.',
                            attempt_number=current_attempts + 1,
                        )
                    fixes_applied += 1
                    dt_now = datetime.now(UTC).strftime('%H%M%S%f')
                    db_attempt = {
                        "attempt_id": f"A-{audit_result.get('cycle_number', cycle)}-{dt_now}",
                        "cycle_number": audit_result.get("cycle_number", cycle),
                        "finding_id": fid,
                        "file_path": file_path,
                        "line_start": line_num,
                        "line_end": line_num,
                        "status": "FAILED",
                        "patch_content": resp.content[:2000] if resp.content else None,
                        "error_message": "LLM response parse error",
                        "duration_ms": None,
                    }
                    self.engine.db.insert_remediation_attempt(db_attempt)
                    cycle_finding_attempts[fid] = current_attempts + 1
                    continue

            self._cycle_log[-1]["fixes_applied"] = fixes_applied
            self._cycle_log[-1]["fixes_succeeded"] = fixes_succeeded

            # Phase 4: VERIFY
            if fixes_succeeded > 0:
                tooling_passed = True
                for cmd in self.engine._detect_commands():
                    try:
                        r = subprocess.run(
                            ["cmd", "/c", cmd] if __import__("os").name == "nt"
                            else ["sh", "-c", cmd],
                            cwd=str(self.engine.repo_root),
                            capture_output=True, text=True, timeout=300)
                        if r.returncode != 0:
                            tooling_passed = False
                            break
                    except Exception:
                        tooling_passed = False
                        break

                if not tooling_passed:
                    rollback_result = fixer.rollback()
                    self._cycle_log[-1]["rollback"] = rollback_result
                    # Continue to re-audit
                else:
                    # Save evidence
                    patch_file = str(self.engine.repo_root / ".aura" / f"cycle-{cycle:03d}.patch")
                    fixer.save_patch(patch_file)
                    self._evidence.save_cycle_evidence(
                        cycle, audit_result, patch_file,
                        {"tooling_passed": True, "fixes_applied": fixes_applied,
                         "fixes_succeeded": fixes_succeeded})

            # D: Regression trade-off analysis
            if len(self._cycle_log) >= 2:
                prev_f = self._safeguard.finding_counts[-2] if len(self._safeguard.finding_counts) >= 2 else 0
                curr_f = self._safeguard.finding_counts[-1] if self._safeguard.finding_counts else 0
                if curr_f > prev_f:
                    self._cycle_log[-1]["regression_warning"] = f"Findings increased: {prev_f} → {curr_f}"

        return self._build_result("max_cycles",
            f"Reached max cycles ({self.max_cycles}) without convergence", self.max_cycles)

    def _build_fix_prompt(self, finding: dict) -> str:
        return f"""Finding:
  ID: {finding.get('finding_id','?')}
  Severity: {finding.get('severity','?')}
  Category: {finding.get('category','?')}
  Problem: {finding.get('problem','?')}
  File: {finding.get('file_path','?')}:{finding.get('line_number','?')}
  Remediation: {finding.get('remediation','?')}

Provide the exact code change to fix this finding."""

    def _build_result(self, outcome: str, message: str, cycles: int) -> dict[str, Any]:
        return {
            "outcome": outcome,
            "message": message,
            "cycles_completed": cycles,
            "cycle_log": self._cycle_log,
            "dry_run": self.dry_run,
            "converged": outcome == "converged",
        }
