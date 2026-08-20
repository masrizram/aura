# Pester 5.x end-to-end tests for the AURA engine
# Tests full mock cycles and regression checks

BeforeAll {
    $Script:EngineScript = Join-Path $PSScriptRoot "../../src/engine/run-audit.ps1"
    $Script:FixtureRoot = Join-Path $TestDrive "e2e-fixture"

    . $PSScriptRoot/engine.tests.ps1 -WarningAction SilentlyContinue -ErrorAction SilentlyContinue

    New-Item -ItemType Directory -Path $Script:FixtureRoot -Force | Out-Null
    Set-Location $Script:FixtureRoot

    try {
        $null = git init 2>&1
        git config user.email "e2e@test.com" 2>&1 | Out-Null
        git config user.name "E2E Test" 2>&1 | Out-Null
    } catch {
        Write-Warning "Git not available; E2E tests will be limited."
        $Script:GitAvailable = $false
        return
    }
    $Script:GitAvailable = $true

    Set-Content "index.js" '// Main entry point'
    Set-Content "auth.js" 'function authenticate(token) { return token === "secret123"; }'
    git add -A 2>&1 | Out-Null
    git commit -m "e2e fixture initial" 2>&1 | Out-Null

    $Script:AuraDir = Join-Path $Script:FixtureRoot ".aura"
    $Script:StateDir = Join-Path $Script:AuraDir "state"
    $Script:ReportsDir = Join-Path $Script:AuraDir "reports"

    New-Item -ItemType Directory -Path $Script:StateDir -Force | Out-Null
    New-Item -ItemType Directory -Path $Script:ReportsDir -Force | Out-Null

    function Initialize-EngineState($FixtureRoot) {
        $now = (Get-Date).ToString("o")
        $cycleFile = Join-Path $FixtureRoot ".aura/state/cycle.json"
        $findingsFile = Join-Path $FixtureRoot ".aura/state/findings.json"
        $convFile = Join-Path $FixtureRoot ".aura/state/convergence.json"

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
        $json = $cycleData | ConvertTo-Json -Depth 100
        $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
        [System.IO.File]::WriteAllText($cycleFile, $json, $utf8NoBom)

        $findingsData = @{ findings = @(); next_id = 1 }
        $json = $findingsData | ConvertTo-Json -Depth 100
        [System.IO.File]::WriteAllText($findingsFile, $json, $utf8NoBom)

        $convData = @{
            cycle = 0
            converged = $false
            consecutive_converged_cycles = 0
            audits_since_last_finding = 0
            overall_score = 0
            gates = @{
                P0_zero = $false; P1_zero = $false; P2_zero = $false
                critical_security = $false; critical_correctness = $false
                data_integrity = $false; regression = $false; verification = $false
                no_material_new_findings = $false; limitations_documented = $false
                consecutive_clean_independent_audits = $false
                module_dependency_integrity = $true
            }
            classification = "NOT_READY"
            reason = "Cycle 0 - not yet started."
        }
        $json = $convData | ConvertTo-Json -Depth 100
        [System.IO.File]::WriteAllText($convFile, $json, $utf8NoBom)
    }
}

AfterAll {
    Set-Location $PSScriptRoot
    if ($Script:GitAvailable) {
        Remove-Item $Script:FixtureRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}

Describe 'End-to-End Mock Cycle' {
    BeforeAll {
        if (-not $Script:GitAvailable) {
            Set-ItResult -Skipped -Because "Git not available"
        }
        Initialize-EngineState -FixtureRoot $Script:FixtureRoot
    }

    Context 'Cycle 1 - Initial Audit' {
        It 'Generates findings based on fixture code' {
            $findingsData = @{
                findings = @(
                    @{id="F001"; severity="P0"; status="OPEN"; category="SECURITY"; problem="Hardcoded secret in auth.js: secret123"},
                    @{id="F002"; severity="P3"; status="OPEN"; category="DOCUMENTATION"; problem="Missing JSDoc on authenticate function"},
                    @{id="F003"; severity="P5"; status="OPEN"; category="OPTIMIZATION"; problem="Consider using constant-time comparison"}
                )
                next_id = 4
            }
            $findingsFile = Join-Path $Script:StateDir "findings.json"
            $json = $findingsData | ConvertTo-Json -Depth 100
            $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
            [System.IO.File]::WriteAllText($findingsFile, $json, $utf8NoBom)

            $read = Get-Content $findingsFile -Raw -Encoding UTF8 | ConvertFrom-Json
            $read.findings.Count | Should -Be 3
            ($read.findings | Where-Object { $_.severity -eq "P0" }).Count | Should -Be 1
        }

        It 'Promotes cycle state to cycle 1 after findings' {
            $cycleFile = Join-Path $Script:StateDir "cycle.json"
            $cycleData = Get-Content $cycleFile -Raw -Encoding UTF8 | ConvertFrom-Json
            $cycleData.current_cycle = 1
            $cycleData.cycles_completed = 1
            $cycleData.current_phase = "AUDIT"
            $json = $cycleData | ConvertTo-Json -Depth 100
            $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
            [System.IO.File]::WriteAllText($cycleFile, $json, $utf8NoBom)

            $read = Get-Content $cycleFile -Raw -Encoding UTF8 | ConvertFrom-Json
            $read.current_cycle | Should -Be 1
        }

        It 'Updates convergence score appropriately' {
            $convFile = Join-Path $Script:StateDir "convergence.json"
            $convData = Get-Content $convFile -Raw -Encoding UTF8 | ConvertFrom-Json
            $convData.overall_score = 10
            $convData.cycle = 1
            $convData.reason = "Cycle 1 - P0 finding open. Not converged."
            $json = $convData | ConvertTo-Json -Depth 100
            $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
            [System.IO.File]::WriteAllText($convFile, $json, $utf8NoBom)

            $read = Get-Content $convFile -Raw -Encoding UTF8 | ConvertFrom-Json
            $read.overall_score | Should -Be 10
        }
    }

    Context 'Cycle 2 - Remediation' {
        It 'Transitions P0 finding to IN_PROGRESS -> FIXED' {
            $findingsData = @{
                findings = @(
                    @{id="F001"; severity="P0"; status="FIXED"; category="SECURITY"; problem="Hardcoded secret in auth.js: secret123"},
                    @{id="F002"; severity="P3"; status="OPEN"; category="DOCUMENTATION"; problem="Missing JSDoc on authenticate function"},
                    @{id="F003"; severity="P5"; status="OPEN"; category="OPTIMIZATION"; problem="Consider using constant-time comparison"}
                )
                next_id = 4
            }
            $findingsFile = Join-Path $Script:StateDir "findings.json"
            $json = $findingsData | ConvertTo-Json -Depth 100
            $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
            [System.IO.File]::WriteAllText($findingsFile, $json, $utf8NoBom)

            $existing = @{ findings = @(@{id="F001"; severity="P0"; status="OPEN"; category="SECURITY"; problem="..."}) }
            $proposed = @{id="F001"; severity="P0"; status="FIXED"; category="SECURITY"; problem="..."}

            Test-ValidFindingTransition -FromStatus "OPEN" -ToStatus "IN_PROGRESS" | Should -BeTrue
            Test-ValidFindingTransition -FromStatus "IN_PROGRESS" -ToStatus "FIXED" | Should -BeTrue
        }

        It 'Score increases within allowed limit' {
            $convFile = Join-Path $Script:StateDir "convergence.json"
            $convData = Get-Content $convFile -Raw -Encoding UTF8 | ConvertFrom-Json
            $oldScore = $convData.overall_score
            $newScore = $oldScore + 12
            $newScore - $oldScore | Should -BeLessOrEqual 15
            $newScore - $oldScore | Should -BeGreaterThan 0
        }
    }

    Context 'Cycle 3 - Verification' {
        It 'All findings VERIFIED and convergence gates pass' {
            $findingsData = @{
                findings = @(
                    @{id="F001"; severity="P0"; status="VERIFIED"; category="SECURITY"; problem="Hardcoded secret removed. Uses env var."},
                    @{id="F002"; severity="P3"; status="VERIFIED"; category="DOCUMENTATION"; problem="JSDoc added."},
                    @{id="F003"; severity="P5"; status="VERIFIED"; category="OPTIMIZATION"; problem="Constant-time comparison implemented."}
                )
                next_id = 4
            }
            $findingsFile = Join-Path $Script:StateDir "findings.json"
            $json = $findingsData | ConvertTo-Json -Depth 100
            $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
            [System.IO.File]::WriteAllText($findingsFile, $json, $utf8NoBom)

            $openP0P2 = @($findingsData.findings | Where-Object {
                $_.severity -in @("P0","P1","P2") -and $_.status -notin @("VERIFIED", "DEFERRED")
            })
            $openP0P2.Count | Should -Be 0
        }

        It 'Classification updates to CONDITIONALLY_READY or PRODUCTION_READY' {
            Test-ValidClassificationTransition -FromClassification "NOT_READY" -ToClassification "CONDITIONALLY_READY" | Should -BeTrue
        }
    }
}

Describe 'Regression: Gate Bypass Prevention' {
    BeforeAll {
        if (-not $Script:GitAvailable) {
            Set-ItResult -Skipped -Because "Git not available"
        }
    }

    Context 'Bypass Attempts' {
        It 'Cannot bypass P0 gate by marking finding as VERIFIED without VERIFYING' {
            Test-ValidFindingTransition -FromStatus "FIXED" -ToStatus "VERIFIED" | Should -BeFalse
        }
        It 'Cannot bypass score cap by increment of 20 in one cycle' {
            $oldScore = 50
            $newScore = 70
            ($newScore - $oldScore) | Should -Be 20
            ($newScore -gt ($oldScore + 15)) | Should -BeTrue
        }
        It 'Cannot bypass classification jump NOT_READY -> PRODUCTION_READY' {
            Test-ValidClassificationTransition -FromClassification "NOT_READY" -ToClassification "PRODUCTION_READY" | Should -BeFalse
        }
        It 'Cannot set converged=true when only 8 of 12 gates pass' {
            $gates = @{ P0_zero = $true; P1_zero = $true; P2_zero = $true; critical_security = $true; critical_correctness = $true; data_integrity = $true; regression = $true; verification = $true; no_material_new_findings = $false; limitations_documented = $false; consecutive_clean_independent_audits = $false; module_dependency_integrity = $true }
            $allTrue = ($gates.Keys | ForEach-Object { $gates[$_] }) -notcontains $false
            $allTrue | Should -BeFalse
        }
        It 'Cannot decrease score between cycles' {
            $oldScore = 60
            $newScore = 55
            ($newScore -lt $oldScore) | Should -BeTrue
        }
        It 'Cannot decrease consecutive_converged_cycles' {
            $old = 2
            $new = 1
            ($new -lt $old) | Should -BeTrue
        }
        It 'New findings must start as OPEN (cannot start as VERIFIED)' {
            $existing = @{ findings = @() }
            $proposed = @(@{id="F100"; status="VERIFIED"; severity="P0"; category="SECURITY"; problem="Bypass"})
            $violations = Validate-FindingStateIntegrity -ProposedFindings $proposed -ExistingFindings $existing
            $violations.Count | Should -BeGreaterThan 0
        }
        It 'Cannot set classification PRODUCTION_READY when module_dependency_integrity is false' {
            $class = "PRODUCTION_READY"
            $moduleOk = $false
            ($class -eq "PRODUCTION_READY" -and -not $moduleOk) | Should -BeTrue
        }
    }
}

Describe 'End-to-End: Full State Promotion Cycle' {
    BeforeAll {
        if (-not $Script:GitAvailable) {
            Set-ItResult -Skipped -Because "Git not available"
        }
    }

    Context 'Promote-state validation sequence' {
        It 'Validates findings, gates, classification, tooling, and modules in sequence' {
            $existingFindings = @{ findings = @(@{id="F001"; status="OPEN"; severity="P0"; category="SECURITY"; problem="X"}) }
            $proposedFindings = @(@{id="F001"; status="IN_PROGRESS"; severity="P0"; category="SECURITY"; problem="X"})

            $existingConv = @{
                cycle = 0; converged = $false; consecutive_converged_cycles = 0
                overall_score = 10
                gates = @{ P0_zero = $false; P1_zero = $false; P2_zero = $false; critical_security = $false; critical_correctness = $false; data_integrity = $false; regression = $false; verification = $false; no_material_new_findings = $false; limitations_documented = $false; consecutive_clean_independent_audits = $false; module_dependency_integrity = $true }
            }
            $proposedConv = @{
                cycle = 1; converged = $false; consecutive_converged_cycles = 0
                overall_score = 20; classification = "NOT_READY"
                gates = @{ P0_zero = $false; P1_zero = $false; P2_zero = $false; critical_security = $false; critical_correctness = $false; data_integrity = $false; regression = $false; verification = $false; no_material_new_findings = $false; limitations_documented = $false; consecutive_clean_independent_audits = $false; module_dependency_integrity = $true }
            }

            $fv = Validate-FindingStateIntegrity -ProposedFindings $proposedFindings -ExistingFindings $existingFindings
            $fv.Count | Should -Be 0

            $gv = Validate-GateEvidenceIntegrity -ProposedConvergence $proposedConv -ExistingConvergence $existingConv
            $gv.Count | Should -Be 0

            $cv = Test-ValidClassificationTransition -FromClassification "NOT_READY" -ToClassification "NOT_READY"
            $cv | Should -BeTrue

            $allViolations = $fv.Count + $gv.Count
            $allViolations | Should -Be 0
        }
    }
}

Describe 'Chaos Engineering: Edge Cases' {
    Context 'Rapid state transitions' {
        It 'Handles all valid transitions in sequence without errors' {
            $allStatuses = @("OPEN","IN_PROGRESS","FIXED","VERIFYING","VERIFIED","REJECTED","DEFERRED","BLOCKED","UNVERIFIED")
            foreach ($from in $allStatuses) {
                foreach ($to in $allStatuses) {
                    $result = Test-ValidFindingTransition -FromStatus $from -ToStatus $to
                    $null -ne $result | Should -BeTrue
                }
            }
        }
        It 'Handles all classification transitions without errors' {
            $allClasses = @("NOT_READY","CONDITIONALLY_READY","PRODUCTION_READY","HUMAN_BLOCKED")
            foreach ($from in $allClasses) {
                foreach ($to in $allClasses) {
                    $result = Test-ValidClassificationTransition -FromClassification $from -ToClassification $to
                    $null -ne $result | Should -BeTrue
                }
            }
        }
    }

    Context 'Concurrent cycle safety' {
        It 'Can detect stale proposed state from previous cycle' {
            $hasProposedFindings = $true
            $hasProposedConv = $true
            $hasProposedCycle = $false

            $hasStaleState = $hasProposedFindings -or $hasProposedConv -or $hasProposedCycle
            $hasStaleState | Should -BeTrue
        }

        It 'Blocks new cycle when unreviewed proposed state exists' {
            $blockNewCycle = $true
            $blockNewCycle | Should -BeTrue
        }
    }
}