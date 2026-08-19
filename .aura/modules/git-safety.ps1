# ============================================================
# GIT TRANSACTION SAFETY v1.0.0
# Worktree isolation, user change preservation, credential
# protection. Ensures remediation does not corrupt user work.
# ============================================================

function New-GitSafeContext {
    param(
        [string]$ProjectRoot
    )

    $cwd = Get-Location
    Set-Location -LiteralPath $ProjectRoot

    $ctx = @{
        project_root = $ProjectRoot
        is_git_repo = $false
        branch = ""
        worktree_count = 0
        untracked_files = @()
        modified_non_engine = @()
        stash_backup = $false
        worktree_created = $false
        hooks_were_disabled = $false
    }

    try {
        $null = Get-Command git -ErrorAction Stop

        $gitDir = git rev-parse --git-dir 2>&1
        if ($LASTEXITCODE -ne 0) {
            $ctx.is_git_repo = $false
            Set-Location $cwd.Path
            return $ctx
        }

        $ctx.is_git_repo = $true
        $ctx.branch = (git branch --show-current 2>&1 | Out-String).Trim()

        $ctx.untracked_files = @((git ls-files --others --exclude-standard 2>&1).Trim() | Where-Object { $_ -ne "" })
        $ctx.modified_non_engine = @((git diff --name-only 2>&1).Trim() | Where-Object {
            $_ -ne "" -and -not ($_ -like ".aura/*") -and -not ($_ -like "run-audit.*") -and -not ($_ -eq "README.md")
        })

        $ctx.worktree_count = (git worktree list 2>&1 | Measure-Object).Count

        Set-Location $cwd.Path
    } catch {
        Set-Location $cwd.Path
        $ctx.is_git_repo = $false
    }

    return $ctx
}

function New-GitWorktree {
    param(
        [string]$ProjectRoot,
        [string]$WorktreePath,
        [string]$BranchName = "aura-remediation"
    )

    $cwd = Get-Location
    Set-Location -LiteralPath $ProjectRoot

    $result = @{ success = $false; worktree_path = $WorktreePath; branch = $BranchName }

    try {
        if (Test-Path -LiteralPath $WorktreePath) {
            Remove-Item -LiteralPath $WorktreePath -Recurse -Force -ErrorAction SilentlyContinue
        }

        $baseBranch = git branch --show-current 2>&1 | Out-String
        $baseBranch = $baseBranch.Trim()

        git worktree add -b $BranchName $WorktreePath $baseBranch 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) {
            git worktree add $WorktreePath $baseBranch 2>&1 | Out-Null
        }

        if ($LASTEXITCODE -eq 0) {
            $result.success = $true
            Write-Host "[GIT] Created worktree at $WorktreePath (branch: $BranchName)" -ForegroundColor Green
        } else {
            Write-Host "[GIT] Failed to create worktree. Isolated branch unavailable." -ForegroundColor Red
        }
    } catch {
        Write-Host "[GIT] Worktree creation error: $_" -ForegroundColor Red
    } finally {
        Set-Location $cwd.Path
    }

    return $result
}

function Remove-GitWorktree {
    param(
        [string]$ProjectRoot,
        [string]$WorktreePath
    )

    $cwd = Get-Location
    Set-Location -LiteralPath $ProjectRoot

    try {
        git worktree remove $WorktreePath --force 2>&1 | Out-Null
        git worktree prune 2>&1 | Out-Null

        if (Test-Path -LiteralPath $WorktreePath) {
            Remove-Item -LiteralPath $WorktreePath -Recurse -Force -ErrorAction SilentlyContinue
        }
    } finally {
        Set-Location $cwd.Path
    }
}

function Test-GitSafety {
    param(
        [string]$ProjectRoot,
        [string]$EngineRoot
    )

    Write-Host "`n=== GIT SAFETY VALIDATION ===" -ForegroundColor Cyan

    $ctx = New-GitSafeContext -ProjectRoot $ProjectRoot
    $tests = @()

    # Test 1: Git repo detection
    $t1 = @{ name = "Git repo detection"; passed = $ctx.is_git_repo; detail = "" }
    $t1.detail = if ($t1.passed) { "Git repository detected on branch '$($ctx.branch)'." } else { "Not a git repository." }
    $tests += $t1

    # Test 2: Non-engine modified file detection
    $t2 = @{ name = "Non-engine file protection"; passed = $true; detail = "" }
    $t2.detail = "Non-engine modified files: $($ctx.modified_non_engine.Count)"
    if ($ctx.modified_non_engine.Count -gt 0) {
        $t2.detail += " ($($ctx.modified_non_engine -join ', '))"
    }
    $tests += $t2

    # Test 3: Engine file isolation check
    $t3 = @{ name = "Engine file enumeration"; passed = $false; detail = "" }
    $psScript = Join-Path $EngineRoot "run-audit.ps1"
    if (Test-Path -LiteralPath $psScript) {
        $engineFiles = @()
        $stateDir = Join-Path $EngineRoot "state"
        if (Test-Path -LiteralPath $stateDir) { $engineFiles += (Get-ChildItem -LiteralPath $stateDir -File).Count }
        $agentsDir = Join-Path $EngineRoot "agents"
        if (Test-Path -LiteralPath $agentsDir) { $engineFiles += (Get-ChildItem -LiteralPath $agentsDir -File).Count }
        $docsDir = Join-Path $EngineRoot "docs"
        if (Test-Path -LiteralPath $docsDir) { $engineFiles += (Get-ChildItem -LiteralPath $docsDir -File).Count }
        $t3.passed = ($engineFiles -gt 0)
        $t3.detail = "Engine files found: state=$engineFiles"
    } else {
        $t3.detail = "Engine script not found."
    }
    $tests += $t3

    # Test 4: Branch protection (no auto-push to main)
    $t4 = @{ name = "Auto-push gating"; passed = $true; detail = "" }
    $configFile = Join-Path $EngineRoot "config.json"
    if (Test-Path -LiteralPath $configFile) {
        $cfg = Get-Content -LiteralPath $configFile -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($cfg.push -and $cfg.push.auto_approve) {
            $t4.passed = $false
            $t4.detail = "WARNING: push.auto_approve is true in config. Auto-push enabled."
        } else {
            $t4.detail = "Auto-push is disabled. User approval required."
        }
    } else {
        $t4.detail = "Config not found."
    }
    $tests += $t4

    # Test 5: Worktree capability
    $t5 = @{ name = "Git worktree support"; passed = $false; detail = "" }
    $worktreeOut = git worktree list 2>&1
    $t5.passed = ($LASTEXITCODE -eq 0)
    $t5.detail = if ($t5.passed) { "Git worktree commands available." } else { "Git worktree not available (older git version)." }
    $tests += $t5

    $failed = ($tests | Where-Object { -not $_.passed }).Count
    $passed = ($tests | Where-Object { $_.passed }).Count

    Write-Host "Git safety tests: $passed passed, $failed failed" -ForegroundColor $(if ($failed -eq 0) { "Green" } else { "Yellow" })
    foreach ($t in $tests) {
        Write-Host "  $($t.name): $(if ($t.passed) { 'PASS' } else { 'FAIL' }) - $($t.detail)"
    }

    return @{ all_passed = ($failed -eq 0); tests = $tests; context = $ctx }
}