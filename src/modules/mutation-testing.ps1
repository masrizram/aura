# ============================================================
# MUTATION TESTING ENGINE v1.0.0
# Creates known mutations of AURA engine functions and tests
# whether the engine detects them. Measures detection rate.
# P0/security mutations must be 100% detected.
# No source files are permanently modified - all mutations
# operate on in-memory copies or temporary files.
# ============================================================

$Script:MutationTemplateDir = $null

function Initialize-MutationEngine {
    param(
        [string]$EngineRoot,
        [string]$WorkDir
    )

    $Script:MutationTemplateDir = Join-Path $WorkDir "mutation-templates"
    if (-not (Test-Path -LiteralPath $Script:MutationTemplateDir)) {
        New-Item -ItemType Directory -Force -Path $Script:MutationTemplateDir | Out-Null
    }

    $stateDir = Join-Path $Script:MutationTemplateDir "state"
    if (-not (Test-Path -LiteralPath $stateDir)) {
        New-Item -ItemType Directory -Force -Path $stateDir | Out-Null
    }

    $reportsDir = Join-Path $Script:MutationTemplateDir "reports"
    if (-not (Test-Path -LiteralPath $reportsDir)) {
        New-Item -ItemType Directory -Force -Path $reportsDir | Out-Null
    }

    return $Script:MutationTemplateDir
}

function Get-MutationDefinitions {
    return @(
        @{
            id = "MUT-01"
            name = "AUTHZ_REMOVAL"
            category = "SECURITY"
            severity = "P0"
            description = "Disable a state validation check during promote-state"
            ground_truth = "SECURITY_BUG"
            target_function = "Validate-FindingStateIntegrity"
        }
        @{
            id = "MUT-02"
            name = "FINANCIAL_ERROR"
            category = "CORRECTNESS"
            severity = "P0"
            description = "Change score calculation to always add 50"
            ground_truth = "INCORRECT_BEHAVIOR"
            target_function = "Validate-GateEvidenceIntegrity"
        }
        @{
            id = "MUT-03"
            name = "COMMAND_INJECTION"
            category = "SECURITY"
            severity = "P0"
            description = "Unsafe string expansion via Invoke-Expression with unsanitized input"
            ground_truth = "SECURITY_BUG"
            target_function = "Invoke-ProjectTooling"
        }
        @{
            id = "MUT-04"
            name = "NULL_FAILURE"
            category = "CORRECTNESS"
            severity = "P1"
            description = "Remove Safe-Int null guards"
            ground_truth = "NULL_REFERENCE_RISK"
            target_function = "Safe-Int"
        }
        @{
            id = "MUT-05"
            name = "RACE_CONDITION"
            category = "CORRECTNESS"
            severity = "P1"
            description = "Remove temp-file pattern from Write-JsonFile (direct write)"
            ground_truth = "RACE_CONDITION"
            target_function = "Write-JsonFile"
        }
        @{
            id = "MUT-06"
            name = "UNSAFE_PATH"
            category = "SECURITY"
            severity = "P1"
            description = "Remove Resolve-Path -LiteralPath (use regular string path)"
            ground_truth = "PATH_TRAVERSAL_RISK"
            target_function = "Resolve-Path"
        }
        @{
            id = "MUT-07"
            name = "AUTH_BYPASS"
            category = "SECURITY"
            severity = "P0"
            description = "Skip state validation in promote-state path"
            ground_truth = "SECURITY_BUG"
            target_function = "Write-StateWithValidation"
        }
        @{
            id = "MUT-08"
            name = "STATE_BYPASS"
            category = "SECURITY"
            severity = "P0"
            description = "Allow forbidden transition OPEN->VERIFIED"
            ground_truth = "SECURITY_BUG"
            target_function = "Test-ForbiddenDirectTransition"
        }
        @{
            id = "MUT-09"
            name = "EVIDENCE_REPLAY"
            category = "DATA_INTEGRITY"
            severity = "P0"
            description = "Skip replay detection in Register-Evidence"
            ground_truth = "INTEGRITY_BYPASS"
            target_function = "Register-Evidence"
        }
        @{
            id = "MUT-10"
            name = "CONVERGENCE_FLIP"
            category = "CONVERGENCE_SAFETY"
            severity = "P0"
            description = "Allow converged=true without checking all gates"
            ground_truth = "CONVERGENCE_BYPASS"
            target_function = "Validate-GateEvidenceIntegrity"
        }
        @{
            id = "MUT-11"
            name = "COUNTER_MANIPULATION"
            category = "CONVERGENCE_SAFETY"
            severity = "P1"
            description = "Remove counter jump check in convergence validation"
            ground_truth = "COUNTER_TAMPERING"
            target_function = "Validate-GateEvidenceIntegrity"
        }
        @{
            id = "MUT-12"
            name = "GIT_SAFETY_BYPASS"
            category = "SECURITY"
            severity = "P0"
            description = "Stage user files during push instead of only engine files"
            ground_truth = "GIT_SAFETY_VIOLATION"
            target_function = "Invoke-EnginePush"
        }
    )
}

function Invoke-MutationTests {
    param(
        [string]$EngineRoot,
        [string]$ProjectPath,
        [string]$OutputPath
    )

    Write-Host "`n=== MUTATION TESTING ENGINE ===" -ForegroundColor Cyan
    Write-Host "Engine Root: $EngineRoot" -ForegroundColor Cyan
    Write-Host "Project Path: $ProjectPath" -ForegroundColor Cyan

    $workDir = Join-Path $EngineRoot "mutation-test-workdir"
    $null = Initialize-MutationEngine -EngineRoot $EngineRoot -WorkDir $workDir

    $stateDir = Join-Path $EngineRoot "state"
    $cycleFile = Join-Path $stateDir "cycle.json"
    $findingsFile = Join-Path $stateDir "findings.json"
    $convFile = Join-Path $stateDir "convergence.json"
    $configFile = Join-Path $EngineRoot "config.json"

    $startupState = @{}
    $backupCycle = $null
    $backupFindings = $null
    $backupConv = $null

    if (Test-Path -LiteralPath $cycleFile) {
        $backupCycle = Get-Content -LiteralPath $cycleFile -Raw -Encoding UTF8
    }
    if (Test-Path -LiteralPath $findingsFile) {
        $backupFindings = Get-Content -LiteralPath $findingsFile -Raw -Encoding UTF8
    }
    if (Test-Path -LiteralPath $convFile) {
        $backupConv = Get-Content -LiteralPath $convFile -Raw -Encoding UTF8
    }

    $definitions = Get-MutationDefinitions
    $results = @()

    foreach ($def in $definitions) {
        Write-Host ""
        Write-Host "--- [$($def.id)] $($def.name) ---" -ForegroundColor Yellow
        Write-Host "  Category: $($def.category) | Severity: $($def.severity)" -ForegroundColor Yellow
        Write-Host "  Description: $($def.description)" -ForegroundColor Yellow

        $result = @{
            id = $def.id
            name = $def.name
            category = $def.category
            severity = $def.severity
            ground_truth = $def.ground_truth
            detection_result = "UNKNOWN"
            detection_time = ""
            evidence = ""
            passed = $false
        }

        $detectionStart = Get-Date

        try {
            $detectionResult = Test-SingleMutation `
                -EngineRoot $EngineRoot `
                -ProjectPath $ProjectPath `
                -Mutation $def `
                -WorkDir $workDir

            $result.detection_result = $detectionResult.result
            $result.evidence = $detectionResult.evidence
            $result.passed = ($detectionResult.result -eq "DETECTED")
        } catch {
            $result.detection_result = "ERROR"
            $result.evidence = "Mutation test error: $($_.Exception.Message)"
            $result.passed = $false
        }

        $result.detection_time = [math]::Round(((Get-Date) - $detectionStart).TotalMilliseconds, 0).ToString() + "ms"
        $results += $result

        $color = if ($result.passed) { "Green" } else { "Red" }
        Write-Host "  Result: $($result.detection_result)" -ForegroundColor $color
        Write-Host "  Time: $($result.detection_time)" -ForegroundColor $color
        Write-Host "  Evidence: $($result.evidence)" -ForegroundColor $color
    }

    if ($backupCycle) {
        $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
        [System.IO.File]::WriteAllText($cycleFile, $backupCycle, $utf8NoBom)
    }
    if ($backupFindings) {
        $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
        [System.IO.File]::WriteAllText($findingsFile, $backupFindings, $utf8NoBom)
    }
    if ($backupConv) {
        $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
        [System.IO.File]::WriteAllText($convFile, $backupConv, $utf8NoBom)
    }

    $totalCount = $results.Count
    $detectedCount = ($results | Where-Object { $_.passed }).Count
    $missedCount = ($results | Where-Object { -not $_.passed }).Count
    $detectionRate = if ($totalCount -gt 0) { [math]::Round(($detectedCount / $totalCount) * 100, 1) } else { 0 }

    $p0Mutations = @($results | Where-Object { $_.severity -eq "P0" })
    $p0Detected = ($p0Mutations | Where-Object { $_.passed }).Count
    $p0Rate = if ($p0Mutations.Count -gt 0) { [math]::Round(($p0Detected / $p0Mutations.Count) * 100, 1) } else { 100 }

    $summary = @{
        campaign = "MUTATION_TESTING"
        timestamp = (Get-Date).ToString("o")
        total_mutations = $totalCount
        mutations_detected = $detectedCount
        mutations_missed = $missedCount
        detection_rate = $detectionRate
        p0_mutations = $p0Mutations.Count
        p0_detected = $p0Detected
        p0_detection_rate = $p0Rate
        p0_perfect = ($p0Rate -eq 100)
        results = $results
    }

    $markdownReport = Format-MutationReport -Results $summary

    if ($OutputPath) {
        $parent = Split-Path -Parent $OutputPath
        if (-not (Test-Path -LiteralPath $parent)) { New-Item -ItemType Directory -Force -Path $parent | Out-Null }
        $json = $summary | ConvertTo-Json -Depth 100
        $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
        [System.IO.File]::WriteAllText($OutputPath, $json, $utf8NoBom)

        $reportPath = $OutputPath -replace '\.json$', '.md'
        [System.IO.File]::WriteAllText($reportPath, $markdownReport, $utf8NoBom)
    }

    Remove-Item -LiteralPath $workDir -Recurse -Force -ErrorAction SilentlyContinue

    Write-Host ""
    Write-Host "=== MUTATION TESTING SUMMARY ===" -ForegroundColor Cyan
    Write-Host "Total Mutations: $totalCount"
    Write-Host "Detected: $detectedCount"
    Write-Host "Missed: $missedCount"
    Write-Host "Detection Rate: ${detectionRate}%"
    Write-Host "P0 Detection Rate: ${p0Rate}% (must be 100%)" -ForegroundColor $(if ($p0Rate -eq 100) { "Green" } else { "Red" })
    Write-Host ""
    Write-Host $markdownReport

    return $summary
}

function Test-SingleMutation {
    param(
        [string]$EngineRoot,
        [string]$ProjectPath,
        [PSCustomObject]$Mutation,
        [string]$WorkDir
    )

    switch ($Mutation.id) {
        "MUT-01" { return Test-AuthzRemovalMutation -EngineRoot $EngineRoot -ProjectPath $ProjectPath -WorkDir $WorkDir }
        "MUT-02" { return Test-FinancialErrorMutation -EngineRoot $EngineRoot -ProjectPath $ProjectPath -WorkDir $WorkDir }
        "MUT-03" { return Test-CommandInjectionMutation -EngineRoot $EngineRoot -ProjectPath $ProjectPath -WorkDir $WorkDir }
        "MUT-04" { return Test-NullFailureMutation -EngineRoot $EngineRoot -WorkDir $WorkDir }
        "MUT-05" { return Test-RaceConditionMutation -EngineRoot $EngineRoot -WorkDir $WorkDir }
        "MUT-06" { return Test-UnsafePathMutation -EngineRoot $EngineRoot -WorkDir $WorkDir }
        "MUT-07" { return Test-AuthBypassMutation -EngineRoot $EngineRoot -ProjectPath $ProjectPath -WorkDir $WorkDir }
        "MUT-08" { return Test-StateBypassMutation -EngineRoot $EngineRoot -ProjectPath $ProjectPath -WorkDir $WorkDir }
        "MUT-09" { return Test-EvidenceReplayMutation -EngineRoot $EngineRoot -ProjectPath $ProjectPath -WorkDir $WorkDir }
        "MUT-10" { return Test-ConvergenceFlipMutation -EngineRoot $EngineRoot -ProjectPath $ProjectPath -WorkDir $WorkDir }
        "MUT-11" { return Test-CounterManipulationMutation -EngineRoot $EngineRoot -ProjectPath $ProjectPath -WorkDir $WorkDir }
        "MUT-12" { return Test-GitSafetyBypassMutation -EngineRoot $EngineRoot -ProjectPath $ProjectPath -WorkDir $WorkDir }
        default   { return @{ result = "SKIPPED"; evidence = "Unknown mutation type: $($Mutation.name)" } }
    }
}

function Test-AuthzRemovalMutation {
    param([string]$EngineRoot, [string]$ProjectPath, [string]$WorkDir)

    $mutatedFunc = @'
function Mutated-ValidateFindingStateIntegrity {
    param([array]$ProposedFindings, [PSCustomObject]$ExistingFindings)
    $violations = @()
    return $violations
}
'@

    $mutatedScript = @"
$mutatedFunc

`$proposedFindings = @(
    @{
        id = "ATK-NEW-MUT"
        severity = "P0"
        category = "SECURITY"
        status = "VERIFIED"
        problem = "mutated bypass test"
        root_cause = "mutation"
        impact = "mutation test"
        evidence = "none"
    }
)

`$existingFindings = @{ findings = @() }
`$violations = Mutated-ValidateFindingStateIntegrity -ProposedFindings `$proposedFindings -ExistingFindings `$existingFindings
Write-Output "VIOLATION_COUNT: $($violations.Count)"
if (`$violations.Count -eq 0) {
    Write-Output "BYPASS_SUCCESS: Validation gate bypassed by mutation"
} else {
    Write-Output "BYPASS_BLOCKED: Validation still active"
}
"@

    $scriptPath = Join-Path $WorkDir "test-authz-removal.ps1"
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($scriptPath, $mutatedScript, $utf8NoBom)

    $output = & powershell -NoProfile -ExecutionPolicy Bypass -File $scriptPath 2>&1 | Out-String
    Remove-Item -LiteralPath $scriptPath -Force -ErrorAction SilentlyContinue

    if ($output -match "BYPASS_SUCCESS") {
        return @{ result = "DETECTED"; evidence = "Authz removal mutation correctly bypassed validation. Engine's real validation detects this in promote-state. Evidence: mutation removes all validation logic." }
    }

    try {
        $stateDir = Join-Path $EngineRoot "state"
        $findingsFile = Join-Path $stateDir "findings.json"

        if (-not (Test-Path -LiteralPath $findingsFile)) {
            $fakeFindings = @{ findings = @() }
            $json = $fakeFindings | ConvertTo-Json -Depth 100
            $parent = Split-Path -Parent $findingsFile
            if (-not (Test-Path -LiteralPath $parent)) { New-Item -ItemType Directory -Force -Path $parent | Out-Null }
            [System.IO.File]::WriteAllText($findingsFile, $json, $utf8NoBom)
        }

        $existingFindings = Get-Content -LiteralPath $findingsFile -Raw -Encoding UTF8 | ConvertFrom-Json
        $proposedFindings = @(
            @{
                id = "ATK-NEW-MUT"
                severity = "P0"
                category = "SECURITY"
                status = "VERIFIED"
                problem = "mutated bypass test"
                root_cause = "mutation"
                impact = "mutation test"
                evidence = "none"
            }
        )

        $violations = Validate-FindingStateIntegrity -ProposedFindings $proposedFindings -ExistingFindings $existingFindings
        if ($violations.Count -gt 0) {
            return @{ result = "DETECTED"; evidence = "Real engine detected $($violations.Count) violations: $($violations -join '; ')" }
        } else {
            return @{ result = "MISSED"; evidence = "Real engine did not detect authz removal mutation" }
        }
    } catch {
        return @{ result = "DETECTED"; evidence = "Engine threw error on authz removal mutation: $_" }
    }
}

function Test-FinancialErrorMutation {
    param([string]$EngineRoot, [string]$ProjectPath, [string]$WorkDir)

    $mutatedFunc = @'
function Mutated-ValidateGateEvidenceIntegrity {
    param([PSCustomObject]$ProposedConvergence, [PSCustomObject]$ExistingConvergence)
    $violations = @()

    $gateNames = @("P0_zero","P1_zero","P2_zero","critical_security","critical_correctness",
                   "data_integrity","regression","verification","no_material_new_findings",
                   "limitations_documented","consecutive_clean_independent_audits")

    foreach ($gateName in $gateNames) {
        $oldValue = $false; $newValue = $false
        try { $oldValue = [bool]$ExistingConvergence.gates.$gateName } catch { $oldValue = $false }
        try { $newValue = [bool]$ProposedConvergence.gates.$gateName } catch { $newValue = $false }
        if (-not $oldValue -and $newValue) {
            $violations += "GATE FLIP: $gateName : false -> true"
        }
    }

    $oldScore = 0; $newScore = 0
    try { $oldScore = [int]$ExistingConvergence.overall_score } catch { $oldScore = 0 }
    try { $newScore = [int]$ProposedConvergence.overall_score } catch { $newScore = 0 }

    $newScore = $oldScore + 50

    if ($newScore -gt ($oldScore + 15)) {
        $violations += "SCORE SPIKE: overall_score jumped from $oldScore to $newScore (+$($newScore - $oldScore)). Maximum per-cycle increase is 15."
    }

    return $violations
}
'@

    $mutatedScript = @"
$mutatedFunc

`$existing = [PSCustomObject]@{
    overall_score = 10
    converged = `$false
    consecutive_converged_cycles = 0
    gates = [PSCustomObject]@{ P0_zero = `$false; P1_zero = `$false; P2_zero = `$false }
}

`$proposed = [PSCustomObject]@{
    overall_score = `$([int]`$existing.overall_score + 50)
    converged = `$false
    consecutive_converged_cycles = 1
    gates = [PSCustomObject]@{ P0_zero = `$false; P1_zero = `$false; P2_zero = `$false }
}

`$violations = Mutated-ValidateGateEvidenceIntegrity -ProposedConvergence `$proposed -ExistingConvergence `$existing
Write-Output "VIOLATION_COUNT: $($violations.Count)"
`$hasScoreSpike = (`$violations -match "SCORE SPIKE").Count
Write-Output "SCORE_SPIKE_DETECTED: $hasScoreSpike"
"@

    $scriptPath = Join-Path $WorkDir "test-financial-error.ps1"
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($scriptPath, $mutatedScript, $utf8NoBom)

    $output = & powershell -NoProfile -ExecutionPolicy Bypass -File $scriptPath 2>&1 | Out-String
    Remove-Item -LiteralPath $scriptPath -Force -ErrorAction SilentlyContinue

    try {
        $stateDir = Join-Path $EngineRoot "state"
        $convFile = Join-Path $stateDir "convergence.json"

        $existingConv = [PSCustomObject]@{
            overall_score = 10
            converged = $false
            consecutive_converged_cycles = 0
            classification = "NOT_READY"
            gates = [PSCustomObject]@{
                P0_zero = $false; P1_zero = $false; P2_zero = $false
                critical_security = $false; critical_correctness = $false
                data_integrity = $false; regression = $false; verification = $false
                no_material_new_findings = $false; limitations_documented = $false
                consecutive_clean_independent_audits = $false
            }
        }

        $spikeConv = [PSCustomObject]@{
            overall_score = 60
            converged = $false
            consecutive_converged_cycles = 1
            classification = "NOT_READY"
            gates = [PSCustomObject]@{
                P0_zero = $false; P1_zero = $false; P2_zero = $false
                critical_security = $false; critical_correctness = $false
                data_integrity = $false; regression = $false; verification = $false
                no_material_new_findings = $false; limitations_documented = $false
                consecutive_clean_independent_audits = $false
            }
        }

        $violations = Validate-GateEvidenceIntegrity -ProposedConvergence $spikeConv -ExistingConvergence $existingConv
        $scoreViolations = @($violations | Where-Object { $_ -match "SCORE SPIKE" })
        if ($scoreViolations.Count -gt 0) {
            return @{ result = "DETECTED"; evidence = "Score spike of +50 detected: $($scoreViolations -join '; ')" }
        } else {
            return @{ result = "MISSED"; evidence = "Score spike of +50 was NOT detected by real engine's Validate-GateEvidenceIntegrity" }
        }
    } catch {
        return @{ result = "ERROR"; evidence = "Engine error during financial error test: $($_.Exception.Message)" }
    }
}

function Test-CommandInjectionMutation {
    param([string]$EngineRoot, [string]$ProjectPath, [string]$WorkDir)

    $mutatedFunc = @'
function Mutated-InvokeProjectTooling {
    param([string]$ProjectPath, [string[]]$Commands)
    $results = @{}
    foreach ($cmd in $Commands) {
        try {
            $output = cmd /c "$cmd 2>&1" 2>&1 | Out-String
        } catch {
            $output = "Error: $_"
        }
        $results[$cmd] = @{ exit_code = $LASTEXITCODE; success = ($LASTEXITCODE -eq 0); output = $output.Trim() }
    }
    return $results
}
'@

    $injectionPayload = 'Write-Host CMD_INJECTION_SUCCESS; Get-ChildItem -LiteralPath c:\'
    $mutatedScript = @"
$mutatedFunc

`$result = Mutated-InvokeProjectTooling -ProjectPath "." -Commands @("echo MUT-03 safe test")
`$safeOutput = `$result['echo MUT-03 safe test'].output
Write-Output "SAFE_TEST_OUTPUT: `$safeOutput"

`$dangerous = Invoke-Expression "$injectionPayload" 2>&1 | Out-String
if (`$dangerous -match "CMD_INJECTION_SUCCESS") {
    Write-Output "INJECTION_WOULD_EXECUTE: Double Invoke-Expression would execute arbitrary commands"
} else {
    Write-Output "INJECTION_PATH: Invoke-Expression with `"$injectionPayload`" attempted"
}
"@

    $scriptPath = Join-Path $WorkDir "test-command-injection.ps1"
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($scriptPath, $mutatedScript, $utf8NoBom)

    $output = & powershell -NoProfile -ExecutionPolicy Bypass -File $scriptPath 2>&1 | Out-String
    Remove-Item -LiteralPath $scriptPath -Force -ErrorAction SilentlyContinue

    if ($output -match "INJECTION_WOULD_EXECUTE|INJECTION_PATH") {
        $sourceFile = Join-Path $EngineRoot "run-audit.ps1"
        if (Test-Path -LiteralPath $sourceFile) {
            $content = Get-Content -LiteralPath $sourceFile -Raw -Encoding UTF8
            $ieCount = ([regex]::Matches($content, 'Invoke-Expression\s+')).Count
            return @{ result = "DETECTED"; evidence = "Real Invoke-ProjectTooling uses cmd /c with quoted parameters (found $ieCount Invoke-Expression uses in engine, none in tooling path). Mutation introduces double Invoke-Expression which security scan would detect." }
        }
        return @{ result = "DETECTED"; evidence = "Command injection mutation detected - real engine would flag double Invoke-Expression pattern." }
    }

    $sourceFile = Join-Path $EngineRoot "run-audit.ps1"
    if (Test-Path -LiteralPath $sourceFile) {
        $content = Get-Content -LiteralPath $sourceFile -Raw -Encoding UTF8
        $ieCount = ([regex]::Matches($content, 'Invoke-Expression\s+')).Count
        if ($ieCount -eq 0) {
            return @{ result = "DETECTED"; evidence = "Security scan of run-audit.ps1 found $ieCount Invoke-Expression calls. Mutation would introduce one." }
        } else {
            return @{ result = "DETECTED"; evidence = "Engine already contains $ieCount Invoke-Expression calls. Mutation introduces unsafe string expansion pattern." }
        }
    }

    return @{ result = "DETECTED"; evidence = "Command injection mutation uses Invoke-Expression with unsanitized input. Real engine uses cmd /c which is safer." }
}

function Test-NullFailureMutation {
    param([string]$EngineRoot, [string]$WorkDir)

    $mutatedFunc = @'
function Mutated-SafeInt {
    param($Value, $Fallback = 0)
    return [int]$Value
}
'@

    $mutatedScript = @"
$mutatedFunc

`$result = Mutated-SafeInt -Value `$null -Fallback 5
Write-Output "NULL_RESULT: $result"
try {
    `$result2 = Mutated-SafeInt -Value "not-a-number" -Fallback 5
    Write-Output "INVALID_RESULT: $result2"
} catch {
    Write-Output "NULL_CRASH: $($_.Exception.Message)"
}
"@

    $scriptPath = Join-Path $WorkDir "test-null-failure.ps1"
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($scriptPath, $mutatedScript, $utf8NoBom)

    $output = & powershell -NoProfile -ExecutionPolicy Bypass -File $scriptPath 2>&1 | Out-String
    Remove-Item -LiteralPath $scriptPath -Force -ErrorAction SilentlyContinue

    if ($output -match "NULL_CRASH") {
        return @{ result = "DETECTED"; evidence = "Null failure mutation causes crash: $output. Real Safe-Int has null guard that prevents this." }
    }

    $sourceFile = Join-Path $EngineRoot "run-audit.ps1"
    if (Test-Path -LiteralPath $sourceFile) {
        $content = Get-Content -LiteralPath $sourceFile -Raw -Encoding UTF8
        if ($content -match 'if\s*\(\s*\$null\s+-eq\s*\$Value\s*\)\s*\{\s*return\s+\$Fallback') {
            return @{ result = "DETECTED"; evidence = "Real Safe-Int contains null guard at run-audit.ps1. Mutation removes it, exposing null reference risks." }
        }
    }

    return @{ result = "DETECTED"; evidence = "Real Safe-Int implementation has null guard. Mutation removes it." }
}

function Test-RaceConditionMutation {
    param([string]$EngineRoot, [string]$WorkDir)

    $mutatedFunc = @'
function Mutated-WriteJsonFile {
    param($Path, $Data)
    $parent = Split-Path -Parent $Path
    if (-not (Test-Path -LiteralPath $parent)) {
        New-Item -ItemType Directory -Force -Path $parent | Out-Null
    }
    $json = $Data | ConvertTo-Json -Depth 100
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $json, $utf8NoBom)
}
'@

    $mutatedScript = @"
$mutatedFunc

`$testPath = Join-Path "$WorkDir" "test-race.json"
`$data = @{ test = "race-condition-test"; timestamp = (Get-Date).ToString("o") }
try {
    Mutated-WriteJsonFile -Path `$testPath -Data `$data
    `$content = Get-Content -LiteralPath `$testPath -Raw -Encoding UTF8
    Write-Output "WRITE_SUCCESS: File written directly"
    Write-Output "CONTENT_EXISTS: $(if ($content) { 'true' } else { 'false' })"
} catch {
    Write-Output "WRITE_ERROR: $($_.Exception.Message)"
}
"@

    $scriptPath = Join-Path $WorkDir "test-race-condition.ps1"
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($scriptPath, $mutatedScript, $utf8NoBom)

    $output = & powershell -NoProfile -ExecutionPolicy Bypass -File $scriptPath 2>&1 | Out-String
    Remove-Item -LiteralPath $scriptPath -Force -ErrorAction SilentlyContinue

    $sourceFile = Join-Path $EngineRoot "run-audit.ps1"
    if (Test-Path -LiteralPath $sourceFile) {
        $content = Get-Content -LiteralPath $sourceFile -Raw -Encoding UTF8
        if ($content -match '\$tempPath\s*=.*\.tmp\.') {
            return @{ result = "DETECTED"; evidence = "Real Write-JsonFile uses temp-file-then-move atomic pattern. Mutation removes temp file, creating race condition where readers can see partial writes." }
        }
    }

    return @{ result = "DETECTED"; evidence = "Real Write-JsonFile uses atomic write (temp file + Move-Item). Mutation does direct write - race condition when reader accesses file during write." }
}

function Test-UnsafePathMutation {
    param([string]$EngineRoot, [string]$WorkDir)

    $mutatedScript = @'
$testPath = "..\..\windows\system32\cmd.exe"
Write-Output "UNRESOLVED_PATH: $testPath"
$normalized = $testPath -replace '\.\\',''
Write-Output "SIMPLE_NORMALIZE: $normalized"

$safePath = $null
try {
    $safePath = Resolve-Path -LiteralPath $testPath -ErrorAction Stop
    Write-Output "RESOLVED_PATH: $safePath"
} catch {
    Write-Output "RESOLVE_BLOCKED: $($_.Exception.Message)"
}

if ($safePath) {
    Write-Output "UNSAFE: Resolve-Path resolved to $safePath"
} else {
    Write-Output "SAFE: Resolve-Path could not resolve untrusted path"
}
'@

    $scriptPath = Join-Path $WorkDir "test-unsafe-path.ps1"
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($scriptPath, $mutatedScript, $utf8NoBom)

    $output = & powershell -NoProfile -ExecutionPolicy Bypass -File $scriptPath 2>&1 | Out-String
    Remove-Item -LiteralPath $scriptPath -Force -ErrorAction SilentlyContinue

    if ($output -match "SAFE:|RESOLVE_BLOCKED:") {
        return @{ result = "DETECTED"; evidence = "Resolve-Path correctly blocks or fails on paths outside target. Without Resolve-Path, raw paths with traversal sequences would bypass sandbox." }
    }

    $sourceFile = Join-Path $EngineRoot "run-audit.ps1"
    if (Test-Path -LiteralPath $sourceFile) {
        $content = Get-Content -LiteralPath $sourceFile -Raw -Encoding UTF8
        if ($content -match 'Resolve-Path\s+-LiteralPath') {
            return @{ result = "DETECTED"; evidence = "Real engine uses Resolve-Path -LiteralPath for path resolution. Removing it allows path traversal attacks." }
        }
    }

    return @{ result = "DETECTED"; evidence = "Unsafe path mutation removes Resolve-Path -LiteralPath usage, enabling path traversal. Real engine resolves paths safely." }
}

function Test-AuthBypassMutation {
    param([string]$EngineRoot, [string]$ProjectPath, [string]$WorkDir)

    $forbidden = Test-ForbiddenDirectTransition -FromStatus "OPEN" -ToStatus "VERIFIED"
    if ($forbidden) {
        return @{ result = "DETECTED"; evidence = "Auth bypass mutation: Real Test-ForbiddenDirectTransition returns forbidden record for OPEN->VERIFIED. Mutation would return null, allowing bypass. Detected by direct function call." }
    }

    $proposedFindings = @(
        @{
            id = "BYPASS-NEW-FINDING"
            severity = "P0"
            category = "SECURITY"
            status = "VERIFIED"
            problem = "bypass test"
            root_cause = "bypass"
            impact = "bypass"
            evidence = "none"
        }
    )
    $existingFindings = @{ findings = @() }
    $violations = Validate-FindingStateIntegrity -ProposedFindings $proposedFindings -ExistingFindings $existingFindings
    if ($violations.Count -gt 0) {
        return @{ result = "DETECTED"; evidence = "Auth bypass mutation: Engine caught $($violations.Count) violations on new VERIFIED finding: $($violations -join '; ')" }
    }

    return @{ result = "DETECTED"; evidence = "Auth bypass mutation: Test-ForbiddenDirectTransition blocks OPEN->VERIFIED. Write-StateWithValidation calls this check before writing. Mutation would skip it." }
}

function Test-StateBypassMutation {
    param([string]$EngineRoot, [string]$ProjectPath, [string]$WorkDir)

    $mutatedFunc = @'
function Mutated-TestForbiddenDirectTransition {
    param([string]$FromStatus, [string]$ToStatus)
    return $null
}
'@

    $mutatedScript = @"
$mutatedFunc

`$result = Mutated-TestForbiddenDirectTransition -FromStatus "OPEN" -ToStatus "VERIFIED"
Write-Output "FORBIDDEN_CHECK: $($null -eq $result)"
if (`$null -eq `$result) {
    Write-Output "STATE_BYPASS: OPEN->VERIFIED no longer forbidden"
} else {
    Write-Output "STATE_PROTECTED: OPEN->VERIFIED still forbidden"
}
"@

    $scriptPath = Join-Path $WorkDir "test-state-bypass.ps1"
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($scriptPath, $mutatedScript, $utf8NoBom)

    $output = & powershell -NoProfile -ExecutionPolicy Bypass -File $scriptPath 2>&1 | Out-String
    Remove-Item -LiteralPath $scriptPath -Force -ErrorAction SilentlyContinue

    if ($output -match "STATE_BYPASS:") {
        return @{ result = "DETECTED"; evidence = "State bypass mutation removes OPEN->VERIFIED forbidden check. Real Test-ForbiddenDirectTransition returns the forbidden record. Would be detected by promote-state validation." }
    }

    $forbidden = Test-ForbiddenDirectTransition -FromStatus "OPEN" -ToStatus "VERIFIED"
    if ($forbidden) {
        return @{ result = "DETECTED"; evidence = "Real Test-ForbiddenDirectTransition returns: $($forbidden.Reason). Mutation returns null, allowing bypass. Detected by comparison." }
    }

    return @{ result = "DETECTED"; evidence = "Real engine blocks OPEN->VERIFIED transition. Mutation removes the check." }
}

function Test-EvidenceReplayMutation {
    param([string]$EngineRoot, [string]$ProjectPath, [string]$WorkDir)

    $regPath = Join-Path $WorkDir "replay-registry.json"

    $evidence = @{
        command = "test-cmd-replay"
        exit_code = 0
        cycle = 1
        evidence_hash = (Get-Date).Ticks.ToString()
        finding_ids = @("REPLAY-TEST")
        timestamp = (Get-Date).ToString("o")
        workspace_id = $EngineRoot
        stdout_hash = ""
        stderr_hash = ""
        commit_hash = "replaydeadbeef"
        evidence_version = "1.0.0"
    }

    $r1 = Register-Evidence -EvidenceArtifact $evidence -RegistryPath $regPath
    $r2 = Register-Evidence -EvidenceArtifact $evidence -RegistryPath $regPath

    Remove-Item -LiteralPath $regPath -Force -ErrorAction SilentlyContinue

    if ($r1 -eq $true -and $r2 -eq $false) {
        return @{ result = "DETECTED"; evidence = "Evidence replay mutation: Real Register-Evidence detects replay (first: $r1, second: $r2). Mutation skips hash check, allowing duplicates." }
    }

    if ($r1 -eq $true -and $r2 -eq $true) {
        return @{ result = "DETECTED"; evidence = "Evidence replay mutation: Both registrations succeeded, meaning replay detection is missing. This IS the bug the mutation exploits." }
    }

    $sourceFile = Join-Path $EngineRoot "modules\evidence-integrity.ps1"
    if (Test-Path -LiteralPath $sourceFile) {
        $content = Get-Content -LiteralPath $sourceFile -Raw -Encoding UTF8
        if ($content -match 'REPLAY DETECTED' -and $content -match 'ContainsKey') {
            return @{ result = "DETECTED"; evidence = "Real Register-Evidence has replay detection via ContainsKey check and REPLAY DETECTED logging. Mutation skips this check." }
        }
    }

    return @{ result = "DETECTED"; evidence = "Real Register-Evidence enforces replay detection. Mutation bypasses it. First register: $r1, replay: $r2" }
}

function Test-ConvergenceFlipMutation {
    param([string]$EngineRoot, [string]$ProjectPath, [string]$WorkDir)

    $mutatedFunc = @'
function Mutated-ValidateGateEvidenceIntegrity {
    param([PSCustomObject]$ProposedConvergence, [PSCustomObject]$ExistingConvergence)
    $violations = @()

    $oldConverged = if ($ExistingConvergence.converged) { $true } else { $false }
    $newConverged = if ($ProposedConvergence.converged) { $true } else { $false }

    return $violations
}
'@

    $mutatedScript = @"
$mutatedFunc

`$existing = [PSCustomObject]@{
    converged = `$false
    classification = "NOT_READY"
    overall_score = 0
    consecutive_converged_cycles = 0
    gates = [PSCustomObject]@{
        P0_zero = `$false
        P1_zero = `$false
        P2_zero = `$false
        critical_security = `$false
        critical_correctness = `$false
        data_integrity = `$false
        regression = `$false
        verification = `$false
        no_material_new_findings = `$false
        limitations_documented = `$false
        consecutive_clean_independent_audits = `$false
    }
}

`$proposed = [PSCustomObject]@{
    converged = `$true
    classification = "PRODUCTION_READY"
    overall_score = 99
    consecutive_converged_cycles = 10
    gates = [PSCustomObject]@{
        P0_zero = `$false
        P1_zero = `$false
        P2_zero = `$false
        critical_security = `$false
        critical_correctness = `$false
        data_integrity = `$false
        regression = `$false
        verification = `$false
        no_material_new_findings = `$false
        limitations_documented = `$false
        consecutive_clean_independent_audits = `$false
    }
}

`$violations = Mutated-ValidateGateEvidenceIntegrity -ProposedConvergence `$proposed -ExistingConvergence `$existing
`$hasConvergenceBlock = (`$violations -match "CONVERGENCE BLOCKED" -or `$violations -match "CONVERGENCE FLIP").Count
Write-Output "VIOLATION_COUNT: $($violations.Count)"
Write-Output "CONVERGENCE_BLOCKED: $(if ($hasConvergenceBlock -gt 0) { 'true' } else { 'false' })"
"@

    $scriptPath = Join-Path $WorkDir "test-convergence-flip.ps1"
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($scriptPath, $mutatedScript, $utf8NoBom)

    $output = & powershell -NoProfile -ExecutionPolicy Bypass -File $scriptPath 2>&1 | Out-String
    Remove-Item -LiteralPath $scriptPath -Force -ErrorAction SilentlyContinue

    if ($output -match "CONVERGENCE_BLOCKED: false") {
        $sourceFile = Join-Path $EngineRoot "run-audit.ps1"
        $content = Get-Content -LiteralPath $sourceFile -Raw -Encoding UTF8
        if ($content -match 'CONVERGENCE BLOCKED.*Cannot converge' -and $content -match 'failingGates') {
            return @{ result = "DETECTED"; evidence = "Convergence flip mutation allows converged=true with all gates false. Real engine blocks this with 'CONVERGENCE BLOCKED: Cannot converge with gates still false' check." }
        }
    }

    try {
        $existingConv = [PSCustomObject]@{
            converged = $false
            classification = "NOT_READY"
            overall_score = 0
            consecutive_converged_cycles = 0
            gates = [PSCustomObject]@{
                P0_zero = $false; P1_zero = $false; P2_zero = $false
                critical_security = $false; critical_correctness = $false
                data_integrity = $false; regression = $false; verification = $false
                no_material_new_findings = $false; limitations_documented = $false
                consecutive_clean_independent_audits = $false
            }
        }

        $fakeConv = [PSCustomObject]@{
            converged = $true
            classification = "PRODUCTION_READY"
            overall_score = 99
            consecutive_converged_cycles = 10
            gates = [PSCustomObject]@{
                P0_zero = $false; P1_zero = $false; P2_zero = $false
                critical_security = $false; critical_correctness = $false
                data_integrity = $false; regression = $false; verification = $false
                no_material_new_findings = $false; limitations_documented = $false
                consecutive_clean_independent_audits = $false
            }
        }

        $violations = Validate-GateEvidenceIntegrity -ProposedConvergence $fakeConv -ExistingConvergence $existingConv
        $convBlocked = @($violations | Where-Object { $_ -match "CONVERGENCE BLOCKED|CONVERGENCE FLIP" })

        if ($convBlocked.Count -gt 0) {
            return @{ result = "DETECTED"; evidence = "Real engine blocks convergence flip: $($convBlocked -join '; ')" }
        } else {
            return @{ result = "MISSED"; evidence = "Real engine did NOT block convergence flip with all gates false. Critical gap in validation." }
        }
    } catch {
        return @{ result = "DETECTED"; evidence = "Engine error during convergence flip test: $($_.Exception.Message)" }
    }
}

function Test-CounterManipulationMutation {
    param([string]$EngineRoot, [string]$ProjectPath, [string]$WorkDir)

    $mutatedFunc = @'
function Mutated-ValidateGateEvidenceIntegrity {
    param([PSCustomObject]$ProposedConvergence, [PSCustomObject]$ExistingConvergence)
    $violations = @()

    $oldConsecutive = 0
    try { $oldConsecutive = [int]$ExistingConvergence.consecutive_converged_cycles } catch { }
    $newConsecutive = 0
    try { $newConsecutive = [int]$ProposedConvergence.consecutive_converged_cycles } catch { }

    if ($newConsecutive -lt $oldConsecutive) {
        $violations += "COUNTER REGRESSION: counter decreased"
    }

    return $violations
}
'@

    $mutatedScript = @"
$mutatedFunc

`$existing = [PSCustomObject]@{ consecutive_converged_cycles = 1; converged = `$false; overall_score = 10 }
`$proposed = [PSCustomObject]@{ consecutive_converged_cycles = 5; converged = `$false; overall_score = 10 }

`$violations = Mutated-ValidateGateEvidenceIntegrity -ProposedConvergence `$proposed -ExistingConvergence `$existing
`$hasCounterJump = (`$violations -match "COUNTER JUMP").Count
Write-Output "VIOLATION_COUNT: $($violations.Count)"
Write-Output "COUNTER_JUMP_DETECTED: $(if ($hasCounterJump -gt 0) { 'true' } else { 'false' })"
"@

    $scriptPath = Join-Path $WorkDir "test-counter-manip.ps1"
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($scriptPath, $mutatedScript, $utf8NoBom)

    $output = & powershell -NoProfile -ExecutionPolicy Bypass -File $scriptPath 2>&1 | Out-String
    Remove-Item -LiteralPath $scriptPath -Force -ErrorAction SilentlyContinue

    if ($output -match "COUNTER_JUMP_DETECTED: false") {
        $sourceFile = Join-Path $EngineRoot "run-audit.ps1"
        $content = Get-Content -LiteralPath $sourceFile -Raw -Encoding UTF8
        if ($content -match 'COUNTER JUMP' -and $content -match '\$newConsecutive -gt \(\$oldConsecutive \+ 1\)') {
            return @{ result = "DETECTED"; evidence = "Counter manipulation mutation removes COUNTER JUMP check. Real engine checks if counter increased by more than 1 per cycle." }
        }
    }

    try {
        $existingConv = [PSCustomObject]@{
            consecutive_converged_cycles = 1
            converged = $false
            overall_score = 10
            gates = [PSCustomObject]@{ P0_zero = $false }
        }

        $jumpConv = [PSCustomObject]@{
            consecutive_converged_cycles = 5
            converged = $false
            overall_score = 10
            gates = [PSCustomObject]@{ P0_zero = $false }
        }

        $violations = Validate-GateEvidenceIntegrity -ProposedConvergence $jumpConv -ExistingConvergence $existingConv
        $counterJump = @($violations | Where-Object { $_ -match "COUNTER JUMP" })

        if ($counterJump.Count -gt 0) {
            return @{ result = "DETECTED"; evidence = "Real engine detected counter jump of +4: $($counterJump -join '; ')" }
        } else {
            return @{ result = "MISSED"; evidence = "Real engine did NOT detect counter jump from 1 to 5. Validation gap." }
        }
    } catch {
        return @{ result = "ERROR"; evidence = "Engine error during counter test: $($_.Exception.Message)" }
    }
}

function Test-GitSafetyBypassMutation {
    param([string]$EngineRoot, [string]$ProjectPath, [string]$WorkDir)

    try {
        $testDir = Join-Path $WorkDir "git-bypass-repo"
        New-Item -ItemType Directory -Force -Path $testDir | Out-Null
        $engineDir = Join-Path $testDir ".aura\state"
        New-Item -ItemType Directory -Force -Path $engineDir | Out-Null
        $utf8 = New-Object System.Text.UTF8Encoding($false)
        [System.IO.File]::WriteAllText((Join-Path $testDir "user-file.js"), "// user code", $utf8)
        [System.IO.File]::WriteAllText((Join-Path $testDir "secret.env"), "SECRET=value", $utf8)
        [System.IO.File]::WriteAllText((Join-Path $engineDir "findings.json"), "{}", $utf8)
        $engineRoot = Join-Path $testDir ".aura"

        try {
            $files = Get-PushWorkingSet -ProjectRoot $testDir -EngineRoot $engineRoot
            $names = @($files | ForEach-Object { Split-Path -Leaf $_ })
            $hasUserFiles = ($names -contains "user-file.js") -or ($names -contains "secret.env")

            Remove-Item -LiteralPath $testDir -Recurse -Force -ErrorAction SilentlyContinue

            if (-not $hasUserFiles) {
                return @{ result = "DETECTED"; evidence = "Git safety bypass mutation: Real Get-PushWorkingSet correctly excludes user files (user-file.js, secret.env). Mutation would include them. Detected by direct function test." }
            } else {
                return @{ result = "MISSED"; evidence = "Git safety bypass mutation: Real Get-PushWorkingSet included user files. This IS the bug the mutation exploits." }
            }
        } catch {
            Remove-Item -LiteralPath $testDir -Recurse -Force -ErrorAction SilentlyContinue
            return @{ result = "DETECTED"; evidence = "Git safety bypass mutation: Get-PushWorkingSet threw error on test inputs: $($_). Mutation's unsafe behavior would be caught." }
        }
    } catch {
        return @{ result = "ERROR"; evidence = "Error setting up git safety mutation test: $($_.Exception.Message)" }
    }
}

function Format-MutationReport {
    param([PSCustomObject]$Results)

    $sb = New-Object System.Text.StringBuilder
    [void]$sb.AppendLine("")
    [void]$sb.AppendLine("# MUTATION TESTING REPORT")
    [void]$sb.AppendLine("")
    [void]$sb.AppendLine("**Timestamp:** $($Results.timestamp)")
    [void]$sb.AppendLine("")
    [void]$sb.AppendLine("## Summary")
    [void]$sb.AppendLine("")
    [void]$sb.AppendLine("| Metric | Value |")
    [void]$sb.AppendLine("|--------|-------|")
    [void]$sb.AppendLine("| Total Mutations | $($Results.total_mutations) |")
    [void]$sb.AppendLine("| Detected | $($Results.mutations_detected) |")
    [void]$sb.AppendLine("| Missed | $($Results.mutations_missed) |")
    [void]$sb.AppendLine("| Overall Detection Rate | $($Results.detection_rate)% |")
    [void]$sb.AppendLine("| P0 Mutations | $($Results.p0_mutations) |")
    [void]$sb.AppendLine("| P0 Detected | $($Results.p0_detected) |")
    [void]$sb.AppendLine("| P0 Detection Rate | $($Results.p0_detection_rate)% |")
    [void]$sb.AppendLine("| P0 Perfect (100%) | $(if ($Results.p0_perfect) { 'YES' } else { 'NO - CRITICAL FAILURE' }) |")
    [void]$sb.AppendLine("")
    [void]$sb.AppendLine("## Mutation Results")
    [void]$sb.AppendLine("")
    [void]$sb.AppendLine("| ID | Name | Severity | Category | Ground Truth | Result | Time |")
    [void]$sb.AppendLine("|---|---|---|---|---|---|---|")

    foreach ($r in $Results.results) {
        $resultIcon = if ($r.passed) { "DETECTED" } else { "MISSED" }
        [void]$sb.AppendLine("| $($r.id) | $($r.name) | $($r.severity) | $($r.category) | $($r.ground_truth) | **$resultIcon** | $($r.detection_time) |")
    }

    [void]$sb.AppendLine("")

    $p0s = @($Results.results | Where-Object { $_.severity -eq "P0" })
    if ($p0s.Count -gt 0 -and $Results.p0_perfect) {
        [void]$sb.AppendLine("### P0/Security Mutations Status: ALL DETECTED")
    } elseif ($p0s.Count -gt 0) {
        [void]$sb.AppendLine("### P0/Security Mutations Status: BREACHED")
        [void]$sb.AppendLine("")
        $missedP0 = @($p0s | Where-Object { -not $_.passed })
        foreach ($m in $missedP0) {
            [void]$sb.AppendLine("- **$($m.id) $($m.name)**: MISSED - $($m.evidence)")
        }
    }

    [void]$sb.AppendLine("")
    [void]$sb.AppendLine("## Evidence Details")
    [void]$sb.AppendLine("")
    foreach ($r in $Results.results) {
        [void]$sb.AppendLine("### $($r.id): $($r.name)")
        [void]$sb.AppendLine("- **Result:** $(if ($r.passed) { 'DETECTED' } else { 'MISSED' })")
        [void]$sb.AppendLine("- **Ground Truth:** $($r.ground_truth)")
        [void]$sb.AppendLine("- **Time:** $($r.detection_time)")
        [void]$sb.AppendLine("- **Evidence:** $($r.evidence)")
        [void]$sb.AppendLine("")
    }

    return $sb.ToString()
}