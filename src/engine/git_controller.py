import os
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional


def get_git_context(project_path: str) -> Dict[str, Any]:
    context: Dict[str, Any] = {}

    try:
        subprocess.run(["git", "--version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        context["Error"] = "git not installed or not on PATH"
        return context

    def _git(args, cwd):
        try:
            result = subprocess.run(["git"] + args, capture_output=True, text=True,
                                    cwd=cwd)
            if result.returncode != 0:
                context["GitError"] = True
                return ""
            return result.stdout.strip()
        except Exception:
            context["GitError"] = True
            return ""

    context["Status"] = _git(["status", "--short"], project_path)
    context["DiffStat"] = _git(["diff", "--stat", "HEAD"], project_path)
    context["RecentCommits"] = _git(["log", "--oneline", "--max-count=15"], project_path)
    context["Branch"] = _git(["branch", "--show-current"], project_path)
    context["LastCommitMsg"] = _git(["log", "-1", "--format=%s"], project_path)
    context["LastCommitHash"] = _git(["log", "-1", "--format=%H"], project_path)

    try:
        result = subprocess.run(["git", "ls-files"], capture_output=True, text=True,
                                cwd=project_path, shell=False)
        if result.returncode == 0:
            context["FileCount"] = len([l for l in result.stdout.splitlines() if l.strip()])
        else:
            context["FileCount"] = 0
            context["GitError"] = True
    except Exception:
        context["FileCount"] = 0
        context["GitError"] = True

    return context


def get_push_working_set(project_root: str, engine_root: str, repo_root: str) -> list:
    files = []
    runtime_path = Path(engine_root)

    for dir_name in ["state", "reports", "docs", "agents", "lang"]:
        d = runtime_path / dir_name
        if d.is_dir():
            for f in d.iterdir():
                if f.is_file():
                    files.append(str(f))

    repo = Path(repo_root)
    src_modules_dir = repo / "src" / "modules"
    if src_modules_dir.is_dir():
        for f in src_modules_dir.iterdir():
            if f.is_file():
                files.append(str(f))

    src_agents_dir = repo / "src" / "agents"
    if src_agents_dir.is_dir():
        for f in src_agents_dir.iterdir():
            if f.is_file():
                files.append(str(f))

    src_lang_dir = repo / "src" / "lang"
    if src_lang_dir.is_dir():
        for f in src_lang_dir.iterdir():
            if f.is_file():
                files.append(str(f))

    config_file = repo / "config" / "aura.json"
    if config_file.exists():
        files.append(str(config_file))

    ps_script = repo / "src" / "engine" / "run-audit.ps1"
    if ps_script.exists():
        files.append(str(ps_script))

    py_engine = repo / "src" / "engine" / "aura_engine.py"
    if py_engine.exists():
        files.append(str(py_engine))

    project = Path(project_root)
    aura_proxy = project / ".aura" / "run-audit.ps1"
    if aura_proxy.exists():
        files.append(str(aura_proxy))

    root_files = ["README.md", "run-audit.sh", "bin/aura.ps1", "bin/aura.sh",
                  ".gitignore", ".gitattributes", ".gitmessage"]
    for rf in root_files:
        rp = project / rf
        if rp.exists():
            files.append(str(rp))

    return sorted(set(files))


def get_push_summary(state: Optional[dict], findings: Optional[dict], conv: Optional[dict]) -> dict:
    cycle = state.get("current_cycle", "?") if state else "?"
    classification = conv.get("classification", "UNKNOWN") if conv else "UNKNOWN"

    def count(sev: str) -> int:
        if findings and findings.get("findings"):
            return sum(1 for f in findings["findings"]
                       if f.get("severity") == sev and f.get("status") != "VERIFIED")
        return 0

    p0, p1, p2 = count("P0"), count("P1"), count("P2")

    if p0 == 0 and p1 == 0 and p2 == 0:
        summary_type = "clean"
    elif p0 == 0 and p1 == 0:
        summary_type = "minor"
    else:
        summary_type = "critical"

    return {
        "cycle": cycle,
        "classification": classification,
        "p0_open": p0,
        "p1_open": p1,
        "p2_open": p2,
        "summaryType": summary_type,
    }


def invoke_engine_push(project_root: str, engine_root: str, repo_root: str,
                       force_approve: bool = False, amend: bool = False,
                       config: Optional[Any] = None,
                       rich_console: Optional[Any] = None) -> bool:

    from .config import get_config as _get_config
    from .state_manager import StateManager

    if config is None:
        config = _get_config(repo_root)

    state_mgr = StateManager(engine_root)
    state = state_mgr.read_cycle()
    findings = state_mgr.read_findings()
    conv = state_mgr.read_convergence()

    summary = get_push_summary(state, findings, conv)
    files = get_push_working_set(project_root, engine_root, repo_root)

    relative_files = []
    pr = str(Path(project_root).resolve())
    for f in files:
        try:
            rel = str(Path(f).resolve()).replace(pr, "").lstrip("\\").lstrip("/")
            relative_files.append(rel)
        except Exception:
            pass

    prt = print
    if rich_console:
        from rich.console import Console
        if isinstance(rich_console, Console):
            def prt(*args, **kwargs):
                style = kwargs.pop("style", None)
                text = " ".join(str(a) for a in args)
                if style:
                    rich_console.print(text, style=style)
                else:
                    rich_console.print(text)
        else:
            prt = rich_console.print

    if not force_approve:
        prt("[INFO] Push requires explicit approval. Use -Approve flag to auto-approve,", style="info")
        prt("        or call this function interactively from supported environments.", style="info")
        from .config import get_config as _gc
        cfg = _gc(repo_root)
        if cfg.push_require_interactive_fallback:
            prt("[INTERACTIVE] Running push in interactive mode.", style="warn")
        else:
            return False

    prt("Push auto-approved via -Approve flag.", style="green")

    push_enabled = config.push_enabled
    if not push_enabled:
        prt("[SKIP] Push is disabled in config.json (push.enabled = false).", style="yellow")
        return False

    try:
        git_check = subprocess.run(["git", "rev-parse", "--git-dir"],
                                    capture_output=True, text=True, cwd=project_root, shell=False)
        if git_check.returncode != 0:
            prt("[ERROR] Not a git repository or git not available.", style="red")
            return False
    except Exception:
        prt("[ERROR] Not a git repository or git not available.", style="red")
        return False

    prt("Files to stage:", style="yellow")
    for rf in sorted(relative_files):
        prt("  + {}".format(rf))
    prt("")

    status_result = subprocess.run(["git", "status", "--porcelain"],
                                    capture_output=True, text=True, cwd=project_root, shell=False)
    all_modified = []
    if status_result.returncode == 0:
        for line in status_result.stdout.splitlines():
            path_part = line[3:].strip()
            if path_part:
                all_modified.append(path_part.replace("\\", "/").lstrip("/"))

    engine_set = set()
    for rf in relative_files:
        engine_set.add(rf.replace("\\", "/").lstrip("/"))

    non_engine_modified = [f for f in all_modified if f not in engine_set and f]
    if non_engine_modified:
        prt("[WARNING] Non-engine files modified in working tree:", style="yellow")
        for f in non_engine_modified:
            prt("  ! {}".format(f), style="yellow")
        prt("  These files will NOT be staged, reset, or modified.")
        prt("")

    commit_template = config.push_commit_template
    commit_msg = commit_template.replace("{cycle}", str(summary["cycle"]))
    commit_msg = commit_msg.replace("{classification}", str(summary["classification"]))
    commit_msg = commit_msg.replace("{summary}", str(summary["summaryType"]))

    import uuid
    import tempfile
    temp_index = os.path.join(tempfile.gettempdir(), "aura-push-{}.index".format(uuid.uuid4().hex[:8]))
    old_index = os.environ.get("GIT_INDEX_FILE")

    try:
        os.environ["GIT_INDEX_FILE"] = temp_index
        prt("[GIT] Using transactional staging (temp index: {})".format(os.path.basename(temp_index)), style="cyan")

        staging_ok = True
        for rf in relative_files:
            result = subprocess.run(["git", "add", ":(literal)" + rf],
                                     capture_output=True, cwd=project_root, shell=False)
            if result.returncode != 0:
                prt("[WARNING] Failed to stage: {}".format(rf), style="yellow")
                staging_ok = False

        if not staging_ok:
            if old_index:
                os.environ["GIT_INDEX_FILE"] = old_index
            else:
                del os.environ["GIT_INDEX_FILE"]
            if os.path.exists(temp_index):
                os.remove(temp_index)
            return False

        temp_staged = subprocess.run(["git", "diff", "--cached", "--name-only"],
                                      capture_output=True, text=True, cwd=project_root, shell=False)
        staged_lines = [l.strip() for l in temp_staged.stdout.splitlines() if l.strip()]
        non_engine_staged = [f for f in staged_lines
                             if f.replace("\\", "/").lstrip("/") not in engine_set]
        if non_engine_staged:
            prt("[GIT] TRANSACTION ABORTED -- non-engine files staged in temp index:", style="red")
            for f in non_engine_staged:
                prt("  ! {}".format(f), style="red")
            if old_index:
                os.environ["GIT_INDEX_FILE"] = old_index
            else:
                del os.environ["GIT_INDEX_FILE"]
            if os.path.exists(temp_index):
                os.remove(temp_index)
            return False

        if amend:
            amend_result = subprocess.run(["git", "commit", "--amend", "--no-edit"],
                                           capture_output=True, cwd=project_root, shell=False)
            if amend_result.returncode != 0:
                prt("[WARNING] Amend failed. Creating new commit instead.", style="yellow")
                subprocess.run(["git", "commit", "-m", commit_msg],
                               capture_output=True, cwd=project_root, shell=False)
            else:
                prt("[OK] Amended latest commit (transactional index).", style="green")
        else:
            commit_result = subprocess.run(["git", "commit", "-m", commit_msg],
                                            capture_output=True, cwd=project_root, shell=False)
            if commit_result.returncode != 0:
                prt("[ERROR] Commit failed. User index untouched. Check git status.", style="red")
                if old_index:
                    os.environ["GIT_INDEX_FILE"] = old_index
                else:
                    del os.environ["GIT_INDEX_FILE"]
                if os.path.exists(temp_index):
                    os.remove(temp_index)
                return False
            prt("[OK] Committed: {} (transactional index)".format(commit_msg), style="green")

        prt("[GIT] Transaction complete. User index preserved.", style="green")
    finally:
        if old_index:
            os.environ["GIT_INDEX_FILE"] = old_index
        else:
            os.environ.pop("GIT_INDEX_FILE", None)
        if os.path.exists(temp_index):
            try:
                os.remove(temp_index)
            except OSError:
                pass

    local_sha_result = subprocess.run(["git", "rev-parse", "HEAD"],
                                       capture_output=True, text=True, cwd=project_root, shell=False)
    local_sha = local_sha_result.stdout.strip()
    if not local_sha:
        prt("[ERROR] Could not get local HEAD SHA after commit.", style="red")
        return False
    prt("  Local SHA: {}".format(local_sha))

    max_retries = config.push_max_retries
    push_success = False
    for attempt in range(1, max_retries + 1):
        push_result = subprocess.run(["git", "push"], capture_output=True, text=True,
                                      cwd=project_root, shell=False)
        if push_result.returncode == 0:
            push_success = True
            break
        if attempt < max_retries:
            prt("[RETRY] Push attempt {} failed. Retrying...".format(attempt), style="yellow")
            import time
            time.sleep(2)

    if not push_success:
        prt("[WARNING] Push to remote failed after {} attempt(s).".format(max_retries), style="yellow")
        prt("  Commit is local only (SHA: {}). Run 'git push' manually.".format(local_sha), style="yellow")
        return False

    prt("[OK] Push succeeded.", style="green")

    if config.push_verify_remote_sha:
        fetch_result = subprocess.run(["git", "fetch", "origin"], capture_output=True,
                                       cwd=project_root, shell=False)
        if fetch_result.returncode != 0:
            prt("[WARNING] git fetch origin failed. Skipping remote SHA verification.", style="yellow")
            return True
        branch = get_git_context(project_root).get("Branch", "")
        remote_sha_result = subprocess.run(["git", "rev-parse", "origin/{}".format(branch)],
                                            capture_output=True, text=True, cwd=project_root, shell=False)
        remote_sha = remote_sha_result.stdout.strip()
        if remote_sha == local_sha:
            prt("[VERIFIED] Remote SHA matches local SHA: {}".format(remote_sha), style="green")
        else:
            prt("[WARNING] Remote SHA mismatch:", style="yellow")
            prt("  Local:  {}".format(local_sha))
            prt("  Remote: {}".format(remote_sha))
            prt("  Manual verification recommended.", style="yellow")

    return True