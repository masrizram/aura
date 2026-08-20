# ============================================================
# SMART PRIORITIZATION ENGINE v1.0.0
# Purpose: Heuristic-based file prioritization for large repos.
# Author bug rate analysis, risk hotspot clustering, dependency
# impact propagation, and smart audit rotation plans.
# Classification: OPTIONAL
# ============================================================

function Get-AuthorBugRate {
    <#
    .SYNOPSIS
        Analyzes git log to identify which authors' commits most often
        become bug-fix commits later.
    .DESCRIPTION
        Uses heuristics: counts "fix", "bug", "hotfix" commits vs total
        commits per author. Returns @{ "author email" = bug_rate 0-1 }.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepoPath
    )

    $null = Get-Command git -ErrorAction Stop
    $cwd = Get-Location
    $authorStats = @{}

    try {
        Set-Location -LiteralPath $RepoPath

        $allCommits = git log --format="%ae|%s" --max-count=2000 2>&1
        if ($LASTEXITCODE -ne 0) { return @{} }

        if ($allCommits -is [string]) {
            $allCommits = $allCommits -split "`n"
        }

        $bugPattern = '(?i)\b(fix|bug|hotfix|patch|vuln|security|cve|crash|segfault|null|oob|overflow|inject|race|deadlock)\b'
        $nonBugPattern = '(?i)\b(refactor|docs|style|chore|typo|format|lint|cleanup|spelling|comment|readme)\b'

        foreach ($line in $allCommits) {
            $trimmed = $line.Trim()
            if (-not $trimmed) { continue }

            $parts = $trimmed -split '\|', 2
            if ($parts.Count -lt 2) { continue }

            $email = $parts[0].Trim().ToLowerInvariant()
            $subject = $parts[1] -join '|'

            if (-not $authorStats.ContainsKey($email)) {
                $authorStats[$email] = @{
                    total = 0
                    bug_commits = 0
                    non_bug_commits = 0
                }
            }

            $authorStats[$email].total++

            $isBug = $subject -match $bugPattern
            $isNonBug = $subject -match $nonBugPattern

            if ($isBug -and -not $isNonBug) {
                $authorStats[$email].bug_commits++
            } elseif ($isNonBug -and -not $isBug) {
                $authorStats[$email].non_bug_commits++
            }
        }

        $result = @{}
        foreach ($email in $authorStats.Keys) {
            $stats = $authorStats[$email]
            if ($stats.total -lt 5) { continue }

            $ratedCommits = $stats.bug_commits + $stats.non_bug_commits
            if ($ratedCommits -eq 0) { continue }

            $bugRate = [math]::Round($stats.bug_commits / $ratedCommits, 3)
            $result[$email] = $bugRate
        }

        return $result
    } catch {
        Write-Warning "Get-AuthorBugRate: git error: $_"
        return @{}
    } finally {
        Set-Location $cwd.Path
    }
}

function Get-RiskHotspots {
    <#
    .SYNOPSIS
        Identifies code "hotspots" where findings cluster.
    .DESCRIPTION
        Analyzes finding history and git log to find files with
        repeated high-severity findings over time. Uses --follow to
        track file renames.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepoPath,

        [PSCustomObject]$Findings,

        [int]$WindowSize = 90
    )

    $hotspots = @{}
    $null = Get-Command git -ErrorAction Stop

    if (-not $Findings -or -not $Findings.findings) {
        return $hotspots
    }

    foreach ($finding in $Findings.findings) {
        if (-not $finding.file) { continue }
        $file = $finding.file.Replace("\", "/").TrimStart("/")

        $severityWeight = switch ($finding.severity) {
            "P0" { 10 }
            "P1" { 7 }
            "P2" { 4 }
            "P3" { 2 }
            "P4" { 1 }
            "P5" { 0 }
            default { 0 }
        }

        if (-not $hotspots.ContainsKey($file)) {
            $hotspots[$file] = @{
                finding_count = 0
                severity_sum = 0
                p0_count = 0
                p1_count = 0
                p2_count = 0
                categories = @{}
                last_finding_date = $null
                first_finding_cycle = $null
            }
        }

        $hs = $hotspots[$file]
        $hs.finding_count++
        $hs.severity_sum += $severityWeight

        switch ($finding.severity) {
            "P0" { $hs.p0_count++ }
            "P1" { $hs.p1_count++ }
            "P2" { $hs.p2_count++ }
        }

        if ($finding.category) {
            if (-not $hs.categories[$finding.category]) {
                $hs.categories[$finding.category] = 0
            }
            $hs.categories[$finding.category]++
        }

        if (-not $hs.last_finding_date) {
            $hs.last_finding_date = $finding.timestamp
        } elseif ($finding.timestamp -and $finding.timestamp -gt $hs.last_finding_date) {
            $hs.last_finding_date = $finding.timestamp
        }

        if (-not $hs.first_finding_cycle) {
            $hs.first_finding_cycle = $finding.cycle
        }
    }

    $cwd = Get-Location
    try {
        Set-Location -LiteralPath $RepoPath

        foreach ($file in $hotspots.Keys) {
            $hs = $hotspots[$file]

            $logOutput = git log --follow --format="%H %ai" --max-count=50 -- $file 2>&1
            if ($LASTEXITCODE -ne 0) { continue }

            if ($logOutput -is [string]) { $logOutput = $logOutput -split "`n" }

            $commitDates = @()
            foreach ($line in $logOutput) {
                $trimmed = $line.Trim()
                if (-not $trimmed) { continue }
                if ($trimmed -match '^[0-9a-f]{40}\s+(\d{4}-\d{2}-\d{2})') {
                    $commitDates += $matches[1]
                }
            }

            $hs.commit_dates = $commitDates
            $cutoff = (Get-Date).AddDays(-$WindowSize).ToString("yyyy-MM-dd")
            $recent = @($commitDates | Where-Object { $_ -ge $cutoff })
            $hs.recent_commits = $recent.Count
            $hs.total_recent_commits = $commitDates.Count

            $hs.risk_score = [math]::Min(100, [math]::Round(
                ($hs.p0_count * 25) + ($hs.p1_count * 15) + ($hs.p2_count * 8) +
                ($hs.finding_count * 3) + ($hs.recent_commits * 0.5)
            ))
        }
    } catch {
        Write-Warning "Get-RiskHotspots: git error during log analysis: $_"
    } finally {
        Set-Location $cwd.Path
    }

    return $hotspots
}

function Get-DependencyImpact {
    <#
    .SYNOPSIS
        Given changed files, compute which dependents are affected.
    .DESCRIPTION
        Uses the dependency graph to find all files that import/include
        the changed files. Returns list of files that should be re-audited.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepoPath,

        [Parameter(Mandatory = $true)]
        [PSCustomObject]$GraphData,

        [Parameter(Mandatory = $true)]
        [string[]]$ChangedFiles
    )

    $impacted = @()
    $seen = @{}

    if (-not $GraphData -or -not $GraphData.dependency_graph) {
        return @()
    }

    $changedNorm = @{}
    foreach ($f in $ChangedFiles) {
        $norm = $f.Replace("\", "/").TrimStart("/")
        $changedNorm[$norm] = $true
        $baseName = [System.IO.Path]::GetFileName($norm)
        if ($baseName) { $changedNorm[$baseName] = $true }
    }

    if ($GraphData.dependency_graph -is [PSCustomObject]) {
        foreach ($depKey in $GraphData.dependency_graph.PSObject.Properties.Name) {
            $deps = $GraphData.dependency_graph.$depKey
            if (-not $deps) { continue }

            foreach ($dep in $deps) {
                $depFile = if ($dep.file) { $dep.file.Replace("\", "/").TrimStart("/") } else { $null }
                $depRaw  = if ($dep.raw) { $dep.raw } else { "" }

                $isImpacted = $false

                if ($depFile -and $changedNorm.ContainsKey($depFile)) {
                    $isImpacted = $true
                } elseif ($depRaw) {
                    foreach ($changedKey in $changedNorm.Keys) {
                        if ($depRaw -like "*$changedKey*") {
                            $isImpacted = $true
                            break
                        }
                    }
                }

                if ($isImpacted -and -not $seen.ContainsKey($depKey)) {
                    $seen[$depKey] = $true
                    $impacted += $depKey
                }
            }
        }

        foreach ($depKey in $GraphData.dependency_graph.PSObject.Properties.Name) {
            if ($seen.ContainsKey($depKey)) { continue }
            $deps = $GraphData.dependency_graph.$depKey
            if (-not $deps) { continue }

            foreach ($dep in $deps) {
                $depFile = if ($dep.file) { $dep.file.Replace("\", "/").TrimStart("/") } else { $null }
                if ($depFile -and $seen.ContainsKey($depFile)) {
                    $seen[$depKey] = $true
                    $impacted += $depKey
                    break
                }
            }
        }
    } elseif ($GraphData.dependency_graph -is [hashtable]) {
        foreach ($depKey in $GraphData.dependency_graph.Keys) {
            $deps = $GraphData.dependency_graph[$depKey]
            if (-not $deps) { continue }

            foreach ($dep in $deps) {
                $depFile = if ($dep.file) { $dep.file.Replace("\", "/").TrimStart("/") } else { $null }
                $depRaw  = if ($dep.raw) { $dep.raw } else { "" }

                $isImpacted = $false
                if ($depFile -and $changedNorm.ContainsKey($depFile)) {
                    $isImpacted = $true
                } elseif ($depRaw) {
                    foreach ($changedKey in $changedNorm.Keys) {
                        if ($depRaw -like "*$changedKey*") {
                            $isImpacted = $true
                            break
                        }
                    }
                }

                if ($isImpacted -and -not $seen.ContainsKey($depKey)) {
                    $seen[$depKey] = $true
                    $impacted += $depKey
                }
            }
        }
    }

    return $impacted
}

function New-SmartAuditPlan {
    <#
    .SYNOPSIS
        Creates a smart audit plan with rotation across tiers.
    .DESCRIPTION
        1. Always audit tier-1 files
        2. Rotate through tier-2 files (configurable % per cycle)
        3. Rotate through tier-3 files (configurable % per cycle)
        4. Always audit dependency-affected files
        Ensures full coverage over ~3-5 cycles for medium repos.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepoPath,

        [Parameter(Mandatory = $true)]
        [string]$EngineRoot,

        [int]$CycleNumber,

        [int]$MaxFilesPerCycle = 50,

        [float]$Tier2RotationPct = 30,

        [float]$Tier3RotationPct = 10,

        [PSCustomObject]$GraphData
    )

    $stateDir = Join-Path $EngineRoot "state"
    $rotationFile = Join-Path $stateDir "audit-rotation.json"

    $rotationState = @{
        tier_2_position = 0
        tier_3_position = 0
        last_updated_cycle = 0
    }

    if (Test-Path -LiteralPath $rotationFile) {
        try {
            $content = Get-Content -LiteralPath $rotationFile -Raw -Encoding UTF8
            if ($content) {
                $existing = $content | ConvertFrom-Json
                if ($existing) {
                    $rotationState.tier_2_position = [int]($existing.tier_2_position -as [int])
                    $rotationState.tier_3_position = [int]($existing.tier_3_position -as [int])
                    $rotationState.last_updated_cycle = [int]($existing.last_updated_cycle -as [int])
                }
            }
        } catch { }
    }

    $hasPriorAudit = ($rotationState.last_updated_cycle -gt 0)

    $null = Get-Command git -ErrorAction Stop
    $cwd = Get-Location
    $allFiles = @()

    try {
        Set-Location -LiteralPath $RepoPath
        $lsOutput = git ls-files 2>&1
        Set-Location $cwd.Path
        if ($LASTEXITCODE -eq 0) {
            if ($lsOutput -is [string]) { $lsOutput = $lsOutput -split "`n" }
            $allFiles = @($lsOutput | ForEach-Object { $_.Trim() } | Where-Object { $_ })
        }
    } catch {
        Write-Warning "New-SmartAuditPlan: git ls-files error: $_"
    } finally {
        Set-Location $cwd.Path
    }

    $cache = Load-AuditCache -EngineRoot $EngineRoot
    $lastCommit = if ($cache -and $cache.commit) { $cache.commit } else { "" }

    if (-not $allFiles) {
        $allFiles = @(Get-ChildItem -LiteralPath $RepoPath -File -Recurse -ErrorAction SilentlyContinue |
            Where-Object {
                $rel = $_.FullName.Substring($RepoPath.Length).TrimStart("\","/").Replace("\","/")
                ($rel -notmatch '\\\.git\\|\\\.aura\\|\\node_modules\\|\\vendor\\|\\__pycache__\\')
            } |
            ForEach-Object { $_.FullName.Substring($RepoPath.Length).TrimStart("\","/").Replace("\","/") })
    }

    $findings = $null
    $findingsPath = Join-Path $EngineRoot "state/findings.json"
    if (Test-Path -LiteralPath $findingsPath) {
        try {
            $content = Get-Content -LiteralPath $findingsPath -Raw -Encoding UTF8
            if ($content) { $findings = $content | ConvertFrom-Json }
        } catch { }
    }

    $hotspots = if ($findings) {
        Get-RiskHotspots -RepoPath $RepoPath -Findings $findings
    } else { @{} }

    $priorities = Get-AuditPriority -RepoPath $RepoPath -Files $allFiles `
        -GraphData $GraphData -CycleNumber $CycleNumber -EngineRoot $EngineRoot

    $tier1 = @($priorities | Where-Object { $_.tier -eq "tier_1" })
    $tier2 = @($priorities | Where-Object { $_.tier -eq "tier_2" })
    $tier3 = @($priorities | Where-Object { $_.tier -eq "tier_3" })

    $plan = @()
    $takenSet = @{}

    foreach ($f in $tier1) {
        $plan += $f
        $takenSet[$f.file] = $true
    }

    $depImpacted = @()
    if ($lastCommit -and $GraphData) {
        $changed = Get-ChangedFilesSinceLastAudit -RepoPath $RepoPath -LastAuditCommit $lastCommit
        $changedFiles = @($changed | Where-Object { $_.status -ne "D" } | ForEach-Object { $_.file })
        if ($changedFiles.Count -gt 0) {
            $depImpacted = Get-DependencyImpact -RepoPath $RepoPath -GraphData $GraphData -ChangedFiles $changedFiles
        }
    }

    foreach ($di in $depImpacted) {
        if (-not $takenSet.ContainsKey($di)) {
            $takenSet[$di] = $true
            $plan += [PSCustomObject]@{
                file = $di
                churn_score = 0
                criticality_score = 50
                bug_density_score = 0
                author_bug_score = 0
                combined_score = 50
                tier = "tier_2"
                reason = "Dependency-affected by changed files"
            }
        }
    }

    $tier2Count = [math]::Max(1, [math]::Round($tier2.Count * ($Tier2RotationPct / 100.0)))
    $tier2Start = $rotationState.tier_2_position
    $tier2Slice = @()

    for ($i = 0; $i -lt $tier2Count; $i++) {
        $idx = ($tier2Start + $i) % $tier2.Count
        if ($tier2.Count -gt 0) {
            $tier2Slice += $tier2[$idx]
        }
    }

    foreach ($f in $tier2Slice) {
        if (-not $takenSet.ContainsKey($f.file) -and $plan.Count -lt $MaxFilesPerCycle) {
            $plan += $f
            $takenSet[$f.file] = $true
        }
    }

    $tier3Count = [math]::Max(1, [math]::Round($tier3.Count * ($Tier3RotationPct / 100.0)))
    $tier3Start = $rotationState.tier_3_position
    $tier3Slice = @()

    for ($i = 0; $i -lt $tier3Count; $i++) {
        if ($tier3.Count -gt 0) {
            $idx = ($tier3Start + $i) % $tier3.Count
            $tier3Slice += $tier3[$idx]
        }
    }

    foreach ($f in $tier3Slice) {
        if (-not $takenSet.ContainsKey($f.file) -and $plan.Count -lt $MaxFilesPerCycle) {
            $plan += $f
            $takenSet[$f.file] = $true
        }
    }

    foreach ($file in $hotspots.Keys) {
        $hs = $hotspots[$file]
        if ($hs.risk_score -ge 50 -and -not $takenSet.ContainsKey($file) -and $plan.Count -lt $MaxFilesPerCycle) {
            $plan += [PSCustomObject]@{
                file = $file
                churn_score = 0
                criticality_score = 0
                bug_density_score = $hs.risk_score
                author_bug_score = 0
                combined_score = $hs.risk_score
                tier = "tier_1"
                reason = "Risk hotspot: $($hs.finding_count) prior findings, severity sum=$($hs.severity_sum)"
            }
            $takenSet[$file] = $true
        }
    }

    $rotationState.last_updated_cycle = $CycleNumber
    if ($tier2.Count -gt 0) {
        $rotationState.tier_2_position = ($tier2Start + $tier2Count) % $tier2.Count
    }
    if ($tier3.Count -gt 0) {
        $rotationState.tier_3_position = ($tier3Start + $tier3Count) % $tier3.Count
    }

    try {
        $parent = Split-Path -Parent $rotationFile
        if (-not (Test-Path -LiteralPath $parent)) {
            New-Item -ItemType Directory -Force -Path $parent | Out-Null
        }
        $json = $rotationState | ConvertTo-Json
        $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
        [System.IO.File]::WriteAllText($rotationFile, $json, $utf8NoBom)
    } catch {
        Write-Warning "New-SmartAuditPlan: Failed to save rotation state: $_"
    }

    return [PSCustomObject]@{
        cycle = $CycleNumber
        plan = $plan
        total_planned = $plan.Count
        max_per_cycle = $MaxFilesPerCycle
        tier_1_count = ($plan | Where-Object { $_.tier -eq "tier_1" }).Count
        tier_2_count = ($plan | Where-Object { $_.tier -eq "tier_2" }).Count
        tier_3_count = ($plan | Where-Object { $_.tier -eq "tier_3" }).Count
        dependency_affected = $depImpacted.Count
        hotspot_included = ($plan | Where-Object { $_.reason -like "*hotspot*" }).Count
        tier_2_pool_size = $tier2.Count
        tier_3_pool_size = $tier3.Count
        rotation = $rotationState
    }
}

function Format-AuditPlanReport {
    <#
    .SYNOPSIS
        Formats an audit plan into a readable report string.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [PSCustomObject]$AuditPlan
    )

    $sb = New-Object System.Text.StringBuilder

    [void]$sb.AppendLine("")
    [void]$sb.AppendLine("=== SMART AUDIT PLAN ===")
    [void]$sb.AppendLine("Cycle: $($AuditPlan.cycle)")
    [void]$sb.AppendLine("Total planned files: $($AuditPlan.total_planned) / $($AuditPlan.max_per_cycle) max")
    [void]$sb.AppendLine("")
    [void]$sb.AppendLine("### Tier Breakdown")
    [void]$sb.AppendLine("- Tier 1 (must audit): $($AuditPlan.tier_1_count)")
    [void]$sb.AppendLine("- Tier 2 (rotated): $($AuditPlan.tier_2_count) (pool: $($AuditPlan.tier_2_pool_size))")
    [void]$sb.AppendLine("- Tier 3 (rotated): $($AuditPlan.tier_3_count) (pool: $($AuditPlan.tier_3_pool_size))")
    [void]$sb.AppendLine("- Dependency-affected: $($AuditPlan.dependency_affected)")
    [void]$sb.AppendLine("- Hotspot-recovered: $($AuditPlan.hotspot_included)")
    [void]$sb.AppendLine("")

    [void]$sb.AppendLine("### Planned Files")
    [void]$sb.AppendLine("| File | Score | Tier | Reason |")
    [void]$sb.AppendLine("|------|-------|------|--------|")

    foreach ($f in $AuditPlan.plan) {
        $score = [math]::Round($f.combined_score, 1)
        $tier = $f.tier -replace "_", " "
        $reason = if ($f.reason.Length -gt 60) { $f.reason.Substring(0, 57) + "..." } else { $f.reason }
        [void]$sb.AppendLine("| $($f.file) | $score | $tier | $reason |")
    }

    return $sb.ToString()
}

Export-ModuleMember -Function Get-AuthorBugRate, Get-RiskHotspots, Get-DependencyImpact,
    New-SmartAuditPlan, Format-AuditPlanReport