from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
from pip._vendor.packaging.requirements import Requirement
from pip._vendor.packaging.utils import canonicalize_name
from pip._vendor.packaging.version import Version


ROOT = Path(__file__).resolve().parents[1]
RELEASE_METADATA_PATH = ROOT / "packaging" / "release_metadata.py"
_SPEC = importlib.util.spec_from_file_location("refra_release_metadata", RELEASE_METADATA_PATH)
assert _SPEC is not None and _SPEC.loader is not None
release_metadata = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(release_metadata)


def _copy_release_inputs(tmp_path: Path) -> Path:
    fixture_root = tmp_path / "project"
    for relative in (
        "pyproject.toml",
        "packaging/requirements-core.txt",
        "packaging/ocr_wheel_manifest.json",
        "src/game_screen_translator/_version.py",
    ):
        target = fixture_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)
    return fixture_root


def _core_pin(root: Path, name: str) -> Requirement:
    for requirement in release_metadata.load_core_requirements(root):
        if canonicalize_name(requirement.name) == canonicalize_name(name):
            return requirement
    raise AssertionError(f"No fixed core requirement for {name}")


def _set_core_pin(root: Path, name: str, version: str) -> None:
    path = root / "packaging" / "requirements-core.txt"
    lines = path.read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(lines):
        raw = line.split("#", 1)[0].strip()
        if not raw:
            continue
        requirement = Requirement(raw)
        if canonicalize_name(requirement.name) != canonicalize_name(name):
            continue
        extras = f"[{','.join(sorted(requirement.extras))}]" if requirement.extras else ""
        lines[index] = f"{requirement.name}{extras}=={version}"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return
    raise AssertionError(f"No fixed core requirement for {name}")


def _bump_version(version: str) -> str:
    release = list(Version(version).release)
    while len(release) < 3:
        release.append(0)
    release[-1] += 1
    return ".".join(str(part) for part in release)


def _project_requirement(root: Path, extra: str, name: str) -> Requirement:
    with (root / "pyproject.toml").open("rb") as handle:
        project = tomllib.load(handle)["project"]
    raw_requirements = (
        project.get("dependencies", [])
        if not extra
        else project.get("optional-dependencies", {}).get(extra, [])
    )
    for raw in raw_requirements:
        requirement = Requirement(raw)
        if canonicalize_name(requirement.name) == canonicalize_name(name):
            return requirement
    raise AssertionError(f"No project requirement for {name} in {extra or 'dependencies'}")


def test_release_metadata_is_consistent_offline() -> None:
    summary = release_metadata.check_release_metadata(ROOT)
    manifest = release_metadata.validate_ocr_manifest(
        ROOT / "packaging" / "ocr_wheel_manifest.json",
        ROOT,
    )

    assert summary["version"] == release_metadata.read_version(ROOT)
    assert summary["core_pin_count"] == len(release_metadata.load_core_requirements(ROOT))
    assert summary["ocr_wheel_count"] == len(manifest["wheels"])
    assert summary["ocr_download_bytes"] == sum(
        int(item["size_bytes"]) for item in manifest["wheels"]
    )


def test_missing_project_pin_is_rejected(tmp_path: Path) -> None:
    fixture_root = _copy_release_inputs(tmp_path)
    core = fixture_root / "packaging" / "requirements-core.txt"
    core.write_text(
        "\n".join(
            line for line in core.read_text(encoding="utf-8").splitlines()
            if not line.startswith("httpx==")
        ) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(release_metadata.ReleaseMetadataError, match="missing project dependency httpx"):
        release_metadata.check_release_metadata(fixture_root)


def test_duplicate_fixed_pin_is_rejected(tmp_path: Path) -> None:
    fixture_root = _copy_release_inputs(tmp_path)
    core = fixture_root / "packaging" / "requirements-core.txt"
    duplicate = next(
        line for line in core.read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#")
    )
    core.write_text(core.read_text(encoding="utf-8") + duplicate + "\n", encoding="utf-8")

    with pytest.raises(release_metadata.ReleaseMetadataError, match="Duplicate fixed core dependency"):
        release_metadata.check_release_metadata(fixture_root)


def test_fixed_pin_outside_development_range_is_rejected(tmp_path: Path) -> None:
    fixture_root = _copy_release_inputs(tmp_path)
    pin = _core_pin(fixture_root, "httpx")
    development = _project_requirement(fixture_root, "", "httpx")
    major = Version(next(iter(pin.specifier)).version).release[0] + 1
    candidate = f"{major}.0.0"
    while development.specifier.contains(candidate, prereleases=True):
        major += 1
        candidate = f"{major}.0.0"
    _set_core_pin(fixture_root, "httpx", candidate)

    with pytest.raises(release_metadata.ReleaseMetadataError, match="outside pyproject range"):
        release_metadata.check_release_metadata(fixture_root)


def test_inconsistent_ocr_root_wheel_is_rejected(tmp_path: Path) -> None:
    fixture_root = _copy_release_inputs(tmp_path)
    manifest_path = fixture_root / "packaging" / "ocr_wheel_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    paddle = next(item for item in manifest["wheels"] if item["name"] == "paddlepaddle-gpu")
    previous_version = paddle["version"]
    paddle["version"] = _bump_version(previous_version)
    paddle["url"] = paddle["url"].replace(
        f"paddlepaddle_gpu-{previous_version}",
        f"paddlepaddle_gpu-{paddle['version']}",
    )
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    expected = next(
        req for req in manifest["requirements"]
        if canonicalize_name(Requirement(req).name) == "paddlepaddle-gpu"
    )
    expected_version = next(iter(Requirement(expected).specifier)).version
    with pytest.raises(release_metadata.ReleaseMetadataError, match=f"expected {expected_version}"):
        release_metadata.check_release_metadata(fixture_root)


def test_core_and_ocr_shared_package_versions_must_match(tmp_path: Path) -> None:
    fixture_root = _copy_release_inputs(tmp_path)
    manifest_path = fixture_root / "packaging" / "ocr_wheel_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    numpy_wheel = next(item for item in manifest["wheels"] if item["name"] == "numpy")
    previous_version = numpy_wheel["version"]
    numpy_wheel["version"] = _bump_version(previous_version)
    numpy_wheel["url"] = numpy_wheel["url"].replace(
        f"numpy-{previous_version}",
        f"numpy-{numpy_wheel['version']}",
    )
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(release_metadata.ReleaseMetadataError, match="Core/OCR version conflict for numpy"):
        release_metadata.check_release_metadata(fixture_root)


def test_project_markers_use_the_windows_amd64_cpython_313_target(tmp_path: Path) -> None:
    fixture_root = _copy_release_inputs(tmp_path)
    pyproject_path = fixture_root / "pyproject.toml"
    pyproject = pyproject_path.read_text(encoding="utf-8")
    pyproject = pyproject.replace(
        '  "dxcam[winrt]>=0.3,<0.4",',
        '  "dxcam[winrt]>=0.3,<0.4",\n'
        '  \'WindowsOnly>=1; sys_platform == "win32" and platform_machine == "AMD64" and python_version == "3.13"\',\n'
        '  \'LinuxOnly>=1; sys_platform == "linux"\',',
    )
    pyproject = pyproject.replace(
        '  "paddlex[ocr-core]>=3.7.2,<3.8",',
        '  "paddlex[ocr-core]>=3.7.2,<3.8",\n'
        '  \'LinuxOCROnly>=1; sys_platform == "linux"\',',
    )
    pyproject_path.write_text(pyproject, encoding="utf-8")
    core_path = fixture_root / "packaging" / "requirements-core.txt"
    core_path.write_text(
        core_path.read_text(encoding="utf-8") + "WindowsOnly==1.0\n",
        encoding="utf-8",
    )

    summary = release_metadata.check_release_metadata(fixture_root)

    assert summary["core_pin_count"] == len(release_metadata.load_core_requirements(fixture_root))


@pytest.mark.parametrize(
    "filename",
    [
        "numpy-{version}-cp313-cp313-manylinux_2_17_x86_64.whl",
        "numpy-{version}-cp312-cp312-win_amd64.whl",
    ],
    ids=["linux-wheel", "wrong-cpython"],
)
def test_manifest_rejects_wheels_outside_the_target_tags(
    tmp_path: Path,
    filename: str,
) -> None:
    fixture_root = _copy_release_inputs(tmp_path)
    manifest_path = fixture_root / "packaging" / "ocr_wheel_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    numpy_wheel = next(item for item in manifest["wheels"] if item["name"] == "numpy")
    numpy_wheel["url"] = f"https://example.invalid/{filename.format(version=numpy_wheel['version'])}"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(release_metadata.ReleaseMetadataError, match="not compatible with Windows x64 CPython 3.13"):
        release_metadata.validate_ocr_manifest(manifest_path, fixture_root)


def test_manifest_accepts_py3_any_and_cpython313_windows_wheels(tmp_path: Path) -> None:
    fixture_root = _copy_release_inputs(tmp_path)
    manifest_path = fixture_root / "packaging" / "ocr_wheel_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    universal = next(item for item in manifest["wheels"] if item["name"] == "aiohappyeyeballs")
    universal["url"] = (
        "https://example.invalid/aiohappyeyeballs-"
        f"{universal['version']}-py3-none-any.whl"
    )
    native = next(item for item in manifest["wheels"] if item["name"] == "numpy")
    native["url"] = (
        f"https://example.invalid/numpy-{native['version']}-cp313-cp313-win_amd64.whl"
    )
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    validated = release_metadata.validate_ocr_manifest(manifest_path, fixture_root)

    assert len(validated["wheels"]) == len(manifest["wheels"])


def test_builder_rejects_installed_core_version_different_from_pin(
    monkeypatch,
) -> None:
    builder = _fake_builder(
        monkeypatch,
        ("httpx==0.27.0",),
        {"httpx": _FakeDistribution("httpx", "0.28.1")},
    )

    with pytest.raises(builder.BuildError, match="requires exactly 0.27.0"):
        builder._resolve_core_distributions()


def test_builder_rejects_a_missing_transitive_pin(monkeypatch) -> None:
    builder = _fake_builder(
        monkeypatch,
        ("httpx==0.28.1",),
        {
            "httpx": _FakeDistribution("httpx", "0.28.1", requires=("anyio>=3.0",)),
        },
    )

    with pytest.raises(builder.BuildError, match="missing dependency anyio"):
        builder._resolve_core_distributions()


class _FakeDistribution:
    def __init__(self, name: str, version: str, requires: tuple[str, ...] = ()) -> None:
        self.metadata = {"Name": name}
        self.version = version
        self.requires = list(requires)


def _fake_builder(monkeypatch, pins: tuple[str, ...], distributions: dict[str, _FakeDistribution]):
    builder = builder_module()
    monkeypatch.setattr(
        builder,
        "load_core_requirements",
        lambda _root: tuple(Requirement(pin) for pin in pins),
    )
    monkeypatch.setattr(
        builder.metadata,
        "distribution",
        lambda name: distributions[name.lower()],
    )
    return builder


def test_ocr_lock_cannot_omit_extras_required_by_development(tmp_path: Path) -> None:
    fixture_root = _copy_release_inputs(tmp_path)
    manifest_path = fixture_root / "packaging" / "ocr_wheel_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["requirements"] = [
        requirement.replace("paddlex[ocr-core]", "paddlex")
        for requirement in manifest["requirements"]
    ]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(release_metadata.ReleaseMetadataError, match="extras.*differ"):
        release_metadata.check_release_metadata(fixture_root)


@pytest.mark.skipif(os.name != "nt", reason="Windows builder validation")
def test_build_rejects_shared_pin_conflict_in_actual_candidate_before_staging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture_root = _copy_release_inputs(tmp_path)
    manifest_path = fixture_root / "packaging" / "ocr_wheel_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    wheel = next(item for item in manifest["wheels"] if item["name"].lower() == "numpy")
    old_version = wheel["version"]
    parts = list(Version(old_version).release)
    parts[-1] += 1
    wheel["version"] = ".".join(str(part) for part in parts)
    wheel["url"] = wheel["url"].replace(f"numpy-{old_version}-", f"numpy-{wheel['version']}-")
    candidate = tmp_path / "candidate.json"
    candidate.write_text(json.dumps(manifest), encoding="utf-8")
    # Its structure and platform are valid; its actual shared version is not.
    release_metadata.validate_ocr_manifest(candidate, fixture_root)
    release_metadata.check_release_metadata(fixture_root)
    embed_zip = tmp_path / "embed.zip"
    compiler = tmp_path / "ISCC.exe"
    embed_zip.write_bytes(b"")
    compiler.write_bytes(b"")
    sentinel = fixture_root / "build" / "windows-installer" / "app" / "keep.txt"
    sentinel.parent.mkdir(parents=True)
    sentinel.write_text("previous staged app", encoding="utf-8")
    builder = builder_module()
    monkeypatch.setattr(builder, "ROOT", fixture_root)
    monkeypatch.setattr(builder.sys, "version_info", (3, 13))
    monkeypatch.setattr(builder, "_resolve_core_distributions", lambda: pytest.fail("must reject before staging"))
    args = builder.argparse.Namespace(
        python_embed=embed_zip, iscc=compiler, ocr_manifest=candidate,
        output_dir=tmp_path / "dist", csc=None,
    )
    with pytest.raises(builder.BuildError, match="Core/OCR version conflict for numpy"):
        builder.build(args)
    assert sentinel.read_text(encoding="utf-8") == "previous staged app"
    assert not args.output_dir.exists()


def builder_module():
    builder_path = ROOT / "packaging" / "build_windows_installer.py"
    spec = importlib.util.spec_from_file_location("refra_test_release_builder", builder_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_setuptools_wheel_metadata_reads_changed_version_fixture(
    tmp_path: Path,
) -> None:
    fixture_root = _copy_release_inputs(tmp_path)
    package_dir = fixture_root / "src" / "game_screen_translator"
    shutil.copy2(ROOT / "src" / "game_screen_translator" / "__init__.py", package_dir)
    for relative in ("README.md", "LICENSE", "THIRD_PARTY_NOTICES.md"):
        shutil.copy2(ROOT / relative, fixture_root / relative)
    (package_dir / "_version.py").write_text('__version__ = "4.5.6"\n', encoding="utf-8")
    metadata_dir = tmp_path / "metadata"
    metadata_dir.mkdir()

    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; from setuptools import build_meta; "
            "build_meta.prepare_metadata_for_build_wheel(sys.argv[1])",
            str(metadata_dir),
        ],
        cwd=fixture_root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr

    dist_info_directories = list(metadata_dir.glob("*.dist-info"))
    assert len(dist_info_directories) == 1
    metadata_text = (dist_info_directories[0] / "METADATA").read_text(encoding="utf-8")
    assert "Version: 4.5.6\n" in metadata_text
