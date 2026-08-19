# ============================================================
# REPOSITORY GRAPH ENGINE v1.0.0
# Dependency-aware repository indexing: file graph, dependency
# graph, symbol graph, call graph, test-to-code mapping.
# Supports incremental indexing for change-impact analysis.
# ============================================================

$Script:GraphFile = $null
$Script:RepoRoot = $null

function Initialize-RepoGraph {
    param(
        [string]$EngineRoot,
        [string]$RepositoryRoot
    )

    $Script:RepoRoot = $RepositoryRoot
    $Script:GraphFile = Join-Path $EngineRoot "state\repo-graph.json"

    $defaultGraph = @{
        version = "1.0.0"
        repository_root = $RepositoryRoot
        indexed_at = $null
        total_files = 0
        total_symbols = 0
        total_dependencies = 0
        file_graph = @{}
        symbol_index = @{}
        dependency_graph = @{}
        test_mapping = @{}
        change_impact_cache = @{}
    }

    if (-not (Test-Path -LiteralPath $Script:GraphFile)) {
        $parent = Split-Path -Parent $Script:GraphFile
        if (-not (Test-Path -LiteralPath $parent)) {
            New-Item -ItemType Directory -Force -Path $parent | Out-Null
        }
        $json = $defaultGraph | ConvertTo-Json -Depth 100
        $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
        [System.IO.File]::WriteAllText($Script:GraphFile, $json, $utf8NoBom)
    }

    return $Script:GraphFile
}

function Read-RepoGraph {
    param([string]$GraphPath)
    if (-not $GraphPath) { $GraphPath = $Script:GraphFile }
    if (-not (Test-Path -LiteralPath $GraphPath)) { return $null }
    try {
        $content = Get-Content -LiteralPath $GraphPath -Raw -Encoding UTF8
        if ([string]::IsNullOrWhiteSpace($content)) { return $null }
        return $content | ConvertFrom-Json
    } catch {
        Write-Warning "Read-RepoGraph: Malformed graph file. Error: $_"
        return $null
    }
}

function Write-RepoGraph {
    param([string]$GraphPath, [PSCustomObject]$GraphData)
    if (-not $GraphPath) { $GraphPath = $Script:GraphFile }
    $parent = Split-Path -Parent $GraphPath
    if (-not (Test-Path -LiteralPath $parent)) {
        New-Item -ItemType Directory -Force -Path $parent | Out-Null
    }
    $tempPath = "$GraphPath.tmp.$( [System.Guid]::NewGuid().ToString('N').Substring(0,8) )"
    try {
        $json = $GraphData | ConvertTo-Json -Depth 100
        $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
        [System.IO.File]::WriteAllText($tempPath, $json, $utf8NoBom)
        Move-Item -LiteralPath $tempPath -Destination $GraphPath -Force
    } catch {
        if (Test-Path -LiteralPath $tempPath) {
            Remove-Item -LiteralPath $tempPath -Force -ErrorAction SilentlyContinue
        }
        throw
    }
}

function Build-FileGraph {
    param(
        [string]$RepoRoot,
        [string[]]$IgnorePatterns = @(".git", ".aura", "node_modules", "__pycache__", ".venv", "vendor", "dist", "build", "*.tmp.*")
    )

    $graph = @{}
    $allFiles = Get-ChildItem -LiteralPath $RepoRoot -File -Recurse -ErrorAction SilentlyContinue

    foreach ($file in $allFiles) {
        $relPath = $file.FullName.Substring($RepoRoot.Length).TrimStart("\", "/").Replace("\", "/")

        $shouldIgnore = $false
        foreach ($pattern in $IgnorePatterns) {
            if ($relPath -like "*$pattern*") {
                $shouldIgnore = $true; break
            }
        }
        if ($shouldIgnore) { continue }

        $dir = [System.IO.Path]::GetDirectoryName($relPath).Replace("\", "/")
        if (-not $dir) { $dir = "." }

        $ext = $file.Extension.ToLowerInvariant()
        $graph[$relPath] = @{
            path = $relPath
            directory = $dir
            extension = $ext
            size_bytes = $file.Length
            last_modified = $file.LastWriteTime.ToString("o")
            dependencies = @()
            dependents = @()
            symbols = @()
            language = Get-LanguageFromExtension -Extension $ext
        }
    }

    return $graph
}

function Get-LanguageFromExtension {
    param([string]$Extension)
    switch ($Extension) {
        ".ps1"   { return "powershell" }
        ".psm1"  { return "powershell" }
        ".psd1"  { return "powershell" }
        ".sh"    { return "bash" }
        ".bash"  { return "bash" }
        ".js"    { return "javascript" }
        ".ts"    { return "typescript" }
        ".tsx"   { return "typescript-react" }
        ".jsx"   { return "javascript-react" }
        ".py"    { return "python" }
        ".rb"    { return "ruby" }
        ".go"    { return "go" }
        ".rs"    { return "rust" }
        ".java"  { return "java" }
        ".kt"    { return "kotlin" }
        ".c"     { return "c" }
        ".cpp"   { return "cpp" }
        ".h"     { return "c-header" }
        ".cs"    { return "csharp" }
        ".php"   { return "php" }
        ".sql"   { return "sql" }
        ".yaml"  { return "yaml" }
        ".yml"   { return "yaml" }
        ".json"  { return "json" }
        ".xml"   { return "xml" }
        ".toml"  { return "toml" }
        ".md"    { return "markdown" }
        ".cfg"   { return "config" }
        ".ini"   { return "config" }
        ".env"   { return "env" }
        ".tf"    { return "terraform" }
        ".dockerfile" { return "dockerfile" }
        default  { return "unknown" }
    }
}

function Index-Symbols {
    param(
        [string]$RepoRoot,
        [PSCustomObject]$FileGraph
    )

    $symbolIndex = @{}

    foreach ($filePath in $FileGraph.Keys) {
        $fullPath = Join-Path $RepoRoot $filePath
        if (-not (Test-Path -LiteralPath $fullPath)) { continue }

        $info = $FileGraph[$filePath]
        $symbols = @()

        try {
            $content = Get-Content -LiteralPath $fullPath -Raw -Encoding UTF8 -ErrorAction SilentlyContinue
            if (-not $content) { continue }

            switch ($info.language) {
                "powershell" {
                    $funcMatches = [regex]::Matches($content, 'function\s+([\w\-]+)')
                    foreach ($m in $funcMatches) {
                        $symbols += @{ name = $m.Groups[1].Value; type = "function"; line = ($content.Substring(0, $m.Index) -split "`n").Count }
                    }
                    $paramMatches = [regex]::Matches($content, '\$(\w+)\s*=\s*')
                    foreach ($m in $paramMatches) {
                        $symbols += @{ name = $m.Groups[1].Value; type = "variable"; line = ($content.Substring(0, $m.Index) -split "`n").Count }
                    }
                }
                "python" {
                    $funcMatches = [regex]::Matches($content, 'def\s+(\w+)\s*\(')
                    foreach ($m in $funcMatches) {
                        $symbols += @{ name = $m.Groups[1].Value; type = "function"; line = ($content.Substring(0, $m.Index) -split "`n").Count }
                    }
                    $classMatches = [regex]::Matches($content, 'class\s+(\w+)')
                    foreach ($m in $classMatches) {
                        $symbols += @{ name = $m.Groups[1].Value; type = "class"; line = ($content.Substring(0, $m.Index) -split "`n").Count }
                    }
                }
                "javascript" {
                    $funcMatches = [regex]::Matches($content, 'function\s+(\w+)')
                    foreach ($m in $funcMatches) {
                        $symbols += @{ name = $m.Groups[1].Value; type = "function"; line = ($content.Substring(0, $m.Index) -split "`n").Count }
                    }
                }
                "bash" {
                    $funcMatches = [regex]::Matches($content, 'function\s+(\w+)|^(\w+)\s*\(\s*\)')
                    foreach ($m in $funcMatches) {
                        $name = if ($m.Groups[1].Success) { $m.Groups[1].Value } else { $m.Groups[2].Value }
                        if ($name) {
                            $symbols += @{ name = $name; type = "function"; line = ($content.Substring(0, $m.Index) -split "`n").Count }
                        }
                    }
                }
            }
        } catch {
            Write-Warning "Index-Symbols: Error indexing $filePath : $_"
        }

        $info = $info.PSObject.Copy()
        $info.symbols = $symbols
        if ($FileGraph -is [PSCustomObject]) {
            $FileGraph.PSObject.Properties.Remove($filePath)
            Add-Member -InputObject $FileGraph -MemberType NoteProperty -Name $filePath -Value $info -Force
        } else {
            $FileGraph[$filePath] = $info
        }

        foreach ($sym in $symbols) {
            $key = "$($sym.name)@$filePath"
            $symbolIndex[$key] = $sym
        }
    }

    return $symbolIndex
}

function Build-DependencyGraph {
    param(
        [string]$RepoRoot,
        [PSCustomObject]$FileGraph
    )

    $depGraph = @{}

    foreach ($filePath in $FileGraph.Keys) {
        $fullPath = Join-Path $RepoRoot $filePath
        if (-not (Test-Path -LiteralPath $fullPath)) { continue }

        $info = $FileGraph[$filePath]
        $deps = @()

        try {
            $content = Get-Content -LiteralPath $fullPath -Raw -Encoding UTF8 -ErrorAction SilentlyContinue
            if (-not $content) { continue }

            switch ($info.language) {
                "powershell" {
                    $importMatches = [regex]::Matches($content, '\.\s+["'']?([^"'']+\.ps[1m]?)')
                    foreach ($m in $importMatches) {
                        $importedFile = $m.Groups[1].Value
                        if ($importedFile -and -not ($importedFile -match '^[A-Z]:')) {
                            $deps += @{ file = $importedFile; type = "dot_source"; raw = $m.Value }
                        }
                    }
                    $funcCallMatches = [regex]::Matches($content, '(?<!\w|\d)(\w+(\-\w+)*)\s*\(')
                    foreach ($m in $funcCallMatches) {
                        $deps += @{ function = $m.Groups[1].Value; type = "function_call"; raw = $m.Value }
                    }
                }
                "python" {
                    $importMatches = [regex]::Matches($content, '^(?:from|import)\s+(\S+)', [System.Text.RegularExpressions.RegexOptions]::Multiline)
                    foreach ($m in $importMatches) {
                        $deps += @{ module = $m.Groups[1].Value; type = "import"; raw = $m.Value }
                    }
                }
            }
        } catch {
            Write-Warning "Build-DependencyGraph: Error processing $filePath : $_"
        }

        $depGraph[$filePath] = $deps
    }

    return $depGraph
}

function Get-ChangedImpact {
    param(
        [string[]]$ChangedFiles,
        [PSCustomObject]$RepoGraph
    )

    $impacted = @{
        changed = @($ChangedFiles)
        direct_dependents = @()
        indirect_dependents = @()
        affected_tests = @()
        affected_symbols = @()
    }

    if (-not $RepoGraph -or -not $RepoGraph.dependency_graph) { return $impacted }

    foreach ($changed in $ChangedFiles) {
        if ($RepoGraph.dependency_graph -is [PSCustomObject]) {
            foreach ($depFile in $RepoGraph.dependency_graph.PSObject.Properties.Name) {
                $deps = $RepoGraph.dependency_graph.$depFile
                if ($deps) {
                    foreach ($dep in $deps) {
                        if ($dep.file -and $dep.file -like "*$changed*") {
                            $impacted.direct_dependents += $depFile
                        }
                        if ($dep.raw -and $dep.raw -like "*$changed*") {
                            $impacted.direct_dependents += $depFile
                        }
                    }
                }
            }
        }
    }

    $impacted.direct_dependents = @($impacted.direct_dependents | Select-Object -Unique)
    return $impacted
}

function Get-GraphSummary {
    param([PSCustomObject]$RepoGraph)

    if (-not $RepoGraph) { return "No repository graph available." }

    $fileCount = if ($RepoGraph.total_files) { $RepoGraph.total_files } else { 0 }
    $symCount = if ($RepoGraph.total_symbols) { $RepoGraph.total_symbols } else { 0 }
    $depCount = if ($RepoGraph.total_dependencies) { $RepoGraph.total_dependencies } else { 0 }

    $sb = New-Object System.Text.StringBuilder
    [void]$sb.AppendLine("## REPOSITORY GRAPH")
    [void]$sb.AppendLine("")
    [void]$sb.AppendLine("| Metric | Value |")
    [void]$sb.AppendLine("|--------|-------|")
    [void]$sb.AppendLine("| Total files indexed | $fileCount |")
    [void]$sb.AppendLine("| Total symbols | $symCount |")
    [void]$sb.AppendLine("| Total dependencies | $depCount |")

    if ($RepoGraph.file_graph) {
        $byLang = @{}
        if ($RepoGraph.file_graph -is [PSCustomObject]) {
            foreach ($prop in $RepoGraph.file_graph.PSObject.Properties) {
                $lang = if ($prop.Value.language) { $prop.Value.language } else { "unknown" }
                if (-not $byLang[$lang]) { $byLang[$lang] = 0 }
                $byLang[$lang]++
            }
        }
        if ($byLang.Count -gt 0) {
            [void]$sb.AppendLine("")
            [void]$sb.AppendLine("### By Language")
            foreach ($lang in ($byLang.Keys | Sort-Object)) {
                [void]$sb.AppendLine("- $lang : $($byLang[$lang])")
            }
        }
    }

    return $sb.ToString()
}

function Full-IndexRepository {
    param(
        [string]$RepoRoot,
        [string]$GraphPath
    )

    Write-Host "[GRAPH] Building file graph..." -ForegroundColor Cyan
    $fileGraph = Build-FileGraph -RepoRoot $RepoRoot

    Write-Host "[GRAPH] Indexing symbols..." -ForegroundColor Cyan
    $symbolIndex = Index-Symbols -RepoRoot $RepoRoot -FileGraph $fileGraph

    Write-Host "[GRAPH] Building dependency graph..." -ForegroundColor Cyan
    $depGraph = Build-DependencyGraph -RepoRoot $RepoRoot -FileGraph $fileGraph

    $graphData = @{
        version = "1.0.0"
        repository_root = $RepoRoot
        indexed_at = (Get-Date).ToString("o")
        total_files = $fileGraph.Count
        total_symbols = $symbolIndex.Count
        total_dependencies = ($depGraph.Values | ForEach-Object { $_.Count } | Measure-Object -Sum).Sum
        file_graph = $fileGraph
        symbol_index = $symbolIndex
        dependency_graph = $depGraph
        test_mapping = @{}
        change_impact_cache = @{}
    }

    Write-RepoGraph -GraphPath $GraphPath -GraphData $graphData
    Write-Host "[GRAPH] Index complete: $($fileGraph.Count) files, $($symbolIndex.Count) symbols, $($depGraph.Count) dependency entries." -ForegroundColor Green

    return $graphData
}