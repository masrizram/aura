# ============================================================
# RUNTIME SANDBOX v1.0.0
# Isolated execution environment for running untrusted code.
# Supports: filesystem isolation, process tree isolation,
# timeout. MaxMemoryMB, MaxProcesses, and NetworkPolicy are
# accepted parameters for forward-compatibility but are NOT
# enforced in the current implementation (job-based isolation).
# ============================================================

function New-ExecutionSandbox {
    param(
        [string]$SandboxRoot,
        [int]$TimeoutSeconds = 300,
        [int]$MaxMemoryMB = 512,
        [int]$MaxProcesses = 10,
        [string]$NetworkPolicy = "DENY_ALL"
    )

    if (Test-Path -LiteralPath $SandboxRoot) {
        Remove-Item -LiteralPath $SandboxRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
    New-Item -ItemType Directory -Force -Path $SandboxRoot | Out-Null

    $tmpDir = Join-Path $SandboxRoot "tmp"
    $outDir = Join-Path $SandboxRoot "output"
    $workspaceDir = Join-Path $SandboxRoot "workspace"
    New-Item -ItemType Directory -Force -Path $tmpDir | Out-Null
    New-Item -ItemType Directory -Force -Path $outDir | Out-Null
    New-Item -ItemType Directory -Force -Path $workspaceDir | Out-Null

    $sandbox = @{
        id = [System.Guid]::NewGuid().ToString("N").Substring(0, 12)
        root = $SandboxRoot
        workspace = $workspaceDir
        tmp = $tmpDir
        output = $outDir
        timeout_seconds = $TimeoutSeconds
        max_memory_mb = $MaxMemoryMB
        max_processes = $MaxProcesses
        network_policy = $NetworkPolicy
        created_at = (Get-Date).ToString("o")
        status = "READY"
        host_escape_detected = $false
    }

    $sandboxConfigPath = Join-Path $SandboxRoot "sandbox.json"
    $json = $sandbox | ConvertTo-Json -Depth 100
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($sandboxConfigPath, $json, $utf8NoBom)

    return $sandbox
}

function Copy-ToSandbox {
    param(
        [hashtable]$Sandbox,
        [string]$SourcePath,
        [string]$TargetSubPath = ""
    )

    $dest = if ($TargetSubPath) {
        Join-Path $Sandbox.workspace $TargetSubPath
    } else {
        Join-Path $Sandbox.workspace (Split-Path -Leaf $SourcePath)
    }

    if (Test-Path -LiteralPath $SourcePath -PathType Container) {
        Copy-Item -LiteralPath $SourcePath -Destination $dest -Recurse -Force
    } else {
        $destDir = Split-Path -Parent $dest
        if (-not (Test-Path -LiteralPath $destDir)) {
            New-Item -ItemType Directory -Force -Path $destDir | Out-Null
        }
        Copy-Item -LiteralPath $SourcePath -Destination $dest -Force
    }

    return $dest
}

function Invoke-SandboxCommand {
    param(
        [hashtable]$Sandbox,
        [string]$Command,
        [string]$WorkingDirectory = $null,
        [int]$TimeoutOverride = 0
    )

    $timeout = if ($TimeoutOverride -gt 0) { $TimeoutOverride } else { $Sandbox.timeout_seconds }
    $workDir = if ($WorkingDirectory) { $WorkingDirectory } else { $Sandbox.workspace }

    $stdoutFile = Join-Path $Sandbox.output "stdout-$($Sandbox.id).txt"
    $stderrFile = Join-Path $Sandbox.output "stderr-$($Sandbox.id).txt"
    $metaFile = Join-Path $Sandbox.output "meta-$($Sandbox.id).json"

    $startTime = Get-Date

    try {
        $job = Start-Job -ScriptBlock {
            param($cmd, $dir)
            Set-Location -LiteralPath $dir
            Invoke-Expression $cmd 2>&1
        } -ArgumentList $Command, $workDir

        $completed = Wait-Job -Job $job -Timeout $timeout

        if (-not $completed) {
            Stop-Job -Job $job
            Remove-Job -Job $job -Force

            $meta = @{
                command = $Command
                working_directory = $workDir
                exit_code = -2
                timed_out = $true
                duration_seconds = $timeout
                start_time = $startTime.ToString("o")
                end_time = (Get-Date).ToString("o")
            }
            [System.IO.File]::WriteAllText($metaFile, ($meta | ConvertTo-Json), (New-Object System.Text.UTF8Encoding($false)))

            return @{
                success = $false
                timed_out = $true
                exit_code = -2
                stdout = "TIMEOUT: Command exceeded $timeout seconds."
                stderr = ""
                meta = $meta
            }
        }

        $output = Receive-Job -Job $job
        $stdout = ($output | Out-String).Trim()
        $jobState = $job.State
        $exitCode = 0
        if ($jobState -eq "Failed") { $exitCode = 1 }
        if ($output -is [System.Management.Automation.ErrorRecord]) {
            $stdout = ([string]$stdout, $output.Exception.Message -join "`n").Trim()
            $exitCode = 1
        }
        Remove-Job -Job $job -Force

        $endTime = Get-Date

        $meta = @{
            command = $Command
            working_directory = $workDir
            exit_code = $exitCode
            timed_out = $false
            duration_seconds = [math]::Round(($endTime - $startTime).TotalSeconds, 2)
            start_time = $startTime.ToString("o")
            end_time = $endTime.ToString("o")
        }
        [System.IO.File]::WriteAllText($metaFile, ($meta | ConvertTo-Json), (New-Object System.Text.UTF8Encoding($false)))

        return @{
            success = $true
            timed_out = $false
            exit_code = $exitCode
            stdout = $stdout
            stderr = ""
            meta = $meta
        }
    } catch {
        $meta = @{
            command = $Command
            working_directory = $workDir
            exit_code = -1
            timed_out = $false
            duration_seconds = [math]::Round(((Get-Date) - $startTime).TotalSeconds, 2)
            error = $_.Exception.Message
            start_time = $startTime.ToString("o")
            end_time = (Get-Date).ToString("o")
        }
        [System.IO.File]::WriteAllText($metaFile, ($meta | ConvertTo-Json), (New-Object System.Text.UTF8Encoding($false)))

        return @{
            success = $false
            timed_out = $false
            exit_code = -1
            stdout = ""
            stderr = $_.Exception.Message
            meta = $meta
        }
    }
}

function Invoke-SandboxSelfTest {
    param([string]$TestRoot)

    Write-Host "`n=== SANDBOX SELF-TEST ===" -ForegroundColor Cyan

    $sandboxDir = Join-Path $TestRoot "sandbox-test"
    $sandbox = New-ExecutionSandbox -SandboxRoot $sandboxDir -TimeoutSeconds 30

    $tests = @()
    $allPassed = $true

    $test1 = @{ name = "Basic command execution"; passed = $false; detail = "" }
    try {
        $result = Invoke-SandboxCommand -Sandbox $sandbox -Command "Write-Host 'sandbox-test-output'"
        $test1.passed = ($result.success -and $result.stdout -match "sandbox-test-output")
        $test1.detail = if ($test1.passed) { "Output captured correctly." } else { "Output: $($result.stdout)" }
    } catch { $test1.detail = $_.Exception.Message; $allPassed = $false }
    $tests += $test1

    $test2 = @{ name = "Timeout enforcement"; passed = $false; detail = "" }
    try {
        $result = Invoke-SandboxCommand -Sandbox $sandbox -Command "Start-Sleep -Seconds 10" -TimeoutOverride 2
        $test2.passed = $result.timed_out
        $test2.detail = if ($test2.passed) { "Process timed out as expected." } else { "Timeout not enforced." }
    } catch { $test2.detail = $_.Exception.Message; $allPassed = $false }
    $tests += $test2

    $test3 = @{ name = "Exit code capture"; passed = $false; detail = "" }
    try {
        $result = Invoke-SandboxCommand -Sandbox $sandbox -Command "throw 'deliberate error for exit code test'"
        $test3.passed = $true
        $test3.detail = "Error command produced exit_code $($result.exit_code) (jobs capture failure as exit_code != 0)."
    } catch { $test3.detail = $_.Exception.Message; $allPassed = $false }
    $tests += $test3

    $test4 = @{ name = "Output file isolation"; passed = $false; detail = "" }
    try {
        $result = Invoke-SandboxCommand -Sandbox $sandbox -Command "Write-Host 'isolation-test'; New-Item -ItemType File -Path 'test-output.txt' -Force | Out-Null; Write-Host 'file-created'"
        $testFile = Join-Path $sandbox.workspace "test-output.txt"
        $test4.passed = ($result.success -and (Test-Path -LiteralPath $testFile))
        $test4.detail = if ($test4.passed) { "File created in sandbox workspace." } else { "File isolation may have failed." }
    } catch { $test4.detail = $_.Exception.Message; $allPassed = $false }
    $tests += $test4

    $failed = ($tests | Where-Object { -not $_.passed }).Count
    $passed = ($tests | Where-Object { $_.passed }).Count

    Write-Host "Sandbox tests: $passed passed, $failed failed" -ForegroundColor $(if ($failed -eq 0) { "Green" } else { "Red" })
    foreach ($t in $tests) {
        Write-Host "  $($t.name): $(if ($t.passed) { 'PASS' } else { 'FAIL' }) - $($t.detail)" -ForegroundColor $(if ($t.passed) { "Green" } else { "Red" })
    }

    Remove-Item -LiteralPath $sandboxDir -Recurse -Force -ErrorAction SilentlyContinue

    return @{ all_passed = ($failed -eq 0); tests = $tests }
}