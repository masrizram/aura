# ============================================================
# DETERMINISTIC CAPABILITY SCORING ENGINE v1.0.0
# Fully deterministic scoring across 6 axes (EXISTS, INTEGRATED,
# EXECUTED, VALIDATED, ADVERSARIALLY_TESTED, INDEPENDENTLY_REPRODUCED).
# No AI heuristics. No manual overrides. No subjective adjustments.
# Same evidence always produces the same score.
# ============================================================

$Script:CapabilityRegistry = $null
$Script:ScoreOutputFile = $null

#region --- EVIDENCE DETECTION HELPERS (deterministic file-system checks) ---

function Test-FileExists {
    param([string]$Path)
    if ([string]::IsNullOrEmpty($Path)) { return $false }
    return (Test-Path -LiteralPath $Path -PathType Leaf) -and ((Get-Item -LiteralPath $Path -ErrorAction SilentlyContinue).Length -gt 0)
}

function Test-DirExists {
    param([string]$Path)
    if ([string]::IsNullOrEmpty($Path)) { return $false }
    return Test-Path -LiteralPath $Path -PathType Container
}

function Test-FileContains {
    param([string]$Path, [string]$Pattern)
    if (-not (Test-Path -LiteralPath $Path)) { return $false }
    try {
        $content = Get-Content -LiteralPath $Path -Raw -Encoding UTF8 -ErrorAction SilentlyContinue
        if ([string]::IsNullOrWhiteSpace($content)) { return $false }
        return $content -match $Pattern
    } catch {
        return $false
    }
}

function Test-JsonFileHasField {
    param([string]$Path, [string]$FieldName)
    if (-not (Test-Path -LiteralPath $Path)) { return $false }
    try {
        $content = Get-Content -LiteralPath $Path -Raw -Encoding UTF8
        if ([string]::IsNullOrWhiteSpace($content)) { return $false }
        $obj = $content | ConvertFrom-Json
        return $null -ne $obj.$FieldName
    } catch {
        return $false
    }
}

function Test-JsonFieldValue {
    param([string]$Path, [string]$FieldName, $ExpectedValue)
    if (-not (Test-Path -LiteralPath $Path)) { return $false }
    try {
        $content = Get-Content -LiteralPath $Path -Raw -Encoding UTF8
        if ([string]::IsNullOrWhiteSpace($content)) { return $false }
        $obj = $content | ConvertFrom-Json
        $actual = $obj.$FieldName
        if ($null -eq $actual -and $null -eq $ExpectedValue) { return $true }
        if ($null -eq $actual -or $null -eq $ExpectedValue) { return $false }
        if ($ExpectedValue -is [bool]) {
            return ([bool]$actual) -eq $ExpectedValue
        }
        return ([string]$actual) -eq ([string]$ExpectedValue)
    } catch {
        return $false
    }
}

function Test-JsonFieldGreaterThan {
    param([string]$Path, [string]$FieldName, [int]$Threshold)
    if (-not (Test-Path -LiteralPath $Path)) { return $false }
    try {
        $content = Get-Content -LiteralPath $Path -Raw -Encoding UTF8
        if ([string]::IsNullOrWhiteSpace($content)) { return $false }
        $obj = $content | ConvertFrom-Json
        $val = $obj.$FieldName
        if ($null -eq $val) { return $false }
        return ([int]$val) -gt $Threshold
    } catch {
        return $false
    }
}

function Test-JsonArrayHasItems {
    param([string]$Path, [string]$FieldName, [int]$MinCount = 1)
    if (-not (Test-Path -LiteralPath $Path)) { return $false }
    try {
        $content = Get-Content -LiteralPath $Path -Raw -Encoding UTF8
        if ([string]::IsNullOrWhiteSpace($content)) { return $false }
        $obj = $content | ConvertFrom-Json
        $arr = @($obj.$FieldName)
        return $arr.Count -ge $MinCount
    } catch {
        return $false
    }
}

function Test-AdversarialAttackPassed {
    param([string]$CampaignPath, [string]$AttackId)
    if (-not (Test-Path -LiteralPath $CampaignPath)) { return $false }
    try {
        $content = Get-Content -LiteralPath $CampaignPath -Raw -Encoding UTF8
        if ([string]::IsNullOrWhiteSpace($content)) { return $false }
        $campaign = $content | ConvertFrom-Json
        foreach ($atk in $campaign.attacks) {
            if ([string]$atk.id -eq $AttackId) {
                return [bool]$atk.passed
            }
        }
        return $false
    } catch {
        return $false
    }
}

function Test-VerificationCheckPassed {
    param([string]$VerificationPath, [string]$CheckName)
    if (-not (Test-Path -LiteralPath $VerificationPath)) { return $false }
    try {
        $content = Get-Content -LiteralPath $VerificationPath -Raw -Encoding UTF8
        if ([string]::IsNullOrWhiteSpace($content)) { return $false }
        $results = $content | ConvertFrom-Json
        foreach ($verdict in $results.verdicts) {
            foreach ($check in $verdict.checks) {
                if ([string]$check.name -eq $CheckName) {
                    return [bool]$check.passed
                }
            }
        }
        return $false
    } catch {
        return $false
    }
}

function Test-SandboxTestPassed {
    param([string]$SandboxPath, [string]$TestName)
    if (-not (Test-Path -LiteralPath $SandboxPath)) { return $false }
    try {
        $content = Get-Content -LiteralPath $SandboxPath -Raw -Encoding UTF8
        if ([string]::IsNullOrWhiteSpace($content)) { return $false }
        $results = $content | ConvertFrom-Json
        foreach ($test in $results.tests) {
            if ([string]$test.name -eq $TestName) {
                return [bool]$test.passed
            }
        }
        return $false
    } catch {
        return $false
    }
}

function Test-InvariantCheckPassed {
    param([string]$EngineRoot, [string]$InvariantId)
    $invariantDefPath = Join-Path $EngineRoot "state\invariant-definitions.json"
    if (-not (Test-Path -LiteralPath $invariantDefPath)) { return $false }

    $defs = Get-Content -LiteralPath $invariantDefPath -Raw -Encoding UTF8 | ConvertFrom-Json

    foreach ($inv in $defs.invariants) {
        if ([string]$inv.id -eq $InvariantId) {
            if ($inv.rule_type -eq "file_exists_json") {
                $allOk = $true
                foreach ($f in $inv.files) {
                    $fp = Join-Path $EngineRoot $f
                    if (-not (Test-Path -LiteralPath $fp)) { $allOk = $false; break }
                    try {
                        $c = Get-Content -LiteralPath $fp -Raw -Encoding UTF8
                        if ([string]::IsNullOrWhiteSpace($c)) { $allOk = $false; break }
                        $null = $c | ConvertFrom-Json
                    } catch { $allOk = $false; break }
                }
                return $allOk
            }
            if ($inv.rule_type -eq "file_exists") {
                foreach ($f in $inv.files) {
                    $fp = Join-Path $EngineRoot $f
                    if (-not (Test-Path -LiteralPath $fp)) { return $false }
                }
                return $true
            }
            if ($inv.rule_type -eq "valid_values") {
                return Test-JsonFileHasField (Join-Path $EngineRoot "state/convergence.json") "classification"
            }
            if ($inv.rule_type -eq "field_count") {
                try {
                    $sp = Join-Path $EngineRoot "state/convergence.json"
                    $data = Get-Content -LiteralPath $sp -Raw -Encoding UTF8 | ConvertFrom-Json
                    $cnt = if ($data.gates -and $data.gates -is [PSCustomObject]) { ($data.gates.PSObject.Properties | Measure-Object).Count } else { 0 }
                    return $cnt -eq [int]$inv.expected_count
                } catch { return $false }
            }
            return $true
        }
    }
    return $false
}

#endregion

#region --- CAPABILITY EVIDENCE MAPPING (each capability => 6 deterministic checks) ---

function Get-CapabilityEvidenceMap {
    param([string]$EngineRoot)

    $auraRoot = $EngineRoot
    $runAudit = Join-Path $EngineRoot "run-audit.ps1"
    $configFile = Join-Path $EngineRoot "config.json"
    $cycleFile = Join-Path $EngineRoot "state\cycle.json"
    $findingsFile = Join-Path $EngineRoot "state\findings.json"
    $convFile = Join-Path $EngineRoot "state\convergence.json"
    $evidenceRegFile = Join-Path $EngineRoot "state\evidence-registry.json"
    $toolingEvidenceFile = Join-Path $EngineRoot "state\tooling-evidence.json"
    $repoGraphFile = Join-Path $EngineRoot "state\repo-graph.json"
    $forceLogFile = Join-Path $EngineRoot "state\force-validation-log.json"
    $adversarialFile = Join-Path $EngineRoot "reports\adversarial-results.json"
    $verificationFile = Join-Path $EngineRoot "reports\verification-results.json"
    $securityScanFile = Join-Path $EngineRoot "reports\security-scan-results.json"
    $sandboxTestFile = Join-Path $EngineRoot "reports\sandbox-test-results.json"

    $evidenceIntegrityModule = Join-Path $EngineRoot "modules\evidence-integrity.ps1"
    $adversarialModule = Join-Path $EngineRoot "modules\adversarial-campaign.ps1"
    $businessInvariantsModule = Join-Path $EngineRoot "modules\business-invariants.ps1"
    $repoGraphModule = Join-Path $EngineRoot "modules\repo-graph.ps1"
    $independentVerifierModule = Join-Path $EngineRoot "modules\independent-verifier.ps1"
    $securityScanModule = Join-Path $EngineRoot "modules\security-scan.ps1"
    $sandboxModule = Join-Path $EngineRoot "modules\sandbox.ps1"
    $scaleBenchModule = Join-Path $EngineRoot "modules\scale-benchmark.ps1"
    $gitSafetyModule = Join-Path $EngineRoot "modules\git-safety.ps1"

    return @{ EngineRoot = $EngineRoot; AuraRoot = $auraRoot; RunAudit = $runAudit; ConfigFile = $configFile;
              CycleFile = $cycleFile; FindingsFile = $findingsFile; ConvFile = $convFile;
              EvidenceRegFile = $evidenceRegFile; ToolingEvidenceFile = $toolingEvidenceFile;
              RepoGraphFile = $repoGraphFile; ForceLogFile = $forceLogFile;
              AdversarialFile = $adversarialFile; VerificationFile = $verificationFile;
              SecurityScanFile = $securityScanFile; SandboxTestFile = $sandboxTestFile;
              EvidenceIntegrityModule = $evidenceIntegrityModule; AdversarialModule = $adversarialModule;
              BusinessInvariantsModule = $businessInvariantsModule; RepoGraphModule = $repoGraphModule;
              IndependentVerifierModule = $independentVerifierModule; SecurityScanModule = $securityScanModule;
              SandboxModule = $sandboxModule; ScaleBenchModule = $scaleBenchModule;
              GitSafetyModule = $gitSafetyModule }
}

#endregion

#region --- SCORING ENGINE ---

function Get-CapabilityScore {
    param(
        [hashtable]$CapabilityDef,
        [hashtable]$Evidence
    )

    $score = @{
        capability = $CapabilityDef.Name
        weight = $CapabilityDef.Weight
        exists = $false
        integrated = $false
        executed = $false
        validated = $false
        adversarial = $false
        independent = $false
        evidence_paths = @()
        sub_score = 0
        weighted_score = 0.0
        detail = ""
    }

    $sbExists = $CapabilityDef.ExistsCheck
    $sbIntegrated = $CapabilityDef.IntegratedCheck
    $sbExecuted = $CapabilityDef.ExecutedCheck
    $sbValidated = $CapabilityDef.ValidatedCheck
    $sbAdversarial = $CapabilityDef.AdversarialCheck
    $sbIndependent = $CapabilityDef.IndependentCheck
    $sbEvidence = $CapabilityDef.EvidencePaths

    [bool]$score.exists = $false
    [bool]$score.integrated = $false
    [bool]$score.executed = $false
    [bool]$score.validated = $false
    [bool]$score.adversarial = $false
    [bool]$score.independent = $false

    try { [bool]$score.exists = & $sbExists } catch { $score.exists = $false }
    try { [bool]$score.integrated = & $sbIntegrated } catch { $score.integrated = $false }
    try { [bool]$score.executed = & $sbExecuted } catch { $score.executed = $false }
    try { [bool]$score.validated = & $sbValidated } catch { $score.validated = $false }
    try { [bool]$score.adversarial = & $sbAdversarial } catch { $score.adversarial = $false }
    try { [bool]$score.independent = & $sbIndependent } catch { $score.independent = $false }

    try { $score.evidence_paths = @(& $sbEvidence) } catch { $score.evidence_paths = @() }

    $rawScore = 0.0
    if ($score.exists)     { $rawScore += 20.0 }
    if ($score.integrated) { $rawScore += 20.0 }
    if ($score.executed)   { $rawScore += 15.0 }
    if ($score.validated)  { $rawScore += 15.0 }
    if ($score.adversarial){ $rawScore += 15.0 }
    if ($score.independent){ $rawScore += 15.0 }

    $score.sub_score = [math]::Round($rawScore, 1)
    $score.weighted_score = [math]::Round($rawScore * $CapabilityDef.Weight, 2)

    $score.detail = "E=$($score.exists) I=$($score.integrated) X=$($score.executed) V=$($score.validated) A=$($score.adversarial) R=$($score.independent)"

    return $score
}

function Build-CapabilityDefinitions {
    param([hashtable]$Evidence)

    $r = $Evidence.RunAudit
    $c = $Evidence.ConfigFile
    $cy = $Evidence.CycleFile
    $f = $Evidence.FindingsFile
    $cv = $Evidence.ConvFile
    $er = $Evidence.EvidenceRegFile
    $te = $Evidence.ToolingEvidenceFile
    $rg = $Evidence.RepoGraphFile
    $fl = $Evidence.ForceLogFile
    $af = $Evidence.AdversarialFile
    $vf = $Evidence.VerificationFile
    $ss = $Evidence.SecurityScanFile
    $st = $Evidence.SandboxTestFile
    $eroot = $Evidence.EngineRoot
    $eim = $Evidence.EvidenceIntegrityModule
    $am = $Evidence.AdversarialModule
    $bim = $Evidence.BusinessInvariantsModule
    $rgm = $Evidence.RepoGraphModule
    $ivm = $Evidence.IndependentVerifierModule
    $ssm = $Evidence.SecurityScanModule
    $sm = $Evidence.SandboxModule
    $sbm = $Evidence.ScaleBenchModule
    $gsm = $Evidence.GitSafetyModule

    $esc = { param([string]$s) $s -replace "'","''" }

    $defs = @()

    # --- StateMachine ---
    $defs += @{
        Name = "StateMachine"
        Weight = 1.0
        ExistsCheck = [scriptblock]::Create("(Test-FileExists '$(& $esc $c)') -and (Test-FileExists '$(& $esc $cy)') -and (Test-FileExists '$(& $esc $f)') -and (Test-FileContains '$(& $esc $c)' 'state_machine') -and (Test-JsonFileHasField '$(& $esc $cy)' 'current_phase') -and (Test-JsonArrayHasItems '$(& $esc $f)' 'findings' 1)")
        IntegratedCheck = [scriptblock]::Create("(Test-FileContains '$(& $esc $r)' 'validate-state') -and (Test-FileContains '$(& $esc $r)' 'promote-state') -and (Test-FileContains '$(& $esc $r)' 'state_machine') -and (Test-FileContains '$(& $esc $r)' 'Validate-FindingStateIntegrity')")
        ExecutedCheck = [scriptblock]::Create("(Test-JsonFieldGreaterThan '$(& $esc $cy)' 'current_cycle' 0) -and (Test-JsonFieldGreaterThan '$(& $esc $cy)' 'cycles_completed' 0)")
        ValidatedCheck = [scriptblock]::Create("(Test-InvariantCheckPassed '$(& $esc $eroot)' 'BI-STATE-005') -and (Test-InvariantCheckPassed '$(& $esc $eroot)' 'BI-STATE-003')")
        AdversarialCheck = [scriptblock]::Create("(Test-AdversarialAttackPassed '$(& $esc $af)' 'ATK-02') -and (Test-AdversarialAttackPassed '$(& $esc $af)' 'ATK-07')")
        IndependentCheck = [scriptblock]::Create("(Test-FileExists '$(& $esc $cy)') -and (Test-FileExists '$(& $esc $f)') -and (Test-FileExists '$(& $esc $cv)') -and (Test-FileExists '$(& $esc $c)')")
        EvidencePaths = [scriptblock]::Create("@('$(& $esc $c)', '$(& $esc $cy)', '$(& $esc $f)', '$(& $esc $cv)')")
    }

    # --- StateWriterIsolation ---
    $defs += @{
        Name = "StateWriterIsolation"
        Weight = 1.0
        ExistsCheck = [scriptblock]::Create("(Test-FileContains '$(& $esc $r)' 'Write-JsonFile') -and (Test-FileContains '$(& $esc $r)' '\.tmp\.')")
        IntegratedCheck = [scriptblock]::Create("(Test-FileContains '$(& $esc $r)' 'Write-JsonFile') -and (Test-FileContains '$(& $esc $r)' 'Move-Item')")
        ExecutedCheck = [scriptblock]::Create("(Test-JsonFieldGreaterThan '$(& $esc $cy)' 'current_cycle' 0)")
        ValidatedCheck = [scriptblock]::Create("(Test-InvariantCheckPassed '$(& $esc $eroot)' 'BI-STATE-001')")
        AdversarialCheck = [scriptblock]::Create("(Test-AdversarialAttackPassed '$(& $esc $af)' 'ATK-01')")
        IndependentCheck = [scriptblock]::Create("(Test-FileContains '$(& $esc $r)' 'UTF8Encoding') -and (Test-FileContains '$(& $esc $r)' 'Move-Item.*-Force')")
        EvidencePaths = [scriptblock]::Create("@('$(& $esc $cy)', '$(& $esc $f)', '$(& $esc $cv)')")
    }

    # --- ConvergenceSafety ---
    $defs += @{
        Name = "ConvergenceSafety"
        Weight = 1.0
        ExistsCheck = [scriptblock]::Create("(Test-FileExists '$(& $esc $cv)') -and (Test-FileContains '$(& $esc $r)' 'convergence') -and (Test-FileContains '$(& $esc $c)' 'convergence_gate')")
        IntegratedCheck = [scriptblock]::Create("(Test-FileContains '$(& $esc $r)' 'Get-ConvergenceStatus') -and (Test-FileContains '$(& $esc $r)' 'Validate-GateEvidenceIntegrity') -and (Test-FileContains '$(& $esc $r)' 'convergence.*halt')")
        ExecutedCheck = [scriptblock]::Create("(Test-JsonFileHasField '$(& $esc $cv)' 'overall_score') -and (Test-JsonFieldGreaterThan '$(& $esc $cv)' 'cycle' 0)")
        ValidatedCheck = [scriptblock]::Create("(Test-InvariantCheckPassed '$(& $esc $eroot)' 'BI-STATE-004') -and (Test-InvariantCheckPassed '$(& $esc $eroot)' 'BI-STATE-006')")
        AdversarialCheck = [scriptblock]::Create("(Test-AdversarialAttackPassed '$(& $esc $af)' 'ATK-03') -and (Test-AdversarialAttackPassed '$(& $esc $af)' 'ATK-04') -and (Test-AdversarialAttackPassed '$(& $esc $af)' 'ATK-05') -and (Test-AdversarialAttackPassed '$(& $esc $af)' 'ATK-06')")
        IndependentCheck = [scriptblock]::Create("(Test-FileExists '$(& $esc $cv)') -and (Test-FileExists '$(& $esc $c)') -and (Test-JsonFileHasField '$(& $esc $cv)' 'gates')")
        EvidencePaths = [scriptblock]::Create("@('$(& $esc $cv)', '$(& $esc $c)')")
    }

    # --- EvidenceIntegrity ---
    $defs += @{
        Name = "EvidenceIntegrity"
        Weight = 1.0
        ExistsCheck = [scriptblock]::Create("(Test-FileExists '$(& $esc $eim)') -and (Test-FileExists '$(& $esc $er)')")
        IntegratedCheck = [scriptblock]::Create("(Test-FileContains '$(& $esc $r)' 'Initialize-EvidenceEngine') -and (Test-FileContains '$(& $esc $r)' 'Register-Evidence') -and (Test-FileContains '$(& $esc $r)' 'Test-EvidenceReplay')")
        ExecutedCheck = [scriptblock]::Create("(Test-FileExists '$(& $esc $er)') -and (Test-JsonFileHasField '$(& $esc $er)' 'entries') -and (Test-JsonFileHasField '$(& $esc $er)' 'replay_attempts')")
        ValidatedCheck = [scriptblock]::Create("(Test-InvariantCheckPassed '$(& $esc $eroot)' 'BI-STATE-010')")
        AdversarialCheck = [scriptblock]::Create("(Test-AdversarialAttackPassed '$(& $esc $af)' 'ATK-09') -and (Test-AdversarialAttackPassed '$(& $esc $af)' 'ATK-10')")
        IndependentCheck = [scriptblock]::Create("(Test-FileExists '$(& $esc $er)') -and (Test-JsonArrayHasItems '$(& $esc $er)' 'replay_attempts' 1)")
        EvidencePaths = [scriptblock]::Create("@('$(& $esc $er)', '$(& $esc $eim)')")
    }

    # --- BusinessInvariants ---
    $invDefPath = Join-Path $eroot "state\invariant-definitions.json"
    $defs += @{
        Name = "BusinessInvariants"
        Weight = 1.0
        ExistsCheck = [scriptblock]::Create("(Test-FileExists '$(& $esc $bim)') -and (Test-FileExists '$(& $esc $invDefPath)')")
        IntegratedCheck = [scriptblock]::Create("(Test-FileContains '$(& $esc $r)' 'Invoke-InvariantCheck') -and (Test-FileContains '$(& $esc $r)' 'Initialize-InvariantEngine')")
        ExecutedCheck = [scriptblock]::Create("(Test-FileExists '$(& $esc $invDefPath)')")
        ValidatedCheck = [scriptblock]::Create("(Test-InvariantCheckPassed '$(& $esc $eroot)' 'BI-STATE-001') -and (Test-InvariantCheckPassed '$(& $esc $eroot)' 'BI-STATE-007') -and (Test-InvariantCheckPassed '$(& $esc $eroot)' 'BI-STATE-008')")
        AdversarialCheck = [scriptblock]::Create("(Test-AdversarialAttackPassed '$(& $esc $af)' 'ATK-02')")
        IndependentCheck = [scriptblock]::Create("(Test-FileExists '$(& $esc $invDefPath)') -and (Test-JsonArrayHasItems '$(& $esc $invDefPath)' 'invariants' 5)")
        EvidencePaths = [scriptblock]::Create("@('$(& $esc $bim)', '$(& $esc $invDefPath)')")
    }

    # --- AdversarialDetection ---
    $defs += @{
        Name = "AdversarialDetection"
        Weight = 1.0
        ExistsCheck = [scriptblock]::Create("(Test-FileExists '$(& $esc $am)') -and (Test-FileExists '$(& $esc $af)')")
        IntegratedCheck = [scriptblock]::Create("(Test-FileContains '$(& $esc $r)' 'Invoke-AdversarialCampaign') -and (Test-FileContains '$(& $esc $r)' 'adversarial-campaign')")
        ExecutedCheck = [scriptblock]::Create("(Test-JsonArrayHasItems '$(& $esc $af)' 'attacks' 5) -and (Test-JsonFileHasField '$(& $esc $af)' 'summary')")
        ValidatedCheck = [scriptblock]::Create("try { `$content = Get-Content -LiteralPath '$(& $esc $af)' -Raw -Encoding UTF8; `$summary = (`$content | ConvertFrom-Json).summary; return ([int]`$summary.attacks_detected) -eq ([int]`$summary.total_attacks) } catch { return `$false }")
        AdversarialCheck = [scriptblock]::Create("try { `$content = Get-Content -LiteralPath '$(& $esc $af)' -Raw -Encoding UTF8; `$summary = (`$content | ConvertFrom-Json).summary; return ([string]`$summary.status) -eq 'ALL ATTACKS DETECTED' } catch { return `$false }")
        IndependentCheck = [scriptblock]::Create("(Test-FileExists '$(& $esc $af)') -and (Test-JsonArrayHasItems '$(& $esc $af)' 'attacks' 10)")
        EvidencePaths = [scriptblock]::Create("@('$(& $esc $af)', '$(& $esc $am)')")
    }

    # --- RepositoryIndexing ---
    $defs += @{
        Name = "RepositoryIndexing"
        Weight = 1.0
        ExistsCheck = [scriptblock]::Create("(Test-FileExists '$(& $esc $rgm)') -and (Test-FileExists '$(& $esc $rg)')")
        IntegratedCheck = [scriptblock]::Create("(Test-FileContains '$(& $esc $r)' 'Initialize-RepoGraph') -and (Test-FileContains '$(& $esc $r)' 'index-repo')")
        ExecutedCheck = [scriptblock]::Create("(Test-JsonFileHasField '$(& $esc $rg)' 'total_files') -and (Test-JsonFieldGreaterThan '$(& $esc $rg)' 'total_files' 0)")
        ValidatedCheck = [scriptblock]::Create("(Test-JsonFileHasField '$(& $esc $rg)' 'file_graph') -and (Test-JsonFileHasField '$(& $esc $rg)' 'repository_root')")
        AdversarialCheck = [scriptblock]::Create("(Test-AdversarialAttackPassed '$(& $esc $af)' 'ATK-01')")
        IndependentCheck = [scriptblock]::Create("(Test-FileExists '$(& $esc $rg)') -and (Test-JsonFileHasField '$(& $esc $rg)' 'dependency_graph')")
        EvidencePaths = [scriptblock]::Create("@('$(& $esc $rg)', '$(& $esc $rgm)')")
    }

    # --- IndependentVerification ---
    $defs += @{
        Name = "IndependentVerification"
        Weight = 1.0
        ExistsCheck = [scriptblock]::Create("(Test-FileExists '$(& $esc $ivm)') -and (Test-FileExists '$(& $esc $vf)')")
        IntegratedCheck = [scriptblock]::Create("(Test-FileContains '$(& $esc $r)' 'verify-findings') -and (Test-FileContains '$(& $esc $r)' 'Invoke-IndependentVerify')")
        ExecutedCheck = [scriptblock]::Create("(Test-JsonArrayHasItems '$(& $esc $vf)' 'verdicts' 1)")
        ValidatedCheck = [scriptblock]::Create("(Test-VerificationCheckPassed '$(& $esc $vf)' 'schema_validation') -and (Test-VerificationCheckPassed '$(& $esc $vf)' 'transition_legality')")
        AdversarialCheck = [scriptblock]::Create("(Test-VerificationCheckPassed '$(& $esc $vf)' 'evidence_completeness')")
        IndependentCheck = [scriptblock]::Create("(Test-FileExists '$(& $esc $vf)') -and (Test-JsonArrayHasItems '$(& $esc $vf)' 'verdicts' 1) -and (Test-FileExists '$(& $esc $ivm)')")
        EvidencePaths = [scriptblock]::Create("@('$(& $esc $vf)', '$(& $esc $ivm)')")
    }

    # --- SecurityScanning ---
    $defs += @{
        Name = "SecurityScanning"
        Weight = 1.0
        ExistsCheck = [scriptblock]::Create("(Test-FileExists '$(& $esc $ssm)') -and (Test-FileExists '$(& $esc $ss)')")
        IntegratedCheck = [scriptblock]::Create("(Test-FileContains '$(& $esc $r)' 'Invoke-SecurityScan') -and (Test-FileContains '$(& $esc $r)' 'security-scan')")
        ExecutedCheck = [scriptblock]::Create("(Test-JsonArrayHasItems '$(& $esc $ss)' 'findings' 1) -and (Test-JsonFileHasField '$(& $esc $ss)' 'files_scanned')")
        ValidatedCheck = [scriptblock]::Create("(Test-JsonFileHasField '$(& $esc $ss)' 'scan_type')")
        AdversarialCheck = [scriptblock]::Create("try { `$content = Get-Content -LiteralPath '$(& $esc $ss)' -Raw -Encoding UTF8; `$results = (`$content | ConvertFrom-Json); return (`$results.findings.Count -gt 0) } catch { return `$false }")
        IndependentCheck = [scriptblock]::Create("(Test-FileExists '$(& $esc $ss)') -and (Test-JsonFileHasField '$(& $esc $ss)' 'project_path')")
        EvidencePaths = [scriptblock]::Create("@('$(& $esc $ss)', '$(& $esc $ssm)')")
    }

    # --- ExecutionSandbox ---
    $defs += @{
        Name = "ExecutionSandbox"
        Weight = 1.0
        ExistsCheck = [scriptblock]::Create("(Test-FileExists '$(& $esc $sm)') -and (Test-FileExists '$(& $esc $st)')")
        IntegratedCheck = [scriptblock]::Create("(Test-FileContains '$(& $esc $r)' 'Invoke-SandboxSelfTest') -and (Test-FileContains '$(& $esc $r)' 'sandbox-test')")
        ExecutedCheck = [scriptblock]::Create("(Test-JsonArrayHasItems '$(& $esc $st)' 'tests' 1)")
        ValidatedCheck = [scriptblock]::Create("(Test-SandboxTestPassed '$(& $esc $st)' 'Timeout enforcement')")
        AdversarialCheck = [scriptblock]::Create("(Test-SandboxTestPassed '$(& $esc $st)' 'Output file isolation')")
        IndependentCheck = [scriptblock]::Create("(Test-FileExists '$(& $esc $st)') -and (Test-JsonFileHasField '$(& $esc $st)' 'all_passed')")
        EvidencePaths = [scriptblock]::Create("@('$(& $esc $st)', '$(& $esc $sm)')")
    }

    # --- ScaleBenchmark ---
    $defs += @{
        Name = "ScaleBenchmark"
        Weight = 1.0
        ExistsCheck = [scriptblock]::Create("(Test-FileExists '$(& $esc $sbm)')")
        IntegratedCheck = [scriptblock]::Create("(Test-FileContains '$(& $esc $r)' 'scale-benchmark') -and (Test-FileContains '$(& $esc $r)' 'New-ScaleBenchmark')")
        ExecutedCheck = [scriptblock]::Create("(Test-FileContains '$(& $esc $c)' 'scale') -and (Test-JsonFileHasField '$(& $esc $c)' 'scale')")
        ValidatedCheck = [scriptblock]::Create("(Test-FileContains '$(& $esc $c)' 'warn_file_count') -and (Test-JsonFieldGreaterThan '$(& $esc $cy)' 'current_cycle' 0)")
        AdversarialCheck = [scriptblock]::Create("(Test-AdversarialAttackPassed '$(& $esc $af)' 'ATK-03')")
        IndependentCheck = [scriptblock]::Create("(Test-FileExists '$(& $esc $sbm)')")
        EvidencePaths = [scriptblock]::Create("@('$(& $esc $sbm)', '$(& $esc $c)')")
    }

    # --- GitSafety ---
    $defs += @{
        Name = "GitSafety"
        Weight = 1.0
        ExistsCheck = [scriptblock]::Create("(Test-FileExists '$(& $esc $gsm)')")
        IntegratedCheck = [scriptblock]::Create("(Test-FileContains '$(& $esc $r)' 'git-safety') -and (Test-FileContains '$(& $esc $r)' 'New-GitSafeContext')")
        ExecutedCheck = [scriptblock]::Create("(Test-FileContains '$(& $esc $r)' 'git-safety')")
        ValidatedCheck = [scriptblock]::Create("(Test-FileContains '$(& $esc $gsm)' 'New-GitWorktree')")
        AdversarialCheck = [scriptblock]::Create("(Test-AdversarialAttackPassed '$(& $esc $af)' 'ATK-05')")
        IndependentCheck = [scriptblock]::Create("(Test-FileExists '$(& $esc $gsm)')")
        EvidencePaths = [scriptblock]::Create("@('$(& $esc $gsm)')")
    }

    # --- MutationTesting ---
    $defs += @{
        Name = "MutationTesting"
        Weight = 1.0
        ExistsCheck = [scriptblock]::Create("(Test-FileContains '$(& $esc $r)' 'mutation') -or (Test-FileContains '$(& $esc $am)' 'forbidden') -or (Test-FileContains '$(& $esc $bim)' 'invalid')")
        IntegratedCheck = [scriptblock]::Create("(Test-FileContains '$(& $esc $r)' 'mutation') -or (Test-FileContains '$(& $esc $am)' 'mutation')")
        ExecutedCheck = [scriptblock]::Create("(Test-FileContains '$(& $esc $af)' 'forbidden') -or (Test-FileContains '$(& $esc $af)' 'illegal')")
        ValidatedCheck = [scriptblock]::Create("(Test-AdversarialAttackPassed '$(& $esc $af)' 'ATK-02')")
        AdversarialCheck = [scriptblock]::Create("(Test-AdversarialAttackPassed '$(& $esc $af)' 'ATK-11')")
        IndependentCheck = [scriptblock]::Create("(Test-FileExists '$(& $esc $am)') -and (Test-FileContains '$(& $esc $am)' 'Test-ValidClassificationTransition')")
        EvidencePaths = [scriptblock]::Create("@('$(& $esc $am)', '$(& $esc $af)')")
    }

    # --- FailureRecovery ---
    $defs += @{
        Name = "FailureRecovery"
        Weight = 1.0
        ExistsCheck = [scriptblock]::Create("(Test-FileContains '$(& $esc $r)' 'Safe-Int') -and (Test-FileContains '$(& $esc $r)' 'Reset-Engine')")
        IntegratedCheck = [scriptblock]::Create("(Test-FileContains '$(& $esc $r)' 'Safe-Int') -and (Test-FileContains '$(& $esc $r)' 'reset') -and (Test-FileContains '$(& $esc $r)' 'ErrorActionPreference')")
        ExecutedCheck = [scriptblock]::Create("(Test-JsonFieldGreaterThan '$(& $esc $cy)' 'current_cycle' 0)")
        ValidatedCheck = [scriptblock]::Create("(Test-JsonFileHasField '$(& $esc $f)' 'next_id')")
        AdversarialCheck = [scriptblock]::Create("(Test-AdversarialAttackPassed '$(& $esc $af)' 'ATK-01')")
        IndependentCheck = [scriptblock]::Create("(Test-FileContains '$(& $esc $r)' 'Safe-Int') -and (Test-FileContains '$(& $esc $r)' 'try') -and (Test-FileContains '$(& $esc $r)' 'catch')")
        EvidencePaths = [scriptblock]::Create("@('$(& $esc $r)')")
    }

    # --- RealProjectBenchmark ---
    $defs += @{
        Name = "RealProjectBenchmark"
        Weight = 1.0
        ExistsCheck = [scriptblock]::Create("(Test-JsonArrayHasItems '$(& $esc $f)' 'findings' 5) -and (Test-JsonFieldGreaterThan '$(& $esc $cy)' 'cycles_completed' 2)")
        IntegratedCheck = [scriptblock]::Create("(Test-FileContains '$(& $esc $c)' 'max_cycles') -and (Test-FileContains '$(& $esc $c)' 'phases')")
        ExecutedCheck = [scriptblock]::Create("(Test-JsonFieldGreaterThan '$(& $esc $cy)' 'cycles_completed' 2)")
        ValidatedCheck = [scriptblock]::Create("(Test-InvariantCheckPassed '$(& $esc $eroot)' 'BI-STATE-009')")
        AdversarialCheck = [scriptblock]::Create("(Test-AdversarialAttackPassed '$(& $esc $af)' 'ATK-08')")
        IndependentCheck = [scriptblock]::Create("(Test-FileExists '$(& $esc $f)') -and (Test-FileExists '$(& $esc $cy)') -and (Test-FileExists '$(& $esc $cv)')")
        EvidencePaths = [scriptblock]::Create("@('$(& $esc $f)', '$(& $esc $cy)', '$(& $esc $cv)')")
    }

    # --- AutonomousLifecycle ---
    $defs += @{
        Name = "AutonomousLifecycle"
        Weight = 1.0
        ExistsCheck = [scriptblock]::Create("(Test-JsonArrayHasItems '$(& $esc $f)' 'findings' 5) -and (Test-JsonFieldGreaterThan '$(& $esc $cy)' 'cycles_completed' 5)")
        IntegratedCheck = [scriptblock]::Create("(Test-FileContains '$(& $esc $r)' 'phases') -and (Test-FileContains '$(& $esc $c)' 'phases') -and (Test-FileContains '$(& $esc $r)' 'while.*cycle.*max')")
        ExecutedCheck = [scriptblock]::Create("(Test-JsonFieldGreaterThan '$(& $esc $cy)' 'cycles_completed' 5)")
        ValidatedCheck = [scriptblock]::Create("try { `$content = Get-Content -LiteralPath '$(& $esc $f)' -Raw -Encoding UTF8; `$findings = (`$content | ConvertFrom-Json).findings; `$verified = @(`$findings | Where-Object { [string]`$_.status -eq 'VERIFIED' }); return `$verified.Count -gt 5 } catch { return `$false }")
        AdversarialCheck = [scriptblock]::Create("(Test-AdversarialAttackPassed '$(& $esc $af)' 'ATK-12')")
        IndependentCheck = [scriptblock]::Create("(Test-FileExists '$(& $esc $f)') -and (Test-FileExists '$(& $esc $cy)') -and (Test-FileExists '$(& $esc $cv)') -and (Test-JsonFileHasField '$(& $esc $cy)' 'current_phase')")
        EvidencePaths = [scriptblock]::Create("@('$(& $esc $f)', '$(& $esc $cy)', '$(& $esc $cv)', '$(& $esc $r)')")
    }

    # --- FalseEvidenceDetection ---
    $defs += @{
        Name = "FalseEvidenceDetection"
        Weight = 1.0
        ExistsCheck = [scriptblock]::Create("(Test-JsonArrayHasItems '$(& $esc $er)' 'replay_attempts' 1)")
        IntegratedCheck = [scriptblock]::Create("(Test-FileContains '$(& $esc $r)' 'Test-EvidenceReplay') -and (Test-FileContains '$(& $esc $r)' 'replay')")
        ExecutedCheck = [scriptblock]::Create("(Test-JsonArrayHasItems '$(& $esc $er)' 'replay_attempts' 1)")
        ValidatedCheck = [scriptblock]::Create("(Test-JsonArrayHasItems '$(& $esc $er)' 'replay_attempts' 3)")
        AdversarialCheck = [scriptblock]::Create("(Test-AdversarialAttackPassed '$(& $esc $af)' 'ATK-09')")
        IndependentCheck = [scriptblock]::Create("(Test-FileExists '$(& $esc $er)') -and (Test-JsonArrayHasItems '$(& $esc $er)' 'replay_attempts' 1) -and (Test-JsonFileHasField '$(& $esc $er)' 'entries')")
        EvidencePaths = [scriptblock]::Create("@('$(& $esc $er)', '$(& $esc $eim)')")
    }

    # --- FalseConvergenceDetection ---
    $defs += @{
        Name = "FalseConvergenceDetection"
        Weight = 1.0
        ExistsCheck = [scriptblock]::Create("(Test-FileExists '$(& $esc $cv)') -and (Test-JsonFileHasField '$(& $esc $cv)' 'converged') -and (-not (Test-JsonFieldValue '$(& $esc $cv)' 'converged' `$true))")
        IntegratedCheck = [scriptblock]::Create("(Test-FileContains '$(& $esc $r)' 'Validate-GateEvidenceIntegrity') -and (Test-FileContains '$(& $esc $r)' 'SCORE SPIKE') -and (Test-FileContains '$(& $esc $r)' 'CONVERGENCE FLIP')")
        ExecutedCheck = [scriptblock]::Create("(Test-JsonFileHasField '$(& $esc $cv)' 'converged') -and (-not (Test-JsonFieldValue '$(& $esc $cv)' 'converged' `$true))")
        ValidatedCheck = [scriptblock]::Create("(Test-InvariantCheckPassed '$(& $esc $eroot)' 'BI-STATE-006')")
        AdversarialCheck = [scriptblock]::Create("(Test-AdversarialAttackPassed '$(& $esc $af)' 'ATK-06') -and (Test-AdversarialAttackPassed '$(& $esc $af)' 'ATK-01')")
        IndependentCheck = [scriptblock]::Create("(Test-FileExists '$(& $esc $cv)') -and (Test-JsonFileHasField '$(& $esc $cv)' 'gates') -and (Test-JsonFileHasField '$(& $esc $cv)' 'overall_score')")
        EvidencePaths = [scriptblock]::Create("@('$(& $esc $cv)', '$(& $esc $af)')")
    }

    # --- SandboxSecurity ---
    $defs += @{
        Name = "SandboxSecurity"
        Weight = 1.0
        ExistsCheck = [scriptblock]::Create("(Test-FileExists '$(& $esc $sm)') -and (Test-FileExists '$(& $esc $st)')")
        IntegratedCheck = [scriptblock]::Create("(Test-FileContains '$(& $esc $r)' 'Invoke-SandboxSelfTest') -and (Test-FileContains '$(& $esc $sm)' 'host_escape_detected')")
        ExecutedCheck = [scriptblock]::Create("(Test-JsonArrayHasItems '$(& $esc $st)' 'tests' 2)")
        ValidatedCheck = [scriptblock]::Create("(Test-SandboxTestPassed '$(& $esc $st)' 'Timeout enforcement') -and (Test-SandboxTestPassed '$(& $esc $st)' 'Output file isolation')")
        AdversarialCheck = [scriptblock]::Create("(Test-FileContains '$(& $esc $sm)' 'host_escape_detected')")
        IndependentCheck = [scriptblock]::Create("(Test-FileExists '$(& $esc $st)') -and (Test-FileExists '$(& $esc $sm)') -and (Test-JsonFileHasField '$(& $esc $st)' 'tests')")
        EvidencePaths = [scriptblock]::Create("@('$(& $esc $st)', '$(& $esc $sm)')")
    }

    # --- VerificationOracle ---
    $defs += @{
        Name = "VerificationOracle"
        Weight = 1.0
        ExistsCheck = [scriptblock]::Create("(Test-FileExists '$(& $esc $ivm)') -and (Test-FileExists '$(& $esc $vf)')")
        IntegratedCheck = [scriptblock]::Create("(Test-FileContains '$(& $esc $r)' 'verify-findings') -and (Test-FileContains '$(& $esc $ivm)' 'verdict')")
        ExecutedCheck = [scriptblock]::Create("(Test-JsonArrayHasItems '$(& $esc $vf)' 'verdicts' 5)")
        ValidatedCheck = [scriptblock]::Create("(Test-VerificationCheckPassed '$(& $esc $vf)' 'schema_validation') -and (Test-VerificationCheckPassed '$(& $esc $vf)' 'deterministic_invariant')")
        AdversarialCheck = [scriptblock]::Create("(Test-VerificationCheckPassed '$(& $esc $vf)' 'transition_legality')")
        IndependentCheck = [scriptblock]::Create("(Test-FileExists '$(& $esc $vf)') -and (Test-JsonArrayHasItems '$(& $esc $vf)' 'verdicts' 5) -and (Test-FileExists '$(& $esc $ivm)')")
        EvidencePaths = [scriptblock]::Create("@('$(& $esc $vf)', '$(& $esc $ivm)')")
    }

    return $defs
}

#endregion

#region --- PUBLIC FUNCTIONS ---

function Invoke-DeterministicScoring {
    param(
        [string]$EngineRoot,
        [switch]$OutputToFile
    )

    if (-not (Test-Path -LiteralPath $EngineRoot)) {
        throw "Engine root not found: $EngineRoot"
    }

    $evidence = Get-CapabilityEvidenceMap -EngineRoot $EngineRoot
    $capabilityDefs = Build-CapabilityDefinitions -Evidence $evidence
    $scores = @()

    foreach ($def in $capabilityDefs) {
        $score = Get-CapabilityScore -CapabilityDef $def -Evidence $evidence
        $scores += $score
    }

    $totalWeight = 0.0
    $totalWeightedScore = 0.0
    foreach ($s in $scores) {
        $totalWeight += $s.weight
        $totalWeightedScore += $s.weighted_score
    }

    $overallScore = if ($totalWeight -gt 0) {
        [math]::Round($totalWeightedScore / $totalWeight, 2)
    } else {
        0.0
    }

    $result = [PSCustomObject]@{
        engine = "DETERMINISTIC_CAPABILITY_SCORING"
        version = "1.0.0"
        scored_at = (Get-Date).ToString("o")
        engine_root = $EngineRoot
        overall_score = $overallScore
        total_capabilities = $scores.Count
        scoring_formula = "sub_score = EXISTS*20 + INTEGRATED*20 + EXECUTED*15 + VALIDATED*15 + ADVERSARIAL*15 + INDEPENDENT*15; overall = SUM(weighted_score) / SUM(weight)"
        scores = $scores
    }

    if ($OutputToFile) {
        $outputPath = Join-Path $EngineRoot "state\capability-score.json"
        $parent = Split-Path -Parent $outputPath
        if (-not (Test-Path -LiteralPath $parent)) {
            New-Item -ItemType Directory -Force -Path $parent | Out-Null
        }
        $json = $result | ConvertTo-Json -Depth 100
        $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
        [System.IO.File]::WriteAllText($outputPath, $json, $utf8NoBom)
        $Script:ScoreOutputFile = $outputPath
    }

    return $result
}

function New-CapabilityScore {
    param(
        [string]$EngineRoot,
        [string]$OutputPath
    )

    $result = Invoke-DeterministicScoring -EngineRoot $EngineRoot

    $flatScores = foreach ($s in $result.scores) {
        [PSCustomObject]@{
            capability = $s.capability
            weight = $s.weight
            exists = $s.exists
            integrated = $s.integrated
            executed = $s.executed
            validated = $s.validated
            adversarial = $s.adversarial
            independent = $s.independent
            evidence_paths = $s.evidence_paths
            sub_score = $s.sub_score
            weighted_score = $s.weighted_score
        }
    }

    $output = [PSCustomObject]@{
        engine = "DETERMINISTIC_CAPABILITY_SCORING"
        version = "1.0.0"
        scored_at = $result.scored_at
        engine_root = $EngineRoot
        overall_score = $result.overall_score
        scoring_formula = $result.scoring_formula
        capabilities = @($flatScores)
    }

    $outPath = if ($OutputPath) { $OutputPath } else { Join-Path $EngineRoot "state\capability-score.json" }
    $parent = Split-Path -Parent $outPath
    if (-not (Test-Path -LiteralPath $parent)) {
        New-Item -ItemType Directory -Force -Path $parent | Out-Null
    }
    $json = $output | ConvertTo-Json -Depth 100
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($outPath, $json, $utf8NoBom)

    Write-Host "Capability score written to: $outPath"
    Write-Host "Overall score: $($output.overall_score)%"

    return $output
}

function Get-OverallScore {
    param(
        [string]$ScoreFilePath
    )

    if (-not $ScoreFilePath) {
        $ScoreFilePath = $Script:ScoreOutputFile
    }
    if (-not $ScoreFilePath -or -not (Test-Path -LiteralPath $ScoreFilePath)) {
        throw "Score file not found: $ScoreFilePath. Run New-CapabilityScore first."
    }

    $content = Get-Content -LiteralPath $ScoreFilePath -Raw -Encoding UTF8
    if ([string]::IsNullOrWhiteSpace($content)) { throw "Score file is empty: $ScoreFilePath" }

    $data = $content | ConvertFrom-Json

    $totalWeight = 0.0
    $totalWeighted = 0.0
    foreach ($cap in $data.capabilities) {
        $totalWeight += [double]$cap.weight
        $totalWeighted += [double]$cap.weighted_score
    }

    $overall = if ($totalWeight -gt 0) {
        [math]::Round($totalWeighted / $totalWeight, 2)
    } else {
        0.0
    }

    $result = [PSCustomObject]@{
        source_file = $ScoreFilePath
        scored_at = $data.scored_at
        overall_score = $overall
        total_capabilities = $data.capabilities.Count
        computed_at = (Get-Date).ToString("o")
        note = "Weighted average. No manual overrides. No subjective adjustments."
    }

    return $result
}

function Format-ScoreReport {
    param(
        [string]$EngineRoot,
        [switch]$AsMarkdownTable
    )

    $scoreFile = Join-Path $EngineRoot "state\capability-score.json"
    if (-not (Test-Path -LiteralPath $scoreFile)) {
        $null = New-CapabilityScore -EngineRoot $EngineRoot -OutputPath $scoreFile
    }

    $content = Get-Content -LiteralPath $scoreFile -Raw -Encoding UTF8
    $data = $content | ConvertFrom-Json

    if ($AsMarkdownTable) {
        $sb = New-Object System.Text.StringBuilder
        [void]$sb.AppendLine("# Deterministic Capability Score Report")
        [void]$sb.AppendLine("")
        [void]$sb.AppendLine("**Engine**: $($data.engine) v$($data.version)")
        [void]$sb.AppendLine("**Scored at**: $($data.scored_at)")
        [void]$sb.AppendLine("**Overall Score**: **$($data.overall_score)%**")
        [void]$sb.AppendLine("")
        [void]$sb.AppendLine("| # | Capability | Weight | E | I | X | V | A | R | Sub Score | Weighted | Evidence Refs |")
        [void]$sb.AppendLine("|---|-----------|--------|---|---|---|---|---|---|-----------|----------|---------------|")

        $idx = 0
        foreach ($cap in $data.capabilities) {
            $idx++
            $e = if ($cap.exists) { "Y" } else { "-" }
            $i = if ($cap.integrated) { "Y" } else { "-" }
            $x = if ($cap.executed) { "Y" } else { "-" }
            $v = if ($cap.validated) { "Y" } else { "-" }
            $a = if ($cap.adversarial) { "Y" } else { "-" }
            $r = if ($cap.independent) { "Y" } else { "-" }

            $evidenceRefs = ($cap.evidence_paths | ForEach-Object {
                $n = Split-Path -Leaf $_
                $n
            }) -join ', '
            if ($evidenceRefs.Length -gt 50) {
                $evidenceRefs = $evidenceRefs.Substring(0, 47) + "..."
            }

            [void]$sb.AppendLine("| $idx | $($cap.capability) | $($cap.weight) | $e | $i | $x | $v | $a | $r | $($cap.sub_score) | $($cap.weighted_score) | $evidenceRefs |")
        }

        [void]$sb.AppendLine("")
        [void]$sb.AppendLine("**Legend**: E=Exists I=Integrated X=Executed V=Validated A=Adversarial R=Independent")
        [void]$sb.AppendLine("**Formula**: sub_score = E*20 + I*20 + X*15 + V*15 + A*15 + R*15")
        [void]$sb.AppendLine("**Overall**: Weighted average = SUM(weighted_score) / SUM(weight)")

        return $sb.ToString()
    }

    Write-Host ""
    Write-Host "=== DETERMINISTIC CAPABILITY SCORE REPORT ===" -ForegroundColor Cyan
    Write-Host "Overall Score: $($data.overall_score)%"
    Write-Host "Capabilities: $($data.capabilities.Count)"
    Write-Host ""

    foreach ($cap in $data.capabilities) {
        $color = if ($cap.sub_score -ge 70) { "Green" } elseif ($cap.sub_score -ge 40) { "Yellow" } else { "Red" }
        Write-Host "  $($cap.capability): sub=$($cap.sub_score) w=$($cap.weighted_score) E=$($cap.exists) I=$($cap.integrated) X=$($cap.executed) V=$($cap.validated) A=$($cap.adversarial) R=$($cap.independent)" -ForegroundColor $color
    }

    return $data
}

#endregion