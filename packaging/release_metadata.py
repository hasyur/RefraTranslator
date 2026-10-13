"""Offline consistency checks for release versions and pinned dependencies."""

from __future__ import annotations

import argparse
import ast
import json
import re
import tomllib
from pathlib import Path
from urllib.parse import urlparse

from pip._vendor.packaging.markers import default_environment
from pip._vendor.packaging.requirements import Requirement
from pip._vendor.packaging.tags import compatible_tags, cpython_tags
from pip._vendor.packaging.utils import canonicalize_name, parse_wheel_filename
from pip._vendor.packaging.version import InvalidVersion, Version


ROOT = Path(__file__).resolve().parents[1]
VERSION_FILE = Path("src/game_screen_translator/_version.py")
CORE_REQUIREMENTS_FILE = Path("packaging/requirements-core.txt")
OCR_MANIFEST_FILE = Path("packaging/ocr_wheel_manifest.json")
WINDOWS_VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")
SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")
TARGET_MARKER_ENVIRONMENT = {
    **default_environment(),
    "implementation_name": "cpython",
    "implementation_version": "3.13.5",
    "os_name": "nt",
    "platform_machine": "AMD64",
    "platform_python_implementation": "CPython",
    "platform_release": "10",
    "platform_system": "Windows",
    "platform_version": "10",
    "python_full_version": "3.13.5",
    "python_version": "3.13",
    "sys_platform": "win32",
    "extra": "",
}


class ReleaseMetadataError(ValueError):
    """Release metadata is incomplete or inconsistent."""


def read_version(root: Path = ROOT) -> str:
    path = root / VERSION_FILE
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError) as exc:
        raise ReleaseMetadataError(f"Could not read the version source {path}: {exc}") from exc
    assignments: list[ast.expr] = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "__version__"
            for target in node.targets
        ):
            assignments.append(node.value)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == "__version__":
                assignments.append(node.value)
    if len(assignments) != 1 or not isinstance(assignments[0], ast.Constant):
        raise ReleaseMetadataError(
            f"{path} must define exactly one literal __version__ string"
        )
    version = assignments[0].value
    if not isinstance(version, str):
        raise ReleaseMetadataError(f"{path} __version__ must be a string")
    try:
        parsed = Version(version)
    except InvalidVersion as exc:
        raise ReleaseMetadataError(f"Invalid project version {version!r}") from exc
    if not WINDOWS_VERSION_PATTERN.fullmatch(version) or parsed.is_prerelease or parsed.is_devrelease:
        raise ReleaseMetadataError(
            f"Project version {version!r} must use numeric MAJOR.MINOR.PATCH form for Windows metadata"
        )
    return version


def windows_file_version(version: str) -> str:
    if not WINDOWS_VERSION_PATTERN.fullmatch(version):
        raise ReleaseMetadataError(
            f"Project version {version!r} cannot be represented as a Windows file version"
        )
    return f"{version}.0"


def _read_project(root: Path) -> dict[str, object]:
    path = root / "pyproject.toml"
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ReleaseMetadataError(f"Could not read {path}: {exc}") from exc


def _parse_requirement(raw: object, context: str) -> Requirement:
    if not isinstance(raw, str):
        raise ReleaseMetadataError(f"{context} must be a requirement string")
    try:
        return Requirement(raw)
    except Exception as exc:
        raise ReleaseMetadataError(f"Invalid requirement in {context}: {raw!r}") from exc


def _requirement_is_active(requirement: Requirement, extra: str = "") -> bool:
    return requirement.marker is None or requirement.marker.evaluate(
        environment={**TARGET_MARKER_ENVIRONMENT, "extra": extra}
    )


def _target_wheel_tags() -> set:
    return set(
        cpython_tags(
            (3, 13),
            abis=["cp313"],
            platforms=["win_amd64"],
        )
    ) | set(
        compatible_tags(
            (3, 13),
            interpreter="cp313",
            platforms=["win_amd64"],
        )
    )


def _exact_version(requirement: Requirement, context: str) -> str:
    specifiers = tuple(requirement.specifier)
    if (
        requirement.url is not None
        or requirement.marker is not None
        or len(specifiers) != 1
        or specifiers[0].operator != "=="
        or "*" in specifiers[0].version
    ):
        raise ReleaseMetadataError(
            f"{context} must be a single exact == pin without a marker: {requirement}"
        )
    try:
        Version(specifiers[0].version)
    except InvalidVersion as exc:
        raise ReleaseMetadataError(f"Invalid pinned version in {context}: {requirement}") from exc
    return specifiers[0].version


def load_core_requirements(root: Path = ROOT) -> tuple[Requirement, ...]:
    path = root / CORE_REQUIREMENTS_FILE
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ReleaseMetadataError(f"Could not read the fixed core requirements {path}: {exc}") from exc
    requirements: list[Requirement] = []
    names: set[str] = set()
    for line_number, line in enumerate(lines, start=1):
        raw = line.split("#", 1)[0].strip()
        if not raw:
            continue
        context = f"{path}:{line_number}"
        requirement = _parse_requirement(raw, context)
        _exact_version(requirement, context)
        name = canonicalize_name(requirement.name)
        if name in names:
            raise ReleaseMetadataError(f"Duplicate fixed core dependency {requirement.name} in {path}")
        names.add(name)
        requirements.append(requirement)
    if not requirements:
        raise ReleaseMetadataError(f"The fixed core requirements file {path} is empty")
    return tuple(requirements)


def load_ocr_manifest(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReleaseMetadataError(f"Could not read OCR wheel manifest {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ReleaseMetadataError(f"OCR wheel manifest {path} must contain a JSON object")
    return payload


def validate_ocr_manifest(path: Path, root: Path = ROOT) -> dict[str, object]:
    payload = load_ocr_manifest(path)
    if payload.get("schema_version") != 1:
        raise ReleaseMetadataError(f"OCR manifest {path} must use schema_version 1")
    if payload.get("python") != "3.13" or payload.get("platform") != "win_amd64":
        raise ReleaseMetadataError(
            f"OCR manifest {path} must target CPython 3.13 on Windows x64"
        )

    raw_requirements = payload.get("requirements")
    if not isinstance(raw_requirements, list) or not raw_requirements:
        raise ReleaseMetadataError(f"OCR manifest {path} has no fixed root requirements")
    requirements: dict[str, tuple[Requirement, str]] = {}
    for index, raw in enumerate(raw_requirements):
        context = f"OCR manifest {path} requirements[{index}]"
        requirement = _parse_requirement(raw, context)
        version = _exact_version(requirement, context)
        name = canonicalize_name(requirement.name)
        if name in requirements:
            raise ReleaseMetadataError(f"Duplicate OCR root requirement {requirement.name}")
        requirements[name] = requirement, version

    raw_wheels = payload.get("wheels")
    if not isinstance(raw_wheels, list) or not raw_wheels:
        raise ReleaseMetadataError(f"OCR manifest {path} has no wheel records")
    supported_tags = _target_wheel_tags()
    wheels: dict[str, dict[str, object]] = {}
    for index, entry in enumerate(raw_wheels):
        context = f"OCR manifest {path} wheels[{index}]"
        if not isinstance(entry, dict):
            raise ReleaseMetadataError(f"{context} must be an object")
        raw_name = entry.get("name")
        raw_version = entry.get("version")
        url = entry.get("url")
        digest = entry.get("sha256")
        if not all(isinstance(value, str) and value for value in (raw_name, raw_version, url)):
            raise ReleaseMetadataError(f"{context} is missing its name, version or URL")
        name = canonicalize_name(raw_name)
        if name in wheels:
            raise ReleaseMetadataError(f"Duplicate OCR wheel record {raw_name}")
        if not url.startswith("https://"):
            raise ReleaseMetadataError(f"{context} URL must use HTTPS")
        if not isinstance(digest, str) or not SHA256_PATTERN.fullmatch(digest):
            raise ReleaseMetadataError(f"{context} must contain a 64-character SHA-256")
        for size_key in ("size_bytes", "installed_size_bytes"):
            size = entry.get(size_key)
            if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
                raise ReleaseMetadataError(f"{context} must contain a positive {size_key}")
        filename = Path(urlparse(url).path).name
        try:
            wheel_name, wheel_version, _build, wheel_tags = parse_wheel_filename(filename)
            declared_version = Version(raw_version)
        except Exception as exc:
            raise ReleaseMetadataError(f"{context} does not name a valid wheel file") from exc
        if canonicalize_name(wheel_name) != name or wheel_version != declared_version:
            raise ReleaseMetadataError(f"{context} wheel filename does not match its name/version")
        if not wheel_tags.intersection(supported_tags):
            raise ReleaseMetadataError(
                f"{context} wheel is not compatible with Windows x64 CPython 3.13"
            )
        wheels[name] = entry

    for name, (requirement, version) in requirements.items():
        entry = wheels.get(name)
        if entry is None:
            raise ReleaseMetadataError(
                f"OCR manifest root {requirement.name} has no matching wheel record"
            )
        if str(entry["version"]) != version:
            raise ReleaseMetadataError(
                f"OCR wheel version for {requirement.name} is {entry['version']}, expected {version}"
            )

    project = _read_project(root).get("project", {})
    optional = project.get("optional-dependencies", {}) if isinstance(project, dict) else {}
    ocr_development = optional.get("ocr-gpu", []) if isinstance(optional, dict) else []
    if not isinstance(ocr_development, list):
        raise ReleaseMetadataError("pyproject.toml project.optional-dependencies.ocr-gpu must be a list")
    development_by_name: dict[str, Requirement] = {}
    for raw in ocr_development:
        requirement = _parse_requirement(raw, "pyproject.toml ocr-gpu extra")
        if not _requirement_is_active(requirement, "ocr-gpu"):
            continue
        name = canonicalize_name(requirement.name)
        if name in development_by_name:
            raise ReleaseMetadataError(f"Duplicate active OCR development dependency {requirement.name}")
        development_by_name[name] = requirement
    if set(development_by_name) != set(requirements):
        missing = sorted(set(requirements) - set(development_by_name))
        extra = sorted(set(development_by_name) - set(requirements))
        raise ReleaseMetadataError(
            f"OCR manifest roots do not match the pyproject ocr-gpu extra (missing={missing}, extra={extra})"
        )
    for name, (pinned, version) in requirements.items():
        development = development_by_name[name]
        if not development.specifier.contains(version, prereleases=True):
            raise ReleaseMetadataError(
                f"OCR manifest pin {pinned.name}=={version} is outside pyproject range {development.specifier}"
            )
        if set(pinned.extras) != set(development.extras):
            raise ReleaseMetadataError(
                f"OCR manifest extras for {pinned.name} differ from pyproject.toml"
            )
    return payload


def check_release_metadata(
    root: Path = ROOT, *, ocr_manifest: Path | None = None,
) -> dict[str, object]:
    version = read_version(root)
    project_data = _read_project(root)
    project = project_data.get("project")
    if not isinstance(project, dict):
        raise ReleaseMetadataError("pyproject.toml must contain a [project] table")
    if "version" in project or "version" not in project.get("dynamic", []):
        raise ReleaseMetadataError(
            "pyproject.toml must obtain its dynamic version from the single _version.py source"
        )
    dynamic_version = (
        project_data.get("tool", {})
        .get("setuptools", {})
        .get("dynamic", {})
        .get("version", {})
        .get("attr")
    )
    if dynamic_version != "game_screen_translator._version.__version__":
        raise ReleaseMetadataError(
            "setuptools dynamic version must use game_screen_translator._version.__version__"
        )

    requirements = load_core_requirements(root)
    core_by_name = {canonicalize_name(req.name): req for req in requirements}
    version_by_name = {
        name: _exact_version(req, "fixed core requirements")
        for name, req in core_by_name.items()
    }
    runtime_requirements: list[Requirement] = []
    for raw in project.get("dependencies", []):
        requirement = _parse_requirement(raw, "pyproject.toml project.dependencies")
        if _requirement_is_active(requirement):
            runtime_requirements.append(requirement)
    optional = project.get("optional-dependencies", {})
    if not isinstance(optional, dict):
        raise ReleaseMetadataError("pyproject.toml optional-dependencies must be a table")
    gui_requirements = optional.get("gui", [])
    if not isinstance(gui_requirements, list):
        raise ReleaseMetadataError("pyproject.toml project.optional-dependencies.gui must be a list")
    for raw in gui_requirements:
        requirement = _parse_requirement(raw, "pyproject.toml gui extra")
        if _requirement_is_active(requirement, "gui"):
            runtime_requirements.append(requirement)
    for requirement in runtime_requirements:
        name = canonicalize_name(requirement.name)
        pinned = core_by_name.get(name)
        if pinned is None:
            raise ReleaseMetadataError(
                f"Fixed core requirements are missing project dependency {requirement.name}"
            )
        version_pin = version_by_name[name]
        if not requirement.specifier.contains(version_pin, prereleases=True):
            raise ReleaseMetadataError(
                f"Fixed core pin {requirement.name}=={version_pin} is outside pyproject range {requirement.specifier}"
            )
        if not set(requirement.extras).issubset(pinned.extras):
            raise ReleaseMetadataError(
                f"Fixed core pin {requirement.name} does not include project extras {sorted(requirement.extras)}"
            )

    manifest = validate_ocr_manifest(ocr_manifest or root / OCR_MANIFEST_FILE, root)
    ocr_wheel_versions = {
        canonicalize_name(str(entry["name"])): Version(str(entry["version"]))
        for entry in manifest["wheels"]
    }
    for name, core_version in version_by_name.items():
        ocr_version = ocr_wheel_versions.get(name)
        if ocr_version is not None and Version(core_version) != ocr_version:
            raise ReleaseMetadataError(
                f"Core/OCR version conflict for {name}: core pin {core_version}, "
                f"OCR manifest {ocr_version}"
            )
    return {
        "version": version,
        "windows_version": windows_file_version(version),
        "core_pin_count": len(requirements),
        "ocr_wheel_count": len(manifest["wheels"]),
        "ocr_download_bytes": sum(int(item["size_bytes"]) for item in manifest["wheels"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="check release metadata without network access")
    args = parser.parse_args()
    if not args.check:
        parser.error("--check is required")
    try:
        summary = check_release_metadata()
    except (ReleaseMetadataError, OSError, ValueError, KeyError, TypeError) as exc:
        parser.error(str(exc))
    print(
        "Release metadata OK: version {version} ({core_pin_count} core pins, "
        "{ocr_wheel_count} OCR wheels, {ocr_download_bytes:,} OCR bytes)".format(**summary)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
