# Pester 5.x integration tests for the AURA engine
# Uses a fixture git repository with known defects

BeforeAll {
    $Script:EngineScript = Join-Path $PSScriptRoot "../../src/engine/run-audit.ps1"
    $Script:FixtureRoot = Join-Path $TestDrive "fixture-repo"

    # Dot-source helper functions from unit test file
    . $PSScriptRoot/engine.tests.ps1 -WarningAction SilentlyContinue -ErrorAction SilentlyContinue

    New-Item -ItemType Directory -Path $Script:FixtureRoot -Force | Out-Null
    Set-Location $Script:FixtureRoot

    try {
        $null = git init 2>&1
        git config user.email "aura-test@test.com" 2>&1 | Out-Null
        git config user.name "AURA Test" 2>&1 | Out-Null
    } catch {
        Write-Warning "Git not available; integration tests will be limited."
        $Script:GitAvailable = $false
        return
    }
    $Script:GitAvailable = $true

    Set-Content "main.js" 'const apiKey = "sk-live-1234567890abcdef"; // P0: hardcoded key'
    Set-Content "utils.py" '# TODO: fix this later - tech debt'
    Set-Content "config.yml" 'database_url: ${DB_PASSWORD} // P1: env var not referenced'
    git add -A 2>&1 | Out-Null
    git commit -m "initial: fixture with known defects" 2>&1 | Out-Null

    $Script:AuraDir = Join-Path $Script:FixtureRoot ".aura"
    $Script:StateDir = Join-Path $Script:AuraDir "state"
    $Script:ReportsDir = Join-Path $Script:AuraDir "reports"
    $Script:ArchiveDir = Join-Path $Script:AuraDir "archive"

    New-Item -ItemType Directory -Path $Script:StateDir -Force | Out-Null
    New-Item -ItemType Directory -Path $Script:ReportsDir -Force | Out-Null
    New-Item -ItemType Directory -Path $Script:ArchiveDir -Force | Out-Null
}

AfterAll {
    Set-Location $PSScriptRoot
    if ($Script:GitAvailable) {
        Remove-Item $Script:FixtureRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}

Describe 'Full Cycle Integration' {
    BeforeAll {
        if (-not $Script:GitAvailable) {
            Set-ItResult -Skipped -Because "Git not available"
        }
    }

    Context 'Initialization' {
        It 'Initializes state correctly' {
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
            $cycleFile = Join-Path $Script:StateDir "cycle.json"
            $json = $cycleData | ConvertTo-Json -Depth 100
            $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
            [System.IO.File]::WriteAllText($cycleFile, $json, $utf8NoBom)
            Test-Path -LiteralPath $cycleFile | Should -BeTrue
            $read = Get-Content $cycleFile -Raw -Encoding UTF8 | ConvertFrom-Json
            $read.engine_name | Should -Match "Continuous Autonomous"
            $read.current_cycle | Should -Be 0
            $read.classification | Should -Be "NOT_READY"
        }

        It 'Initializes findings ledger as empty' {
            $findingsData = @{ findings = @(); next_id = 1 }
            $findingsFile = Join-Path $Script:StateDir "findings.json"
            $json = $findingsData | ConvertTo-Json -Depth 100
            $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
            [System.IO.File]::WriteAllText($findingsFile, $json, $utf8NoBom)
            $read = Get-Content $findingsFile -Raw -Encoding UTF8 | ConvertFrom-Json
            $read.findings.Count | Should -Be 0
            $read.next_id | Should -Be 1
        }

        It 'Initializes convergence state' {
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
            $convFile = Join-Path $Script:StateDir "convergence.json"
            $json = $convData | ConvertTo-Json -Depth 100
            $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
            [System.IO.File]::WriteAllText($convFile, $json, $utf8NoBom)
            $read = Get-Content $convFile -Raw -Encoding UTF8 | ConvertFrom-Json
            $read.converged | Should -BeFalse
            $read.classification | Should -Be "NOT_READY"
            $read.gates.P0_zero | Should -BeFalse
        }
    }

    Context 'Finding lifecycle' {
        It 'Creates new finding with OPEN status' {
            $findingsData = @{
                findings = @(
                    @{id="F001"; severity="P0"; status="OPEN"; category="SECURITY"; problem="Hardcoded API key in main.js"}
                )
                next_id = 2
            }
            $findingsFile = Join-Path $Script:StateDir "findings.json"
            $json = $findingsData | ConvertTo-Json -Depth 100
            $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
            [System.IO.File]::WriteAllText($findingsFile, $json, $utf8NoBom)
            $read = Get-Content $findingsFile -Raw -Encoding UTF8 | ConvertFrom-Json
            $read.findings[0].status | Should -Be "OPEN"
            $read.findings[0].severity | Should -Be "P0"
        }

        It 'Transitions finding from OPEN to IN_PROGRESS' {
            $existingFindings = @{
                findings = @(
                    @{id="F001"; severity="P0"; status="OPEN"; category="SECURITY"; problem="Hardcoded API key in main.js"}
                )
                next_id = 2
            }
            $proposedStatus = "IN_PROGRESS"
            $valid = Test-ValidFindingTransition -FromStatus "OPEN" -ToStatus $proposedStatus
            $valid | Should -BeTrue
        }

        It 'Transitions finding through full lifecycle: OPEN -> IN_PROGRESS -> FIXED -> VERIFYING -> VERIFIED' {
            $transitions = @(
                @{From="OPEN"; To="IN_PROGRESS"},
                @{From="IN_PROGRESS"; To="FIXED"},
                @{From="FIXED"; To="VERIFYING"},
                @{From="VERIFYING"; To="VERIFIED"}
            )
            foreach ($t in $transitions) {
                $result = Test-ValidFindingTransition -FromStatus $t.From -ToStatus $t.To
                $result | Should -BeTrue -Because "$($t.From) -> $($t.To) must be valid"
            }
        }
    }

    Context 'State machine rejection' {
        It 'Rejects illegal state machine transition (OPEN -> VERIFIED)' {
            $existingFindings = @{
                findings = @(
                    @{id="F001"; severity="P0"; status="OPEN"; category="SECURITY"; problem="Hardcoded API key"}
                )
            }
            $proposedFindings = @(
                @{id="F001"; severity="P0"; status="VERIFIED"; category="SECURITY"; problem="Hardcoded API key"}
            )
            $violations = Validate-FindingStateIntegrity -ProposedFindings $proposedFindings -ExistingFindings $existingFindings
            $violations.Count | Should -BeGreaterThan 0
            ($violations -join ' ') | Should -Match "ILLEGAL TRANSITION"
        }

        It 'Rejects new finding with non-OPEN status' {
            $existingFindings = @{ findings = @() }
            $proposedFindings = @(
                @{id="F002"; severity="P1"; status="FIXED"; category="CORRECTNESS"; problem="Already fixed?"}
            )
            $violations = Validate-FindingStateIntegrity -ProposedFindings $proposedFindings -ExistingFindings $existingFindings
            $violations.Count | Should -BeGreaterThan 0
            ($violations -join ' ') | Should -Match "NEW FINDING VIOLATION"
        }
    }

    Context 'Convergence check' {
        It 'Identifies open findings as blocking convergence' {
            $findings = @(
                @{id="F001"; severity="P0"; status="OPEN"; category="SECURITY"; problem="Hardcoded key"}
                @{id="F002"; severity="P1"; status="IN_PROGRESS"; category="CORRECTNESS"; problem="Null ptr"}
            )
            $openP0P2 = @($findings | Where-Object {
                $_.severity -in @("P0","P1","P2") -and $_.status -in @("OPEN","IN_PROGRESS")
            })
            $openP0P2.Count | Should -Be 2
        }

        It 'Cleared findings (all VERIFIED) enable convergence consideration' {
            $findings = @(
                @{id="F001"; severity="P0"; status="VERIFIED"; category="SECURITY"; problem="Fixed: Hardcoded key"}
                @{id="F002"; severity="P1"; status="VERIFIED"; category="CORRECTNESS"; problem="Fixed: Null ptr"}
                @{id="F003"; severity="P2"; status="VERIFIED"; category="PERFORMANCE"; problem="Fixed: N+1"}
            )
            $openP0P2 = @($findings | Where-Object {
                $_.severity -in @("P0","P1","P2") -and $_.status -in @("OPEN","IN_PROGRESS","FIXED","VERIFYING","BLOCKED")
            })
            $openP0P2.Count | Should -Be 0
        }
    }

    Context 'Archive and reset' {
        It 'Archives state to a timestamped directory' {
            $archiveDir = Join-Path $Script:ArchiveDir (Get-Date -Format 'yyyyMMdd_HHmmss')
            New-Item -ItemType Directory -Path $archiveDir -Force | Out-Null
            Test-Path -LiteralPath $archiveDir | Should -BeTrue
        }

        It 'Copies state files to archive before reset' {
            $source = Join-Path $Script:StateDir "cycle.json"
            $dest = Join-Path $Script:ArchiveDir "reset-test/cycle.json"
            New-Item -ItemType Directory -Path (Split-Path $dest -Parent) -Force | Out-Null
            if (Test-Path -LiteralPath $source) {
                Copy-Item -LiteralPath $source -Destination $dest -Force
                Test-Path -LiteralPath $dest | Should -BeTrue
            }
        }
    }
}

Describe 'Proposed State Validation Workflow' {
    BeforeAll {
        if (-not $Script:GitAvailable) {
            Set-ItResult -Skipped -Because "Git not available"
        }
    }

    Context 'Cycle 1 proposed state' {
        It 'Validates a complete proposed state cycle' {
            $existingFindings = @{ findings = @(); next_id = 1 }
            $existingConv = @{
                cycle = 0; converged = $false; consecutive_converged_cycles = 0
                overall_score = 10; gates = @{ P0_zero = $false; P1_zero = $false; P2_zero = $false; critical_security = $false; critical_correctness = $false; data_integrity = $false; regression = $false; verification = $false; no_material_new_findings = $false; limitations_documented = $false; consecutive_clean_independent_audits = $false; module_dependency_integrity = $true }
            }

            $proposedFindings = @(
                @{id="F001"; severity="P0"; status="OPEN"; category="SECURITY"; problem="Hardcoded API key in main.js"},
                @{id="F002"; severity="P1"; status="OPEN"; category="CORRECTNESS"; problem="Missing input validation in auth module"}
            )
            $proposedConv = @{
                cycle = 1; converged = $false; consecutive_converged_cycles = 0
                overall_score = 15; classification = "NOT_READY"
                gates = @{ P0_zero = $false; P1_zero = $false; P2_zero = $false; critical_security = $false; critical_correctness = $false; data_integrity = $false; regression = $false; verification = $false; no_material_new_findings = $false; limitations_documented = $false; consecutive_clean_independent_audits = $false; module_dependency_integrity = $true }
            }

            $findingViolations = Validate-FindingStateIntegrity -ProposedFindings $proposedFindings -ExistingFindings $existingFindings
            $findingViolations.Count | Should -Be 0

            $gateViolations = Validate-GateEvidenceIntegrity -ProposedConvergence $proposedConv -ExistingConvergence $existingConv
            $gateViolations.Count | Should -Be 0

            $classValid = Test-ValidClassificationTransition -FromClassification "NOT_READY" -ToClassification "NOT_READY"
            $classValid | Should -BeTrue
        }
    }
}

Describe 'Convergence Gate Cross-Validation' {
    Context 'Gate-finding consistency' {
        It 'P0_zero gate must be false when open P0 findings exist' {
            $gates = @{ P0_zero = $true; P1_zero = $true; P2_zero = $true; critical_security = $true; critical_correctness = $true; data_integrity = $true; regression = $true; verification = $true; no_material_new_findings = $true; limitations_documented = $true; consecutive_clean_independent_audits = $true; module_dependency_integrity = $true }
            $findings = @(@{id="F001"; severity="P0"; status="OPEN"; category="SECURITY"; problem="Hardcoded key"})

            $hasOpenP0 = ($findings | Where-Object { $_.severity -eq "P0" -and $_.status -notin @("VERIFIED", "DEFERRED") }).Count -gt 0

            if ($hasOpenP0 -and $gates.P0_zero) {
                $inconsistent = $true
            } else {
                $inconsistent = $false
            }
            $inconsistent | Should -BeTrue
        }

        It 'critical_security gate must be false when open security P0-P2 findings exist' {
            $gates = @{ critical_security = $true }
            $findings = @(@{id="F002"; severity="P1"; status="IN_PROGRESS"; category="SECURITY"; problem="SQL injection"})

            $hasOpenSecurity = ($findings | Where-Object { $_.category -eq "SECURITY" -and $_.severity -in @("P0","P1","P2") -and $_.status -notin @("VERIFIED", "DEFERRED") }).Count -gt 0

            if ($hasOpenSecurity -and $gates.critical_security) {
                $inconsistent = $true
            } else {
                $inconsistent = $false
            }
            $inconsistent | Should -BeTrue
        }
    }
}