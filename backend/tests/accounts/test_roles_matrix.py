"""Role x capability truth table, registry invariants and the generated-doc drift test (P2-04).

The expectations below are written out by hand on purpose: they must not be derived from the code under
test, so a change to the matrix has to be made twice and is therefore reviewed.
"""

from pathlib import Path

import pytest

from apps.accounts.roles import (
    ALL_ROLES,
    CAPABILITIES,
    CAPABILITY_NAMES,
    CLIENT_GRANTABLE,
    ROLE_ADMIN,
    ROLE_CAMPAIGN_MANAGER,
    ROLE_CAPABILITIES,
    ROLE_SALES_FOLLOW_UP,
    ROLE_SYSTEM,
)
from scripts.gen_rbac_matrix import render

MANAGER = {
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
ADMIN_EXTRA = {
    "campaigns.view_all",
    "contacts.view_all",
    "attempts.view_all",
    "analytics.view_all",
    "retry_policy.write",
    "agent_config.write",
    "suppression.manage",
    "audit.view",
}
EXPECTED = {
    ROLE_CAMPAIGN_MANAGER: MANAGER,
    ROLE_ADMIN: MANAGER | ADMIN_EXTRA,
    ROLE_SALES_FOLLOW_UP: {"contacts.view_own", "final_output.view"},
    ROLE_SYSTEM: set(),
}


@pytest.mark.parametrize("role", ALL_ROLES)
def test_role_capabilities_match_the_reviewed_truth_table(role):
    assert set(ROLE_CAPABILITIES[role]) == EXPECTED[role]


@pytest.mark.parametrize("capability", sorted(CAPABILITY_NAMES))
@pytest.mark.parametrize("role", ALL_ROLES)
def test_every_role_by_capability_cell(role, capability):
    assert (capability in ROLE_CAPABILITIES[role]) is (capability in EXPECTED[role])


def test_only_admin_can_write_configuration_or_manage_suppression():
    for capability in ("retry_policy.write", "agent_config.write", "suppression.manage", "audit.view"):
        holders = {r for r in ALL_ROLES if capability in ROLE_CAPABILITIES[r]}
        assert holders == {ROLE_ADMIN}, capability


def test_sales_is_read_only_and_cannot_hear_recordings():
    granted = ROLE_CAPABILITIES[ROLE_SALES_FOLLOW_UP]
    assert not {c for c in granted if c.endswith((".write", ".create", ".import", ".suppress", ".manage"))}
    assert "recordings.listen" not in granted and "transcripts.view" not in granted


@pytest.mark.parametrize(
    "capability", ["recordings.listen", "transcripts.view", "users.manage", "api_clients.manage"]
)
def test_sensitive_capabilities_belong_to_no_role(capability):
    assert not any(capability in ROLE_CAPABILITIES[r] for r in ALL_ROLES)


def test_system_role_has_no_capability_at_all():
    assert ROLE_CAPABILITIES[ROLE_SYSTEM] == frozenset()


def test_registry_names_are_unique_namespaced_and_described():
    names = [c.name for c in CAPABILITIES]
    assert len(names) == len(set(names))
    for cap in CAPABILITIES:
        assert cap.name.count(".") == 1 and cap.name == cap.name.lower() and cap.description


def test_every_role_capability_exists_in_the_registry():
    for granted in ROLE_CAPABILITIES.values():
        assert granted <= CAPABILITY_NAMES


def test_admin_is_a_superset_of_campaign_manager():
    assert ROLE_CAPABILITIES[ROLE_CAMPAIGN_MANAGER] < ROLE_CAPABILITIES[ROLE_ADMIN]


def test_api_clients_can_only_be_granted_read_only_cross_scope_capabilities():
    assert {
        "campaigns.view_all",
        "contacts.view_all",
        "attempts.view_all",
        "analytics.view_all",
        "final_output.view",
    } == CLIENT_GRANTABLE
    for name in CLIENT_GRANTABLE:
        assert not name.endswith((".write", ".create", ".import", ".suppress", ".manage", ".update_status"))
    for name in ("recordings.listen", "transcripts.view", "audit.view", "suppression.manage"):
        assert name not in CLIENT_GRANTABLE


def test_committed_rbac_matrix_has_not_drifted():
    committed = Path(__file__).resolve().parents[3] / "docs" / "phase-2" / "RBAC-MATRIX.md"
    assert committed.read_text() == render(), (
        "run: python -m scripts.gen_rbac_matrix > ../docs/phase-2/RBAC-MATRIX.md"
    )


def test_registry_self_check_rejects_duplicates_unknown_roles_and_unknown_capabilities(monkeypatch):
    from apps.accounts import roles

    roles._check_registry()  # the real registry is consistent
    monkeypatch.setattr(roles, "CAPABILITIES", (*roles.CAPABILITIES, roles.CAPABILITIES[0]))
    with pytest.raises(RuntimeError, match="Duplicate"):
        roles._check_registry()
    monkeypatch.undo()
    monkeypatch.setattr(roles, "ROLE_CAPABILITIES", {ROLE_ADMIN: frozenset()})
    with pytest.raises(RuntimeError, match="exactly the known roles"):
        roles._check_registry()
    monkeypatch.undo()
    broken = {**roles.ROLE_CAPABILITIES, ROLE_SYSTEM: frozenset({"made.up"})}
    monkeypatch.setattr(roles, "ROLE_CAPABILITIES", broken)
    with pytest.raises(RuntimeError, match="not in the registry"):
        roles._check_registry()
