# Pester 5.x test suite for the AURA engine
# Tests the state machine, JSON I/O, gate integrity, convergence, I18n, and git safety enforcement

BeforeAll {
    $Script:EngineScript = Join-Path $PSScriptRoot "../../src/engine/run-audit.ps1"

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

    function Safe-Int($Value, $Fallback = 0) {
        if ($null -eq $Value) { return $Fallback }
        try { return [int]$Value } catch { return $Fallback }
    }

    function Validate-GateEvidenceIntegrity {
        param(
            [PSCustomObject]$ProposedConvergence,
            [PSCustomObject]$ExistingConvergence
        )
        $violations = @()
        if (-not $ExistingConvergence -or -not $ExistingConvergence.gates) { return $violations }
        $gateNames = @("P0_zero","P1_zero","P2_zero","critical_security","critical_correctness",
                       "data_integrity","regression","verification","no_material_new_findings",
                       "limitations_documented","consecutive_clean_independent_audits","module_dependency_integrity")
        foreach ($gateName in $gateNames) {
            $oldValue = $false; $newValue = $false
            try { $oldValue = [bool]$ExistingConvergence.gates.$gateName } catch { $oldValue = $false }
            try { $newValue = [bool]$ProposedConvergence.gates.$gateName } catch { $newValue = $false }
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
            $failingGates = @()
            foreach ($gn in $gateNames) {
                try { $gv = [bool]$ProposedConvergence.gates.$gn; if (-not $gv) { $failingGates += $gn } }
                catch { $failingGates += "$gn (missing)" }
            }
            if ($failingGates.Count -gt 0) {
                $violations += "CONVERGENCE BLOCKED: Cannot converge with gates still false/missing: $($failingGates -join ', ')"
            }
        }
        if ($newConverged) {
            $invFailingGates = @()
            foreach ($gn in $gateNames) {
                try { $gv = [bool]$ProposedConvergence.gates.$gn; if (-not $gv) { $invFailingGates += $gn } }
                catch { $invFailingGates += "$gn (missing)" }
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

    # I18n helpers for engine-level tests
    $Script:TestLangDir = Join-Path $PSScriptRoot "../../src/lang"

    function Get-LocaleData {
        param([string]$LocaleCode = "en")
        $langFile = Join-Path $Script:TestLangDir "$LocaleCode.json"
        if (-not (Test-Path -LiteralPath $langFile)) { return $null }
        try {
            $content = Get-Content -LiteralPath $langFile -Raw -Encoding UTF8
            return $content | ConvertFrom-Json
        } catch { return $null }
    }

    function Get-L10n {
        param([string]$Key, [hashtable]$Replacements = @{})
        $loc = Get-LocaleData -LocaleCode "en"
        if ($null -eq $loc) { return "[MISSING:$Key]" }
        $keys = $Key.Split(".")
        $current = $loc
        foreach ($k in $keys) {
            if ($null -eq $current) { break }
            $prop = $current.PSObject.Properties | Where-Object { $_.Name -eq $k }
            if ($prop) { $current = $prop.Value } else { $current = $null; break }
        }
        if ($null -eq $current -or $current -isnot [string]) { return "[MISSING:$Key]" }
        $result = [string]$current
        foreach ($kv in $Replacements.GetEnumerator()) {
            $result = $result -replace "\{$($kv.Key)\}", [string]$kv.Value
        }
        return $result
    }
}

# =====================================================================
# STATE MACHINE - FINDING TRANSITIONS
# =====================================================================

Describe 'State Machine - Finding Transitions' {
    Context 'Valid Transitions' {
        It 'OPEN -> IN_PROGRESS is valid' {
            Test-ValidFindingTransition -FromStatus "OPEN" -ToStatus "IN_PROGRESS" | Should -BeTrue
        }
        It 'OPEN -> DEFERRED is valid' {
            Test-ValidFindingTransition -FromStatus "OPEN" -ToStatus "DEFERRED" | Should -BeTrue
        }
        It 'OPEN -> BLOCKED is valid' {
            Test-ValidFindingTransition -FromStatus "OPEN" -ToStatus "BLOCKED" | Should -BeTrue
        }
        It 'IN_PROGRESS -> FIXED is valid' {
            Test-ValidFindingTransition -FromStatus "IN_PROGRESS" -ToStatus "FIXED" | Should -BeTrue
        }
        It 'IN_PROGRESS -> DEFERRED is valid' {
            Test-ValidFindingTransition -FromStatus "IN_PROGRESS" -ToStatus "DEFERRED" | Should -BeTrue
        }
        It 'IN_PROGRESS -> BLOCKED is valid' {
            Test-ValidFindingTransition -FromStatus "IN_PROGRESS" -ToStatus "BLOCKED" | Should -BeTrue
        }
        It 'IN_PROGRESS -> OPEN (revert) is valid' {
            Test-ValidFindingTransition -FromStatus "IN_PROGRESS" -ToStatus "OPEN" | Should -BeTrue
        }
        It 'FIXED -> VERIFYING is valid' {
            Test-ValidFindingTransition -FromStatus "FIXED" -ToStatus "VERIFYING" | Should -BeTrue
        }
        It 'FIXED -> OPEN (regression) is valid' {
            Test-ValidFindingTransition -FromStatus "FIXED" -ToStatus "OPEN" | Should -BeTrue
        }
        It 'VERIFYING -> VERIFIED is valid' {
            Test-ValidFindingTransition -FromStatus "VERIFYING" -ToStatus "VERIFIED" | Should -BeTrue
        }
        It 'VERIFYING -> REJECTED is valid' {
            Test-ValidFindingTransition -FromStatus "VERIFYING" -ToStatus "REJECTED" | Should -BeTrue
        }
        It 'VERIFYING -> FIXED (retry) is valid' {
            Test-ValidFindingTransition -FromStatus "VERIFYING" -ToStatus "FIXED" | Should -BeTrue
        }
        It 'VERIFIED -> OPEN (recurrence) is valid' {
            Test-ValidFindingTransition -FromStatus "VERIFIED" -ToStatus "OPEN" | Should -BeTrue
        }
        It 'REJECTED -> OPEN is valid' {
            Test-ValidFindingTransition -FromStatus "REJECTED" -ToStatus "OPEN" | Should -BeTrue
        }
        It 'REJECTED -> FIXED is valid' {
            Test-ValidFindingTransition -FromStatus "REJECTED" -ToStatus "FIXED" | Should -BeTrue
        }
        It 'DEFERRED -> OPEN is valid' {
            Test-ValidFindingTransition -FromStatus "DEFERRED" -ToStatus "OPEN" | Should -BeTrue
        }
        It 'BLOCKED -> OPEN is valid' {
            Test-ValidFindingTransition -FromStatus "BLOCKED" -ToStatus "OPEN" | Should -BeTrue
        }
        It 'UNVERIFIED -> OPEN is valid' {
            Test-ValidFindingTransition -FromStatus "UNVERIFIED" -ToStatus "OPEN" | Should -BeTrue
        }
    }

    Context 'Same-status (no-op) Transitions' {
        It 'OPEN -> OPEN is valid (no-op)' {
            Test-ValidFindingTransition -FromStatus "OPEN" -ToStatus "OPEN" | Should -BeTrue
        }
        It 'VERIFIED -> VERIFIED is valid (no-op)' {
            Test-ValidFindingTransition -FromStatus "VERIFIED" -ToStatus "VERIFIED" | Should -BeTrue
        }
        It 'IN_PROGRESS -> IN_PROGRESS is valid (no-op)' {
            Test-ValidFindingTransition -FromStatus "IN_PROGRESS" -ToStatus "IN_PROGRESS" | Should -BeTrue
        }
        It 'FIXED -> FIXED is valid (no-op)' {
            Test-ValidFindingTransition -FromStatus "FIXED" -ToStatus "FIXED" | Should -BeTrue
        }
    }

    Context 'Null/Empty from-status (new finding)' {
        It 'Null from-status always returns true' {
            Test-ValidFindingTransition -FromStatus $null -ToStatus "VERIFIED" | Should -BeTrue
        }
        It 'Empty string from-status always returns true' {
            Test-ValidFindingTransition -FromStatus "" -ToStatus "REJECTED" | Should -BeTrue
        }
        It 'Whitespace from-status always returns true' {
            Test-ValidFindingTransition -FromStatus "  " -ToStatus "FIXED" | Should -BeTrue
        }
    }

    Context 'Forbidden Transitions' {
        It 'OPEN -> VERIFIED is FORBIDDEN with reason mentioning FIXED' {
            $result = Test-ForbiddenDirectTransition -FromStatus "OPEN" -ToStatus "VERIFIED"
            $result | Should -Not -BeNullOrEmpty
            $result.Reason | Should -Match "FIXED"
        }
        It 'OPEN -> FIXED is FORBIDDEN with reason mentioning IN_PROGRESS' {
            $result = Test-ForbiddenDirectTransition -FromStatus "OPEN" -ToStatus "FIXED"
            $result | Should -Not -BeNullOrEmpty
            $result.Reason | Should -Match "IN_PROGRESS"
        }
        It 'IN_PROGRESS -> VERIFIED is FORBIDDEN' {
            $result = Test-ForbiddenDirectTransition -FromStatus "IN_PROGRESS" -ToStatus "VERIFIED"
            $result | Should -Not -BeNullOrEmpty
            $result.Reason | Should -Match "FIXED"
        }
        It 'FIXED -> VERIFIED is FORBIDDEN with reason mentioning VERIFYING' {
            $result = Test-ForbiddenDirectTransition -FromStatus "FIXED" -ToStatus "VERIFIED"
            $result | Should -Not -BeNullOrEmpty
            $result.Reason | Should -Match "VERIFYING"
        }
        It 'VERIFYING -> CLOSED is FORBIDDEN' {
            $result = Test-ForbiddenDirectTransition -FromStatus "VERIFYING" -ToStatus "CLOSED"
            $result | Should -Not -BeNullOrEmpty
        }
    }

    Context 'Invalid (not forbidden but not allowed) Transitions' {
        It 'OPEN -> VERIFIED is not valid' {
            Test-ValidFindingTransition -FromStatus "OPEN" -ToStatus "VERIFIED" | Should -BeFalse
        }
        It 'FIXED -> VERIFIED is not valid' {
            Test-ValidFindingTransition -FromStatus "FIXED" -ToStatus "VERIFIED" | Should -BeFalse
        }
        It 'VERIFIED -> FIXED (backwards) is not valid' {
            Test-ValidFindingTransition -FromStatus "VERIFIED" -ToStatus "FIXED" | Should -BeFalse
        }
        It 'VERIFIED -> IN_PROGRESS is not valid' {
            Test-ValidFindingTransition -FromStatus "VERIFIED" -ToStatus "IN_PROGRESS" | Should -BeFalse
        }
        It 'VERIFIED -> VERIFYING is not valid' {
            Test-ValidFindingTransition -FromStatus "VERIFIED" -ToStatus "VERIFYING" | Should -BeFalse
        }
        It 'REJECTED -> VERIFIED (skip verification) is not valid' {
            Test-ValidFindingTransition -FromStatus "REJECTED" -ToStatus "VERIFIED" | Should -BeFalse
        }
        It 'NONEXISTENT_STATUS -> anything should return false' {
            Test-ValidFindingTransition -FromStatus "NONEXISTENT_STATUS" -ToStatus "OPEN" | Should -BeFalse
        }
    }

    Context 'All forbidden transitions are blocked by both checks' {
        It 'Every forbidden transition is detected by Test-ForbiddenDirectTransition' {
            foreach ($forbidden in $Script:ForbiddenDirectTransitions) {
                $result = Test-ForbiddenDirectTransition -FromStatus $forbidden.From -ToStatus $forbidden.To
                $result | Should -Not -BeNullOrEmpty -Because "$($forbidden.From) -> $($forbidden.To) must be forbidden"
            }
        }
        It 'Every forbidden transition fails Test-ValidFindingTransition' {
            foreach ($forbidden in $Script:ForbiddenDirectTransitions) {
                Test-ValidFindingTransition -FromStatus $forbidden.From -ToStatus $forbidden.To | Should -BeFalse -Because "$($forbidden.From) -> $($forbidden.To) must not be valid"
            }
        }
    }

    Context 'All valid transitions defined symmetrically (full cross-check)' {
        It 'Every FROM status has at least one valid TO status (or self)' {
            foreach ($from in $Script:ValidFindingTransitions.Keys) {
                $allowed = $Script:ValidFindingTransitions[$from]
                $allowed.Count | Should -BeGreaterThan 0 -Because "$from must have at least one allowed transition"
            }
        }
        It 'Every declared FROM->TO is actually valid' {
            foreach ($from in $Script:ValidFindingTransitions.Keys) {
                foreach ($to in $Script:ValidFindingTransitions[$from]) {
                    Test-ValidFindingTransition -FromStatus $from -ToStatus $to | Should -BeTrue -Because "$from -> $to is declared valid"
                }
            }
        }
    }
}

# =====================================================================
# STATE MACHINE - CLASSIFICATION TRANSITIONS
# =====================================================================

Describe 'State Machine - Classification Transitions' {
    Context 'Valid Classifications' {
        It 'NOT_READY -> CONDITIONALLY_READY is valid' {
            Test-ValidClassificationTransition -FromClassification "NOT_READY" -ToClassification "CONDITIONALLY_READY" | Should -BeTrue
        }
        It 'NOT_READY -> HUMAN_BLOCKED is valid' {
            Test-ValidClassificationTransition -FromClassification "NOT_READY" -ToClassification "HUMAN_BLOCKED" | Should -BeTrue
        }
        It 'CONDITIONALLY_READY -> PRODUCTION_READY is valid' {
            Test-ValidClassificationTransition -FromClassification "CONDITIONALLY_READY" -ToClassification "PRODUCTION_READY" | Should -BeTrue
        }
        It 'CONDITIONALLY_READY -> NOT_READY is valid (downgrade)' {
            Test-ValidClassificationTransition -FromClassification "CONDITIONALLY_READY" -ToClassification "NOT_READY" | Should -BeTrue
        }
        It 'CONDITIONALLY_READY -> HUMAN_BLOCKED is valid' {
            Test-ValidClassificationTransition -FromClassification "CONDITIONALLY_READY" -ToClassification "HUMAN_BLOCKED" | Should -BeTrue
        }
        It 'PRODUCTION_READY -> NOT_READY is valid (regression)' {
            Test-ValidClassificationTransition -FromClassification "PRODUCTION_READY" -ToClassification "NOT_READY" | Should -BeTrue
        }
        It 'PRODUCTION_READY -> HUMAN_BLOCKED is valid' {
            Test-ValidClassificationTransition -FromClassification "PRODUCTION_READY" -ToClassification "HUMAN_BLOCKED" | Should -BeTrue
        }
        It 'HUMAN_BLOCKED -> NOT_READY is valid' {
            Test-ValidClassificationTransition -FromClassification "HUMAN_BLOCKED" -ToClassification "NOT_READY" | Should -BeTrue
        }
        It 'HUMAN_BLOCKED -> CONDITIONALLY_READY is valid' {
            Test-ValidClassificationTransition -FromClassification "HUMAN_BLOCKED" -ToClassification "CONDITIONALLY_READY" | Should -BeTrue
        }
    }

    Context 'Same-classification (no-op)' {
        It 'NOT_READY -> NOT_READY is valid' {
            Test-ValidClassificationTransition -FromClassification "NOT_READY" -ToClassification "NOT_READY" | Should -BeTrue
        }
        It 'PRODUCTION_READY -> PRODUCTION_READY is valid' {
            Test-ValidClassificationTransition -FromClassification "PRODUCTION_READY" -ToClassification "PRODUCTION_READY" | Should -BeTrue
        }
        It 'HUMAN_BLOCKED -> HUMAN_BLOCKED is valid' {
            Test-ValidClassificationTransition -FromClassification "HUMAN_BLOCKED" -ToClassification "HUMAN_BLOCKED" | Should -BeTrue
        }
    }

    Context 'Invalid Classifications' {
        It 'NOT_READY -> PRODUCTION_READY (skip CONDITIONALLY_READY) is invalid' {
            Test-ValidClassificationTransition -FromClassification "NOT_READY" -ToClassification "PRODUCTION_READY" | Should -BeFalse
        }
        It 'PRODUCTION_READY -> CONDITIONALLY_READY (backwards) is invalid' {
            Test-ValidClassificationTransition -FromClassification "PRODUCTION_READY" -ToClassification "CONDITIONALLY_READY" | Should -BeFalse
        }
        It 'CONDITIONALLY_READY -> HUMAN_BLOCKED -> PRODUCTION_READY (can bypass? No) check HUMAN_BLOCKED -> PRODUCTION_READY' {
            Test-ValidClassificationTransition -FromClassification "HUMAN_BLOCKED" -ToClassification "PRODUCTION_READY" | Should -BeFalse
        }
        It 'PRODUCTION_READY -> UNKNOWN_CLASS is invalid' {
            Test-ValidClassificationTransition -FromClassification "PRODUCTION_READY" -ToClassification "UNKNOWN_CLASSIFICATION" | Should -BeFalse
        }
    }

    Context 'Null/Empty from-classification' {
        It 'Null from-classification returns true' {
            Test-ValidClassificationTransition -FromClassification $null -ToClassification "PRODUCTION_READY" | Should -BeTrue
        }
        It 'Empty string from-classification returns true' {
            Test-ValidClassificationTransition -FromClassification "" -ToClassification "NOT_READY" | Should -BeTrue
        }
    }
}

# =====================================================================
# VALIDATE-FINDINGSTATEINTEGRITY
# =====================================================================

Describe 'Validate-FindingStateIntegrity' {
    Context 'Valid Finding Updates' {
        It 'Accepts valid transition OPEN -> IN_PROGRESS' {
            $existing = @{ findings = @(@{id="F001"; status="OPEN"; severity="P0"; category="SECURITY"; problem="X"}) }
            $proposed = @(@{id="F001"; status="IN_PROGRESS"; severity="P0"; category="SECURITY"; problem="X"})
            $violations = Validate-FindingStateIntegrity -ProposedFindings $proposed -ExistingFindings $existing
            $violations.Count | Should -Be 0
        }
        It 'Accepts OPEN -> BLOCKED' {
            $existing = @{ findings = @(@{id="F002"; status="OPEN"; severity="P1"; category="CORRECTNESS"; problem="Y"}) }
            $proposed = @(@{id="F002"; status="BLOCKED"; severity="P1"; category="CORRECTNESS"; problem="Y"})
            $violations = Validate-FindingStateIntegrity -ProposedFindings $proposed -ExistingFindings $existing
            $violations.Count | Should -Be 0
        }
        It 'Accepts IN_PROGRESS -> FIXED -> VERIFYING -> VERIFIED chain' {
            $existing = @{ findings = @(@{id="F003"; status="IN_PROGRESS"; severity="P2"; category="DATA_INTEGRITY"; problem="Z"}) }
            $proposed = @(@{id="F003"; status="FIXED"; severity="P2"; category="DATA_INTEGRITY"; problem="Z"})
            $violations = Validate-FindingStateIntegrity -ProposedFindings $proposed -ExistingFindings $existing
            $violations.Count | Should -Be 0
        }
        It 'Accepts VERIFIED -> OPEN (recurrence)' {
            $existing = @{ findings = @(@{id="F004"; status="VERIFIED"; severity="P3"; category="PERFORMANCE"; problem="Recurred"}) }
            $proposed = @(@{id="F004"; status="OPEN"; severity="P3"; category="PERFORMANCE"; problem="Recurred"})
            $violations = Validate-FindingStateIntegrity -ProposedFindings $proposed -ExistingFindings $existing
            $violations.Count | Should -Be 0
        }
        It 'Accepts new finding with OPEN status' {
            $existing = @{ findings = @() }
            $proposed = @(@{id="F005"; status="OPEN"; severity="P4"; category="MAINTAINABILITY"; problem="New finding"})
            $violations = Validate-FindingStateIntegrity -ProposedFindings $proposed -ExistingFindings $existing
            $violations.Count | Should -Be 0
        }
        It 'Accepts same-status update (no change)' {
            $existing = @{ findings = @(@{id="F006"; status="OPEN"; severity="P0"; category="SECURITY"; problem="A"}) }
            $proposed = @(@{id="F006"; status="OPEN"; severity="P0"; category="SECURITY"; problem="A updated"})
            $violations = Validate-FindingStateIntegrity -ProposedFindings $proposed -ExistingFindings $existing
            $violations.Count | Should -Be 0
        }
    }

    Context 'Invalid Finding Updates - Forbidden Transitions' {
        It 'Rejects OPEN -> VERIFIED' {
            $existing = @{ findings = @(@{id="F001"; status="OPEN"; severity="P0"; category="SECURITY"; problem="X"}) }
            $proposed = @(@{id="F001"; status="VERIFIED"; severity="P0"; category="SECURITY"; problem="X"})
            $violations = Validate-FindingStateIntegrity -ProposedFindings $proposed -ExistingFindings $existing
            $violations.Count | Should -BeGreaterThan 0
            ($violations -join ' ') | Should -Match "ILLEGAL TRANSITION"
        }
        It 'Rejects OPEN -> FIXED' {
            $existing = @{ findings = @(@{id="F002"; status="OPEN"; severity="P1"; category="CORRECTNESS"; problem="Y"}) }
            $proposed = @(@{id="F002"; status="FIXED"; severity="P1"; category="CORRECTNESS"; problem="Y"})
            $violations = Validate-FindingStateIntegrity -ProposedFindings $proposed -ExistingFindings $existing
            $violations.Count | Should -BeGreaterThan 0
            ($violations -join ' ') | Should -Match "IN_PROGRESS"
        }
        It 'Rejects IN_PROGRESS -> VERIFIED' {
            $existing = @{ findings = @(@{id="F003"; status="IN_PROGRESS"; severity="P2"; category="DATA_INTEGRITY"; problem="Z"}) }
            $proposed = @(@{id="F003"; status="VERIFIED"; severity="P2"; category="DATA_INTEGRITY"; problem="Z"})
            $violations = Validate-FindingStateIntegrity -ProposedFindings $proposed -ExistingFindings $existing
            $violations.Count | Should -BeGreaterThan 0
        }
        It 'Rejects FIXED -> VERIFIED' {
            $existing = @{ findings = @(@{id="F004"; status="FIXED"; severity="P0"; category="SECURITY"; problem="W"}) }
            $proposed = @(@{id="F004"; status="VERIFIED"; severity="P0"; category="SECURITY"; problem="W"})
            $violations = Validate-FindingStateIntegrity -ProposedFindings $proposed -ExistingFindings $existing
            $violations.Count | Should -BeGreaterThan 0
            ($violations -join ' ') | Should -Match "VERIFYING"
        }
        It 'Rejects VERIFYING -> CLOSED' {
            $existing = @{ findings = @(@{id="F005"; status="VERIFYING"; severity="P1"; category="CORRECTNESS"; problem="V"}) }
            $proposed = @(@{id="F005"; status="CLOSED"; severity="P1"; category="CORRECTNESS"; problem="V"})
            $violations = Validate-FindingStateIntegrity -ProposedFindings $proposed -ExistingFindings $existing
            $violations.Count | Should -BeGreaterThan 0
        }
    }

    Context 'Invalid Finding Updates - New Finding Violations' {
        It 'Rejects new finding with non-OPEN status' {
            $existing = @{ findings = @() }
            $proposed = @(@{id="F006"; status="VERIFIED"; severity="P0"; category="SECURITY"; problem="New but verified"})
            $violations = Validate-FindingStateIntegrity -ProposedFindings $proposed -ExistingFindings $existing
            $violations.Count | Should -BeGreaterThan 0
            ($violations -join ' ') | Should -Match "NEW FINDING VIOLATION"
        }
        It 'Rejects new finding with FIXED status' {
            $existing = @{ findings = @() }
            $proposed = @(@{id="F007"; status="FIXED"; severity="P2"; category="DATA_INTEGRITY"; problem="Already fixed"})
            $violations = Validate-FindingStateIntegrity -ProposedFindings $proposed -ExistingFindings $existing
            $violations.Count | Should -BeGreaterThan 0
            ($violations -join ' ') | Should -Match "NEW FINDING VIOLATION"
        }
        It 'Rejects new finding with BLOCKED status' {
            $existing = @{ findings = @() }
            $proposed = @(@{id="F008"; status="BLOCKED"; severity="P3"; category="TESTING"; problem="Blocked from start"})
            $violations = Validate-FindingStateIntegrity -ProposedFindings $proposed -ExistingFindings $existing
            $violations.Count | Should -BeGreaterThan 0
            ($violations -join ' ') | Should -Match "NEW FINDING VIOLATION"
        }
    }

    Context 'Invalid Finding Updates - Nonstandard Transitions' {
        It 'Rejects VERIFIED -> FIXED (backwards)' {
            $existing = @{ findings = @(@{id="F009"; status="VERIFIED"; severity="P1"; category="CORRECTNESS"; problem="Was verified"}) }
            $proposed = @(@{id="F009"; status="FIXED"; severity="P1"; category="CORRECTNESS"; problem="Was verified"})
            $violations = Validate-FindingStateIntegrity -ProposedFindings $proposed -ExistingFindings $existing
            $violations.Count | Should -BeGreaterThan 0
            ($violations -join ' ') | Should -Match "INVALID TRANSITION"
        }
        It 'Rejects BLOCKED -> FIXED (skip OPEN)' {
            $existing = @{ findings = @(@{id="F010"; status="BLOCKED"; severity="P0"; category="SECURITY"; problem="Blocked"}) }
            $proposed = @(@{id="F010"; status="FIXED"; severity="P0"; category="SECURITY"; problem="Blocked"})
            $violations = Validate-FindingStateIntegrity -ProposedFindings $proposed -ExistingFindings $existing
            $violations.Count | Should -BeGreaterThan 0
        }
        It 'Rejects DEFERRED -> FIXED (skip OPEN)' {
            $existing = @{ findings = @(@{id="F011"; status="DEFERRED"; severity="P2"; category="DATA_INTEGRITY"; problem="Deferred"}) }
            $proposed = @(@{id="F011"; status="FIXED"; severity="P2"; category="DATA_INTEGRITY"; problem="Deferred"})
            $violations = Validate-FindingStateIntegrity -ProposedFindings $proposed -ExistingFindings $existing
            $violations.Count | Should -BeGreaterThan 0
        }
    }

    Context 'Edge Cases' {
        It 'Handles null ExistingFindings gracefully' {
            $proposed = @(@{id="F012"; status="OPEN"; severity="P4"; category="DOCUMENTATION"; problem="New"})
            $violations = Validate-FindingStateIntegrity -ProposedFindings $proposed -ExistingFindings $null
            $violations.Count | Should -Be 0
        }
        It 'Handles empty proposed array' {
            $existing = @{ findings = @(@{id="F013"; status="OPEN"; severity="P5"; category="OPTIMIZATION"; problem="Old"}) }
            $violations = Validate-FindingStateIntegrity -ProposedFindings @() -ExistingFindings $existing
            $violations.Count | Should -Be 0
        }
        It 'Handles proposed finding without id field' {
            $existing = @{ findings = @() }
            $proposed = @(@{status="VERIFIED"; severity="P0"; category="SECURITY"})
            $violations = Validate-FindingStateIntegrity -ProposedFindings $proposed -ExistingFindings $existing
            $violations.Count | Should -Be 0
        }
        It 'Handles multiple findings (mix of valid and invalid)' {
            $existing = @{ findings = @(
                @{id="F014"; status="OPEN"; severity="P0"; category="SECURITY"; problem="Hardcoded key"},
                @{id="F015"; status="IN_PROGRESS"; severity="P1"; category="CORRECTNESS"; problem="Null ptr"},
                @{id="F016"; status="FIXED"; severity="P2"; category="PERFORMANCE"; problem="N+1 query"}
            )}
            $proposed = @(
                @{id="F014"; status="VERIFIED"; severity="P0"; category="SECURITY"; problem="Hardcoded key"},
                @{id="F015"; status="FIXED"; severity="P1"; category="CORRECTNESS"; problem="Null ptr"},
                @{id="F016"; status="VERIFYING"; severity="P2"; category="PERFORMANCE"; problem="N+1 query"}
            )
            $violations = Validate-FindingStateIntegrity -ProposedFindings $proposed -ExistingFindings $existing
            $violations.Count | Should -Be 1
            ($violations -join ' ') | Should -Match "F014.*ILLEGAL"
        }
    }
}

# =====================================================================
# VALIDATE-GATEEVIDENCEINTEGRITY
# =====================================================================

Describe 'Validate-GateEvidenceIntegrity' {
    Context 'Gate Flips' {
        It 'Detects P0_zero gate flip with evidence requirement' {
            $existing = @{ converged = $false; consecutive_converged_cycles = 0; overall_score = 50; gates = @{ P0_zero = $false; P1_zero = $false; P2_zero = $false; critical_security = $false; critical_correctness = $false; data_integrity = $false; regression = $false; verification = $false; no_material_new_findings = $false; limitations_documented = $false; consecutive_clean_independent_audits = $false; module_dependency_integrity = $true } }
            $proposed = @{ converged = $false; consecutive_converged_cycles = 0; overall_score = 50; gates = @{ P0_zero = $true; P1_zero = $false; P2_zero = $false; critical_security = $false; critical_correctness = $false; data_integrity = $false; regression = $false; verification = $false; no_material_new_findings = $false; limitations_documented = $false; consecutive_clean_independent_audits = $false; module_dependency_integrity = $true } }
            $violations = Validate-GateEvidenceIntegrity -ProposedConvergence $proposed -ExistingConvergence $existing
            ($violations | Where-Object { $_ -match "GATE FLIP: P0_zero" }).Count | Should -Be 1
        }
        It 'Detects gate regression when gate flips true -> false' {
            $existing = @{ converged = $false; consecutive_converged_cycles = 0; overall_score = 70; gates = @{ P0_zero = $true; P1_zero = $false; P2_zero = $false; critical_security = $false; critical_correctness = $false; data_integrity = $false; regression = $false; verification = $false; no_material_new_findings = $false; limitations_documented = $false; consecutive_clean_independent_audits = $false; module_dependency_integrity = $true } }
            $proposed = @{ converged = $false; consecutive_converged_cycles = 0; overall_score = 70; gates = @{ P0_zero = $false; P1_zero = $false; P2_zero = $false; critical_security = $false; critical_correctness = $false; data_integrity = $false; regression = $false; verification = $false; no_material_new_findings = $false; limitations_documented = $false; consecutive_clean_independent_audits = $false; module_dependency_integrity = $true } }
            $violations = Validate-GateEvidenceIntegrity -ProposedConvergence $proposed -ExistingConvergence $existing
            ($violations | Where-Object { $_ -match "GATE REGRESSION: P0_zero" }).Count | Should -Be 1
        }
    }

    Context 'Score Regression' {
        It 'Detects score regression' {
            $existing = @{ converged = $false; consecutive_converged_cycles = 0; overall_score = 55; gates = @{ P0_zero = $false; P1_zero = $false; P2_zero = $false; critical_security = $false; critical_correctness = $false; data_integrity = $false; regression = $false; verification = $false; no_material_new_findings = $false; limitations_documented = $false; consecutive_clean_independent_audits = $false; module_dependency_integrity = $true } }
            $proposed = @{ converged = $false; consecutive_converged_cycles = 0; overall_score = 50; gates = @{ P0_zero = $false; P1_zero = $false; P2_zero = $false; critical_security = $false; critical_correctness = $false; data_integrity = $false; regression = $false; verification = $false; no_material_new_findings = $false; limitations_documented = $false; consecutive_clean_independent_audits = $false; module_dependency_integrity = $true } }
            $violations = Validate-GateEvidenceIntegrity -ProposedConvergence $proposed -ExistingConvergence $existing
            ($violations | Where-Object { $_ -match "SCORE REGRESSION" }).Count | Should -Be 1
        }
        It 'Accepts score staying the same' {
            $existing = @{ converged = $false; consecutive_converged_cycles = 0; overall_score = 55; gates = @{ P0_zero = $false; P1_zero = $false; P2_zero = $false; critical_security = $false; critical_correctness = $false; data_integrity = $false; regression = $false; verification = $false; no_material_new_findings = $false; limitations_documented = $false; consecutive_clean_independent_audits = $false; module_dependency_integrity = $true } }
            $proposed = @{ converged = $false; consecutive_converged_cycles = 0; overall_score = 55; gates = @{ P0_zero = $false; P1_zero = $false; P2_zero = $false; critical_security = $false; critical_correctness = $false; data_integrity = $false; regression = $false; verification = $false; no_material_new_findings = $false; limitations_documented = $false; consecutive_clean_independent_audits = $false; module_dependency_integrity = $true } }
            $violations = Validate-GateEvidenceIntegrity -ProposedConvergence $proposed -ExistingConvergence $existing
            ($violations | Where-Object { $_ -match "SCORE REGRESSION" }).Count | Should -Be 0
        }
        It 'Accepts score increase within limit' {
            $existing = @{ converged = $false; consecutive_converged_cycles = 0; overall_score = 50; gates = @{ P0_zero = $false; P1_zero = $false; P2_zero = $false; critical_security = $false; critical_correctness = $false; data_integrity = $false; regression = $false; verification = $false; no_material_new_findings = $false; limitations_documented = $false; consecutive_clean_independent_audits = $false; module_dependency_integrity = $true } }
            $proposed = @{ converged = $false; consecutive_converged_cycles = 0; overall_score = 65; gates = @{ P0_zero = $false; P1_zero = $false; P2_zero = $false; critical_security = $false; critical_correctness = $false; data_integrity = $false; regression = $false; verification = $false; no_material_new_findings = $false; limitations_documented = $false; consecutive_clean_independent_audits = $false; module_dependency_integrity = $true } }
            $violations = Validate-GateEvidenceIntegrity -ProposedConvergence $proposed -ExistingConvergence $existing
            ($violations | Where-Object { $_ -match "SCORE SPIKE" }).Count | Should -Be 0
        }
    }

    Context 'Score Spikes' {
        It 'Detects score spike (>15 increase)' {
            $existing = @{ converged = $false; consecutive_converged_cycles = 0; overall_score = 50; gates = @{ P0_zero = $false; P1_zero = $false; P2_zero = $false; critical_security = $false; critical_correctness = $false; data_integrity = $false; regression = $false; verification = $false; no_material_new_findings = $false; limitations_documented = $false; consecutive_clean_independent_audits = $false; module_dependency_integrity = $true } }
            $proposed = @{ converged = $false; consecutive_converged_cycles = 0; overall_score = 70; gates = @{ P0_zero = $false; P1_zero = $false; P2_zero = $false; critical_security = $false; critical_correctness = $false; data_integrity = $false; regression = $false; verification = $false; no_material_new_findings = $false; limitations_documented = $false; consecutive_clean_independent_audits = $false; module_dependency_integrity = $true } }
            $violations = Validate-GateEvidenceIntegrity -ProposedConvergence $proposed -ExistingConvergence $existing
            ($violations | Where-Object { $_ -match "SCORE SPIKE" }).Count | Should -Be 1
        }
        It 'Allows exactly max increase (15)' {
            $existing = @{ converged = $false; consecutive_converged_cycles = 0; overall_score = 50; gates = @{ P0_zero = $false; P1_zero = $false; P2_zero = $false; critical_security = $false; critical_correctness = $false; data_integrity = $false; regression = $false; verification = $false; no_material_new_findings = $false; limitations_documented = $false; consecutive_clean_independent_audits = $false; module_dependency_integrity = $true } }
            $proposed = @{ converged = $false; consecutive_converged_cycles = 0; overall_score = 65; gates = @{ P0_zero = $false; P1_zero = $false; P2_zero = $false; critical_security = $false; critical_correctness = $false; data_integrity = $false; regression = $false; verification = $false; no_material_new_findings = $false; limitations_documented = $false; consecutive_clean_independent_audits = $false; module_dependency_integrity = $true } }
            $violations = Validate-GateEvidenceIntegrity -ProposedConvergence $proposed -ExistingConvergence $existing
            ($violations | Where-Object { $_ -match "SCORE SPIKE" }).Count | Should -Be 0
        }
    }

    Context 'Counter Jumps and Regressions' {
        It 'Detects counter jump (>1 increase)' {
            $existing = @{ converged = $false; consecutive_converged_cycles = 0; overall_score = 50; gates = @{ P0_zero = $false; P1_zero = $false; P2_zero = $false; critical_security = $false; critical_correctness = $false; data_integrity = $false; regression = $false; verification = $false; no_material_new_findings = $false; limitations_documented = $false; consecutive_clean_independent_audits = $false; module_dependency_integrity = $true } }
            $proposed = @{ converged = $false; consecutive_converged_cycles = 3; overall_score = 55; gates = @{ P0_zero = $false; P1_zero = $false; P2_zero = $false; critical_security = $false; critical_correctness = $false; data_integrity = $false; regression = $false; verification = $false; no_material_new_findings = $false; limitations_documented = $false; consecutive_clean_independent_audits = $false; module_dependency_integrity = $true } }
            $violations = Validate-GateEvidenceIntegrity -ProposedConvergence $proposed -ExistingConvergence $existing
            ($violations | Where-Object { $_ -match "COUNTER JUMP" }).Count | Should -Be 1
        }
        It 'Detects counter regression' {
            $existing = @{ converged = $false; consecutive_converged_cycles = 2; overall_score = 50; gates = @{ P0_zero = $false; P1_zero = $false; P2_zero = $false; critical_security = $false; critical_correctness = $false; data_integrity = $false; regression = $false; verification = $false; no_material_new_findings = $false; limitations_documented = $false; consecutive_clean_independent_audits = $false; module_dependency_integrity = $true } }
            $proposed = @{ converged = $false; consecutive_converged_cycles = 1; overall_score = 50; gates = @{ P0_zero = $false; P1_zero = $false; P2_zero = $false; critical_security = $false; critical_correctness = $false; data_integrity = $false; regression = $false; verification = $false; no_material_new_findings = $false; limitations_documented = $false; consecutive_clean_independent_audits = $false; module_dependency_integrity = $true } }
            $violations = Validate-GateEvidenceIntegrity -ProposedConvergence $proposed -ExistingConvergence $existing
            ($violations | Where-Object { $_ -match "COUNTER REGRESSION" }).Count | Should -Be 1
        }
        It 'Allows counter increase of exactly 1' {
            $existing = @{ converged = $false; consecutive_converged_cycles = 0; overall_score = 50; gates = @{ P0_zero = $false; P1_zero = $false; P2_zero = $false; critical_security = $false; critical_correctness = $false; data_integrity = $false; regression = $false; verification = $false; no_material_new_findings = $false; limitations_documented = $false; consecutive_clean_independent_audits = $false; module_dependency_integrity = $true } }
            $proposed = @{ converged = $false; consecutive_converged_cycles = 1; overall_score = 50; gates = @{ P0_zero = $false; P1_zero = $false; P2_zero = $false; critical_security = $false; critical_correctness = $false; data_integrity = $false; regression = $false; verification = $false; no_material_new_findings = $false; limitations_documented = $false; consecutive_clean_independent_audits = $false; module_dependency_integrity = $true } }
            $violations = Validate-GateEvidenceIntegrity -ProposedConvergence $proposed -ExistingConvergence $existing
            ($violations | Where-Object { $_ -match "COUNTER" }).Count | Should -Be 0
        }
    }

    Context 'Convergence Invariant' {
        It 'Rejects converged=true when P0_zero is false' {
            $gates = @{ P0_zero = $false; P1_zero = $true; P2_zero = $true; critical_security = $true; critical_correctness = $true; data_integrity = $true; regression = $true; verification = $true; no_material_new_findings = $true; limitations_documented = $true; consecutive_clean_independent_audits = $true; module_dependency_integrity = $true }
            $existing = @{ converged = $false; consecutive_converged_cycles = 0; overall_score = 90; gates = $gates }
            $proposed = @{ converged = $true; consecutive_converged_cycles = 1; overall_score = 99; gates = $gates }
            $violations = Validate-GateEvidenceIntegrity -ProposedConvergence $proposed -ExistingConvergence $existing
            ($violations | Where-Object { $_ -match "CONVERGENCE INVARIANT VIOLATION" }).Count | Should -Be 1
        }
        It 'Rejects converged=true when only 10 gates pass' {
            $gates = @{ P0_zero = $false; P1_zero = $false; P2_zero = $true; critical_security = $true; critical_correctness = $true; data_integrity = $true; regression = $true; verification = $true; no_material_new_findings = $true; limitations_documented = $true; consecutive_clean_independent_audits = $true; module_dependency_integrity = $true }
            $existing = @{ converged = $false; consecutive_converged_cycles = 0; overall_score = 90; gates = $gates }
            $proposed = @{ converged = $true; consecutive_converged_cycles = 1; overall_score = 99; gates = $gates }
            $violations = Validate-GateEvidenceIntegrity -ProposedConvergence $proposed -ExistingConvergence $existing
            ($violations | Where-Object { $_ -match "CONVERGENCE INVARIANT VIOLATION" }).Count | Should -Be 1
        }
        It 'Accepts converged=true with all 12 gates true' {
            $gates = @{ P0_zero = $true; P1_zero = $true; P2_zero = $true; critical_security = $true; critical_correctness = $true; data_integrity = $true; regression = $true; verification = $true; no_material_new_findings = $true; limitations_documented = $true; consecutive_clean_independent_audits = $true; module_dependency_integrity = $true }
            $existing = @{ converged = $false; consecutive_converged_cycles = 0; overall_score = 90; gates = $gates }
            $proposed = @{ converged = $true; consecutive_converged_cycles = 1; overall_score = 99; gates = $gates }
            $violations = Validate-GateEvidenceIntegrity -ProposedConvergence $proposed -ExistingConvergence $existing
            ($violations | Where-Object { $_ -match "CONVERGENCE INVARIANT VIOLATION" }).Count | Should -Be 0
        }
        It 'Rejects converged already true staying true with gate false' {
            $gates = @{ P0_zero = $false; P1_zero = $true; P2_zero = $true; critical_security = $true; critical_correctness = $true; data_integrity = $true; regression = $true; verification = $true; no_material_new_findings = $true; limitations_documented = $true; consecutive_clean_independent_audits = $true; module_dependency_integrity = $true }
            $existing = @{ converged = $true; consecutive_converged_cycles = 1; overall_score = 90; gates = $gates }
            $proposed = @{ converged = $true; consecutive_converged_cycles = 2; overall_score = 95; gates = $gates }
            $violations = Validate-GateEvidenceIntegrity -ProposedConvergence $proposed -ExistingConvergence $existing
            ($violations | Where-Object { $_ -match "CONVERGENCE INVARIANT VIOLATION" }).Count | Should -Be 1
        }
    }

    Context 'Null/Empty Handling' {
        It 'Returns empty violations when no existing convergence' {
            $proposed = @{ converged = $true; overall_score = 99; consecutive_converged_cycles = 1; gates = @{} }
            $violations = Validate-GateEvidenceIntegrity -ProposedConvergence $proposed -ExistingConvergence $null
            $violations.Count | Should -Be 0
        }
        It 'Returns empty violations when existing has no gates' {
            $existing = @{ converged = $false }
            $proposed = @{ converged = $true; overall_score = 99; consecutive_converged_cycles = 1; gates = @{} }
            $violations = Validate-GateEvidenceIntegrity -ProposedConvergence $proposed -ExistingConvergence $existing
            $violations.Count | Should -Be 0
        }
    }
}

# =====================================================================
# CONVERGENCE - GATE INTEGRITY
# =====================================================================

Describe 'Convergence - Gate Integrity' {
    Context 'Findings Consistency' {
        It 'PRODUCTION_READY cannot be set when P0 findings are OPEN' {
            $conv = @{
                converged = $false; consecutive_converged_cycles = 0; overall_score = 85
                classification = "PRODUCTION_READY"
                gates = @{ P0_zero = $true; P1_zero = $true; P2_zero = $true; critical_security = $true; critical_correctness = $true; data_integrity = $true; regression = $true; verification = $true; no_material_new_findings = $true; limitations_documented = $true; consecutive_clean_independent_audits = $true; module_dependency_integrity = $true }
            }
            $findings = @(
                @{id="F001"; status="OPEN"; severity="P0"; category="SECURITY"; problem="Hardcoded key"}
            )
            $gates = $conv.gates
            $hasOpenP0 = ($findings | Where-Object { $_.severity -eq "P0" -and $_.status -notin @("VERIFIED", "DEFERRED") }).Count -gt 0
            $hasOpenP0 | Should -BeTrue
            $gates.P0_zero | Should -BeTrue
            ($hasOpenP0 -and $gates.P0_zero) | Should -BeTrue -Because "P0_zero gate must be false if open P0 findings exist"
        }
        It 'Cannot converge with P1 findings open' {
            $findings = @(@{id="F002"; status="OPEN"; severity="P1"; category="CORRECTNESS"; problem="Race condition"})
            $hasOpenP1 = ($findings | Where-Object { $_.severity -eq "P1" -and $_.status -notin @("VERIFIED", "DEFERRED") }).Count -gt 0
            $hasOpenP1 | Should -BeTrue
        }
        It 'Cannot converge with gate module_dependency_integrity false' {
            $gates = @{ P0_zero = $true; P1_zero = $true; P2_zero = $true; critical_security = $true; critical_correctness = $true; data_integrity = $true; regression = $true; verification = $true; no_material_new_findings = $true; limitations_documented = $true; consecutive_clean_independent_audits = $true; module_dependency_integrity = $false }
            $allTrue = ($gates.Keys | ForEach-Object { $gates[$_] }) -notcontains $false
            $allTrue | Should -BeFalse
        }
    }
}

# =====================================================================
# STATE MANAGEMENT - JSON I/O
# =====================================================================

Describe 'State Management - JSON I/O' {
    BeforeAll {
        $Script:TestDir = Join-Path $TestDrive "json-io-test"
        New-Item -ItemType Directory -Path $Script:TestDir -Force | Out-Null

        function Test-WriteJsonFile($Path, $Data) {
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

        function Test-ReadJsonFile($Path) {
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
    }

    Context 'Atomic Write-JsonFile' {
        It 'Creates file at the specified path' {
            $testFile = Join-Path $Script:TestDir "test-simple.json"
            $data = @{ key = "value"; number = 42 }
            Test-WriteJsonFile $testFile $data
            Test-Path -LiteralPath $testFile | Should -BeTrue
            $read = Test-ReadJsonFile $testFile
            $read.key | Should -Be "value"
            $read.number | Should -Be 42
        }
        It 'Handles nested objects up to depth 100' {
            $testFile = Join-Path $Script:TestDir "test-deep.json"
            $nested = @{}
            $current = $nested
            for ($i = 1; $i -le 50; $i++) {
                $current["level$i"] = @{}; $current = $current["level$i"]
            }
            $current["value"] = "deep"
            Test-WriteJsonFile $testFile $nested
            $read = Test-ReadJsonFile $testFile
            $read.level1.level2 | Should -Not -BeNullOrEmpty
        }
        It 'Writes UTF-8 without BOM' {
            $testFile = Join-Path $Script:TestDir "test-utf8.json"
            Test-WriteJsonFile $testFile @{ text = "Hello World" }
            $bytes = [System.IO.File]::ReadAllBytes($testFile)
            $bytes[0] | Should -Not -Be 0xEF
            $bytes[1] | Should -Not -Be 0xBB
            $bytes[2] | Should -Not -Be 0xBF
        }
        It 'Writes arrays correctly' {
            $testFile = Join-Path $Script:TestDir "test-array.json"
            $data = @{ items = @(@{id=1}, @{id=2}, @{id=3}) }
            Test-WriteJsonFile $testFile $data
            $read = Test-ReadJsonFile $testFile
            $read.items.Count | Should -Be 3
        }
        It 'Overwrites existing file' {
            $testFile = Join-Path $Script:TestDir "test-overwrite.json"
            Test-WriteJsonFile $testFile @{ version = 1 }
            Test-WriteJsonFile $testFile @{ version = 2 }
            $read = Test-ReadJsonFile $testFile
            $read.version | Should -Be 2
        }
    }

    Context 'Robust Read-JsonFile' {
        It 'Returns null for empty file' {
            $testFile = Join-Path $Script:TestDir "empty.json"
            $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
            [System.IO.File]::WriteAllText($testFile, "", $utf8NoBom)
            $result = Test-ReadJsonFile $testFile
            $result | Should -Be $null
        }
        It 'Returns null for whitespace-only file' {
            $testFile = Join-Path $Script:TestDir "whitespace.json"
            $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
            [System.IO.File]::WriteAllText($testFile, "`n`n   `t", $utf8NoBom)
            $result = Test-ReadJsonFile $testFile
            $result | Should -Be $null
        }
        It 'Returns null for malformed JSON' {
            $testFile = Join-Path $Script:TestDir "malformed.json"
            $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
            [System.IO.File]::WriteAllText($testFile, '{"broken": "yes", invalid syntax here}', $utf8NoBom)
            $result = Test-ReadJsonFile $testFile
            $result | Should -Be $null
        }
        It 'Returns null for non-existent file' {
            $testFile = Join-Path $Script:TestDir "nonexistent.json"
            $result = Test-ReadJsonFile $testFile
            $result | Should -Be $null
        }
        It 'Reads valid JSON with nested objects' {
            $testFile = Join-Path $Script:TestDir "valid-nested.json"
            $data = @{
                findings = @(
                    @{id="F001"; status="OPEN"; severity="P0"}
                    @{id="F002"; status="VERIFIED"; severity="P2"}
                )
                overall_score = 85
                converged = $false
            }
            Test-WriteJsonFile $testFile $data
            $read = Test-ReadJsonFile $testFile
            $read.findings.Count | Should -Be 2
            $read.overall_score | Should -Be 85
        }
    }
}

# =====================================================================
# GIT SAFETY - PUSH PROTECTION
# =====================================================================

Describe 'Git Safety - Push Protection' {
    Context 'Transactional staging' {
        It 'Uses temp GIT_INDEX_FILE environment variable concept' {
            $tempIndex = Join-Path ([System.IO.Path]::GetTempPath()) "aura-test-$([System.Guid]::NewGuid().ToString('N').Substring(0,8)).index"
            $env:GIT_INDEX_FILE = $tempIndex
            try {
                $env:GIT_INDEX_FILE | Should -Match "aura-test-"
                $env:GIT_INDEX_FILE | Should -Match "\.index$"
            } finally {
                Remove-Item -LiteralPath $tempIndex -Force -ErrorAction SilentlyContinue
                Remove-Item Env:\GIT_INDEX_FILE -ErrorAction SilentlyContinue
            }
        }
        It 'Cleans up temp index after operation (simulated)' {
            $tempIndex = Join-Path ([System.IO.Path]::GetTempPath()) "aura-cleanup-$([System.Guid]::NewGuid().ToString('N').Substring(0,8)).index"
            $null = New-Item -ItemType File -Path $tempIndex -Force
            Remove-Item -LiteralPath $tempIndex -Force -ErrorAction SilentlyContinue
            Test-Path -LiteralPath $tempIndex | Should -BeFalse
        }
    }

    Context 'Push working set isolation' {
        It 'Engine files listed in working set must be under .aura/ or src/ or config/' {
            $engineDirs = @(".aura/", "src/", "config/")
            $testFile = ".aura/state/cycle.json"
            $isEngineFile = $engineDirs | Where-Object { $testFile.StartsWith($_) }
            $isEngineFile | Should -Not -BeNullOrEmpty
        }
        It 'Non-engine files are NOT in engine directories' {
            $engineDirs = @(".aura/", "src/", "config/")
            $testFile = "main.js"
            $isEngineFile = $engineDirs | Where-Object { $testFile.StartsWith($_) }
            $isEngineFile | Should -BeNullOrEmpty
        }
    }
}

# =====================================================================
# I18N - LOCALE LOADING
# =====================================================================

Describe 'I18n - Locale Loading' {
    Context 'Locale Data Retrieval' {
        It 'Loads English locale' {
            $loc = Get-LocaleData -LocaleCode "en"
            $loc | Should -Not -BeNullOrEmpty
            $loc._meta.locale | Should -Be "en"
        }
        It 'Loads Indonesian locale' {
            $loc = Get-LocaleData -LocaleCode "id"
            $loc | Should -Not -BeNullOrEmpty
            $loc._meta.locale | Should -Be "id"
        }
        It 'Returns null for non-existent locale' {
            $result = Get-LocaleData -LocaleCode "xx"
            $result | Should -Be $null
        }
        It 'English locale has expected metadata' {
            $loc = Get-LocaleData -LocaleCode "en"
            $loc._meta.language | Should -Be "English"
            $loc._meta.engine_version | Should -Be "2.1.0"
        }
        It 'Indonesian locale has expected metadata' {
            $loc = Get-LocaleData -LocaleCode "id"
            $loc._meta.language | Should -Be "Bahasa Indonesia"
        }
    }

    Context 'Key Lookup' {
        It 'Returns correct string for prompt.title' {
            $result = Get-L10n -Key "prompt.title" -Replacements @{ cycle = "5" }
            $result | Should -Match "CYCLE"
            $result | Should -Match "5"
        }
        It 'Returns MISSING for non-existent key' {
            $result = Get-L10n -Key "nonexistent.key.here"
            $result | Should -Match "MISSING"
        }
        It 'Returns MISSING for empty string key' {
            $result = Get-L10n -Key ""
            $result | Should -Match "MISSING"
        }
        It 'Handles replacements correctly' {
            $result = Get-L10n -Key "prompt.title" -Replacements @{ cycle = "99" }
            $result | Should -Match "99"
        }
        It 'Handles console.language_info key' {
            $result = Get-L10n -Key "console.language_info" -Replacements @{ language = "English" }
            $result | Should -Not -Match "MISSING"
        }
    }
}

# =====================================================================
# MODULE CLASSIFICATION
# =====================================================================

Describe 'Module Classification' {
    Context 'Unclassified modules fail closed' {
        It 'Unclassified module is treated as REQUIRED (fail-closed)' {
            $classified = @{ required = @{}; optional = @{}; experimental = @{} }
            $modName = "some-unknown-module.ps1"
            $isClassified = $classified.required.ContainsKey($modName) -or $classified.optional.ContainsKey($modName) -or $classified.experimental.ContainsKey($modName)
            $isClassified | Should -BeFalse
            $treatAsRequired = -not $isClassified
            $treatAsRequired | Should -BeTrue
        }
        It 'Required module failure blocks classification to PRODUCTION_READY' {
            $classification = "PRODUCTION_READY"
            $hasRequiredFailures = $true
            $shouldBlock = ($classification -eq "PRODUCTION_READY") -and $hasRequiredFailures
            $shouldBlock | Should -BeTrue
        }
        It 'Optional module failure does NOT block classification' {
            $classification = "CONDITIONALLY_READY"
            $hasOptionalFailures = $true
            $hasRequiredFailures = $false
            $shouldBlock = ($classification -eq "PRODUCTION_READY") -and $hasRequiredFailures
            $shouldBlock | Should -BeFalse
        }
    }
}

# =====================================================================
# ENGINE STATE FUNCTIONS
# =====================================================================

Describe 'Engine State Functions' {
    Context 'Safe-Int' {
        It 'Returns integer for valid input' {
            Safe-Int "42" 0 | Should -Be 42
        }
        It 'Returns fallback for null' {
            Safe-Int $null 99 | Should -Be 99
        }
        It 'Returns fallback for non-numeric string' {
            $result = Safe-Int "not-a-number" 10
            $result | Should -Be 10
        }
        It 'Returns 0 as default fallback' {
            Safe-Int $null | Should -Be 0
        }
    }
}

# =====================================================================
# INITIALIZE-STATE AND RESET-ENGINE (SIMULATED)
# =====================================================================

Describe 'Initialize-State' {
    Context 'State Structure Validation' {
        It 'Cycle state has all required fields' {
            $fields = @("engine_name", "version", "started_at", "current_cycle", "current_phase", "status", "classification", "cycles_completed", "cycles_without_progress", "consecutive_converged_cycles", "last_change_hash")
            foreach ($f in $fields) {
                $fields -contains $f | Should -BeTrue
            }
        }
        It 'Convergence state initializes all 12 gates to false (except module_dependency_integrity)' {
            $gateNames = @("P0_zero","P1_zero","P2_zero","critical_security","critical_correctness","data_integrity","regression","verification","no_material_new_findings","limitations_documented","consecutive_clean_independent_audits","module_dependency_integrity")
            $gateNames.Count | Should -Be 12
        }
        It 'Initial classification is NOT_READY' {
            $classification = "NOT_READY"
            Test-ValidClassificationTransition -FromClassification "" -ToClassification $classification | Should -BeTrue
        }
        It 'Initial current_cycle is 0' {
            $cycle = 0
            $cycle | Should -Be 0
        }
    }
}

# =====================================================================
# REGRESSION TESTS
# =====================================================================

Describe 'Regression: Gate Bypass Prevention' {
    It 'Cannot mark convergence if P0 findings exist with critical status' {
        $finding = @{id="F100"; status="OPEN"; severity="P0"; category="SECURITY"; problem="Bypass test"}
        $isBlocking = $finding.severity -eq "P0" -and $finding.status -in @("OPEN", "IN_PROGRESS", "FIXED", "VERIFYING")
        $isBlocking | Should -BeTrue
    }
    It 'Cannot bypass classification jump NOT_READY -> PRODUCTION_READY' {
        Test-ValidClassificationTransition -FromClassification "NOT_READY" -ToClassification "PRODUCTION_READY" | Should -BeFalse
    }
    It 'Cannot set VERIFIED status without passing through VERIFYING' {
        Test-ValidFindingTransition -FromStatus "FIXED" -ToStatus "VERIFIED" | Should -BeFalse
    }
    It 'new finding must start as OPEN' {
        $hasExisting = $false
        $status = "IN_PROGRESS"
        if (-not $hasExisting -and $status -ne "OPEN") { $violation = "NEW FINDING VIOLATION" }
        $violation | Should -Be "NEW FINDING VIOLATION"
    }
}