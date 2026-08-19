# ============================================================
# EVIDENCE INTEGRITY ENGINE v1.0.0
# Hash-based evidence validation, replay detection, freshness
# checks, evidence-to-finding binding, evidence-to-cycle binding.
# ============================================================

$Script:EvidenceRegistryFile = $null

function Initialize-EvidenceEngine {
    param([string]$EngineRoot)
    $Script:EvidenceRegistryFile = Join-Path $EngineRoot "state\evidence-registry.json"
    if (-not (Test-Path -LiteralPath $Script:EvidenceRegistryFile)) {
        $parent = Split-Path -Parent $Script:EvidenceRegistryFile
        if (-not (Test-Path -LiteralPath $parent)) {
            New-Item -ItemType Directory -Force -Path $parent | Out-Null
        }
        $registry = @{
            version = "1.0.0"
            created_at = (Get-Date).ToString("o")
            entries = @{}
            replay_attempts = @()
        }
        $json = $registry | ConvertTo-Json -Depth 100
        $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
        [System.IO.File]::WriteAllText($Script:EvidenceRegistryFile, $json, $utf8NoBom)
    }
    return $Script:EvidenceRegistryFile
}

function Read-EvidenceRegistry {
    param([string]$RegistryPath)
    if (-not $RegistryPath) { $RegistryPath = $Script:EvidenceRegistryFile }
    if (-not (Test-Path -LiteralPath $RegistryPath)) { return $null }
    try {
        $content = Get-Content -LiteralPath $RegistryPath -Raw -Encoding UTF8
        if ([string]::IsNullOrWhiteSpace($content)) { return $null }
        return $content | ConvertFrom-Json
    } catch {
        Write-Warning "Read-EvidenceRegistry: Malformed registry. Error: $_"
        return $null
    }
}

function Write-EvidenceRegistry {
    param([string]$RegistryPath, [PSCustomObject]$RegistryData)
    if (-not $RegistryPath) { $RegistryPath = $Script:EvidenceRegistryFile }
    $parent = Split-Path -Parent $RegistryPath
    if (-not (Test-Path -LiteralPath $parent)) {
        New-Item -ItemType Directory -Force -Path $parent | Out-Null
    }
    $tempPath = "$RegistryPath.tmp.$( [System.Guid]::NewGuid().ToString('N').Substring(0,8) )"
    try {
        $json = $RegistryData | ConvertTo-Json -Depth 100
        $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
        [System.IO.File]::WriteAllText($tempPath, $json, $utf8NoBom)
        Move-Item -LiteralPath $tempPath -Destination $RegistryPath -Force
    } catch {
        if (Test-Path -LiteralPath $tempPath) {
            Remove-Item -LiteralPath $tempPath -Force -ErrorAction SilentlyContinue
        }
        throw
    }
}

function Get-EvidenceHash {
    param(
        [string]$Content,
        [string]$Algorithm = "SHA256"
    )
    if ([string]::IsNullOrEmpty($Content)) { return $null }
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($Content)
    $hasher = [System.Security.Cryptography.HashAlgorithm]::Create($Algorithm)
    if (-not $hasher) { return $null }
    $hashBytes = $hasher.ComputeHash($bytes)
    return [BitConverter]::ToString($hashBytes) -replace '-', ''
}

function New-EvidenceArtifact {
    param(
        [string]$Command,
        [string]$CommandArgs,
        [int]$ExitCode,
        [string]$Stdout,
        [string]$Stderr,
        [string]$ArtifactPath,
        [string]$ArtifactHash,
        [int]$Cycle,
        [string]$CommitHash,
        [string]$WorkspaceId,
        [string]$FindingId,
        [string[]]$FindingIds
    )

    $timestamp = (Get-Date).ToString("o")
    $stdoutHash = if ($Stdout) { Get-EvidenceHash -Content $Stdout } else { "" }
    $stderrHash = if ($Stderr) { Get-EvidenceHash -Content $Stderr } else { "" }

    $canonicalContent = @(
        "COMMAND=$Command"
        "EXIT_CODE=$ExitCode"
        "STDOUT_HASH=$stdoutHash"
        "STDERR_HASH=$stderrHash"
        "CYCLE=$Cycle"
        "COMMIT=$CommitHash"
        "TIMESTAMP=$timestamp"
        "WORKSPACE=$WorkspaceId"
    ) -join "`n"

    $evidenceHash = Get-EvidenceHash -Content $canonicalContent

    if ($FindingId -and -not $FindingIds) { $FindingIds = @($FindingId) }

    return @{
        command = $Command
        command_args = $CommandArgs
        exit_code = $ExitCode
        stdout_hash = $stdoutHash
        stderr_hash = $stderrHash
        artifact_path = $ArtifactPath
        artifact_hash = $ArtifactHash
        cycle = $Cycle
        commit_hash = $CommitHash
        workspace_id = $WorkspaceId
        timestamp = $timestamp
        finding_ids = @($FindingIds)
        evidence_hash = $evidenceHash
        evidence_version = "1.0.0"
    }
}

function Test-EvidenceReplay {
    param(
        [string]$EvidenceHash,
        [string]$RegistryPath
    )
    if (-not $EvidenceHash) { return $false }

    $registry = Read-EvidenceRegistry -RegistryPath $RegistryPath
    if (-not $registry -or -not $registry.entries) { return $false }

    $normalizedHash = $EvidenceHash.ToUpperInvariant()
    foreach ($key in $registry.entries.PSObject.Properties.Name) {
        if ($key.ToUpperInvariant() -eq $normalizedHash) { return $true }
    }
    return $false
}

function Test-EvidenceFreshness {
    param(
        [PSCustomObject]$EvidenceArtifact,
        [int]$CurrentCycle,
        [int]$MaxAgeCycles = 1
    )
    if (-not $EvidenceArtifact) { return $false }
    $evidenceCycle = if ($EvidenceArtifact.cycle) { [int]$EvidenceArtifact.cycle } else { 0 }
    if ($evidenceCycle -le 0) { return $false }
    return ($CurrentCycle - $evidenceCycle) -lt $MaxAgeCycles
}

function Test-EvidenceBinding {
    param(
        [PSCustomObject]$EvidenceArtifact,
        [string]$FindingId,
        [int]$ExpectedCycle
    )
    if (-not $EvidenceArtifact -or -not $FindingId) { return $false }

    if ($EvidenceArtifact.finding_ids -and $FindingId -in $EvidenceArtifact.finding_ids) {
        if ($ExpectedCycle -gt 0 -and $EvidenceArtifact.cycle -ne $ExpectedCycle) { return $false }
        return $true
    }
    return $false
}

function Register-Evidence {
    param(
        [PSCustomObject]$EvidenceArtifact,
        [string]$RegistryPath
    )
    if (-not $EvidenceArtifact -or -not $EvidenceArtifact.evidence_hash) {
        Write-Warning "Register-Evidence: Cannot register evidence without hash."
        return $false
    }

    $registry = Read-EvidenceRegistry -RegistryPath $RegistryPath
    if (-not $registry) {
        $registry = @{
            version = "1.0.0"
            created_at = (Get-Date).ToString("o")
            entries = @{}
            replay_attempts = @()
        }
    }

    $hash = $EvidenceArtifact.evidence_hash.ToUpperInvariant()

    if ($registry.entries -is [PSCustomObject]) {
        $entries = @{}
        foreach ($prop in $registry.entries.PSObject.Properties) {
            $entries[$prop.Name] = $prop.Value
        }
    } else {
        $entries = @{}
    }

    if ($entries.ContainsKey($hash)) {
        $replayRecord = @{
            hash = $hash
            original_cycle = $entries[$hash].cycle
            attempt_cycle = $EvidenceArtifact.cycle
            attempt_timestamp = (Get-Date).ToString("o")
            finding_ids = $EvidenceArtifact.finding_ids
        }
        if (-not $registry.replay_attempts) { $registry.replay_attempts = @() }
        $registry.replay_attempts += $replayRecord
        Write-Warning "Register-Evidence: REPLAY DETECTED for hash $hash (originally cycle $($entries[$hash].cycle), attempted cycle $($EvidenceArtifact.cycle))"
        Write-EvidenceRegistry -RegistryPath $RegistryPath -RegistryData $registry
        return $false
    }

    $entry = @{}
    foreach ($prop in $EvidenceArtifact.PSObject.Properties) {
        $entry[$prop.Name] = $prop.Value
    }
    $entries[$hash] = $entry
    $registry.entries = $entries

    Write-EvidenceRegistry -RegistryPath $RegistryPath -RegistryData $registry
    return $true
}

function Test-EvidenceIntegrity {
    param(
        [PSCustomObject]$EvidenceArtifact,
        [string]$ExpectedCommand,
        [int]$ExpectedCycle,
        [string]$ExpectedCommit,
        [string]$ExpectedStdoutHash,
        [string]$ExpectedStderrHash,
        [hashtable]$CommandResults
    )

    $violations = @()

    if (-not $EvidenceArtifact) {
        $violations += "EVIDENCE: No evidence artifact provided."
        return $violations
    }

    if (-not $EvidenceArtifact.evidence_hash) {
        $violations += "EVIDENCE: Evidence artifact missing hash."
    }

    if ($EvidenceArtifact.cycle -ne $ExpectedCycle) {
        $violations += "EVIDENCE: Cycle mismatch (evidence=$($EvidenceArtifact.cycle), expected=$ExpectedCycle). Evidence from wrong cycle."
    }

    if ($EvidenceArtifact.command -ne $ExpectedCommand) {
        $violations += "EVIDENCE: Command mismatch (evidence='$($EvidenceArtifact.command)', expected='$ExpectedCommand')."
    }

    if ($EvidenceArtifact.stdout_hash -ne $ExpectedStdoutHash) {
        $violations += "EVIDENCE: Stdout hash mismatch. Evidence may be fabricated or corrupted."
    }

    if ($EvidenceArtifact.stderr_hash -ne $ExpectedStderrHash) {
        $violations += "EVIDENCE: Stderr hash mismatch."
    }

    if ($EvidenceArtifact.exit_code -ne $CommandResults.exit_code) {
        $violations += "EVIDENCE: Exit code mismatch (evidence=$($EvidenceArtifact.exit_code), actual=$($CommandResults.exit_code))."
    }

    return $violations
}

function New-EvidenceFromToolingResults {
    param(
        [hashtable]$ToolingResults,
        [int]$Cycle,
        [string]$CommitHash,
        [string]$WorkspaceId,
        [string[]]$FindingIds
    )

    $artifacts = @()
    foreach ($cmdName in $ToolingResults.Keys | Sort-Object) {
        $result = $ToolingResults[$cmdName]
        $artifact = New-EvidenceArtifact `
            -Command $cmdName `
            -CommandArgs "" `
            -ExitCode ([int]$result.exit_code) `
            -Stdout ([string]$result.output) `
            -Stderr "" `
            -Cycle $Cycle `
            -CommitHash $CommitHash `
            -WorkspaceId $WorkspaceId `
            -FindingIds $FindingIds
        $artifacts += $artifact
    }
    return $artifacts
}

function Write-EvidenceFile {
    param(
        [string]$FilePath,
        [PSCustomObject]$EvidenceData
    )
    $parent = Split-Path -Parent $FilePath
    if (-not (Test-Path -LiteralPath $parent)) {
        New-Item -ItemType Directory -Force -Path $parent | Out-Null
    }
    $json = $EvidenceData | ConvertTo-Json -Depth 100
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($FilePath, $json, $utf8NoBom)
}

function Read-EvidenceFile {
    param([string]$FilePath)
    if (-not (Test-Path -LiteralPath $FilePath)) { return $null }
    try {
        $content = Get-Content -LiteralPath $FilePath -Raw -Encoding UTF8
        if ([string]::IsNullOrWhiteSpace($content)) { return $null }
        return $content | ConvertFrom-Json
    } catch {
        Write-Warning "Read-EvidenceFile: Malformed evidence file at $FilePath. Error: $_"
        return $null
    }
}