# ============================================================
# BUSINESS INVARIANT ENGINE v1.0.0
# Executable, deterministic invariant validation independent
# of the LLM. Business invariants are defined as JSON rules
# and evaluated against actual repository state.
# ============================================================

function Initialize-InvariantEngine {
    param([string]$InvariantDefPath)

    $Script:InvariantDefinitionFile = $InvariantDefPath
    if (-not (Test-Path -LiteralPath $Script:InvariantDefinitionFile)) {
        $defaultInvariants = Get-DefaultInvariants
        $parent = Split-Path -Parent $Script:InvariantDefinitionFile
        if (-not (Test-Path -LiteralPath $parent)) {
            New-Item -ItemType Directory -Force -Path $parent | Out-Null
        }
        $json = $defaultInvariants | ConvertTo-Json -Depth 100
        $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
        [System.IO.File]::WriteAllText($Script:InvariantDefinitionFile, $json, $utf8NoBom)
    }
    return $Script:InvariantDefinitionFile
}

function Get-DefaultInvariants {
    return @{
        version = "1.0.0"
        description = "Default business invariants for the AURA engine itself"
        invariants = @(
            @{
                id = "BI-STATE-001"; name = "State files must be valid JSON"
                category = "DATA_INTEGRITY"; severity = "P0"
                rule_type = "file_exists_json"
                files = @("state/cycle.json", "state/findings.json", "state/convergence.json")
                check = "files_must_parse_as_json"
                description = "All state files must exist and parse as valid JSON."
            }
            @{
                id = "BI-STATE-002"; name = "Cycle number must be monotonic"
                category = "DATA_INTEGRITY"; severity = "P0"
                rule_type = "monotonic_increasing"
                field_path = "state/cycle.json.current_cycle"
                description = "Cycle number must never decrease between consecutive reads."
            }
            @{
                id = "BI-STATE-003"; name = "No duplicate finding IDs"
                category = "DATA_INTEGRITY"; severity = "P0"
                rule_type = "no_duplicates"
                field_path = "state/findings.json.findings[*].id"
                description = "Each finding must have a unique ID."
            }
            @{
                id = "BI-STATE-004"; name = "Convergence gates count must be 12"
                category = "CORRECTNESS"; severity = "P0"
                rule_type = "field_count"
                field_path = "state/convergence.json.gates"; expected_count = 12
                description = "Convergence gate must have exactly 12 gates."
            }
            @{
                id = "BI-STATE-005"; name = "Finding status must be valid"
                category = "CORRECTNESS"; severity = "P1"
                rule_type = "valid_values"
                field_path = "state/findings.json.findings[*].status"
                valid_values = @("OPEN", "IN_PROGRESS", "FIXED", "VERIFYING", "VERIFIED", "REJECTED", "DEFERRED", "BLOCKED", "UNVERIFIED")
                description = "Every finding status must be recognized."
            }
            @{
                id = "BI-STATE-006"; name = "Classification must be valid"
                category = "CORRECTNESS"; severity = "P0"
                rule_type = "valid_values"
                field_path = "state/convergence.json.classification"
                valid_values = @("NOT_READY", "CONDITIONALLY_READY", "PRODUCTION_READY", "HUMAN_BLOCKED")
                description = "Engine classification must be recognized."
            }
            @{
                id = "BI-STATE-007"; name = "Configuration must exist and be valid JSON"
                category = "CORRECTNESS"; severity = "P0"
                rule_type = "file_exists_json"
                files = @("config/aura.json")
                check = "files_must_parse_as_json"
                description = "Engine configuration must exist and parse."
            }
            @{
                id = "BI-STATE-008"; name = "Orchestrator script must exist"
                category = "CORRECTNESS"; severity = "P0"
                rule_type = "file_exists"
                files = @("src/engine/run-audit.ps1")
                description = "The orchestrator script must exist."
            }
            @{
                id = "BI-STATE-009"; name = "All agent definitions must exist"
                category = "CORRECTNESS"; severity = "P1"
                rule_type = "file_exists"
                files = @("src/agents/independent-auditor.md","src/agents/adversarial-auditor.md","src/agents/remediator.md","src/agents/verifier.md","src/agents/regression-auditor.md","src/agents/convergence-judge.md")
                description = "All six agent definitions must exist."
            }
            @{
                id = "BI-STATE-010"; name = "Evidence registry integrity"
                category = "DATA_INTEGRITY"; severity = "P1"
                rule_type = "no_cross_cycle_evidence"
                field_path = "state/evidence-registry.json"
                description = "No evidence artifact may be registered under wrong cycle."
            }
            @{
                id = "BI-STATE-011"; name = "Force-validation bypass audit trail"
                category = "DATA_INTEGRITY"; severity = "P1"
                rule_type = "audit_trail"
                field_path = "state/force-validation-log.json"
                description = "Force-validation bypasses must be logged."
            }
            @{
                id = "BI-STATE-012"; name = "No orphan proposed files older than 1 hour"
                category = "OPERATIONS"; severity = "P3"
                rule_type = "no_stale_proposed"
                field_path = "state/proposed-*.json"; max_age_minutes = 60
                description = "Proposed files older than 60 min indicate stalled agent."
            }
        )
    }
}

function Read-InvariantDefinitions {
    param([string]$DefPath)
    if (-not $DefPath) { $DefPath = $Script:InvariantDefinitionFile }
    if (-not (Test-Path -LiteralPath $DefPath)) { return $null }
    try {
        $content = Get-Content -LiteralPath $DefPath -Raw -Encoding UTF8
        if ([string]::IsNullOrWhiteSpace($content)) { return $null }
        return $content | ConvertFrom-Json
    } catch {
        Write-Warning "Read-InvariantDefinitions: Malformed file. $_"
        return $null
    }
}

function Invoke-InvariantCheck {
    param([string]$EngineRoot, [string]$InvariantDefPath, [switch]$IncludeWarnings)
    if (-not $InvariantDefPath) { $InvariantDefPath = $Script:InvariantDefinitionFile }
    $definitions = Read-InvariantDefinitions -DefPath $InvariantDefPath
    if (-not $definitions -or -not $definitions.invariants) {
        return @{ passed = $false; total = 0; passed_count = 0; failed_count = 0; errors = @("No invariant definitions found"); results = @() }
    }
    $results = @()
    $allPassed = $true
    foreach ($inv in $definitions.invariants) {
        $r = Test-SingleInvariant -EngineRoot $EngineRoot -Invariant $inv
        $results += $r
        if (-not $r.passed -and $inv.severity -in @("P0","P1")) { $allPassed = $false }
    }
    return @{
        passed = $allPassed
        total = $results.Count
        passed_count = ($results | Where-Object { $_.passed }).Count
        failed_count = ($results | Where-Object { -not $_.passed }).Count
        results = $results
    }
}

function Test-SingleInvariant {
    param([string]$EngineRoot, [PSCustomObject]$Invariant)

    $r = @{ id = $Invariant.id; name = $Invariant.name; severity = $Invariant.severity; category = $Invariant.category; passed = $false; detail = "" }
    $ruleType = [string]$Invariant.rule_type

    if ($ruleType -eq "file_exists_json") {
        $allOk = $true
        foreach ($f in $Invariant.files) {
            $fp = Join-Path $EngineRoot $f
            if (-not (Test-Path -LiteralPath $fp)) { $r.detail = "MISSING: $f"; $allOk = $false; break }
            try {
                $c = Get-Content -LiteralPath $fp -Raw -Encoding UTF8
                if ([string]::IsNullOrWhiteSpace($c)) { $r.detail = "EMPTY: $f"; $allOk = $false; break }
                $null = $c | ConvertFrom-Json
            } catch { $r.detail = "MALFORMED JSON: $f - $_"; $allOk = $false; break }
        }
        $r.passed = $allOk
        if ($allOk) { $r.detail = "All files exist and parse." }
        return $r
    }

    if ($ruleType -eq "file_exists") {
        $allOk = $true
        foreach ($f in $Invariant.files) {
            $fp = Join-Path $EngineRoot $f
            if (-not (Test-Path -LiteralPath $fp)) { $r.detail = "MISSING: $f"; $allOk = $false; break }
        }
        $r.passed = $allOk
        if ($allOk) { $r.detail = "All required files exist." }
        return $r
    }

    if ($ruleType -eq "valid_values") {
        try {
            $parts = [string]$Invariant.field_path -split '\.json\.'
            if ($parts.Count -lt 2) { $r.detail = "Invalid field_path"; return $r }
            $sf = if ($parts[0] -match '\.json$') { $parts[0] } else { "$($parts[0]).json" }
            $fe = $parts[1]
            $sp = Join-Path $EngineRoot $sf
            if (-not (Test-Path -LiteralPath $sp)) { $r.detail = "State file not found: $sf"; return $r }
            $data = Get-Content -LiteralPath $sp -Raw -Encoding UTF8 | ConvertFrom-Json
            if ($fe -match '\[\*\]') {
                $af = $fe -replace '\[\*\].*',''
                $ef = $fe -replace '.*\[\*\]\.',''
                $arr = if ($data.$af) { @($data.$af) } else { @() }
                $validVals = $Invariant.valid_values
                $bad = foreach ($item in $arr) {
                    $v = if ($ef) { [string]$item.$ef } else { [string]$item }
                    if ($v -notin $validVals) { $item }
                }
                $bad = @($bad)
                $r.passed = ($bad.Count -eq 0)
                if (-not $r.passed) {
                    $vals = ($bad | ForEach-Object { [string](if ($ef) { $_.$ef } else { $_ }) } | Select-Object -Unique)
                    $r.detail = "Invalid: $($vals -join ', ')"
                } else { $r.detail = "All values valid." }
            } else {
                $val = [string]$data.$fe
                $r.passed = ($val -in $Invariant.valid_values)
                $r.detail = if ($r.passed) { "Value '$val' valid." } else { "Value '$val' not in valid set." }
            }
        } catch { $r.detail = "Eval error: $($_.Exception.Message)" }
        return $r
    }

    if ($ruleType -eq "no_duplicates") {
        try {
            $sp = Join-Path $EngineRoot "state/findings.json"
            $data = Get-Content -LiteralPath $sp -Raw -Encoding UTF8 | ConvertFrom-Json
            $ids = @($data.findings | ForEach-Object { $_.id })
            $dupes = $ids | Group-Object | Where-Object { $_.Count -gt 1 }
            $r.passed = ($dupes.Count -eq 0)
            if (-not $r.passed) { $r.detail = "Duplicates: $($dupes.Name -join ', ')" }
            else { $r.detail = "No duplicates ($($ids.Count) total)." }
        } catch { $r.detail = "Eval error: $_" }
        return $r
    }

    if ($ruleType -eq "field_count") {
        try {
            $sp = Join-Path $EngineRoot "state/convergence.json"
            $data = Get-Content -LiteralPath $sp -Raw -Encoding UTF8 | ConvertFrom-Json
            $cnt = if ($data.gates -and $data.gates -is [PSCustomObject]) { ($data.gates.PSObject.Properties | Measure-Object).Count } else { 0 }
            $exp = [int]$Invariant.expected_count
            $r.passed = ($cnt -eq $exp)
            $r.detail = if ($r.passed) { "Gate count = $cnt (expected $exp)." } else { "Gate count = $cnt, expected $exp." }
        } catch { $r.detail = "Eval error: $_" }
        return $r
    }

    if ($ruleType -eq "monotonic_increasing") {
        try {
            $cyclePath = Join-Path $EngineRoot "state/cycle.json"
            if (Test-Path -LiteralPath $cyclePath) {
                $cycleData = Get-Content -LiteralPath $cyclePath -Raw -Encoding UTF8 | ConvertFrom-Json
                $currentCycle = [int]$cycleData.current_cycle
                $prevCycle = [int]$cycleData.previous_cycle
                if ($prevCycle -gt 0) {
                    $r.passed = ($currentCycle -gt $prevCycle)
                    $r.detail = if ($r.passed) { "Cycle $currentCycle > $prevCycle (monotonic)." } else { "Cycle decreased from $prevCycle to $currentCycle." }
                } else {
                    $r.passed = $true
                    $r.detail = "No previous cycle to compare."
                }
            } else {
                $r.passed = $true
                $r.detail = "cycle.json not yet created."
            }
        } catch { $r.detail = "Eval error: $_" }
        return $r
    }

    if ($ruleType -eq "no_stale_proposed") {
        try {
            $pat = Join-Path $EngineRoot "state\proposed-*.json"
            $stale = Get-ChildItem -Path $pat -ErrorAction SilentlyContinue | Where-Object { $_.LastWriteTime -lt (Get-Date).AddMinutes(-$Invariant.max_age_minutes) }
            $r.passed = ($stale.Count -eq 0)
            if (-not $r.passed) { $r.detail = "Stale files (>$($Invariant.max_age_minutes)min): $(($stale | ForEach-Object { $_.Name }) -join ', ')" }
            else { $r.detail = "No stale proposed files." }
        } catch { $r.detail = "Eval error: $_" }
        return $r
    }

    if ($ruleType -eq "audit_trail") {
        try {
            $logPath = Join-Path $EngineRoot "state/force-validation-log.json"
            if (Test-Path -LiteralPath $logPath) {
                $logData = Get-Content -LiteralPath $logPath -Raw -Encoding UTF8 | ConvertFrom-Json
                if ($logData -is [array]) {
                    $r.passed = ($logData.Count -gt 0)
                    $r.detail = "Audit trail log contains $($logData.Count) entries."
                } elseif ($logData.entries) {
                    $r.passed = ($logData.entries.Count -gt 0)
                    $r.detail = "Audit trail log has $($logData.entries.Count) entries."
                } else {
                    $r.passed = $true
                    $r.detail = "Audit trail file exists but has unrecognized format."
                }
            } else {
                $r.passed = $true
                $r.detail = "No force-validation bypasses logged."
            }
        } catch { $r.detail = "Eval error: $_" }
        return $r
    }

    if ($ruleType -eq "no_cross_cycle_evidence") {
        try {
            $rp = Join-Path $EngineRoot "state\evidence-registry.json"
            if (Test-Path -LiteralPath $rp) {
                $reg = Get-Content -LiteralPath $rp -Raw -Encoding UTF8 | ConvertFrom-Json
                $bad = @()
                if ($reg.replay_attempts -and $reg.replay_attempts.Count -gt 0) {
                    $bad += "Registry contains $($reg.replay_attempts.Count) replay attempt(s)"
                }
                if ($reg.entries -and $reg.entries -is [PSCustomObject]) {
                    foreach ($entryProp in $reg.entries.PSObject.Properties) {
                        $entry = $entryProp.Value
                        if ($entry.cycle -and $reg.cycle -and [int]$entry.cycle -ne [int]$reg.cycle) {
                            $bad += "Entry hash $($entryProp.Name) cycle=$($entry.cycle) != registry cycle=$($reg.cycle)"
                        }
                    }
                }
                $r.passed = ($bad.Count -eq 0)
                $r.detail = if ($r.passed) { "No cross-cycle evidence reuse." } else { "VIOLATIONS: $($bad -join '; ')" }
            } else { $r.passed = $true; $r.detail = "Registry not yet created." }
        } catch { $r.detail = "Eval error: $_" }
        return $r
    }

    $r.detail = "Unknown rule_type: $ruleType"
    return $r
}

function Format-InvariantReport {
    param([PSCustomObject]$CheckResult)
    $sb = New-Object System.Text.StringBuilder
    [void]$sb.AppendLine("")
    [void]$sb.AppendLine("=== BUSINESS INVARIANT VALIDATION ===")
    [void]$sb.AppendLine("Total invariants: $($CheckResult.total)")
    [void]$sb.AppendLine("Passed: $($CheckResult.passed_count)")
    [void]$sb.AppendLine("Failed: $($CheckResult.failed_count)")
    [void]$sb.AppendLine("Overall: $(if ($CheckResult.passed) { 'PASS' } else { 'FAIL' })")
    [void]$sb.AppendLine("")
    $failed = @($CheckResult.results | Where-Object { -not $_.passed })
    if ($failed.Count -gt 0) {
        [void]$sb.AppendLine("## FAILED INVARIANTS")
        foreach ($f in $failed) {
            [void]$sb.AppendLine("- **[$($f.severity)] $($f.id)**: $($f.name)")
            [void]$sb.AppendLine("  Detail: $($f.detail)")
        }
    }
    [void]$sb.AppendLine("## Passed: $($CheckResult.passed_count)/$($CheckResult.total)")
    return $sb.ToString()
}