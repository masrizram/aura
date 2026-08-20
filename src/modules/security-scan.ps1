# ============================================================
# SECURITY VALIDATION ENGINE v1.0.0
# Integrates security scanning: grep-based SAST, secret
# detection, path traversal, injection pattern detection.
# ============================================================

function Invoke-SecurityScan {
    param(
        [string]$ProjectPath,
        [string]$OutputPath,
        [string[]]$ExcludePatterns = @(".git",".aura","node_modules","vendor","__pycache__")
    )

    $findings = @()

    # Build exclusion regex for file scanning
    $excludeRegex = ($ExcludePatterns | ForEach-Object { [regex]::Escape($_) }) -join '|'

    $allFiles = Get-ChildItem -LiteralPath $ProjectPath -File -Recurse -ErrorAction SilentlyContinue | Where-Object {
        $rel = $_.FullName.Substring($ProjectPath.Length).TrimStart("\","/")
        -not ($rel -match $excludeRegex)
    }

    $findings += Scan-Secrets -Files $allFiles -ProjectPath $ProjectPath
    $findings += Scan-HardcodedCredentials -Files $allFiles -ProjectPath $ProjectPath
    $findings += Scan-InjectionPatterns -Files $allFiles -ProjectPath $ProjectPath
    $findings += Scan-WeakCrypto -Files $allFiles -ProjectPath $ProjectPath
    $findings += Scan-UnsafeSubprocess -Files $allFiles -ProjectPath $ProjectPath
    $findings += Scan-PathTraversal -Files $allFiles -ProjectPath $ProjectPath
    $findings += Scan-AuthBypass -Files $allFiles -ProjectPath $ProjectPath
    $findings += Scan-UnsafeDeserialization -Files $allFiles -ProjectPath $ProjectPath

    $result = @{
        scan_type = "SECURITY_AUDIT"
        timestamp = (Get-Date).ToString("o")
        project_path = $ProjectPath
        files_scanned = $allFiles.Count
        total_findings = $findings.Count
        by_severity = @{}
        findings = $findings
    }

    if ($OutputPath) {
        $parent = Split-Path -Parent $OutputPath
        if (-not (Test-Path -LiteralPath $parent)) { New-Item -ItemType Directory -Force -Path $parent | Out-Null }
        $json = $result | ConvertTo-Json -Depth 100
        $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
        [System.IO.File]::WriteAllText($OutputPath, $json, $utf8NoBom)
    }

    return $result
}

function Scan-Secrets {
    param([array]$Files, [string]$ProjectPath)
    $results = @()

    $secretPatterns = @{
        "API_KEY" = '(?i)(api[_-]?key|apikey|api_secret)\s*[:=]\s*[''"][\w\-\.]{10,}[''"]'
        "PASSWORD" = '(?i)(password|passwd|pwd)\s*[:=]\s*[''"][^''"]{4,}[''"]'
        "TOKEN" = '(?i)(token|secret|jwt)\s*[:=]\s*[''"][\w\-\.]{10,}[''"]'
        "PRIVATE_KEY" = '-----BEGIN (RSA|EC|DSA|OPENSSH) PRIVATE KEY-----'
        "CONNECTION_STRING" = '(?i)(connection[_-]?string|connstr|dsn)\s*[:=]\s*[''"]\S+[''"]'
        "AWS_KEY" = '(?i)AKIA[0-9A-Z]{16}'
        "GITHUB_TOKEN" = '(?i)gh[pousr]_[A-Za-z0-9_]{36,}'
    }

    foreach ($file in $Files) {
        $relPath = $file.FullName.Substring($ProjectPath.Length).TrimStart("\","/")
        try {
            $content = Get-Content -LiteralPath $file.FullName -Raw -Encoding UTF8 -ErrorAction SilentlyContinue
            if (-not $content) { continue }
            foreach ($patternName in $secretPatterns.Keys) {
                $matches = [regex]::Matches($content, $secretPatterns[$patternName])
                foreach ($match in $matches) {
                    $line = ($content.Substring(0, $match.Index) -split "`n").Count
                    $maskedValue = $match.Value -replace '([:=])\s*[''"](.+?)[''"]', '$1 "***"'
                    $results += @{
                        category = "SECRET_EXPOSURE"
                        severity = "P0"
                        file = $relPath
                        line = $line
                        match = $maskedValue
                        pattern = $patternName
                        risk_score = 625
                        confidence = "HIGH"
                        description = "Potential secret exposure ($patternName) at $relPath`:$line"
                    }
                }
            }
        } catch { }
    }
    return $results
}

function Scan-HardcodedCredentials {
    param([array]$Files, [string]$ProjectPath)
    $results = @()

    $credsPatterns = @(
        '(?i)(username|user)\s*=\s*[''"]admin[''"]',
        '(?i)(username|user)\s*=\s*[''"]root[''"]',
        'default_password\s*=\s*',
        '(?i)credential\s*=\s*\{'
    )

    foreach ($file in $Files) {
        $relPath = $file.FullName.Substring($ProjectPath.Length).TrimStart("\","/")
        try {
            $content = Get-Content -LiteralPath $file.FullName -Raw -Encoding UTF8 -ErrorAction SilentlyContinue
            if (-not $content) { continue }
            foreach ($pattern in $credsPatterns) {
                $matches = [regex]::Matches($content, $pattern)
                foreach ($match in $matches) {
                    $line = ($content.Substring(0, $match.Index) -split "`n").Count
                    $results += @{
                        category = "HARDCODED_CREDENTIALS"
                        severity = "P1"
                        file = $relPath
                        line = $line
                        match = $match.Value.Substring(0, [math]::Min(80, $match.Value.Length))
                        risk_score = 405
                        confidence = "HIGH"
                        description = "Hardcoded credentials at $relPath`:$line"
                    }
                }
            }
        } catch { }
    }
    return $results
}

function Scan-InjectionPatterns {
    param([array]$Files, [string]$ProjectPath)
    $results = @()

    $injectionPatterns = @{
        "SQL_INJECTION" = '(?i)(execute\s*\(\s*[''"].*?\$\w+|sql\s*=\s*[''"].*?\$\w+|query\s*=\s*[''"].*?\$\w+|Invoke-SqlCmd.*?\$\w+)'
        "COMMAND_INJECTION" = '(?i)(Invoke-Expression\s+\$|iex\s+\$|Start-Process.*?\$\w+|exec\s*\(\s*\$)'
        "XSS" = '(?i)(innerHTML\s*=|document\.write\s*\(|dangerouslySetInnerHTML|v-html=|unescape\s*\()'
        "SSRF" = '(?i)(Invoke-WebRequest.*?\$|curl_exec.*?\$|file_get_contents.*?\$)'
    }

    foreach ($file in $Files) {
        $relPath = $file.FullName.Substring($ProjectPath.Length).TrimStart("\","/")
        try {
            $content = Get-Content -LiteralPath $file.FullName -Raw -Encoding UTF8 -ErrorAction SilentlyContinue
            if (-not $content) { continue }
            foreach ($category in $injectionPatterns.Keys) {
                $matches = [regex]::Matches($content, $injectionPatterns[$category])
                foreach ($match in $matches) {
                    $line = ($content.Substring(0, $match.Index) -split "`n").Count
                    $results += @{
                        category = $category
                        severity = "P0"
                        file = $relPath
                        line = $line
                        match = $match.Value.Substring(0, [math]::Min(80, $match.Value.Length))
                        risk_score = 625
                        confidence = "HIGH"
                        description = "Potential $category at $relPath`:$line"
                    }
                }
            }
        } catch { }
    }
    return $results
}

function Scan-WeakCrypto {
    param([array]$Files, [string]$ProjectPath)
    $results = @()

    $weakPatterns = @{
        "MD5" = '\b(MD5)\b'
        "SHA1" = '\b(SHA1)\b'
        "DES" = '\b(DES)\b'
        "RC4" = '\b(RC4)\b'
        "WEAK_RANDOM" = '\b(Math\.random|rand\s*\()\b'
    }

    foreach ($file in $Files) {
        $relPath = $file.FullName.Substring($ProjectPath.Length).TrimStart("\","/")
        try {
            $content = Get-Content -LiteralPath $file.FullName -Raw -Encoding UTF8 -ErrorAction SilentlyContinue
            if (-not $content) { continue }
            if ($relPath -match '\.(md|txt)$') { continue }
            foreach ($algo in $weakPatterns.Keys) {
                $matches = [regex]::Matches($content, $weakPatterns[$algo])
                foreach ($match in $matches) {
                    $line = ($content.Substring(0, $match.Index) -split "`n").Count
                    $results += @{
                        category = "WEAK_CRYPTO"
                        severity = "P2"
                        file = $relPath
                        line = $line
                        match = $algo
                        risk_score = 216
                        confidence = "MEDIUM"
                        description = "Weak crypto ($algo) at $relPath`:$line"
                    }
                }
            }
        } catch { }
    }
    return $results
}

function Scan-UnsafeSubprocess {
    param([array]$Files, [string]$ProjectPath)
    $results = @()

    $patterns = @(
        '(?i)(shell_exec|exec\s*\(|system\s*\(|passthru\s*\()',
        '(?i)(os\.system\s*\(|subprocess\.call\s*\(\s*shell\s*=\s*True)',
        'Invoke-Expression\s+\"'
    )

    foreach ($file in $Files) {
        $relPath = $file.FullName.Substring($ProjectPath.Length).TrimStart("\","/")
        try {
            $content = Get-Content -LiteralPath $file.FullName -Raw -Encoding UTF8 -ErrorAction SilentlyContinue
            if (-not $content) { continue }
            foreach ($pattern in $patterns) {
                $matches = [regex]::Matches($content, $pattern)
                foreach ($match in $matches) {
                    $line = ($content.Substring(0, $match.Index) -split "`n").Count
                    $results += @{
                        category = "UNSAFE_SUBPROCESS"
                        severity = "P1"
                        file = $relPath
                        line = $line
                        match = $match.Value.Substring(0, [math]::Min(80, $match.Value.Length))
                        risk_score = 405
                        confidence = "HIGH"
                        description = "Unsafe subprocess execution at $relPath`:$line"
                    }
                }
            }
        } catch { }
    }
    return $results
}

function Scan-PathTraversal {
    param([array]$Files, [string]$ProjectPath)
    $results = @()

    $patterns = @(
        '(?i)(\.\.\/|\.\.\\|path\.join\(.*?\$\w+|os\.path\.join\(.*?\$\w+)',
        '(?i)(file_get_contents\(\$|readfile\(\$|fopen\(\$)',
        'Get-Content\s+\"\$'
    )

    foreach ($file in $Files) {
        $relPath = $file.FullName.Substring($ProjectPath.Length).TrimStart("\","/")
        try {
            $content = Get-Content -LiteralPath $file.FullName -Raw -Encoding UTF8 -ErrorAction SilentlyContinue
            if (-not $content) { continue }
            foreach ($pattern in $patterns) {
                $matches = [regex]::Matches($content, $pattern)
                foreach ($match in $matches) {
                    $line = ($content.Substring(0, $match.Index) -split "`n").Count
                    $results += @{
                        category = "PATH_TRAVERSAL"
                        severity = "P1"
                        file = $relPath
                        line = $line
                        match = $match.Value.Substring(0, [math]::Min(80, $match.Value.Length))
                        risk_score = 405
                        confidence = "HIGH"
                        description = "Potential path traversal at $relPath`:$line"
                    }
                }
            }
        } catch { }
    }
    return $results
}

function Scan-AuthBypass {
    param([array]$Files, [string]$ProjectPath)
    $results = @()

    $patterns = @(
        '(?i)(auth\s*=\s*false|authenticated\s*=\s*false|skip.*auth|bypass.*auth)',
        '(?i)(if\s*\(\s*true\s*\).*authenticate|return\s+true.*password)'
    )

    foreach ($file in $Files) {
        $relPath = $file.FullName.Substring($ProjectPath.Length).TrimStart("\","/")
        try {
            $content = Get-Content -LiteralPath $file.FullName -Raw -Encoding UTF8 -ErrorAction SilentlyContinue
            if (-not $content) { continue }
            foreach ($pattern in $patterns) {
                $matches = [regex]::Matches($content, $pattern)
                foreach ($match in $matches) {
                    $line = ($content.Substring(0, $match.Index) -split "`n").Count
                    $results += @{
                        category = "AUTH_BYPASS"
                        severity = "P0"
                        file = $relPath
                        line = $line
                        match = $match.Value.Substring(0, [math]::Min(80, $match.Value.Length))
                        risk_score = 625
                        confidence = "HIGH"
                        description = "Potential authentication bypass at $relPath`:$line"
                    }
                }
            }
        } catch { }
    }
    return $results
}

function Scan-UnsafeDeserialization {
    param([array]$Files, [string]$ProjectPath)
    $results = @()

    $patterns = @(
        '(?i)(unserialize\s*\(|pickle\.loads\s*\(|yaml\.load\s*\(|json\.loads\s*\()',
        '(?i)(Invoke-Expression.*(ConvertFrom|Deserialize|Invoke-))|(?<!ConvertFrom-Json\s+)(?i)(ConvertFrom-Json)'
    )

    foreach ($file in $Files) {
        $relPath = $file.FullName.Substring($ProjectPath.Length).TrimStart("\","/")
        $ext = [System.IO.Path]::GetExtension($relPath).ToLowerInvariant()
        if ($relPath -match '\.(md|txt|json|yml|yaml|toml|cfg)$') { continue }
        if ($relPath -match '\.ps1$') { continue }
        try {
            $content = Get-Content -LiteralPath $file.FullName -Raw -Encoding UTF8 -ErrorAction SilentlyContinue
            if (-not $content) { continue }
            foreach ($pattern in $patterns) {
                $matches = [regex]::Matches($content, $pattern)
                foreach ($match in $matches) {
                    $line = ($content.Substring(0, $match.Index) -split "`n").Count
                    $results += @{
                        category = "UNSAFE_DESERIALIZATION"
                        severity = "P1"
                        file = $relPath
                        line = $line
                        match = $match.Value.Substring(0, [math]::Min(80, $match.Value.Length))
                        risk_score = 405
                        confidence = "MEDIUM"
                        description = "Potential unsafe deserialization at $relPath`:$line"
                    }
                }
            }
        } catch { }
    }
    return $results
}

function Format-SecurityReport {
    param([PSCustomObject]$ScanResult)

    $sb = New-Object System.Text.StringBuilder
    [void]$sb.AppendLine("")
    [void]$sb.AppendLine("=== SECURITY SCAN REPORT ===")
    [void]$sb.AppendLine("Files scanned: $($ScanResult.files_scanned)")
    [void]$sb.AppendLine("Total findings: $($ScanResult.total_findings)")
    [void]$sb.AppendLine("")

    if ($ScanResult.findings.Count -gt 0) {
        $bySev = $ScanResult.findings | Group-Object -Property severity
        [void]$sb.AppendLine("## By Severity")
        foreach ($g in $bySev) { [void]$sb.AppendLine("- $($g.Name): $($g.Count)") }
        [void]$sb.AppendLine("")

        $p0s = @($ScanResult.findings | Where-Object { $_.severity -eq "P0" })
        if ($p0s.Count -gt 0) {
            [void]$sb.AppendLine("## P0 Findings")
            foreach ($f in $p0s) {
                [void]$sb.AppendLine("- **[$($f.category)]** $($f.file):$($f.line) - $($f.description)")
            }
        }
    } else {
        [void]$sb.AppendLine("No security findings detected.")
    }

    return $sb.ToString()
}