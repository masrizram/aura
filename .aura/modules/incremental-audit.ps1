# ============================================================
# INCREMENTAL AUDIT ENGINE v1.0.0
# Purpose: Differential/incremental audit instead of full-spectrum
# every cycle. Computes file priority scores and scope plans.
# Classification: OPTIONAL
# ============================================================

$Script:_IncrementalCacheFile = $null
$Script:_IncrementalRoot = $null

function Get-ChangedFilesSinceLastAudit {
    <#
    .SYNOPSIS
        Returns list of files changed since last audit commit.
    .DESCRIPTION
        Uses git diff to enumerate files modified, added, deleted, or
        renamed since the commit recorded in the audit cache.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepoPath,

        [Parameter(Mandatory = $true)]
        [string]$LastAuditCommit
    )

    $changed = @()
    $null = Get-Command git -ErrorAction Stop
    $cwd = Get-Location

    try {
        Set-Location -LiteralPath $RepoPath

        $diffOutput = git diff --name-status $LastAuditCommit HEAD 2>&1
        if ($LASTEXITCODE -ne 0) {
            $diffOutput = git diff --name-status HEAD~1 HEAD 2>&1
        }
        if ($LASTEXITCODE -ne 0) {
            $changed = @(git ls-files 2>&1)
            if ($LASTEXITCODE -ne 0) { return @() }
        }

        if ($diffOutput -is [string]) {
            $lines = $diffOutput -split "`n" | Where-Object { $_ -and $_ -ne "" }
        } else {
            $lines = $diffOutput
        }

        foreach ($line in $lines) {
            $trimmed = $line.Trim()
            if (-not $trimmed) { continue }
            $parts = $trimmed -split "\s+", 2
            if ($parts.Count -ge 2) {
                $status = $parts[0]
                $file   = $parts[1]
                $changed += @{
                    file = $file
                    status = $status
                }
            }
        }
    } catch {
        Write-Warning "Get-ChangedFilesSinceLastAudit: git error: $_"
    } finally {
        Set-Location $cwd.Path
    }

    return $changed
}

function Get-FileChangeType {
    <#
    .SYNOPSIS
        Returns the type of change for a specific file.
    .DESCRIPTION
        Uses git log and diff to classify a file change type since
        a base commit: added, modified, deleted, renamed, or unchanged.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepoPath,

        [Parameter(Mandatory = $true)]
        [string]$File,

        [Parameter(Mandatory = $true)]
        [string]$BaseCommit
    )

    $null = Get-Command git -ErrorAction Stop
    $cwd = Get-Location

    try {
        Set-Location -LiteralPath $RepoPath

        $statusOutput = git diff --name-status $BaseCommit HEAD -- $File 2>&1
        if ($LASTEXITCODE -ne 0) {
            $statusOutput = git diff --name-status HEAD~1 HEAD -- $File 2>&1
        }
        if ($LASTEXITCODE -ne 0) {
            return "unknown"
        }

        $statusTrimmed = ($statusOutput -is [array] ? ($statusOutput -join "`n") : [string]$statusOutput).Trim()
        if (-not $statusTrimmed) {
            return "unchanged"
        }

        $firstChar = $statusTrimmed[0]
        switch ($firstChar) {
            "A" { return "added" }
            "M" { return "modified" }
            "D" { return "deleted" }
            "R" { return "renamed" }
            "C" { return "copied" }
            "T" { return "type-changed" }
            default { return "modified" }
        }
    } catch {
        Write-Warning "Get-FileChangeType: git error: $_"
        return "unknown"
    } finally {
        Set-Location $cwd.Path
    }
}

function Get-FileChurnScore {
    <#
    .SYNOPSIS
        Returns churn score (0-100) based on commit frequency in last N days.
    .DESCRIPTION
        High churn = frequently changed files = higher risk.
        Uses git log to count commits touching the file in the window.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepoPath,

        [Parameter(Mandatory = $true)]
        [string]$File,

        [int]$WindowDays = 90
    )

    $null = Get-Command git -ErrorAction Stop
    $cwd = Get-Location

    try {
        Set-Location -LiteralPath $RepoPath

        $sinceDate = (Get-Date).AddDays(-$WindowDays).ToString("yyyy-MM-dd")
        $commitCount = (git log --oneline --since=$sinceDate -- $File 2>&1 | Measure-Object).Count

        if ($LASTEXITCODE -ne 0 -or $commitCount -eq 0) {
            return 0
        }

        $totalCommits = (git log --oneline 2>&1 | Measure-Object).Count
        if ($totalCommits -eq 0) { return 0 }

        $maxChurnPerFile = [math]::Max(1, [math]::Round($totalCommits * 0.1))
        $score = [math]::Min(100, [math]::Round(($commitCount / $maxChurnPerFile) * 100))
        return [math]::Max(5, $score)
    } catch {
        Write-Warning "Get-FileChurnScore: git error: $_"
        return 25
    } finally {
        Set-Location $cwd.Path
    }
}

function Get-FileCriticalityScore {
    <#
    .SYNOPSIS
        Returns criticality score (0-100) based on architectural role.
    .DESCRIPTION
        - Entry points (main files, route files, controllers) = high
        - High fan-in modules (many importers/dependents) = high
        - Config files = high
        - Test files = low
        - Markdown/docs = very low
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepoPath,

        [Parameter(Mandatory = $true)]
        [string]$File,

        [PSCustomObject]$GraphData
    )

    $normalized = $File.Replace("\", "/").TrimStart("/")
    $fileName = [System.IO.Path]::GetFileName($normalized)
    $ext = [System.IO.Path]::GetExtension($normalized).ToLowerInvariant()
    $dir = [System.IO.Path]::GetDirectoryName($normalized).Replace("\", "/").ToLowerInvariant()

    $score = 30

    if ($fileName -match '^(index|main|app|server|bootstrap|startup|kernel|init|run)') {
        $score += 35
    }
    elseif ($dir -match '(controller|route|handler|middleware|service|resolver|endpoint|api)') {
        $score += 25
    }

    if ($dir -match '(config|settings|env|secrets)') {
        $score += 20
    }
    if ($fileName -match '(config|settings|env|secret|\.env\.|\.config\.)') {
        $score += 20
    }

    if ($fileName -match '(composer\.json|package\.json|pyproject\.toml|Cargo\.toml|go\.mod|Makefile|Dockerfile|docker-compose)') {
        $score += 30
    }

    if ($dir -match '(test|spec|__tests__|t/|spec/)') {
        $score -= 25
    }
    if ($fileName -match '(test|spec|\.test\.|\.spec\.|_test\.)') {
        $score -= 25
    }

    if ($ext -in @('.md', '.txt', '.rst', '.adoc')) {
        $score -= 20
    }

    if ($GraphData -and $GraphData.dependency_graph) {
        $dependents = 0
        if ($GraphData.dependency_graph -is [PSCustomObject]) {
            foreach ($depKey in $GraphData.dependency_graph.PSObject.Properties.Name) {
                $deps = $GraphData.dependency_graph.$depKey
                if ($deps) {
                    foreach ($d in $deps) {
                        if ($d.file -and $d.file -like "*$fileName*") {
                            $dependents++
                        }
                    }
                }
            }
        } elseif ($GraphData.dependency_graph -is [hashtable]) {
            foreach ($depKey in $GraphData.dependency_graph.Keys) {
                $deps = $GraphData.dependency_graph[$depKey]
                if ($deps) {
                    foreach ($d in $deps) {
                        if ($d.file -and $d.file -like "*$fileName*") {
                            $dependents++
                        }
                    }
                }
            }
        }

        if ($dependents -ge 10) {
            $score += 25
        } elseif ($dependents -ge 5) {
            $score += 15
        } elseif ($dependents -ge 2) {
            $score += 8
        }
    }

    $entryPointPatterns = @(
        '^\s*function main\b', '^\s*if __name__\s*==\s*["\x27]__main__["\x27]',
        '^\s*public static void main\b', '^\s*func main\(\)',
        '\bentry_point\b', '\bconsole_command\b', '\bhandle\(\)'
    )

    $fullPath = Join-Path $RepoPath $normalized
    if (Test-Path -LiteralPath $fullPath) {
        try {
            $content = Get-Content -LiteralPath $fullPath -Raw -Encoding UTF8 -ErrorAction SilentlyContinue
            if ($content) {
                foreach ($pattern in $entryPointPatterns) {
                    if ($content -match $pattern) {
                        $score += 10
                        break
                    }
                }
            }
        } catch { }
    }

    return [math]::Max(5, [math]::Min(100, $score))
}

function Get-BugDensityScore {
    <#
    .SYNOPSIS
        Returns bug density score (0-100) based on prior findings.
    .DESCRIPTION
        Files with P0-P2 findings in past cycles get higher scores.
        Files authored by developers with higher bug rates get higher scores.
        Score decays slightly over cycles to allow rehabilitation.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepoPath,

        [Parameter(Mandatory = $true)]
        [string]$File,

        [int]$CycleNumber,

        [string]$EngineRoot
    )

    $score = 0
    $normalized = $File.Replace("\", "/").TrimStart("/")

    if ($EngineRoot) {
        $findingsPath = Join-Path $EngineRoot "state/findings.json"
        if (Test-Path -LiteralPath $findingsPath) {
            try {
                $content = Get-Content -LiteralPath $findingsPath -Raw -Encoding UTF8
                if ($content) {
                    $findings = $content | ConvertFrom-Json
                    if ($findings -and $findings.findings) {
                        $fileFindings = @($findings.findings | Where-Object {
                            $_.file -and ($_.file -like "*$normalized*")
                        })

                        foreach ($f in $fileFindings) {
                            switch ($f.severity) {
                                "P0" { $score += 30 }
                                "P1" { $score += 20 }
                                "P2" { $score += 12 }
                                "P3" { $score += 6 }
                                "P4" { $score += 3 }
                                "P5" { $score += 1 }
                            }
                        }

                        $recentFindings = @($fileFindings | Where-Object {
                            $_.cycle_number -and ($CycleNumber - ($_.cycle_number -as [int])) -le 3
                        })
                        if ($recentFindings.Count -gt 0) {
                            $score = [math]::Min(100, $score + ($recentFindings.Count * 8))
                        }

                        $oldFindings = @($fileFindings | Where-Object {
                            $_.cycle_number -and ($CycleNumber - ($_.cycle_number -as [int])) -gt 5
                        })
                        if ($oldFindings.Count -gt 0) {
                            $score = [math]::Max(0, $score - ($oldFindings.Count * 5))
                        }
                    }
                }
            } catch { }
        }

        $archiveDir = Join-Path $EngineRoot "archive"
        if (Test-Path -LiteralPath $archiveDir) {
            try {
                $archiveFindings = Get-ChildItem -LiteralPath $archiveDir -Filter "proposed-findings-*.json" -File -ErrorAction SilentlyContinue |
                    Sort-Object LastWriteTime -Descending |
                    Select-Object -First 5

                foreach ($af in $archiveFindings) {
                    try {
                        $afContent = Get-Content -LiteralPath $af.FullName -Raw -Encoding UTF8
                        if ($afContent) {
                            $afData = $afContent | ConvertFrom-Json
                            if ($afData -and $afData.findings) {
                                $archFindings = @($afData.findings | Where-Object {
                                    $_.file -and ($_.file -like "*$normalized*") -and
                                    $_.severity -in @("P0","P1","P2")
                                })
                                $score += ($archFindings.Count * 4)
                            }
                        }
                    } catch { }
                }
            } catch { }
        }
    }

    return [math]::Max(0, [math]::Min(100, $score))
}

function Get-AuditPriority {
    <#
    .SYNOPSIS
        Combines churn + criticality + bug_density into priority score.
    .DESCRIPTION
        Returns sorted list of files with priority scores.
        Tier 1 (score >= 70): Must audit this cycle
        Tier 2 (score 40-69): Audit if time permits
        Tier 3 (score < 40): Can defer
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepoPath,

        [Parameter(Mandatory = $true)]
        [string[]]$Files,

        [PSCustomObject]$GraphData,

        [int]$CycleNumber,

        [string]$EngineRoot,

        [hashtable]$Weights = @{
            churn_weight = 0.35
            criticality_weight = 0.40
            bug_density_weight = 0.15
            author_bug_rate_weight = 0.10
        }
    )

    $results = @()

    foreach ($file in $Files) {
        $churn = Get-FileChurnScore -RepoPath $RepoPath -File $file
        $criticality = Get-FileCriticalityScore -RepoPath $RepoPath -File $file -GraphData $GraphData
        $bugDensity = Get-BugDensityScore -RepoPath $RepoPath -File $file -CycleNumber $CycleNumber -EngineRoot $EngineRoot
        $authorBug = 0

        try {
            $authorRates = Get-AuthorBugRate -RepoPath $RepoPath
            if ($authorRates -and $authorRates.Count -gt 0) {
                $cwd = Get-Location
                Set-Location -LiteralPath $RepoPath
                $lastAuthorOutput = git log -1 --format="%ae" -- $file 2>&1
                Set-Location $cwd.Path
                if ($LASTEXITCODE -eq 0 -and $lastAuthorOutput) {
                    $email = $lastAuthorOutput.Trim()
                    if ($authorRates.ContainsKey($email)) {
                        $authorBug = [math]::Round($authorRates[$email] * 100, 1)
                    }
                }
            }
        } catch { }

        $combined = [math]::Round(
            ($churn * $Weights.churn_weight) +
            ($criticality * $Weights.criticality_weight) +
            ($bugDensity * $Weights.bug_density_weight) +
            ($authorBug * $Weights.author_bug_rate_weight),
            1
        )

        if ($combined -ge 70) {
            $tier = "tier_1"
            $reason = "High priority: combined score >= 70"
        } elseif ($combined -ge 40) {
            $tier = "tier_2"
            $reason = "Medium priority: combined score 40-69"
        } else {
            $tier = "tier_3"
            $reason = "Low priority: combined score < 40"
        }

        $results += [PSCustomObject]@{
            file = $file
            churn_score = $churn
            criticality_score = $criticality
            bug_density_score = $bugDensity
            author_bug_score = $authorBug
            combined_score = $combined
            tier = $tier
            reason = $reason
        }
    }

    return $results | Sort-Object -Property combined_score -Descending
}

function Get-AuditScopeForCycle {
    <#
    .SYNOPSIS
        Determines what to audit this cycle.
    .DESCRIPTION
        - If files changed < max_differential_pct% → differential audit (only changed + tier-1)
        - If files changed >= max_differential_pct% OR no prior audit → full audit
        - Every full_audit_every_n_cycles a full audit is forced
        Returns audit plan with file list and rationale.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepoPath,

        [string]$LastAuditCommit,

        [PSCustomObject]$GraphData,

        [int]$CycleNumber,

        [string]$EngineRoot,

        [int]$MaxDifferentialPct = 20,

        [int]$FullAuditEveryNCycles = 5
    )

    $null = Get-Command git -ErrorAction Stop
    $cwd = Get-Location

    $totalFiles = 0
    $changedEntries = @()
    $mode = "full"

    try {
        Set-Location -LiteralPath $RepoPath

        $lsOutput = git ls-files 2>&1
        if ($LASTEXITCODE -eq 0) {
            $totalFiles = ($lsOutput | Measure-Object).Count
        }

        if ($LastAuditCommit) {
            $changedEntries = Get-ChangedFilesSinceLastAudit -RepoPath $RepoPath -LastAuditCommit $LastAuditCommit
        } else {
            $allFiles = $lsOutput
            if ($allFiles -is [string]) { $allFiles = $allFiles -split "`n" }
            foreach ($f in $allFiles) {
                $trimmed = $f.Trim()
                if ($trimmed) {
                    $changedEntries += @{ file = $trimmed; status = "initial" }
                }
            }
        }
    } catch {
        Write-Warning "Get-AuditScopeForCycle: git error: $_"
    } finally {
        Set-Location $cwd.Path
    }

    $forceFull = ($CycleNumber % $FullAuditEveryNCycles -eq 0)
    $hasPriorAudit = ($null -ne $LastAuditCommit -and $LastAuditCommit -ne "")

    if (-not $hasPriorAudit) {
        $mode = "full"
        $rationale = "No prior audit commit recorded -- performing full audit."
    } elseif ($forceFull) {
        $mode = "full"
        $rationale = "Cycle $CycleNumber is a scheduled full audit (every $FullAuditEveryNCycles cycles)."
    } elseif ($totalFiles -gt 0) {
        $changedCount = $changedEntries.Count
        $changedPct = [math]::Round(($changedCount / $totalFiles) * 100, 1)

        if ($changedPct -lt $MaxDifferentialPct) {
            $mode = "differential"
            $rationale = "Only $changedPct% of files changed (< $MaxDifferentialPct% threshold) -- differential audit."
        } else {
            $mode = "full"
            $rationale = "$changedPct% of files changed (>= $MaxDifferentialPct% threshold) -- full audit required."
        }
    } else {
        $mode = "full"
        $rationale = "Could not determine file counts -- defaulting to full audit."
    }

    $allChangedFiles = @($changedEntries | ForEach-Object { $_.file } | Where-Object { $_ })
    $auditFiles = @()

    if ($mode -eq "differential") {
        $nonDeleteChanged = @($changedEntries | Where-Object { $_.status -ne "D" } | ForEach-Object { $_.file })
        $existingFiles = @($nonDeleteChanged | Where-Object {
            Test-Path -LiteralPath (Join-Path $RepoPath $_)
        })

        $priorities = Get-AuditPriority -RepoPath $RepoPath -Files $existingFiles `
            -GraphData $GraphData -CycleNumber $CycleNumber -EngineRoot $EngineRoot

        $tier1 = @($priorities | Where-Object { $_.tier -eq "tier_1" })

        $auditFiles = $tier1

        $currentCommit = ""
        try {
            Set-Location -LiteralPath $RepoPath
            $currentCommit = (git rev-parse HEAD 2>&1 | Out-String).Trim()
            Set-Location $cwd.Path
        } catch { }

        $allExisting = @(Get-ChildItem -LiteralPath $RepoPath -File -Recurse -ErrorAction SilentlyContinue |
            Where-Object {
                $rel = $_.FullName.Substring($RepoPath.Length).TrimStart("\","/").Replace("\","/")
                ($rel -notmatch '\\\.git\\|\\\.aura\\|\\node_modules\\|\\vendor\\|\\__pycache__\\') -and
                ($rel -notlike '.git/*') -and ($rel -notlike '.aura/*') -and
                ($rel -notlike 'node_modules/*') -and ($rel -notlike 'vendor/*')
            } |
            ForEach-Object { $_.FullName.Substring($RepoPath.Length).TrimStart("\","/").Replace("\","/") })

        $tier1Set = @{}
        foreach ($f in $auditFiles) { $tier1Set[$f.file] = $true }

        $otherPriorities = Get-AuditPriority -RepoPath $RepoPath -Files $allExisting `
            -GraphData $GraphData -CycleNumber $CycleNumber -EngineRoot $EngineRoot

        $tier2and3 = @($otherPriorities | Where-Object { $_.tier -ne "tier_1" })

        $additionalFiles = @($tier2and3 | Where-Object {
            -not $tier1Set.ContainsKey($_.file)
        } | Select-Object -First 15)

        $auditFiles += $additionalFiles

        if ($GraphData) {
            $changedFileNames = @($existingFiles)
            $dependencyImpacted = Get-DependencyImpact -RepoPath $RepoPath -GraphData $GraphData -ChangedFiles $changedFileNames
            foreach ($di in $dependencyImpacted) {
                if (-not $tier1Set.ContainsKey($di)) {
                    $tier1Set[$di] = $true
                    $auditFiles += [PSCustomObject]@{
                        file = $di
                        churn_score = 0
                        criticality_score = 50
                        bug_density_score = 0
                        author_bug_score = 0
                        combined_score = 50
                        tier = "tier_2"
                        reason = "Dependency-affected: importers of changed files"
                    }
                }
            }
        }
    } else {
        $allExisting = @(Get-ChildItem -LiteralPath $RepoPath -File -Recurse -ErrorAction SilentlyContinue |
            Where-Object {
                $rel = $_.FullName.Substring($RepoPath.Length).TrimStart("\","/").Replace("\","/")
                ($rel -notmatch '\\\.git\\|\\\.aura\\|\\node_modules\\|\\vendor\\|\\__pycache__\\') -and
                ($rel -notlike '.git/*') -and ($rel -notlike '.aura/*') -and
                ($rel -notlike 'node_modules/*') -and ($rel -notlike 'vendor/*')
            } |
            ForEach-Object { $_.FullName.Substring($RepoPath.Length).TrimStart("\","/").Replace("\","/") })

        $priorities = Get-AuditPriority -RepoPath $RepoPath -Files $allExisting `
            -GraphData $GraphData -CycleNumber $CycleNumber -EngineRoot $EngineRoot
        $auditFiles = $priorities
    }

    return [PSCustomObject]@{
        mode = $mode
        rationale = $rationale
        cycle = $CycleNumber
        total_repo_files = $totalFiles
        changed_files = $changedEntries
        changed_count = $changedEntries.Count
        audit_file_count = $auditFiles.Count
        audit_files = $auditFiles
        force_full = $forceFull
        has_prior_audit = $hasPriorAudit
    }
}

function Save-AuditCache {
    <#
    .SYNOPSIS
        Saves file-hash cache to .aura/state/audit-cache.json
    .DESCRIPTION
        Caches file hashes and audit cycle data for incremental comparison.
        Format: { commit: "...", timestamp: "...", files: { "path/to/file": { hash: "...", last_audited_cycle: N } } }
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$EngineRoot,

        [Parameter(Mandatory = $true)]
        [string]$RepoPath,

        [Parameter(Mandatory = $true)]
        [string]$CommitHash,

        [hashtable]$AuditData
    )

    $stateDir = Join-Path $EngineRoot "state"
    if (-not (Test-Path -LiteralPath $stateDir)) {
        New-Item -ItemType Directory -Force -Path $stateDir | Out-Null
    }

    $cacheFile = Join-Path $stateDir "audit-cache.json"
    $Script:_IncrementalCacheFile = $cacheFile

    $existingCache = Load-AuditCache -EngineRoot $EngineRoot

    $newCache = @{
        version = "1.0.0"
        commit = $CommitHash
        timestamp = (Get-Date).ToString("o")
        repo_path = $RepoPath
    }

    if ($existingCache) {
        $newCache.previous_commit = $existingCache.commit
        $newCache.previous_timestamp = $existingCache.timestamp
        $newCache.total_cycles = (([int]($existingCache.total_cycles -as [int])) + 1)
        $newCache.files = $existingCache.files
    } else {
        $newCache.previous_commit = $null
        $newCache.previous_timestamp = $null
        $newCache.total_cycles = 1
        $newCache.files = @{}
    }

    if ($AuditData -and $AuditData.ContainsKey("files")) {
        foreach ($key in $AuditData["files"].Keys) {
            $newCache.files[$key] = $AuditData["files"][$key]
        }
    }

    $tempPath = "$cacheFile.tmp.$([System.Guid]::NewGuid().ToString('N').Substring(0,8))"
    try {
        $json = $newCache | ConvertTo-Json -Depth 100
        $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
        [System.IO.File]::WriteAllText($tempPath, $json, $utf8NoBom)
        Move-Item -LiteralPath $tempPath -Destination $cacheFile -Force
    } catch {
        if (Test-Path -LiteralPath $tempPath) {
            Remove-Item -LiteralPath $tempPath -Force -ErrorAction SilentlyContinue
        }
        Write-Warning "Save-AuditCache: Failed to write audit cache: $_"
    }
}

function Load-AuditCache {
    <#
    .SYNOPSIS
        Loads audit cache from .aura/state/audit-cache.json
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$EngineRoot
    )

    $cacheFile = Join-Path $EngineRoot "state/audit-cache.json"
    if (-not (Test-Path -LiteralPath $cacheFile)) {
        return $null
    }

    try {
        $content = Get-Content -LiteralPath $cacheFile -Raw -Encoding UTF8
        if ([string]::IsNullOrWhiteSpace($content)) { return $null }
        return $content | ConvertFrom-Json
    } catch {
        Write-Warning "Load-AuditCache: Failed to read cache: $_"
        return $null
    }
}

function Get-FileHashFast {
    <#
    .SYNOPSIS
        Computes a fast SHA256 hash of file path + size + mtime.
        Faster than full content hash, sufficient for change detection.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath
    )

    if (-not (Test-Path -LiteralPath $FilePath)) {
        return $null
    }

    try {
        $fileInfo = Get-Item -LiteralPath $FilePath
        $hashInput = "$($fileInfo.FullName)|$($fileInfo.Length)|$($fileInfo.LastWriteTime.ToString('o'))"
        $sha = [System.Security.Cryptography.SHA256]::Create()
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($hashInput)
        $hashBytes = $sha.ComputeHash($bytes)
        return [System.BitConverter]::ToString($hashBytes) -replace '-', ''
    } catch {
        return $null
    }
}

function Update-AuditCacheForFiles {
    <#
    .SYNOPSIS
        Updates the audit cache with hashes for audited files.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$EngineRoot,

        [Parameter(Mandatory = $true)]
        [string]$RepoPath,

        [string[]]$AuditedFiles,

        [int]$CycleNumber
    )

    $cache = Load-AuditCache -EngineRoot $EngineRoot
    if (-not $cache) {
        $cache = @{
            version = "1.0.0"
            commit = ""
            timestamp = (Get-Date).ToString("o")
            repo_path = $RepoPath
            previous_commit = $null
            previous_timestamp = $null
            total_cycles = 0
            files = @{}
        }
    }

    foreach ($file in $AuditedFiles) {
        $fullPath = Join-Path $RepoPath $file
        $hash = Get-FileHashFast -FilePath $fullPath
        if ($hash) {
            $cache.files[$file] = @{
                hash = $hash
                last_audited_cycle = $CycleNumber
                last_audited_at = (Get-Date).ToString("o")
            }
        }
    }

    $cwd = Get-Location
    try {
        Set-Location -LiteralPath $RepoPath
        $currentCommit = (git rev-parse HEAD 2>&1 | Out-String).Trim()
        Set-Location $cwd.Path
        if ($LASTEXITCODE -eq 0 -and $currentCommit) {
            Save-AuditCache -EngineRoot $EngineRoot -RepoPath $RepoPath -CommitHash $currentCommit `
                -AuditData @{ files = $cache.files }
        }
    } catch { }
}

function Get-UnchangedFilesWithOldHashes {
    <#
    .SYNOPSIS
        Identifies tracked files whose hash is stale or missing from cache.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$EngineRoot,

        [Parameter(Mandatory = $true)]
        [string]$RepoPath
    )

    $cache = Load-AuditCache -EngineRoot $EngineRoot
    $stale = @()

    $null = Get-Command git -ErrorAction Stop
    $cwd = Get-Location

    try {
        Set-Location -LiteralPath $RepoPath
        $allFiles = git ls-files 2>&1
        Set-Location $cwd.Path

        if ($LASTEXITCODE -ne 0) { return @() }

        if ($allFiles -is [string]) { $allFiles = $allFiles -split "`n" }

        foreach ($file in $allFiles) {
            $trimmed = $file.Trim()
            if (-not $trimmed) { continue }

            if (-not $cache -or -not $cache.files -or -not $cache.files.ContainsKey($trimmed)) {
                $stale += $trimmed
                continue
            }

            $cachedEntry = $cache.files[$trimmed]
            $fullPath = Join-Path $RepoPath $trimmed
            $currentHash = Get-FileHashFast -FilePath $fullPath

            if ($currentHash -and $currentHash -ne $cachedEntry.hash) {
                $stale += $trimmed
            }
        }
    } catch {
        Write-Warning "Get-UnchangedFilesWithOldHashes: Error: $_"
    } finally {
        Set-Location $cwd.Path
    }

    return $stale
}

function Get-AuthorBugRate {
    param([string]$RepoPath)
    $rates = @{}
    try {
        $cwd = Get-Location
        Set-Location -LiteralPath $RepoPath
        $logOutput = git log --format="%ae" --since="90.days.ago" 2>&1
        if ($LASTEXITCODE -eq 0 -and $logOutput) {
            $emails = @($logOutput | ForEach-Object { $_.Trim() } | Where-Object { $_ -match '@' })
            $total = $emails.Count
            if ($total -gt 0) {
                $grouped = $emails | Group-Object | Sort-Object Count -Descending
                foreach ($g in $grouped) {
                    $rate = [math]::Round($g.Count / $total, 3)
                    $rates[$g.Name] = $rate
                }
            }
        }
    } catch { } finally {
        Set-Location $cwd.Path
    }
    return $rates
}

function Get-DependencyImpact {
    param(
        [string]$RepoPath,
        [object]$GraphData,
        [string[]]$ChangedFiles
    )
    $impacted = @()
    if (-not $GraphData -or -not $ChangedFiles) { return $impacted }
    $changedSet = @{}
    foreach ($cf in $ChangedFiles) { $changedSet[$cf] = $true }
    try {
        if ($GraphData -is [hashtable] -and $GraphData.ContainsKey('importers')) {
            foreach ($cf in $ChangedFiles) {
                if ($GraphData.importers.ContainsKey($cf)) {
                    foreach ($importer in $GraphData.importers[$cf]) {
                        if (-not $changedSet.ContainsKey($importer)) {
                            $impacted += $importer
                            $changedSet[$importer] = $true
                        }
                    }
                }
            }
        }
    } catch { }
    return $impacted | Select-Object -Unique
}

Export-ModuleMember -Function Get-ChangedFilesSinceLastAudit, Get-FileChangeType,
    Get-FileChurnScore, Get-FileCriticalityScore, Get-BugDensityScore,
    Get-AuditPriority, Get-AuditScopeForCycle, Save-AuditCache, Load-AuditCache,
    Get-FileHashFast, Update-AuditCacheForFiles, Get-UnchangedFilesWithOldHashes