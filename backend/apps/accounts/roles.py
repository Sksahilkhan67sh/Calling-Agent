"""Roles, the capability registry and the role matrix (Security-Architecture §3, Backend-Design §4.2).

Pure Python (no Django imports) so settings, models, the matrix generator and tests share one source.
A *capability* is one named action. It is stored as a Django custom permission on ``accounts.User`` and
granted to roles (Django Groups) by ``sync_roles``. Capabilities ending in ``_own`` mean "rows in the
caller's scope as defined by ``Model.objects.for_user(user)``", ``_all`` means "every row".
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

ROLE_ADMIN = "Admin"
ROLE_CAMPAIGN_MANAGER = "Campaign Manager"
ROLE_SALES_FOLLOW_UP = "Sales / Follow-up"
ROLE_SYSTEM = "System"

ALL_ROLES = (ROLE_ADMIN, ROLE_CAMPAIGN_MANAGER, ROLE_SALES_FOLLOW_UP, ROLE_SYSTEM)
# MFA is mandatory for these roles in production (Django-Backend-Design §4.1).
MFA_MANDATORY_ROLES = (ROLE_ADMIN, ROLE_CAMPAIGN_MANAGER)


@dataclass(frozen=True)
class Capability:
    name: str
    description: str
    # May an API client (machine key) be scoped to this capability? Only read-only, cross-campaign data.
    client_grantable: bool = False


CAPABILITIES: tuple[Capability, ...] = (
    Capability("campaigns.create", "Create campaigns"),
    Capability("campaigns.view_own", "View campaigns in the caller's scope"),
    Capability("campaigns.view_all", "View every campaign", client_grantable=True),
    Capability("campaigns.update_status", "Pause, resume or complete campaigns in scope"),
    Capability("contacts.import", "Import contacts into campaigns"),
    Capability("contacts.view_own", "View contacts in the caller's scope"),
    Capability("contacts.view_all", "View every contact", client_grantable=True),
    Capability("contacts.suppress", "Record a do-not-call request for contacts in scope"),
    Capability("attempts.view_own", "View call attempts in the caller's scope"),
    Capability("attempts.view_all", "View every call attempt", client_grantable=True),
    Capability("analytics.view_own", "View analytics of campaigns in scope"),
    Capability("analytics.view_all", "View cross-campaign analytics", client_grantable=True),
    Capability("retry_policy.view", "Read a campaign's retry policy"),
    Capability("retry_policy.write", "Configure a campaign's retry policy"),
    Capability("agent_config.view", "Read a campaign's agent configuration"),
    Capability("agent_config.write", "Configure a campaign's agent"),
    Capability("suppression.manage", "View and manage the suppression list"),
    Capability("final_output.view", "Read Final Output records in scope", client_grantable=True),
    Capability("recordings.listen", "Listen to call recordings (granted per user, audited)"),
    Capability("transcripts.view", "Read call transcripts (granted per user, audited)"),
    Capability("audit.view", "Read audit events"),
    Capability("users.manage", "Manage users (management commands only in Phase 2)"),
    Capability("api_clients.manage", "Manage API clients (management commands only in Phase 2)"),
)
CAPABILITY_NAMES = frozenset(c.name for c in CAPABILITIES)
CLIENT_GRANTABLE = frozenset(c.name for c in CAPABILITIES if c.client_grantable)

_CAMPAIGN_MANAGER = frozenset(
    {
        "campaigns.create",
        "campaigns.view_own",
        "campaigns.update_status",
        "contacts.import",
        "contacts.view_own",
        "contacts.suppress",
        "attempts.view_own",
        "analytics.view_own",
        "retry_policy.view",
        "agent_config.view",
        "final_output.view",
    }
)

ROLE_CAPABILITIES: Mapping[str, frozenset[str]] = {
    ROLE_CAMPAIGN_MANAGER: _CAMPAIGN_MANAGER,
    ROLE_ADMIN: _CAMPAIGN_MANAGER
    | {
        "campaigns.view_all",
        "contacts.view_all",
        "attempts.view_all",
        "analytics.view_all",
        "retry_policy.write",
        "agent_config.write",
        "suppression.manage",
        "audit.view",
    },
    ROLE_SALES_FOLLOW_UP: frozenset({"contacts.view_own", "final_output.view"}),
    # System is not a login role: service accounts use database roles and internal code paths.
    ROLE_SYSTEM: frozenset(),
}


def _check_registry() -> None:
    names = [c.name for c in CAPABILITIES]
    if len(names) != len(CAPABILITY_NAMES):
        raise RuntimeError("Duplicate capability name in the registry")
    if set(ROLE_CAPABILITIES) != set(ALL_ROLES):
        raise RuntimeError("ROLE_CAPABILITIES must define exactly the known roles")
    for role, granted in ROLE_CAPABILITIES.items():
        if not granted <= CAPABILITY_NAMES:
            raise RuntimeError(f"Role {role} grants a capability that is not in the registry")


_check_registry()
