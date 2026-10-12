"""Render the role x capability matrix from ``apps.accounts.roles`` as Markdown.

Usage (from ``backend/``): ``python -m scripts.gen_rbac_matrix > ../docs/phase-2/RBAC-MATRIX.md``.
A test fails when the committed file differs from this output.
"""

from __future__ import annotations

from apps.accounts.roles import (
    ALL_ROLES,
    CAPABILITIES,
    ROLE_ADMIN,
    ROLE_CAMPAIGN_MANAGER,
    ROLE_CAPABILITIES,
    ROLE_SALES_FOLLOW_UP,
    ROLE_SYSTEM,
)

_COLUMNS = (ROLE_CAMPAIGN_MANAGER, ROLE_ADMIN, ROLE_SALES_FOLLOW_UP, ROLE_SYSTEM)


def render() -> str:
    assert set(_COLUMNS) == set(ALL_ROLES)
    lines = [
        "# Phase 2 — RBAC matrix",
        "",
        "Generated from `backend/apps/accounts/roles.py` by `python -m scripts.gen_rbac_matrix`.",
        "Do not edit by hand: a test fails when this file drifts from the code.",
        "`own` = rows in the caller's scope via `for_user()`; `all` = every row.",
        "",
        "| Capability | " + " | ".join(_COLUMNS) + " | API client grantable | Description |",
        "|---|" + "---|" * (len(_COLUMNS) + 2),
    ]
    for cap in CAPABILITIES:
        cells = ["yes" if cap.name in ROLE_CAPABILITIES[role] else "-" for role in _COLUMNS]
        grantable = "yes" if cap.client_grantable else "-"
        lines.append(f"| `{cap.name}` | " + " | ".join(cells) + f" | {grantable} | {cap.description} |")
    unassigned = [c.name for c in CAPABILITIES if not any(c.name in ROLE_CAPABILITIES[r] for r in ALL_ROLES)]
    lines += [
        "",
        "Capabilities held by no role (`"
        + "`, `".join(unassigned)
        + "`) are granted to individual users only, "
        "or are management-command level in Phase 2.",
        "`System` has no capabilities and cannot log in: service accounts use database roles and",
        "internal code paths.",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    print(render(), end="")
