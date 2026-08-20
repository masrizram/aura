# ============================================================
# MODULE: evidence-signing.ps1
# Purpose: Cryptographic evidence signing for PowerShell orchestrator
# Classification: OPTIONAL
# ============================================================

$Script:_EvidenceSigningEngineInitialized = $false
$Script:_EvidenceKeyPath = $null
$Script:_EvidenceChainFile = $null

function Initialize-EvidenceSigning {
    param(
        [string]$EngineRoot,
        [string]$KeyPath
    )
    $Script:_EvidenceSigningEngineInitialized = $true
    if ($KeyPath) {
        $Script:_EvidenceKeyPath = $KeyPath
    } else {
        $keysDir = Join-Path $EngineRoot "keys"
        if (-not (Test-Path -LiteralPath $keysDir)) {
            New-Item -ItemType Directory -Force -Path $keysDir | Out-Null
        }
        $Script:_EvidenceKeyPath = Join-Path $keysDir "evidence-key.pem"
    }
    $Script:_EvidenceChainFile = Join-Path $EngineRoot "state\evidence-chain.json"
    return $Script:_EvidenceKeyPath
}

function New-EvidenceKeypair {
    param(
        [string]$KeyPath
    )
    if (-not $KeyPath) { $KeyPath = $Script:_EvidenceKeyPath }
    if (-not $KeyPath) {
        Write-Error "New-EvidenceKeypair: No key path specified."
        return $null
    }

    $keysDir = Split-Path -Parent $KeyPath
    if (-not (Test-Path -LiteralPath $keysDir)) {
        New-Item -ItemType Directory -Force -Path $keysDir | Out-Null
    }

    $engineRoot = Resolve-Path "$PSScriptRoot\..\.." -ErrorAction SilentlyContinue
    if (-not $engineRoot) { $engineRoot = (Get-Location).Path }
    $engineRootEscaped = $engineRoot -replace "'", "''"
    $keyPathEscaped = $KeyPath -replace "'", "''"

    $pythonScript = @"
import sys, os
sys.path.insert(0, r'${engineRootEscaped}')
from src.evidence.signing import EvidenceSigner
engine_root = sys.argv[1]
key_path = sys.argv[2]
signer = EvidenceSigner(engine_root, key_path)
pub_key, priv_path = signer.generate_keypair()
print(pub_key)
print(priv_path)
"@

    $tempScript = Join-Path ([System.IO.Path]::GetTempPath()) "aura-gen-keypair-$([System.Guid]::NewGuid().ToString('N').Substring(0,8)).py"

    try {
        [System.IO.File]::WriteAllText($tempScript, $pythonScript, [System.Text.Encoding]::UTF8)
        $output = & python $tempScript $engineRoot $KeyPath 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Error "New-EvidenceKeypair: Python generation failed: $output"
            return $null
        }
        $lines = $output -split "`n" | ForEach-Object { $_.Trim() } | Where-Object { $_ }
        $pubKey = $lines[0]
        $privPath = $lines[1]
        Write-Host "[EVIDENCE-SIGNING] Keypair generated. Public: $($pubKey.Substring(0, [Math]::Min(24, $pubKey.Length))...)" -ForegroundColor Green
        Write-Host "[EVIDENCE-SIGNING] Private key: $privPath" -ForegroundColor Green
        return @{
            public_key = $pubKey
            private_key_path = $privPath
        }
    } catch {
        Write-Error "New-EvidenceKeypair: Failed: $_"
        return $null
    } finally {
        if (Test-Path -LiteralPath $tempScript) {
            Remove-Item -LiteralPath $tempScript -Force -ErrorAction SilentlyContinue
        }
    }
}

function Sign-EvidenceEntry {
    param(
        [string]$EngineRoot,
        [PSCustomObject]$Evidence,
        [string]$EvidenceId
    )
    if (-not $Evidence) {
        Write-Warning "Sign-EvidenceEntry: No evidence provided."
        return $null
    }
    if (-not $EvidenceId) {
        $evidenceJson = $Evidence | ConvertTo-Json -Depth 50 -Compress
        $sha = [System.Security.Cryptography.SHA256]::Create()
        $hashBytes = $sha.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($evidenceJson))
        $EvidenceId = "ev_" + [BitConverter]::ToString($hashBytes).Replace("-", "").Substring(0, 12)
    }

    $tempEvidenceFile = Join-Path ([System.IO.Path]::GetTempPath()) "aura-evidence-$([System.Guid]::NewGuid().ToString('N').Substring(0,8)).json"
    $tempOutputFile = Join-Path ([System.IO.Path]::GetTempPath()) "aura-signed-$([System.Guid]::NewGuid().ToString('N').Substring(0,8)).json"

    try {
        $evidenceJson = $Evidence | ConvertTo-Json -Depth 50 -Compress
        $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
        [System.IO.File]::WriteAllText($tempEvidenceFile, $evidenceJson, $utf8NoBom)

        $engineRootPath = Resolve-Path $EngineRoot -ErrorAction SilentlyContinue
        if (-not $engineRootPath) { $engineRootPath = $EngineRoot }

        $pythonScript = @'
import sys, os, json
from src.evidence.signing import EvidenceSigner
engine_root = sys.argv[1]
sys.path.insert(0, engine_root)
evidence_file = sys.argv[2]
evidence_id = sys.argv[3]
output_file = sys.argv[4]
key_path = os.path.join(engine_root, 'keys', 'evidence-key.pem')
signer = EvidenceSigner(engine_root, key_path)
try:
    signer._load_keys()
except Exception:
    signer.generate_keypair()
with open(evidence_file, 'r', encoding='utf-8') as f:
    evidence = json.load(f)
signed = signer.sign_evidence(evidence, evidence_id)
with open(output_file, 'w', encoding='utf-8') as f:
    json.dump(signed.to_dict(), f, indent=2)
'@

        $tempScript = Join-Path ([System.IO.Path]::GetTempPath()) "aura-sign-$([System.Guid]::NewGuid().ToString('N').Substring(0,8)).py"
        [System.IO.File]::WriteAllText($tempScript, $pythonScript, [System.Text.Encoding]::UTF8)

        $output = & python $tempScript $engineRootPath $tempEvidenceFile $EvidenceId $tempOutputFile 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Error "Sign-EvidenceEntry: Python signing failed: $output"
            return $null
        }

        $signedJson = Get-Content -LiteralPath $tempOutputFile -Raw -Encoding UTF8
        if (-not $signedJson) {
            Write-Error "Sign-EvidenceEntry: Empty signed output."
            return $null
        }

        $signed = $signedJson | ConvertFrom-Json
        Write-Host "[EVIDENCE-SIGNING] Signed evidence $EvidenceId ($($signed.content_hash.Substring(0, [Math]::Min(16, $signed.content_hash.Length))...))" -ForegroundColor Green
        return $signed
    } catch {
        Write-Error "Sign-EvidenceEntry: Exception: $_"
        return $null
    } finally {
        @($tempEvidenceFile, $tempOutputFile, $tempScript) | ForEach-Object {
            if (Test-Path -LiteralPath $_) { Remove-Item -LiteralPath $_ -Force -ErrorAction SilentlyContinue }
        }
    }
}

function Test-EvidenceChainIntegrity {
    param(
        [string]$EngineRoot
    )
    if (-not $EngineRoot) {
        Write-Warning "Test-EvidenceChainIntegrity: No EngineRoot specified."
        return @{ valid = $false; violations = @("No EngineRoot specified") }
    }

    $chainFile = Join-Path $EngineRoot "state\evidence-chain.json"
    if (-not (Test-Path -LiteralPath $chainFile)) {
        return @{ valid = $false; violations = @("Evidence chain file not found: $chainFile"); total_entries = 0 }
    }

    $pythonScript = @'
import sys, os, json
from src.evidence.signing import EvidenceSigner, TamperEvidentLog, SignedEvidence
engine_root = sys.argv[1]
sys.path.insert(0, engine_root)
signer = EvidenceSigner(engine_root)
log = TamperEvidentLog(engine_root, signer)
is_valid, details = log.verify()
result = {
    "valid": is_valid,
    "violations": details["violations"],
    "verified_entries": details["verified_entries"],
    "tampered_entries": details["tampered_entries"],
    "total_entries": details["total_entries"],
    "chain_health_score": details["chain_health_score"],
}
print(json.dumps(result))
'@

    $tempScript = Join-Path ([System.IO.Path]::GetTempPath()) "aura-chain-check-$([System.Guid]::NewGuid().ToString('N').Substring(0,8)).py"

    try {
        [System.IO.File]::WriteAllText($tempScript, $pythonScript, [System.Text.Encoding]::UTF8)
        $engineRootPath = Resolve-Path $EngineRoot -ErrorAction SilentlyContinue
        if (-not $engineRootPath) { $engineRootPath = $EngineRoot }

        $output = & python $tempScript $engineRootPath 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Error "Test-EvidenceChainIntegrity: Python verification failed: $output"
            return @{ valid = $false; violations = @("Python verification failed"); total_entries = 0 }
        }

        $result = $output | ConvertFrom-Json
        return @{
            valid = [bool]$result.valid
            violations = @($result.violations)
            verified_entries = [int]$result.verified_entries
            tampered_entries = [int]$result.tampered_entries
            total_entries = [int]$result.total_entries
            chain_health_score = [double]$result.chain_health_score
        }
    } catch {
        Write-Error "Test-EvidenceChainIntegrity: Exception: $_"
        return @{ valid = $false; violations = @("Exception: $_"); total_entries = 0 }
    } finally {
        if (Test-Path -LiteralPath $tempScript) {
            Remove-Item -LiteralPath $tempScript -Force -ErrorAction SilentlyContinue
        }
    }
}

function Export-AuditLog {
    param(
        [string]$EngineRoot,
        [string]$OutputPath,
        [string]$Format = "json"
    )
    if (-not $EngineRoot) {
        Write-Error "Export-AuditLog: No EngineRoot specified."
        return $null
    }
    if (-not $OutputPath) {
        $OutputPath = Join-Path $EngineRoot "reports\audit-log-$(Get-Date -Format 'yyyyMMdd_HHmmss').$Format"
    }

    $chainFile = Join-Path $EngineRoot "state\evidence-chain.json"
    if (-not (Test-Path -LiteralPath $chainFile)) {
        Write-Warning "Export-AuditLog: No evidence chain file found at $chainFile. Nothing to export."
        return $null
    }

    $parent = Split-Path -Parent $OutputPath
    if (-not (Test-Path -LiteralPath $parent)) {
        New-Item -ItemType Directory -Force -Path $parent | Out-Null
    }

    $pythonScript = @'
import sys, os, json
from src.evidence.signing import EvidenceSigner, TamperEvidentLog
engine_root = sys.argv[1]
sys.path.insert(0, engine_root)
output_path = sys.argv[2]
fmt = sys.argv[3]
signer = EvidenceSigner(engine_root)
log = TamperEvidentLog(engine_root, signer)
result = log.export_audit_log(output_path, fmt)
print(result)
'@

    $tempScript = Join-Path ([System.IO.Path]::GetTempPath()) "aura-export-log-$([System.Guid]::NewGuid().ToString('N').Substring(0,8)).py"

    try {
        [System.IO.File]::WriteAllText($tempScript, $pythonScript, [System.Text.Encoding]::UTF8)
        $engineRootPath = Resolve-Path $EngineRoot -ErrorAction SilentlyContinue
        if (-not $engineRootPath) { $engineRootPath = $EngineRoot }

        $output = & python $tempScript $engineRootPath $OutputPath $Format 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Error "Export-AuditLog: Export failed: $output"
            return $null
        }

        Write-Host "[EVIDENCE-SIGNING] Audit log exported to: $OutputPath ($Format format)" -ForegroundColor Green
        return $OutputPath
    } catch {
        Write-Error "Export-AuditLog: Exception: $_"
        return $null
    } finally {
        if (Test-Path -LiteralPath $tempScript) {
            Remove-Item -LiteralPath $tempScript -Force -ErrorAction SilentlyContinue
        }
    }
}

Export-ModuleMember -Function Initialize-EvidenceSigning, New-EvidenceKeypair,
    Sign-EvidenceEntry, Test-EvidenceChainIntegrity, Export-AuditLog