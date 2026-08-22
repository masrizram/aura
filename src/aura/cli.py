"""AURA CLI — command-line interface for the audit engine.

Commands:
  aura init        Initialize database and engine
  aura audit       Run a full 13-phase audit cycle
  aura status      Show current engine status
  aura health      Health check
  aura doctor      System diagnostics
  aura verify      Verify findings with remediation guidance
  aura log         Show audit log with 13-phase trace
  aura report      Generate markdown audit report
  aura trend       Show trend analysis across cycles
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

from dotenv import load_dotenv

from .config import AuraConfig, ConfigError
from .engine import Engine
from .errors import AuraError
from .llm import LLMClient
from .remediation import AutoFixer, AutonomousRemediationLoop
from .logging import configure_logging

# Load .env at module import time — safe, idempotent
load_dotenv()

console = Console()
VERSION = "3.5.3"

# ── Gate descriptions for remediation guidance ─────────────────────────

GATE_DESCRIPTIONS = {
    "P0_zero": ("Zero P0 (catastrophic) findings", "Fix all P0 findings first — these are blockers."),
    "P1_zero": ("Zero P1 (critical) findings", "Fix all P1 findings — critical issues."),
    "P2_zero": ("Zero P2 (high) findings", "Address P2 findings or defer with justification."),
    "critical_security": ("All SECURITY P0-P2 VERIFIED", "Every security finding must have independent verification evidence."),
    "critical_correctness": ("All CORRECTNESS P0-P2 VERIFIED", "Correctness issues need verified fixes with tool output."),
    "data_integrity": ("All DATA_INTEGRITY findings VERIFIED", "Data integrity issues must be independently verified."),
    "regression": ("Zero re-appeared findings", "Run regression audit — fix re-appeared defects, then re-audit."),
    "verification": ("All FIXED have verifier evidence", "Run 'aura verify' for each finding, capture tool exit codes."),
    "no_material_new_findings": ("No new P0-P3 for 2 cycles", "Fix new findings, run 2+ clean cycles without new P0-P3 issues."),
    "limitations_documented": ("Limitations explicitly listed", "Document remaining known limitations in a LIMITATIONS.md file."),
    "consecutive_clean_independent_audits": ("≥2 clean cycles + ≥3 total cycles", "Run at least 2 consecutive audit cycles with zero new P0-P3 findings."),
    "module_dependency_integrity": ("All required modules loaded", "Ensure all required engine modules are present and loadable."),
}

REMEDIATION_GUIDE: dict[str, list[str]] = {
    "P0": [
        "🚨 CRITICAL — Fix immediately before any other work.",
        "1. Identify the root cause in the source file listed.",
        "2. Apply the fix according to the remediation suggestion.",
        "3. Run your test suite to verify the fix.",
        "4. Run 'aura audit' again to re-verify.",
    ],
    "P1": [
        "⚠️ HIGH — Schedule fix in current sprint.",
        "1. Review the finding and its evidence.",
        "2. Apply remediation suggested in the finding.",
        "3. Run tooling (tests, lint, build) to confirm.",
        "4. Re-run audit to verify fix is detected.",
    ],
    "P2": [
        "📋 MEDIUM — Address within 2 sprints.",
        "1. Triage: is this a real issue or acceptable risk?",
        "2. If real: apply fix per remediation suggestion.",
        "3. If acceptable: document as DEFERRED with justification.",
    ],
    "P3": [
        "📝 LOW — Address when convenient.",
        "Review and fix during regular maintenance cycles.",
    ],
}


@click.group()
@click.option("--config", "-c", default=None, help="Path to config file")
@click.option("--repo", "-r", default=".", help="Repository root path")
@click.option("--verbose", "-v", is_flag=True, help="Verbose output")
@click.option("--json", "json_output", is_flag=True, help="JSON output")
@click.pass_context
def cli(ctx: click.Context, config: str | None, repo: str, verbose: bool, json_output: bool) -> None:
    """AURA — Autonomous Audit-Remediate-Verify Engine v3.5.3"""
    ctx.ensure_object(dict)
    ctx.obj["repo_root"] = Path(repo).resolve()
    ctx.obj["verbose"] = verbose
    ctx.obj["json"] = json_output
    level = "WARNING" if not verbose else "DEBUG"
    configure_logging(level=level, json_output=json_output)
    try:
        if config:
            aura_config = AuraConfig.from_file(config)
        else:
            aura_config = AuraConfig.from_env_or_file(ctx.obj["repo_root"])
        ctx.obj["config"] = aura_config
    except ConfigError as e:
        console.print(f"[red]Configuration error: {e}[/red]")
        sys.exit(1)


@cli.command()
@click.pass_context
def init(ctx: click.Context) -> None:
    """Initialize database and engine."""
    engine = Engine(ctx.obj["repo_root"], ctx.obj["config"])
    try:
        engine.initialize()
        console.print("[green]✅ Engine initialized successfully[/green]")
        console.print("[dim]Run 'aura audit' to start your first audit cycle.[/dim]")
    except AuraError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)


def _format_audit_result(result: dict) -> None:
    """Pretty-print audit result with actionable remediation guidance."""
    cn = result.get("cycle_number", "?")
    classification = result.get("classification", "?")
    score = result.get("overall_score", 0)
    converged = result.get("converged", False)
    code_quality = result.get("code_quality", 0)
    files_analyzed = result.get("files_analyzed", 0)
    total_lines = result.get("total_lines", 0)
    code_issues = result.get("code_issues", 0)
    findings_count = result.get("findings_count", 0)
    adversarial_count = result.get("adversarial_count", 0)
    tooling = result.get("tooling_passed", "0/0")
    verified = result.get("verified_count", 0)
    regressions = result.get("regressions", 0)

    score_color = "green" if score >= 90 else ("yellow" if score >= 70 else "red")
    class_color = "green" if classification == "PRODUCTION_READY" else ("yellow" if classification == "CONDITIONALLY_READY" else "red")

    console.print()
    console.print(Panel(
        f"[bold]Cycle {cn} Complete[/bold]\n\n"
        f"Classification: [{class_color}]{classification}[/{class_color}]    "
        f"Score: [{score_color}]{score}/100[/{score_color}]    "
        f"Converged: {'[green]✅' if converged else '[red]❌'}\n\n"
        f"[dim]Quality: {code_quality}/100 | Files: {files_analyzed} | "
        f"Lines: {total_lines:,} | Findings: {findings_count} | "
        f"Adversarial: {adversarial_count} | Tooling: {tooling}[/dim]",
        title="Audit Result",
        border_style="cyan",
    ))

    # Flow summary
    console.print(f"\n[bold]13-Phase Cycle Flow:[/bold]")
    console.print("[dim]DISCOVER → MODEL → AUDIT → ADVERSARIAL_AUDIT → CORRELATE → "
                   "PRIORITIZE → REMEDIATE → TEST → VERIFY → REGRESSION → "
                   "UPDATE_STATE → CONVERGENCE → PUSH_APPROVAL[/dim]")

    # Gates with WHY each failed and HOW to fix
    gates = result.get("gates", {})
    if gates:
        passed = sum(1 for v in gates.values() if v)
        total = len(gates)
        console.print(f"\n[bold]Convergence Gates: {passed}/{total} passed[/bold]")

        failing = [(gn, gv) for gn, gv in sorted(gates.items()) if not gv]
        if failing:
            console.print()
            for gn, _ in failing:
                desc, fix = GATE_DESCRIPTIONS.get(gn, (gn, "Fix issues blocking this gate."))
                console.print(f"  [red]❌ {gn}[/red] — {desc}")
                console.print(f"     [dim]→ {fix}[/dim]")
        passing = [(gn, gv) for gn, gv in sorted(gates.items()) if gv]
        if passing:
            console.print()
            for gn, _ in passing:
                desc, _ = GATE_DESCRIPTIONS.get(gn, (gn, ""))
                console.print(f"  [green]✅ {gn}[/green] — {desc}")

    # Remediation roadmap
    if classification != "PRODUCTION_READY":
        console.print(f"\n[bold yellow]📋 Remediation Roadmap[/bold yellow]")
        if score < 30:
            console.print("[red]CRITICAL: Multiple blocking issues. Prioritize P0→P1→P2 in order.[/red]")
        elif score < 60:
            console.print("[yellow]SIGNIFICANT: P0/P1 issues detected. Fix security & correctness first.[/yellow]")
        elif score < 80:
            console.print("[yellow]MODERATE: Address remaining P2 issues to reach CONDITIONALLY_READY.[/yellow]")
        else:
            console.print("[green]CLOSE: Document remaining limitations to reach PRODUCTION_READY.[/green]")

        console.print(f"\n  Next steps:")
        console.print(f"  1. Run [bold]aura verify[/bold] to see all findings grouped by severity")
        console.print(f"  2. Fix P0 findings first ({result.get('open_p0', '?') if 'open_p0' in result else '?'} remaining)")
        console.print(f"  3. Re-run [bold]aura audit[/bold] to verify fixes")
        console.print(f"  4. Run [bold]aura trend[/bold] to track progress across cycles")
    else:
        console.print(f"\n[bold green]🎉 PRODUCTION READY — All 12 gates pass![/bold green]")


@cli.command()
@click.pass_context
def audit(ctx: click.Context) -> None:
    """Run a full 13-phase audit cycle."""
    engine = Engine(ctx.obj["repo_root"], ctx.obj["config"])
    try:
        engine.initialize()
        result = engine.run_audit()
        if ctx.obj["json"]:
            click.echo(json.dumps(result, indent=2, default=str))
        else:
            _format_audit_result(result)
    except AuraError as e:
        console.print(f"[red]{e}[/red]")
        if ctx.obj["verbose"] and e.detail:
            console.print(f"[dim]{e.detail}[/dim]")
        sys.exit(1)


@cli.command()
@click.pass_context
def status(ctx: click.Context) -> None:
    """Show current engine status."""
    engine = Engine(ctx.obj["repo_root"], ctx.obj["config"])
    try:
        engine.initialize()
        sd = engine.get_status()
        if sd.get("status") == "NOT_INITIALIZED":
            console.print("[yellow]Not initialized. Run 'aura init' first.[/yellow]")
            return
        if ctx.obj["json"]:
            click.echo(json.dumps(sd, indent=2, default=str))
        else:
            cn = sd.get("cycle", "?")
            sc = sd.get("overall_score", 0)
            sc_c = "green" if sc >= 90 else ("yellow" if sc >= 70 else "red")
            console.print(f"\n[bold]Cycle {cn}[/bold] | Phase: {sd.get('phase')} | "
                          f"Status: {sd.get('status')} | "
                          f"Classification: [{'green' if sd.get('classification') == 'PRODUCTION_READY' else 'yellow'}]{sd.get('classification')}[/]")
            console.print(f"Score: [{sc_c}]{sc}/100[/] | "
                          f"Findings: {sd.get('open_findings')} open "
                          f"(P0:{sd.get('open_p0')} P1:{sd.get('open_p1')} P2:{sd.get('open_p2')})")
            gates = sd.get("gates", {})
            if gates:
                pv = sum(1 for v in gates.values() if v)
                console.print(f"Gates: {pv}/{len(gates)} passed")
    except AuraError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)


@cli.command()
@click.pass_context
def health(ctx: click.Context) -> None:
    engine = Engine(ctx.obj["repo_root"], ctx.obj["config"])
    try:
        engine.initialize()
        integrity = engine.db.integrity_check()
        db_ok = len(integrity) == 1 and integrity[0] == "ok"
        if ctx.obj["json"]:
            click.echo(json.dumps({"status": "healthy" if db_ok else "degraded", "version": VERSION, "database": {"path": str(engine.config.database.path), "integrity": "ok" if db_ok else integrity, "exists": Path(engine.config.database.path).exists()}}, indent=2))
        else:
            if db_ok:
                console.print(f"[green]HEALTHY — v{VERSION} — DB: OK[/green]")
            else:
                console.print(f"[red]DEGRADED — {integrity}[/red]")
    except AuraError as e:
        console.print(f"[red]UNHEALTHY: {e}[/red]")
        sys.exit(1)


@cli.command()
@click.pass_context
def doctor(ctx: click.Context) -> None:
    engine = Engine(ctx.obj["repo_root"], ctx.obj["config"])
    issues = []
    console.print(f"\n[bold]AURA v{VERSION} — System Diagnostics[/bold]\n")
    try:
        import subprocess
        r = subprocess.run(["git", "--version"], capture_output=True, text=True, timeout=10)
        if r.returncode == 0:
            console.print(f"[green]✓[/green] git: {r.stdout.strip()}")
        else:
            issues.append("git not found"); console.print("[red]✗[/red] git: NOT FOUND")
    except Exception:
        issues.append("git not found"); console.print("[red]✗[/red] git: NOT FOUND")
    console.print(f"[green]✓[/green] Python: {sys.version.split()[0]}")
    try:
        engine.initialize()
        i = engine.db.integrity_check()
        if len(i) == 1 and i[0] == "ok":
            console.print("[green]✓[/green] Database: OK")
        else:
            issues.append(f"DB: {i}"); console.print(f"[red]✗[/red] DB: {i}")
    except Exception as e:
        issues.append(f"DB: {e}"); console.print(f"[red]✗[/red] DB: {e}")
    console.print("[green]✓[/green] Config: loaded")
    if issues:
        console.print(f"\n[yellow]{len(issues)} issue(s)[/yellow]")
        sys.exit(1)
    else:
        console.print("\n[green]All systems OK[/green]")


@cli.command()
@click.pass_context
def log(ctx: click.Context) -> None:
    engine = Engine(ctx.obj["repo_root"], ctx.obj["config"])
    try:
        engine.initialize()
        entries = engine.db.get_audit_log(limit=50)
        if not entries:
            console.print("[yellow]No audit log entries[/yellow]")
            return
        if ctx.obj["json"]:
            click.echo(json.dumps(entries, indent=2, default=str))
        else:
            console.print(f"\n[bold]13-Phase Audit Trail[/bold]")
            table = Table()
            table.add_column("Phase", style="bold")
            table.add_column("Detail")
            for entry in entries:
                table.add_row(entry.get("event_type", ""), (entry.get("detail", "") or "")[:120])
            console.print(table)
    except AuraError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)


@cli.command()
@click.argument("finding_id", required=False)
@click.option("--fix", is_flag=True, help="Show remediation guidance")
@click.pass_context
def verify(ctx: click.Context, finding_id: str | None, fix: bool) -> None:
    """Verify findings with actionable remediation guidance."""
    engine = Engine(ctx.obj["repo_root"], ctx.obj["config"])
    try:
        engine.initialize()
        findings = engine.db.get_findings()
        open_findings = [f for f in findings if f.get("status") in ("OPEN", "IN_PROGRESS")]

        if fix:
            # Show remediation guide
            console.print("\n[bold]🔧 Remediation Guide[/bold]\n")
            for sev in ["P0", "P1", "P2", "P3"]:
                if sev in REMEDIATION_GUIDE:
                    console.print(f"[bold]{_sev_color(sev)}{sev}[/]")
                    for step in REMEDIATION_GUIDE[sev]:
                        console.print(f"  {step}")
                    console.print()
            console.print("[dim]Use 'aura verify <FINDING_ID>' for per-finding details.[/dim]")
            return

        if finding_id:
            finding = next((f for f in findings if f.get("finding_id") == finding_id), None)
            if not finding:
                if ctx.obj["json"]:
                    click.echo(json.dumps({"error": f"Finding {finding_id} not found"}))
                else:
                    console.print(f"[red]Finding {finding_id} not found[/red]")
                sys.exit(1)
            if ctx.obj["json"]:
                click.echo(json.dumps(finding, indent=2, default=str))
            else:
                sev = finding.get("severity", "?")
                console.print(f"\n[bold]Finding: {finding['finding_id']}[/bold]")
                console.print(f"  Severity: [{_sev_color(sev)}]{sev}[/]  |  Category: {finding.get('category', '?')}  |  Status: {finding.get('status', '?')}")
                console.print(f"  Problem: [yellow]{finding.get('problem', '?')}[/yellow]")
                if finding.get("file_path"):
                    console.print(f"  File: [cyan]{finding['file_path']}[/cyan]:{finding.get('line_number', '')}")
                if finding.get("remediation"):
                    console.print(f"\n  [bold green]🔧 Fix:[/bold green] {finding['remediation']}")
                if finding.get("evidence"):
                    console.print(f"  [dim]Evidence: {str(finding.get('evidence', ''))[:200]}[/dim]")

                # Show remediation steps for this severity
                steps = REMEDIATION_GUIDE.get(sev, [])
                if steps:
                    console.print(f"\n  [bold]Remediation Steps:[/bold]")
                    for step in steps:
                        console.print(f"    {step}")
        else:
            if ctx.obj["json"]:
                click.echo(json.dumps({"open_findings": open_findings, "count": len(open_findings),
                    "p0": len([f for f in open_findings if f.get("severity") == "P0"]),
                    "p1": len([f for f in open_findings if f.get("severity") == "P1"]),
                    "p2": len([f for f in open_findings if f.get("severity") == "P2"])}, indent=2, default=str))
            else:
                if not open_findings:
                    console.print("[green]✅ No open findings — all issues resolved![/green]")
                    return

                by_sev: dict[str, list] = {}
                for f in open_findings:
                    sev = f.get("severity", "?")
                    by_sev.setdefault(sev, []).append(f)

                total = len(open_findings)
                p0_count = len(by_sev.get("P0", []))
                p1_count = len(by_sev.get("P1", []))
                console.print(f"\n[bold]{total} Open Findings[/bold] "
                              f"(P0: {p0_count} | P1: {p1_count} | "
                              f"P2: {len(by_sev.get('P2',[]))} | "
                              f"P3: {len(by_sev.get('P3',[]))} | "
                              f"P4: {len(by_sev.get('P4',[]))} | "
                              f"P5: {len(by_sev.get('P5',[]))})")

                for sev in ["P0", "P1", "P2", "P3", "P4", "P5"]:
                    items = by_sev.get(sev, [])
                    if not items:
                        continue
                    console.print(f"\n[bold]{_sev_color(sev)}{sev} ({len(items)})[/]")
                    for f in items[:10]:  # limit per severity
                        fid = f.get("finding_id", "?")
                        cat = f.get("category", "?")
                        prob = (f.get("problem", "") or "")[:80]
                        fpath = f.get("file_path", "")
                        loc = f" [dim]{fpath}[/dim]" if fpath else ""
                        console.print(f"  • [{cat}] {prob}{loc}")
                    if len(items) > 10:
                        console.print(f"  [dim]... and {len(items) - 10} more[/dim]")

                console.print(f"\n[dim]Run [bold]aura verify --fix[/bold] for remediation guidance.")
                console.print(f"[dim]Run [bold]aura verify <ID>[/bold] for per-finding details.[/dim]")
    except AuraError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)


def _sev_color(sev: str) -> str:
    return {"P0": "red", "P1": "red", "P2": "yellow", "P3": "yellow", "P4": "blue", "P5": "dim"}.get(sev, "white")


@cli.command()
@click.option("--output", "-o", default=None, help="Output file path")
@click.pass_context
def report(ctx: click.Context, output: str | None) -> None:
    engine = Engine(ctx.obj["repo_root"], ctx.obj["config"])
    try:
        text = engine.generate_report()
        if output:
            Path(output).write_text(text, encoding="utf-8")
            console.print(f"[green]✅ Report saved to {output}[/green]")
        else:
            console.print(text)
    except AuraError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)


@cli.command()
@click.pass_context
def trend(ctx: click.Context) -> None:
    engine = Engine(ctx.obj["repo_root"], ctx.obj["config"])
    try:
        engine.initialize()
        td = engine.get_trend()
        if not td:
            console.print("[yellow]Need 2+ cycles. Run 'aura audit' first.[/yellow]")
            return
        if ctx.obj["json"]:
            click.echo(json.dumps(td, indent=2, default=str))
        else:
            di = {"improving": "📈 IMPROVING", "declining": "📉 DECLINING", "stable": "➡️ STABLE"}
            console.print(f"\n[bold]{di.get(td['trend']['direction'], '❓')}[/bold]")
            table = Table(title="Cycle History")
            table.add_column("Cycle", style="bold")
            table.add_column("Score")
            table.add_column("Findings")
            table.add_column("Gates")
            table.add_column("Classification")
            for c in td["all_cycles"]:
                sc = c["score"]
                sc_c = "green" if sc >= 90 else ("yellow" if sc >= 70 else "red")
                table.add_row(str(c["cycle"]), f"[{sc_c}]{sc}[/]", str(c["findings"]),
                              f"{c['gates_passed']}/12", c["classification"])
            console.print(table)
            delta_s = td["trend"]["score_delta"]
            delta_f = td["trend"]["findings_delta"]
            console.print(f"\nScore: [{'green' if delta_s >=0 else 'red'}]{delta_s:+d}[/] | "
                          f"Findings: [{'red' if delta_f > 0 else 'green'}]{delta_f:+d}[/]")
    except AuraError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)


def main() -> None:
    cli(obj={})


@cli.command()
@click.option("--dry-run", is_flag=True, help="Preview fixes without applying")
@click.option("--max-cycles", default=5, help="Maximum autonomous cycles (default: 5)")
@click.option("--resume", is_flag=True, help="Resume from last checkpoint")
@click.option("--llm-url", default="http://localhost:20128/v1", help="LLM API URL")
@click.option("--llm-key", default=None, help="LLM API key (default: $AURA_LLM_KEY)")
@click.option("--llm-model", default="streamlake/deepseek-v4-pro", help="LLM model name")
@click.option("--timeout", default=120, help="LLM request timeout in seconds")
@click.pass_context
def auto_fix(ctx: click.Context, dry_run: bool, max_cycles: int,
             resume: bool, llm_url: str, llm_key: str, llm_model: str,
             timeout: int) -> None:
    """Run autonomous audit→fix→verify→re-audit loop until converged.

    Uses LLM to generate code fixes, applies them, verifies with tooling,
    and repeats until all convergence gates pass or max cycles reached.

    Use --dry-run to preview changes without modifying files.
    Use --resume to continue from the last checkpoint after a timeout.
    """
    from .durable import CheckpointManager, DurableAutonomousLoop
    from .llm import ProviderBackedLLMClient
    from .providers import ProviderRegistry, OpenAICompatibleProvider

    # P0 SECURITY: llm-key defaults to env var, never hardcoded
    if not llm_key:
        llm_key = os.environ.get("AURA_LLM_KEY", "")
    if not llm_key:
        console.print("[red]LLM API key required. Set AURA_LLM_KEY env var or use --llm-key.[/red]")
        sys.exit(1)

    engine = Engine(ctx.obj["repo_root"], ctx.obj["config"])

    # Use ProviderRegistry with circuit breaker for resilience
    registry = ProviderRegistry()
    primary_provider = OpenAICompatibleProvider(
        name="primary",
        base_url=llm_url,
        api_key=llm_key,
        model=llm_model,
        timeout=timeout,
        max_retries=3,
    )
    registry.register(primary_provider, priority=0)

    # Detect local Ollama as fallback if available
    ollama_host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
    try:
        import httpx
        resp = httpx.get(f"{ollama_host}/api/tags", timeout=3)
        if resp.status_code == 200:
            ollama_models = resp.json().get("models", [])
            if ollama_models:
                fallback_model = ollama_models[0].get("name", "llama3")
                ollama_provider = OpenAICompatibleProvider(
                    name="ollama-fallback",
                    base_url=f"{ollama_host}/v1",
                    api_key="ollama",
                    model=fallback_model,
                    timeout=timeout,
                )
                registry.register(ollama_provider, priority=1)
                console.print(f"[dim]Ollama fallback registered: {fallback_model}[/dim]")
    except Exception:
        pass

    # Canonical adapter — ProviderRegistry is the single resilience layer.
    # (Previously an inline _RegistryLLMWrapper class defined per-invocation.)
    llm = ProviderBackedLLMClient(registry, default_model=llm_model)
    engine.llm = llm  # type: ignore[attr-defined]
    engine.autonomous = AutonomousRemediationLoop(  # type: ignore[attr-defined]
        engine, llm, max_cycles=max_cycles, dry_run=dry_run)
    durable = DurableAutonomousLoop(engine.autonomous,  # type: ignore[attr-defined]
                                    ctx.obj["repo_root"])

    mode = "[yellow]DRY-RUN[/yellow]" if dry_run else "[red]LIVE[/red]"
    res_mode = " [RESUMING]" if resume else ""

    if resume:
        cp = CheckpointManager(ctx.obj["repo_root"])
        progress = cp.get_progress()
        if progress["status"] == "no_checkpoint":
            console.print("[yellow]No checkpoint found — starting from scratch.[/yellow]")
        else:
            console.print(f"[green]Resuming from cycle {progress['cycles_completed']}[/green]")
            console.print(f"  Score: {progress.get('last_score','?')} | "
                          f"Findings: {progress.get('last_findings','?')} | "
                          f"Classification: {progress.get('last_classification','?')}")

    console.print(f"\n[bold]🤖 AURA Autonomous Remediation Loop[/bold] — {mode}{res_mode}")
    console.print(f"   LLM: {llm_model} | Max cycles: {max_cycles} | Timeout: {timeout}s")
    console.print(f"   Flow: [dim]AUDIT → FIX → VERIFY → RE-AUDIT → repeat[/dim]")
    console.print()

    result = durable.run_or_resume(max_cycles)

    console.print(f"\n[bold]═══ Result ═══[/bold]")
    outcome_color = "green" if result["converged"] else "yellow"
    console.print(f"  Outcome: [{outcome_color}]{result['outcome']}[/{outcome_color}]")
    console.print(f"  Cycles: {result['cycles_completed']}")
    console.print(f"  Message: {result['message']}")

    console.print(f"\n[bold]Cycle Log:[/bold]")
    table = Table()
    table.add_column("Cycle")
    table.add_column("Score")
    table.add_column("Class")
    table.add_column("Findings")
    table.add_column("Fixes")
    table.add_column("OK")
    for entry in result.get("cycle_log", []):
        table.add_row(
            str(entry["cycle"]),
            str(entry["score"]),
            entry["classification"],
            str(entry["findings"]),
            str(entry.get("fixes_applied", 0)),
            str(entry.get("fixes_succeeded", 0)),
        )
    console.print(table)

    # Show provider health status
    statuses = registry.get_all_statuses()
    if statuses:
        console.print(f"\n[dim]Provider health: " +
                      ", ".join(f"{k}: {v.health.value}" for k, v in statuses.items()) +
                      "[/dim]")

    if result["converged"]:
        console.print("\n[bold green]🎉 CONVERGED — Project is PRODUCTION READY![/bold green]")
    else:
        console.print(f"\n[yellow]⚠ Not converged — {result['outcome']}[/yellow]")


if __name__ == "__main__":
    main()