#!/usr/bin/env python3
"""Build a clean wheel and verify QML package-data parity.

The check intentionally deletes ignored setuptools build metadata before and
after the build. Reusing build/lib can otherwise leak QML files that no longer
exist in the source tree into release wheels.
"""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import zipfile


ROOT = Path(__file__).resolve().parents[1]
QML_DIR = ROOT / "app" / "qml_ui" / "qml"
REQUIRED_QML = {
    "Main.qml",
    "OverviewPage.qml",
    "ActivityPage.qml",
    "WorkspacesPage.qml",
    "LogsPage.qml",
    "DiagnosticsPage.qml",
    "SettingsPage.qml",
    "Theme.qml",
}
REQUIRED_PYTHON = {
    "app/qml_ui/app.py",
    "app/qml_ui/backend.py",
    "app/qml_ui/models.py",
    "app/cli/center/services.py",
}


def _clean_generated_build_state() -> None:
    shutil.rmtree(ROOT / "build", ignore_errors=True)
    for path in ROOT.glob("*.egg-info"):
        shutil.rmtree(path, ignore_errors=True)


def main() -> int:
    source_qml = sorted(path.name for path in QML_DIR.glob("*.qml"))
    missing_source_required = sorted(REQUIRED_QML - set(source_qml))
    if missing_source_required:
        print(
            json.dumps(
                {
                    "ok": False,
                    "stage": "source",
                    "missing_required_qml": missing_source_required,
                },
                indent=2,
            )
        )
        return 1

    uv = shutil.which("uv")
    if uv is None:
        print(json.dumps({"ok": False, "stage": "tooling", "error": "uv not found"}, indent=2))
        return 1

    _clean_generated_build_state()
    try:
        with tempfile.TemporaryDirectory(prefix="bqa-wheel-audit-") as temporary:
            output_dir = Path(temporary)
            build = subprocess.run(
                [uv, "build", "--wheel", "--out-dir", str(output_dir)],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            if build.returncode != 0:
                print(
                    json.dumps(
                        {
                            "ok": False,
                            "stage": "build",
                            "returncode": build.returncode,
                            "stdout": build.stdout[-4000:],
                            "stderr": build.stderr[-4000:],
                        },
                        indent=2,
                    )
                )
                return 1

            wheels = sorted(output_dir.glob("*.whl"))
            if len(wheels) != 1:
                print(
                    json.dumps(
                        {
                            "ok": False,
                            "stage": "artifact",
                            "wheel_count": len(wheels),
                        },
                        indent=2,
                    )
                )
                return 1

            wheel = wheels[0]
            with zipfile.ZipFile(wheel) as archive:
                entries = set(archive.namelist())

            wheel_qml = sorted(
                Path(name).name
                for name in entries
                if name.startswith("app/qml_ui/qml/") and name.endswith(".qml")
            )
            source_set = set(source_qml)
            wheel_set = set(wheel_qml)
            missing = sorted(source_set - wheel_set)
            stale = sorted(wheel_set - source_set)
            missing_python = sorted(REQUIRED_PYTHON - entries)
            ok = not missing and not stale and not missing_python

            print(
                json.dumps(
                    {
                        "ok": ok,
                        "source_qml_count": len(source_qml),
                        "wheel_qml_count": len(wheel_qml),
                        "missing_qml": missing,
                        "stale_qml": stale,
                        "missing_python": missing_python,
                        "wheel_name": wheel.name,
                    },
                    indent=2,
                )
            )
            return 0 if ok else 1
    finally:
        _clean_generated_build_state()


if __name__ == "__main__":
    raise SystemExit(main())
