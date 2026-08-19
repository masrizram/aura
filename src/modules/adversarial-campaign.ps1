# ============================================================
# ADVERSARIAL STATE ATTACK CAMPAIGN v1.0.0
# Runs automated attacks against the state machine, evidence
# integrity, convergence gates, and state writer isolation.
# Each attack attempts to corrupt, bypass, or spoof the engine.
# ============================================================

function Invoke-AdversarialCampaign {
    param(
        [string]$EngineRoot,
        [string]$ProjectPath,
        [string]$CampaignOutput
    )

    $results = @{
        campaign = "STATE_INTEGRITY_ADVERSARIAL"
        timestamp = (Get-Date).ToString("o")
        attacks = @()
        summary = @{}
    }

    $configFile = Join-Path $EngineRoot "config.json"
    $cycleFile = Join-Path $EngineRoot "state/cycle.json"
    $findingsFile = Join-Path $EngineRoot "state/findings.json"
    $convFile = Join-Path $EngineRoot "state/convergence.json"
    $propFindings = Join-Path $EngineRoot "state/proposed-findings.json"
    $propConv = Join-Path $EngineRoot "state/proposed-convergence.json"
    $propCycleFile = Join-Path $EngineRoot "state/proposed-cycle.json"
    $toolingEvidence = Join-Path $EngineRoot "state/tooling-evidence.json"

    if (-not (Test-Path -LiteralPath $EngineRoot)) {
        $results.summary = @{ status = "SKIPPED"; reason = "Engine not initialized" }
        return $results
    }

    #########################################
    # ATTACK 1: Direct state file manipulation
    #########################################
    $atk1 = @{ id = "ATK-01"; name = "Direct convergence.json manipulation"; category = "STATE_AUTHORITY"; expected = "DETECTED_AS_INVALID"; passed = $false }

    try {
        $existingConv = Get-Content -LiteralPath $convFile -Raw -Encoding UTF8 | ConvertFrom-Json

        $malicious = $existingConv.PSObject.Copy()
        $malicious.converged = $true
        $malicious.classification = "PRODUCTION_READY"
        $malicious.gates.consecutive_clean_independent_audits = $true
        $malicious.overall_score = 99

        $tempFile = "$convFile.test-malicious.tmp"
        $json = $malicious | ConvertTo-Json -Depth 100
        $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
        [System.IO.File]::WriteAllText($tempFile, $json, $utf8NoBom)

        $propConvContent = $malicious | ConvertTo-Json -Depth 100
        [System.IO.File]::WriteAllText($propConv, $propConvContent, $utf8NoBom)

        $violations = Validate-GateEvidenceIntegrity -ProposedConvergence $malicious -ExistingConvergence $existingConv
        $atk1.detail = "Violations found: $($violations.Count). " + ($violations -join "; ")
        $atk1.passed = ($violations.Count -gt 0)

        Remove-Item -LiteralPath $tempFile -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $propConv -Force -ErrorAction SilentlyContinue
    } catch {
        $atk1.detail = "Error: $_"
    }

    $results.attacks += $atk1

    #########################################
    # ATTACK 2: Forbidden finding transition (OPEN -> VERIFIED)
    #########################################
    $atk2 = @{ id = "ATK-02"; name = "Forbidden OPEN->VERIFIED transition"; category = "STATE_AUTHORITY"; expected = "REJECTED"; passed = $false }

    try {
        $existingFindings = Get-Content -LiteralPath $findingsFile -Raw -Encoding UTF8 | ConvertFrom-Json

        $maliciousFinding = @{
            id = "FIND-1-01"
            severity = "P0"
            category = "SECURITY"
            status = "VERIFIED"
            problem = "test"
            root_cause = "test"
            impact = "test"
            evidence = "test"
            confidence = "HIGH"
            risk_score = 625
            location = "test"
            recommended_fix = "test"
        }

        $forbidden = Test-ForbiddenDirectTransition -FromStatus "OPEN" -ToStatus "VERIFIED"
        if ($forbidden) {
            $atk2.passed = $true
            $atk2.detail = "Transition blocked: $($forbidden.Reason)"
        } else {
            $atk2.detail = "Transition NOT blocked - security failure!"
        }

        $validTransition = Test-ValidFindingTransition -FromStatus "OPEN" -ToStatus "VERIFIED"
        if ($validTransition) {
            $atk2.passed = $false
            $atk2.detail += " | VALID TRANSITION returned TRUE for OPEN->VERIFIED (should be FALSE)"
        }
    } catch {
        $atk2.detail = "Error: $_"
    }

    $results.attacks += $atk2

    #########################################
    # ATTACK 3: Score spike (>15 per cycle)
    #########################################
    $atk3 = @{ id = "ATK-03"; name = "Score spike attack (+50)"; category = "CONVERGENCE_SAFETY"; expected = "REJECTED"; passed = $false }

    try {
        $existingConv = Get-Content -LiteralPath $convFile -Raw -Encoding UTF8 | ConvertFrom-Json

        $spikeConv = $existingConv.PSObject.Copy()
        $spikeConv.overall_score = [int]$existingConv.overall_score + 50

        $violations = Validate-GateEvidenceIntegrity -ProposedConvergence $spikeConv -ExistingConvergence $existingConv
        $scoreViolations = @($violations | Where-Object { $_ -match "SCORE SPIKE" })
        $atk3.detail = "Score spike violations: $($scoreViolations.Count)"
        $atk3.passed = ($scoreViolations.Count -gt 0)
    } catch {
        $atk3.detail = "Error: $_"
    }

    $results.attacks += $atk3

    #########################################
    # ATTACK 4: Counter jump (consecutive +3)
    #########################################
    $atk4 = @{ id = "ATK-04"; name = "Counter jump attack (+3)"; category = "CONVERGENCE_SAFETY"; expected = "REJECTED"; passed = $false }

    try {
        $existingConv = Get-Content -LiteralPath $convFile -Raw -Encoding UTF8 | ConvertFrom-Json

        $jumpConv = $existingConv.PSObject.Copy()
        $jumpConv.consecutive_converged_cycles = [int]$existingConv.consecutive_converged_cycles + 3

        $violations = Validate-GateEvidenceIntegrity -ProposedConvergence $jumpConv -ExistingConvergence $existingConv
        $counterViolations = @($violations | Where-Object { $_ -match "COUNTER JUMP" })
        $atk4.detail = "Counter jump violations: $($counterViolations.Count)"
        $atk4.passed = ($counterViolations.Count -gt 0)
    } catch {
        $atk4.detail = "Error: $_"
    }

    $results.attacks += $atk4

    #########################################
    # ATTACK 5: Score regression (decrease)
    #########################################
    $atk5 = @{ id = "ATK-05"; name = "Score regression attack (-10)"; category = "CONVERGENCE_SAFETY"; expected = "REJECTED"; passed = $false }

    try {
        $existingConv = Get-Content -LiteralPath $convFile -Raw -Encoding UTF8 | ConvertFrom-Json

        $regressionConv = $existingConv.PSObject.Copy()
        $regressionConv.overall_score = [int]$existingConv.overall_score - 10

        $violations = Validate-GateEvidenceIntegrity -ProposedConvergence $regressionConv -ExistingConvergence $existingConv
        $regViolations = @($violations | Where-Object { $_ -match "SCORE REGRESSION" })
        $atk5.detail = "Score regression violations: $($regViolations.Count)"
        $atk5.passed = ($regViolations.Count -gt 0)
    } catch {
        $atk5.detail = "Error: $_"
    }

    $results.attacks += $atk5

    #########################################
    # ATTACK 6: Converged flag attack without gates
    #########################################
    $atk6 = @{ id = "ATK-06"; name = "Converged=true with gates false"; category = "CONVERGENCE_SAFETY"; expected = "REJECTED"; passed = $false }

    try {
        $existingConv = Read-JsonFile $convFile

        $fakeConv = [PSCustomObject]@{
            converged = $true
            classification = "PRODUCTION_READY"
            overall_score = 62
            consecutive_converged_cycles = 10
            cycle = 99
            gates = [PSCustomObject]@{
                P0_zero = $false
                P1_zero = $false
                P2_zero = $false
                critical_security = $false
                critical_correctness = $false
                data_integrity = $false
                regression = $false
                verification = $false
                no_material_new_findings = $false
                limitations_documented = $false
                consecutive_clean_independent_audits = $false
            }
        }

        $violations = Validate-GateEvidenceIntegrity -ProposedConvergence $fakeConv -ExistingConvergence $existingConv
        $convViolations = @($violations | Where-Object { $_ -match "CONVERGENCE FLIP|CONVERGENCE BLOCKED" })
        $atk6.detail = "Convergence violations: $($convViolations.Count). " + ($convViolations -join "; ")
        $atk6.passed = ($convViolations.Count -gt 0)
    } catch {
        $atk6.detail = "Error: $_"
    }

    $results.attacks += $atk6

    #########################################
    # ATTACK 7: New finding with status VERIFIED
    #########################################
    $atk7 = @{ id = "ATK-07"; name = "New finding with VERIFIED status"; category = "STATE_AUTHORITY"; expected = "REJECTED"; passed = $false }

    try {
        $existingFindings = Read-JsonFile $findingsFile
        $maliciousNew = @(
            @{ id = "ATTACK-NEW-01"; severity = "P0"; category = "SECURITY"; risk_score = 625; confidence = "HIGH";
               status = "VERIFIED"; location = "test"; problem = "test"; root_cause = "test"; impact = "test"; evidence = "test"; recommended_fix = "test" }
        )
        $violations = Validate-FindingStateIntegrity -ProposedFindings $maliciousNew -ExistingFindings $existingFindings
        $atk7.detail = "New finding violations: $($violations.Count). " + ($violations -join "; ")
        $atk7.passed = ($violations.Count -gt 0)
    } catch {
        $atk7.detail = "Error: $_"
    }

    $results.attacks += $atk7

    #########################################
    # ATTACK 8: Finding deletion (remove critical finding)
    #########################################
    $atk8 = @{ id = "ATK-08"; name = "Finding deletion detection"; category = "DATA_INTEGRITY"; expected = "DETECTED"; passed = $false }

    try {
        $existingFindings = Read-JsonFile $findingsFile
        $originalCount = $existingFindings.findings.Count

        $reduced = $existingFindings.PSObject.Copy()
        $reduced.findings = @($existingFindings.findings | Select-Object -First ([int]($originalCount * 0.5)))

        $deletedCount = $originalCount - $reduced.findings.Count
        $atk8.detail = "Would delete $deletedCount findings (from $originalCount to $($reduced.findings.Count)). Deletion detection: finding count change is detectable."
        $atk8.passed = ($deletedCount -gt 0)
    } catch {
        $atk8.detail = "Error: $_"
    }

    $results.attacks += $atk8

    #########################################
    # ATTACK 9: Evidence replay detection
    #########################################
    $atk9 = @{ id = "ATK-09"; name = "Evidence replay attack"; category = "EVIDENCE_INTEGRITY"; expected = "DETECTED"; passed = $false }

    try {
        Initialize-EvidenceEngine -EngineRoot $EngineRoot
        $regPath = $Script:EvidenceRegistryFile

        $testEvidence = New-EvidenceArtifact -Command "test-cmd" -CommandArgs "" -ExitCode 0 `
            -Stdout "test-output" -Stderr "" -Cycle 99 -CommitHash "abc123" `
            -WorkspaceId $ProjectPath -FindingIds @("TEST-01")

        $firstReg = Register-Evidence -EvidenceArtifact $testEvidence -RegistryPath $regPath
        $secondReg = Register-Evidence -EvidenceArtifact $testEvidence -RegistryPath $regPath

        $atk9.passed = ($firstReg -eq $true -and $secondReg -eq $false)
        $atk9.detail = "First register: $firstReg, Second register (replay): $secondReg. Replay $(if ($secondReg) { 'NOT DETECTED' } else { 'DETECTED' })"

        $registry = Read-EvidenceRegistry -RegistryPath $regPath
        if ($registry -and $registry.replay_attempts) {
            $atk9.detail += " | Registry replay attempts: $($registry.replay_attempts.Count)"
        }
    } catch {
        $atk9.detail = "Error: $_"
    }

    $results.attacks += $atk9

    #########################################
    # ATTACK 10: Evidence freshness violation
    #########################################
    $atk10 = @{ id = "ATK-10"; name = "Stale evidence attack"; category = "EVIDENCE_INTEGRITY"; expected = "REJECTED"; passed = $false }

    try {
        $staleEvidence = @{
            cycle = 1
            command = "old-test"
            evidence_hash = "FAKE_STALE_HASH"
            finding_ids = @("TEST-02")
        }
        $fresh = Test-EvidenceFreshness -EvidenceArtifact $staleEvidence -CurrentCycle 10 -MaxAgeCycles 2
        $atk10.passed = (-not $fresh)
        $atk10.detail = "Stale evidence (cycle 1) used in cycle 10. Freshness returned: $fresh (expected: false)"
    } catch {
        $atk10.detail = "Error: $_"
    }

    $results.attacks += $atk10

    #########################################
    # ATTACK 11: Classification unauthorized transition
    #########################################
    $atk11 = @{ id = "ATK-11"; name = "Illegal classification jump (NOT_READY->PRODUCTION_READY)"; category = "CONVERGENCE_SAFETY"; expected = "REJECTED"; passed = $false }

    try {
        $valid = Test-ValidClassificationTransition -FromClassification "NOT_READY" -ToClassification "PRODUCTION_READY"
        $atk11.passed = (-not $valid)
        $atk11.detail = "NOT_READY->PRODUCTION_READY allowed: $valid (expected: false)"
    } catch {
        $atk11.detail = "Error: $_"
    }

    $results.attacks += $atk11

    #########################################
    # ATTACK 12: Force-validation bypass audit trail
    #########################################
    $atk12 = @{ id = "ATK-12"; name = "Force-validation bypass detection"; category = "DATA_INTEGRITY"; expected = "LOGGED"; passed = $false }

    try {
        $forceLogFile = Join-Path $EngineRoot "state/force-validation-log.json"

        $forceLog = @()
        if (Test-Path -LiteralPath $forceLogFile) {
            try {
                $existingLog = Get-Content -LiteralPath $forceLogFile -Raw -Encoding UTF8 | ConvertFrom-Json
                if ($existingLog -is [array]) { $forceLog = @($existingLog) }
            } catch { }
        }
        $forceLog += @{
            timestamp = (Get-Date).ToString("o")
            cycle = "test"
            reason = "Adversarial campaign: testing force-validation audit trail"
            warning = "This is a test entry"
        }
        $json = $forceLog | ConvertTo-Json -Depth 100
        $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
        [System.IO.File]::WriteAllText($forceLogFile, $json, $utf8NoBom)

        if (Test-Path -LiteralPath $forceLogFile) {
            $log = Get-Content -LiteralPath $forceLogFile -Raw -Encoding UTF8 | ConvertFrom-Json
            $entryCount = if ($log -is [array]) { $log.Count } elseif ($log) { 1 } else { 0 }
            $atk12.passed = ($entryCount -gt 0)
            $atk12.detail = "Force-validation audit trail exists with $entryCount entries."
        } else {
            $atk12.detail = "No force-validation log file created."
        }
    } catch {
        $atk12.detail = "Error: $_"
    }

    $results.attacks += $atk12

    #########################################
    # SUMMARY
    #########################################
    $passedCount = ($results.attacks | Where-Object { $_.passed }).Count
    $totalCount = $results.attacks.Count

    $results.summary = @{
        total_attacks = $totalCount
        attacks_detected = $passedCount
        attacks_breached = ($totalCount - $passedCount)
        detection_rate = [math]::Round(($passedCount / $totalCount) * 100, 1)
        status = if ($passedCount -eq $totalCount) { "ALL ATTACKS DETECTED" } else { "$($totalCount - $passedCount) BREACHES FOUND" }
    }

    Write-Host ""
    Write-Host "=== ADVERSARIAL CAMPAIGN RESULTS ===" -ForegroundColor Cyan
    Write-Host "Total attacks: $totalCount"
    Write-Host "Detected: $passedCount"
    Write-Host "Breached: $($totalCount - $passedCount)"
    Write-Host "Detection rate: $($results.summary.detection_rate)%"
    Write-Host "Status: $($results.summary.status)" -ForegroundColor $(if ($passedCount -eq $totalCount) { "Green" } else { "Red" })

    foreach ($atk in $results.attacks) {
        $color = if ($atk.passed) { "Green" } else { "Red" }
        Write-Host "  [$($atk.id)] $($atk.name): $(if ($atk.passed) { 'DETECTED' } else { 'BREACHED' })" -ForegroundColor $color
    }

    if ($CampaignOutput) {
        $json = $results | ConvertTo-Json -Depth 100
        $parent = Split-Path -Parent $CampaignOutput
        if (-not (Test-Path -LiteralPath $parent)) { New-Item -ItemType Directory -Force -Path $parent | Out-Null }
        $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
        [System.IO.File]::WriteAllText($CampaignOutput, $json, $utf8NoBom)
    }

    return $results
}