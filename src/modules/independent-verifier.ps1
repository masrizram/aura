# ============================================================
# INDEPENDENT VERIFICATION ENGINE v1.0.0
# Deterministic, independent oracle for finding validation.
# Cannot be subverted by the remediation agent.
# ============================================================

function New-IndependentVerifier {
    param(
        [string]$EngineRoot,
        [string]$ProjectPath
    )

    @{
        engine_root = $EngineRoot
        project_path = $ProjectPath
        orchestrators_executed = @()
        evidence_collected = @()
        verdicts = @()
    }
}

function Invoke-IndependentVerify {
    param(
        [hashtable]$Verifier,
        [PSCustomObject]$Finding,
        [PSCustomObject]$ProposedFix
    )

    $verdict = @{
        finding_id = $Finding.id
        timestamp = (Get-Date).ToString("o")
        verdict = "UNVERIFIED"
        checks = @()
        evidence = @{}
    }

    # Check 1: Schema validation
    $schemaCheck = Test-FindingSchema -Finding $Finding
    $verdict.checks += @{ name = "schema_validation"; passed = $schemaCheck.passed; detail = $schemaCheck.detail }

    # Check 2: Status transition legality
    $transitionCheck = Test-FindingTransitionLegality -Finding $Finding -Verifier $Verifier
    $verdict.checks += @{ name = "transition_legality"; passed = $transitionCheck.passed; detail = $transitionCheck.detail }

    # Check 3: Evidence completeness
    $evidenceCheck = Test-EvidenceCompleteness -Finding $Finding
    $verdict.checks += @{ name = "evidence_completeness"; passed = $evidenceCheck.passed; detail = $evidenceCheck.detail }

    # Check 4: Tooling evidence correlation
    $toolingCheck = Test-ToolingCorrelation -Finding $Finding -Verifier $Verifier
    $verdict.checks += @{ name = "tooling_correlation"; passed = $toolingCheck.passed; detail = $toolingCheck.detail }

    # Check 5: Deterministic invariant check
    $invariantCheck = Test-DeterministicInvariant -Finding $Finding -Verifier $Verifier
    $verdict.checks += @{ name = "deterministic_invariant"; passed = $invariantCheck.passed; detail = $invariantCheck.detail }

    $allPassed = ($verdict.checks | Where-Object { -not $_.passed }).Count -eq 0
    $verdict.verdict = if ($allPassed) { "VERIFIED" } else { "REJECTED" }

    return $verdict
}

function Test-FindingSchema {
    param([PSCustomObject]$Finding)

    $requiredFields = @("id", "severity", "category", "status", "problem", "root_cause", "impact", "evidence")
    $missingFields = @()
    foreach ($f in $requiredFields) {
        if (-not $Finding.$f -or [string]::IsNullOrWhiteSpace([string]$Finding.$f)) {
            $missingFields += $f
        }
    }

    $validSeverities = @("P0","P1","P2","P3","P4","P5")
    $validStatuses = @("OPEN","IN_PROGRESS","FIXED","VERIFYING","VERIFIED","REJECTED","DEFERRED","BLOCKED","UNVERIFIED","MERGED")

    $typeErrors = @()
    if ($Finding.severity -and [string]$Finding.severity -notin $validSeverities) {
        $typeErrors += "Invalid severity: $($Finding.severity)"
    }
    if ($Finding.status -and [string]$Finding.status -notin $validStatuses) {
        $typeErrors += "Invalid status: $($Finding.status)"
    }

    $passed = ($missingFields.Count -eq 0 -and $typeErrors.Count -eq 0)
    $detail = if ($passed) { "All required fields present and valid." }
              else { "Issues: $($missingFields -join ', ') $($typeErrors -join '; ')".Trim() }

    return @{ passed = $passed; detail = $detail }
}

function Test-FindingTransitionLegality {
    param([PSCustomObject]$Finding, [hashtable]$Verifier)
    $result = @{ passed = $true; detail = "Transition valid." }
    if ($Finding.status -eq "VERIFIED") {
        $hasVerification = $Finding.verification -and -not [string]::IsNullOrWhiteSpace($Finding.verification)
        $hasImplementFix = $Finding.implemented_fix -and -not [string]::IsNullOrWhiteSpace($Finding.implemented_fix)
        if (-not $hasVerification) {
            $result.passed = $false
            $result.detail += " Finding marked VERIFIED but verification field is empty."
        }
        if (-not $hasImplementFix) {
            $result.passed = $false
            $result.detail += " Finding marked VERIFIED but implemented_fix field is empty."
        }
    }
    return $result
}

function Test-EvidenceCompleteness {
    param([PSCustomObject]$Finding)

    $passed = $true
    $detail = "Evidence present."

    if (-not $Finding.evidence -or $Finding.evidence -match '^(test|fixed|done|yes|none|n/a|ok)$') {
        $passed = $false
        $detail = "Evidence field is generic/vacuous. Must contain specific, verifiable evidence (e.g., file paths, command output, specific behavior)."
    }

    return @{ passed = $passed; detail = $detail }
}

function Test-ToolingCorrelation {
    param([PSCustomObject]$Finding, [hashtable]$Verifier)

    $toolingFile = Join-Path $Verifier.engine_root "state/tooling-evidence.json"
    if (-not (Test-Path -LiteralPath $toolingFile)) {
        return @{ passed = $false; detail = "No tooling evidence file exists. Cannot correlate finding with tool execution." }
    }

    try {
        $tooling = Get-Content -LiteralPath $toolingFile -Raw -Encoding UTF8 | ConvertFrom-Json
        if (-not $tooling.results -or ($tooling.results.PSObject.Properties | Measure-Object).Count -eq 0) {
            return @{ passed = $false; detail = "Tooling evidence has no results. No tooling was executed." }
        }

        $anyPassed = $false
        foreach ($prop in $tooling.results.PSObject.Properties) {
            $r = $prop.Value
            if ($null -ne $r -and $r.success -eq $true -and $null -ne $r.exit_code -and ([int]$r.exit_code) -eq 0) {
                $anyPassed = $true; break
            }
        }

        if ($anyPassed) {
            return @{ passed = $true; detail = "Tooling evidence present with passing results." }
        } else {
            return @{ passed = $false; detail = "All tooling results show failures. Fix cannot be independently verified." }
        }
    } catch {
        return @{ passed = $false; detail = "Tooling evidence malformed: $_" }
    }
}

function Test-DeterministicInvariant {
    param([PSCustomObject]$Finding, [hashtable]$Verifier)

    $invariantsFile = Join-Path $Verifier.engine_root "state/invariant-definitions.json"
    if (Test-Path -LiteralPath $invariantsFile) {
        return @{ passed = $false; detail = "Deterministic invariant verification requires actual invariant check execution, not stub detection." }
    }
    return @{ passed = $false; detail = "Deterministic invariant definitions not initialized. Verification deferred until invariants loaded." }
}

function Invoke-BulkVerify {
    param(
        [hashtable]$Verifier,
        [array]$Findings
    )

    $verdicts = @()
    foreach ($f in $Findings) {
        $verdicts += Invoke-IndependentVerify -Verifier $Verifier -Finding $f -ProposedFix $null
    }

    $verified = ($verdicts | Where-Object { $_.verdict -eq "VERIFIED" }).Count
    $rejected = ($verdicts | Where-Object { $_.verdict -eq "REJECTED" }).Count
    $unverified = ($verdicts | Where-Object { $_.verdict -eq "UNVERIFIED" }).Count

    return @{
        total = $verdicts.Count
        verified = $verified
        rejected = $rejected
        unverified = $unverified
        verdicts = $verdicts
    }
}

function Test-IndependentDetectionRate {
    param(
        [hashtable]$Verifier,
        [array]$Defects,
        [array]$DetectedFindings
    )

    $defectIds = $Defects | ForEach-Object { $_.id }
    $detectedIds = $DetectedFindings | ForEach-Object {
        if ($_.id) { $_.id } else { $null }
    } | Where-Object { $_ }

    $found = @($defectIds | Where-Object { $_ -in $detectedIds })
    $missed = @($defectIds | Where-Object { $_ -notin $detectedIds })

    $detectionRate = if ($defectIds.Count -gt 0) {
        [math]::Round(($found.Count / $defectIds.Count) * 100, 1)
    } else { 0 }

    Write-Host "`n=== INDEPENDENT VERIFICATION DETECTION RATE ===" -ForegroundColor Cyan
    Write-Host "Total known defects: $($defectIds.Count)"
    Write-Host "Detected: $($found.Count)"
    Write-Host "Missed: $($missed.Count)"
    Write-Host "Detection rate: ${detectionRate}%"
    Write-Host "Critical false negatives: $(($missed | Where-Object { $_ -match 'P0|AUTH|SQL|BYPASS' } | Measure-Object).Count)"

    return @{
        total_defects = $defectIds.Count
        detected = $found.Count
        missed = $missed.Count
        detection_rate = $detectionRate
        missed_ids = $missed
        detected_ids = $found
    }
}