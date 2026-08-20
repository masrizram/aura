#!/usr/bin/env bash
# AURA — Autonomous Engineering Audit Engine (entry point)
# Python-first with PowerShell fallback.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

find_python() {
    for candidate in python3 python; do
        if command -v "$candidate" &>/dev/null; then
            echo "$candidate"
            return
        fi
    done
    echo ""
}

args=()
for a in "$@"; do
    args+=("$a")
done

PY=$(find_python)
if [[ -n "$PY" ]]; then
    exec "$PY" -m src.engine.main "${args[@]}"
fi

echo "[WARN] Python not found, falling back to PowerShell engine." >&2

find_powershell() {
    if command -v pwsh &>/dev/null; then echo "pwsh"
    elif command -v powershell &>/dev/null; then echo "powershell"
    else echo ""; fi
}

PS_EXE=$(find_powershell)
PS1_SCRIPT="$REPO_ROOT/src/engine/run-audit.ps1"

if [[ -z "$PS_EXE" ]]; then
    echo "[ERROR] Neither Python nor PowerShell found." >&2
    exit 1
fi

if [[ ! -f "$PS1_SCRIPT" ]]; then
    echo "[ERROR] Engine script not found: $PS1_SCRIPT" >&2
    exit 1
fi

if [[ "$PS_EXE" == "powershell" ]]; then
    PS_FLAGS=(-NoProfile -ExecutionPolicy Bypass)
else
    PS_FLAGS=(-NoProfile)
fi

exec "$PS_EXE" "${PS_FLAGS[@]}" -File "$PS1_SCRIPT" -Action "${args[@]}"