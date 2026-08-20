import json
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from .state_manager import write_json_file, write_text_file


MANIFEST_FILES = [
    "package.json", "composer.json", "pyproject.toml", "requirements.txt",
    "go.mod", "Cargo.toml", "Gemfile", "Makefile", "build.gradle", "pom.xml",
    "CMakeLists.txt", "Dockerfile", "docker-compose.yml",
]


def get_project_tooling(project_path: str) -> Dict[str, Any]:
    tooling: Dict[str, Any] = {"commands": {}, "files": []}
    pp = Path(project_path)

    for mf in MANIFEST_FILES:
        p = pp / mf
        if p.exists():
            tooling["files"].append(mf)

    workflows_dir = pp / ".github" / "workflows"
    if workflows_dir.is_dir():
        for wf in workflows_dir.rglob("*.yml"):
            try:
                rel = str(wf.resolve()).replace(str(pp.resolve()), "").lstrip("\\").lstrip("/")
                tooling["files"].append(rel)
            except Exception:
                pass
        for wf in workflows_dir.rglob("*.yaml"):
            try:
                rel = str(wf.resolve()).replace(str(pp.resolve()), "").lstrip("\\").lstrip("/")
                if rel not in tooling["files"]:
                    tooling["files"].append(rel)
            except Exception:
                pass

    pkg_json = pp / "package.json"
    if pkg_json.exists():
        try:
            pkg = json.loads(pkg_json.read_text(encoding="utf-8"))
            scripts = pkg.get("scripts", {})
            if isinstance(scripts, dict):
                for key, val in scripts.items():
                    tooling["commands"]["npm run {}".format(key)] = val
        except json.JSONDecodeError:
            pass

    composer_json = pp / "composer.json"
    if composer_json.exists():
        tooling["commands"]["composer test"] = None
        tooling["commands"]["composer lint"] = None

    pyproject = pp / "pyproject.toml"
    if pyproject.exists():
        tooling["commands"]["pytest"] = None
        tooling["commands"]["ruff check"] = None

    makefile = pp / "Makefile"
    if makefile.exists():
        tooling["commands"]["make test"] = None
        tooling["commands"]["make build"] = None
        tooling["commands"]["make lint"] = None

    return tooling


def get_tooling_commands(project_path: str) -> List[str]:
    commands = []
    pp = Path(project_path)

    pkg_json = pp / "package.json"
    if pkg_json.exists():
        try:
            pkg = json.loads(pkg_json.read_text(encoding="utf-8"))
            scripts = pkg.get("scripts", {})
            if scripts.get("test"):
                commands.append("npm test")
            if scripts.get("lint"):
                commands.append("npm run lint")
            if scripts.get("build"):
                commands.append("npm run build")
        except json.JSONDecodeError:
            pass

    pyproject = pp / "pyproject.toml"
    if pyproject.exists():
        commands.append("pytest --tb=short 2>&1")
        commands.append("ruff check . 2>&1")

    makefile = pp / "Makefile"
    if makefile.exists():
        commands.append("make test 2>&1")
        commands.append("make lint 2>&1")

    return commands


def invoke_project_tooling(project_path: str, commands: List[str]) -> Dict[str, Any]:
    results: Dict[str, Any] = {}
    pp = Path(project_path)

    for cmd in commands:
        cmd_name = cmd.replace(" ", "_")
        try:
            if os.name == "nt":
                result = subprocess.run(["cmd", "/c", cmd], capture_output=True, text=True,
                                        cwd=str(pp), timeout=300, shell=False)
            else:
                result = subprocess.run(["sh", "-c", cmd], capture_output=True, text=True,
                                        cwd=str(pp), timeout=300)
            results[cmd] = {
                "exit_code": result.returncode,
                "success": result.returncode == 0,
                "output": (result.stdout + result.stderr).strip(),
            }
        except subprocess.TimeoutExpired:
            results[cmd] = {
                "exit_code": -1,
                "success": False,
                "output": "Execution timed out after 300s",
            }
        except Exception as e:
            results[cmd] = {
                "exit_code": -1,
                "success": False,
                "output": "Execution error: {}".format(e),
            }

    return results


def format_tooling_report(results: Dict[str, Any]) -> str:
    lines = []
    lines.append("\n## TOOL EXECUTION REPORT (Orchestrator-Executed)")
    lines.append("")
    lines.append("| Command | Exit Code | Result | Output |")
    lines.append("|---------|-----------|--------|--------|")

    for cmd in sorted(results.keys()):
        r = results[cmd]
        status = "PASS" if r["success"] else "FAIL"
        short_output = r.get("output", "")
        if len(short_output) > 200:
            short_output = " ".join(short_output[:200].split()) + "..."
        else:
            short_output = " ".join(short_output.split())
        lines.append("| ``{}`` | {} | {} | {} |".format(cmd, r["exit_code"], status, short_output))

    lines.append("")
    all_passed = all(r["success"] for r in results.values())
    if all_passed:
        lines.append("All tooling commands PASSED.")
    else:
        lines.append("Some tooling commands FAILED. Do not declare compliance until resolved.")

    return "\n".join(lines)


def execute_tooling_and_save(project_path: str, engine_root: str) -> Dict[str, Any]:
    from .state_manager import StateManager
    state_mgr = StateManager(engine_root)
    state_mgr.ensure_dirs()

    commands = get_tooling_commands(project_path)
    tooling_info = get_project_tooling(project_path)

    if not commands:
        tooling_evidence = {
            "timestamp": datetime.now().isoformat(),
            "command_count": 0,
            "all_passed": True,
            "results": {},
            "note": "No test/lint/build commands detected in project manifests",
        }
        state_mgr.write_tooling_evidence(tooling_evidence)
        return {"status": "no_commands", "tooling": tooling_info}

    results = invoke_project_tooling(project_path, commands)
    report = format_tooling_report(results)

    tooling_output_file = Path(engine_root) / "tooling-output.txt"
    write_text_file(str(tooling_output_file), report)

    tooling_evidence = {
        "timestamp": datetime.now().isoformat(),
        "command_count": len(commands),
        "all_passed": all(r["success"] for r in results.values()),
        "results": results,
    }
    state_mgr.write_tooling_evidence(tooling_evidence)

    return {"status": "executed", "results": results, "report": report, "tooling": tooling_info}