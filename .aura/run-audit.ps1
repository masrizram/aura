<#
.SYNOPSIS
    AURA Engine — Bootstrap Proxy
.DESCRIPTION
    This file is a lightweight proxy that delegates to the canonical
    engine entry point at src/engine/run-audit.ps1.

    The engine root is the repository root (parent of .aura/).
    All modules, agents, and configuration are loaded from src/.
    The .aura/ directory is reserved for runtime state and reports.

    Usage:
      powershell -NoProfile -File .aura/run-audit.ps1 -Action status
      powershell -NoProfile -File .aura/run-audit.ps1 -Action run
#>

#requires -Version 5.1

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptDir
$EngineScript = Join-Path $RepoRoot "src/engine/run-audit.ps1"

if (-not (Test-Path -LiteralPath $EngineScript)) {
    Write-Error "Engine script not found: $EngineScript"
    exit 1
}

& $EngineScript @PSBoundParameters @args