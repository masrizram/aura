#!/usr/bin/env bash
# AURA — Autonomous Engineering Audit Engine (bash entry)
# Usage: ./bin/aura.sh status
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PS1_SCRIPT="$REPO_ROOT/src/engine/run-audit.ps1"

find_powershell() {
    if command -v pwsh &>/dev/null; then echo "pwsh"
    elif command -v powershell &>/dev/null; then echo "powershell"
    else echo ""; fi
}

PS_EXE=$(find_powershell)

if [[ -z "$PS_EXE" ]]; then
    echo "[ERROR] PowerShell not found."
    exit 1
fi

if [[ ! -f "$PS1_SCRIPT" ]]; then
    echo "[ERROR] Engine script not found: $PS1_SCRIPT"
    exit 1
fi

if [[ "$PS_EXE" == "powershell" ]]; then
    PS_FLAGS=(-NoProfile -ExecutionPolicy Bypass)
else
    PS_FLAGS=(-NoProfile)
fi

exec "$PS_EXE" "${PS_FLAGS[@]}" -File "$PS1_SCRIPT" -Action "$@"