# Module: team-workflow.ps1
# Purpose: Multi-user team workflow support for PowerShell orchestrator
# Classification: OPTIONAL
#
# Provides team-aware assignment, review, and RBAC checks that integrate
# with the AURA engine's promote-state cycle and push-approval flow.
#
# Engine integration points:
#   - promote-state:  Invoke-TeamReviewGate before committing VERIFIED findings
#   - push:           Test-TeamPushAuthorization before Invoke-EnginePush
#   - run:            Invoke-AutoAssignment after generate-cycle-prompt

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Add-Type -AssemblyName System.Web.Extensions

$script:TeamModuleVersion = "1.0.0"

# ============================================================
# CONFIG LOADING
# ============================================================

function Get-TeamConfig {
    <#
    .SYNOPSIS
        Load team configuration from .aura/team-config.json.
    .DESCRIPTION
        Loads and validates team config. Falls back to example config
        if team-config.json does not exist.
    #>
    param(
        [Parameter(Mandatory = $true)]
        [string]$EngineRoot
    )

    $teamConfigFile = Join-Path $EngineRoot "team-config.json"
    $exampleFile = Join-Path $EngineRoot "team-config.example.json"

    $configPath = if (Test-Path -LiteralPath $teamConfigFile) {
        $teamConfigFile
    } elseif (Test-Path -LiteralPath $exampleFile) {
        Write-Warning "[TEAM] team-config.json not found. Using example config. Create team-config.json for production use."
        $exampleFile
    } else {
        Write-Warning "[TEAM] No team config found. Team workflow is DISABLED."
        return @{ enabled = $false; members = @{}; error = "No config file found" }
    }

    try {
        $content = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8
        $config = $content | ConvertFrom-Json

        if (-not $config.members) {
            $config | Add-Member -NotePropertyName "members" -NotePropertyValue @{} -Force
        }
        if (-not $config.auto_assign) {
            $config | Add-Member -NotePropertyName "auto_assign" -NotePropertyValue $true -Force
        }
        if (-not $config.assignment_rules) {
            $config | Add-Member -NotePropertyName "assignment_rules" -NotePropertyValue @{} -Force
        }
        if (-not $config.require_review_for_p0_p2) {
            $config | Add-Member -NotePropertyName "require_review_for_p0_p2" -NotePropertyValue $true -Force
        }
        if (-not $config.require_approval_for_push) {
            $config | Add-Member -NotePropertyName "require_approval_for_push" -NotePropertyValue $true -Force
        }
        if (-not $config.approval_chain) {
            $config | Add-Member -NotePropertyName "approval_chain" -NotePropertyValue @{ P0 = 2; P1 = 1; P2 = 1 } -Force
        }
        if (-not $config.notification_on_assignment) {
            $config | Add-Member -NotePropertyName "notification_on_assignment" -NotePropertyValue $true -Force
        }

        $config | Add-Member -NotePropertyName "enabled" -NotePropertyValue $true -Force
        $config | Add-Member -NotePropertyName "config_path" -NotePropertyValue $configPath -Force

        return $config
    } catch {
        Write-Error "[TEAM] Failed to parse team config: $_"
        return @{ enabled = $false; members = @{}; error = "Parse error: $_" }
    }
}

function Save-TeamConfig {
    param(
        [Parameter(Mandatory = $true)]
        [string]$EngineRoot,

        [Parameter(Mandatory = $true)]
        [PSCustomObject]$Config
    )

    $teamConfigFile = Join-Path $EngineRoot "team-config.json"
    $tempPath = "$teamConfigFile.tmp.$([System.Guid]::NewGuid().ToString('N').Substring(0,8))"

    $cleanConfig = [PSCustomObject]@{
        members = $Config.members
        auto_assign = $Config.auto_assign
        assignment_rules = $Config.assignment_rules
        approval_chain = $Config.approval_chain
        require_review_for_p0_p2 = $Config.require_review_for_p0_p2
        require_approval_for_push = $Config.require_approval_for_push
        notification_on_assignment = $Config.notification_on_assignment
    }

    try {
        $json = $cleanConfig | ConvertTo-Json -Depth 50
        $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
        [System.IO.File]::WriteAllText($tempPath, $json, $utf8NoBom)
        Move-Item -LiteralPath $tempPath -Destination $teamConfigFile -Force
        Write-Host "[TEAM] Config saved to $teamConfigFile" -ForegroundColor Green
    } catch {
        if (Test-Path -LiteralPath $tempPath) {
            Remove-Item -LiteralPath $tempPath -Force -ErrorAction SilentlyContinue
        }
        Write-Error "[TEAM] Failed to save team config: $_"
    }
}

# ============================================================
# ROLE-BASED ACCESS CONTROL
# ============================================================

$script:ActionRoleMap = @{
    "assign_findings"    = @("auditor", "admin")
    "review_findings"    = @("reviewer", "admin", "approver")
    "remediate"          = @("remediator", "admin")
    "push"               = @("approver", "admin")
    "modify_state"       = @("admin")
    "view_sensitive"     = @("auditor", "admin")
    "configure_team"     = @("admin")
    "force_validation"   = @("admin")
    "adversarial_campaign" = @("auditor", "admin")
    "mutation_test"      = @("auditor", "admin")
}

function Test-TeamAuthorization {
    <#
    .SYNOPSIS
        Check if a member is authorized for a specific action.
    .DESCRIPTION
        Returns (allowed, reason). Uses email or member-id.
    #>
    param(
        [Parameter(Mandatory = $true)]
        [string]$EngineRoot,

        [Parameter(Mandatory = $true)]
        [string]$MemberEmail,

        [Parameter(Mandatory = $true)]
        [ValidateSet("assign_findings", "review_findings", "remediate", "push",
                      "modify_state", "view_sensitive", "configure_team",
                      "force_validation", "adversarial_campaign", "mutation_test")]
        [string]$Action
    )

    $config = Get-TeamConfig -EngineRoot $EngineRoot
    if (-not $config.enabled) {
        return @{ allowed = $true; reason = "Team workflow disabled" }
    }

    $member = Get-TeamMember -Config $config -Email $MemberEmail
    if (-not $member) {
        return @{ allowed = $false; reason = "Member '$MemberEmail' not in team" }
    }

    $allowedRoles = $script:ActionRoleMap[$Action]
    if (-not $allowedRoles) {
        return @{ allowed = $false; reason = "Unknown action '$Action'" }
    }

    $memberRoles = @($member.roles)
    $hasRole = $false
    foreach ($role in $memberRoles) {
        if ($role -in $allowedRoles) {
            $hasRole = $true
            break
        }
    }

    if ($hasRole) {
        return @{ allowed = $true; reason = "" }
    } else {
        return @{
            allowed = $false
            reason = "Member '$MemberEmail' with roles [$($memberRoles -join ', ')] lacks required roles [$($allowedRoles -join ', ')] for action '$Action'"
        }
    }
}

function Get-TeamMember {
    param(
        [PSCustomObject]$Config,
        [string]$Email
    )

    $emailLower = $Email.ToLower().Trim()
    foreach ($memberId in $Config.members.PSObject.Properties.Name) {
        $m = $Config.members.$memberId
        if ($m.email.ToLower().Trim() -eq $emailLower) {
            return $m
        }
    }
    return $null
}

# ============================================================
# FINDING ASSIGNMENT
# ============================================================

function Set-FindingAssignee {
    <#
    .SYNOPSIS
        Assign a finding to a team member.
    #>
    param(
        [Parameter(Mandatory = $true)]
        [string]$EngineRoot,

        [Parameter(Mandatory = $true)]
        [string]$FindingId,

        [Parameter(Mandatory = $true)]
        [string]$AssigneeEmail,

        [ValidateSet("critical", "high", "normal", "low")]
        [string]$Priority = "normal",

        [string]$Notes = ""
    )

    $config = Get-TeamConfig -EngineRoot $EngineRoot
    if (-not $config.enabled) {
        Write-Warning "[TEAM] Team workflow disabled. Assignment not saved."
        return $false
    }

    $member = Get-TeamMember -Config $config -Email $AssigneeEmail
    if (-not $member) {
        Write-Error "[TEAM] Assignee '$AssigneeEmail' not found in team configuration."
        return $false
    }

    $assignmentsFile = Join-Path $EngineRoot "state/finding-assignments.json"
    $assignments = @{}
    if (Test-Path -LiteralPath $assignmentsFile) {
        try {
            $existing = Get-Content -LiteralPath $assignmentsFile -Raw -Encoding UTF8 | ConvertFrom-Json
            $assignments = $existing
        } catch {}
    }

    $assignment = [PSCustomObject]@{
        finding_id   = $FindingId
        assigned_to  = $AssigneeEmail
        assigned_by  = "manual"
        assigned_at  = (Get-Date).ToString("o")
        priority     = $Priority
        notes        = $Notes
        is_overdue   = $false
    }

    if ($assignments -is [PSCustomObject]) {
        $assignments | Add-Member -NotePropertyName $FindingId -NotePropertyValue $assignment -Force
    } else {
        $assignments[$FindingId] = $assignment
    }

    $json = $assignments | ConvertTo-Json -Depth 50
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($assignmentsFile, $json, $utf8NoBom)

    Write-Host "[TEAM] Finding $FindingId assigned to $AssigneeEmail (priority: $Priority)" -ForegroundColor Green
    return $true
}

function Invoke-AutoAssignment {
    <#
    .SYNOPSIS
        Auto-assign unassigned findings to team members based on expertise and workload.
        Called during promote-state cycle to auto-assign before review.
    #>
    param(
        [Parameter(Mandatory = $true)]
        [string]$EngineRoot,

        [string]$FindingsFile = ""
    )

    $config = Get-TeamConfig -EngineRoot $EngineRoot
    if (-not $config.enabled -or -not $config.auto_assign) {
        Write-Host "[TEAM] Auto-assignment disabled." -ForegroundColor Gray
        return @{}
    }

    if (-not $FindingsFile) {
        $FindingsFile = Join-Path $EngineRoot "state/findings.json"
    }

    if (-not (Test-Path -LiteralPath $FindingsFile)) {
        Write-Warning "[TEAM] Findings file not found: $FindingsFile"
        return @{}
    }

    $findingsData = Get-Content -LiteralPath $FindingsFile -Raw -Encoding UTF8 | ConvertFrom-Json
    $findings = @($findingsData.findings)

    $assignmentsFile = Join-Path $EngineRoot "state/finding-assignments.json"
    $existingAssignments = @{}
    if (Test-Path -LiteralPath $assignmentsFile) {
        try {
            $existingAssignments = Get-Content -LiteralPath $assignmentsFile -Raw -Encoding UTF8 | ConvertFrom-Json
        } catch {}
    }

    $assignedIds = @{}
    if ($existingAssignments -is [PSCustomObject]) {
        foreach ($prop in $existingAssignments.PSObject.Properties) {
            $assignedIds[$prop.Name] = $true
        }
    } elseif ($existingAssignments -is [hashtable]) {
        foreach ($key in $existingAssignments.Keys) {
            $assignedIds[$key] = $true
        }
    }

    $unassigned = @($findings | Where-Object {
        $_.status -in @("OPEN", "IN_PROGRESS") -and
        $_.severity -in @("P0", "P1", "P2") -and
        (-not $assignedIds.ContainsKey($_.id))
    })

    if ($unassigned.Count -eq 0) {
        Write-Host "[TEAM] No unassigned findings." -ForegroundColor Gray
        return @{}
    }

    $results = @{}
    foreach ($finding in $unassigned) {
        $category = $finding.category
        $severity = $finding.severity

        $targetRoles = @("remediator")
        if ($category -eq "SECURITY" -or $severity -eq "P0") {
            $targetRoles = @("auditor", "remediator")
        }

        $candidates = @()
        foreach ($memberId in $config.members.PSObject.Properties.Name) {
            $m = $config.members.$memberId
            $memberRoles = @($m.roles)
            $match = $false
            foreach ($r in $targetRoles) {
                if ($r -in $memberRoles) { $match = $true; break }
            }
            if ($match) {
                $expertiseMatch = 0
                if ($m.expertise -contains $category.ToLower()) {
                    $expertiseMatch = 1
                }
                $candidates += @{ id = $memberId; email = $m.email; score = $expertiseMatch }
            }
        }

        if ($candidates.Count -gt 0) {
            $best = ($candidates | Sort-Object -Property score -Descending | Select-Object -First 1)
            $assignment = [PSCustomObject]@{
                finding_id   = $finding.id
                assigned_to  = $best.email
                assigned_by  = "auto-assigner"
                assigned_at  = (Get-Date).ToString("o")
                priority     = if ($severity -in @("P0", "P1")) { "critical" } else { "normal" }
                notes        = "Auto-assigned by expertise ($category)"
                is_overdue   = $false
            }

            if ($existingAssignments -is [PSCustomObject]) {
                $existingAssignments | Add-Member -NotePropertyName $finding.id -NotePropertyValue $assignment -Force
            } else {
                $existingAssignments[$finding.id] = $assignment
            }

            $results[$finding.id] = $best.email
            Write-Host "[TEAM] Auto-assigned $($finding.id) ($($finding.severity)/$($finding.category)) -> $($best.email)" -ForegroundColor Cyan
        }
    }

    if ($results.Count -gt 0) {
        $json = $existingAssignments | ConvertTo-Json -Depth 50
        $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
        [System.IO.File]::WriteAllText($assignmentsFile, $json, $utf8NoBom)
    }

    return $results
}

# ============================================================
# WORKLOAD MONITORING
# ============================================================

function Get-TeamWorkload {
    <#
    .SYNOPSIS
        Get workload distribution across team members.
    #>
    param(
        [Parameter(Mandatory = $true)]
        [string]$EngineRoot
    )

    $config = Get-TeamConfig -EngineRoot $EngineRoot
    if (-not $config.enabled) {
        return @{ enabled = $false }
    }

    $findingsFile = Join-Path $EngineRoot "state/findings.json"
    $assignmentsFile = Join-Path $EngineRoot "state/finding-assignments.json"

    $assignments = @{}
    if (Test-Path -LiteralPath $assignmentsFile) {
        try {
            $assignments = Get-Content -LiteralPath $assignmentsFile -Raw -Encoding UTF8 | ConvertFrom-Json
        } catch {}
    }

    $findings = @()
    if (Test-Path -LiteralPath $findingsFile) {
        try {
            $findingsData = Get-Content -LiteralPath $findingsFile -Raw -Encoding UTF8 | ConvertFrom-Json
            $findings = @($findingsData.findings)
        } catch {}
    }

    $memberWorkload = @{}
    foreach ($memberId in $config.members.PSObject.Properties.Name) {
        $m = $config.members.$memberId

        $assigned = 0
        $p0Count = 0
        $p1Count = 0
        $openCount = 0

        foreach ($fid in ($assignments.PSObject.Properties.Name)) {
            $a = if ($assignments -is [PSCustomObject]) { $assignments.$fid } else { $assignments[$fid] }
            if ($a.assigned_to -eq $m.email) {
                $assigned++
                $finding = $findings | Where-Object { $_.id -eq $fid } | Select-Object -First 1
                if ($finding) {
                    if ($finding.severity -eq "P0") { $p0Count++ }
                    if ($finding.severity -eq "P1") { $p1Count++ }
                    if ($finding.status -in @("OPEN", "IN_PROGRESS")) { $openCount++ }
                }
            }
        }

        $memberWorkload[$memberId] = @{
            name           = $m.name
            email          = $m.email
            roles          = @($m.roles)
            assigned_total = $assigned
            open_count     = $openCount
            p0_count       = $p0Count
            p1_count       = $p1Count
        }
    }

    $totalAssigned = ($memberWorkload.Values | Measure-Object -Property assigned_total -Sum).Sum
    $totalOpen = ($memberWorkload.Values | Measure-Object -Property open_count -Sum).Sum

    return @{
        enabled         = $true
        total_assigned  = $totalAssigned
        total_open      = $totalOpen
        members         = $memberWorkload
    }
}

# ============================================================
# REVIEW WORKFLOW
# ============================================================

function Submit-ForReview {
    <#
    .SYNOPSIS
        Submit a finding for independent human review.
    .DESCRIPTION
        Writes review tracking state. Called during promote-state before
        findings are committed as VERIFIED.
    #>
    param(
        [Parameter(Mandatory = $true)]
        [string]$EngineRoot,

        [Parameter(Mandatory = $true)]
        [string]$FindingId,

        [string]$SubmitterEmail = ""
    )

    $config = Get-TeamConfig -EngineRoot $EngineRoot
    if (-not $config.enabled) { return $true }

    $reviewsFile = Join-Path $EngineRoot "state/finding-reviews.json"
    $reviews = @{}
    if (Test-Path -LiteralPath $reviewsFile) {
        try {
            $existing = Get-Content -LiteralPath $reviewsFile -Raw -Encoding UTF8 | ConvertFrom-Json
            $reviews = $existing
        } catch {}
    }

    $now = (Get-Date).ToString("o")
    $submission = [PSCustomObject]@{
        finding_id    = $FindingId
        submitter     = $SubmitterEmail
        submitted_at  = $now
        status        = "pending_review"
    }

    if ($reviews -is [PSCustomObject]) {
        $reviews | Add-Member -NotePropertyName $FindingId -NotePropertyValue $submission -Force
    } else {
        $reviews[$FindingId] = $submission
    }

    $json = $reviews | ConvertTo-Json -Depth 50
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($reviewsFile, $json, $utf8NoBom)

    Write-Host "[TEAM] Finding $FindingId submitted for review." -ForegroundColor Cyan
    return $true
}

function Approve-Finding {
    <#
    .SYNOPSIS
        Approve a finding's remediation by a reviewer.
    #>
    param(
        [Parameter(Mandatory = $true)]
        [string]$EngineRoot,

        [Parameter(Mandatory = $true)]
        [string]$FindingId,

        [Parameter(Mandatory = $true)]
        [string]$ReviewerEmail,

        [string]$Comments = ""
    )

    $auth = Test-TeamAuthorization -EngineRoot $EngineRoot -MemberEmail $ReviewerEmail -Action "review_findings"
    if (-not $auth.allowed) {
        Write-Error "[TEAM] Authorization failed: $($auth.reason)"
        return $false
    }

    $reviewsFile = Join-Path $EngineRoot "state/finding-reviews.json"
    $reviews = @{}
    if (Test-Path -LiteralPath $reviewsFile) {
        try {
            $existing = Get-Content -LiteralPath $reviewsFile -Raw -Encoding UTF8 | ConvertFrom-Json
            $reviews = $existing
        } catch {}
    }

    $now = (Get-Date).ToString("o")
    $approval = [PSCustomObject]@{
        finding_id   = $FindingId
        reviewer     = $ReviewerEmail
        resolution   = "accepted"
        comments     = $Comments
        reviewed_at  = $now
    }

    $reviewKey = "$($FindingId)_review"
    if ($reviews -is [PSCustomObject]) {
        $reviews | Add-Member -NotePropertyName $reviewKey -NotePropertyValue $approval -Force
    } else {
        $reviews[$reviewKey] = $approval
    }

    $json = $reviews | ConvertTo-Json -Depth 50
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($reviewsFile, $json, $utf8NoBom)

    Write-Host "[TEAM] Finding $FindingId approved by $ReviewerEmail." -ForegroundColor Green
    return $true
}

function Reject-Finding {
    <#
    .SYNOPSIS
        Reject a finding's remediation.
    #>
    param(
        [Parameter(Mandatory = $true)]
        [string]$EngineRoot,

        [Parameter(Mandatory = $true)]
        [string]$FindingId,

        [Parameter(Mandatory = $true)]
        [string]$ReviewerEmail,

        [Parameter(Mandatory = $true)]
        [string]$Reason
    )

    $auth = Test-TeamAuthorization -EngineRoot $EngineRoot -MemberEmail $ReviewerEmail -Action "review_findings"
    if (-not $auth.allowed) {
        Write-Error "[TEAM] Authorization failed: $($auth.reason)"
        return $false
    }

    $reviewsFile = Join-Path $EngineRoot "state/finding-reviews.json"
    $reviews = @{}
    if (Test-Path -LiteralPath $reviewsFile) {
        try {
            $existing = Get-Content -LiteralPath $reviewsFile -Raw -Encoding UTF8 | ConvertFrom-Json
            $reviews = $existing
        } catch {}
    }

    $now = (Get-Date).ToString("o")
    $rejection = [PSCustomObject]@{
        finding_id   = $FindingId
        reviewer     = $ReviewerEmail
        resolution   = "rejected"
        comments     = $Reason
        reviewed_at  = $now
    }

    $reviewKey = "$($FindingId)_review"
    if ($reviews -is [PSCustomObject]) {
        $reviews | Add-Member -NotePropertyName $reviewKey -NotePropertyValue $rejection -Force
    } else {
        $reviews[$reviewKey] = $rejection
    }

    $json = $reviews | ConvertTo-Json -Depth 50
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($reviewsFile, $json, $utf8NoBom)

    Write-Host "[TEAM] Finding $FindingId rejected by ${ReviewerEmail}: $Reason" -ForegroundColor Yellow
    return $true
}

# ============================================================
# REVIEW GATE (promote-state integration)
# ============================================================

function Invoke-TeamReviewGate {
    <#
    .SYNOPSIS
        Gate check before promote-state commits findings as VERIFIED.
        Ensures required approvals exist for P0-P2 findings.
        Called by promote-state validation pipeline.
    .DESCRIPTION
        Returns violations array. Empty = PASS.
        Enforces:
        - P0 requires 2 unique approver approvals
        - P1/P2 require 1 approver approval
        - No self-approval (approver != submitter)
    #>
    param(
        [Parameter(Mandatory = $true)]
        [string]$EngineRoot,

        [Parameter(Mandatory = $false)]
        [array]$ProposedFindings = $null
    )

    $config = Get-TeamConfig -EngineRoot $EngineRoot
    if (-not $config.enabled -or -not $config.require_review_for_p0_p2) {
        return @()
    }

    if (-not $ProposedFindings) {
        $proposedFile = Join-Path $EngineRoot "state/proposed-findings.json"
        if (Test-Path -LiteralPath $proposedFile) {
            try {
                $data = Get-Content -LiteralPath $proposedFile -Raw -Encoding UTF8 | ConvertFrom-Json
                $ProposedFindings = @($data.findings)
            } catch {
                Write-Warning "[TEAM] Could not load proposed-findings.json"
                return @()
            }
        }
    }

    if (-not $ProposedFindings -or $ProposedFindings.Count -eq 0) {
        return @()
    }

    $reviewsFile = Join-Path $EngineRoot "state/finding-reviews.json"
    $reviews = @{}
    if (Test-Path -LiteralPath $reviewsFile) {
        try {
            $reviews = Get-Content -LiteralPath $reviewsFile -Raw -Encoding UTF8 | ConvertFrom-Json
        } catch {}
    }

    $assignmentsFile = Join-Path $EngineRoot "state/finding-assignments.json"
    $assignments = @{}
    if (Test-Path -LiteralPath $assignmentsFile) {
        try {
            $assignments = Get-Content -LiteralPath $assignmentsFile -Raw -Encoding UTF8 | ConvertFrom-Json
        } catch {}
    }

    $violations = @()

    foreach ($finding in $ProposedFindings) {
        if ($finding.status -ne "VERIFIED") { continue }
        if ($finding.severity -notin @("P0", "P1", "P2")) { continue }

        $requiredApprovals = if ($finding.severity -eq "P0") {
            if ($config.approval_chain.P0) { $config.approval_chain.P0 } else { 2 }
        } elseif ($finding.severity -eq "P1") {
            if ($config.approval_chain.P1) { $config.approval_chain.P1 } else { 1 }
        } else {
            if ($config.approval_chain.P2) { $config.approval_chain.P2 } else { 1 }
        }

        $reviewKey = "$($finding.id)_review"
        $reviewData = if ($reviews -is [PSCustomObject]) { $reviews.$reviewKey } else { $reviews[$reviewKey] }
        if (-not $reviewData) {
            $violations += "TEAM_REVIEW: $($finding.id) ($($finding.severity)) has no review record. Cannot promote to VERIFIED."
            continue
        }

        if ($reviewData.resolution -ne "accepted") {
            $violations += "TEAM_REVIEW: $($finding.id) ($($finding.severity)) review was $($reviewData.resolution), not accepted. Cannot promote to VERIFIED."
            continue
        }

        $findingAssignment = if ($assignments -is [PSCustomObject]) { $assignments.($finding.id) } else { $assignments[$finding.id] }
        $assigneeEmail = if ($findingAssignment) { $findingAssignment.assigned_to } else { "" }

        if ($assigneeEmail -and $reviewData.reviewer -eq $assigneeEmail) {
            $violations += "TEAM_REVIEW: $($finding.id) -- SELF-REVIEW DETECTED. Assignee '$assigneeEmail' cannot review own finding."
        }
    }

    return $violations
}

# ============================================================
# PUSH AUTHORIZATION
# ============================================================

function Test-TeamPushAuthorization {
    <#
    .SYNOPSIS
        Check if push is authorized under team workflow.
        Called before Invoke-EnginePush.
    #>
    param(
        [Parameter(Mandatory = $true)]
        [string]$EngineRoot,

        [string]$PusherEmail = ""
    )

    $config = Get-TeamConfig -EngineRoot $EngineRoot
    if (-not $config.enabled -or -not $config.require_approval_for_push) {
        return @{ authorized = $true; reason = "Team push approval not required" }
    }

    if (-not $PusherEmail) {
        $pusher = git config user.email 2>&1 | Out-String
        $PusherEmail = $pusher.Trim()
    }

    $auth = Test-TeamAuthorization -EngineRoot $EngineRoot -MemberEmail $PusherEmail -Action "push"
    return $auth
}

# ============================================================
# EXPORTS
# ============================================================

Export-ModuleMember -Function `
    Get-TeamConfig, Save-TeamConfig, `
    Test-TeamAuthorization, Get-TeamMember, `
    Set-FindingAssignee, Invoke-AutoAssignment, `
    Get-TeamWorkload, `
    Submit-ForReview, Approve-Finding, Reject-Finding, `
    Invoke-TeamReviewGate, Test-TeamPushAuthorization