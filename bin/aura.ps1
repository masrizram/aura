<#
.SYNOPSIS
    AURA — Autonomous Engineering Audit Engine (entry point)
.DESCRIPTION
    Python-first entry with PowerShell 5.1 fallback.
    Usage: .\bin\aura.ps1 -Action status
#>
#requires -Version 5.1

$RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)

function Find-Python {
    if (Get-Command python -ErrorAction SilentlyContinue) { return "python" }
    if (Get-Command python3 -ErrorAction SilentlyContinue) { return "python3" }
    return ""
}

$PyExe = Find-Python
if ($PyExe) {
    $PyModule = "src.engine.main"
    $PyArgs = @("-m", $PyModule)
    foreach ($key in $PSBoundParameters.Keys) {
        $val = $PSBoundParameters[$key]
        $flag = "--$key"
        if ($val -is [switch]) {
            if ($val) { $PyArgs += $flag }
        } elseif ($val -is [string]) {
            $PyArgs += $flag
            $PyArgs += $val
        } elseif ($val -is [bool]) {
            if ($val) { $PyArgs += $flag }
        } else {
            $PyArgs += $flag
            $PyArgs += $val
        }
    }
    foreach ($a in $args) {
        $PyArgs += $a
    }
    Push-Location $RepoRoot
    & $PyExe $PyArgs
    $exitCode = $LASTEXITCODE
    Pop-Location
    exit $exitCode
}

Write-Warning "Python not found or Python engine unavailable, falling back to PowerShell engine."
$EngineScript = Join-Path $RepoRoot "src/engine/run-audit.ps1"
if (-not (Test-Path -LiteralPath $EngineScript)) {
    Write-Error "Engine script not found: $EngineScript"
    exit 1
}
& $EngineScript @PSBoundParameters @args