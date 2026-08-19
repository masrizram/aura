<#
.SYNOPSIS
    AURA — Autonomous Engineering Audit Engine (PowerShell entry)
.DESCRIPTION
    Symlink-friendly entry point. Delegates to src/engine/run-audit.ps1.
    Usage: .\bin\aura.ps1 -Action status
#>
#requires -Version 5.1

$RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$EngineScript = Join-Path $RepoRoot "src/engine/run-audit.ps1"

if (-not (Test-Path -LiteralPath $EngineScript)) {
    Write-Error "Engine script not found: $EngineScript"
    exit 1
}

& $EngineScript @PSBoundParameters @args