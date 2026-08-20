import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import get_config
from .state_manager import StateManager, sanitize_prompt_string, write_text_file, read_json_file
from .git_controller import get_git_context
from .tooling import get_project_tooling


def load_locale(locale_code: str = "en", repo_root: Optional[str] = None) -> Optional[dict]:
    if repo_root is None:
        return None

    root = Path(repo_root)
    candidates = [root / ".aura" / "lang", root / "src" / "lang"]

    for candidate in candidates:
        if candidate.is_dir():
            lang_file = candidate / "{}.json".format(locale_code)
            if lang_file.exists():
                try:
                    return json.loads(lang_file.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    continue
            fallback = candidate / "en.json"
            if fallback.exists():
                try:
                    return json.loads(fallback.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    continue

    return None


def get_l10n(locale_data: Optional[dict], key: str, replacements: Optional[dict] = None) -> str:
    if locale_data is None:
        return "[MISSING:{}]".format(key)

    parts = key.split(".")
    current: Any = locale_data
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return "[MISSING:{}]".format(key)
        if current is None:
            return "[MISSING:{}]".format(key)

    if not isinstance(current, str):
        return "[MISSING:{}]".format(key)

    result = str(current)
    if replacements:
        for rk, rv in replacements.items():
            result = result.replace("{" + rk + "}", str(rv))

    return result


def get_findings_summary(findings: Optional[dict]) -> str:
    if not findings or not findings.get("findings"):
        return "No findings recorded yet."

    findings_list = findings["findings"]
    by_severity: Dict[str, int] = {}
    by_status: Dict[str, int] = {}

    for f in findings_list:
        sev = f.get("severity", "UNKNOWN")
        st = f.get("status", "UNKNOWN")
        by_severity[sev] = by_severity.get(sev, 0) + 1
        by_status[st] = by_status.get(st, 0) + 1

    lines = []
    lines.append("---")
    lines.append("## CURRENT FINDINGS LEDGER")
    lines.append("")
    lines.append("### By Severity")
    for sev in sorted([k for k in by_severity.keys() if k is not None]):
        lines.append("- **{}** : {}".format(sev, by_severity[sev]))
    lines.append("")
    lines.append("### By Status")
    for st in sorted([k for k in by_status.keys() if k is not None]):
        lines.append("- **{}** : {}".format(st, by_status[st]))
    lines.append("")
    lines.append("### Open P0-P2")
    open_findings = [f for f in findings_list
                     if f.get("severity") in ("P0", "P1", "P2")
                     and f.get("status") in ("OPEN", "IN_PROGRESS")]
    if not open_findings:
        lines.append("*None*")
    else:
        for f in open_findings:
            lines.append("- **{}** | {} | {} | {}".format(
                f.get("id", "?"), f.get("severity", "?"),
                f.get("category", "?"), sanitize_prompt_string(f.get("problem", ""))
            ))

    return "\n".join(lines)


def generate_cycle_prompt(project_path: str, state_mgr: StateManager,
                           is_multi_agent: bool = False, language: str = "en",
                           repo_root: Optional[str] = None) -> dict:
    full_project_path = str(Path(project_path).resolve())
    config = get_config(repo_root or str(Path(full_project_path).parent))
    state = state_mgr.read_cycle()
    findings = state_mgr.read_findings()
    conv = state_mgr.read_convergence()

    current_cycle = (state.get("current_cycle", 0) or 0) + 1 if state else 1
    max_cycles = config.max_cycles
    max_no_progress = config.max_cycles_without_progress

    cycles_without_progress = state.get("cycles_without_progress", 0) or 0 if state else 0
    conv_classification = str(conv.get("classification", "UNKNOWN")) if conv else "UNKNOWN"
    conv_converged = str(conv.get("converged", "UNKNOWN")) if conv else "UNKNOWN"

    git_ctx = get_git_context(full_project_path)
    tooling = get_project_tooling(full_project_path)
    findings_summary = get_findings_summary(findings)

    locale_data = load_locale(language, repo_root)

    def __(key: str, replacements: Optional[dict] = None) -> str:
        return get_l10n(locale_data, key, replacements)

    tooling_block = ""
    tooling_cmds = tooling.get("commands", {})
    if tooling_cmds:
        cmd_header = __("prompt.tooling_table_header_command")
        script_header = __("prompt.tooling_table_header_script")
        det_header = __("prompt.detected_tooling_header")
        tooling_block = "\n## {}\n\n| {} | {} |\n|---------|--------|".format(
            det_header, cmd_header, script_header
        )
        for cmd in sorted(tooling_cmds.keys()):
            val = tooling_cmds[cmd] or "(detected, verify exact command)"
            safe_cmd = sanitize_prompt_string(cmd)
            safe_val = sanitize_prompt_string(val)
            tooling_block += "\n| ``{}`` | ``{}`` |".format(safe_cmd, safe_val)

    manifest_block = ""
    tooling_files = tooling.get("files", [])
    if tooling_files:
        manifest_header = __("prompt.project_manifest_header")
        manifest_block = "\n## {}\n\n".format(manifest_header)
        for f in tooling_files:
            safe_name = sanitize_prompt_string(f)
            manifest_block += "- ``{}``\n".format(safe_name)

    safe_branch = sanitize_prompt_string(git_ctx.get("Branch", ""))
    safe_commits = sanitize_prompt_string(git_ctx.get("RecentCommits", ""))
    safe_status = sanitize_prompt_string(git_ctx.get("Status", ""))
    safe_project_path = sanitize_prompt_string(full_project_path)
    safe_last_commit_msg = sanitize_prompt_string(git_ctx.get("LastCommitMsg", ""))
    safe_last_commit_hash = sanitize_prompt_string(git_ctx.get("LastCommitHash", ""))
    git_error_note = ""
    if git_ctx.get("GitError"):
        git_error_note = "\n" + __("prompt.git_error_note") + "\n"

    scale_note = ""
    file_count = int(git_ctx.get("FileCount", 0) or 0)
    if file_count > 500:
        scale_note = "\n" + __("prompt.scale_warning_500", {"count": str(file_count)}) + "\n"
    if file_count > 2000:
        scale_note = "\n" + __("prompt.scale_warning_2000", {"count": str(file_count)}) + "\n"

    if is_multi_agent:
        ma_header = __("prompt.multi_agent_mode")
        ma_intro = __("prompt.multi_agent_intro")
        ma1 = __("prompt.multi_agent_1")
        ma2 = __("prompt.multi_agent_2")
        ma3 = __("prompt.multi_agent_3")
        ma4 = __("prompt.multi_agent_4")
        ma5 = __("prompt.multi_agent_5")
        ma6 = __("prompt.multi_agent_6")
        ma7 = __("prompt.multi_agent_7")
        ma_par = __("prompt.multi_agent_parallel_note")
        multi_agent_block = """
## {}

{}

1. {}
2. {}
3. {}
4. {}
5. {}
6. {}
7. {}

{}
""".format(ma_header, ma_intro, ma1, ma2, ma3, ma4, ma5, ma6, ma7, ma_par)
    else:
        sa_header = __("prompt.single_agent_mode")
        sa_body = __("prompt.single_agent_body")
        multi_agent_block = """
## {}

{}
""".format(sa_header, sa_body)

    pa_header = __("prompt.push_approval_header")
    pa_intro = __("prompt.push_approval_intro")
    pa_now = __("prompt.push_now")
    pa_later = __("prompt.push_later")
    pa_now_desc = __("prompt.push_now_desc")
    pa_later_desc = __("prompt.push_later_desc")
    pa_b1 = __("prompt.push_now_behavior_1")
    pa_b2 = __("prompt.push_now_behavior_2")
    pa_b3 = __("prompt.push_now_behavior_3")
    pa_b4 = __("prompt.push_now_behavior_4")
    pa_b5 = __("prompt.push_now_behavior_5")
    pa_b6 = __("prompt.push_now_behavior_6")
    pa_b7 = __("prompt.push_now_behavior_7")
    pa_late_b = __("prompt.push_later_behavior")

    push_approval_block = """

---

## {}

{}

```
=== PUSH APPROVAL ===
Cycle: <N> | Classification: <X> | Open P0-P2: <N>
Files staged: [list of engine files]

[{}]  -- {}
[{}] -- {}
```

### {} behavior (engine invokes via -Action push -Approve):
1. {}
2. {}
3. {}
4. {}
5. {}
6. {}
7. {}

### {} behavior:
- {}

---

""".format(pa_header, pa_intro, pa_now, pa_now_desc, pa_later, pa_later_desc,
           pa_now, pa_b1, pa_b2, pa_b3, pa_b4, pa_b5, pa_b6, pa_b7,
           pa_later, pa_late_b)

    title = __("prompt.title", {"cycle": str(current_cycle)})
    ed_header = __("prompt.engine_directive_header")
    ed1 = __("prompt.engine_directive_line1", {"cycle": str(current_cycle)})
    ed2 = __("prompt.engine_directive_line2")
    ed3 = __("prompt.engine_directive_line3")
    ed4 = __("prompt.engine_directive_line4")
    sm_header = __("prompt.state_machine_header")
    sm_intro = __("prompt.state_machine_intro")
    ft_header = __("prompt.finding_transitions_header")
    ce_header = __("prompt.convergence_enforcement_header")
    te_header = __("prompt.tool_execution_header")
    te1 = __("prompt.tool_execution_item1")
    te2 = __("prompt.tool_execution_item2")
    te3 = __("prompt.tool_execution_item3")
    te4 = __("prompt.tool_execution_item4")
    sa_header2 = __("prompt.scale_awareness_header")
    sa1 = __("prompt.scale_awareness_item1")
    sa2 = __("prompt.scale_awareness_item2")
    sa3 = __("prompt.scale_awareness_item3")
    sa4 = __("prompt.scale_awareness_item4")
    vw = __("prompt.violation_warning")
    ic_header = __("prompt.injected_context_header")
    gs_header = __("prompt.git_state_header")
    br_label = __("prompt.branch_label")
    rc_label = __("prompt.recent_commits_label")
    lc_label = __("prompt.last_commit_label")
    wt_label = __("prompt.working_tree_label")
    fc_label = __("prompt.file_count_label")
    es_header = __("prompt.engine_state_header")
    cy_label = __("prompt.cycle_label")
    max_label = __("prompt.max_label")
    cwp_label = __("prompt.cycles_without_progress_label")
    lcl_label = __("prompt.last_classification_label")
    cs_label = __("prompt.convergence_status_label")
    nf_label = __("prompt.no_findings")
    sms_header = __("prompt.state_machine_status_header")
    sai = __("prompt.state_authority_isolation")
    wp1 = __("prompt.write_to_proposed_1")
    wp2 = __("prompt.write_to_proposed_2")
    wp3 = __("prompt.write_to_proposed_3")
    wp4 = __("prompt.write_to_proposed_4")
    psh = __("prompt.promote_state_hint")
    ter_header = __("prompt.tool_execution_required_header")
    tes1 = __("prompt.tool_execution_step1")
    tes2 = __("prompt.tool_execution_step2")
    tes3 = __("prompt.tool_execution_step3")
    tew = __("prompt.tool_execution_warning")
    ci_header = __("prompt.cycle_instructions_header")
    ci_note = __("prompt.cycle_instructions_note")
    ci_intro = __("prompt.cycle_instructions_intro")
    ma_header2 = __("prompt.mandatory_audit_header")
    ma_warn = __("prompt.mandatory_audit_warning")
    ma_intro2 = __("prompt.mandatory_audit_intro")
    ma_1 = __("prompt.mandatory_audit_1", {"project_path": safe_project_path})
    ma_2 = __("prompt.mandatory_audit_2")
    ma_3 = __("prompt.mandatory_audit_3")
    ma_4 = __("prompt.mandatory_audit_4")
    ma_5 = __("prompt.mandatory_audit_5")
    ma_6 = __("prompt.mandatory_audit_6")
    cg_header = __("prompt.convergence_gate_header")
    cg_intro = __("prompt.convergence_gate_intro")
    cg1 = __("prompt.convergence_gate_1")
    cg2 = __("prompt.convergence_gate_2")
    cg3 = __("prompt.convergence_gate_3")
    cg4 = __("prompt.convergence_gate_4")
    cg5 = __("prompt.convergence_gate_5")
    cg6 = __("prompt.convergence_gate_6")
    cg7 = __("prompt.convergence_gate_7")
    tr_header = __("prompt.target_repository_header")
    tr1 = __("prompt.target_repository_line1", {"project_path": safe_project_path})
    tr2 = __("prompt.target_repository_line2")
    ac_header = __("prompt.after_cycle_header")
    ac_intro = __("prompt.after_cycle_intro")
    acwi = __("prompt.after_cycle_write_intro")
    acpc = __("prompt.after_cycle_proposed_cycle")
    acpf = __("prompt.after_cycle_proposed_findings")
    acpconv = __("prompt.after_cycle_proposed_convergence")
    acpt = __("prompt.after_cycle_proposed_tooling")
    acow = __("prompt.after_cycle_orchestrator_will")
    aco1 = __("prompt.after_cycle_orch_1")
    aco2 = __("prompt.after_cycle_orch_2")
    aco3 = __("prompt.after_cycle_orch_3")
    aco4 = __("prompt.after_cycle_orch_4")
    aco5 = __("prompt.after_cycle_orch_5")
    aco6 = __("prompt.after_cycle_orch_6")
    acmw = __("prompt.after_cycle_must_write")
    acur = __("prompt.after_cycle_update_reports")
    acv = __("prompt.after_cycle_verdict")
    acpa = __("prompt.after_cycle_push_approval")
    acc = __("prompt.after_cycle_critical")
    acs = __("prompt.after_cycle_stop")
    acr = __("prompt.after_cycle_remember")
    bc = __("prompt.begin_cycle", {"cycle": str(current_cycle)})

    findings_summary_display = findings_summary
    if not findings_summary_display.strip():
        findings_summary_display = nf_label

    session_prompt = """# {}

## {}

{}

{}

## {}

{}

### {}
- ``OPEN`` -> only ``IN_PROGRESS``, ``DEFERRED``, or ``BLOCKED``
- ``IN_PROGRESS`` -> only ``FIXED``, ``DEFERRED``, ``BLOCKED``, or ``OPEN``
- ``FIXED`` -> only ``VERIFYING`` or ``OPEN`` (regression)
- ``VERIFYING`` -> only ``VERIFIED``, ``REJECTED``, or ``FIXED`` (retry)
- ``VERIFIED`` -> only ``OPEN`` (recurrence)
- **FORBIDDEN: OPEN -> VERIFIED** (must pass FIXED + VERIFYING)
- **FORBIDDEN: OPEN -> FIXED** (must pass IN_PROGRESS)

### {}
- Any gate flipping from ``false`` to ``true`` requires evidence (which the orchestrator checks)
- ``consecutive_converged_cycles`` can only increase by 0 or 1 per cycle
- ``overall_score`` cannot decrease between cycles
- ``overall_score`` cannot increase by more than 15 per cycle
- ``converged`` can only become ``true`` when ALL 12 gates pass including ``module_dependency_integrity``
- Classification transitions are restricted to valid paths

### {}
- {}
- {}
- {}
- {}

### {}
- {}
- {}
- {}
- {}

{}

---

---

## {}

### {}

{}
{} ``{}``

{}
````
{}
````

{} ``{}`` -- ``{}``

{}
````
{}
````

{} {}
{}
### {}

**{}** {} / {} {}
**{}** {} / {} {}
**{}** {}
**{}** {}
{}
{}
{}

### {}

{}

- {}
- {}
- {}
- {}

{}

**{}**
1. {}
2. {}
3. {}
{}

---

## {}

{}

{}

1. ``.aura/docs/master.md`` - audit rules, standards, methodology
2. ``.aura/docs/cycle.md`` - per-cycle phases (Phase 1-13)
3. ``.aura/reports/architecture-map.md`` - prior architecture model
4. ``.aura/reports/risk-register.md`` - prior risk register
5. ``.aura/reports/remediation-log.md`` - prior remediation history
6. ``.aura/reports/verification-matrix.md`` - prior verification evidence
7. ``.aura/reports/audit-ledger.md`` - full finding history
8. ``.aura/state/findings.json`` - machine-readable findings
9. ``.aura/state/convergence.json`` - convergence gate history

## {}

{}

{}

1. {}
2. {}
3. {}
4. {}
5. {}
6. {}

## {}

{}

- {}
- {}
- {}
- {}
- {}
- {}
- {}

## {}

{}

{}

**``{}``**

---

## {}

{}

{}

1. {}
2. {}
3. {}
4. {}

{}
- {}
- {}
- {}
- {}
- {}
- {}

{}

5. {}
6. {}
7. {}

{}

{}

{}
{}
{}

---
{}
""".format(
        title, ed_header, ed1, ed2, ed3, ed4,
        sm_header, sm_intro,
        ft_header, ce_header, te_header, te1, te2, te3, te4,
        sa_header2, sa1, sa2, sa3, sa4,
        vw, ic_header, gs_header,
        git_error_note, br_label, safe_branch,
        rc_label, safe_commits,
        lc_label, safe_last_commit_hash, safe_last_commit_msg,
        wt_label, safe_status,
        fc_label, file_count,
        scale_note, es_header,
        cy_label, current_cycle, max_label, max_cycles,
        cwp_label, cycles_without_progress, max_label, max_no_progress,
        lcl_label, conv_classification,
        cs_label, conv_converged,
        findings_summary_display,
        manifest_block, tooling_block,
        sms_header, sai,
        wp1, wp2, wp3, wp4,
        psh,
        ter_header, tes1, tes2, tes3, tew,
        ci_header, ci_note, ci_intro,
        ma_header2, ma_warn, ma_intro2,
        ma_1, ma_2, ma_3, ma_4, ma_5, ma_6,
        cg_header, cg_intro,
        cg1, cg2, cg3, cg4, cg5, cg6, cg7,
        tr_header, tr1, tr2,
        safe_project_path,
        ac_header, ac_intro, acwi,
        acpc, acpf, acpconv, acpt,
        acow, aco1, aco2, aco3, aco4, aco5, aco6,
        acmw, acur, acv, acpa,
        acc, acs, acr,
        multi_agent_block, push_approval_block, bc,
    )

    return {
        "prompt": session_prompt,
        "cycle": current_cycle,
        "projectPath": full_project_path,
        "gitContext": git_ctx,
        "tooling": tooling,
    }