from __future__ import annotations

import argparse
import json
from collections import deque
from importlib.metadata import PackageNotFoundError, distributions, version
from typing import Any, Iterable

from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version


PROJECT_ROOTS = (
    "botquanganh-host-mcp",
    "fastmcp",
    "python-dotenv",
    "pytest",
)


def _active_requirements(raw_requirements: Iterable[str] | None) -> list[Requirement]:
    active: list[Requirement] = []
    for raw in raw_requirements or ():
        try:
            requirement = Requirement(raw)
        except InvalidRequirement:
            continue
        # Optional-extra requirements are inactive unless an extra is selected.
        if requirement.marker and not requirement.marker.evaluate({"extra": ""}):
            continue
        active.append(requirement)
    return active


def check_project_dependencies(
    roots: Iterable[str] = PROJECT_ROOTS,
) -> dict[str, Any]:
    queue = deque(canonicalize_name(name) for name in roots)
    closure: set[str] = set()
    errors: list[dict[str, str]] = []
    installed_versions: dict[str, str] = {}

    while queue:
        name = queue.popleft()
        if name in closure:
            continue
        closure.add(name)
        try:
            installed = version(name)
            from importlib.metadata import distribution

            dist = distribution(name)
        except PackageNotFoundError:
            errors.append(
                {
                    "package": name,
                    "code": "MISSING",
                    "message": f"Required project package is not installed: {name}",
                }
            )
            continue
        installed_versions[name] = installed
        for requirement in _active_requirements(dist.requires):
            dependency = canonicalize_name(requirement.name)
            try:
                dependency_version = version(dependency)
            except PackageNotFoundError:
                errors.append(
                    {
                        "package": dependency,
                        "required_by": name,
                        "code": "MISSING",
                        "message": f"{name} requires {requirement}, but it is not installed",
                    }
                )
                continue
            try:
                satisfies = not requirement.specifier or Version(
                    dependency_version
                ) in requirement.specifier
            except InvalidVersion:
                satisfies = False
            if not satisfies:
                errors.append(
                    {
                        "package": dependency,
                        "required_by": name,
                        "code": "VERSION_CONFLICT",
                        "message": (
                            f"{name} requires {requirement}, but {dependency_version} "
                            "is installed"
                        ),
                    }
                )
            queue.append(dependency)

    all_installed = {
        canonicalize_name(dist.metadata["Name"])
        for dist in distributions()
        if dist.metadata.get("Name")
    }
    foreign = sorted(all_installed - closure)
    return {
        "ok": not errors,
        "roots": list(roots),
        "closure_count": len(closure),
        "closure": sorted(closure),
        "installed_versions": dict(sorted(installed_versions.items())),
        "errors": errors,
        "foreign_package_count": len(foreign),
        "foreign_packages": foreign,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate the installed dependency closure used by this project"
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--strict-foreign",
        action="store_true",
        help="Also fail when unrelated packages are installed in the virtualenv",
    )
    args = parser.parse_args(argv)
    result = check_project_dependencies()
    ok = result["ok"] and not (
        args.strict_foreign and result["foreign_package_count"] > 0
    )
    result["ok"] = ok
    result["strict_foreign"] = args.strict_foreign
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        for error in result["errors"]:
            print(f"FAIL: {error['message']}")
        print(f"Project dependency closure: {result['closure_count']} packages")
        print(f"Unrelated packages in virtualenv: {result['foreign_package_count']}")
        print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
