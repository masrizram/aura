# ============================================================
# SAST INTEGRATION MODULE v1.0.0
# Integrates external SAST tools: Semgrep, CodeQL, SonarQube,
# Bandit, ESLint security plugins.
# Classification: OPTIONAL
# ============================================================

function Invoke-SemgrepScan {
    param(
        [string]$ProjectPath,
        [string]$OutputPath,
        [string[]]$ExtraArgs = @()
    )

    $results = @{
        tool = "semgrep"
        available = $false
        timestamp = (Get-Date).ToString("o")
        findings = @()
        raw_output = ""
        exit_code = -1
    }

    $semgrepPath = Get-Command semgrep -ErrorAction SilentlyContinue
    if (-not $semgrepPath) {
        Write-Warning "Invoke-SemgrepScan: semgrep CLI not found on PATH. Skipping."
        if ($OutputPath) { Save-SASTRawOutput -Path $OutputPath -Data $results }
        return $results
    }

    $results.available = $true
    $configArgs = @("--config=auto")

    $outputFile = Join-Path ([System.IO.Path]::GetTempPath()) "aura-semgrep-$([System.Guid]::NewGuid().ToString('N').Substring(0,8)).json"

    try {
        $cwd = Get-Location
        Set-Location -LiteralPath $ProjectPath

        $processArgs = @(
            "scan",
            "--json",
            "--output", $outputFile,
            "--quiet",
            "--no-git-ignore"
        ) + $configArgs + $ExtraArgs

        Write-Host "[SAST] Running semgrep scan..." -ForegroundColor Cyan
        $output = & semgrep $processArgs 2>&1 | Out-String
        $results.exit_code = $LASTEXITCODE
        $results.raw_output = $output.Trim()

        if (Test-Path -LiteralPath $outputFile) {
            try {
                $rawJson = Get-Content -LiteralPath $outputFile -Raw -Encoding UTF8
                $parsed = $rawJson | ConvertFrom-Json

                if ($parsed.results) {
                    foreach ($finding in $parsed.results) {
                        $file = ""
                        if ($finding.path) { $file = $finding.path }
                        $line = 0
                        if ($finding.start -and $finding.start.line) { $line = [int]$finding.start.line }
                        $col = 0
                        if ($finding.start -and $finding.start.col) { $col = [int]$finding.start.col }

                        $severity = if ($finding.extra -and $finding.extra.severity) {
                            $finding.extra.severity
                        } else { "WARNING" }

                        $results.findings += @{
                            rule_id = if ($finding.check_id) { $finding.check_id } else { "unknown" }
                            message = if ($finding.extra -and $finding.extra.message) { $finding.extra.message } else { "" }
                            severity_original = $severity
                            severity_mapped = Convert-SASTSeverity -Tool "semgrep" -Severity $severity
                            file = $file
                            line = $line
                            column = $col
                            category = "SAST"
                            confidence = "HIGH"
                            evidence = if ($finding.extra -and $finding.extra.lines) { $finding.extra.lines } else { "" }
                        }
                    }
                }
            } catch {
                Write-Warning "Invoke-SemgrepScan: Failed to parse semgrep JSON output: $_"
            } finally {
                Remove-Item -LiteralPath $outputFile -Force -ErrorAction SilentlyContinue
            }
        }
    } catch {
        Write-Warning "Invoke-SemgrepScan: Execution error: $_"
        $results.exit_code = -1
        $results.raw_output = "Error: $_"
    } finally {
        Set-Location $cwd.Path
    }

    Write-Host "[SAST] Semgrep: $($results.findings.Count) finding(s)" -ForegroundColor $(if ($results.findings.Count -gt 0) { "Yellow" } else { "Green" })

    if ($OutputPath) { Save-SASTRawOutput -Path $OutputPath -Data $results }
    return $results
}

function Invoke-CodeQLAnalysis {
    param(
        [string]$ProjectPath,
        [string]$OutputPath,
        [string]$Language = "auto"
    )

    $results = @{
        tool = "codeql"
        available = $false
        timestamp = (Get-Date).ToString("o")
        findings = @()
        raw_output = ""
        exit_code = -1
    }

    $codeqlPath = Get-Command codeql -ErrorAction SilentlyContinue
    if (-not $codeqlPath) {
        Write-Warning "Invoke-CodeQLAnalysis: CodeQL CLI not found on PATH. Skipping."
        if ($OutputPath) { Save-SASTRawOutput -Path $OutputPath -Data $results }
        return $results
    }

    $results.available = $true
    $dbDir = Join-Path ([System.IO.Path]::GetTempPath()) "aura-codeql-db-$([System.Guid]::NewGuid().ToString('N').Substring(0,8))"
    $resultsFile = Join-Path ([System.IO.Path]::GetTempPath()) "aura-codeql-results-$([System.Guid]::NewGuid().ToString('N').Substring(0,8)).sarif"

    try {
        $cwd = Get-Location
        Set-Location -LiteralPath $ProjectPath

        $createArgs = @("database", "create", $dbDir, "--source-root", $ProjectPath)
        if ($Language -ne "auto") { $createArgs += "--language=$Language" }

        Write-Host "[SAST] Creating CodeQL database..." -ForegroundColor Cyan
        $createOutput = & codeql $createArgs 2>&1 | Out-String
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "Invoke-CodeQLAnalysis: Database creation failed: $($createOutput.Trim())"
            $results.raw_output = $createOutput.Trim()
            if ($OutputPath) { Save-SASTRawOutput -Path $OutputPath -Data $results }
            return $results
        }

        $analyzeArgs = @(
            "database", "analyze", $dbDir,
            "--format=sarif-latest",
            "--output", $resultsFile,
            "security-extended"
        )

        Write-Host "[SAST] Running CodeQL analysis with security-extended suite..." -ForegroundColor Cyan
        $analyzeOutput = & codeql $analyzeArgs 2>&1 | Out-String
        $results.exit_code = $LASTEXITCODE
        $results.raw_output = $analyzeOutput.Trim()

        if (Test-Path -LiteralPath $resultsFile) {
            try {
                $rawJson = Get-Content -LiteralPath $resultsFile -Raw -Encoding UTF8
                $parsed = $rawJson | ConvertFrom-Json

                if ($parsed.runs) {
                    foreach ($run in $parsed.runs) {
                        if ($run.results) {
                            foreach ($finding in $run.results) {
                                $ruleId = if ($finding.ruleId) { $finding.ruleId } else { "unknown" }
                                $message = if ($finding.message -and $finding.message.text) { $finding.message.text } else { "" }
                                $file = ""
                                $line = 0
                                $col = 0

                                if ($finding.locations -and $finding.locations.Count -gt 0) {
                                    $loc = $finding.locations[0]
                                    if ($loc.physicalLocation) {
                                        $pl = $loc.physicalLocation
                                        if ($pl.artifactLocation -and $pl.artifactLocation.uri) {
                                            $file = $pl.artifactLocation.uri
                                        }
                                        if ($pl.region) {
                                            if ($pl.region.startLine) { $line = [int]$pl.region.startLine }
                                            if ($pl.region.startColumn) { $col = [int]$pl.region.startColumn }
                                        }
                                    }
                                }

                                $severity = if ($finding.properties -and $finding.properties."problem.severity") {
                                    $finding.properties."problem.severity"
                                } else { "warning" }

                                $results.findings += @{
                                    rule_id = $ruleId
                                    message = $message
                                    severity_original = $severity
                                    severity_mapped = Convert-SASTSeverity -Tool "codeql" -Severity $severity
                                    file = $file
                                    line = $line
                                    column = $col
                                    category = "SAST_CODEQL"
                                    confidence = "HIGH"
                                    evidence = $message
                                }
                            }
                        }
                    }
                }
            } catch {
                Write-Warning "Invoke-CodeQLAnalysis: Failed to parse SARIF output: $_"
            } finally {
                Remove-Item -LiteralPath $resultsFile -Force -ErrorAction SilentlyContinue
            }
        }
    } catch {
        Write-Warning "Invoke-CodeQLAnalysis: Execution error: $_"
        $results.exit_code = -1
        $results.raw_output = "Error: $_"
    } finally {
        Set-Location $cwd.Path
        if (Test-Path -LiteralPath $dbDir) {
            Remove-Item -LiteralPath $dbDir -Recurse -Force -ErrorAction SilentlyContinue
        }
    }

    Write-Host "[SAST] CodeQL: $($results.findings.Count) finding(s)" -ForegroundColor $(if ($results.findings.Count -gt 0) { "Yellow" } else { "Green" })

    if ($OutputPath) { Save-SASTRawOutput -Path $OutputPath -Data $results }
    return $results
}

function Invoke-SonarQubeScan {
    param(
        [string]$ProjectPath,
        [string]$SonarHostUrl,
        [string]$SonarToken,
        [string]$ProjectKey
    )

    $results = @{
        tool = "sonarqube"
        available = $false
        timestamp = (Get-Date).ToString("o")
        scan_id = ""
        findings = @()
        raw_output = ""
        exit_code = -1
    }

    if ([string]::IsNullOrWhiteSpace($SonarHostUrl)) {
        Write-Warning "Invoke-SonarQubeScan: SonarHostUrl not configured. Skipping."
        return $results
    }
    if ([string]::IsNullOrWhiteSpace($SonarToken)) {
        Write-Warning "Invoke-SonarQubeScan: SonarToken not configured. Skipping."
        return $results
    }

    $scannerPath = Get-Command sonar-scanner -ErrorAction SilentlyContinue
    if (-not $scannerPath) {
        Write-Warning "Invoke-SonarQubeScan: sonar-scanner CLI not found on PATH. Skipping."
        return $results
    }

    $results.available = $true

    try {
        $cwd = Get-Location
        Set-Location -LiteralPath $ProjectPath

        $env:SONAR_HOST_URL = $SonarHostUrl
        $env:SONAR_TOKEN = $SonarToken

        $args = @(
            "-Dsonar.projectKey=$ProjectKey",
            "-Dsonar.sources=.",
            "-Dsonar.host.url=$SonarHostUrl",
            "-Dsonar.login=$SonarToken"
        )

        Write-Host "[SAST] Running SonarQube scan (project: $ProjectKey)..." -ForegroundColor Cyan
        $output = & sonar-scanner $args 2>&1 | Out-String
        $results.exit_code = $LASTEXITCODE
        $results.raw_output = $output.Trim()

        if ($LASTEXITCODE -eq 0) {
            Write-Host "[SAST] SonarQube scan submitted. See dashboard at $SonarHostUrl/dashboard?id=$ProjectKey" -ForegroundColor Cyan
            $results.scan_id = "SONAR_$ProjectKey_$(Get-Date -Format 'yyyyMMddHHmmss')"
        } else {
            Write-Warning "Invoke-SonarQubeScan: Scanner exited with code $LASTEXITCODE."
        }
    } catch {
        Write-Warning "Invoke-SonarQubeScan: Execution error: $_"
        $results.exit_code = -1
        $results.raw_output = "Error: $_"
    } finally {
        Set-Location $cwd.Path
        Remove-Item Env:\SONAR_HOST_URL -ErrorAction SilentlyContinue
        Remove-Item Env:\SONAR_TOKEN -ErrorAction SilentlyContinue
    }

    return $results
}

function Invoke-BanditScan {
    param(
        [string]$ProjectPath,
        [string]$OutputPath
    )

    $results = @{
        tool = "bandit"
        available = $false
        timestamp = (Get-Date).ToString("o")
        findings = @()
        raw_output = ""
        exit_code = -1
    }

    $banditPath = Get-Command bandit -ErrorAction SilentlyContinue
    if (-not $banditPath) {
        Write-Warning "Invoke-BanditScan: bandit CLI not found on PATH. Skipping."
        if ($OutputPath) { Save-SASTRawOutput -Path $OutputPath -Data $results }
        return $results
    }

    $results.available = $true
    $outputFile = Join-Path ([System.IO.Path]::GetTempPath()) "aura-bandit-$([System.Guid]::NewGuid().ToString('N').Substring(0,8)).json"

    try {
        $cwd = Get-Location
        Set-Location -LiteralPath $ProjectPath

        $banditArgs = @(
            "-r", ".",
            "-f", "json",
            "-o", $outputFile,
            "-ll"
        )

        Write-Host "[SAST] Running Bandit scan (Python)..." -ForegroundColor Cyan
        $output = & bandit $banditArgs 2>&1 | Out-String
        $results.exit_code = $LASTEXITCODE
        $results.raw_output = $output.Trim()

        if (Test-Path -LiteralPath $outputFile) {
            try {
                $rawJson = Get-Content -LiteralPath $outputFile -Raw -Encoding UTF8
                $parsed = $rawJson | ConvertFrom-Json

                if ($parsed.results) {
                    foreach ($finding in $parsed.results) {
                        $results.findings += @{
                            rule_id = if ($finding.test_id) { $finding.test_id } else { "unknown" }
                            message = if ($finding.issue_text) { $finding.issue_text } else { "" }
                            severity_original = if ($finding.issue_severity) { $finding.issue_severity } else { "LOW" }
                            severity_mapped = Convert-SASTSeverity -Tool "bandit" -Severity $finding.issue_severity
                            file = if ($finding.filename) { $finding.filename } else { "" }
                            line = if ($finding.line_number) { [int]$finding.line_number } else { 0 }
                            column = if ($finding.col_offset) { [int]$finding.col_offset } else { 0 }
                            category = "SAST_PYTHON"
                            confidence = if ($finding.issue_confidence) { $finding.issue_confidence } else { "MEDIUM" }
                            evidence = if ($finding.code) { $finding.code.Trim() } else { "" }
                        }
                    }
                }
            } catch {
                Write-Warning "Invoke-BanditScan: Failed to parse Bandit JSON output: $_"
            } finally {
                Remove-Item -LiteralPath $outputFile -Force -ErrorAction SilentlyContinue
            }
        }
    } catch {
        Write-Warning "Invoke-BanditScan: Execution error: $_"
        $results.exit_code = -1
        $results.raw_output = "Error: $_"
    } finally {
        Set-Location $cwd.Path
    }

    Write-Host "[SAST] Bandit: $($results.findings.Count) finding(s)" -ForegroundColor $(if ($results.findings.Count -gt 0) { "Yellow" } else { "Green" })

    if ($OutputPath) { Save-SASTRawOutput -Path $OutputPath -Data $results }
    return $results
}

function Invoke-ESLintSecurityScan {
    param(
        [string]$ProjectPath,
        [string]$OutputPath
    )

    $results = @{
        tool = "eslint-security"
        available = $false
        timestamp = (Get-Date).ToString("o")
        findings = @()
        raw_output = ""
        exit_code = -1
    }

    $eslintPath = Get-Command eslint -ErrorAction SilentlyContinue
    if (-not $eslintPath) {
        Write-Warning "Invoke-ESLintSecurityScan: eslint CLI not found on PATH. Skipping."
        if ($OutputPath) { Save-SASTRawOutput -Path $OutputPath -Data $results }
        return $results
    }

    $pkgJson = Join-Path $ProjectPath "package.json"
    if (Test-Path -LiteralPath $pkgJson) {
        try {
            $pkg = Get-Content -LiteralPath $pkgJson -Raw -Encoding UTF8 | ConvertFrom-Json
            $hasSecurityPlugin = ($pkg.devDependencies -and ($pkg.devDependencies.PSObject.Properties.Name -contains "eslint-plugin-security")) -or
                                ($pkg.dependencies -and ($pkg.dependencies.PSObject.Properties.Name -contains "eslint-plugin-security"))
        } catch { }
    }

    if (-not $hasSecurityPlugin) {
        Write-Warning "Invoke-ESLintSecurityScan: eslint-plugin-security not found in project dependencies. Skipping."
        if ($OutputPath) { Save-SASTRawOutput -Path $OutputPath -Data $results }
        return $results
    }

    $results.available = $true
    $outputFile = Join-Path ([System.IO.Path]::GetTempPath()) "aura-eslint-$([System.Guid]::NewGuid().ToString('N').Substring(0,8)).json"

    try {
        $cwd = Get-Location
        Set-Location -LiteralPath $ProjectPath

        $eslintArgs = @(
            ".",
            "--format", "json",
            "--output-file", $outputFile,
            "--rule", "{'security/detect-object-injection':'warn','security/detect-non-literal-regexp':'warn','security/detect-non-literal-fs-filename':'warn','security/detect-non-literal-require':'warn','security/detect-child-process':'warn','security/detect-eval-with-expression':'warn','security/detect-no-csrf-before-method-override':'warn','security/detect-possible-timing-attacks':'warn','security/detect-pseudoRandomBytes':'warn','security/detect-unsafe-regex':'warn'}"
        )

        Write-Host "[SAST] Running ESLint security scan..." -ForegroundColor Cyan
        $output = & eslint $eslintArgs 2>&1 | Out-String
        $results.exit_code = $LASTEXITCODE
        $results.raw_output = $output.Trim()

        if (Test-Path -LiteralPath $outputFile) {
            try {
                $rawJson = Get-Content -LiteralPath $outputFile -Raw -Encoding UTF8
                $parsed = $rawJson | ConvertFrom-Json

                foreach ($fileEntry in $parsed) {
                    $filePath = if ($fileEntry.filePath) { $fileEntry.filePath } else { "" }
                    if ($fileEntry.messages) {
                        foreach ($msg in $fileEntry.messages) {
                            $ruleId = if ($msg.ruleId) { $msg.ruleId } else { "unknown" }
                            if ($ruleId -notmatch "^security/") { continue }

                            $severity = if ($msg.severity -eq 2) { "error" } else { "warning" }

                            $results.findings += @{
                                rule_id = $ruleId
                                message = if ($msg.message) { $msg.message } else { "" }
                                severity_original = $severity
                                severity_mapped = Convert-SASTSeverity -Tool "eslint" -Severity $severity
                                file = $filePath
                                line = if ($msg.line) { [int]$msg.line } else { 0 }
                                column = if ($msg.column) { [int]$msg.column } else { 0 }
                                category = "SAST_JAVASCRIPT"
                                confidence = "MEDIUM"
                                evidence = if ($msg.message) { $msg.message } else { "" }
                            }
                        }
                    }
                }
            } catch {
                Write-Warning "Invoke-ESLintSecurityScan: Failed to parse ESLint JSON output: $_"
            } finally {
                Remove-Item -LiteralPath $outputFile -Force -ErrorAction SilentlyContinue
            }
        }
    } catch {
        Write-Warning "Invoke-ESLintSecurityScan: Execution error: $_"
        $results.exit_code = -1
        $results.raw_output = "Error: $_"
    } finally {
        Set-Location $cwd.Path
    }

    Write-Host "[SAST] ESLint Security: $($results.findings.Count) finding(s)" -ForegroundColor $(if ($results.findings.Count -gt 0) { "Yellow" } else { "Green" })

    if ($OutputPath) { Save-SASTRawOutput -Path $OutputPath -Data $results }
    return $results
}

function Get-AvailableSASTTools {
    $tools = @{
        semgrep = (Get-Command semgrep -ErrorAction SilentlyContinue) -ne $null
        codeql = (Get-Command codeql -ErrorAction SilentlyContinue) -ne $null
        bandit = (Get-Command bandit -ErrorAction SilentlyContinue) -ne $null
        eslint = (Get-Command eslint -ErrorAction SilentlyContinue) -ne $null
        sonarqube = (Get-Command sonar-scanner -ErrorAction SilentlyContinue) -ne $null
    }

    Write-Host "`n[SAST TOOL AVAILABILITY]"
    foreach ($tool in $tools.Keys | Sort-Object) {
        $icon = if ($tools[$tool]) { "[INSTALLED]" } else { "[MISSING]" }
        $color = if ($tools[$tool]) { "Green" } else { "DarkGray" }
        Write-Host "  $icon $tool" -ForegroundColor $color
    }
    Write-Host ""

    return $tools
}

function Invoke-AllSASTScans {
    param(
        [string]$ProjectPath,
        [string]$EngineRoot
    )

    $config = Read-JsonFile (Join-Path $EngineRoot "..\\config\\aura.json")
    if (-not $config) {
        $config = Read-JsonFile (Join-Path (Split-Path -Parent $EngineRoot) "config\\aura.json")
    }

    $sastConfig = $null
    if ($config -and $config.sast) { $sastConfig = $config.sast }

    $allResults = @{
        timestamp = (Get-Date).ToString("o")
        project_path = $ProjectPath
        tools_available = @{}
        scans = @{}
        total_findings = 0
    }

    $sastDir = Join-Path $EngineRoot "sast-scans"
    if (-not (Test-Path -LiteralPath $sastDir)) {
        New-Item -ItemType Directory -Force -Path $sastDir | Out-Null
    }

    $tools = Get-AvailableSASTTools
    $allResults.tools_available = $tools

    if ($tools.semgrep) {
        $semEnabled = if ($sastConfig) { $sastConfig.tools.semgrep.enabled } else { $true }
        if (-not $semEnabled) { Write-Host "[SAST] Semgrep disabled by config." -ForegroundColor DarkGray }
        else {
            $semOutput = Join-Path $sastDir "semgrep-results.json"
            $semResult = Invoke-SemgrepScan -ProjectPath $ProjectPath -OutputPath $semOutput
            $allResults.scans["semgrep"] = @{
                findings_count = $semResult.findings.Count
                exit_code = $semResult.exit_code
                output_file = $semOutput
            }
            $allResults.total_findings += $semResult.findings.Count
        }
    }

    if ($tools.bandit) {
        $banditEnabled = if ($sastConfig) { $sastConfig.tools.bandit.enabled } else { $true }
        if (-not $banditEnabled) { Write-Host "[SAST] Bandit disabled by config." -ForegroundColor DarkGray }
        else {
            $banditOutput = Join-Path $sastDir "bandit-results.json"
            $banditResult = Invoke-BanditScan -ProjectPath $ProjectPath -OutputPath $banditOutput
            $allResults.scans["bandit"] = @{
                findings_count = $banditResult.findings.Count
                exit_code = $banditResult.exit_code
                output_file = $banditOutput
            }
            $allResults.total_findings += $banditResult.findings.Count
        }
    }

    if ($tools.eslint) {
        $eslintEnabled = if ($sastConfig) { $sastConfig.tools.eslint_security.enabled } else { $false }
        if (-not $eslintEnabled) { Write-Host "[SAST] ESLint Security disabled by config." -ForegroundColor DarkGray }
        else {
            $eslintOutput = Join-Path $sastDir "eslint-results.json"
            $eslintResult = Invoke-ESLintSecurityScan -ProjectPath $ProjectPath -OutputPath $eslintOutput
            $allResults.scans["eslint_security"] = @{
                findings_count = $eslintResult.findings.Count
                exit_code = $eslintResult.exit_code
                output_file = $eslintOutput
            }
            $allResults.total_findings += $eslintResult.findings.Count
        }
    }

    if ($tools.codeql) {
        $codeqlEnabled = if ($sastConfig) { $sastConfig.tools.codeql.enabled } else { $false }
        if (-not $codeqlEnabled) { Write-Host "[SAST] CodeQL disabled by config." -ForegroundColor DarkGray }
        else {
            $codeqlOutput = Join-Path $sastDir "codeql-results.json"
            $codeqlResult = Invoke-CodeQLAnalysis -ProjectPath $ProjectPath -OutputPath $codeqlOutput
            $allResults.scans["codeql"] = @{
                findings_count = $codeqlResult.findings.Count
                exit_code = $codeqlResult.exit_code
                output_file = $codeqlOutput
            }
            $allResults.total_findings += $codeqlResult.findings.Count
        }
    }

    $summaryOutput = Join-Path $sastDir "sast-summary.json"
    $json = $allResults | ConvertTo-Json -Depth 100
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($summaryOutput, $json, $utf8NoBom)

    $reportPath = Join-Path $EngineRoot "reports\\sast-report.md"
    $report = Generate-SASTRawReport -AllResults $allResults
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($reportPath, $report, $utf8NoBom)

    Write-Host "[SAST] Scan summary: $($allResults.total_findings) total finding(s) across $($allResults.scans.Count) tool(s)" -ForegroundColor Cyan
    Write-Host "[SAST] Summary: $summaryOutput" -ForegroundColor Green
    Write-Host "[SAST] Report: $reportPath" -ForegroundColor Green

    return $allResults
}

function Convert-SASTToAuraFindings {
    param(
        [PSCustomObject]$SASTResults,
        [string]$ToolName,
        [int]$CycleNumber
    )

    $findings = @()

    if (-not $SASTResults -or -not $SASTResults.findings -or $SASTResults.findings.Count -eq 0) {
        return $findings
    }

    foreach ($raw in $SASTResults.findings) {
        $finding = @{
            id = "SAST-${ToolName}-$([System.Guid]::NewGuid().ToString('N').Substring(0,8).ToUpper())"
            severity = if ($raw.severity_mapped) { $raw.severity_mapped } else { "P4" }
            category = if ($raw.category) { $raw.category } else { "SAST" }
            status = "OPEN"
            problem = if ($raw.message) { $raw.message } else { "SAST finding: $($raw.rule_id)" }
            evidence = if ($raw.evidence) { $raw.evidence } else { "" }
            file = if ($raw.file) { $raw.file } else { "" }
            line = if ($raw.line) { [int]$raw.line } else { 0 }
            column = if ($raw.column) { [int]$raw.column } else { 0 }
            tool = $ToolName
            rule_id = if ($raw.rule_id) { $raw.rule_id } else { "unknown" }
            confidence = if ($raw.confidence) { $raw.confidence } else { "MEDIUM" }
            cycle = $CycleNumber
            discovered_at = (Get-Date).ToString("o")
            risk_score = 0
        }

        $weights = @{ P0=625; P1=405; P2=216; P3=90; P4=30; P5=6 }
        if ($weights.ContainsKey($finding.severity)) {
            $finding.risk_score = $weights[$finding.severity]
        }

        $findings += $finding
    }

    return $findings
}

function Convert-SASTSeverity {
    param(
        [string]$Tool,
        [string]$Severity
    )

    if ([string]::IsNullOrWhiteSpace($Severity)) { return "P4" }

    $normalized = $Severity.ToUpperInvariant()

    $mapping = @{
        "CRITICAL" = "P0"
        "ERROR" = "P1"
        "HIGH" = "P1"
        "MEDIUM" = "P2"
        "MODERATE" = "P2"
        "WARNING" = "P4"
        "LOW" = "P4"
        "NOTE" = "P5"
        "INFO" = "P5"
    }

    if ($mapping.ContainsKey($normalized)) {
        return $mapping[$normalized]
    }

    return "P4"
}

function Generate-SASTRawReport {
    param(
        [hashtable]$AllResults
    )

    $sb = New-Object System.Text.StringBuilder
    [void]$sb.AppendLine("# SAST Scan Report")
    [void]$sb.AppendLine("")
    [void]$sb.AppendLine("**Generated:** $($AllResults.timestamp)")
    [void]$sb.AppendLine("**Project:** $($AllResults.project_path)")
    [void]$sb.AppendLine("")
    [void]$sb.AppendLine("## Tool Availability")
    [void]$sb.AppendLine("")
    [void]$sb.AppendLine("| Tool | Status |")
    [void]$sb.AppendLine("|------|--------|")

    if ($AllResults.tools_available) {
        foreach ($tool in $AllResults.tools_available.Keys | Sort-Object) {
            $status = if ($AllResults.tools_available[$tool]) { "INSTALLED" } else { "NOT FOUND" }
            [void]$sb.AppendLine("| $tool | $status |")
        }
    }

    [void]$sb.AppendLine("")
    [void]$sb.AppendLine("## Scan Results")
    [void]$sb.AppendLine("")
    [void]$sb.AppendLine("| Tool | Findings | Exit Code | Output File |")
    [void]$sb.AppendLine("|------|----------|-----------|-------------|")

    if ($AllResults.scans) {
        foreach ($scan in $AllResults.scans.Keys | Sort-Object) {
            $s = $AllResults.scans[$scan]
            $outputFile = if ($s.output_file) { Split-Path -Leaf $s.output_file } else { "N/A" }
            [void]$sb.AppendLine("| $scan | $($s.findings_count) | $($s.exit_code) | $outputFile |")
        }
    }

    [void]$sb.AppendLine("")
    [void]$sb.AppendLine("**Total Findings:** $($AllResults.total_findings)")

    return $sb.ToString()
}

function Generate-SASTReport {
    param(
        [hashtable]$AllResults,
        [string]$OutputPath
    )

    $report = Generate-SASTRawReport -AllResults $AllResults

    if ($OutputPath) {
        $parent = Split-Path -Parent $OutputPath
        if (-not (Test-Path -LiteralPath $parent)) {
            New-Item -ItemType Directory -Force -Path $parent | Out-Null
        }
        $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
        [System.IO.File]::WriteAllText($OutputPath, $report, $utf8NoBom)
    }

    return $report
}

function Save-SASTRawOutput {
    param(
        [string]$Path,
        [hashtable]$Data
    )

    $parent = Split-Path -Parent $Path
    if (-not (Test-Path -LiteralPath $parent)) {
        New-Item -ItemType Directory -Force -Path $parent | Out-Null
    }

    $json = $Data | ConvertTo-Json -Depth 100
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $json, $utf8NoBom)
}

Export-ModuleMember -Function Invoke-SemgrepScan, Invoke-CodeQLAnalysis,
    Invoke-SonarQubeScan, Invoke-BanditScan, Invoke-ESLintSecurityScan,
    Get-AvailableSASTTools, Invoke-AllSASTScans, Convert-SASTToAuraFindings,
    Convert-SASTSeverity, Generate-SASTReport, Generate-SASTRawReport