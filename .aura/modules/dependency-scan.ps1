# ============================================================
# DEPENDENCY & SECRET SCANNING MODULE v1.0.0
# Dependency vulnerability scanning and secret detection
# with external tool integration.
# Classification: OPTIONAL
# ============================================================

function Invoke-DependencyCheck {
    param(
        [string]$ProjectPath,
        [string]$OutputPath
    )

    $results = @{
        tool = "dependency-check"
        available = $false
        timestamp = (Get-Date).ToString("o")
        findings = @()
        raw_output = ""
        exit_code = -1
    }

    $depCheckPath = Get-Command dependency-check -ErrorAction SilentlyContinue
    if (-not $depCheckPath) {
        $depCheckPath = Get-Command dependency-check.bat -ErrorAction SilentlyContinue
    }
    if (-not $depCheckPath) {
        Write-Warning "Invoke-DependencyCheck: OWASP Dependency-Check not found on PATH. Skipping."
        if ($OutputPath) { Save-DepRawOutput -Path $OutputPath -Data $results }
        return $results
    }

    $results.available = $true
    $outputDir = Join-Path ([System.IO.Path]::GetTempPath()) "aura-depcheck-$([System.Guid]::NewGuid().ToString('N').Substring(0,8))"

    try {
        $cwd = Get-Location
        Set-Location -LiteralPath $ProjectPath
        New-Item -ItemType Directory -Force -Path $outputDir | Out-Null

        $args = @(
            "--project", (Split-Path -Leaf $ProjectPath),
            "--scan", $ProjectPath,
            "--out", $outputDir,
            "--format", "JSON",
            "--noupdate"
        )

        Write-Host "[DEP] Running OWASP Dependency-Check..." -ForegroundColor Cyan
        $output = & $depCheckPath $args 2>&1 | Out-String
        $results.exit_code = $LASTEXITCODE
        $results.raw_output = $output.Trim()

        $jsonFiles = Get-ChildItem -LiteralPath $outputDir -Filter "*.json" -ErrorAction SilentlyContinue
        foreach ($jf in $jsonFiles) {
            try {
                $rawJson = Get-Content -LiteralPath $jf.FullName -Raw -Encoding UTF8
                $parsed = $rawJson | ConvertFrom-Json

                if ($parsed.dependencies) {
                    foreach ($dep in $parsed.dependencies) {
                        if ($dep.vulnerabilities -and $dep.vulnerabilities.Count -gt 0) {
                            foreach ($vuln in $dep.vulnerabilities) {
                                $cvss = 0.0
                                if ($vuln.cvssv3 -and $vuln.cvssv3.baseScore) {
                                    $cvss = [double]$vuln.cvssv3.baseScore
                                } elseif ($vuln.cvssv2 -and $vuln.cvssv2.score) {
                                    $cvss = [double]$vuln.cvssv2.score
                                }

                                $results.findings += @{
                                    dependency = if ($dep.fileName) { $dep.fileName } else { "unknown" }
                                    cve = if ($vuln.name) { $vuln.name } else { "unknown" }
                                    severity_cvss = $cvss
                                    severity_mapped = Convert-VulnSeverity -CvssScore $cvss
                                    description = if ($vuln.description) { $vuln.description } else { "" }
                                    category = "VULNERABLE_DEPENDENCY"
                                    confidence = "HIGH"
                                    evidence = "CVSS: $cvss"
                                }
                            }
                        }
                    }
                }
            } catch {
                Write-Warning "Invoke-DependencyCheck: Failed to parse output: $_"
            }
        }
    } catch {
        Write-Warning "Invoke-DependencyCheck: Execution error: $_"
        $results.exit_code = -1
        $results.raw_output = "Error: $_"
    } finally {
        Set-Location $cwd.Path
        if (Test-Path -LiteralPath $outputDir) {
            Remove-Item -LiteralPath $outputDir -Recurse -Force -ErrorAction SilentlyContinue
        }
    }

    Write-Host "[DEP] Dependency-Check: $($results.findings.Count) vulnerable dependency/dependencies" -ForegroundColor $(if ($results.findings.Count -gt 0) { "Yellow" } else { "Green" })

    if ($OutputPath) { Save-DepRawOutput -Path $OutputPath -Data $results }
    return $results
}

function Invoke-NPMAudit {
    param(
        [string]$ProjectPath,
        [string]$OutputPath
    )

    $results = @{
        tool = "npm-audit"
        available = $false
        timestamp = (Get-Date).ToString("o")
        findings = @()
        raw_output = ""
        exit_code = -1
    }

    $npmPath = Get-Command npm -ErrorAction SilentlyContinue
    if (-not $npmPath) {
        Write-Warning "Invoke-NPMAudit: npm not found on PATH. Skipping."
        if ($OutputPath) { Save-DepRawOutput -Path $OutputPath -Data $results }
        return $results
    }

    $pkgLock = Join-Path $ProjectPath "package-lock.json"
    $npmShrinkwrap = Join-Path $ProjectPath "npm-shrinkwrap.json"
    if (-not (Test-Path -LiteralPath $pkgLock) -and -not (Test-Path -LiteralPath $npmShrinkwrap)) {
        Write-Warning "Invoke-NPMAudit: No package-lock.json or npm-shrinkwrap.json found. Skipping."
        if ($OutputPath) { Save-DepRawOutput -Path $OutputPath -Data $results }
        return $results
    }

    $pkgJson = Join-Path $ProjectPath "package.json"
    if (-not (Test-Path -LiteralPath $pkgJson)) {
        Write-Warning "Invoke-NPMAudit: No package.json found. Skipping."
        if ($OutputPath) { Save-DepRawOutput -Path $OutputPath -Data $results }
        return $results
    }

    $results.available = $true
    $outputFile = Join-Path ([System.IO.Path]::GetTempPath()) "aura-npm-audit-$([System.Guid]::NewGuid().ToString('N').Substring(0,8)).json"

    try {
        $cwd = Get-Location
        Set-Location -LiteralPath $ProjectPath

        Write-Host "[DEP] Running npm audit..." -ForegroundColor Cyan
        $output = & npm audit --json 2>&1 | Out-String
        $results.exit_code = $LASTEXITCODE

        try {
            $parsed = $output | ConvertFrom-Json

            if ($parsed.vulnerabilities) {
                foreach ($vulnKey in $parsed.vulnerabilities.PSObject.Properties) {
                    $vuln = $vulnKey.Value
                    if (-not $vuln) { continue }

                    $severity = if ($vuln.severity) { $vuln.severity } else { "low" }
                    $name = if ($vuln.name) { $vuln.name } else { $vulnKey.Name }

                    foreach ($via in $vuln.via) {
                        if ($via -is [string]) { continue }
                        if (-not $via) { continue }

                        $cveId = if ($via.source) { $via.source } else { "unknown" }

                        $results.findings += @{
                            package = $name
                            cve = $cveId
                            severity_original = $severity
                            severity_mapped = Convert-VulnSeverity -Severity $severity
                            description = if ($via.title) { $via.title } else { "Vulnerability in $name" }
                            category = "VULNERABLE_NPM_PACKAGE"
                            confidence = "HIGH"
                            evidence = if ($via.url) { $via.url } else { "" }
                            fix_available = if ($via.fixAvailable) { $true } else { $false }
                        }
                    }
                }
            }
        } catch {
            if ($output -match "found 0 vulnerabilities") {
                $results.raw_output = $output.Trim()
            } else {
                Write-Warning "Invoke-NPMAudit: Failed to parse audit output: $_"
                $results.raw_output = $output.Trim()
            }
        }
    } catch {
        Write-Warning "Invoke-NPMAudit: Execution error: $_"
        $results.exit_code = -1
        $results.raw_output = "Error: $_"
    } finally {
        Set-Location $cwd.Path
    }

    Write-Host "[DEP] npm audit: $($results.findings.Count) vulnerability/vulnerabilities" -ForegroundColor $(if ($results.findings.Count -gt 0) { "Yellow" } else { "Green" })

    if ($OutputPath) { Save-DepRawOutput -Path $OutputPath -Data $results }
    return $results
}

function Invoke-ComposerAudit {
    param(
        [string]$ProjectPath,
        [string]$OutputPath
    )

    $results = @{
        tool = "composer-audit"
        available = $false
        timestamp = (Get-Date).ToString("o")
        findings = @()
        raw_output = ""
        exit_code = -1
    }

    $composerPath = Get-Command composer -ErrorAction SilentlyContinue
    if (-not $composerPath) {
        Write-Warning "Invoke-ComposerAudit: composer not found on PATH. Skipping."
        if ($OutputPath) { Save-DepRawOutput -Path $OutputPath -Data $results }
        return $results
    }

    $composerLock = Join-Path $ProjectPath "composer.lock"
    if (-not (Test-Path -LiteralPath $composerLock)) {
        Write-Warning "Invoke-ComposerAudit: No composer.lock found. Skipping."
        if ($OutputPath) { Save-DepRawOutput -Path $OutputPath -Data $results }
        return $results
    }

    $results.available = $true

    try {
        $cwd = Get-Location
        Set-Location -LiteralPath $ProjectPath

        Write-Host "[DEP] Running composer audit..." -ForegroundColor Cyan
        $output = & composer audit --format=json 2>&1 | Out-String
        $results.exit_code = $LASTEXITCODE

        try {
            $parsed = $output | ConvertFrom-Json

            if ($parsed.advisories) {
                foreach ($advisoryKey in $parsed.advisories.PSObject.Properties) {
                    $advisory = $advisoryKey.Value

                    $results.findings += @{
                        package = if ($advisory.packageName) { $advisory.packageName } else { $advisoryKey.Name }
                        cve = if ($advisory.cve) { $advisory.cve } else { "unknown" }
                        severity_original = if ($advisory.severity) { $advisory.severity } else { "medium" }
                        severity_mapped = Convert-VulnSeverity -Severity $advisory.severity
                        description = if ($advisory.title) { $advisory.title } else { "" }
                        category = "VULNERABLE_COMPOSER_PACKAGE"
                        confidence = "HIGH"
                        evidence = if ($advisory.link) { $advisory.link } else { "" }
                    }
                }
            }
        } catch {
            $results.raw_output = $output.Trim()
        }
    } catch {
        Write-Warning "Invoke-ComposerAudit: Execution error: $_"
        $results.exit_code = -1
        $results.raw_output = "Error: $_"
    } finally {
        Set-Location $cwd.Path
    }

    Write-Host "[DEP] composer audit: $($results.findings.Count) advisory/advisories" -ForegroundColor $(if ($results.findings.Count -gt 0) { "Yellow" } else { "Green" })

    if ($OutputPath) { Save-DepRawOutput -Path $OutputPath -Data $results }
    return $results
}

function Invoke-PipAudit {
    param(
        [string]$ProjectPath,
        [string]$OutputPath
    )

    $results = @{
        tool = "pip-audit"
        available = $false
        timestamp = (Get-Date).ToString("o")
        findings = @()
        raw_output = ""
        exit_code = -1
    }

    $pipAuditPath = Get-Command pip-audit -ErrorAction SilentlyContinue
    if (-not $pipAuditPath) {
        Write-Warning "Invoke-PipAudit: pip-audit not found on PATH. Skipping."
        if ($OutputPath) { Save-DepRawOutput -Path $OutputPath -Data $results }
        return $results
    }

    $reqFile = Join-Path $ProjectPath "requirements.txt"
    $pyproject = Join-Path $ProjectPath "pyproject.toml"
    if (-not (Test-Path -LiteralPath $reqFile) -and -not (Test-Path -LiteralPath $pyproject)) {
        Write-Warning "Invoke-PipAudit: No requirements.txt or pyproject.toml found. Skipping."
        if ($OutputPath) { Save-DepRawOutput -Path $OutputPath -Data $results }
        return $results
    }

    $results.available = $true
    $outputFile = Join-Path ([System.IO.Path]::GetTempPath()) "aura-pipaudit-$([System.Guid]::NewGuid().ToString('N').Substring(0,8)).json"

    try {
        $cwd = Get-Location
        Set-Location -LiteralPath $ProjectPath

        $auditArgs = @(
            "-r", "requirements.txt",
            "--format=json",
            "-o", $outputFile
        )

        if (-not (Test-Path -LiteralPath $reqFile)) {
            $auditArgs = @("--format=json", "-o", $outputFile)
        }

        Write-Host "[DEP] Running pip-audit..." -ForegroundColor Cyan
        $output = & pip-audit $auditArgs 2>&1 | Out-String
        $results.exit_code = $LASTEXITCODE

        if (Test-Path -LiteralPath $outputFile) {
            try {
                $rawJson = Get-Content -LiteralPath $outputFile -Raw -Encoding UTF8
                $parsed = $rawJson | ConvertFrom-Json

                if ($parsed -is [array]) {
                    foreach ($vuln in $parsed) {
                        $results.findings += @{
                            package = if ($vuln.name) { $vuln.name } else { "unknown" }
                            cve = if ($vuln.id) { $vuln.id } else { "unknown" }
                            severity_original = if ($vuln.severity) { $vuln.severity } else { "MEDIUM" }
                            severity_mapped = Convert-VulnSeverity -Severity $vuln.severity
                            description = if ($vuln.description) { $vuln.description } else { "" }
                            category = "VULNERABLE_PYTHON_PACKAGE"
                            confidence = "HIGH"
                            evidence = if ($vuln.fix_versions) { "Fix: $($vuln.fix_versions -join ', ')" } else { "" }
                        }
                    }
                }
            } catch {
                Write-Warning "Invoke-PipAudit: Failed to parse JSON output: $_"
            } finally {
                Remove-Item -LiteralPath $outputFile -Force -ErrorAction SilentlyContinue
            }
        }

        $results.raw_output = $output.Trim()
    } catch {
        Write-Warning "Invoke-PipAudit: Execution error: $_"
        $results.exit_code = -1
        $results.raw_output = "Error: $_"
    } finally {
        Set-Location $cwd.Path
    }

    Write-Host "[DEP] pip-audit: $($results.findings.Count) vulnerability/vulnerabilities" -ForegroundColor $(if ($results.findings.Count -gt 0) { "Yellow" } else { "Green" })

    if ($OutputPath) { Save-DepRawOutput -Path $OutputPath -Data $results }
    return $results
}

function Invoke-GitleaksScan {
    param(
        [string]$ProjectPath,
        [string]$OutputPath,
        [switch]$ScanHistory
    )

    $results = @{
        tool = "gitleaks"
        available = $false
        timestamp = (Get-Date).ToString("o")
        findings = @()
        raw_output = ""
        exit_code = -1
    }

    $gitleaksPath = Get-Command gitleaks -ErrorAction SilentlyContinue
    if (-not $gitleaksPath) {
        Write-Warning "Invoke-GitleaksScan: gitleaks CLI not found on PATH. Skipping."
        if ($OutputPath) { Save-DepRawOutput -Path $OutputPath -Data $results }
        return $results
    }

    $results.available = $true
    $outputFile = Join-Path ([System.IO.Path]::GetTempPath()) "aura-gitleaks-$([System.Guid]::NewGuid().ToString('N').Substring(0,8)).json"

    try {
        $cwd = Get-Location
        Set-Location -LiteralPath $ProjectPath

        $gitleaksArgs = @(
            "detect",
            "--source", $ProjectPath,
            "--report-format", "json",
            "--report-path", $outputFile,
            "--no-git"
        )

        if (-not $ScanHistory) {
            $gitleaksArgs += "--no-git"
        }

        Write-Host "[DEP] Running Gitleaks secret scan..." -ForegroundColor Cyan
        $output = & gitleaks $gitleaksArgs 2>&1 | Out-String
        $results.exit_code = $LASTEXITCODE

        if (Test-Path -LiteralPath $outputFile) {
            try {
                $rawJson = Get-Content -LiteralPath $outputFile -Raw -Encoding UTF8
                $parsed = $rawJson | ConvertFrom-Json

                if ($parsed -is [array]) {
                    foreach ($leak in $parsed) {
                        $secret = if ($leak.Secret) {
                            if ($leak.Secret.Length -gt 20) { $leak.Secret.Substring(0, 20) + "..." } else { $leak.Secret }
                        } else { "***" }

                        $results.findings += @{
                            rule_id = if ($leak.RuleID) { $leak.RuleID } else { "unknown" }
                            file = if ($leak.File) { $leak.File } else { "" }
                            line = if ($leak.StartLine) { [int]$leak.StartLine } else { 0 }
                            description = if ($leak.Description) { $leak.Description } else { "Hardcoded secret detected" }
                            severity_mapped = "P0"
                            category = "HARDCODED_SECRET"
                            confidence = "HIGH"
                            evidence = "Match: *** (rule: $($leak.RuleID))"
                        }
                    }
                }
            } catch {
                Write-Warning "Invoke-GitleaksScan: Failed to parse JSON output: $_"
            } finally {
                Remove-Item -LiteralPath $outputFile -Force -ErrorAction SilentlyContinue
            }
        }

        $results.raw_output = $output.Trim()
    } catch {
        Write-Warning "Invoke-GitleaksScan: Execution error: $_"
        $results.exit_code = -1
        $results.raw_output = "Error: $_"
    } finally {
        Set-Location $cwd.Path
    }

    Write-Host "[DEP] Gitleaks: $($results.findings.Count) secret(s) found" -ForegroundColor $(if ($results.findings.Count -gt 0) { "Yellow" } else { "Green" })

    if ($OutputPath) { Save-DepRawOutput -Path $OutputPath -Data $results }
    return $results
}

function Invoke-TruffleHogScan {
    param(
        [string]$ProjectPath,
        [string]$OutputPath
    )

    $results = @{
        tool = "trufflehog"
        available = $false
        timestamp = (Get-Date).ToString("o")
        findings = @()
        raw_output = ""
        exit_code = -1
    }

    $truffleHogPath = Get-Command trufflehog -ErrorAction SilentlyContinue
    if (-not $truffleHogPath) {
        Write-Warning "Invoke-TruffleHogScan: trufflehog CLI not found on PATH. Skipping."
        if ($OutputPath) { Save-DepRawOutput -Path $OutputPath -Data $results }
        return $results
    }

    $results.available = $true
    $outputFile = Join-Path ([System.IO.Path]::GetTempPath()) "aura-trufflehog-$([System.Guid]::NewGuid().ToString('N').Substring(0,8)).json"

    try {
        $cwd = Get-Location
        Set-Location -LiteralPath $ProjectPath

        $args = @(
            "filesystem", $ProjectPath,
            "--json",
            "--no-update"
        )

        Write-Host "[DEP] Running TruffleHog secret scan (entropy-based)..." -ForegroundColor Cyan
        $output = & trufflehog $args 2>&1 | Out-String
        $results.exit_code = $LASTEXITCODE

        if (-not [string]::IsNullOrWhiteSpace($output)) {
            $lines = $output -split "`n"
            foreach ($line in $lines) {
                if ([string]::IsNullOrWhiteSpace($line)) { continue }
                try {
                    $parsed = $line | ConvertFrom-Json

                    $results.findings += @{
                        rule_id = if ($parsed.DetectorName) { $parsed.DetectorName } else { "unknown" }
                        file = if ($parsed.SourceMetadata -and $parsed.SourceMetadata.Data) {
                            if ($parsed.SourceMetadata.Data.Filesystem -and $parsed.SourceMetadata.Data.Filesystem.file) {
                                $parsed.SourceMetadata.Data.Filesystem.file
                            } else { "" }
                        } else { "" }
                        line = if ($parsed.SourceMetadata -and $parsed.SourceMetadata.Data) {
                            if ($parsed.SourceMetadata.Data.Filesystem -and $parsed.SourceMetadata.Data.Filesystem.line) {
                                [int]$parsed.SourceMetadata.Data.Filesystem.line
                            } else { 0 }
                        } else { 0 }
                        description = if ($parsed.DetectorName) { "Secret detected by $($parsed.DetectorName)" } else { "Secret detected" }
                        severity_mapped = "P0"
                        category = "HARDCODED_SECRET_ENTROPY"
                        confidence = if ($parsed.Verified) { "HIGH" } else { "MEDIUM" }
                        evidence = if ($parsed.Raw) {
                            if ($parsed.Raw.Length -gt 20) { $parsed.Raw.Substring(0, 20) + "..." } else { $parsed.Raw }
                        } else { "" }
                    }
                } catch { }
            }
        }

        $results.raw_output = $output.Trim()
    } catch {
        Write-Warning "Invoke-TruffleHogScan: Execution error: $_"
        $results.exit_code = -1
        $results.raw_output = "Error: $_"
    } finally {
        Set-Location $cwd.Path
        if (Test-Path -LiteralPath $outputFile) {
            Remove-Item -LiteralPath $outputFile -Force -ErrorAction SilentlyContinue
        }
    }

    Write-Host "[DEP] TruffleHog: $($results.findings.Count) secret(s) found" -ForegroundColor $(if ($results.findings.Count -gt 0) { "Yellow" } else { "Green" })

    if ($OutputPath) { Save-DepRawOutput -Path $OutputPath -Data $results }
    return $results
}

function Invoke-SBOMGenerate {
    param(
        [string]$ProjectPath,
        [string]$OutputPath,
        [string]$Format = "cyclonedx"
    )

    $results = @{
        tool = "sbom-generator"
        available = $false
        timestamp = (Get-Date).ToString("o")
        format = $Format
        output_path = $OutputPath
        error = ""
    }

    $syftPath = Get-Command syft -ErrorAction SilentlyContinue
    if ($syftPath) {
        $results.available = $true
        $syftFormat = if ($Format -eq "spdx") { "spdx-json" } else { "cyclonedx-json" }

        try {
            $cwd = Get-Location
            Set-Location -LiteralPath $ProjectPath

            $syftArgs = @(
                $ProjectPath,
                "-o", "$syftFormat-json",
                "--file", $OutputPath
            )

            Write-Host "[DEP] Generating $Format SBOM with syft..." -ForegroundColor Cyan
            $output = & syft $syftArgs 2>&1 | Out-String
            $results.exit_code = $LASTEXITCODE

            if ($LASTEXITCODE -ne 0) {
                Write-Warning "Invoke-SBOMGenerate: syft exited with code ${LASTEXITCODE}: $output"
                $results.error = $output.Trim()
            } else {
                Write-Host "[DEP] SBOM generated: $OutputPath" -ForegroundColor Green
            }
        } catch {
            Write-Warning "Invoke-SBOMGenerate: Execution error: $_"
            $results.exit_code = -1
            $results.error = "Error: $_"
        } finally {
            Set-Location $cwd.Path
        }

        return $results
    }

    Write-Warning "Invoke-SBOMGenerate: syft CLI not found. Generating manual SBOM from package manifests."

    $results.available = $false
    try {
        $sbom = Build-ManualSBOM -ProjectPath $ProjectPath -Format $Format

        if ($OutputPath) {
            $parent = Split-Path -Parent $OutputPath
            if (-not (Test-Path -LiteralPath $parent)) {
                New-Item -ItemType Directory -Force -Path $parent | Out-Null
            }
            $json = $sbom | ConvertTo-Json -Depth 100
            $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
            [System.IO.File]::WriteAllText($OutputPath, $json, $utf8NoBom)
            $results.output_path = $OutputPath
            Write-Host "[DEP] Manual SBOM generated: $OutputPath" -ForegroundColor Green
        }
    } catch {
        $results.error = "Manual SBOM generation failed: $_"
        Write-Warning "Invoke-SBOMGenerate: $_"
    }

    return $results
}

function Build-ManualSBOM {
    param(
        [string]$ProjectPath,
        [string]$Format
    )

    $sbom = @{
        bomFormat = if ($Format -eq "spdx") { "SPDX" } else { "CycloneDX" }
        specVersion = if ($Format -eq "spdx") { "SPDX-2.3" } else { "1.4" }
        serialNumber = "urn:uuid:$([System.Guid]::NewGuid())"
        version = 1
        metadata = @{
            timestamp = (Get-Date).ToString("o")
            component = @{
                name = Split-Path -Leaf $ProjectPath
                type = "application"
            }
        }
        components = @()
    }

    $manifests = @{
        "npm" = Join-Path $ProjectPath "package.json"
        "composer" = Join-Path $ProjectPath "composer.json"
        "python" = Join-Path $ProjectPath "requirements.txt"
        "python-poetry" = Join-Path $ProjectPath "pyproject.toml"
        "python-pipenv" = Join-Path $ProjectPath "Pipfile"
        "rust" = Join-Path $ProjectPath "Cargo.toml"
        "go" = Join-Path $ProjectPath "go.mod"
        "ruby" = Join-Path $ProjectPath "Gemfile"
        "java-gradle" = Join-Path $ProjectPath "build.gradle"
        "java-maven" = Join-Path $ProjectPath "pom.xml"
    }

    foreach ($eco in $manifests.Keys) {
        $manifestPath = $manifests[$eco]
        if (-not (Test-Path -LiteralPath $manifestPath)) { continue }

        switch ($eco) {
            "npm" {
                try {
                    $pkg = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
                    if ($pkg.dependencies) {
                        foreach ($prop in $pkg.dependencies.PSObject.Properties) {
                            $sbom.components += @{
                                name = $prop.Name
                                version = $prop.Value
                                type = "library"
                                purl = "pkg:npm/$($prop.Name)@$($prop.Value)"
                            }
                        }
                    }
                    if ($pkg.devDependencies) {
                        foreach ($prop in $pkg.devDependencies.PSObject.Properties) {
                            $sbom.components += @{
                                name = $prop.Name
                                version = $prop.Value
                                type = "library"
                                scope = "development"
                                purl = "pkg:npm/$($prop.Name)@$($prop.Value)"
                            }
                        }
                    }
                } catch { }
            }
            "composer" {
                try {
                    $comp = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
                    if ($comp.require) {
                        foreach ($prop in $comp.require.PSObject.Properties) {
                            $sbom.components += @{
                                name = $prop.Name
                                version = $prop.Value
                                type = "library"
                                purl = "pkg:composer/$($prop.Name)@$($prop.Value)"
                            }
                        }
                    }
                    if ($comp."require-dev") {
                        foreach ($prop in $comp."require-dev".PSObject.Properties) {
                            $sbom.components += @{
                                name = $prop.Name
                                version = $prop.Value
                                type = "library"
                                scope = "development"
                                purl = "pkg:composer/$($prop.Name)@$($prop.Value)"
                            }
                        }
                    }
                } catch { }
            }
            "python" {
                try {
                    $lines = Get-Content -LiteralPath $manifestPath -Encoding UTF8 -ErrorAction SilentlyContinue
                    foreach ($line in $lines) {
                        $trimmed = $line.Trim()
                        if ($trimmed -match '^([a-zA-Z0-9_\-\.]+)([><=!~]+[\d\.\*,\s]+.*)?$' -and $trimmed -notmatch '^\s*#' -and $trimmed -notmatch '^\s*-') {
                            $pkgName = $Matches[1]
                            $version = if ($Matches[2]) { $Matches[2].Trim() } else { "*" }
                            $sbom.components += @{
                                name = $pkgName
                                version = $version
                                type = "library"
                                purl = "pkg:pypi/$pkgName@$version"
                            }
                        }
                    }
                } catch { }
            }
            "go" {
                try {
                    $lines = Get-Content -LiteralPath $manifestPath -Encoding UTF8 -ErrorAction SilentlyContinue
                    foreach ($line in $lines) {
                        if ($line -match '^\s*([^\s]+)\s+(v[\d\.]+[^\s]*)') {
                            $sbom.components += @{
                                name = $Matches[1]
                                version = $Matches[2]
                                type = "library"
                                purl = "pkg:golang/$($Matches[1])@$($Matches[2])"
                            }
                        }
                    }
                } catch { }
            }
        }
    }

    return $sbom
}

function Get-AvailableDepTools {
    $tools = @{
        dependency_check = (Get-Command dependency-check -ErrorAction SilentlyContinue) -ne $null
        npm = (Get-Command npm -ErrorAction SilentlyContinue) -ne $null
        pip_audit = (Get-Command pip-audit -ErrorAction SilentlyContinue) -ne $null
        composer = (Get-Command composer -ErrorAction SilentlyContinue) -ne $null
        gitleaks = (Get-Command gitleaks -ErrorAction SilentlyContinue) -ne $null
        trufflehog = (Get-Command trufflehog -ErrorAction SilentlyContinue) -ne $null
        syft = (Get-Command syft -ErrorAction SilentlyContinue) -ne $null
    }

    Write-Host "`n[DEPENDENCY TOOL AVAILABILITY]"
    foreach ($tool in $tools.Keys | Sort-Object) {
        $icon = if ($tools[$tool]) { "[INSTALLED]" } else { "[MISSING]" }
        $color = if ($tools[$tool]) { "Green" } else { "DarkGray" }
        Write-Host "  $icon $tool" -ForegroundColor $color
    }
    Write-Host ""

    return $tools
}

function Invoke-AllDepScans {
    param(
        [string]$ProjectPath,
        [string]$EngineRoot
    )

    $configPath = Join-Path $EngineRoot "..\\config\\aura.json"
    if (-not (Test-Path -LiteralPath $configPath)) {
        $configPath = Join-Path (Split-Path -Parent $EngineRoot) "config\\aura.json"
    }
    $config = if (Test-Path -LiteralPath $configPath) {
        try {
            $raw = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8
            $raw | ConvertFrom-Json
        } catch { $null }
    } else { $null }

    $depConfig = $null
    if ($config -and $config.sast -and $config.sast.dependency_scanning) {
        $depConfig = $config.sast.dependency_scanning
    }

    $allResults = @{
        timestamp = (Get-Date).ToString("o")
        project_path = $ProjectPath
        tools_available = @{}
        scans = @{}
        total_findings = 0
    }

    $depDir = Join-Path $EngineRoot "dep-scans"
    if (-not (Test-Path -LiteralPath $depDir)) {
        New-Item -ItemType Directory -Force -Path $depDir | Out-Null
    }

    $tools = Get-AvailableDepTools
    $allResults.tools_available = $tools

    if ($tools.npm) {
        $npmEnabled = if ($depConfig) { $depConfig.npm_audit } else { $true }
        if ($npmEnabled) {
            $npmOutput = Join-Path $depDir "npm-audit-results.json"
            $npmResult = Invoke-NPMAudit -ProjectPath $ProjectPath -OutputPath $npmOutput
            $allResults.scans["npm_audit"] = @{
                findings_count = $npmResult.findings.Count
                exit_code = $npmResult.exit_code
                output_file = $npmOutput
            }
            $allResults.total_findings += $npmResult.findings.Count
        }
    }

    if ($tools.pip_audit) {
        $pipEnabled = if ($depConfig) { $depConfig.pip_audit } else { $true }
        if ($pipEnabled) {
            $pipOutput = Join-Path $depDir "pip-audit-results.json"
            $pipResult = Invoke-PipAudit -ProjectPath $ProjectPath -OutputPath $pipOutput
            $allResults.scans["pip_audit"] = @{
                findings_count = $pipResult.findings.Count
                exit_code = $pipResult.exit_code
                output_file = $pipOutput
            }
            $allResults.total_findings += $pipResult.findings.Count
        }
    }

    if ($tools.composer) {
        $compEnabled = if ($depConfig) { $depConfig.composer_audit } else { $true }
        if ($compEnabled) {
            $compOutput = Join-Path $depDir "composer-audit-results.json"
            $compResult = Invoke-ComposerAudit -ProjectPath $ProjectPath -OutputPath $compOutput
            $allResults.scans["composer_audit"] = @{
                findings_count = $compResult.findings.Count
                exit_code = $compResult.exit_code
                output_file = $compOutput
            }
            $allResults.total_findings += $compResult.findings.Count
        }
    }

    if ($tools.gitleaks) {
        $gleaksEnabled = if ($depConfig -and $depConfig.gitleaks) { $depConfig.gitleaks.enabled } else { $true }
        if ($gleaksEnabled) {
            $scanHistory = if ($depConfig -and $depConfig.gitleaks) { $depConfig.gitleaks.scan_history } else { $false }
            $gleaksOutput = Join-Path $depDir "gitleaks-results.json"
            $gleaksResult = Invoke-GitleaksScan -ProjectPath $ProjectPath -OutputPath $gleaksOutput -ScanHistory:$scanHistory
            $allResults.scans["gitleaks"] = @{
                findings_count = $gleaksResult.findings.Count
                exit_code = $gleaksResult.exit_code
                output_file = $gleaksOutput
            }
            $allResults.total_findings += $gleaksResult.findings.Count
        }
    }

    if ($tools.trufflehog) {
        $thogEnabled = if ($depConfig -and $depConfig.trufflehog) { $depConfig.trufflehog.enabled } else { $false }
        if ($thogEnabled) {
            $thogOutput = Join-Path $depDir "trufflehog-results.json"
            $thogResult = Invoke-TruffleHogScan -ProjectPath $ProjectPath -OutputPath $thogOutput
            $allResults.scans["trufflehog"] = @{
                findings_count = $thogResult.findings.Count
                exit_code = $thogResult.exit_code
                output_file = $thogOutput
            }
            $allResults.total_findings += $thogResult.findings.Count
        }
    }

    $sbomEnabled = $true
    if ($config -and $config.sast -and $config.sast.sbom) {
        $sbomEnabled = $config.sast.sbom.enabled
    }
    if ($sbomEnabled) {
        $sbomFormat = if ($config -and $config.sast -and $config.sast.sbom) { $config.sast.sbom.format } else { "cyclonedx" }
        $sbomOutputPath = Join-Path $depDir "sbom.$sbomFormat.json"
        $sbomResult = Invoke-SBOMGenerate -ProjectPath $ProjectPath -OutputPath $sbomOutputPath -Format $sbomFormat
        $allResults.scans["sbom"] = @{
            tool = if ($sbomResult.available) { "syft" } else { "manual" }
            format = $sbomFormat
            output_file = $sbomOutputPath
            findings_count = 0
            exit_code = if (@($sbomResult.PSObject.Properties | Where-Object { $_.Name -eq 'exit_code' }).Count -gt 0) { $sbomResult.exit_code } else { 0 }
        }
    }

    if ($tools.dependency_check) {
        $dcEnabled = if ($depConfig) { $depConfig.owasp_dependency_check } else { $false }
        if ($dcEnabled) {
            $dcOutput = Join-Path $depDir "dependency-check-results.json"
            $dcResult = Invoke-DependencyCheck -ProjectPath $ProjectPath -OutputPath $dcOutput
            $allResults.scans["dependency_check"] = @{
                findings_count = $dcResult.findings.Count
                exit_code = $dcResult.exit_code
                output_file = $dcOutput
            }
            $allResults.total_findings += $dcResult.findings.Count
        }
    }

    $summaryOutput = Join-Path $depDir "dep-summary.json"
    $json = $allResults | ConvertTo-Json -Depth 100
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($summaryOutput, $json, $utf8NoBom)

    $reportPath = Join-Path $EngineRoot "reports\\dependency-scan-report.md"
    $report = Generate-DepReport -AllResults $allResults
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($reportPath, $report, $utf8NoBom)

    Write-Host "[DEP] Scan summary: $($allResults.total_findings) total finding(s) across $($allResults.scans.Count) tool(s)" -ForegroundColor Cyan
    Write-Host "[DEP] Summary: $summaryOutput" -ForegroundColor Green
    Write-Host "[DEP] Report: $reportPath" -ForegroundColor Green

    return $allResults
}

function Convert-VulnSeverity {
    param(
        [double]$CvssScore = 0.0,
        [string]$Severity = ""
    )

    if ($CvssScore -gt 0) {
        if ($CvssScore -ge 9.0) { return "P0" }
        if ($CvssScore -ge 7.0) { return "P1" }
        if ($CvssScore -ge 4.0) { return "P2" }
        if ($CvssScore -ge 0.1) { return "P4" }
        return "P5"
    }

    if (-not [string]::IsNullOrWhiteSpace($Severity)) {
        $normalized = $Severity.ToUpperInvariant()
        $map = @{
            "CRITICAL" = "P0"
            "HIGH" = "P1"
            "MODERATE" = "P2"
            "MEDIUM" = "P2"
            "LOW" = "P4"
            "INFO" = "P5"
            "NONE" = "P5"
        }
        if ($map.ContainsKey($normalized)) { return $map[$normalized] }
    }

    return "P4"
}

function Generate-DepReport {
    param(
        [hashtable]$AllResults
    )

    $sb = New-Object System.Text.StringBuilder
    [void]$sb.AppendLine("# Dependency & Secret Scan Report")
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
            $findingsStr = if ($s.PSObject.Properties.Name -contains 'format') {
                "SBOM ($($s.format))"
            } else {
                "$($s.findings_count)"
            }
            [void]$sb.AppendLine("| $scan | $findingsStr | $($s.exit_code) | $outputFile |")
        }
    }

    [void]$sb.AppendLine("")
    [void]$sb.AppendLine("**Total Findings:** $($AllResults.total_findings)")

    return $sb.ToString()
}

function Save-DepRawOutput {
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

Export-ModuleMember -Function Invoke-DependencyCheck, Invoke-NPMAudit,
    Invoke-ComposerAudit, Invoke-PipAudit, Invoke-GitleaksScan,
    Invoke-TruffleHogScan, Invoke-SBOMGenerate, Get-AvailableDepTools,
    Invoke-AllDepScans, Convert-VulnSeverity, Generate-DepReport