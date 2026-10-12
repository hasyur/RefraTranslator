from __future__ import annotations

import hashlib
import importlib.util
import json
import zipfile
from pathlib import Path


_BUILDER_PATH = Path(__file__).resolve().parents[1] / "packaging" / "build_windows_installer.py"
_SPEC = importlib.util.spec_from_file_location("refra_build_windows_installer", _BUILDER_PATH)
assert _SPEC is not None and _SPEC.loader is not None
builder = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(builder)


def test_application_staging_uses_embedded_python_zip_and_writes_runtime_path(
    tmp_path: Path,
    monkeypatch,
) -> None:
    embed_zip = tmp_path / "python-embed.zip"
    with zipfile.ZipFile(embed_zip, "w") as archive:
        archive.writestr("LICENSE.txt", "CPython license")
        archive.writestr("python.exe", "not a real executable")
    digest = hashlib.sha256(embed_zip.read_bytes()).hexdigest()
    monkeypatch.setattr(builder, "PYTHON_EMBED_SHA256", digest)
    monkeypatch.setattr(builder, "_resolve_core_distributions", lambda: ())
    monkeypatch.setattr(builder, "sysconfig_path", lambda: str(tmp_path / "site-packages"))

    manifest = tmp_path / "ocr-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "platform": "win_amd64",
                "wheels": [
                    {
                        "name": "test-wheel",
                        "version": "1.0",
                        "url": "https://example.invalid/test_wheel-1.0-py3-none-any.whl",
                        "sha256": "0" * 64,
                        "size_bytes": 10,
                        "installed_size_bytes": 20,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    app_root = tmp_path / "staged-app"

    summary = builder._copy_application(
        app_root,
        python_embed=embed_zip,
        ocr_manifest=manifest,
    )

    runtime = app_root / "runtime"
    assert (runtime / "LICENSE.txt").read_text(encoding="utf-8") == "CPython license"
    assert (runtime / "python.exe").read_text(encoding="utf-8") == "not a real executable"
    assert (runtime / "python313._pth").read_text(encoding="ascii") == (
        "python313.zip\n.\nLib/site-packages\nimport site\n"
    )
    installed_package = runtime / "Lib" / "site-packages" / "game_screen_translator"
    assert (installed_package / "gui_entry.py").is_file()
    assert (installed_package / "ocr_wheel_manifest.json").is_file()
    assert not any(installed_package.rglob("__pycache__"))
    assert summary["ocr_wheel_count"] == 1
    assert summary["ocr_installed_bytes"] == 20


def test_inno_script_preserves_supported_windows_and_portable_smoke_modes() -> None:
    script = (_BUILDER_PATH.parent / "windows_installer.iss").read_text(encoding="utf-8")

    assert 'MinVersion=10.0' in script
    assert 'ArchitecturesAllowed=x64' in script
    assert 'ArchitecturesInstallIn64BitMode=x64' in script
    assert '#define PortableBuild "0"' in script
    assert '#if PortableBuild == "1"' in script
    assert 'Compression=lzma2/max' in script
    assert 'Uninstallable={#InstallUninstaller}' in script
