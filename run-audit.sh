#!/usr/bin/env bash
# =============================================================================
# Cross-platform entry point for the Continuous Autonomous Engineering Audit Engine
# Usage: ./run-audit.sh [action] [options]
#
# Examples:
#   ./run-audit.sh status
#   ./run-audit.sh run
#   ./run-audit.sh run --multi-agent
#   ./run-audit.sh run --target-project /path/to/project
#   ./run-audit.sh reset
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENGINE_DIR="$SCRIPT_DIR/.aura"
PS1_SCRIPT="$SCRIPT_DIR/src/engine/run-audit.ps1"

find_powershell() {
    if command -v pwsh &>/dev/null; then
        echo "pwsh"
    elif command -v powershell &>/dev/null; then
        echo "powershell"
    else
        echo ""
    fi
}

usage() {
    cat <<EOF
Usage: ./run-audit.sh <action> [options]

Actions:
  run       Generate next cycle prompt and display it
  status    Show convergence status and current findings
  context   Generate cycle prompt only (no state advance)
  reset     Archive current state and reinitialize engine
  push      Stage & commit engine files, push to git (interactive approval)

Options:
  --multi-agent       Enable multi-agent mode (maximum thoroughness)
  --target-project    Path to the project to audit (default: current directory)
  --force             Force another cycle even if converged
  --approve           Auto-approve push (skip interactive prompt)
  --amend             Amend previous commit instead of creating new one

Examples:
  ./run-audit.sh status
  ./run-audit.sh run
  ./run-audit.sh run --multi-agent
  ./run-audit.sh run --target-project /home/user/my-project
  ./run-audit.sh run --multi-agent --target-project /home/user/my-project
  ./run-audit.sh reset
  ./run-audit.sh context
  ./run-audit.sh push
  ./run-audit.sh push --approve
EOF
}

PS_EXE=$(find_powershell)

if [[ -z "$PS_EXE" ]]; then
    echo "[ERROR] PowerShell not found. Install PowerShell 7+ (pwsh) or use Windows PowerShell."
    echo "  macOS:   brew install powershell"
    echo "  Ubuntu:  sudo apt install powershell"
    echo "  Others:  https://aka.ms/powershell"
    exit 1
fi

if [[ ! -f "$PS1_SCRIPT" ]]; then
    echo "[ERROR] Engine script not found at: $PS1_SCRIPT"
    exit 1
fi

ACTION="run"
MULTI_AGENT=""
TARGET_PROJECT="."
FORCE=""
APPROVE=""
AMEND=""
POSITIONAL_ARGS=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        run|status|context|reset|push)
            ACTION="$1"
            shift
            ;;
        --multi-agent|-MultiAgent)
            MULTI_AGENT="-MultiAgent"
            shift
            ;;
        --target-project|-TargetProject)
            if [[ -z "${2:-}" || "${2:0:1}" == "-" ]]; then
                echo "[ERROR] --target-project requires a path argument"
                exit 1
            fi
            TARGET_PROJECT="$2"
            shift 2
            ;;
        --force|-Force)
            FORCE="-Force"
            shift
            ;;
        --approve|-Approve)
            APPROVE="-Approve"
            shift
            ;;
        --amend|-Amend)
            AMEND="-Amend"
            shift
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        *)
            echo "[ERROR] Unknown option: $1"
            usage
            exit 1
            ;;
    esac
done

if [[ "$PS_EXE" == "powershell" ]]; then
    PS_FLAGS=(-NoProfile -ExecutionPolicy Bypass)
else
    PS_FLAGS=(-NoProfile)
fi

PS_ARGS=("${PS_FLAGS[@]}" -File "$PS1_SCRIPT" -Action "$ACTION" -TargetProject "$TARGET_PROJECT")
[[ -n "$MULTI_AGENT" ]] && PS_ARGS+=("$MULTI_AGENT")
[[ -n "$FORCE" ]] && PS_ARGS+=("$FORCE")
[[ -n "$APPROVE" ]] && PS_ARGS+=("$APPROVE")
[[ -n "$AMEND" ]] && PS_ARGS+=("$AMEND")

"$PS_EXE" "${PS_ARGS[@]}"