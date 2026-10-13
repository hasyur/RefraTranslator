"""Build the relocatable Windows runtime and Inno Setup installers."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import zipfile
from collections import deque
from importlib import metadata
from pathlib import Path, PurePosixPath

from pip._vendor.packaging.requirements import Requirement
from pip._vendor.packaging.utils import canonicalize_name

sys.path.insert(0, str(Path(__file__).resolve().parent))
from release_metadata import (
    ReleaseMetadataError,
    check_release_metadata,
    load_core_requirements,
    read_version,
    windows_file_version,
)


ROOT = Path(__file__).resolve().parents[1]
PYTHON_EMBED_SHA256 = "7d2650fd9d1b9d002d4a315d5f354247fd6a44f30517c7ef577b08f57a0fb6d9"


class BuildError(RuntimeError):
    pass


def _installed_distribution(requirement: Requirement) -> metadata.Distribution:
    try:
        distribution = metadata.distribution(requirement.name)
    except metadata.PackageNotFoundError as exc:
        raise BuildError(
            f"Build environment is missing {requirement.name}; use the project .venv"
        ) from exc
    exact_pins = tuple(requirement.specifier)
    expected = (
        exact_pins[0].version
        if len(exact_pins) == 1 and exact_pins[0].operator == "=="
        else None
    )
    if expected is not None and distribution.version != expected:
        raise BuildError(
            f"Build environment has {requirement.name} {distribution.version}, "
            f"but the release requires exactly {expected}"
        )
    if requirement.specifier and not requirement.specifier.contains(distribution.version, prereleases=True):
        raise BuildError(
            f"Build environment has {requirement.name} {distribution.version}, "
            f"outside {requirement.specifier}"
        )
    return distribution


def _resolve_core_distributions() -> tuple[metadata.Distribution, ...]:
    try:
        locked_requirements = load_core_requirements(ROOT)
    except ReleaseMetadataError as exc:
        raise BuildError(str(exc)) from exc
    locked_by_name = {
        canonicalize_name(requirement.name): requirement
        for requirement in locked_requirements
    }
    pending: deque[Requirement] = deque(locked_requirements)
    distributions: dict[str, metadata.Distribution] = {}
    active_extras: dict[str, set[str]] = {}
    processed_extras: dict[str, set[str]] = {}
    while pending:
        dependency = pending.popleft()
        name = canonicalize_name(dependency.name)
        requirement = locked_by_name.get(name)
        if requirement is None:
            raise BuildError(
                f"Fixed core requirements are missing dependency {dependency}"
            )
        locked_version = next(iter(requirement.specifier)).version
        if dependency.specifier and not dependency.specifier.contains(
            locked_version,
            prereleases=True,
        ):
            raise BuildError(
                f"Locked {requirement.name}=={locked_version} is outside "
                f"the dependency range {dependency.specifier}"
            )
        distribution = _installed_distribution(requirement)
        distributions[name] = distribution
        extras = set(requirement.extras) | set(dependency.extras)
        known_extras = active_extras.setdefault(name, set())
        new_extras = extras - known_extras
        known_extras.update(extras)
        if name in processed_extras and not new_extras:
            continue
        processed_extras[name] = processed_extras.get(name, set()) | new_extras
        contexts = {"", *known_extras}
        for raw_dependency in distribution.requires or ():
            dependency = Requirement(raw_dependency)
            if dependency.marker and not any(
                dependency.marker.evaluate({"extra": extra})
                for extra in contexts
            ):
                continue
            pending.append(dependency)
    if distributions.keys() != locked_by_name.keys():
        unused = sorted(locked_by_name.keys() - distributions.keys())
        raise BuildError(
            "Fixed core requirements contain entries outside the active runtime closure: "
            + ", ".join(unused)
        )
    return tuple(
        distributions[name] for name in sorted(distributions)
    )


def _copy_distribution(
    distribution: metadata.Distribution,
    site_packages: Path,
    app_site_packages: Path,
) -> tuple[int, list[Path]]:
    site_root = site_packages.resolve()
    copied_bytes = 0
    copied_files: list[Path] = []
    for record in distribution.files or ():
        source = Path(distribution.locate_file(record))
        try:
            relative = source.resolve().relative_to(site_root)
        except (OSError, ValueError):
            # Console scripts and entry-point launchers live under .venv/Scripts.
            continue
        if not source.is_file():
            continue
        target = app_site_packages / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied_bytes += target.stat().st_size
        copied_files.append(target)
    if not copied_files:
        raise BuildError(
            f"No files were copied for {distribution.metadata['Name']} {distribution.version}"
        )
    return copied_bytes, copied_files


def _copy_license_files(
    distribution: metadata.Distribution,
    license_root: Path,
    site_packages: Path,
) -> None:
    dist_name = str(distribution.metadata["Name"])
    safe_name = "".join(character if character.isalnum() or character in "._-" else "_" for character in dist_name)
    target_root = license_root / f"{safe_name}-{distribution.version}"
    declared = distribution.metadata.get_all("License-File") or []
    entries = list(distribution.files or ())
    selected = []
    if declared:
        wanted = {str(item).replace("\\", "/").casefold() for item in declared}
        selected = [
            item
            for item in entries
            if str(item).replace("\\", "/").casefold() in wanted
        ]
    if not selected:
        selected = [
            item
            for item in entries
            if Path(str(item)).name.casefold().startswith(
                ("license", "licence", "copying", "notice", "copyright")
            )
            and Path(str(item)).suffix.casefold() in {"", ".txt", ".md", ".rst", ".html"}
        ]
    site_root = site_packages.resolve()
    for record in selected:
        source = Path(distribution.locate_file(record))
        try:
            relative = source.resolve().relative_to(site_root)
        except (OSError, ValueError):
            continue
        if source.is_file():
            target = target_root / relative.name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _remove_staging(path: Path) -> None:
    resolved = path.resolve()
    allowed_root = (ROOT / "build" / "windows-installer").resolve()
    if resolved == allowed_root or allowed_root not in resolved.parents:
        raise BuildError(f"Refusing to remove staging outside {allowed_root}: {resolved}")
    if resolved.exists():
        shutil.rmtree(resolved)


def _extract_embedded_python(archive: Path, destination: Path) -> None:
    if _sha256(archive) != PYTHON_EMBED_SHA256:
        raise BuildError("The CPython embeddable ZIP SHA-256 does not match the verified official archive")
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as package:
        for item in package.infolist():
            relative = PurePosixPath(item.filename)
            if relative.is_absolute() or ".." in relative.parts:
                raise BuildError(f"Unsafe CPython archive path: {item.filename}")
            if item.is_dir():
                (destination / Path(*relative.parts)).mkdir(parents=True, exist_ok=True)
                continue
            target = destination / Path(*relative.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with package.open(item) as source, target.open("wb") as output:
                shutil.copyfileobj(source, output)
    license_file = destination / "LICENSE.txt"
    if not license_file.is_file():
        raise BuildError("The official CPython archive did not contain LICENSE.txt")
    pth = destination / "python313._pth"
    pth.write_text(
        "python313.zip\n.\nLib/site-packages\nimport site\n",
        encoding="ascii",
        newline="\n",
    )


def _copy_application(
    app_root: Path,
    *,
    python_embed: Path,
    ocr_manifest: Path,
    core_distributions: tuple[metadata.Distribution, ...] | None = None,
) -> dict[str, object]:
    runtime = app_root / "runtime"
    app_site_packages = runtime / "Lib" / "site-packages"
    _extract_embedded_python(python_embed, runtime)
    app_site_packages.mkdir(parents=True, exist_ok=True)

    site_packages = Path(sysconfig_path()).resolve()
    distributions = (
        _resolve_core_distributions()
        if core_distributions is None
        else core_distributions
    )
    copied: list[dict[str, object]] = []
    license_root = app_root / "THIRD_PARTY_LICENSES"
    license_root.mkdir(parents=True, exist_ok=True)
    shutil.copy2(
        ROOT / "packaging" / "ChineseSimplified.LICENSE",
        license_root / "InnoSetup-ChineseSimplified.LICENSE",
    )
    for distribution in distributions:
        size, _files = _copy_distribution(
            distribution,
            site_packages,
            app_site_packages,
        )
        _copy_license_files(distribution, license_root, site_packages)
        copied.append(
            {
                "name": distribution.metadata["Name"],
                "version": distribution.version,
                "installed_bytes": size,
            }
        )

    source_package = ROOT / "src" / "game_screen_translator"
    shutil.copytree(
        source_package,
        app_site_packages / "game_screen_translator",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    shutil.copy2(ROOT / "config.example.toml", app_root / "config.example.toml")
    shutil.copy2(ROOT / "LICENSE", app_root / "LICENSE")
    shutil.copy2(ROOT / "THIRD_PARTY_NOTICES.md", app_root / "THIRD_PARTY_NOTICES.md")
    manifest_target = app_site_packages / "game_screen_translator" / "ocr_wheel_manifest.json"
    manifest_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ocr_manifest, manifest_target)

    payload = json.loads(manifest_target.read_text(encoding="utf-8"))
    if payload.get("platform") != "win_amd64" or not payload.get("wheels"):
        raise BuildError("OCR manifest must contain fixed win_amd64 resources")
    wheel_count = len(payload["wheels"])
    if any(int(item.get("installed_size_bytes", 0)) <= 0 for item in payload["wheels"]):
        raise BuildError("OCR manifest is missing installed_size_bytes; regenerate it with prepare_ocr_manifest.py")

    metadata_path = app_root / "BUILD-INFO.txt"
    metadata_path.write_text(
        "RefraTranslator Windows x64\n"
        f"Application version: {read_version(ROOT)}\n"
        f"Embedded CPython: {sys.version.split()[0]}\n"
        f"OCR fixed wheel resources: {wheel_count}\n",
        encoding="utf-8",
    )
    return {
        "core_distributions": copied,
        "ocr_wheel_count": wheel_count,
        "ocr_download_bytes": sum(int(item["size_bytes"]) for item in payload["wheels"]),
        "ocr_installed_bytes": sum(int(item["installed_size_bytes"]) for item in payload["wheels"]),
    }


def sysconfig_path() -> str:
    import sysconfig

    return sysconfig.get_paths()["purelib"]


def _render_launcher_source(root: Path = ROOT) -> str:
    template_path = root / "packaging" / "windows_launcher.cs"
    source = template_path.read_text(encoding="utf-8")
    version = read_version(root)
    file_version = windows_file_version(version)
    source = source.replace("@@ASSEMBLY_VERSION@@", file_version)
    source = source.replace("@@FILE_VERSION@@", file_version)
    source = source.replace("@@INFORMATIONAL_VERSION@@", version)
    if "@@" in source:
        raise BuildError("The C# launcher template contains an unresolved version placeholder")
    return source


def _build_launcher(app_root: Path, compiler: Path | None = None) -> Path:
    if compiler is None:
        windows_root = Path(os.environ.get("WINDIR", r"C:\Windows"))
        compiler = windows_root / "Microsoft.NET" / "Framework64" / "v4.0.30319" / "csc.exe"
    compiler = compiler.expanduser().resolve()
    if not compiler.is_file():
        raise BuildError(f"Windows .NET Framework C# compiler not found: {compiler}; use --csc")
    app_root.mkdir(parents=True, exist_ok=True)
    output = app_root / "RefraTranslator.exe"
    source_path = app_root.parent / "RefraTranslatorLauncher.versioned.cs"
    try:
        source_path.write_text(_render_launcher_source(), encoding="utf-8", newline="\n")
    except (OSError, ReleaseMetadataError) as exc:
        raise BuildError(f"Could not prepare the versioned C# launcher source: {exc}") from exc
    command = [
        str(compiler),
        "/nologo",
        "/target:winexe",
        "/platform:x64",
        "/optimize+",
        "/codepage:65001",
        f"/out:{output}",
        str(source_path),
    ]
    try:
        result = subprocess.run(
            command,
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError as exc:
        raise BuildError(f"Could not run C# compiler {compiler}: {exc}") from exc
    finally:
        source_path.unlink(missing_ok=True)
    if result.returncode != 0:
        raise BuildError("Application launcher compilation failed:\n" + result.stdout + result.stderr)
    if not output.is_file():
        raise BuildError(f"C# compiler did not create {output}")
    return output


def _run_inno(
    compiler: Path,
    app_root: Path,
    output_dir: Path,
    *,
    portable: bool,
) -> Path:
    filename = (
        "RefraTranslator-Portable-Smoke"
        if portable
        else "RefraTranslator-Setup"
    )
    command = [
        str(compiler),
        f"/DAppVersion={read_version(ROOT)}",
        f"/DWindowsVersion={windows_file_version(read_version(ROOT))}",
        f"/DAppSourceDir={app_root.as_posix()}",
        f"/DPortableBuild={1 if portable else 0}",
        f"/O{output_dir.as_posix()}",
        f"/F{filename}",
        str(ROOT / "packaging" / "windows_installer.iss"),
    ]
    try:
        result = subprocess.run(
            command,
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError as exc:
        raise BuildError(f"Could not run Inno Setup compiler {compiler}: {exc}") from exc
    if result.returncode != 0:
        raise BuildError(
            "Inno Setup compilation failed:\n"
            + result.stdout
            + result.stderr
        )
    output = output_dir / f"{filename}.exe"
    if not output.is_file():
        raise BuildError(f"Inno Setup did not create {output}")
    return output


def build(args: argparse.Namespace) -> dict[str, object]:
    if os.name != "nt" or sys.version_info[:2] != (3, 13) or sys.maxsize <= 2**32:
        raise BuildError("Run this script with the project 64-bit Windows CPython 3.13 environment")
    embed_zip = args.python_embed.expanduser().resolve()
    compiler = args.iscc.expanduser().resolve()
    if not embed_zip.is_file():
        raise BuildError(f"CPython embeddable archive not found: {embed_zip}")
    if not compiler.is_file():
        raise BuildError(f"Inno Setup compiler not found: {compiler}")
    manifest = args.ocr_manifest.expanduser().resolve()
    stage_root = ROOT / "build" / "windows-installer"
    app_root = stage_root / "app"
    output_dir = args.output_dir.expanduser().resolve()
    if not manifest.is_file():
        raise BuildError(f"Fixed OCR wheel manifest not found: {manifest}")
    try:
        check_release_metadata(ROOT, ocr_manifest=manifest)
    except (ReleaseMetadataError, OSError, ValueError, TypeError, KeyError) as exc:
        raise BuildError(str(exc)) from exc
    # Validate every installed version before clearing or copying the staged payload.
    core_distributions = _resolve_core_distributions()
    _remove_staging(app_root)
    stage_root.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    summary = _copy_application(
        app_root,
        python_embed=embed_zip,
        ocr_manifest=manifest,
        core_distributions=core_distributions,
    )
    launcher = _build_launcher(app_root, args.csc)

    runtime_python = app_root / "runtime" / "python.exe"
    probe = subprocess.run(
        [
            str(runtime_python),
            "-c",
            "import httpx, numpy, PIL, PySide6; "
            "from PySide6.QtWidgets import QApplication; "
            "import game_screen_translator.gui.qml_workbench; "
            "print(PySide6.__version__, numpy.__version__)",
        ],
        cwd=app_root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if probe.returncode != 0:
        raise BuildError(
            "The staged embedded runtime failed its GUI import probe:\n"
            + probe.stdout
            + probe.stderr
        )

    setup = _run_inno(compiler, app_root, output_dir, portable=False)
    smoke = _run_inno(compiler, app_root, output_dir, portable=True)
    summary.update(
        {
            "setup": str(setup),
            "portable_smoke_setup": str(smoke),
            "embedded_runtime": str(runtime_python),
            "embedded_runtime_probe": probe.stdout.strip(),
            "application_launcher": str(launcher),
        }
    )
    report = stage_root / "build-report.json"
    report.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iscc", required=True, type=Path)
    parser.add_argument("--python-embed", required=True, type=Path)
    parser.add_argument(
        "--csc",
        type=Path,
        help="C# compiler override; defaults to the Windows .NET Framework compiler",
    )
    parser.add_argument(
        "--ocr-manifest",
        type=Path,
        default=ROOT / "packaging" / "ocr_wheel_manifest.json",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "dist" / "windows-installer",
    )
    args = parser.parse_args()
    try:
        summary = build(args)
    except (BuildError, OSError, ValueError, zipfile.BadZipFile) as exc:
        parser.error(str(exc))
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
