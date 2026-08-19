# ============================================================
# SCALE BENCHMARK GENERATOR v1.0.0
# Creates controlled repositories of increasing size for
# scalability validation of the AURA engine.
# ============================================================

function New-ScaleBenchmark {
    param(
        [string]$BenchmarkRoot,
        [int[]]$Sizes = @(25, 100, 500, 1000, 2000, 5000, 10000)
    )

    $results = @{
        generated_at = (Get-Date).ToString("o")
        sizes = @()
    }

    if (-not (Test-Path -LiteralPath $BenchmarkRoot)) {
        New-Item -ItemType Directory -Force -Path $BenchmarkRoot | Out-Null
    }

    foreach ($size in $Sizes) {
        $projectName = "bench-$size-files"
        $projectPath = Join-Path $BenchmarkRoot $projectName

        Write-Host "[BENCH] Generating $projectName ($size files)..." -ForegroundColor Cyan

        if (Test-Path -LiteralPath $projectPath) {
            Remove-Item -LiteralPath $projectPath -Recurse -Force
        }
        New-Item -ItemType Directory -Force -Path $projectPath | Out-Null

        git -C $projectPath init 2>&1 | Out-Null
        git -C $projectPath config user.email "bench@aura.test" 2>&1 | Out-Null
        git -C $projectPath config user.name "AURA Benchmark" 2>&1 | Out-Null

        $stats = @{
            size = $size
            project = $projectName
            path = $projectPath
            files_created = 0
            functions_created = 0
            interdependencies = 0
            defects_injected = 0
            defect_ids = @()
        }

        $dirs = @("src/core", "src/services", "src/utils", "src/models", "src/api", "src/config",
                   "tests", "docs", "scripts", "config")
        foreach ($d in $dirs) {
            New-Item -ItemType Directory -Force -Path (Join-Path $projectPath $d) | Out-Null
        }

        $filePaths = @()
        $baseNum = [math]::Max(1, [math]::Floor($size / 10))
        $remaining = $size

        for ($di = 0; $di -lt $dirs.Count; $di++) {
            $count = [math]::Min($baseNum, $remaining)
            for ($j = 0; $j -lt $count; $j++) {
                $fileName = "mod_${di}_${j}.ps1"
                $filePath = Join-Path $projectPath $dirs[$di] $fileName
                $filePaths += $filePath
            }
            $remaining -= $count
            if ($remaining -le 0) { break }
        }

        $totalFunctions = 0
        $fileIndex = 0

        foreach ($fp in $filePaths) {
            $relPath = $fp.Substring($projectPath.Length).TrimStart("\", "/")
            $baseName = [System.IO.Path]::GetFileNameWithoutExtension($fp)

            $lines = @(
                '# Auto-generated for AURA scale benchmark',
                "# Project: $size-file repository",
                "# Module: $baseName",
                '',
                "# Module: $baseName"
            )

            $depCount = 0
            if ($filePaths.Count -gt 1) {
                $depIdx = ($fileIndex * 7 + 3) % $filePaths.Count
                if ($depIdx -ne $fileIndex) {
                    $depFile = [System.IO.Path]::GetFileName($filePaths[$depIdx])
                    $lines += ". `"`$PSScriptRoot/$depFile`""
                    $depCount = 1
                    $stats.interdependencies += 1
                }
            }

            $funcCount = [math]::Max(1, [math]::Min(5, [math]::Floor(300 / [math]::Max(1, $size))))

            for ($f = 0; $f -lt $funcCount; $f++) {
                $fn = "Get-${baseName}_Result${fileIndex}_$f"
                $lines += @(
                    '',
                    "function $fn {",
                    '    param([string]$InputData, [int]$Limit = 10)',
                    '    if ($null -eq $InputData) { return $null }',
                    '    if ($InputData.Length -gt $Limit) { return $InputData.Substring(0, $Limit) }',
                    '    return $InputData',
                    '}'
                )
                $totalFunctions++
            }

            $content = $lines -join "`n"
            $utf8 = New-Object System.Text.UTF8Encoding($false)
            [System.IO.File]::WriteAllText($fp, $content, $utf8)
            $stats.files_created++
            $fileIndex++
        }

        if ($totalFunctions -gt 0) {
            $manifestContent = @{
                project = $projectName
                version = "1.0.0"
                files = $size
                functions = $totalFunctions
                generated_for = "AURA scale benchmark"
            } | ConvertTo-Json -Depth 10
            $manifestPath = Join-Path $projectPath "config" "manifest.json"
            New-Item -ItemType Directory -Force -Path (Split-Path -Parent $manifestPath) | Out-Null
            [System.IO.File]::WriteAllText($manifestPath, $manifestContent, (New-Object System.Text.UTF8Encoding($false)))

            $pkgContent = @{
                name = $projectName
                version = "1.0.0"
                scripts = @{ test = "Write-Host 'ok'"; lint = "Write-Host 'ok'"; build = "Write-Host 'ok'" }
            } | ConvertTo-Json -Depth 10
            $pkgPath = Join-Path $projectPath "package.json"
            [System.IO.File]::WriteAllText($pkgPath, $pkgContent, (New-Object System.Text.UTF8Encoding($false)))
        }

        $defects = New-BenchmarkDefects -ProjectPath $projectPath -FilePaths $filePaths -Size $size
        $stats.defects_injected = $defects.Count
        $stats.defect_ids = ($defects | ForEach-Object { $_.id })
        $stats.functions_created = $totalFunctions
        $results.sizes += $stats

        git -C $projectPath add . 2>&1 | Out-Null
        git -C $projectPath commit -m "bench: $size-file benchmark" 2>&1 | Out-Null

        Write-Host "  Done: $($stats.files_created) files, $totalFunctions funcs, $($stats.defects_injected) defects" -ForegroundColor Green
    }

    return $results
}

function New-BenchmarkDefects {
    param([string]$ProjectPath, [string[]]$FilePaths, [int]$Size)

    $defects = @()
    if ($FilePaths.Count -eq 0) { return $defects }

    $numDefects = [math]::Max(1, [math]::Floor($Size / 100))
    $defectTypes = @("AUTHZ_REMOVAL","FINANCIAL_ERROR","SQL_INJECTION","NULL_FAILURE","RACE_CONDITION","SSRF","AUTH_BYPASS")

    $injectedDefects = @()

    for ($d = 0; $d -lt $numDefects; $d++) {
        $dt = $defectTypes[$d % $defectTypes.Count]
        $targetIdx = ($d * 7 + 3) % $FilePaths.Count
        $targetFile = $FilePaths[$targetIdx]
        $defectId = "BENCH-DEFECT-$((Get-Date -Format 'HHmmss'))-$d"

        $vulnLines = switch ($dt) {
            "AUTHZ_REMOVAL" { "`n# BENCH-VULN: Always-allow authorization bypass`nfunction Set-Permission { param(`$u) return `$true }`n" }
            "FINANCIAL_ERROR" { "`n# BENCH-VULN: Incorrect discount calculation`nfunction Calc-Price { param(`$p) return `$p * 0.85 }`n" }
            "SQL_INJECTION" { "`n# BENCH-VULN: SQL injection vulnerable`nfunction Get-User { param(`$n) Invoke-SqlCmd -Query ""SELECT * FROM users WHERE name='`$n'"" }`n" }
            "NULL_FAILURE" { "`n# BENCH-VULN: Null reference without check`nfunction Get-First { param(`$a) return `$a[0] }`n" }
            "RACE_CONDITION" { "`n# BENCH-VULN: Race condition on global`nfunction Add-Count { param(`$v) `$global:cnt += `$v }`n" }
            "SSRF" { "`n# BENCH-VULN: SSRF via unfiltered URL`nfunction Fetch-Url { param(`$u) Invoke-WebRequest -Uri `$u }`n" }
            "AUTH_BYPASS" { "`n# BENCH-VULN: Backdoor authentication`nfunction Auth-Check { param(`$t) if (`$t -eq 'backdoor') { return `$true } }`n" }
        }

        Add-Content -LiteralPath $targetFile -Value $vulnLines -Encoding UTF8

        $severity = if ($dt -in @("SQL_INJECTION","AUTH_BYPASS","AUTHZ_REMOVAL")) { "P0" } else { "P1" }

        $injectedDefects += @{
            id = $defectId
            type = $dt
            file = $targetFile.Substring($ProjectPath.Length).TrimStart("\", "/")
            severity = $severity
            description = "Injected $dt defect for benchmark validation"
        }
    }

    $gtPath = Join-Path $ProjectPath ".benchmark-ground-truth.json"
    $gt = @{
        project = (Split-Path -Leaf $ProjectPath)
        defects = $injectedDefects
        generated_at = (Get-Date).ToString("o")
    } | ConvertTo-Json -Depth 100
    [System.IO.File]::WriteAllText($gtPath, $gt, (New-Object System.Text.UTF8Encoding($false)))

    return $injectedDefects
}

function Invoke-ScaleBenchmark {
    param([string]$BenchmarkRoot, [string]$EngineRoot, [int[]]$Sizes = @())

    if ($Sizes.Count -eq 0) { $Sizes = @(25, 100, 500) }

    $results = @{
        started_at = (Get-Date).ToString("o")
        projects = @()
        summary = @{}
    }

    foreach ($size in $Sizes) {
        $projectName = "bench-$size-files"
        $projectPath = Join-Path $BenchmarkRoot $projectName

        if (-not (Test-Path -LiteralPath $projectPath)) {
            Write-Host "[SKIP] Benchmark $projectName not found" -ForegroundColor Yellow
            continue
        }

        Write-Host "[BENCH] Analyzing $projectName..." -ForegroundColor Cyan
        $startTime = Get-Date

        $psScript = Join-Path $EngineRoot "run-audit.ps1"
        $output = & powershell -NoProfile -ExecutionPolicy Bypass -File $psScript -Action index-repo -TargetProject $projectPath 2>&1
        $endTime = Get-Date

        $graphPath = Join-Path $projectPath ".aura\state\repo-graph.json"
        $graph = $null
        if (Test-Path -LiteralPath $graphPath) {
            try { $graph = Get-Content -LiteralPath $graphPath -Raw -Encoding UTF8 | ConvertFrom-Json } catch {}
        }

        $projResult = @{
            project = $projectName
            size = $size
            indexing_duration_seconds = [math]::Round(($endTime - $startTime).TotalSeconds, 2)
            files_indexed = if ($graph) { $graph.total_files } else { 0 }
            symbols_indexed = if ($graph) { $graph.total_symbols } else { 0 }
            indexing_success = ($null -ne $graph)
        }

        $results.projects += $projResult
        Write-Host "  Indexed $($projResult.files_indexed) files in $($projResult.indexing_duration_seconds)s" -ForegroundColor Green
    }

    $results.summary = @{
        total_projects = $results.projects.Count
        total_files = ($results.projects | Measure-Object -Property size -Sum).Sum
        max_size = ($results.projects | Measure-Object -Property size -Maximum).Maximum
        all_indexed = (($results.projects | Where-Object { -not $_.indexing_success }) | Measure-Object).Count -eq 0
        completed_at = (Get-Date).ToString("o")
    }

    return $results
}