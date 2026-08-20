# Module: plugin-loader.ps1
# Purpose: Plugin loading support in the PowerShell orchestrator
# Classification: OPTIONAL
#
# Provides PowerShell-callable functions for loading YAML/JSON plugin
# configurations and aggregating plugin rules alongside built-in modules.
#
# Depends on: PyYAML (Python) or ConvertFrom-Json for JSON plugins.
# For full plugin lifecycle, delegate to src/plugins/*.py via the AURA CLI.

function Import-AuraPlugin {
    <#
    .SYNOPSIS
        Load a YAML/JSON plugin configuration file.
    .DESCRIPTION
        Parses a plugin configuration file and registers its rules, scales,
        weights, or gates into the current audit session.
    .PARAMETER PluginPath
        Path to the plugin .yml, .yaml, or .json file.
    .PARAMETER PluginType
        Override the plugin type (audit_rule, severity_scale, dimension_weight,
        convergence_gate, evidence_collector, reporter, notifier, remediator).
    #>
    param(
        [Parameter(Mandatory = $true)]
        [string]$PluginPath,

        [ValidateSet(
            "audit_rule", "severity_scale", "dimension_weight",
            "convergence_gate", "evidence_collector", "reporter",
            "notifier", "remediator"
        )]
        [string]$PluginType
    )

    if (-not (Test-Path -LiteralPath $PluginPath -PathType Leaf)) {
        Write-Warning "[AURA][PLUGIN] Plugin file not found: $PluginPath"
        return $null
    }

    $ext = [System.IO.Path]::GetExtension($PluginPath).ToLower()
    $pluginData = $null

    if ($ext -eq ".json") {
        try {
            $pluginData = Read-JsonFile $PluginPath
        } catch {
            Write-Warning "[AURA][PLUGIN] Failed to parse JSON plugin: $PluginPath -- $_"
            return $null
        }
    } elseif ($ext -eq ".yml" -or $ext -eq ".yaml") {
        try {
            $pluginPathSafe = $PluginPath -replace "'", "''"
            $yamlOutput = python -c @"
import yaml, json, sys
with open(r'${pluginPathSafe}', 'r', encoding='utf-8') as f:
    data = yaml.safe_load(f)
print(json.dumps(data, indent=2))
"@ 2>&1
            if ($LASTEXITCODE -ne 0) {
                Write-Warning "[AURA][PLUGIN] YAML parsing failed: $PluginPath -- $yamlOutput"
                return $null
            }
            $pluginData = $yamlOutput | ConvertFrom-Json
        } catch {
            Write-Warning "[AURA][PLUGIN] Python YAML bridge failed: $_"
            return $null
        }
    } else {
        Write-Warning "[AURA][PLUGIN] Unsupported plugin format: $ext"
        return $null
    }

    if (-not $pluginData) {
        Write-Warning "[AURA][PLUGIN] Empty or invalid plugin data in $PluginPath"
        return $null
    }

    $name = $pluginData.name
    if (-not $name) {
        Write-Warning "[AURA][PLUGIN] Plugin missing 'name' field: $PluginPath"
        return $null
    }

    $resolvedType = if ($PluginType) { $PluginType } else { $pluginData.plugin_type }
    if (-not $resolvedType) {
        Write-Warning "[AURA][PLUGIN] Plugin missing 'plugin_type' field: $name"
        return $null
    }

    Write-Host "[AURA][PLUGIN] Loaded: $name (type=$resolvedType, version=$($pluginData.version))" -ForegroundColor Cyan

    $result = @{
        name        = $name
        version     = $pluginData.version
        type        = $resolvedType
        lifecycle   = $pluginData.lifecycle
        path        = $PluginPath
        data        = $pluginData
        enabled     = if ($null -ne $pluginData.enabled) { $pluginData.enabled } else { $true }
        priority    = if ($null -ne $pluginData.priority) { $pluginData.priority } else { 100 }
    }

    return $result
}

function Get-AuraPluginRules {
    <#
    .SYNOPSIS
        Aggregate audit rules from all plugin configurations in a directory.
    .DESCRIPTION
        Scans the given directory for .yml/.yaml/.json plugin files of type
        audit_rule and merges their rules into a single array.
    .PARAMETER PluginsDir
        Directory containing plugin configuration files.
    #>
    param(
        [Parameter(Mandatory = $true)]
        [string]$PluginsDir
    )

    if (-not (Test-Path -LiteralPath $PluginsDir -PathType Container)) {
        Write-Warning "[AURA][PLUGIN] Plugins directory not found: $PluginsDir"
        return @()
    }

    $allRules = @()
    $pluginFiles = Get-ChildItem -LiteralPath $PluginsDir -File |
        Where-Object { $_.Extension -in @(".yml", ".yaml", ".json") }

    foreach ($pf in $pluginFiles) {
        $plugin = Import-AuraPlugin -PluginPath $pf.FullName
        if (-not $plugin -or $plugin.type -ne "audit_rule" -or -not $plugin.enabled) {
            continue
        }
        $rules = $plugin.data.rules
        if ($rules -and $rules.Count -gt 0) {
            foreach ($rule in $rules) {
                $rule | Add-Member -NotePropertyName "plugin_name" -NotePropertyValue $plugin.name -Force
                $allRules += $rule
            }
        }
    }

    return $allRules
}

function Register-AuraPluginCommand {
    <#
    .SYNOPSIS
        Register a plugin-provided PowerShell command for use in the audit engine.
    .DESCRIPTION
        Wraps a plugin's YAML-defined command or Python module function as a
        PowerShell function callable during audit phases.
    .PARAMETER PluginPath
        Path to the plugin file or directory.
    .PARAMETER CommandName
        Name to register the command as in the current scope.
    #>
    param(
        [Parameter(Mandatory = $true)]
        [string]$PluginPath,

        [Parameter(Mandatory = $true)]
        [string]$CommandName
    )

    if (-not (Test-Path -LiteralPath $PluginPath)) {
        Write-Warning "[AURA][PLUGIN] Plugin path not found: $PluginPath"
        return $false
    }

    $isDir = Test-Path -LiteralPath $PluginPath -PathType Container

    if ($isDir) {
        $pyFiles = Get-ChildItem -LiteralPath $PluginPath -File -Filter "*.py"
        if ($pyFiles.Count -gt 0) {
            $pluginPathSafe = $PluginPath -replace "'", "''"
            $scriptBlock = {
                param($Context)
                python -c @"
import sys, json
sys.path.insert(0, r'${pluginPathSafe}')
import plugin
result = plugin.run(json.loads(sys.stdin.read()))
print(json.dumps(result))
"@
            }
            Set-Item -Path "function:script:$CommandName" -Value $scriptBlock -Force
            Write-Host "[AURA][PLUGIN] Registered Python command: $CommandName" -ForegroundColor Cyan
            return $true
        }
    }

    $plugin = Import-AuraPlugin -PluginPath $PluginPath
    if (-not $plugin) {
        return $false
    }

    $scriptBlock = {
        param($Context)
        Write-Host "[AURA][PLUGIN] Command '$CommandName' invoked (type=$($plugin.type))"
    }

    Set-Item -Path "function:script:$CommandName" -Value $scriptBlock -Force
    Write-Host "[AURA][PLUGIN] Registered plugin command: $CommandName" -ForegroundColor Cyan
    return $true
}

Export-ModuleMember -Function Import-AuraPlugin, Get-AuraPluginRules, Register-AuraPluginCommand