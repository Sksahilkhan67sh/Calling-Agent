"""Compare the implemented OpenAPI schema with the contract (Backend/API-Specification.yaml).

Phase 1 mode (informational): spec paths that are not implemented yet are reported but do
not fail. Exit status is non-zero only on DRIFT for implemented paths:
  - an implemented path/method that the contract does not define,
  - a contract method missing on an implemented path,
  - differing path/query parameters,
  - a contract response code missing from the implementation.
Later phases turn "not yet implemented" into a failure as each app lands (docs/phase-1/DECISIONS.md).
Health routes are internal and not part of the contract.

Proposed additions: endpoints that Phase 2 implements but the contract does not define yet
(documented with exact YAML in docs/phase-2/DOC-PATCHES.md) are listed in PROPOSED_ADDITIONS and
reported informationally. Any other implemented-but-undefined operation is still DRIFT. P2-14
replaces this hard-coded set with annotation-driven marking.
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

SPEC_PATH = Path(__file__).resolve().parents[2] / "ai_calling agent" / "Backend" / "API-Specification.yaml"
INTERNAL_PATHS = {"/healthz", "/readyz"}
SERVER_PREFIX = "/v1"
HTTP_METHODS = {"get", "put", "post", "patch", "delete"}
PROPOSED_ADDITIONS = {
    ("get", "/auth/csrf"),
    ("get", "/auth/me"),
    ("post", "/auth/mfa/enroll"),
    ("post", "/auth/mfa/confirm"),
}


@dataclass
class Report:
    drift: list[str] = field(default_factory=list)
    not_implemented: list[str] = field(default_factory=list)
    internal: list[str] = field(default_factory=list)
    proposed_additions: list[str] = field(default_factory=list)
    compared: int = 0

    @property
    def exit_code(self) -> int:
        return 1 if self.drift else 0


def normalise_path(path: str) -> str:
    if path.startswith(SERVER_PREFIX + "/"):
        path = path[len(SERVER_PREFIX) :]
    return re.sub(r"\{[^}]+\}", "{}", path)


def _resolve(spec: dict[str, Any], node: dict[str, Any]) -> dict[str, Any]:
    ref = node.get("$ref")
    if not ref:
        return node
    target: Any = spec
    for part in ref.lstrip("#/").split("/"):
        target = target[part]
    return target  # type: ignore[no-any-return]


def _operations(doc: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for path, item in (doc.get("paths") or {}).items():
        shared = item.get("parameters", [])
        for method, operation in item.items():
            if method in HTTP_METHODS:
                merged = {**operation, "parameters": [*shared, *operation.get("parameters", [])]}
                result[(method, normalise_path(path))] = merged
    return result


def _parameters(doc: dict[str, Any], operation: dict[str, Any]) -> set[tuple[str, str]]:
    found = set()
    for raw in operation.get("parameters", []):
        param = _resolve(doc, raw)
        if param.get("in") == "query":
            found.add(("query", param["name"]))
        elif param.get("in") == "path":  # names may differ; the normalised path template is compared
            found.add(("path", "{}"))
    return found


def compare(spec: dict[str, Any], implemented: dict[str, Any]) -> Report:
    report = Report()
    spec_ops, impl_ops = _operations(spec), _operations(implemented)
    for key in sorted(impl_ops):
        method, path = key
        label = f"{method.upper()} {path}"
        if path in INTERNAL_PATHS:
            report.internal.append(label)
        elif key not in spec_ops:
            if key in PROPOSED_ADDITIONS:
                report.proposed_additions.append(label)
            else:
                report.drift.append(f"{label}: implemented but not defined in the contract")
    for key in sorted(spec_ops):
        method, path = key
        label = f"{method.upper()} {path}"
        impl_paths = {p for _, p in impl_ops}
        if path not in impl_paths:
            report.not_implemented.append(label)
            continue
        if key not in impl_ops:
            report.drift.append(f"{label}: defined in the contract but missing on the implemented path")
            continue
        report.compared += 1
        spec_params = _parameters(spec, spec_ops[key])
        impl_params = _parameters(implemented, impl_ops[key])
        if spec_params != impl_params:
            report.drift.append(
                f"{label}: parameters differ (contract {sorted(spec_params)}, "
                f"implementation {sorted(impl_params)})"
            )
        missing = set(map(str, spec_ops[key].get("responses", {}))) - set(
            map(str, impl_ops[key].get("responses", {}))
        )
        if missing:
            report.drift.append(f"{label}: response codes missing in implementation: {sorted(missing)}")
    return report


def generate_implemented_schema() -> dict[str, Any]:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.test")
    import django

    django.setup()
    from drf_spectacular.generators import SchemaGenerator

    return dict(SchemaGenerator().get_schema(request=None, public=True))


def main() -> int:
    spec = yaml.safe_load(SPEC_PATH.read_text())
    report = compare(spec, generate_implemented_schema())
    print(f"contract operations compared: {report.compared}")
    print(f"not yet implemented (informational): {len(report.not_implemented)}")
    print(f"internal, not in the contract: {', '.join(sorted(INTERNAL_PATHS))}")
    print(f"proposed additions (informational, see DOC-PATCHES.md): {len(report.proposed_additions)}")
    for line in report.proposed_additions:
        print(f"  proposed: {line}")
    for line in report.drift:
        print(f"DRIFT: {line}")
    print("RESULT:", "FAIL (drift)" if report.drift else "OK (no drift for implemented paths)")
    return report.exit_code


if __name__ == "__main__":
    sys.exit(main())
