"""Role-Based Access Control for AURA team operations.

Controls who can push, review, assign, and modify state.
Aligned with AURA engine phases: DISCOVER requires AUDITOR, PUSH_APPROVAL requires APPROVER/ADMIN.
Respects the engine's push.auto_approve and require_approval_for_push configuration.
"""
from __future__ import annotations

from typing import Tuple

from .models import TeamConfig, TeamMember, TeamRole

_ACTION_ROLE_MAP = {
    "assign_findings": (TeamRole.AUDITOR, TeamRole.ADMIN),
    "review_findings": (TeamRole.REVIEWER, TeamRole.ADMIN, TeamRole.APPROVER),
    "remediate": (TeamRole.REMEDIATOR, TeamRole.ADMIN),
    "approve_remediation": (TeamRole.APPROVER, TeamRole.ADMIN),
    "push": (TeamRole.APPROVER, TeamRole.ADMIN),
    "modify_state": (TeamRole.ADMIN,),
    "view_sensitive": (TeamRole.AUDITOR, TeamRole.ADMIN),
    "configure_team": (TeamRole.ADMIN,),
    "force_validation": (TeamRole.ADMIN,),
    "reset_engine": (TeamRole.ADMIN,),
    "manage_plugins": (TeamRole.ADMIN,),
    "view_all_findings": (TeamRole.AUDITOR, TeamRole.ADMIN, TeamRole.REVIEWER, TeamRole.APPROVER),
    "add_comments": (TeamRole.AUDITOR, TeamRole.ADMIN, TeamRole.REVIEWER,
                      TeamRole.REMEDIATOR, TeamRole.APPROVER, TeamRole.VIEWER),
    "trigger_audit": (TeamRole.AUDITOR, TeamRole.ADMIN),
    "adversarial_campaign": (TeamRole.AUDITOR, TeamRole.ADMIN),
    "mutation_test": (TeamRole.AUDITOR, TeamRole.ADMIN),
    "score_report": (TeamRole.AUDITOR, TeamRole.ADMIN, TeamRole.REVIEWER),
}


class RBAC:
    def __init__(self, team_config: TeamConfig):
        self.config = team_config

    def _get_member(self, member_id: str) -> TeamMember:
        member = self.config.get_member(member_id)
        if not member:
            raise ValueError(f"Member '{member_id}' not found in team configuration")
        return member

    def _has_any_role(self, member: TeamMember, roles: Tuple[TeamRole, ...]) -> bool:
        return any(role in member.roles for role in roles)

    def can_assign_findings(self, member_id: str) -> bool:
        member = self._get_member(member_id)
        return self._has_any_role(member, (TeamRole.AUDITOR, TeamRole.ADMIN))

    def can_review_findings(self, member_id: str) -> bool:
        member = self._get_member(member_id)
        return self._has_any_role(member, (TeamRole.REVIEWER, TeamRole.ADMIN, TeamRole.APPROVER))

    def can_remediate(self, member_id: str) -> bool:
        member = self._get_member(member_id)
        return self._has_any_role(member, (TeamRole.REMEDIATOR, TeamRole.ADMIN))

    def can_push(self, member_id: str) -> bool:
        if not self.config.require_approval_for_push:
            return True
        member = self._get_member(member_id)
        return self._has_any_role(member, (TeamRole.APPROVER, TeamRole.ADMIN))

    def can_modify_state(self, member_id: str) -> bool:
        member = self._get_member(member_id)
        return self._has_any_role(member, (TeamRole.ADMIN,))

    def can_view_sensitive(self, member_id: str) -> bool:
        member = self._get_member(member_id)
        return self._has_any_role(member, (TeamRole.AUDITOR, TeamRole.ADMIN))

    def can_force_validation(self, member_id: str) -> bool:
        member = self._get_member(member_id)
        return self._has_any_role(member, (TeamRole.ADMIN,))

    def can_reset_engine(self, member_id: str) -> bool:
        member = self._get_member(member_id)
        return self._has_any_role(member, (TeamRole.ADMIN,))

    def can_configure_team(self, member_id: str) -> bool:
        member = self._get_member(member_id)
        return self._has_any_role(member, (TeamRole.ADMIN,))

    def can_add_comments(self, member_id: str) -> bool:
        member = self._get_member(member_id)
        return True

    def authorize(self, member_id: str, action: str) -> Tuple[bool, str]:
        try:
            member = self._get_member(member_id)
        except ValueError as e:
            return False, str(e)

        allowed_roles = _ACTION_ROLE_MAP.get(action)
        if not allowed_roles:
            return False, f"Unknown action '{action}'. Available actions: {', '.join(sorted(_ACTION_ROLE_MAP.keys()))}"

        if self._has_any_role(member, allowed_roles):
            return True, ""

        role_names = [r.value for r in allowed_roles]
        member_roles = [r.value for r in member.roles]
        return False, (
            f"Member '{member_id}' with roles {member_roles} is not authorized for "
            f"action '{action}'. Required roles: {role_names}."
        )

    def member_permissions(self, member_id: str) -> dict:
        try:
            member = self._get_member(member_id)
        except ValueError as e:
            return {"error": str(e)}

        return {
            "member_id": member_id,
            "member_name": member.name,
            "roles": [r.value for r in member.roles],
            "permissions": {
                action: self._has_any_role(member, allowed_roles)
                for action, allowed_roles in _ACTION_ROLE_MAP.items()
            },
        }

    def require_role(self, member_id: str, action: str) -> None:
        allowed, reason = self.authorize(member_id, action)
        if not allowed:
            raise PermissionError(reason)