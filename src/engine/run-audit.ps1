<#
.SYNOPSIS
    Continuous Autonomous Engineering Audit Engine - Orchestrator
.DESCRIPTION
    Generates cycle prompts with injected context, manages persistent state,
    checks convergence gates, and drives the audit-remediate-verify loop
    until all material defects are resolved or a human blocker is hit.
#>

#requires -Version 5.1

param(
    [ValidateSet("run","status","reset","context","push","validate-state","run-tooling","scope-check","promote-state","invariant-check","index-repo","evidence-check","adversarial-campaign","scale-benchmark","sandbox-test","security-scan","git-safety","verify-findings","score-report","false-evidence-campaign","false-convergence-campaign","git-safety-campaign","mutation-test","failure-recovery")]
    [string]$Action = "run",

    [string]$TargetProject = ".",

    [switch]$MultiAgent,

    [switch]$Force,

    [switch]$Approve,

    [switch]$Amend,

    [switch]$ForceValidation
)

$ErrorActionPreference = "Stop"

function Resolve-RepoRoot {
    <#
    .SYNOPSIS
        Resolves the .aura repository root directory deterministically.
    .DESCRIPTION
        Uses $PSScriptRoot (the directory containing this script) as the
        authoritative starting point. The repo root is two levels above
        src/engine/. Falls back to other resolution methods. Fails closed
        if none is available.
    #>
    $candidate = $PSScriptRoot
    if ($candidate) {
        $repoRoot = Split-Path -Parent (Split-Path -Parent $candidate)
        if ($repoRoot) {
            $normalized = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($repoRoot)
            if (Test-Path -LiteralPath $normalized -PathType Container) {
                return $normalized
            }
            return $repoRoot
        }
    }

    $candidate = if ($PSCommandPath) { Split-Path -Parent (Split-Path -Parent $PSCommandPath) } else { $null }
    if ($candidate -and (Test-Path -LiteralPath $candidate -PathType Container)) {
        return $candidate
    }

    $candidate = if ($MyInvocation.MyCommand.Path) { Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path) } else { $null }
    if ($candidate -and (Test-Path -LiteralPath $candidate -PathType Container)) {
        return $candidate
    }

    throw "ENGINE_ROOT_RESOLUTION_FAILURE: Cannot resolve repository root. `$PSScriptRoot, `$PSCommandPath, and `$MyInvocation.MyCommand.Path are all unavailable."
}

$RepoRoot = Resolve-RepoRoot
Write-Verbose "[AURA] RepoRoot resolved: $RepoRoot"

$ModulesDir = Join-Path $RepoRoot ".aura/modules"
if (-not $ModulesDir) {
    throw "ENGINE_ROOT_RESOLUTION_FAILURE: ModulesDir is null after resolution"
}

$ModulesDirResolved = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($ModulesDir)
if (-not (Test-Path -LiteralPath $ModulesDirResolved -PathType Container)) {
    throw "ENGINE_ROOT_RESOLUTION_FAILURE: Modules directory not found: $ModulesDir (resolved: $ModulesDirResolved)"
}

function Write-Banner {
    Write-Host "`n========================================" -ForegroundColor Cyan
    Write-Host "  CONTINUOUS AUDIT AND REMEDIATION ENGINE  " -ForegroundColor Cyan
    Write-Host "                v2.1.0                   " -ForegroundColor Cyan
    Write-Host "========================================`n" -ForegroundColor Cyan
}

function Read-JsonFile($Path) {
    if (Test-Path -LiteralPath $Path) {
        $content = Get-Content -LiteralPath $Path -Raw -Encoding UTF8
        if ([string]::IsNullOrWhiteSpace($content)) {
            Write-Warning "Read-JsonFile: '$Path' exists but is empty."
            return $null
        }
        try {
            return $content | ConvertFrom-Json
        } catch {
            Write-Warning "Read-JsonFile: '$Path' contains malformed JSON. Error: $_"
            return $null
        }
    } else {
        return $null
    }
}

function Write-TextFile($Path, $Content) {
    $parent = Split-Path -Parent $Path
    if (-not (Test-Path -LiteralPath $parent)) {
        New-Item -ItemType Directory -Force -Path $parent | Out-Null
    }
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $Content, $utf8NoBom)
}

function Write-JsonFile($Path, $Data) {
    $parent = Split-Path -Parent $Path
    if (-not (Test-Path -LiteralPath $parent)) {
        New-Item -ItemType Directory -Force -Path $parent | Out-Null
    }
    $tempPath = "$Path.tmp.$([System.Guid]::NewGuid().ToString('N').Substring(0,8))"
    try {
        $json = $Data | ConvertTo-Json -Depth 100
        $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
        [System.IO.File]::WriteAllText($tempPath, $json, $utf8NoBom)
        Move-Item -LiteralPath $tempPath -Destination $Path -Force
    } catch {
        if (Test-Path -LiteralPath $tempPath) {
            Remove-Item -LiteralPath $tempPath -Force -ErrorAction SilentlyContinue
        }
        throw
    }
}

function Sanitize-PromptString($Value) {
    if ($null -eq $Value) { return "" }
    $sanitized = [string]$Value
    $sanitized = $sanitized -replace "[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", ""
    $sanitized = $sanitized -replace "[\u202A-\u202E\u2066-\u2069]", ""
    $sanitized = $sanitized -replace '`', "'"
    if ($sanitized.Length -gt 4000) {
        $sanitized = $sanitized.Substring(0, 4000)
        if ([char]::IsHighSurrogate($sanitized[$sanitized.Length - 1])) {
            $sanitized = $sanitized.Substring(0, $sanitized.Length - 1)
        }
        $sanitized += "`n... [TRUNCATED]"
    }
    return $sanitized
}

function Get-GitContext($ProjectPath) {
    $context = @{}

    try {
        $null = Get-Command git -ErrorAction Stop
    } catch {
        $context.Error = "git not installed or not on PATH"
        return $context
    }

    $cwd = Get-Location

    try {
        Set-Location -LiteralPath $ProjectPath

        $context.Status        = (git status --short 2>&1 | Out-String).Trim()
        if ($LASTEXITCODE -ne 0) { $context.Status = ""; $context.GitError = $true }
        $context.DiffStat      = (git diff --stat HEAD 2>&1 | Out-String).Trim()
        if ($LASTEXITCODE -ne 0) { $context.DiffStat = ""; $context.GitError = $true }
        $context.RecentCommits = (git log --oneline --max-count=15 2>&1 | Out-String).Trim()
        if ($LASTEXITCODE -ne 0) { $context.RecentCommits = ""; $context.GitError = $true }
        $context.Branch        = (git branch --show-current 2>&1 | Out-String).Trim()
        if ($LASTEXITCODE -ne 0) { $context.Branch = ""; $context.GitError = $true }
        $context.LastCommitMsg = (git log -1 --format="%s" 2>&1 | Out-String).Trim()
        if ($LASTEXITCODE -ne 0) { $context.LastCommitMsg = ""; $context.GitError = $true }
        $context.LastCommitHash = (git log -1 --format="%H" 2>&1 | Out-String).Trim()
        if ($LASTEXITCODE -ne 0) { $context.LastCommitHash = ""; $context.GitError = $true }
        $lsFilesOutput = git ls-files 2>&1
        if ($LASTEXITCODE -eq 0) {
            $context.FileCount = ($lsFilesOutput | Measure-Object).Count
        } else {
            $context.FileCount = 0
            $context.GitError = $true
        }
    } catch {
        $context.Error = "PowerShell error in Get-GitContext: $_"
    } finally {
        Set-Location $cwd.Path
    }

    return $context
}

function Get-ProjectTooling($ProjectPath) {
    $tooling = @{
        commands = @{}
        files = @()
    }

    $manifestFiles = @(
        "package.json","composer.json","pyproject.toml","requirements.txt",
        "go.mod","Cargo.toml","Gemfile","Makefile","build.gradle","pom.xml",
        "CMakeLists.txt","Dockerfile","docker-compose.yml"
    )

    foreach ($f in $manifestFiles) {
        $p = Join-Path $ProjectPath $f
        if (Test-Path -LiteralPath $p) { $tooling.files += $f }
    }

    $workflowsDir = Join-Path $ProjectPath ".github/workflows"
    if (Test-Path -LiteralPath $workflowsDir -PathType Container) {
        $workflowFiles = Get-ChildItem -LiteralPath $workflowsDir -File -Include *.yml,*.yaml -Recurse -ErrorAction SilentlyContinue
        foreach ($wf in $workflowFiles) {
            $tooling.files += $wf.FullName.Substring($ProjectPath.Length).TrimStart("\", "/")
        }
    }

    $pkgJson = Join-Path $ProjectPath "package.json"
    if (Test-Path -LiteralPath $pkgJson) {
        try {
            $pkg = Get-Content -LiteralPath $pkgJson -Raw -Encoding UTF8 | ConvertFrom-Json
            $scripts = $pkg.scripts
            if ($scripts -and $scripts -is [PSCustomObject]) {
                $props = $scripts.PSObject.Properties
                foreach ($prop in $props) {
                    $key = $prop.Name
                    $tooling.commands["npm run $key"] = $prop.Value
                }
            }
        } catch {
            Write-Warning "Get-ProjectTooling: package.json is malformed, skipping npm scripts. Error: $_"
        }
    }

    $composerJson = Join-Path $ProjectPath "composer.json"
    if (Test-Path -LiteralPath $composerJson) {
        $tooling.commands["composer test"] = $null
        $tooling.commands["composer lint"] = $null
    }

    $pyproject = Join-Path $ProjectPath "pyproject.toml"
    if (Test-Path -LiteralPath $pyproject) {
        $tooling.commands["pytest"]     = $null
        $tooling.commands["ruff check"] = $null
    }

    $makefile = Join-Path $ProjectPath "Makefile"
    if (Test-Path -LiteralPath $makefile) {
        $tooling.commands["make test"]  = $null
        $tooling.commands["make build"] = $null
        $tooling.commands["make lint"]  = $null
    }

    return $tooling
}

function Get-FindingsSummary($Findings) {
    if (-not $Findings -or -not $Findings.findings -or $Findings.findings.Count -eq 0) {
        return "No findings recorded yet."
    }

    $bySeverity = @($Findings.findings | Group-Object -Property severity)
    $byStatus   = @($Findings.findings | Group-Object -Property status)

    $sb = New-Object System.Text.StringBuilder
    [void]$sb.AppendLine("---")
    [void]$sb.AppendLine("## CURRENT FINDINGS LEDGER")
    [void]$sb.AppendLine("")

    [void]$sb.AppendLine("### By Severity")
    foreach ($g in $bySeverity) {
        [void]$sb.AppendLine("- **$($g.Name)** : $($g.Count)")
    }

    [void]$sb.AppendLine("")
    [void]$sb.AppendLine("### By Status")
    foreach ($g in $byStatus) {
        [void]$sb.AppendLine("- **$($g.Name)** : $($g.Count)")
    }

    [void]$sb.AppendLine("")
    [void]$sb.AppendLine("### Open P0-P2")
    $open = @($Findings.findings | Where-Object {
        ($_.severity -in @("P0","P1","P2")) -and ($_.status -in @("OPEN","IN_PROGRESS"))
    })
    if (-not $open) {
        [void]$sb.AppendLine("*None*")
    } else {
        foreach ($f in $open) {
            [void]$sb.AppendLine("- **$($f.id)** | $($f.severity) | $($f.category) | $(Sanitize-PromptString $f.problem)")
        }
    }

    return $sb.ToString()
}

function Get-ConvergenceStatus {
    [CmdletBinding()]
    param()

    $state  = Read-JsonFile $CycleFile
    $findings = Read-JsonFile $FindingsFile
    $conv  = Read-JsonFile $ConvergenceFile

    if (-not $state) {
        Write-Host "Engine not yet initialized. Run -Action run first." -ForegroundColor Yellow
        return
    }

    Write-Host "`n=== CONVERGENCE STATUS ===" -ForegroundColor Yellow
    Write-Host "Cycle:                 $($state.current_cycle)"
    Write-Host "Classification:        $($state.classification)"
    Write-Host "Cycles w/o progress:   $($state.cycles_without_progress)"
    Write-Host "Consecutive converged: $($state.consecutive_converged_cycles)"

    if ($conv) {
        Write-Host ""
        Write-Host "Consecutive converged cycles (conv): $($conv.consecutive_converged_cycles)"
        Write-Host "Audits since last finding: $($conv.audits_since_last_finding)"
        Write-Host ""
        foreach ($gate in $conv.gates.PSObject.Properties) {
            $color = if ($gate.Value) { "Green" } else { "Red" }
            Write-Host ("  {0,-30} : {1}" -f $gate.Name, $gate.Value) -ForegroundColor $color
        }
        $classColor = if ($conv.classification -eq "PRODUCTION_READY") { "Green" }
                      elseif ($conv.classification -eq "CONDITIONALLY_READY") { "Yellow" }
                      else { "Red" }
        Write-Host ""
        Write-Host "Classification: $($conv.classification)" -ForegroundColor $classColor
        Write-Host "Reason: $($conv.reason)"

        if ($conv.module_status) {
            Write-Host ""
            $modColor = if ($conv.module_status.integrity_pass) { "Green" } else { "Red" }
            Write-Host "Module Integrity: $($conv.module_status.integrity_pass)" -ForegroundColor $modColor
            Write-Host "  Required failures: $($conv.module_status.required_failures.Count)"
            if ($conv.module_status.required_failures.Count -gt 0) {
                foreach ($rf in $conv.module_status.required_failures) {
                    Write-Host "    [REQUIRED FAIL] $rf" -ForegroundColor Red
                }
            }
            Write-Host "  Optional failures: $($conv.module_status.optional_failures.Count)"
            Write-Host "  Experimental failures: $($conv.module_status.experimental_failures.Count)"
            Write-Host "  Loaded/Total: $($conv.module_status.total_loaded)/$($conv.module_status.total_expected)"
        }
    }

    if ($findings -and $findings.findings) {
        $open = @($findings.findings | Where-Object { $_.status -in @("OPEN","IN_PROGRESS") })
        $openP0P2 = @($open | Where-Object { $_.severity -in @("P0","P1","P2") })
        $cntColor = if ($openP0P2.Count -eq 0) { "Green" } else { "Red" }
        Write-Host "`nOpen P0-P2 findings: $($openP0P2.Count)" -ForegroundColor $cntColor
        if ($openP0P2) {
            foreach ($f in $openP0P2) {
                Write-Host "  $($f.id) | $($f.severity) | $($f.category) | $($f.problem)" -ForegroundColor Red
            }
        }
    }
}

function Initialize-State {
    [CmdletBinding()]
    param()

    $now = (Get-Date).ToString("o")
    $cycleData = @{
        engine_name = "Continuous Autonomous Engineering Audit Engine"
        version = "2.1.0"
        started_at = $now
        current_cycle = 0
        current_phase = "INIT"
        status = "RUNNING"
        classification = "NOT_READY"
        cycles_completed = 0
        cycles_without_progress = 0
        consecutive_converged_cycles = 0
        last_change_hash = $null
    }
    Write-JsonFile $CycleFile $cycleData

    $findingsData = @{ findings = @(); next_id = 1 }
    Write-JsonFile $FindingsFile $findingsData

    $convData = @{
        cycle = 0
        converged = $false
        consecutive_converged_cycles = 0
        audits_since_last_finding = 0
        gates = @{
            P0_zero = $false; P1_zero = $false; P2_zero = $false
            critical_security = $false; critical_correctness = $false
            data_integrity = $false; regression = $false; verification = $false
            no_material_new_findings = $false; limitations_documented = $false
            consecutive_clean_independent_audits = $false
            module_dependency_integrity = $Script:moduleIntegrityPass
        }
        module_status = @{
            integrity_pass = $Script:moduleIntegrityPass
            required_failures = $Script:modRequiredFailures
            optional_failures = $Script:modOptionalFailures
            experimental_failures = $Script:modExperimentalFailures
            total_loaded = $Script:modLoadCount
            total_expected = $moduleOrder.Count
        }
        classification = "NOT_READY"
        reason = "Cycle 0 - not yet started."
    }
    Write-JsonFile $ConvergenceFile $convData

    Write-Host "[OK] State initialized. Engine ready." -ForegroundColor Green
}

function Reset-Engine {
    [CmdletBinding()]
    param()

    $archiveDir = Join-Path $EngineRoot "archive\$(Get-Date -Format 'yyyyMMdd_HHmmss')"
    New-Item -ItemType Directory -Force -Path $archiveDir | Out-Null

    $stateDir = Join-Path $EngineRoot "state"
    if (Test-Path -LiteralPath $stateDir) {
        Get-ChildItem -LiteralPath $stateDir -File | ForEach-Object {
            Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $archiveDir $_.Name) -Force
        }
    }
    if (Test-Path -LiteralPath $ReportsDir) {
        Get-ChildItem -LiteralPath $ReportsDir -File | ForEach-Object {
            Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $archiveDir $_.Name) -Force
        }
    }

    $envFile = Join-Path $EngineRoot "last-cycle.env"
    if (Test-Path -LiteralPath $envFile) {
        Copy-Item -LiteralPath $envFile -Destination (Join-Path $archiveDir "last-cycle.env") -Force
        Remove-Item -LiteralPath $envFile -Force
    }

    $promptFile = Join-Path $EngineRoot "generated-cycle-prompt.md"
    if (Test-Path -LiteralPath $promptFile) {
        Copy-Item -LiteralPath $promptFile -Destination (Join-Path $archiveDir "generated-cycle-prompt.md") -Force
        Remove-Item -LiteralPath $promptFile -Force
    }

    Write-Host "[ARCHIVED] Previous state -> $archiveDir" -ForegroundColor Yellow

    $proposedFiles = @(
        (Join-Path $EngineRoot "state/proposed-findings.json"),
        (Join-Path $EngineRoot "state/proposed-convergence.json"),
        (Join-Path $EngineRoot "state/proposed-cycle.json"),
        (Join-Path $EngineRoot "state/tooling-evidence.json")
    )
    foreach ($pf in $proposedFiles) {
        if (Test-Path -LiteralPath $pf) {
            Copy-Item -LiteralPath $pf -Destination (Join-Path $archiveDir (Split-Path -Leaf $pf)) -Force
            Remove-Item -LiteralPath $pf -Force
            Write-Host "  [CLEANED] $(Split-Path -Leaf $pf)" -ForegroundColor Gray
        }
    }

    Initialize-State

    $ledgerTemplate = @"
# Audit Ledger

| Cycle | Started | Classification | Score | Confidence | P0 | P1 | P2 | P3 | P4 | P5 | Total Open | Converged |
|-------|---------|---------------|-------|------------|----|----|----|----|----|----|------------|-----------|
| - | - | - | - | - | - | - | - | - | - | - | - | - |

---
## Finding History
*No findings yet.*
"@
    Write-TextFile (Join-Path $ReportsDir "audit-ledger.md") $ledgerTemplate

    $archTemplate = "# Architecture Map`n`n*Not yet modeled.*"
    Write-TextFile (Join-Path $ReportsDir "architecture-map.md") $archTemplate
    $riskTemplate = "# Risk Register`n`n*No risks recorded.*"
    Write-TextFile (Join-Path $ReportsDir "risk-register.md") $riskTemplate
    $verifyTemplate = "# Verification Matrix`n`n*No runs yet.*"
    Write-TextFile (Join-Path $ReportsDir "verification-matrix.md") $verifyTemplate
    $remediationTemplate = "# Remediation Log`n`n*No remediations yet.*"
    Write-TextFile (Join-Path $ReportsDir "remediation-log.md") $remediationTemplate

    Write-Host "[OK] Engine fully reset." -ForegroundColor Green
}

function Safe-Int($Value, $Fallback = 0) {
    if ($null -eq $Value) { return $Fallback }
    try {
        return [int]$Value
    } catch {
        Write-Warning "Safe-Int: Could not cast '$Value' to int, using fallback $Fallback."
        return $Fallback
    }
}

# ============================================================
# STATE MACHINE ENFORCEMENT (CRITICAL ARCHITECTURAL CONTROL)
# ============================================================

$Script:ValidFindingTransitions = @{
    "OPEN"         = @("IN_PROGRESS", "DEFERRED", "BLOCKED")
    "IN_PROGRESS"  = @("FIXED", "DEFERRED", "BLOCKED", "OPEN")
    "FIXED"        = @("VERIFYING", "OPEN")
    "VERIFYING"    = @("VERIFIED", "REJECTED", "FIXED")
    "VERIFIED"     = @("OPEN")
    "REJECTED"     = @("OPEN", "FIXED")
    "DEFERRED"     = @("OPEN")
    "BLOCKED"      = @("OPEN")
    "UNVERIFIED"   = @("OPEN")
}

$Script:ValidClassificationTransitions = @{
    "NOT_READY"             = @("CONDITIONALLY_READY", "HUMAN_BLOCKED")
    "CONDITIONALLY_READY"   = @("PRODUCTION_READY", "NOT_READY", "HUMAN_BLOCKED")
    "PRODUCTION_READY"      = @("NOT_READY", "HUMAN_BLOCKED")
    "HUMAN_BLOCKED"         = @("NOT_READY", "CONDITIONALLY_READY")
}

$Script:ForbiddenDirectTransitions = @(
    @{From="OPEN"; To="VERIFIED"; Reason="Must pass through FIXED and VERIFYING"},
    @{From="OPEN"; To="FIXED"; Reason="Must pass through IN_PROGRESS"},
    @{From="IN_PROGRESS"; To="VERIFIED"; Reason="Must pass through FIXED and VERIFYING"},
    @{From="FIXED"; To="VERIFIED"; Reason="Must pass through VERIFYING"},
    @{From="VERIFYING"; To="CLOSED"; Reason="Must pass through VERIFIED or REJECTED"}
)

function Test-ValidFindingTransition {
    param([string]$FromStatus, [string]$ToStatus)

    if ([string]::IsNullOrWhiteSpace($FromStatus)) { return $true }
    if ($FromStatus -eq $ToStatus) { return $true }

    if ($Script:ValidFindingTransitions.ContainsKey($FromStatus)) {
        $allowed = $Script:ValidFindingTransitions[$FromStatus]
        if ($ToStatus -in $allowed) { return $true }
    }

    return $false
}

function Test-ForbiddenDirectTransition {
    param([string]$FromStatus, [string]$ToStatus)

    foreach ($forbidden in $Script:ForbiddenDirectTransitions) {
        if ($forbidden.From -eq $FromStatus -and $forbidden.To -eq $ToStatus) {
            return $forbidden
        }
    }
    return $null
}

function Test-ValidClassificationTransition {
    param([string]$FromClassification, [string]$ToClassification)

    if ([string]::IsNullOrWhiteSpace($FromClassification)) { return $true }
    if ($FromClassification -eq $ToClassification) { return $true }

    if ($Script:ValidClassificationTransitions.ContainsKey($FromClassification)) {
        $allowed = $Script:ValidClassificationTransitions[$FromClassification]
        if ($ToClassification -in $allowed) { return $true }
    }

    return $false
}

function Validate-FindingStateIntegrity {
    param(
        [array]$ProposedFindings,
        [PSCustomObject]$ExistingFindings
    )

    $violations = @()
    $existingMap = @{}
    if ($ExistingFindings -and $ExistingFindings.findings) {
        foreach ($f in $ExistingFindings.findings) {
            $existingMap[$f.id] = $f
        }
    }

    foreach ($proposed in $ProposedFindings) {
        if (-not $proposed.id) { continue }

        $existing = $existingMap[$proposed.id]
        if (-not $existing) {
            if ($proposed.status -ne "OPEN") {
                $violations += "NEW FINDING VIOLATION: $($proposed.id) is a new finding but has status '$($proposed.status)'. New findings must start as OPEN."
            }
            continue
        }

        if (Test-ForbiddenDirectTransition -FromStatus $existing.status -ToStatus $proposed.status) {
            $forbidden = Test-ForbiddenDirectTransition -FromStatus $existing.status -ToStatus $proposed.status
            $violations += "ILLEGAL TRANSITION: $($proposed.id): $($existing.status) -> $($proposed.status). $($forbidden.Reason)"
            continue
        }

        if (-not (Test-ValidFindingTransition -FromStatus $existing.status -ToStatus $proposed.status)) {
            $violations += "INVALID TRANSITION: $($proposed.id): $($existing.status) -> $($proposed.status) is not an allowed transition."
        }
    }

    return $violations
}

function Validate-GateEvidenceIntegrity {
    param(
        [PSCustomObject]$ProposedConvergence,
        [PSCustomObject]$ExistingConvergence
    )

    $violations = @()
    if (-not $ExistingConvergence -or -not $ExistingConvergence.gates) {
        return $violations
    }

    $gateNames = @("P0_zero","P1_zero","P2_zero","critical_security","critical_correctness",
                   "data_integrity","regression","verification","no_material_new_findings",
                   "limitations_documented","consecutive_clean_independent_audits","module_dependency_integrity")

    foreach ($gateName in $gateNames) {
        $oldValue = $false
        $newValue = $false
        try {
            $oldValue = [bool]$ExistingConvergence.gates.$gateName
        } catch { $oldValue = $false }
        try {
            $newValue = [bool]$ProposedConvergence.gates.$gateName
        } catch { $newValue = $false }

        if (-not $oldValue -and $newValue) {
            $evidenceRequired = switch ($gateName) {
                "P0_zero" { "All P0 findings must be VERIFIED or DEFERRED with justification" }
                "P1_zero" { "All P1 findings must be VERIFIED or DEFERRED with justification" }
                "P2_zero" { "All P2 findings must be VERIFIED or DEFERRED with justification" }
                "critical_security" { "All SECURITY category P0-P2 findings must be VERIFIED" }
                "critical_correctness" { "All CORRECTNESS category P0-P2 findings must be VERIFIED" }
                "data_integrity" { "All DATA_INTEGRITY findings must be VERIFIED" }
                "regression" { "Regression audit must produce zero re-appeared findings" }
                "verification" { "All FIXED findings must have verifier evidence (not self-verified)" }
                "no_material_new_findings" { "Two consecutive cycles must produce zero new P0-P3 findings" }
                "limitations_documented" { "Remaining limitations must be explicitly listed in reports" }
                "consecutive_clean_independent_audits" { "consecutive_converged_cycles >= 2 AND audits_since_last_finding >= 2" }
                "module_dependency_integrity" { "All required modules exist, loaded, and no required-module dependency failures" }
            }
            $violations += "GATE FLIP: $gateName : false -> true. Evidence required: $evidenceRequired"
        }

        if ($oldValue -and -not $newValue) {
            $violations += "GATE REGRESSION: $gateName : true -> false. Regression requires documented finding."
        }
    }

    $oldConverged = if ($ExistingConvergence.converged) { $true } else { $false }
    $newConverged = if ($ProposedConvergence.converged) { $true } else { $false }

    if (-not $oldConverged -and $newConverged) {
        $violations += "CONVERGENCE FLIP: converged: false -> true. ALL 12 gates must independently PASS before convergence."

        $gateNames = @("P0_zero","P1_zero","P2_zero","critical_security","critical_correctness",
                       "data_integrity","regression","verification","no_material_new_findings",
                       "limitations_documented","consecutive_clean_independent_audits","module_dependency_integrity")
        $failingGates = @()
        foreach ($gn in $gateNames) {
            try {
                $gv = [bool]$ProposedConvergence.gates.$gn
                if (-not $gv) { $failingGates += $gn }
            } catch { $failingGates += "$gn (missing)" }
        }
        if ($failingGates.Count -gt 0) {
            $violations += "CONVERGENCE BLOCKED: Cannot converge with gates still false/missing: $($failingGates -join ', ')"
        }
    }

    # INVARIANT: converged=true ⇒ ALL gates=true. Checked unconditionally, not only on false→true transition.
    if ($newConverged) {
        $gateNames = @("P0_zero","P1_zero","P2_zero","critical_security","critical_correctness",
                       "data_integrity","regression","verification","no_material_new_findings",
                       "limitations_documented","consecutive_clean_independent_audits","module_dependency_integrity")
        $invFailingGates = @()
        foreach ($gn in $gateNames) {
            try {
                $gv = [bool]$ProposedConvergence.gates.$gn
                if (-not $gv) { $invFailingGates += $gn }
            } catch { $invFailingGates += "$gn (missing)" }
        }
        if ($invFailingGates.Count -gt 0) {
            $violations += "CONVERGENCE INVARIANT VIOLATION: converged=true requires ALL gates=true. Failing: $($invFailingGates -join ', ')"
        }
    }

    $oldScore = Safe-Int $ExistingConvergence.overall_score 0
    $newScore = Safe-Int $ProposedConvergence.overall_score 0
    if ($newScore -lt $oldScore) {
        $violations += "SCORE REGRESSION: overall_score decreased from $oldScore to $newScore. Score can only stay the same or increase."
    }
    if ($newScore -gt ($oldScore + 15)) {
        $violations += "SCORE SPIKE: overall_score jumped from $oldScore to $newScore (+$($newScore - $oldScore)). Maximum per-cycle increase is 15. Requires extraordinary evidence."
    }

    $oldConsecutive = Safe-Int $ExistingConvergence.consecutive_converged_cycles 0
    $newConsecutive = Safe-Int $ProposedConvergence.consecutive_converged_cycles 0
    if ($newConsecutive -lt $oldConsecutive) {
        $violations += "COUNTER REGRESSION: consecutive_converged_cycles decreased from $oldConsecutive to $newConsecutive. Counter must not decrease."
    }
    if ($newConsecutive -gt ($oldConsecutive + 1)) {
        $violations += "COUNTER JUMP: consecutive_converged_cycles jumped from $oldConsecutive to $newConsecutive (+$($newConsecutive - $oldConsecutive)). Max increase is 1 per cycle."
    }

    return $violations
}

function Test-AuditScopeIntegrity {
    param(
        [string]$ProjectPath,
        [int]$ClaimedAuditedFileCount
    )

    $warnings = @()

    try {
        $null = Get-Command git -ErrorAction Stop
        $cwd = Get-Location
        Set-Location -LiteralPath $ProjectPath
        $totalFiles = (git ls-files 2>&1 | Measure-Object).Count
        Set-Location $cwd.Path

        if ($totalFiles -gt 500) {
            $warnings += "SCALE WARNING: Repository has $totalFiles tracked files. Full audit unlikely to fit in single LLM context window. Consider chunked audit with dependency-graph-aware scoping."
        }

        if ($ClaimedAuditedFileCount -gt 0 -and $totalFiles -gt 0) {
            $pct = [math]::Round(($ClaimedAuditedFileCount / $totalFiles) * 100, 1)
            if ($pct -lt 50) {
                $warnings += "SCOPE WARNING: Only $ClaimedAuditedFileCount of $totalFiles files ($pct%) audited. Convergence may be invalid with partial scope."
            }
        }
    } catch {
        $warnings += "SCOPE CHECK FAILED: Could not determine repository file count. Error: $_"
    }

    return $warnings
}

function Invoke-ProjectTooling {
    param(
        [string]$ProjectPath,
        [string[]]$Commands
    )

    $results = @{}
    $cwd = Get-Location

    foreach ($cmd in $Commands) {
        $cmdName = $cmd -replace '\s+', '_'
        try {
            Set-Location -LiteralPath $ProjectPath
            if ($IsLinux -or $IsMacOS) {
                $output = sh -c "$cmd" 2>&1 | Out-String
            } else {
                $output = cmd /c "$cmd 2>&1" 2>&1 | Out-String
            }
            $exitCode = $LASTEXITCODE
            $results[$cmd] = @{
                exit_code = $exitCode
                success = ($exitCode -eq 0)
                output = $output.Trim()
            }
        } catch {
            $results[$cmd] = @{
                exit_code = -1
                success = $false
                output = "Execution error: $_"
            }
        }
    }

    Set-Location $cwd.Path
    return $results
}

function Get-ToolingCommands {
    param(
        [string]$ProjectPath,
        [PSCustomObject]$ToolingFromConfig
    )

    $commands = @()

    $pkgJson = Join-Path $ProjectPath "package.json"
    if (Test-Path -LiteralPath $pkgJson) {
        try {
            $pkg = Get-Content -LiteralPath $pkgJson -Raw -Encoding UTF8 | ConvertFrom-Json
            $testCmd = if ($pkg.scripts -and $pkg.scripts.test) { "npm test" } else { $null }
            $lintCmd = if ($pkg.scripts -and $pkg.scripts.lint) { "npm run lint" } else { $null }
            $buildCmd = if ($pkg.scripts -and $pkg.scripts.build) { "npm run build" } else { $null }
            if ($testCmd) { $commands += $testCmd }
            if ($lintCmd) { $commands += $lintCmd }
            if ($buildCmd) { $commands += $buildCmd }
        } catch {}
    }

    $pyproject = Join-Path $ProjectPath "pyproject.toml"
    if (Test-Path -LiteralPath $pyproject) {
        $commands += "pytest --tb=short 2>&1"
        $commands += "ruff check . 2>&1"
    }

    $makefile = Join-Path $ProjectPath "Makefile"
    if (Test-Path -LiteralPath $makefile) {
        $commands += "make test 2>&1"
        $commands += "make lint 2>&1"
    }

    return $commands
}

function Format-ToolingReport {
    param([hashtable]$Results)

    $sb = New-Object System.Text.StringBuilder
    [void]$sb.AppendLine("`n## TOOL EXECUTION REPORT (Orchestrator-Executed)")
    [void]$sb.AppendLine("")
    [void]$sb.AppendLine("| Command | Exit Code | Result | Output |")
    [void]$sb.AppendLine("|---------|-----------|--------|--------|")

    foreach ($cmd in ($Results.Keys | Sort-Object)) {
        $r = $Results[$cmd]
        $status = if ($r.success) { "PASS" } else { "FAIL" }
        $shortOutput = if ($r.output.Length -gt 200) {
            ($r.output.Substring(0, 200) -replace '\s+', ' ') + "..."
        } else {
            ($r.output -replace '\s+', ' ')
        }
        [void]$sb.AppendLine("| ``$cmd`` | $($r.exit_code) | $status | $shortOutput |")
    }

    $allPassed = ($Results.Values | Where-Object { -not $_.success }).Count -eq 0
    if ($allPassed) {
        [void]$sb.AppendLine("")
        [void]$sb.AppendLine("All tooling commands PASSED.")
    } else {
        [void]$sb.AppendLine("")
        [void]$sb.AppendLine("Some tooling commands FAILED. Do not declare compliance until resolved.")
    }

    return $sb.ToString()
}

function Generate-CyclePrompt {
    param(
        [string]$ProjectPath,
        [bool]$IsMultiAgent = $false
    )

    $fullProjectPath = $ProjectPath
    $config = Read-JsonFile $ConfigFile
    $state  = Read-JsonFile $CycleFile
    $findings = Read-JsonFile $FindingsFile
    $conv  = Read-JsonFile $ConvergenceFile

    if ($null -eq $config) {
        Write-Warning "Generate-CyclePrompt: config.json not found or is invalid. Using fallback engine settings."
    }

    $currentCycle = if ($null -ne $state -and $null -ne $state.current_cycle) { (Safe-Int $state.current_cycle) + 1 } else { 1 }
    $maxCycles = if ($null -ne $config -and $null -ne $config.engine -and $null -ne $config.engine.max_cycles) { Safe-Int $config.engine.max_cycles 25 } else { 25 }
    $maxNoProgress = if ($null -ne $config -and $null -ne $config.engine -and $null -ne $config.engine.max_cycles_without_progress) { Safe-Int $config.engine.max_cycles_without_progress 3 } else { 3 }

    $cyclesWithoutProgress = if ($null -ne $state -and $null -ne $state.cycles_without_progress) { Safe-Int $state.cycles_without_progress } else { 0 }
    $convClassification = if ($null -ne $conv) { Sanitize-PromptString ([string]$conv.classification) } else { "UNKNOWN" }
    $convConverged = if ($null -ne $conv) { Sanitize-PromptString ([string]$conv.converged) } else { "UNKNOWN" }

    $gitCtx = Get-GitContext -ProjectPath $ProjectPath
    $tooling = Get-ProjectTooling -ProjectPath $ProjectPath
    $findingsSummary = Get-FindingsSummary -Findings $findings

    $toolingBlock = ""
    if ($tooling.commands.PSBase.Keys.Count -gt 0) {
        $toolingBlock = "`n## DETECTED TOOLING`n`n| Command | Script |`n|---------|--------|"
        foreach ($cmd in ($tooling.commands.Keys | Sort-Object)) {
            $val = if ($tooling.commands[$cmd]) { $tooling.commands[$cmd] } else { "(detected, verify exact command)" }
            $safeCmd = Sanitize-PromptString $cmd
            $safeVal = Sanitize-PromptString $val
            $toolingBlock += "`n| ``$safeCmd`` | ``$safeVal`` |"
        }
    }

    $manifestBlock = ""
    if ($tooling.files.Count -gt 0) {
        $manifestBlock = "`n## PROJECT MANIFEST FILES`n`n"
        foreach ($f in $tooling.files) {
            $safeName = Sanitize-PromptString $f
            $manifestBlock += "- ``$safeName```n"
        }
    }

    $safeBranch = Sanitize-PromptString $gitCtx.Branch
    $safeCommits = Sanitize-PromptString $gitCtx.RecentCommits
    $safeStatus = Sanitize-PromptString $gitCtx.Status
    $safeProjectPath = Sanitize-PromptString $fullProjectPath
    $safeLastCommitMsg = Sanitize-PromptString $gitCtx.LastCommitMsg
    $safeLastCommitHash = Sanitize-PromptString $gitCtx.LastCommitHash
    $gitErrorNote = if ($gitCtx.GitError) { "`n**WARNING: git errors detected. Git context may be incomplete or unreliable.**`n" } else { "" }

    $scaleNote = ""
    if ($gitCtx.FileCount -gt 500) {
        $scaleNote = "`n**SCALE WARNING: Repository has $($gitCtx.FileCount) tracked files. Full audit may not fit in a single LLM context window. Prioritize high-risk files, dependency-critical paths, entry points, configuration, and security-sensitive code. Report the number of files actually audited vs total.**`n"
    }
    if ($gitCtx.FileCount -gt 2000) {
        $scaleNote = "`n**SCALE CRITICAL: Repository has $($gitCtx.FileCount) tracked files. Chunked/prioritized audit is MANDATORY. Full-context audit is impossible. Use dependency-graph-aware scoping.**`n"
    }

    if ($IsMultiAgent) {
        $multiAgentBlock = @"

## MULTI-AGENT MODE INSTRUCTION

This cycle operates in **multi-agent mode** for maximum thoroughness. Use the task tool to fan out independent audit work:

1. **Independent Auditor** - use agent type general, load .aura/agents/independent-auditor.md, audit the full repository, return findings array.
2. **Adversarial Auditor** - use agent type general, load .aura/docs/adversarial.md + .aura/agents/adversarial-auditor.md, attack the system, return findings array.
3. Wait for both. Correlate findings (deduplicate, merge).
4. **Remediator** - use agent type general, load .aura/agents/remediator.md, fix prioritized findings, return changed-files list.
5. **Verifier** - use agent type general, load .aura/agents/verifier.md, verify every fix, run full suite, return verdicts.
6. **Regression Auditor** - use agent type general, load .aura/agents/regression-auditor.md, check for regressions.
7. **Convergence Judge** - use agent type general, load .aura/agents/convergence-judge.md, evaluate all gates, return classification.

Run auditors (1+2) in parallel. Then remediator (4). Then verifier + regression auditor (5+6) in parallel. Then judge (7).
"@
    } else {
        $multiAgentBlock = @"

## EXECUTION MODE INSTRUCTION

You are executing this cycle as a single comprehensive agent. You must wear all hats: auditor, adversary, remediator, verifier, regression checker, and convergence judge. Complete ALL phases before reporting.
"@
    }

    $pushApprovalBlock = @"

---

## PUSH APPROVAL (Phase 13)

After ALL phases are complete and ALL state files are updated, you MUST display:

```
=== PUSH APPROVAL ===
Cycle: <N> | Classification: <X> | Open P0-P2: <N>
Files staged: [list of engine files]

[Push Now]  -- Commit all engine files + push to remote + verify remote SHA
[Push Later] -- Save state to disk only; user will push manually later
```

### Push Now behavior (engine invokes via -Action push -Approve):
1. Stage ONLY engine files (.aura/state/, .aura/reports/, .aura/docs/, .aura/agents/, .aura/config.json, run-audit.ps1, run-audit.sh, README.md, .gitignore, .gitattributes, .gitmessage)
2. **NEVER stage, reset, overwrite, or modify user changes that are NOT in the engine file set.** Verify working tree before staging: warn if untracked/ modified non-engine files exist.
3. Commit with template commit message.
4. Push to git remote.
5. **Verify remote HEAD SHA matches local committed SHA.** If mismatch, retry up to max_push_retries times (config).
6. If push succeeds and SHA verified: display success with remote SHA.
7. If push fails: state is safe on disk; user must push manually.

### Push Later behavior:
- State files are already on disk. No data loss. User runs `-Action push -Approve` later.

---

"@

    $sessionPrompt = @"
# CYCLE $currentCycle - FULL-SPECTRUM AUDIT & REMEDIATION

## ENGINE DIRECTIVE

You are executing **Cycle $currentCycle** of the Continuous Autonomous Engineering Audit Engine.
Your complete rules, standards, and methodology are defined in `.aura/docs/master.md`.
Your per-cycle execution blueprint is `.aura/docs/cycle.md`.

**Do not skip phases. Do not stop early. Do not fabricate evidence.**

## CRITICAL: STATE MACHINE ENFORCEMENT (v2.1.0)

The orchestrator now enforces a strict state machine on all state transitions. **You cannot bypass these gates:**

### Finding State Transitions (ENFORCED)
- ``OPEN`` → only ``IN_PROGRESS``, ``DEFERRED``, or ``BLOCKED``
- ``IN_PROGRESS`` → only ``FIXED``, ``DEFERRED``, ``BLOCKED``, or ``OPEN``
- ``FIXED`` → only ``VERIFYING`` or ``OPEN`` (regression)
- ``VERIFYING`` → only ``VERIFIED``, ``REJECTED``, or ``FIXED`` (retry)
- ``VERIFIED`` → only ``OPEN`` (recurrence)
- **FORBIDDEN: OPEN → VERIFIED** (must pass FIXED + VERIFYING)
- **FORBIDDEN: OPEN → FIXED** (must pass IN_PROGRESS)

### Convergence Gate Enforcement
- Any gate flipping from ``false`` to ``true`` requires evidence (which the orchestrator checks)
- ``consecutive_converged_cycles`` can only increase by 0 or 1 per cycle
- ``overall_score`` cannot decrease between cycles
- ``overall_score`` cannot increase by more than 15 per cycle
- ``converged`` can only become ``true`` when ALL 12 gates pass including ``module_dependency_integrity``
- Classification transitions are restricted to valid paths

### Tool Execution Required
- Before marking findings VERIFIED, you MUST run the target project's actual test/lint/build commands
- Use the orchestrator's ``-Action run-tooling`` to execute tooling and capture real exit codes
- Tool execution results are captured by the orchestrator, not claimed by the LLM
- Any verification claim without orchestrator-captured tool output will be rejected

### Scale Awareness
- If the project has more than 500 tracked files, full-audit-in-context is impossible
- Prioritize: high-risk files first, dependency-critical files, configuration, entry points
- For projects >2000 files, chunked/prioritized audit is mandatory
- Report how many files were actually audited vs total files

**Violations of any of the above rules will cause the orchestrator to reject your state updates and halt the cycle.**

---

---

## INJECTED CONTEXT - CURRENT SYSTEM STATE

### GIT STATE

$gitErrorNote
Branch: ``$safeBranch``

Recent commits:
````
$safeCommits
````

Last commit: ``$safeLastCommitHash`` -- ``$safeLastCommitMsg``

Working tree status:
````
$safeStatus
````

File count tracked: $($gitCtx.FileCount)
$scaleNote
### ENGINE STATE

**Cycle:** $currentCycle / max $maxCycles
**Cycles without progress:** $cyclesWithoutProgress / max $maxNoProgress
**Last classification:** $convClassification
**Convergence status:** $convConverged
$findingsSummary
$manifestBlock
$toolingBlock

### STATE MACHINE STATUS

**STATE AUTHORITY ISOLATION**: The LLM writes to ``proposed-*.json`` files. The orchestrator validates and promotes valid state to actual state files. Illegal transitions are REJECTED.

- Write findings to ``.aura/state/proposed-findings.json``, NOT ``findings.json``
- Write convergence to ``.aura/state/proposed-convergence.json``, NOT ``convergence.json``  
- Write cycle state to ``.aura/state/proposed-cycle.json``, NOT ``cycle.json``
- Write tool output evidence to ``.aura/state/tooling-evidence.json``

Run ``-Action promote-state`` after writing all proposed files to validate and promote.

**TOOL EXECUTION**: Before marking findings as VERIFIED, you MUST:
1. Run ``-Action run-tooling`` to execute the project's test/lint/build commands
2. Save the RAW orchestrator output to ``.aura/state/tooling-evidence.json``
3. Reference this evidence in your proposed findings
LLM-claimed test results without orchestrator-captured exit codes WILL be rejected during promote-state.

---

## CYCLE INSTRUCTIONS

**IMPORTANT**: All engine paths are relative to the repository root.

Read these files **in parallel** (batch read) before acting:

1. ``.aura/docs/master.md`` - audit rules, standards, methodology
2. ``.aura/docs/cycle.md`` - per-cycle phases (Phase 1-13)
3. ``.aura/reports/architecture-map.md`` - prior architecture model
4. ``.aura/reports/risk-register.md`` - prior risk register
5. ``.aura/reports/remediation-log.md`` - prior remediation history
6. ``.aura/reports/verification-matrix.md`` - prior verification evidence
7. ``.aura/reports/audit-ledger.md`` - full finding history
8. ``.aura/state/findings.json`` - machine-readable findings
9. ``.aura/state/convergence.json`` - convergence gate history

## MANDATORY FULL-SPECTRUM AUDIT EVERY CYCLE

**NEVER skip phases. NEVER shortcut the audit. Zero open findings does NOT prove zero undiscovered findings.**

Every cycle MUST perform:

1. **Full independent fresh audit** -- read and audit the ENTIRE repository at ``$safeProjectPath``, not just changed files. Do NOT skip unchanged files. Do NOT assume prior-cycle findings are complete. Undiscovered defects are real until proven otherwise.
2. **Independent adversarial review** every cycle -- inhabit ALL 6 adversarial roles (attacker, incident, dependency, hostile_input, scale, maintainer) and produce fresh findings regardless of prior-cycle results.
3. **Full correlation** of all findings from both independent auditor and adversarial auditor -- merge, deduplicate, identify new vs known.
4. **If any new material findings exist:** proceed to PRIORITIZE -> REMEDIATE -> TEST -> VERIFY -> REGRESSION.
5. **Remediation must always be followed by independent verification and regression audit.** Never self-verify fixes.
6. **Only after completing all phases:** evaluate convergence gates.

## CONVERGENCE GATE RULES

**Convergence requires repeated independent audit cycles with ZERO material new findings:**

- Gate ``no_material_new_findings``: must remain TRUE for **2 consecutive full independent audits** across 2 separate cycles.
- Gate ``consecutive_clean_independent_audits``: currently passes when 2 consecutive cycles have zero new P0-P3 findings.
- A single new P0-P3 material finding in ANY cycle resets the consecutive counter to 0.
- Only the convergence judge (agent/convergence-judge.md) may declare CONVERGED.
- CONVERGED means: all 12 gates PASS (including module_dependency_integrity), at least min_independent_cycles completed, 2 consecutive clean audits, no human blockers.
- DO NOT declare converged merely because P0-P2 are zero. That is a snapshot, not proof.
- REMINDER: The gate ``module_dependency_integrity`` is controlled by the ORCHESTRATOR (not the LLM). You cannot flip it. It reflects whether all required engine modules are loaded.

## TARGET REPOSITORY

**Critical: the target repository is ``$safeProjectPath``.** The .aura directory at that path is ENGINE STATE ONLY. Do NOT audit .aura/ as target code. The .aura/ directory contains engine configuration, state, reports, agents, and documentation. Target code is everything ELSE under ``$safeProjectPath``. Always use ``$safeProjectPath`` as the git root for target operations.

Then execute EVERY phase of .aura/docs/cycle.md against the repository at:

**``$safeProjectPath``**

---

## AFTER THIS CYCLE

**STATE AUTHORITY ISOLATION (v2.1.0): The LLM does NOT write directly to state files.**

Write your proposed state changes to these files instead:

1. ``.aura/state/proposed-cycle.json`` — proposed cycle state (increment cycle, update phase)
2. ``.aura/state/proposed-findings.json`` — proposed findings (new + updated statuses, observing state machine rules)
3. ``.aura/state/proposed-convergence.json`` — proposed convergence gates and classification
4. ``.aura/state/tooling-evidence.json`` — RAW orchestrator-captured tool output (not LLM claims).

After you write the proposed files, the orchestrator will:
- Validate all state transitions against the state machine
- Verify gate evidence for any false→true flips
- Check counter integrity, score limits, classification paths
- Execute ``-Action run-tooling`` to capture real tool output
- Promote valid proposed state to actual state files
- Reject invalid state and halt the cycle

**You MUST write proposed-*.json — NOT findings.json, cycle.json, or convergence.json directly.**

5. Update all five reports in ``.aura/reports/``
6. Output the convergence verdict (NOT_READY / CONDITIONALLY_READY / PRODUCTION_READY / HUMAN_BLOCKED)
7. After all updates, prompt the user for PUSH APPROVAL (Push Now / Push Later)

**CRITICAL: The orchestrator validates every proposed state change before promotion. Illegal transitions will REJECT the cycle. Write to proposed-*.json files ONLY. The tooling-evidence.json must contain RAW orchestrator output from ``-Action run-tooling`` — NEVER fabricate tool results.

**STOP AFTER WRITING PROPOSED FILES**: Do NOT invoke ``-Action run``, ``-Action run-tooling``, or ``-Action promote-state``. These are human-operated commands. Your job ends when all proposed-*.json files and reports are written. The human will review your work and run ``-Action promote-state`` to validate and commit, then ``-Action run`` to start the next cycle. Starting ``-Action run`` before promote-state will BLOCK with proposed-state-already-exists error.

**REMEMBER:** tests passed is NOT convergence. build passed is NOT convergence.
Only the full gate matrix (all 12 gates PASS including module_dependency_integrity, P0=0, P1=0, P2=0, all critical gates PASS, no material new findings) is convergence.
**The module_dependency_integrity gate is ORCHESTRATOR-CONTROLLED. You CANNOT set it to true. It reflects whether real engine modules actually loaded at startup.**

$multiAgentBlock
$pushApprovalBlock
---

**BEGIN CYCLE $currentCycle NOW.**
"@

    return @{
        prompt = $sessionPrompt
        cycle = $currentCycle
        projectPath = $fullProjectPath
        gitContext = $gitCtx
        tooling = $tooling
    }
}

function Get-PushWorkingSet($ProjectRoot, $RuntimePath) {
    $files = @()

    $stateDir = Join-Path $RuntimePath "state"
    if (Test-Path -LiteralPath $stateDir) {
        $files += (Get-ChildItem -LiteralPath $stateDir -File | ForEach-Object { $_.FullName })
    }

    $reportsDir = Join-Path $RuntimePath "reports"
    if (Test-Path -LiteralPath $reportsDir) {
        $files += (Get-ChildItem -LiteralPath $reportsDir -File | ForEach-Object { $_.FullName })
    }

    $docsDir = Join-Path $RuntimePath "docs"
    if (Test-Path -LiteralPath $docsDir) {
        $files += (Get-ChildItem -LiteralPath $docsDir -File | ForEach-Object { $_.FullName })
    }

    $agentsDir = Join-Path $RuntimePath "agents"
    if (Test-Path -LiteralPath $agentsDir) {
        $files += (Get-ChildItem -LiteralPath $agentsDir -File | ForEach-Object { $_.FullName })
    }

    $srcModulesDir = Join-Path $RepoRoot "src/modules"
    if (Test-Path -LiteralPath $srcModulesDir) {
        $files += (Get-ChildItem -LiteralPath $srcModulesDir -File | ForEach-Object { $_.FullName })
    }

    $srcAgentsDir = Join-Path $RepoRoot "src/agents"
    if (Test-Path -LiteralPath $srcAgentsDir) {
        $files += (Get-ChildItem -LiteralPath $srcAgentsDir -File | ForEach-Object { $_.FullName })
    }

    $configFile = Join-Path $RepoRoot "config/aura.json"
    if (Test-Path -LiteralPath $configFile) {
        $files += $configFile
    }

    $psScript = Join-Path $RepoRoot "src/engine/run-audit.ps1"
    if (Test-Path -LiteralPath $psScript) {
        $files += $psScript
    }

    $auraProxy = Join-Path $ProjectRoot ".aura/run-audit.ps1"
    if (Test-Path -LiteralPath $auraProxy) {
        $files += $auraProxy
    }

    $rootFiles = @("README.md", "run-audit.sh", "bin/aura.ps1", "bin/aura.sh", ".gitignore", ".gitattributes", ".gitmessage")
    foreach ($rf in $rootFiles) {
        $rp = Join-Path $ProjectRoot $rf
        if (Test-Path -LiteralPath $rp) {
            $files += $rp
        }
    }

    return $files | Select-Object -Unique
}

function Get-PushSummary($State, $Findings, $Conv) {
    $cycle = if ($State) { $State.current_cycle } else { "?" }
    $classification = if ($Conv) { $Conv.classification } else { "UNKNOWN" }

    $p0 = if ($Findings -and $Findings.findings) {
        ($Findings.findings | Where-Object { $_.severity -eq "P0" -and $_.status -ne "VERIFIED" }).Count
    } else { 0 }
    $p1 = if ($Findings -and $Findings.findings) {
        ($Findings.findings | Where-Object { $_.severity -eq "P1" -and $_.status -ne "VERIFIED" }).Count
    } else { 0 }
    $p2 = if ($Findings -and $Findings.findings) {
        ($Findings.findings | Where-Object { $_.severity -eq "P2" -and $_.status -ne "VERIFIED" }).Count
    } else { 0 }

    if ($p0 -eq 0 -and $p1 -eq 0 -and $p2 -eq 0) {
        $summaryType = "clean"
    } elseif ($p0 -eq 0 -and $p1 -eq 0) {
        $summaryType = "minor"
    } else {
        $summaryType = "critical"
    }

    return @{
        cycle = $cycle
        classification = $classification
        p0_open = $p0
        p1_open = $p1
        p2_open = $p2
        summaryType = $summaryType
    }
}

function Invoke-EnginePush($ProjectRoot, $EngineRoot, $ForceApprove, $Amend) {
    $gitCtx = Get-GitContext -ProjectPath $ProjectRoot
    if ($gitCtx.Error -or $gitCtx.GitError) {
        Write-Host "[BLOCKED] Git not available. Cannot push." -ForegroundColor Red
        return $false
    }

    $state = Read-JsonFile $CycleFile
    $findings = Read-JsonFile $FindingsFile
    $conv = Read-JsonFile $ConvergenceFile
    $config = Read-JsonFile $ConfigFile

    $summary = Get-PushSummary -State $state -Findings $findings -Conv $conv

    $files = Get-PushWorkingSet -ProjectRoot $ProjectRoot -EngineRoot $EngineRoot
    $relativeFiles = $files | ForEach-Object {
        $_.Replace($ProjectRoot, "").TrimStart("\", "/")
    }

    Write-Host "`n=== PUSH APPROVAL ===" -ForegroundColor Cyan
    Write-Host "Cycle:       $($summary.cycle)"
    Write-Host "Status:      $($summary.classification)"
    Write-Host "Open P0-P2:  $($summary.p0_open + $summary.p1_open + $summary.p2_open)"
    Write-Host ""

    $pushEnabled = if ($config -and $config.push) { $config.push.enabled } else { $true }
    if (-not $pushEnabled) {
        Write-Host "[SKIP] Push is disabled in config.json (push.enabled = false)." -ForegroundColor Yellow
        return $false
    }

    $cwd = Get-Location
    try {
        Set-Location -LiteralPath $ProjectRoot

        $gitCheck = git rev-parse --git-dir 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Host "[ERROR] Not a git repository or git not available." -ForegroundColor Red
            return $false
        }

        Write-Host "Files to stage:" -ForegroundColor Yellow
        foreach ($rf in ($relativeFiles | Sort-Object)) {
            Write-Host "  + $rf"
        }
        Write-Host ""

        $statusOutput = git status --porcelain 2>&1
        $allModified = if ($LASTEXITCODE -eq 0) {
            ($statusOutput -split "`n" | ForEach-Object { ($_ -replace '^...', '').Trim() } | Where-Object { $_ })
        } else { @() }

        $engineFileSet = $relativeFiles | ForEach-Object { $_.Replace("\", "/") }
        $nonEngineModified = @($allModified | Where-Object {
            $norm = $_.Replace("\", "/").TrimStart("/")
            ($norm -notin $engineFileSet) -and ($norm -ne "")
        })

        if ($nonEngineModified.Count -gt 0) {
            Write-Host "[WARNING] Non-engine files modified in working tree:" -ForegroundColor Yellow
            foreach ($f in $nonEngineModified) {
                Write-Host "  ! $f" -ForegroundColor Yellow
            }
            Write-Host "  These files will NOT be staged, reset, or modified."
            Write-Host ""
        }

        if (-not $ForceApprove) {
            Write-Host "Commit and push engine files now?"
            Write-Host "  [P] Push Now     -- commit engine files + push to remote + verify remote SHA"
            Write-Host "  [L] Push Later    -- skip; state saved to disk, push manually later"
            Write-Host "  [N] No / Cancel   -- abort"
            Write-Host ""
            $choice = Read-Host "Choice (P/L/N)"

            switch ($choice.ToUpper()) {
                "P" { Write-Host "`n[OK] Proceeding with push..." -ForegroundColor Green }
                "L" {
                    Write-Host "`n[OK] Skipping push. Engine state saved to disk. No data loss." -ForegroundColor Yellow
                    Write-Host "  Run '-Action push -Approve' later to push." -ForegroundColor Yellow
                    return $false
                }
                default {
                    Write-Host "`n[CANCEL] Push aborted. State saved to disk." -ForegroundColor Red
                    return $false
                }
            }
        } else {
            Write-Host "[APPROVED] Auto-approved push proceeding..." -ForegroundColor Green
        }

        $commitMsg = if ($config -and $config.push.commit_template) {
            $template = $config.push.commit_template
            $template = $template -replace "{cycle}", $summary.cycle
            $template = $template -replace "{classification}", $summary.classification
            $template = $template -replace "{summary}", $summary.summaryType
            $template
        } else {
            "audit: cycle $($summary.cycle) automated remediation"
        }

        # === TRANSACTIONAL GIT STAGING ===
        # Capture pre-staging state snapshot
        $preStageSha = (git rev-parse HEAD 2>&1 | Out-String).Trim()
        $preStageStatus = (git status --porcelain 2>&1 | Out-String).Trim()

        $tempIndexFile = Join-Path ([System.IO.Path]::GetTempPath()) "aura-push-$([System.Guid]::NewGuid().ToString('N').Substring(0,8)).index"
        $oldIndexFile = $env:GIT_INDEX_FILE
        $env:GIT_INDEX_FILE = $tempIndexFile

        try {
            Write-Host "[GIT] Using transactional staging (temp index: $(Split-Path -Leaf $tempIndexFile))" -ForegroundColor Cyan

            $stagingOk = $true
            foreach ($rf in $relativeFiles) {
                git add ":(literal)$rf" 2>&1 | Out-Null
                if ($LASTEXITCODE -ne 0) {
                    Write-Host "[WARNING] Failed to stage: $rf" -ForegroundColor Yellow
                    $stagingOk = $false
                }
            }

            if (-not $stagingOk) {
                Write-Host "[GIT] Staging incomplete — aborting transactional push." -ForegroundColor Red
                $env:GIT_INDEX_FILE = $oldIndexFile
                if (Test-Path -LiteralPath $tempIndexFile) { Remove-Item -LiteralPath $tempIndexFile -Force }
                return $false
            }

            $tempStagedFiles = (git diff --cached --name-only 2>&1 | Out-String).Trim()
            $stagedLines = if ($tempStagedFiles) { @($tempStagedFiles -split "`n" | ForEach-Object { $_.Trim() } | Where-Object { $_ }) } else { @() }
            $engineNormSet = $relativeFiles | ForEach-Object { $_.Replace("\", "/").TrimStart("/") }
            $nonEngineStaged = @($stagedLines | Where-Object {
                $norm = $_.Replace("\", "/").TrimStart("/")
                ($norm -notin $engineNormSet) -and ($norm -ne "")
            })

            if ($nonEngineStaged.Count -gt 0) {
                Write-Host "[GIT] TRANSACTION ABORTED — non-engine files staged in temp index:" -ForegroundColor Red
                foreach ($f in $nonEngineStaged) { Write-Host "  ! $f" -ForegroundColor Red }
                $env:GIT_INDEX_FILE = $oldIndexFile
                if (Test-Path -LiteralPath $tempIndexFile) { Remove-Item -LiteralPath $tempIndexFile -Force }
                return $false
            }

            if ($Amend) {
                git commit --amend --no-edit 2>&1 | Out-Null
                if ($LASTEXITCODE -ne 0) {
                    Write-Host "[WARNING] Amend failed. Creating new commit instead." -ForegroundColor Yellow
                    git commit -m $commitMsg 2>&1 | Out-Null
                } else {
                    Write-Host "[OK] Amended latest commit (transactional index)." -ForegroundColor Green
                }
            } else {
                git commit -m $commitMsg 2>&1 | Out-Null
                if ($LASTEXITCODE -ne 0) {
                    Write-Host "[ERROR] Commit failed. User index untouched. Check git status." -ForegroundColor Red
                    $env:GIT_INDEX_FILE = $oldIndexFile
                    if (Test-Path -LiteralPath $tempIndexFile) { Remove-Item -LiteralPath $tempIndexFile -Force }
                    return $false
                }
                Write-Host "[OK] Committed: $commitMsg (transactional index)" -ForegroundColor Green
            }

            Write-Host "[GIT] Transaction complete. User index preserved." -ForegroundColor Green
        } finally {
            $env:GIT_INDEX_FILE = $oldIndexFile
            if (Test-Path -LiteralPath $tempIndexFile) { Remove-Item -LiteralPath $tempIndexFile -Force -ErrorAction SilentlyContinue }
        }

        $localSha = (git rev-parse HEAD 2>&1 | Out-String).Trim()
        if (-not $localSha) {
            Write-Host "[ERROR] Could not get local HEAD SHA after commit." -ForegroundColor Red
            return $false
        }
        Write-Host "  Local SHA: $localSha"

        $maxRetries = if ($config -and $config.push -and $config.push.max_push_retries) {
            Safe-Int $config.push.max_push_retries 3
        } else { 3 }

        $pushSuccess = $false
        for ($attempt = 1; $attempt -le $maxRetries; $attempt++) {
            $pushOutput = git push 2>&1 | Out-String
            if ($LASTEXITCODE -eq 0) {
                $pushSuccess = $true
                break
            }
            if ($attempt -lt $maxRetries) {
                Write-Host "[RETRY] Push attempt $attempt failed. Retrying..." -ForegroundColor Yellow
                Start-Sleep -Seconds 2
            }
        }

        if (-not $pushSuccess) {
            Write-Host "[WARNING] Push to remote failed after $maxRetries attempt(s)." -ForegroundColor Yellow
            Write-Host "  Commit is local only (SHA: $localSha). Run 'git push' manually." -ForegroundColor Yellow
            return $false
        }

        Write-Host "[OK] Push succeeded." -ForegroundColor Green

        $verifyRemote = if ($config -and $config.push) { $config.push.verify_remote_sha_after_push } else { $true }
        if ($verifyRemote) {
            git fetch origin 2>&1 | Out-Null
            $remoteSha = (git rev-parse "origin/$($gitCtx.Branch)" 2>&1 | Out-String).Trim()
            if ($remoteSha -eq $localSha) {
                Write-Host "[VERIFIED] Remote SHA matches local SHA: $remoteSha" -ForegroundColor Green
            } else {
                Write-Host "[WARNING] Remote SHA mismatch:" -ForegroundColor Yellow
                Write-Host "  Local:  $localSha"
                Write-Host "  Remote: $remoteSha"
                Write-Host "  Manual verification recommended." -ForegroundColor Yellow
            }
        }

        return $true
    } finally {
        Set-Location $cwd.Path
    }
}

# ============================================================
# MAIN
# ============================================================

# Module loading MUST happen at script scope (not inside a function)
# because dot-sourcing inside a function scopes loaded functions to
# that function's scope only.

# ============================================================
# MODULE LOADING
# ============================================================

# Config file path must be resolved early for module classification
$ConfigFile = Join-Path $RepoRoot "config/aura.json"

$Script:modLoadFailed = @()
$Script:modLoadCount = 0
$Script:modRequiredFailures = @()
$Script:modOptionalFailures = @()
$Script:modExperimentalFailures = @()
$Script:modUnknownFailures = @()

$moduleConfig = if (Test-Path -LiteralPath $ConfigFile) {
    $cfg = Read-JsonFile $ConfigFile
    if ($cfg -and $cfg.modules) { $cfg.modules } else { $null }
} else { $null }

$moduleRequiredSet = @{}
$moduleOptionalSet = @{}
$moduleExperimentalSet = @{}

if ($moduleConfig) {
    foreach ($m in $moduleConfig.required) { $moduleRequiredSet[$m] = $true }
    foreach ($m in $moduleConfig.optional) { $moduleOptionalSet[$m] = $true }
    foreach ($m in $moduleConfig.experimental) { $moduleExperimentalSet[$m] = $true }
}

$moduleOrder = @(
    "business-invariants.ps1",
    "evidence-integrity.ps1",
    "independent-verifier.ps1",
    "repo-graph.ps1",
    "sandbox.ps1",
    "security-scan.ps1",
    "git-safety.ps1",
    "git-safety-adversarial.ps1",
    "capability-scoring.ps1",
    "scale-benchmark.ps1",
    "mutation-testing.ps1",
    "failure-recovery.ps1",
    "false-evidence-attacks.ps1",
    "adversarial-campaign.ps1",
    "false-convergence-extended.ps1"
)

foreach ($modName in $moduleOrder) {
    $modPath = Join-Path $ModulesDirResolved $modName
    if (Test-Path -LiteralPath $modPath) {
        try {
            . $modPath
            $Script:modLoadCount++
        } catch {
            $Script:modLoadFailed += "$modName -- $_"
            $classification = "UNCLASSIFIED"
            if ($moduleRequiredSet.ContainsKey($modName)) {
                $Script:modRequiredFailures += "$modName -- $_"
                $classification = "REQUIRED"
            } elseif ($moduleOptionalSet.ContainsKey($modName)) {
                $Script:modOptionalFailures += "$modName -- $_"
                $classification = "OPTIONAL"
            } elseif ($moduleExperimentalSet.ContainsKey($modName)) {
                $Script:modExperimentalFailures += "$modName -- $_"
                $classification = "EXPERIMENTAL"
            } else {
                $Script:modRequiredFailures += "$modName -- $_ (unclassified, treated as REQUIRED)"
                $classification = "UNCLASSIFIED (treated as REQUIRED)"
            }
            $color = if ($classification -like "REQUIRED*") { "Red" } else { "DarkYellow" }
            Write-Host "[AURA] MODULE LOAD FAILURE [$classification]: $modName -- $_" -ForegroundColor $color
        }
    } else {
        $modEntry = "$modName (file not found)"
        $Script:modLoadFailed += $modEntry
        if ($moduleRequiredSet.ContainsKey($modName)) {
            $Script:modRequiredFailures += $modEntry
            Write-Host "[AURA] MODULE MISSING [REQUIRED]: $modName" -ForegroundColor Red
        } elseif ($moduleOptionalSet.ContainsKey($modName)) {
            $Script:modOptionalFailures += $modEntry
            Write-Host "[AURA] MODULE MISSING [OPTIONAL]: $modName" -ForegroundColor DarkYellow
        } elseif ($moduleExperimentalSet.ContainsKey($modName)) {
            $Script:modExperimentalFailures += $modEntry
            Write-Host "[AURA] MODULE MISSING [EXPERIMENTAL]: $modName" -ForegroundColor DarkGray
        } else {
            $Script:modRequiredFailures += "$modEntry (unclassified, treated as REQUIRED)"
            Write-Host "[AURA] MODULE MISSING [UNCLASSIFIED]: $modName (treated as REQUIRED)" -ForegroundColor Red
        }
    }
}

$Script:moduleIntegrityPass = ($Script:modRequiredFailures.Count -eq 0)

$modResult = @{
    loaded = $Script:modLoadCount
    total = $moduleOrder.Count
    failed = $Script:modLoadFailed
    required_failures = $Script:modRequiredFailures
    optional_failures = $Script:modOptionalFailures
    experimental_failures = $Script:modExperimentalFailures
    module_integrity_pass = $Script:moduleIntegrityPass
    missingCommands = @()
}

if ($Script:modLoadFailed.Count -gt 0) {
    Write-Host "[AURA] MODULE_DEPENDENCY_FAILURE: $($Script:modLoadFailed.Count) module(s) could not be loaded." -ForegroundColor $(if ($Script:modRequiredFailures.Count -gt 0) { "Red" } else { "Yellow" })
    if ($Script:modRequiredFailures.Count -gt 0) {
        Write-Host "[AURA] REQUIRED MODULE FAILURES ($($Script:modRequiredFailures.Count)):" -ForegroundColor Red
        foreach ($rf in $Script:modRequiredFailures) {
            Write-Host "  [REQUIRED FAIL] $rf" -ForegroundColor Red
        }
        Write-Host "[AURA] CONVERGENCE BLOCKED: $($Script:modRequiredFailures.Count) required module(s) missing or failed to load." -ForegroundColor Red
        Write-Host "[AURA] Classification cannot be PRODUCTION_READY until all required modules are available and loaded." -ForegroundColor Red
    }
    if ($Script:modOptionalFailures.Count -gt 0) {
        Write-Host "[AURA] OPTIONAL MODULE WARNINGS ($($Script:modOptionalFailures.Count)): $($Script:modOptionalFailures -join '; ')" -ForegroundColor DarkYellow
    }
    if ($Script:modExperimentalFailures.Count -gt 0) {
        Write-Host "[AURA] EXPERIMENTAL MODULE WARNINGS ($($Script:modExperimentalFailures.Count)): $($Script:modExperimentalFailures -join '; ')" -ForegroundColor DarkGray
    }
}

if (-not $Script:moduleIntegrityPass) {
    Write-Host ""
    Write-Host "================================================================" -ForegroundColor Red
    Write-Host "  MODULE DEPENDENCY INTEGRITY: FAILED" -ForegroundColor Red
    Write-Host "  Engine is operating in DEGRADED mode." -ForegroundColor Red
    Write-Host "  Convergence to PRODUCTION_READY is BLOCKED." -ForegroundColor Red
    Write-Host "================================================================" -ForegroundColor Red
    Write-Host ""
} else {
    Write-Host "[AURA] MODULE INTEGRITY: All required modules loaded successfully." -ForegroundColor Green
}

$requiredValidatorCommands = @("Validate-FindingStateIntegrity", "Validate-GateEvidenceIntegrity", "Test-ValidClassificationTransition")
$Script:missingValidators = @()
foreach ($cmdName in $requiredValidatorCommands) {
    if (-not (Get-Command $cmdName -ErrorAction SilentlyContinue)) {
        $Script:missingValidators += $cmdName
    }
}
if ($Script:missingValidators.Count -gt 0) {
    Write-Host "[AURA] REQUIRED COMMAND VALIDATION FAILURE: $($Script:missingValidators -join ', ') not available." -ForegroundColor Red
}

Write-Banner

try {
    $fullProjectPath = Resolve-Path -LiteralPath $TargetProject
} catch {
    Write-Error "Target project path does not exist or is invalid: $TargetProject"
    exit 1
}

$RuntimeDir = Join-Path $fullProjectPath ".aura"
if (-not (Test-Path -LiteralPath $RuntimeDir)) {
    New-Item -ItemType Directory -Force -Path $RuntimeDir | Out-Null
}

$EngineRoot = $RuntimeDir

$ReportsDir = Join-Path $EngineRoot "reports"
if (-not (Test-Path -LiteralPath $ReportsDir)) {
    New-Item -ItemType Directory -Force -Path $ReportsDir | Out-Null
}

$StateDir = Join-Path $EngineRoot "state"
if (-not (Test-Path -LiteralPath $StateDir)) {
    New-Item -ItemType Directory -Force -Path $StateDir | Out-Null
}

$CycleFile  = Join-Path $EngineRoot "state/cycle.json"
$FindingsFile = Join-Path $EngineRoot "state/findings.json"
$ConvergenceFile = Join-Path $EngineRoot "state/convergence.json"

$ProposedCycleFile = Join-Path $EngineRoot "state/proposed-cycle.json"
$ProposedFindingsFile = Join-Path $EngineRoot "state/proposed-findings.json"
$ProposedConvergenceFile = Join-Path $EngineRoot "state/proposed-convergence.json"
$ToolingEvidenceFile = Join-Path $EngineRoot "state/tooling-evidence.json"

$bootstrapDocsDir = Join-Path $EngineRoot "docs"
if (-not (Test-Path -LiteralPath $bootstrapDocsDir)) {
    New-Item -ItemType Directory -Force -Path $bootstrapDocsDir | Out-Null
    $sourceDocsDir = Join-Path $RepoRoot "docs"
    if (Test-Path -LiteralPath $sourceDocsDir) {
        Get-ChildItem -LiteralPath $sourceDocsDir -File | ForEach-Object {
            Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $bootstrapDocsDir $_.Name) -Force -ErrorAction SilentlyContinue
        }
    }
}

$bootstrapAgentsDir = Join-Path $EngineRoot "agents"
if (-not (Test-Path -LiteralPath $bootstrapAgentsDir)) {
    New-Item -ItemType Directory -Force -Path $bootstrapAgentsDir | Out-Null
    $sourceAgentsDir = Join-Path $RepoRoot "src/agents"
    if (Test-Path -LiteralPath $sourceAgentsDir) {
        Get-ChildItem -LiteralPath $sourceAgentsDir -File | ForEach-Object {
            Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $bootstrapAgentsDir $_.Name) -Force -ErrorAction SilentlyContinue
        }
    }
}

switch ($Action) {
    "status" {
        Get-ConvergenceStatus
    }

    "reset" {
        Reset-Engine
    }

    "context" {
        $state = Read-JsonFile $CycleFile
        if (-not $state -or $state.status -eq "NOT_STARTED") {
            Write-Host "[INIT] State not initialized - initializing engine state..." -ForegroundColor Yellow
            Initialize-State
        }
        $result = Generate-CyclePrompt -ProjectPath $fullProjectPath -IsMultiAgent:$MultiAgent
        $ctxFile = Join-Path $EngineRoot "generated-cycle-prompt.md"
        Write-TextFile $ctxFile $result.prompt
        Write-Host "[OK] Context + prompt generated -> $ctxFile" -ForegroundColor Green
    }

    "run" {
        $state = Read-JsonFile $CycleFile
        if (-not $state -or $state.status -eq "NOT_STARTED") {
            Write-Host "[INIT] First run - initializing engine state..." -ForegroundColor Yellow
            Initialize-State
        }

        $hasProposedFindings = Test-Path -LiteralPath $ProposedFindingsFile
        $hasProposedConv = Test-Path -LiteralPath $ProposedConvergenceFile
        $hasProposedCycle = Test-Path -LiteralPath $ProposedCycleFile

        if ($hasProposedFindings -or $hasProposedConv -or $hasProposedCycle) {
            Write-Host "[BLOCKED] Proposed state files already exist — previous cycle was not promoted." -ForegroundColor Red
            Write-Host "  Found:"
            if ($hasProposedFindings)  { Write-Host "    $ProposedFindingsFile" -ForegroundColor Yellow }
            if ($hasProposedConv)      { Write-Host "    $ProposedConvergenceFile" -ForegroundColor Yellow }
            if ($hasProposedCycle)     { Write-Host "    $ProposedCycleFile" -ForegroundColor Yellow }
            Write-Host ""
            Write-Host "  The AI agent must run -Action promote-state to validate and commit the previous cycle."
            Write-Host "  If the proposed state is stale/abandoned, delete the proposed-*.json files manually"
            Write-Host "  or run -Action reset to start fresh."
            Write-Host ""
            Write-Host "  NEVER run -Action run again with unreviewed proposed state. This causes duplicate cycles."
            Write-Host "  The orchestrator does NOT auto-start new cycles. Each cycle requires:"
            Write-Host "    1. human runs -Action run         → produces generated-cycle-prompt.md"
            Write-Host "    2. human feeds prompt to AI agent"
            Write-Host "    3. AI agent writes proposed-*.json"
            Write-Host "    4. human runs -Action promote-state → validates and commits"
            Write-Host "    5. (repeat from step 1 only after promote-state succeeds)"
            return
        }

        $conv = Read-JsonFile $ConvergenceFile
        $config = Read-JsonFile $ConfigFile
        $minIndependent = if ($null -ne $config -and $null -ne $config.engine -and $null -ne $config.engine.min_independent_cycles_for_convergence) {
            Safe-Int $config.engine.min_independent_cycles_for_convergence 3
        } else { 3 }
        $requiredConsecutive = if ($null -ne $config -and $null -ne $config.engine) {
            Safe-Int $config.engine.consecutive_converged_cycles_required 2
        } else { 2 }

        if ($null -ne $conv -and $conv.converged -and -not $Force) {
            $cyclesOk = (Safe-Int $state.cycles_completed) -ge $minIndependent
            $consecutiveOk = (Safe-Int $conv.consecutive_converged_cycles) -ge $requiredConsecutive

            $moduleOk = $true
            if ($conv.gates -and (Get-Member -InputObject $conv.gates -Name "module_dependency_integrity" -MemberType NoteProperty -ErrorAction SilentlyContinue)) {
                $moduleOk = [bool]$conv.gates.module_dependency_integrity
            } elseif ($null -ne $conv.module_status) {
                $moduleOk = [bool]$conv.module_status.integrity_pass
            }

            if (-not $moduleOk) {
                Write-Host "[OVERRIDE] Convergence cannot be trusted — required modules failed to load. Forcing new cycle." -ForegroundColor Red
                Write-Host "  Required module failures:"
                if ($conv.module_status -and $conv.module_status.required_failures) {
                    foreach ($rf in $conv.module_status.required_failures) { Write-Host "    $rf" -ForegroundColor Red }
                }
            } elseif ($cyclesOk -and $consecutiveOk) {
                Write-Host "[HALT] Engine has converged (cycles: $($state.cycles_completed)/$minIndependent, consecutive: $($conv.consecutive_converged_cycles)/$requiredConsecutive). Use -Force to run again." -ForegroundColor Green
                Get-ConvergenceStatus
                return
            } else {
                Write-Host "[NOTE] cycle converged flag is set but cycles ($($state.cycles_completed)/$($minIndependent)) or consecutive ($($conv.consecutive_converged_cycles)/$($requiredConsecutive)) not met. Proceeding." -ForegroundColor Yellow
            }
        }

        if ($null -eq $config) {
            Write-Warning "config.json not found or invalid. Using fallback max_cycles=25."
        }
        $maxCycles = if ($null -ne $config -and $null -ne $config.engine) { Safe-Int $config.engine.max_cycles 25 } else { 25 }
        $currentCycleVal = Safe-Int $state.current_cycle
        if ($currentCycleVal -ge $maxCycles -and -not $Force) {
            Write-Host "[HALT] Max cycles ($maxCycles) reached. Use -Force to continue." -ForegroundColor Yellow
            return
        }

        $maxNoProgress = if ($null -ne $config -and $null -ne $config.engine -and $null -ne $config.engine.max_cycles_without_progress) { Safe-Int $config.engine.max_cycles_without_progress 3 } else { 3 }
        $cyclesWoProgress = Safe-Int $state.cycles_without_progress
        if ($cyclesWoProgress -ge $maxNoProgress -and -not $Force) {
            Write-Host "[HALT] Maximum cycles without progress ($maxNoProgress) reached. Use -Force to continue." -ForegroundColor Yellow
            return
        }

        $result = Generate-CyclePrompt -ProjectPath $fullProjectPath -IsMultiAgent:$MultiAgent

        $ctxFile = Join-Path $EngineRoot "generated-cycle-prompt.md"
        Write-TextFile $ctxFile $result.prompt

        Write-Host "  Cycle:       $($result.cycle)"
        Write-Host "  Project:     $($result.projectPath)"
        Write-Host "  Branch:      $($result.gitContext.Branch)"
        Write-Host "  Multi-Agent: $MultiAgent"
        Write-Host "  Prompt:      $ctxFile"
        Write-Host ""

        Write-Host "=== FULL CYCLE PROMPT ($($result.cycle)) ===" -ForegroundColor Cyan
        Write-Host ""
        Write-Host $result.prompt
        Write-Host ""
        Write-Host "=== END PROMPT ===" -ForegroundColor Cyan

        $envFile = Join-Path $EngineRoot "last-cycle.env"
        $envContent = "CYCLE=$($result.cycle)`nPROJECT=$($result.projectPath)`nMULTI_AGENT=$MultiAgent`nPROMPT_FILE=$ctxFile`nTIMESTAMP=$(Get-Date -Format 'o')`n"
        Write-TextFile $envFile $envContent
    }

    "push" {
        $null = Invoke-EnginePush -ProjectRoot $fullProjectPath -EngineRoot $EngineRoot -ForceApprove:$Approve -Amend:$Amend
    }

    "validate-state" {
        $findings = Read-JsonFile $FindingsFile
        $conv = Read-JsonFile $ConvergenceFile
        $state = Read-JsonFile $CycleFile
        $config = Read-JsonFile $ConfigFile

        $proposedFindings = Read-JsonFile $ProposedFindingsFile
        $proposedConv = Read-JsonFile $ProposedConvergenceFile
        $proposedCycle = Read-JsonFile $ProposedCycleFile

        $hasProposed = ($null -ne $proposedFindings -or $null -ne $proposedConv -or $null -ne $proposedCycle)

        Write-Host "`n=== STATE MACHINE INTEGRITY VALIDATION ===" -ForegroundColor Cyan

        if ($hasProposed) {
            Write-Host "`n-- Proposed State Validation (pre-promote) --" -ForegroundColor Yellow

            if ($proposedFindings -and $proposedFindings.findings) {
                $findingViolations = Validate-FindingStateIntegrity -ProposedFindings $proposedFindings.findings -ExistingFindings $findings
                Write-Host "Proposed finding violations: $($findingViolations.Count)" -ForegroundColor $(if ($findingViolations.Count -eq 0) { "Green" } else { "Red" })
                foreach ($v in $findingViolations) { Write-Host "  $v" -ForegroundColor Red }
            }

            if ($proposedConv) {
                $gateViolations = Validate-GateEvidenceIntegrity -ProposedConvergence $proposedConv -ExistingConvergence $conv
                Write-Host "Proposed gate violations: $($gateViolations.Count)" -ForegroundColor $(if ($gateViolations.Count -eq 0) { "Green" } else { "Red" })
                foreach ($v in $gateViolations) { Write-Host "  $v" -ForegroundColor Red }

                if ($proposedConv.classification) {
                    $oldClass = if ($conv -and $conv.classification) { [string]$conv.classification } else { "" }
                    $newClass = [string]$proposedConv.classification
                    $classOk = Test-ValidClassificationTransition -FromClassification $oldClass -ToClassification $newClass
                    Write-Host "Proposed classification: $newClass ($oldClass -> $newClass) - $(if ($classOk) { 'VALID' } else { 'INVALID' })" -ForegroundColor $(if ($classOk) { "Green" } else { "Red" })
                }
            }

            $toolingEvidence = Read-JsonFile $ToolingEvidenceFile
            if ($proposedFindings -and $proposedFindings.findings) {
                $newVerified = @($proposedFindings.findings | Where-Object { $_.status -eq "VERIFIED" })
                if ($newVerified.Count -gt 0) {
                    if (-not $toolingEvidence) {
                        Write-Host "TOOLING EVIDENCE: MISSING - $($newVerified.Count) findings proposed VERIFIED but no tooling-evidence.json" -ForegroundColor Red
                    } else {
                        Write-Host "TOOLING EVIDENCE: PRESENT - $($newVerified.Count) findings proposed VERIFIED" -ForegroundColor Green
                    }
                }
            }

            Write-Host ""
        }

        Write-Host "-- Current State Validation --" -ForegroundColor Yellow

        $existingConv = $conv
        $result = Validate-GateEvidenceIntegrity -ProposedConvergence $conv -ExistingConvergence $existingConv
        Write-Host "Gate evidence violations: $($result.Count)" -ForegroundColor $(if ($result.Count -eq 0) { "Green" } else { "Red" })
        foreach ($v in $result) { Write-Host "  $v" -ForegroundColor Yellow }

        $findingViolations = Validate-FindingStateIntegrity -ProposedFindings $findings.findings -ExistingFindings $findings
        Write-Host "Finding transition violations: $($findingViolations.Count)" -ForegroundColor $(if ($findingViolations.Count -eq 0) { "Green" } else { "Red" })
        foreach ($v in $findingViolations) { Write-Host "  $v" -ForegroundColor Yellow }

        $gitCtx = Get-GitContext -ProjectPath $fullProjectPath
        $scopeWarnings = Test-AuditScopeIntegrity -ProjectPath $fullProjectPath -ClaimedAuditedFileCount $gitCtx.FileCount
        Write-Host "Scope warnings: $($scopeWarnings.Count)" -ForegroundColor $(if ($scopeWarnings.Count -eq 0) { "Green" } else { "Yellow" })
        foreach ($w in $scopeWarnings) { Write-Host "  $w" -ForegroundColor Yellow }

        $oldClass = if ($conv.classification) { [string]$conv.classification } else { "" }
        $newClass = [string]$conv.classification
        $classOk = Test-ValidClassificationTransition -FromClassification $oldClass -ToClassification $newClass
        Write-Host "Classification valid: $classOk ($oldClass)" -ForegroundColor $(if ($classOk) { "Green" } else { "Red" })

        if ($findings.findings) {
            $openCount = @($findings.findings | Where-Object { $_.status -in @("OPEN","IN_PROGRESS") }).Count
            $verifiedCount = @($findings.findings | Where-Object { $_.status -eq "VERIFIED" }).Count
            Write-Host "Findings: $openCount open, $verifiedCount verified"
        }

        $totalBlocked = $result.Count + $findingViolations.Count
        $totalWarnings = $scopeWarnings.Count
        if ($totalBlocked -eq 0 -and -not $classOk) { $totalBlocked++ }

        Write-Host ""
        if ($totalBlocked -eq 0) {
            Write-Host "STATE INTEGRITY: PASS" -ForegroundColor Green
        } elseif ($totalBlocked -le 3) {
            Write-Host "STATE INTEGRITY: WARN ($totalBlocked violation(s))" -ForegroundColor Yellow
        } else {
            Write-Host "STATE INTEGRITY: FAIL ($totalBlocked violation(s))" -ForegroundColor Red
        }
    }

    "run-tooling" {
        $config = Read-JsonFile $ConfigFile
        $tooling = Get-ProjectTooling -ProjectPath $fullProjectPath
        $commands = Get-ToolingCommands -ProjectPath $fullProjectPath

        if ($commands.Count -eq 0) {
            Write-Host "[TOOLING] No test/lint/build commands detected for this project." -ForegroundColor Yellow
            Write-Host "  Detected manifests: $($tooling.files -join ', ')"

            $toolingEvidence = @{
                timestamp = (Get-Date).ToString("o")
                command_count = 0
                all_passed = $true
                results = @{}
                note = "No test/lint/build commands detected in project manifests"
            }
            Write-JsonFile $ToolingEvidenceFile $toolingEvidence
            Write-Host "[TOOLING] Evidence saved to $ToolingEvidenceFile (no commands available)" -ForegroundColor Green
        } else {
            Write-Host "`n=== EXECUTING PROJECT TOOLING ===" -ForegroundColor Cyan
            Write-Host "Commands: $($commands -join ', ')"
            $results = Invoke-ProjectTooling -ProjectPath $fullProjectPath -Commands $commands
            $report = Format-ToolingReport -Results $results
            Write-Host $report
            $toolingFile = Join-Path $EngineRoot "tooling-output.txt"
            Write-TextFile $toolingFile $report
            Write-Host "[TOOLING] Report saved to $toolingFile" -ForegroundColor Green

            $toolingEvidence = @{
                timestamp = (Get-Date).ToString("o")
                command_count = $commands.Count
                all_passed = ($results.Values | Where-Object { -not $_.success }).Count -eq 0
                results = $results
            }
            Write-JsonFile $ToolingEvidenceFile $toolingEvidence
            Write-Host "[TOOLING] Evidence saved to $ToolingEvidenceFile" -ForegroundColor Green

            $state = Read-JsonFile $CycleFile
            $currentCycle = if ($state -and $state.current_cycle) { Safe-Int $state.current_cycle } else { 0 }
            $gitCtx = Get-GitContext -ProjectPath $fullProjectPath
            $commitHash = if ($gitCtx.LastCommitHash) { $gitCtx.LastCommitHash } else { "unknown" }

            Initialize-EvidenceEngine -EngineRoot $EngineRoot
            $evidenceRegistryPath = $Script:EvidenceRegistryFile

            $evidenceArtifacts = New-EvidenceFromToolingResults `
                -ToolingResults $results `
                -Cycle $currentCycle `
                -CommitHash $commitHash `
                -WorkspaceId $fullProjectPath

            $registeredCount = 0
            $rejectedCount = 0
            foreach ($artifact in $evidenceArtifacts) {
                if (Register-Evidence -EvidenceArtifact $artifact -RegistryPath $evidenceRegistryPath) {
                    $registeredCount++
                } else {
                    $rejectedCount++
                }
            }
            if ($registeredCount -gt 0) {
                Write-Host "[EVIDENCE] $registeredCount evidence artifact(s) registered (replay-ready)" -ForegroundColor Green
            }
            if ($rejectedCount -gt 0) {
                Write-Host "[EVIDENCE] $rejectedCount evidence artifact(s) rejected (REPLAY DETECTED)" -ForegroundColor Red
            }
        }
    }

    "scope-check" {
        $gitCtx = Get-GitContext -ProjectPath $fullProjectPath
        Write-Host "`n=== AUDIT SCOPE ANALYSIS ===" -ForegroundColor Cyan
        Write-Host "Total tracked files: $($gitCtx.FileCount)"

        if ($gitCtx.FileCount -le 100) {
            Write-Host "Risk: LOW - Full audit practical in single context" -ForegroundColor Green
        } elseif ($gitCtx.FileCount -le 500) {
            Write-Host "Risk: MEDIUM - Full audit may approach context limits" -ForegroundColor Yellow
        } elseif ($gitCtx.FileCount -le 2000) {
            Write-Host "Risk: HIGH - Full audit impossible in single context. Chunking required." -ForegroundColor Yellow
            Write-Host "  Recommended: dependency-graph-aware incremental auditing" -ForegroundColor Yellow
        } else {
            Write-Host "Risk: CRITICAL - Repository too large for full context audit. Chunked+prioritized auditing mandatory." -ForegroundColor Red
        }

        $scopeWarnings = Test-AuditScopeIntegrity -ProjectPath $fullProjectPath -ClaimedAuditedFileCount $gitCtx.FileCount
        foreach ($w in $scopeWarnings) { Write-Host $w -ForegroundColor Yellow }
    }

    "promote-state" {
        Write-Host "`n=== STATE PROMOTION (LLM → Validated → Committed) ===" -ForegroundColor Cyan

        $proposedFindings = Read-JsonFile $ProposedFindingsFile
        $proposedConv = Read-JsonFile $ProposedConvergenceFile
        $proposedCycle = Read-JsonFile $ProposedCycleFile

        if (-not $proposedFindings -and -not $proposedConv -and -not $proposedCycle) {
            Write-Host "[REJECTED] No proposed state files found. Expected:" -ForegroundColor Red
            Write-Host "  $ProposedFindingsFile"
            Write-Host "  $ProposedConvergenceFile"
            Write-Host "  $ProposedCycleFile"
            Write-Host "  The LLM agent must write proposed-*.json files, then promote-state validates and commits."
            return
        }

        $existingFindings = Read-JsonFile $FindingsFile
        $existingConv = Read-JsonFile $ConvergenceFile
        $existingCycle = Read-JsonFile $CycleFile

        $allViolations = @()
        $allWarnings = @()

        Write-Host ""
        Write-Host "[1/4] Validating finding state transitions..." -ForegroundColor Yellow
        if ($proposedFindings -and $proposedFindings.findings) {
            $findingViolations = Validate-FindingStateIntegrity -ProposedFindings $proposedFindings.findings -ExistingFindings $existingFindings
            foreach ($v in $findingViolations) {
                $allViolations += "FINDING: $v"
                Write-Host "  [VIOLATION] $v" -ForegroundColor Red
            }
            if ($findingViolations.Count -eq 0) {
                Write-Host "  [PASS] All finding transitions valid" -ForegroundColor Green
            }
        } else {
            Write-Host "  [SKIP] No proposed findings" -ForegroundColor Yellow
        }

        Write-Host ""
        Write-Host "[2/4] Validating convergence gate evidence..." -ForegroundColor Yellow
        if ($proposedConv) {
            $gateViolations = Validate-GateEvidenceIntegrity -ProposedConvergence $proposedConv -ExistingConvergence $existingConv
            foreach ($v in $gateViolations) {
                $allViolations += "GATE: $v"
                Write-Host "  [VIOLATION] $v" -ForegroundColor Red
            }
            if ($gateViolations.Count -eq 0) {
                Write-Host "  [PASS] All convergence gate changes valid" -ForegroundColor Green
            }

            if ($proposedConv.classification) {
                $oldClass = if ($existingConv -and $existingConv.classification) { [string]$existingConv.classification } else { "" }
                $newClass = [string]$proposedConv.classification
                if (-not (Test-ValidClassificationTransition -FromClassification $oldClass -ToClassification $newClass)) {
                    $allViolations += "CLASSIFICATION: $oldClass -> $newClass is not allowed"
                    Write-Host "  [VIOLATION] Classification: $oldClass -> $newClass not allowed" -ForegroundColor Red
                } else {
                    Write-Host "  [PASS] Classification: $oldClass -> $newClass valid" -ForegroundColor Green
                }
            }
        } else {
            Write-Host "  [SKIP] No proposed convergence" -ForegroundColor Yellow
        }

        Write-Host ""
        Write-Host "[2b/4] Cross-validating gate values against findings..." -ForegroundColor Yellow
        if ($proposedConv -and $proposedConv.gates -and $proposedFindings -and $proposedFindings.findings) {
            $gateFindingMap = @{
                "P0_zero" = @{ severities = @("P0"); label = "P0" }
                "P1_zero" = @{ severities = @("P1"); label = "P1" }
                "P2_zero" = @{ severities = @("P2"); label = "P2" }
                "critical_security" = @{ severities = @("P0","P1","P2"); categories = @("SECURITY"); label = "critical security (P0-P2)" }
                "critical_correctness" = @{ severities = @("P0","P1","P2"); categories = @("CORRECTNESS"); label = "critical correctness (P0-P2)" }
                "data_integrity" = @{ severities = @("P0","P1","P2"); categories = @("DATA_INTEGRITY"); label = "data integrity (P0-P2)" }
            }

            foreach ($gateName in $gateFindingMap.Keys) {
                try {
                    $gateValue = [bool]$proposedConv.gates.$gateName
                } catch { continue }

                if ($gateValue) {
                    $spec = $gateFindingMap[$gateName]
                    $openViolators = @($proposedFindings.findings | Where-Object {
                        ($_.severity -in $spec.severities) -and
                        ($_.status -in @("OPEN","IN_PROGRESS","FIXED","VERIFYING","DEFERRED","BLOCKED")) -and
                        (-not $spec.categories -or ($_.category -in $spec.categories))
                    })

                    # Only flag as violation if findings are truly open (not VERIFIED)
                    $trulyOpen = @($openViolators | Where-Object { $_.status -ne "DEFERRED" })
                    if ($trulyOpen.Count -gt 0) {
                        $ids = ($trulyOpen | ForEach-Object { "$($_.id)($($_.status))" }) -join ", "
                        $allViolations += "GATE-FINDINGS MISMATCH: $gateName is TRUE but $($trulyOpen.Count) open $($spec.label) finding(s) exist: $ids"
                        Write-Host "  [VIOLATION] Gate '$gateName' is TRUE but open findings exist:" -ForegroundColor Red
                        foreach ($f in $trulyOpen) {
                            Write-Host "    $($f.id) | $($f.severity) | $($f.status) | $($f.category) | $($f.problem)" -ForegroundColor Red
                        }
                    } else {
                        Write-Host "  [PASS] Gate '$gateName' consistent with findings" -ForegroundColor Green
                    }
                } else {
                    Write-Host "  [INFO] Gate '$gateName' is FALSE - no cross-check needed" -ForegroundColor Cyan
                }
            }

            if ($proposedConv -and $proposedConv.gates) {
                try { $noMaterial = [bool]$proposedConv.gates.no_material_new_findings } catch { $noMaterial = $false }
                if ($noMaterial) {
                    # Check if this cycle actually produced new P0-P3 findings
                    $existingIds = @{}
                    if ($existingFindings -and $existingFindings.findings) {
                        foreach ($ef in $existingFindings.findings) { if ($ef.id) { $existingIds[$ef.id] = $true } }
                    }
                    $newMaterial = @($proposedFindings.findings | Where-Object {
                        $_.id -and (-not $existingIds.ContainsKey($_.id)) -and ($_.severity -in @("P0","P1","P2","P3"))
                    })
                    if ($newMaterial.Count -gt 0) {
                        $ids = ($newMaterial | ForEach-Object { "$($_.id)($($_.severity))" }) -join ", "
                        $allViolations += "GATE-FINDINGS MISMATCH: no_material_new_findings is TRUE but $($newMaterial.Count) new P0-P3 finding(s) created this cycle: $ids"
                        Write-Host "  [VIOLATION] Gate 'no_material_new_findings' is TRUE but new findings found:" -ForegroundColor Red
                        foreach ($f in $newMaterial) {
                            Write-Host "    $($f.id) | $($f.severity) | $($f.problem)" -ForegroundColor Red
                        }
                    } else {
                        Write-Host "  [PASS] Gate 'no_material_new_findings' consistent - no new P0-P3 findings" -ForegroundColor Green
                    }
                }
            }
        } else {
            Write-Host "  [SKIP] Missing proposed convergence or findings for cross-check" -ForegroundColor Yellow
        }

        Write-Host ""
        Write-Host "[3/4] Validating tooling evidence..." -ForegroundColor Yellow
        $toolingEvidence = Read-JsonFile $ToolingEvidenceFile
        if ($proposedFindings -and $proposedFindings.findings) {
            $newlyVerified = @($proposedFindings.findings | Where-Object { $_.status -eq "VERIFIED" })
            if ($newlyVerified.Count -gt 0) {
                if (-not $toolingEvidence) {
                    $allViolations += "TOOLING: $($newlyVerified.Count) findings proposed VERIFIED but tooling-evidence.json is missing"
                    Write-Host "  [VIOLATION] $($newlyVerified.Count) findings proposed VERIFIED but no tooling evidence" -ForegroundColor Red
                } else {
                    $allPassed = $true
                    if ($toolingEvidence.results) {
                        foreach ($key in $toolingEvidence.results.Keys) {
                            $r = $toolingEvidence.results[$key]
                            if (-not $r.success) {
                                $allPassed = $false
                                Write-Host "  [WARN] Tool '$key' FAILED (exit code $($r.exit_code))" -ForegroundColor Yellow
                            }
                        }
                    }
                    if ($allPassed) {
                        Write-Host "  [PASS] Tooling evidence present and all commands passed" -ForegroundColor Green
                    } else {
                        $allWarnings += "Some tooling commands failed. Verify findings carefully."
                        Write-Host "  [WARN] Some tooling commands failed" -ForegroundColor Yellow
                    }
                }
            } else {
                Write-Host "  [INFO] No new VERIFIED findings this cycle; tooling evidence optional" -ForegroundColor Cyan
            }
        } else {
            Write-Host "  [SKIP] No proposed findings" -ForegroundColor Yellow
        }

        Write-Host ""
        Write-Host "[4/4] Validating audit scope..." -ForegroundColor Yellow
        $auditedCount = 0
        if ($proposedCycle -and $proposedCycle.audited_file_count) {
            $auditedCount = Safe-Int $proposedCycle.audited_file_count 0
        }
        $scopeWarnings = Test-AuditScopeIntegrity -ProjectPath $fullProjectPath -ClaimedAuditedFileCount $auditedCount
        foreach ($w in $scopeWarnings) {
            $allWarnings += $w
            Write-Host "  [WARN] $w" -ForegroundColor Yellow
        }
        if ($scopeWarnings.Count -eq 0) {
            Write-Host "  [INFO] Scope assessment: $auditedCount files audited" -ForegroundColor Cyan
        }

        Write-Host ""
        Write-Host "[5/6] Validating module dependency integrity..." -ForegroundColor Yellow
        Write-Host "  Required failures: $($Script:modRequiredFailures.Count)" -ForegroundColor $(if ($Script:modRequiredFailures.Count -eq 0) { "Green" } else { "Red" })
        Write-Host "  Optional failures: $($Script:modOptionalFailures.Count)" -ForegroundColor $(if ($Script:modOptionalFailures.Count -eq 0) { "Green" } else { "DarkYellow" })
        Write-Host "  Experimental failures: $($Script:modExperimentalFailures.Count)" -ForegroundColor DarkGray
        Write-Host "  Module integrity pass: $Script:moduleIntegrityPass" -ForegroundColor $(if ($Script:moduleIntegrityPass) { "Green" } else { "Red" })

        if (-not $Script:moduleIntegrityPass) {
            Write-Host "  [ENFORCE] Overriding module_dependency_integrity gate to FALSE (orchestrator authority)" -ForegroundColor Red
            if ($proposedConv) {
                if (-not ($proposedConv -is [PSCustomObject])) {
                    $proposedConv = [PSCustomObject]@{}
                }
                if (-not (Get-Member -InputObject $proposedConv -Name "gates" -MemberType NoteProperty -ErrorAction SilentlyContinue)) {
                    $proposedConv | Add-Member -NotePropertyName "gates" -NotePropertyValue @{} -Force
                }
                $proposedConv.gates | Add-Member -NotePropertyName "module_dependency_integrity" -NotePropertyValue $false -Force
            }
            $allViolations += "MODULE_INTEGRITY: Required modules failed to load. Convergence blocked."
            Write-Host "  [VIOLATION] Required modules failed to load. module_dependency_integrity gate forced to FALSE." -ForegroundColor Red
            foreach ($rf in $Script:modRequiredFailures) {
                Write-Host "    Missing: $rf" -ForegroundColor Red
            }
        } else {
            Write-Host "  [PASS] All required modules loaded. module_dependency_integrity gate can be evaluated by evidence." -ForegroundColor Green
        }

        if (-not $Script:moduleIntegrityPass -and $proposedConv -and $proposedConv.converged) {
            Write-Host "  [ENFORCE] Overriding converged flag to FALSE (module integrity failure prevents convergence)" -ForegroundColor Red
            $proposedConv | Add-Member -NotePropertyName "converged" -NotePropertyValue $false -Force
            $allViolations += "CONVERGENCE BLOCKED: Cannot converge with required module failures."
        }

        if (-not $Script:moduleIntegrityPass -and $proposedConv -and $proposedConv.classification -eq "PRODUCTION_READY") {
            Write-Host "  [ENFORCE] Overriding classification from PRODUCTION_READY to NOT_READY (module failures)" -ForegroundColor Red
            $proposedConv | Add-Member -NotePropertyName "classification" -NotePropertyValue "NOT_READY" -Force
            $proposedConv | Add-Member -NotePropertyName "reason" -NotePropertyValue "$($proposedConv.reason)`n[ORCHESTRATOR OVERRIDE] Classification downgraded: $($Script:modRequiredFailures.Count) required module(s) missing. Convergence claims not trustworthy." -Force
            $allViolations += "CLASSIFICATION OVERRIDE: PRODUCTION_READY → NOT_READY due to required module failures."
        }

        if ($Script:modRequiredFailures.Count -gt 0) {
            Write-Host ""
            Write-Host "[6/6] Module integrity detail:" -ForegroundColor Yellow
            Write-Host "  Required modules not available:" -ForegroundColor Red
            foreach ($rf in $Script:modRequiredFailures) {
                Write-Host "    - $rf" -ForegroundColor Red
            }
            Write-Host ""
            Write-Host "  To fix: Create these module files in src/modules/ with their expected function exports."
            Write-Host "  Required modules after classification:"
            $cfg = Read-JsonFile $ConfigFile
            if ($cfg -and $cfg.modules -and $cfg.modules.required) {
                foreach ($m in $cfg.modules.required) {
                    $exists = Test-Path -LiteralPath (Join-Path $ModulesDirResolved $m)
                    $color = if ($exists) { "Green" } else { "Red" }
                    Write-Host "    $(if ($exists) { '[OK]' } else { '[MISSING]' }) $m" -ForegroundColor $color
                }
            }
        }

        Write-Host ""
        if ($allViolations.Count -gt 0) {
            Write-Host "=== PROMOTION REJECTED ===" -ForegroundColor Red
            Write-Host "$($allViolations.Count) violation(s) found:" -ForegroundColor Red
            foreach ($v in $allViolations) {
                Write-Host "  $v" -ForegroundColor Red
            }
            Write-Host ""
            Write-Host "Fix violations and re-run promote-state. Proposed files preserved at:" -ForegroundColor Yellow
            Write-Host "  $ProposedFindingsFile"
            Write-Host "  $ProposedConvergenceFile"
            Write-Host "  $ProposedCycleFile"
            Write-Host "  Use -ForceValidation to bypass (UNSAFE)." -ForegroundColor Yellow
            if ($ForceValidation) {
                Write-Host ""
                Write-Host "[FORCE] -ForceValidation active. Bypassing violations and promoting anyway." -ForegroundColor DarkYellow
            }
        } else {
            Write-Host "=== PROMOTION ACCEPTED ===" -ForegroundColor Green
            Write-Host "All validations passed. Committing proposed state..." -ForegroundColor Green

            if ($allWarnings.Count -gt 0) {
                Write-Host ""
                Write-Host "Warnings (non-blocking):" -ForegroundColor Yellow
                foreach ($w in $allWarnings) {
                    Write-Host "  $w" -ForegroundColor Yellow
                }
            }

            $promotedFiles = @()

            if ($proposedFindings) {
                Write-JsonFile $FindingsFile $proposedFindings
                $promotedFiles += "findings.json"
                Write-Host "  [COMMITTED] $FindingsFile" -ForegroundColor Green
            }
            if ($proposedConv) {
                Write-JsonFile $ConvergenceFile $proposedConv
                $promotedFiles += "convergence.json"
                Write-Host "  [COMMITTED] $ConvergenceFile" -ForegroundColor Green
            }
            if ($proposedCycle) {
                Write-JsonFile $CycleFile $proposedCycle
                $promotedFiles += "cycle.json"
                Write-Host "  [COMMITTED] $CycleFile" -ForegroundColor Green
            }

            Write-Host ""
            Write-Host "[SUCCESS] State promoted: $($promotedFiles -join ', ')" -ForegroundColor Green
            if ($allWarnings.Count -gt 0) {
                Write-Host "[WARN] Promotion accepted with warnings. Review warnings above." -ForegroundColor Yellow
            }

            $newMaterialFindingsCount = 0
            if ($proposedFindings -and $proposedFindings.findings -and $existingFindings -and $existingFindings.findings) {
                $existingIds = @{}
                foreach ($ef in $existingFindings.findings) { if ($ef.id) { $existingIds[$ef.id] = $true } }
                $newMaterialFindingsCount = @($proposedFindings.findings | Where-Object {
                    $_.id -and (-not $existingIds.ContainsKey($_.id)) -and ($_.severity -in @("P0","P1","P2","P3"))
                }).Count
            }

            $promotedCycle = Read-JsonFile $CycleFile
            if ($promotedCycle) {
                if ($newMaterialFindingsCount -gt 0) {
                    $promotedCycle | Add-Member -NotePropertyName "cycles_without_progress" -NotePropertyValue 0 -Force
                    Write-Host "  [PROGRESS] $newMaterialFindingsCount new P0-P3 material finding(s) this cycle. cycles_without_progress reset to 0." -ForegroundColor Cyan
                } else {
                    $prevWithout = Safe-Int $existingCycle.cycles_without_progress 0
                    $newWithout = $prevWithout + 1
                    $promotedCycle | Add-Member -NotePropertyName "cycles_without_progress" -NotePropertyValue $newWithout -Force
                    Write-Host "  [STALL] No new P0-P3 material findings. cycles_without_progress: $prevWithout -> $newWithout" -ForegroundColor Yellow
                    if ($newWithout -ge 3) {
                        $configCheck = Read-JsonFile $ConfigFile
                        $maxNoProg = if ($configCheck -and $configCheck.engine) { Safe-Int $configCheck.engine.max_cycles_without_progress 3 } else { 3 }
                        if ($newWithout -ge $maxNoProg) {
                            Write-Host "  [HALT] Stalling: $newWithout cycles without progress. Next -Action run will halt." -ForegroundColor Red
                            $promotedCycle | Add-Member -NotePropertyName "status" -NotePropertyValue "STALLED" -Force
                        }
                    }
                }
                Write-JsonFile $CycleFile $promotedCycle
            }

            $ts = Get-Date -Format "yyyyMMdd_HHmmss"
            $archivedFindings = Join-Path $EngineRoot "archive\proposed-findings-${ts}.json"
            $archivedConv = Join-Path $EngineRoot "archive\proposed-convergence-${ts}.json"
            $archivedCycle = Join-Path $EngineRoot "archive\proposed-cycle-${ts}.json"

            New-Item -ItemType Directory -Force -Path (Join-Path $EngineRoot "archive") | Out-Null
            if (Test-Path -LiteralPath $ProposedFindingsFile) {
                Copy-Item -LiteralPath $ProposedFindingsFile -Destination $archivedFindings -Force
                Remove-Item -LiteralPath $ProposedFindingsFile -Force
            }
            if (Test-Path -LiteralPath $ProposedConvergenceFile) {
                Copy-Item -LiteralPath $ProposedConvergenceFile -Destination $archivedConv -Force
                Remove-Item -LiteralPath $ProposedConvergenceFile -Force
            }
            if (Test-Path -LiteralPath $ProposedCycleFile) {
                Copy-Item -LiteralPath $ProposedCycleFile -Destination $archivedCycle -Force
                Remove-Item -LiteralPath $ProposedCycleFile -Force
            }
            Write-Host "[ARCHIVE] Proposed state archived for audit trail" -ForegroundColor Cyan
        }
    }

    "invariant-check" {
        Write-Host "`n=== BUSINESS INVARIANT VALIDATION ===" -ForegroundColor Cyan
        $invariantDefPath = Join-Path $EngineRoot "state\invariant-definitions.json"
        Initialize-InvariantEngine -InvariantDefPath $invariantDefPath
        $checkResult = Invoke-InvariantCheck -EngineRoot $EngineRoot -InvariantDefPath $invariantDefPath
        $report = Format-InvariantReport -CheckResult $checkResult
        Write-Host $report
        $invariantReportFile = Join-Path $ReportsDir "invariant-report.md"
        Write-TextFile $invariantReportFile $report
        Write-Host "[INVARIANT] Report saved to $invariantReportFile" -ForegroundColor Green
    }

    "index-repo" {
        Write-Host "`n=== REPOSITORY INDEXING ===" -ForegroundColor Cyan
        $graphPath = Join-Path $EngineRoot "state\repo-graph.json"
        Initialize-RepoGraph -EngineRoot $EngineRoot -RepositoryRoot $fullProjectPath
        $graphData = Full-IndexRepository -RepoRoot $fullProjectPath -GraphPath $graphPath
        $summary = Get-GraphSummary -RepoGraph $graphData
        Write-Host $summary
        $graphReportFile = Join-Path $ReportsDir "repo-graph-report.md"
        Write-TextFile $graphReportFile $summary
        Write-Host "[INDEX] Graph saved to $graphPath" -ForegroundColor Green
    }

    "evidence-check" {
        Write-Host "`n=== EVIDENCE INTEGRITY CHECK ===" -ForegroundColor Cyan
        Initialize-EvidenceEngine -EngineRoot $EngineRoot
        $registry = Read-EvidenceRegistry -RegistryPath $Script:EvidenceRegistryFile

        if (-not $registry -or -not $registry.entries -or ($registry.entries.PSObject.Properties | Measure-Object).Count -eq 0) {
            Write-Host "No evidence registered yet." -ForegroundColor Yellow
        } else {
            $entryCount = ($registry.entries.PSObject.Properties | Measure-Object).Count
            $replayCount = if ($registry.replay_attempts) { $registry.replay_attempts.Count } else { 0 }
            Write-Host "Registered evidence hashes: $entryCount"
            Write-Host "Replay attempts detected: $replayCount"
            if ($replayCount -gt 0) {
                Write-Host "  [WARNING] Evidence replay attempts detected!" -ForegroundColor Red
                foreach ($replay in $registry.replay_attempts) {
                    Write-Host "    Hash: $($replay.hash) | Original cycle: $($replay.original_cycle) | Attempted cycle: $($replay.attempt_cycle)" -ForegroundColor Yellow
                }
            } else {
                Write-Host "  [OK] No evidence replay detected." -ForegroundColor Green
            }
        }
    }

    "adversarial-campaign" {
        Write-Host "`n=== ADVERSARIAL STATE ATTACK CAMPAIGN ===" -ForegroundColor Cyan
        $campaignOutput = Join-Path $ReportsDir "adversarial-results.json"
        $results = Invoke-AdversarialCampaign -EngineRoot $EngineRoot -ProjectPath $fullProjectPath -CampaignOutput $campaignOutput
        Write-Host "[CAMPAIGN] Results saved to $campaignOutput" -ForegroundColor Green
    }

    "scale-benchmark" {
        Write-Host "`n=== SCALE BENCHMARK ===" -ForegroundColor Cyan
        $benchRoot = Join-Path $fullProjectPath ".benchmarks"
        $benchmarks = Invoke-ScaleBenchmark -BenchmarkRoot $benchRoot -EngineRoot $EngineRoot -Sizes @(25, 100, 500)
        $benchOutput = Join-Path $ReportsDir "scale-benchmark-results.json"
        $json = $benchmarks | ConvertTo-Json -Depth 100
        $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
        [System.IO.File]::WriteAllText($benchOutput, $json, $utf8NoBom)
        Write-Host "[BENCH] Results saved to $benchOutput" -ForegroundColor Green
    }

    "sandbox-test" {
        Write-Host "`n=== SANDBOX SELF-TEST ===" -ForegroundColor Cyan
        $testRoot = Join-Path $fullProjectPath ".sandbox-tests"
        $results = Invoke-SandboxSelfTest -TestRoot $testRoot
        $sandboxOutput = Join-Path $ReportsDir "sandbox-test-results.json"
        $json = $results | ConvertTo-Json -Depth 100
        $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
        [System.IO.File]::WriteAllText($sandboxOutput, $json, $utf8NoBom)
    }

    "security-scan" {
        Write-Host "`n=== SECURITY SCAN ===" -ForegroundColor Cyan
        $scanOutput = Join-Path $ReportsDir "security-scan-results.json"
        $result = Invoke-SecurityScan -ProjectPath $fullProjectPath -OutputPath $scanOutput
        $report = Format-SecurityReport -ScanResult $result
        Write-Host $report
        $scanReportFile = Join-Path $ReportsDir "security-scan-report.md"
        Write-TextFile $scanReportFile $report
        Write-Host "[SECURITY] Results saved to $scanOutput" -ForegroundColor Green
    }

    "git-safety" {
        $result = Test-GitSafety -ProjectRoot $fullProjectPath -EngineRoot $EngineRoot
    }

    "verify-findings" {
        Write-Host "`n=== INDEPENDENT FINDINGS VERIFICATION ===" -ForegroundColor Cyan
        $existingFindings = Read-JsonFile $FindingsFile
        if (-not $existingFindings -or -not $existingFindings.findings) {
            Write-Host "No findings to verify." -ForegroundColor Yellow
        } else {
            Initialize-InvariantEngine -InvariantDefPath (Join-Path $EngineRoot "state/invariant-definitions.json")
            $verifier = New-IndependentVerifier -EngineRoot $EngineRoot -ProjectPath $fullProjectPath
            $bulkResult = Invoke-BulkVerify -Verifier $verifier -Findings $existingFindings.findings
            Write-Host "Total: $($bulkResult.total)"
            Write-Host "Verified: $($bulkResult.verified)"
            Write-Host "Rejected: $($bulkResult.rejected)"
            Write-Host "Unverified: $($bulkResult.unverified)"

            if ($bulkResult.rejected -gt 0) {
                Write-Host ""
                Write-Host "REJECTED FINDINGS:" -ForegroundColor Red
                foreach ($v in $bulkResult.verdicts) {
                    if ($v.verdict -eq "REJECTED") {
                        Write-Host "  $($v.finding_id):"
                        foreach ($c in $v.checks) {
                            if (-not $c.passed) { Write-Host "    - $($c.name): $($c.detail)" -ForegroundColor Red }
                        }
                    }
                }
            }

            $verifyOutput = Join-Path $ReportsDir "verification-results.json"
            $json = $bulkResult | ConvertTo-Json -Depth 100
            $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
            [System.IO.File]::WriteAllText($verifyOutput, $json, $utf8NoBom)
            Write-Host "[VERIFY] Results saved to $verifyOutput" -ForegroundColor Green
        }
    }

    "score-report" {
        Write-Host "`n=== DETERMINISTIC CAPABILITY SCORING ===" -ForegroundColor Cyan
        $scorePath = Join-Path $EngineRoot "state\capability-score.json"
        $result = New-CapabilityScore -EngineRoot $EngineRoot -OutputPath $scorePath
        $report = Format-ScoreReport -EngineRoot $EngineRoot -AsMarkdownTable
        Write-Host $report
        $scoreReportFile = Join-Path $ReportsDir "capability-score-report.md"
        Write-TextFile $scoreReportFile $report
        Write-Host "[SCORE] Overall: $($result.overall_score)%" -ForegroundColor $(if ($result.overall_score -ge 90) { "Green" } elseif ($result.overall_score -ge 70) { "Yellow" } else { "Red" })
        Write-Host "[SCORE] Report saved to $scoreReportFile" -ForegroundColor Green
    }

    "false-evidence-campaign" {
        Write-Host "`n=== FALSE EVIDENCE ATTACK CAMPAIGN ===" -ForegroundColor Cyan
        $campaignPath = Join-Path $ReportsDir "false-evidence-results.json"
        $result = Invoke-FalseEvidenceCampaign -EngineRoot $EngineRoot -ProjectPath $fullProjectPath -CampaignOutput $campaignPath
    }

    "false-convergence-campaign" {
        Write-Host "`n=== FALSE CONVERGENCE ATTACK CAMPAIGN ===" -ForegroundColor Cyan

        $requiredCmds = @("Validate-FindingStateIntegrity", "Validate-GateEvidenceIntegrity", "Test-ValidClassificationTransition")
        $missingCmds = @()
        foreach ($cmd in $requiredCmds) {
            if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
                $missingCmds += $cmd
            }
        }

        if ($missingCmds.Count -gt 0) {
            Write-Host "[AURA] MODULE_DEPENDENCY_FAILURE: Required validator commands not available: $($missingCmds -join ', ')" -ForegroundColor Red
            Write-Host "[AURA] CAMPAIGN_EXECUTION_ERROR: False-convergence campaign cannot execute. Engine root=$EngineRoot, ModulesDir=$ModulesDir" -ForegroundColor Red
            $errorResult = @{
                campaign = "FALSE_CONVERGENCE_EXTENDED"
                timestamp = (Get-Date).ToString("o")
                status = "CAMPAIGN_EXECUTION_ERROR"
                engine_root = $EngineRoot
                modules_dir = $ModulesDir
                required_commands = $requiredCmds
                available_commands = @()
                missing_commands = $missingCmds
                module_load_status = $modResult
                attacks = @()
                summary = @{
                    total_attacks = 0
                    attacks_detected = 0
                    attacks_breached = 0
                    execution_errors = 0
                    rejection_rate = 0
                    status = "CAMPAIGN_EXECUTION_ERROR"
                }
            }
            $campaignPath = Join-Path $ReportsDir "false-convergence-results.json"
            $parent = Split-Path -Parent $campaignPath
            if (-not (Test-Path -LiteralPath $parent)) { New-Item -ItemType Directory -Force -Path $parent | Out-Null }
            $json = $errorResult | ConvertTo-Json -Depth 100
            $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
            [System.IO.File]::WriteAllText($campaignPath, $json, $utf8NoBom)
            Write-Host "[AURA] Error result written to $campaignPath" -ForegroundColor Red
            return
        }

        Write-Host "[AURA] EngineRoot: $EngineRoot"
        Write-Host "[AURA] ModulesDir: $ModulesDir"
        Write-Host "[AURA] ReportsDir: $ReportsDir"
        foreach ($cmd in $requiredCmds) {
            $cmdInfo = Get-Command $cmd -ErrorAction SilentlyContinue
            Write-Host "[AURA] $cmd = AVAILABLE (source: $($cmdInfo.Source))"
        }

        $campaignPath = Join-Path $ReportsDir "false-convergence-results.json"
        $result = Invoke-FalseConvergenceCampaign -EngineRoot $EngineRoot -CampaignOutput $campaignPath
    }

    "git-safety-campaign" {
        Write-Host "`n=== GIT SAFETY ADVERSARIAL CAMPAIGN ===" -ForegroundColor Cyan
        $campaignPath = Join-Path $ReportsDir "git-safety-campaign-results.json"
        $result = Invoke-GitSafetyCampaign -ProjectRoot $fullProjectPath -EngineRoot $EngineRoot -CampaignOutput $campaignPath
    }

    "mutation-test" {
        Write-Host "`n=== MUTATION TESTING ===" -ForegroundColor Cyan
        $mutationPath = Join-Path $ReportsDir "mutation-test-results.json"
        $result = Invoke-MutationTests -EngineRoot $EngineRoot -ProjectPath $fullProjectPath -OutputPath $mutationPath
        $report = Format-MutationReport -MutationResult $result
        Write-Host $report
        $mutationReportFile = Join-Path $ReportsDir "mutation-test-report.md"
        Write-TextFile $mutationReportFile $report
    }

    "failure-recovery" {
        Write-Host "`n=== FAILURE RECOVERY TESTS ===" -ForegroundColor Cyan
        $recoveryPath = Join-Path $ReportsDir "failure-recovery-results.json"
        $result = Invoke-FailureRecoveryTests -EngineRoot $EngineRoot -ProjectPath $fullProjectPath -OutputPath $recoveryPath
    }
}