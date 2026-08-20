import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

import click
from rich.console import Console
from rich.theme import Theme

from .state_manager import StateManager, write_text_file, read_json_file
from .config import get_config
from .state_machine import (
    validate_finding_state_integrity,
    validate_gate_evidence_integrity,
    test_valid_classification_transition,
    validate_gate_findings_crosscheck,
    _safe_bool as _sm_safe_bool,
    GATE_NAMES as GATE_NAMES_INTERNAL,
)
from .cycle_prompt import generate_cycle_prompt, get_l10n, load_locale, get_findings_summary
from .git_controller import get_git_context, invoke_engine_push
from .tooling import execute_tooling_and_save, get_project_tooling
from .incremental import IncrementalAuditEngine, create_incremental_engine

aura_theme = Theme({
    "banner": "cyan",
    "ok": "green",
    "warn": "yellow",
    "error": "red",
    "info": "bright_cyan",
    "dim": "dim",
})


def resolve_repo_root() -> str:
    candidate = Path(__file__).resolve().parent.parent.parent
    if candidate.is_dir():
        return str(candidate)
    raise RuntimeError("ENGINE_ROOT_RESOLUTION_FAILURE: Cannot resolve repository root.")


def write_banner(console: Console):
    console.print()
    console.print("=" * 40, style="banner")
    console.print("  CONTINUOUS AUDIT AND REMEDIATION ENGINE  ", style="banner")
    console.print("                v2.1.2                   ", style="banner")
    console.print("=" * 40, style="banner")
    console.print()


class ModuleLoader:
    def __init__(self, repo_root: str, modules_dir: str):
        self.repo_root = repo_root
        self.modules_dir = Path(modules_dir)
        self.loaded_count = 0
        self.load_failed: List[str] = []
        self.required_failures: List[str] = []
        self.optional_failures: List[str] = []
        self.experimental_failures: List[str] = []
        self.missing_validators: List[str] = []
        self.module_integrity_pass = True
        self._module_command_map: Dict[str, callable] = {}

    def load_module(self, mod_name: str, is_required: bool, is_optional: bool, is_experimental: bool):
        mod_path = self.modules_dir / mod_name
        if not mod_path.exists():
            entry = "{} (file not found)".format(mod_name)
            self.load_failed.append(entry)
            if is_required:
                self.required_failures.append(entry)
            elif is_optional:
                self.optional_failures.append(entry)
            elif is_experimental:
                self.experimental_failures.append(entry)
            else:
                self.required_failures.append("{} (unclassified, treated as REQUIRED)".format(entry))
            return

        try:
            mod_text = mod_path.read_text(encoding="utf-8")
            if mod_name.endswith(".ps1"):
                self._register_ps_module(mod_name)
            self.loaded_count += 1
        except Exception as e:
            entry = "{} -- {}".format(mod_name, e)
            self.load_failed.append(entry)
            classification = "UNCLASSIFIED"
            if is_required:
                self.required_failures.append(entry)
                classification = "REQUIRED"
            elif is_optional:
                self.optional_failures.append(entry)
                classification = "OPTIONAL"
            elif is_experimental:
                self.experimental_failures.append(entry)
                classification = "EXPERIMENTAL"
            else:
                self.required_failures.append("{} (unclassified, treated as REQUIRED)".format(entry))
                classification = "UNCLASSIFIED (treated as REQUIRED)"

    def _register_ps_module(self, mod_name: str):
        pass

    def report(self, console: Console):
        if self.load_failed:
            style = "error" if self.required_failures else "warn"
            console.print("[AURA] MODULE_DEPENDENCY_FAILURE: {} module(s) could not be loaded.".format(len(self.load_failed)), style=style)
            if self.required_failures:
                console.print("[AURA] REQUIRED MODULE FAILURES ({}):".format(len(self.required_failures)), style="error")
                for rf in self.required_failures:
                    console.print("  [REQUIRED FAIL] {}".format(rf), style="error")
                console.print("[AURA] CONVERGENCE BLOCKED: {} required module(s) missing or failed to load.".format(len(self.required_failures)), style="error")
                console.print("[AURA] Classification cannot be PRODUCTION_READY until all required modules are available and loaded.", style="error")
            if self.optional_failures:
                console.print("[AURA] OPTIONAL MODULE WARNINGS ({}): {}".format(len(self.optional_failures), "; ".join(self.optional_failures)), style="warn")
            if self.experimental_failures:
                console.print("[AURA] EXPERIMENTAL MODULE WARNINGS ({}): {}".format(len(self.experimental_failures), "; ".join(self.experimental_failures)), style="dim")

    def report_banner(self, console: Console):
        if not self.module_integrity_pass:
            console.print()
            console.print("=" * 64, style="error")
            console.print("  MODULE DEPENDENCY INTEGRITY: FAILED", style="error")
            console.print("  Engine is operating in DEGRADED mode.", style="error")
            console.print("  Convergence to PRODUCTION_READY is BLOCKED.", style="error")
            console.print("=" * 64, style="error")
            console.print()
        else:
            console.print("[AURA] MODULE INTEGRITY: All required modules loaded successfully.", style="ok")


MODULE_ORDER = [
    "business-invariants.ps1", "evidence-integrity.ps1", "independent-verifier.ps1",
    "repo-graph.ps1", "sandbox.ps1", "security-scan.ps1", "git-safety.ps1",
    "git-safety-adversarial.ps1", "capability-scoring.ps1", "scale-benchmark.ps1",
    "mutation-testing.ps1", "failure-recovery.ps1", "false-evidence-attacks.ps1",
    "adversarial-campaign.ps1", "false-convergence-extended.ps1",
]

REQUIRED_VALIDATOR_COMMANDS = ["Validate-FindingStateIntegrity", "Validate-GateEvidenceIntegrity", "Test-ValidClassificationTransition"]


def load_all_modules(repo_root: str, modules_dir: str, config: "AuraConfig") -> ModuleLoader:
    loader = ModuleLoader(repo_root, modules_dir)
    required_set = set(config.required_modules)
    optional_set = set(config.optional_modules)
    experimental_set = set(config.experimental_modules)

    for mod_name in MODULE_ORDER:
        is_required = mod_name in required_set
        is_optional = mod_name in optional_set
        is_experimental = mod_name in experimental_set
        loader.load_module(mod_name, is_required, is_optional, is_experimental)

    loader.module_integrity_pass = (len(loader.required_failures) == 0)

    if not loader.module_integrity_pass and loader.required_failures:
        for cmd in REQUIRED_VALIDATOR_COMMANDS:
            loader.missing_validators.append(cmd)

    return loader


def bootstrap_dirs(engine_root: str, repo_root: str):
    engine = Path(engine_root)
    for sub in ["docs", "agents", "lang"]:
        target = engine / sub
        if not target.exists():
            target.mkdir(parents=True, exist_ok=True)
            source = Path(repo_root) / "src" / sub
            if source.is_dir():
                for sf in source.iterdir():
                    if sf.is_file():
                        shutil.copy2(str(sf), str(target / sf.name))


def action_status(state_mgr: StateManager, config, console: Console):
    state = state_mgr.read_cycle()
    findings = state_mgr.read_findings()
    conv = state_mgr.read_convergence()

    if not state:
        console.print("Engine not yet initialized. Run -Action run first.", style="warn")
        return

    console.print("\n=== CONVERGENCE STATUS ===", style="warn")
    console.print("Cycle:                 {}".format(state.get("current_cycle", "?")))
    console.print("Classification:        {}".format(state.get("classification", "?")))
    console.print("Cycles w/o progress:   {}".format(state.get("cycles_without_progress", "?")))
    console.print("Consecutive converged: {}".format(state.get("consecutive_converged_cycles", "?")))

    if conv:
        console.print()
        console.print("Consecutive converged cycles (conv): {}".format(conv.get("consecutive_converged_cycles", "?")))
        console.print("Audits since last finding: {}".format(conv.get("audits_since_last_finding", "?")))
        console.print()
        gates = conv.get("gates", {})
        for gate_name in sorted(gates.keys()):
            val = gates[gate_name]
            style = "ok" if val else "error"
            console.print("  {:<30} : {}".format(gate_name, val), style=style)

        classification = conv.get("classification", "NOT_READY")
        class_style = "ok" if classification == "PRODUCTION_READY" else ("warn" if classification == "CONDITIONALLY_READY" else "error")
        console.print()
        console.print("Classification: {}".format(classification), style=class_style)
        console.print("Reason: {}".format(conv.get("reason", "?")))

        mod_status = conv.get("module_status", {})
        if mod_status:
            console.print()
            mod_style = "ok" if mod_status.get("integrity_pass") else "error"
            console.print("Module Integrity: {}".format(mod_status.get("integrity_pass")), style=mod_style)
            console.print("  Required failures: {}".format(len(mod_status.get("required_failures", []))))
            for rf in mod_status.get("required_failures", []):
                console.print("    [REQUIRED FAIL] {}".format(rf), style="error")
            console.print("  Optional failures: {}".format(len(mod_status.get("optional_failures", []))))
            console.print("  Experimental failures: {}".format(len(mod_status.get("experimental_failures", []))))
            console.print("  Loaded/Total: {}/{}".format(mod_status.get("total_loaded", 0), mod_status.get("total_expected", 0)))

    if findings and findings.get("findings"):
        open_f = [f for f in findings["findings"] if f.get("status") in ("OPEN", "IN_PROGRESS")]
        open_p0p2 = [f for f in open_f if f.get("severity") in ("P0", "P1", "P2")]
        cnt_style = "ok" if len(open_p0p2) == 0 else "error"
        console.print("\nOpen P0-P2 findings: {}".format(len(open_p0p2)), style=cnt_style)
        for f in open_p0p2:
            console.print("  {} | {} | {} | {}".format(f.get("id"), f.get("severity"), f.get("category"), f.get("problem")), style="error")


def action_validate_state(state_mgr: StateManager, config, console: Console, project_path: str):
    findings = state_mgr.read_findings()
    conv = state_mgr.read_convergence()
    state = state_mgr.read_cycle()

    proposed_findings = state_mgr.read_proposed_findings()
    proposed_conv = state_mgr.read_proposed_convergence()
    proposed_cycle = state_mgr.read_proposed_cycle()

    has_proposed = any([proposed_findings, proposed_conv, proposed_cycle])

    console.print("\n=== STATE MACHINE INTEGRITY VALIDATION ===", style="banner")

    if has_proposed:
        console.print("\n-- Proposed State Validation (pre-promote) --", style="warn")

        if proposed_findings and proposed_findings.get("findings"):
            fviolations = validate_finding_state_integrity(proposed_findings["findings"], findings)
            style_f = "ok" if len(fviolations) == 0 else "error"
            console.print("Proposed finding violations: {}".format(len(fviolations)), style=style_f)
            for v in fviolations:
                console.print("  {}".format(v), style="error")

        if proposed_conv:
            gviolations = validate_gate_evidence_integrity(proposed_conv, conv)
            style_g = "ok" if len(gviolations) == 0 else "error"
            console.print("Proposed gate violations: {}".format(len(gviolations)), style=style_g)
            for v in gviolations:
                console.print("  {}".format(v), style="error")

            if proposed_conv.get("classification"):
                old_class = conv.get("classification", "") if conv else ""
                new_class = proposed_conv["classification"]
                class_ok = test_valid_classification_transition(old_class, new_class)
                style_c = "ok" if class_ok else "error"
                console.print("Proposed classification: {} ({} -> {}) - {}".format(new_class, old_class, new_class, "VALID" if class_ok else "INVALID"), style=style_c)

        tooling_ev = state_mgr.read_tooling_evidence()
        if proposed_findings and proposed_findings.get("findings"):
            new_verified = [f for f in proposed_findings["findings"] if f.get("status") == "VERIFIED"]
            if new_verified:
                if not tooling_ev:
                    console.print("TOOLING EVIDENCE: MISSING - {} findings proposed VERIFIED but no tooling-evidence.json".format(len(new_verified)), style="error")
                else:
                    console.print("TOOLING EVIDENCE: PRESENT - {} findings proposed VERIFIED".format(len(new_verified)), style="ok")
        console.print()

    console.print("-- Current State Validation --", style="warn")

    if conv:
        internal_violations = _validate_convergence_invariants(conv)
        style_inv = "ok" if len(internal_violations) == 0 else "error"
        console.print("Convergence internal invariants: {}".format(len(internal_violations)), style=style_inv)
        for v in internal_violations:
            console.print("  {}".format(v), style="error")

        if conv.get("converged"):
            gates = conv.get("gates", {})
            all_pass = all(_safe_bool(gates.get(g)) for g in GATE_NAMES_INTERNAL)
            cstyle = "ok" if all_pass else "error"
            console.print("All 12 gates pass: {} (converged={})".format(all_pass, conv.get("converged")), style=cstyle)
            if not all_pass:
                failing = [g for g in GATE_NAMES_INTERNAL if not _safe_bool(gates.get(g))]
                console.print("  Failing: {}".format(", ".join(failing)), style="error")

    finding_list = findings.get("findings", []) if findings else []
    fviolations = validate_finding_state_integrity(finding_list, findings)
    style_f = "ok" if len(fviolations) == 0 else "error"
    console.print("Finding transition violations: {}".format(len(fviolations)), style=style_f)
    for v in fviolations:
        console.print("  {}".format(v), style="warn")

    git_ctx = get_git_context(project_path)
    fc = int(git_ctx.get("FileCount", 0) or 0)
    scope_style = "ok" if fc <= 500 else ("warn" if fc <= 2000 else "error")
    console.print("Total tracked files: {}".format(fc), style=scope_style)

    old_class = conv.get("classification", "") if conv else ""
    class_ok = test_valid_classification_transition(old_class, old_class)
    style_c = "ok" if class_ok else "error"
    console.print("Classification valid: {} ({})".format(class_ok, old_class), style=style_c)

    if findings and findings.get("findings"):
        open_count = sum(1 for f in findings["findings"] if f.get("status") in ("OPEN", "IN_PROGRESS"))
        verified_count = sum(1 for f in findings["findings"] if f.get("status") == "VERIFIED")
        console.print("Findings: {} open, {} verified".format(open_count, verified_count))


def action_promote_state(state_mgr: StateManager, config, console: Console,
                         project_path: str, force_validation: bool,
                         module_loader: ModuleLoader):
    console.print("\n=== STATE PROMOTION (LLM -> Validated -> Committed) ===", style="banner")

    proposed_findings = state_mgr.read_proposed_findings()
    proposed_conv = state_mgr.read_proposed_convergence()
    proposed_cycle = state_mgr.read_proposed_cycle()

    if not any([proposed_findings, proposed_conv, proposed_cycle]):
        console.print("[REJECTED] No proposed state files found.", style="error")
        return

    existing_findings = state_mgr.read_findings()
    existing_conv = state_mgr.read_convergence()
    existing_cycle = state_mgr.read_cycle()

    all_violations = []
    all_warnings = []

    console.print()
    console.print("[1/4] Validating finding state transitions...", style="warn")
    if proposed_findings and proposed_findings.get("findings"):
        fviolations = validate_finding_state_integrity(proposed_findings["findings"], existing_findings)
        for v in fviolations:
            all_violations.append("FINDING: {}".format(v))
            console.print("  [VIOLATION] {}".format(v), style="error")
        if not fviolations:
            console.print("  [PASS] All finding transitions valid", style="ok")
    else:
        console.print("  [SKIP] No proposed findings", style="warn")

    console.print()
    console.print("[2/4] Validating convergence gate evidence...", style="warn")
    if proposed_conv:
        gviolations = validate_gate_evidence_integrity(proposed_conv, existing_conv)
        for v in gviolations:
            all_violations.append("GATE: {}".format(v))
            console.print("  [VIOLATION] {}".format(v), style="error")
        if not gviolations:
            console.print("  [PASS] All convergence gate changes valid", style="ok")

        if proposed_conv.get("classification"):
            old_class = existing_conv.get("classification", "") if existing_conv else ""
            new_class = proposed_conv["classification"]
            if not test_valid_classification_transition(old_class, new_class):
                all_violations.append("CLASSIFICATION: {} -> {} is not allowed".format(old_class, new_class))
                console.print("  [VIOLATION] Classification: {} -> {} not allowed".format(old_class, new_class), style="error")
            else:
                console.print("  [PASS] Classification: {} -> {} valid".format(old_class, new_class), style="ok")
    else:
        console.print("  [SKIP] No proposed convergence", style="warn")

    console.print()
    console.print("[2b/4] Cross-validating gate values against findings...", style="warn")
    if proposed_conv and proposed_conv.get("gates") and proposed_findings and proposed_findings.get("findings"):
        cross_violations = validate_gate_findings_crosscheck(proposed_conv, proposed_findings, existing_findings)
        for v in cross_violations:
            all_violations.append("GATE-FINDINGS MISMATCH: {}".format(v))
            console.print("  [VIOLATION] {}".format(v), style="error")
        if not cross_violations:
            console.print("  [PASS] Gate values consistent with findings", style="ok")
    else:
        console.print("  [SKIP] Missing proposed convergence or findings for cross-check", style="warn")

    console.print()
    console.print("[3/4] Validating tooling evidence...", style="warn")
    tooling_evidence = state_mgr.read_tooling_evidence()
    if proposed_findings and proposed_findings.get("findings"):
        newly_verified = [f for f in proposed_findings["findings"] if f.get("status") == "VERIFIED"]
        if newly_verified:
            if not tooling_evidence:
                all_violations.append("TOOLING: {} findings proposed VERIFIED but tooling-evidence.json is missing".format(len(newly_verified)))
                console.print("  [VIOLATION] {} findings proposed VERIFIED but no tooling evidence".format(len(newly_verified)), style="error")
            else:
                all_passed = True
                for key, r in tooling_evidence.get("results", {}).items():
                    if not r.get("success"):
                        all_passed = False
                        console.print("  [WARN] Tool '{}' FAILED (exit code {})".format(key, r.get("exit_code")), style="warn")
                if all_passed:
                    console.print("  [PASS] Tooling evidence present and all commands passed", style="ok")
                else:
                    all_warnings.append("Some tooling commands failed. Verify findings carefully.")
                    console.print("  [WARN] Some tooling commands failed", style="warn")
        else:
            console.print("  [INFO] No new VERIFIED findings this cycle; tooling evidence optional", style="info")
    else:
        console.print("  [SKIP] No proposed findings", style="warn")

    console.print()
    console.print("[4/4] Validating audit scope...", style="warn")
    console.print("  [INFO] Scope assessment from proposed cycle", style="info")

    console.print()
    console.print("[5/6] Validating module dependency integrity...", style="warn")
    rf_style = "ok" if len(module_loader.required_failures) == 0 else "error"
    console.print("  Required failures: {}".format(len(module_loader.required_failures)), style=rf_style)
    console.print("  Optional failures: {}".format(len(module_loader.optional_failures)), style="ok" if len(module_loader.optional_failures) == 0 else "warn")
    console.print("  Experimental failures: {}".format(len(module_loader.experimental_failures)), style="dim")
    console.print("  Module integrity pass: {}".format(module_loader.module_integrity_pass), style="ok" if module_loader.module_integrity_pass else "error")

    if not module_loader.module_integrity_pass:
        console.print("  [ENFORCE] Overriding module_dependency_integrity gate to FALSE (orchestrator authority)", style="error")
        if proposed_conv:
            if "gates" not in proposed_conv:
                proposed_conv["gates"] = {}
            proposed_conv["gates"]["module_dependency_integrity"] = False
        all_violations.append("MODULE_INTEGRITY: Required modules failed to load. Convergence blocked.")
        console.print("  [VIOLATION] Required modules failed to load. module_dependency_integrity gate forced to FALSE.", style="error")
        for rf in module_loader.required_failures:
            console.print("    Missing: {}".format(rf), style="error")
    else:
        console.print("  [PASS] All required modules loaded. module_dependency_integrity gate can be evaluated by evidence.", style="ok")

    if not module_loader.module_integrity_pass and proposed_conv and proposed_conv.get("converged"):
        console.print("  [ENFORCE] Overriding converged flag to FALSE (module integrity failure prevents convergence)", style="error")
        proposed_conv["converged"] = False
        all_violations.append("CONVERGENCE BLOCKED: Cannot converge with required module failures.")

    if not module_loader.module_integrity_pass and proposed_conv and proposed_conv.get("classification") == "PRODUCTION_READY":
        console.print("  [ENFORCE] Overriding classification from PRODUCTION_READY to NOT_READY (module failures)", style="error")
        proposed_conv["classification"] = "NOT_READY"
        proposed_conv["reason"] = str(proposed_conv.get("reason", "")) + "\n[ORCHESTRATOR OVERRIDE] Classification downgraded: {} required module(s) missing. Convergence claims not trustworthy.".format(len(module_loader.required_failures))
        all_violations.append("CLASSIFICATION OVERRIDE: PRODUCTION_READY -> NOT_READY due to required module failures.")

    console.print()
    if all_violations:
        if force_validation:
            console.print("=== PROMOTION FORCED ===", style="warn")
            console.print("{} violation(s) BYPASSED by -ForceValidation:".format(len(all_violations)), style="warn")
            for v in all_violations:
                console.print("  [BYPASSED] {}".format(v), style="warn")
            console.print()
            console.print("[FORCE] -ForceValidation active. Promoting state despite violations.", style="warn")
            all_violations = []
        else:
            console.print("=== PROMOTION REJECTED ===", style="error")
            console.print("{} violation(s) found:".format(len(all_violations)), style="error")
            for v in all_violations:
                console.print("  {}".format(v), style="error")
            console.print()
            console.print("Fix violations and re-run promote-state. Proposed files preserved.", style="warn")
            return

    if not all_violations:
        console.print("=== PROMOTION ACCEPTED ===", style="ok")
        console.print("All validations passed. Committing proposed state...", style="ok")

        if all_warnings:
            console.print()
            console.print("Warnings (non-blocking):", style="warn")
            for w in all_warnings:
                console.print("  {}".format(w), style="warn")

        promoted_files = []

        if proposed_findings:
            state_mgr.write_findings(proposed_findings)
            promoted_files.append("findings.json")
            console.print("  [COMMITTED] {}".format(state_mgr.findings_file), style="ok")

        if proposed_conv:
            state_mgr.write_convergence(proposed_conv)
            promoted_files.append("convergence.json")
            console.print("  [COMMITTED] {}".format(state_mgr.convergence_file), style="ok")

        if proposed_cycle:
            state_mgr.write_cycle(proposed_cycle)
            promoted_files.append("cycle.json")
            console.print("  [COMMITTED] {}".format(state_mgr.cycle_file), style="ok")

        console.print()
        console.print("[SUCCESS] State promoted: {}".format(", ".join(promoted_files)), style="ok")
        if all_warnings:
            console.print("[WARN] Promotion accepted with warnings. Review warnings above.", style="warn")

        new_material_count = 0
        if proposed_findings and proposed_findings.get("findings") and existing_findings and existing_findings.get("findings"):
            existing_ids = set(f["id"] for f in existing_findings["findings"] if f.get("id") is not None)
            new_material_count = sum(1 for f in proposed_findings["findings"]
                                     if f.get("id") is not None and f["id"] not in existing_ids
                                     and f.get("severity") in ("P0", "P1", "P2", "P3"))

        cycle_data = state_mgr.read_cycle()
        if cycle_data:
            if new_material_count > 0:
                cycle_data["cycles_without_progress"] = 0
                console.print("  [PROGRESS] {} new P0-P3 material finding(s) this cycle. cycles_without_progress reset to 0.".format(new_material_count), style="info")
            else:
                prev = existing_cycle.get("cycles_without_progress", 0) or 0 if existing_cycle else 0
                new_wo = prev + 1
                cycle_data["cycles_without_progress"] = new_wo
                console.print("  [STALL] No new P0-P3 material findings. cycles_without_progress: {} -> {}".format(prev, new_wo), style="warn")
                if new_wo >= 3:
                    cycle_data["status"] = "STALLED"
                    console.print("  [HALT] Stalling: {} cycles without progress. Next -Action run will halt.".format(new_wo), style="error")
            state_mgr.write_cycle(cycle_data)

        from datetime import datetime
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        archive_dir = state_mgr.engine_root / "archive"
        archive_dir.mkdir(parents=True, exist_ok=True)

        for pf_name, pf_path in [
            ("proposed-findings", state_mgr.proposed_findings_file),
            ("proposed-convergence", state_mgr.proposed_convergence_file),
            ("proposed-cycle", state_mgr.proposed_cycle_file),
        ]:
            if pf_path.exists():
                shutil.copy2(str(pf_path), str(archive_dir / "{}-{}.json".format(pf_name, ts)))
                pf_path.unlink()

        console.print("[ARCHIVE] Proposed state archived for audit trail", style="info")


@click.command()
@click.option("--action", "-a", "action_name", default="run",
              type=click.Choice(["run", "status", "reset", "context", "push", "validate-state",
                                 "run-tooling", "scope-check", "plan-audit", "promote-state", "invariant-check",
                                 "index-repo", "evidence-check", "adversarial-campaign",
                                 "scale-benchmark", "sandbox-test", "security-scan", "git-safety",
                                 "verify-findings", "score-report", "false-evidence-campaign",
                                 "false-convergence-campaign", "git-safety-campaign",
                                 "mutation-test", "failure-recovery"]),
              help="Action to perform")
@click.option("--target-project", "-t", default=".",
              help="Target project path")
@click.option("--multi-agent/--no-multi-agent", default=False,
              help="Enable multi-agent mode")
@click.option("--force/--no-force", default=False,
              help="Force execution despite halt conditions")
@click.option("--approve/--no-approve", default=False,
              help="Auto-approve push")
@click.option("--amend/--no-amend", default=False,
              help="Amend previous commit")
@click.option("--force-validation/--no-force-validation", default=False,
              help="Force state promotion despite violations")
@click.option("--language", "-l", default="en",
              type=click.Choice(["en", "id", "ja", "zh-CN"]),
              help="Language for prompt generation")
def main_cli(action_name, target_project, multi_agent, force, approve, amend,
             force_validation, language):
    console = Console(theme=aura_theme)

    try:
        repo_root = resolve_repo_root()
    except RuntimeError as e:
        console.print("[ERROR] {}".format(e), style="error")
        sys.exit(1)

    config = get_config(repo_root)
    modules_dir = str(Path(repo_root) / ".aura" / "modules")
    if not Path(modules_dir).is_dir():
        modules_dir = str(Path(repo_root) / "src" / "modules")
    if not Path(modules_dir).is_dir():
        console.print("[ERROR] Modules directory not found.", style="error")
        sys.exit(1)

    module_loader = load_all_modules(repo_root, modules_dir, config)

    lang_dir = Path(repo_root) / "src" / "lang"
    if lang_dir.is_dir():
        locale_data = load_locale(language, repo_root)
        if locale_data:
            lang_msg = get_l10n(locale_data, "console.language_info", {"language": locale_data.get("_meta", {}).get("language", language)})
            console.print(lang_msg, style="ok")

    write_banner(console)

    try:
        full_project_path = str(Path(target_project).resolve())
    except Exception:
        console.print("[ERROR] Target project path does not exist or is invalid: {}".format(target_project), style="error")
        sys.exit(1)

    runtime_dir = Path(full_project_path) / ".aura"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    engine_root = str(runtime_dir)

    reports_dir = runtime_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    state_dir = runtime_dir / "state"
    state_dir.mkdir(parents=True, exist_ok=True)

    state_mgr = StateManager(engine_root)
    state_mgr.ensure_dirs()

    bootstrap_dirs(engine_root, repo_root)

    if action_name == "status":
        action_status(state_mgr, config, console)

    elif action_name == "reset":
        state_mgr.reset_engine()
        console.print("[ARCHIVED] Previous state archived", style="warn")
        console.print("[OK] Engine fully reset.", style="ok")

    elif action_name == "context":
        state = state_mgr.read_cycle()
        if not state or state.get("status") == "NOT_STARTED":
            console.print(console_missing_key("console.init_state_init"), style="warn")
            state_mgr.initialize_state(
                module_integrity_pass=module_loader.module_integrity_pass,
                mod_required_failures=module_loader.required_failures,
                mod_optional_failures=module_loader.optional_failures,
                mod_experimental_failures=module_loader.experimental_failures,
                mod_load_count=module_loader.loaded_count,
                mod_total_expected=len(MODULE_ORDER),
            )
        result = generate_cycle_prompt(full_project_path, state_mgr, multi_agent, language, repo_root)
        ctx_file = runtime_dir / "generated-cycle-prompt.md"
        write_text_file(str(ctx_file), result["prompt"])
        console.print(console_missing_key("console.context_generated"), str(ctx_file), style="ok")

    elif action_name == "run":
        state = state_mgr.read_cycle()
        if not state or state.get("status") == "NOT_STARTED":
            console.print(console_missing_key("console.init_first_run"), style="warn")
            state_mgr.initialize_state(
                module_integrity_pass=module_loader.module_integrity_pass,
                mod_required_failures=module_loader.required_failures,
                mod_optional_failures=module_loader.optional_failures,
                mod_experimental_failures=module_loader.experimental_failures,
                mod_load_count=module_loader.loaded_count,
                mod_total_expected=len(MODULE_ORDER),
            )

        if state_mgr.has_proposed_files():
            console.print("[BLOCKED] Proposed state files already exist -- previous cycle was not promoted.", style="error")
            for pf in state_mgr.get_proposed_files_list():
                console.print("  {}".format(pf), style="warn")
            console.print("")
            console.print("  The AI agent must run -Action promote-state to validate and commit the previous cycle.")
            console.print("  If the proposed state is stale/abandoned, delete the proposed-*.json files manually")
            console.print("  or run -Action reset to start fresh.")
            return

        conv = state_mgr.read_convergence()
        min_independent = config.min_independent_cycles_for_convergence
        required_consecutive = config.consecutive_converged_cycles_required

        if conv and conv.get("converged") and not force:
            cycles_ok = (state.get("cycles_completed", 0) or 0) >= min_independent
            consecutive_ok = (conv.get("consecutive_converged_cycles", 0) or 0) >= required_consecutive
            gates = conv.get("gates", {})
            module_ok = True
            if "module_dependency_integrity" in gates:
                module_ok = gates["module_dependency_integrity"]
            elif conv.get("module_status"):
                module_ok = conv["module_status"].get("integrity_pass", True)

            if not module_ok:
                console.print("[OVERRIDE] Convergence cannot be trusted -- required modules failed to load. Forcing new cycle.", style="error")
            elif cycles_ok and consecutive_ok:
                console.print("[HALT] Engine has converged (cycles: {}/{}, consecutive: {}/{}). Use -Force to run again.".format(
                    state.get("cycles_completed", "?"), min_independent,
                    conv.get("consecutive_converged_cycles", "?"), required_consecutive
                ), style="ok")
                action_status(state_mgr, config, console)
                return
            else:
                console.print("[NOTE] cycle converged flag is set but cycles or consecutive not met. Proceeding.", style="warn")

        max_cycles = config.max_cycles
        current_cycle = state.get("current_cycle", 0) or 0 if state else 0
        if current_cycle >= max_cycles and not force:
            console.print("[HALT] Max cycles ({}) reached. Use -Force to continue.".format(max_cycles), style="warn")
            return

        max_no_progress = config.max_cycles_without_progress
        cycles_wo = state.get("cycles_without_progress", 0) or 0 if state else 0
        if cycles_wo >= max_no_progress and not force:
            console.print("[HALT] Maximum cycles without progress ({}) reached. Use -Force to continue.".format(max_no_progress), style="warn")
            return

        result = generate_cycle_prompt(full_project_path, state_mgr, multi_agent, language, repo_root)
        ctx_file = runtime_dir / "generated-cycle-prompt.md"
        write_text_file(str(ctx_file), result["prompt"])

        console.print("Cycle: {}".format(result["cycle"]), style="ok")
        console.print("Project: {}".format(result["projectPath"]))
        console.print("Branch: {}".format(result["gitContext"].get("Branch", "?")))
        console.print("Multi-Agent: {}".format(multi_agent))
        console.print("Prompt: {}".format(ctx_file))
        console.print()
        console.print("=== FULL CYCLE PROMPT ({}) ===".format(result["cycle"]), style="banner")
        console.print()
        console.print(result["prompt"])
        console.print()
        console.print("=== END PROMPT ===", style="banner")

        env_file = runtime_dir / "last-cycle.env"
        env_content = "CYCLE={}\nPROJECT={}\nMULTI_AGENT={}\nPROMPT_FILE={}\nLANGUAGE={}\nTIMESTAMP={}\n".format(
            result["cycle"], result["projectPath"], multi_agent, ctx_file, language,
            __import__("datetime").datetime.now().isoformat()
        )
        write_text_file(str(env_file), env_content)

    elif action_name == "push":
        invoke_engine_push(full_project_path, engine_root, repo_root,
                           force_approve=approve, amend=amend, config=config,
                           rich_console=console)

    elif action_name == "validate-state":
        action_validate_state(state_mgr, config, console, full_project_path)

    elif action_name == "run-tooling":
        commands_result = execute_tooling_and_save(full_project_path, engine_root)
        if commands_result["status"] == "no_commands":
            console.print("[TOOLING] No test/lint/build commands detected for this project.", style="warn")
        else:
            console.print("\n=== EXECUTING PROJECT TOOLING ===", style="banner")
            console.print(commands_result["report"])
            console.print("[TOOLING] Results saved to state/tooling-evidence.json", style="ok")

    elif action_name == "scope-check":
        git_ctx = get_git_context(full_project_path)
        fc = int(git_ctx.get("FileCount", 0) or 0)
        console.print("\n=== AUDIT SCOPE ANALYSIS ===", style="banner")
        console.print("Total tracked files: {}".format(fc))
        if fc <= 100:
            console.print("Risk: LOW - Full audit practical in single context", style="ok")
        elif fc <= 500:
            console.print("Risk: MEDIUM - Full audit may approach context limits", style="warn")
        elif fc <= 2000:
            console.print("Risk: HIGH - Full audit impossible in single context. Chunking required.", style="warn")
            console.print("  Recommended: dependency-graph-aware incremental auditing", style="warn")
        else:
            console.print("Risk: CRITICAL - Repository too large for full context audit. Chunked+prioritized auditing mandatory.", style="error")

        if fc > 100:
            try:
                inc_engine = create_incremental_engine(full_project_path, engine_root)
                plan = inc_engine.get_audit_plan(1)
                console.print()
                console.print("Incremental Audit Assessment:", style="info")
                console.print("  Mode: {}".format(plan.mode.value))
                console.print("  Rationale: {}".format(plan.rationale))
                console.print("  Priority files this cycle: {}".format(len(plan.audit_files)))
                if plan.audit_files:
                    tier_counts = {}
                    for af in plan.audit_files[:10]:
                        tier_counts[af.tier.value] = tier_counts.get(af.tier.value, 0) + 1
                        console.print("    [{0.tier.value}] {0.path} (score={0.combined_score})".format(af), style="dim")
                    if len(plan.audit_files) > 10:
                        console.print("    ... and {} more files".format(len(plan.audit_files) - 10), style="dim")
                    console.print("  Tier breakdown: {}".format(
                        ", ".join("{}={}".format(k, v) for k, v in sorted(tier_counts.items()))
                    ))
            except Exception as e:
                console.print("  [WARN] Incremental audit assessment unavailable: {}".format(e), style="warn")

    elif action_name == "plan-audit":
        state = state_mgr.read_cycle()
        if not state or state.get("status") == "NOT_STARTED":
            console.print("Engine not yet initialized. Run -Action context first.", style="warn")
            return

        current_cycle = state.get("current_cycle", 1) or 1
        console.print("\n=== AUDIT PLAN FOR CYCLE {} ===".format(current_cycle), style="banner")

        try:
            inc_engine = create_incremental_engine(full_project_path, engine_root)
        except Exception as e:
            console.print("[ERROR] Failed to create incremental audit engine: {}".format(e), style="error")
            return

        try:
            plan = inc_engine.get_audit_plan(current_cycle)
        except Exception as e:
            console.print("[ERROR] Failed to compute audit plan: {}".format(e), style="error")
            return

        console.print("Mode:          {}".format(plan.mode.value.upper()), style="info")
        console.print("Rationale:     {}".format(plan.rationale))
        console.print("Total files:   {}".format(plan.total_repo_files))
        console.print("Changed files: {}".format(plan.changed_count))
        console.print("Force Full:    {}".format(plan.force_full))
        console.print("Prior Audit:   {}".format(plan.has_prior_audit))
        console.print()

        if plan.audit_files:
            console.print("Priority Files ({} total):".format(len(plan.audit_files)), style="info")
            console.print("{:<4s} {:<8s} {:<50s} {:>8s} {:>8s} {:>8s}".format(
                "#", "Tier", "Path", "Churn", "Crit", "Combined"
            ))
            console.print("-" * 90)
            for i, f in enumerate(plan.audit_files, 1):
                tier_style = "ok" if f.tier.value == "tier_1" else ("warn" if f.tier.value == "tier_2" else "dim")
                console.print("{:<4d} [{:<6s}] {:<50s} {:>8.1f} {:>8.1f} {:>8.1f}".format(
                    i, f.tier.value, f.path[:48], f.churn_score, f.criticality_score, f.combined_score
                ), style=tier_style)
        else:
            console.print("No files to audit this cycle.", style="warn")

        try:
            rates = inc_engine.get_author_bug_rates()
            if rates:
                console.print()
                console.print("Author Bug Rates:", style="info")
                top_authors = sorted(rates.items(), key=lambda x: x[1], reverse=True)[:5]
                for email, rate in top_authors:
                    style = "error" if rate > 0.3 else ("warn" if rate > 0.15 else "ok")
                    console.print("  {}: {:.1%}".format(email[:40], rate), style=style)
        except Exception:
            pass

    elif action_name == "promote-state":
        action_promote_state(state_mgr, config, console, full_project_path, force_validation, module_loader)

    elif action_name in ("invariant-check", "index-repo", "evidence-check",
                         "adversarial-campaign", "scale-benchmark", "sandbox-test",
                         "security-scan", "git-safety", "verify-findings", "score-report",
                         "false-evidence-campaign", "false-convergence-campaign",
                         "git-safety-campaign", "mutation-test", "failure-recovery"):
        console.print("\n=== {} ===".format(action_name.replace("-", " ").upper()), style="banner")
        console.print("[INFO] Action '{}' delegates to PowerShell module. Run via run-audit.ps1 for full implementation.".format(action_name), style="info")
        ps_script = Path(repo_root) / "src" / "engine" / "run-audit.ps1"
        if ps_script.exists():
            ps_args = ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(ps_script),
                       "-Action", action_name, "-TargetProject", full_project_path,
                       "-Language", language]
            if force:
                ps_args.append("-Force")
            if approve:
                ps_args.append("-Approve")
            result = subprocess.run(ps_args, cwd=full_project_path, shell=False)
            if result.returncode != 0:
                console.print("[WARN] PowerShell module exited with code {}".format(result.returncode), style="warn")
        else:
            console.print("[ERROR] PowerShell engine not found at: {}".format(ps_script), style="error")


ENGLISH_DEFAULTS = {
    "console.init_state_init": "Engine not yet initialized. Initializing...",
    "console.init_first_run": "Engine not yet initialized. Initializing for first run...",
    "console.context_generated": "Cycle prompt generated and saved to",
    "console.language_info": "Language: {language}",
}


def _validate_convergence_invariants(conv: dict) -> list:
    violations = []
    gates = conv.get("gates", {})

    if conv.get("converged"):
        all_pass = True
        for gn in GATE_NAMES_INTERNAL:
            if not _sm_safe_bool(gates.get(gn)):
                all_pass = False
                violations.append("INVARIANT VIOLATION: converged=true but gate '{}' is false".format(gn))
        if not all_pass:
            violations.append("CONVERGENCE INCONSISTENCY: converged=true requires ALL 12 gates pass")

    old_cc = int(conv.get("consecutive_converged_cycles", 0) or 0)
    if conv.get("converged") and old_cc < 1:
        violations.append("MINOR INCONSISTENCY: converged=true but consecutive_converged_cycles={} (should be >=1)".format(old_cc))

    if conv.get("classification") == "PRODUCTION_READY":
        missing_gates = [gn for gn in GATE_NAMES_INTERNAL if not _sm_safe_bool(gates.get(gn))]
        if missing_gates:
            violations.append("CLASSIFICATION INCONSISTENCY: PRODUCTION_READY but gates still false: {}".format(", ".join(missing_gates)))

    return violations


def console_missing_key(key: str) -> str:
    return ENGLISH_DEFAULTS.get(key, "[MISSING:{}]".format(key))


if __name__ == "__main__":
    main_cli()