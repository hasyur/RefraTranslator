from __future__ import annotations

import ctypes
import hashlib
import importlib.util
import json
import os
import shutil
import struct
import subprocess
import zipfile
from pathlib import Path

import pytest


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
    assert (installed_package / "gui" / "assets" / "refra-translator.ico").is_file()
    runtime_icon = installed_package / "gui" / "assets" / "refra-prism.ico"
    assert runtime_icon.is_file()
    assert runtime_icon.read_bytes() == (
        _BUILDER_PATH.parents[1]
        / "src"
        / "game_screen_translator"
        / "gui"
        / "assets"
        / "refra-prism.ico"
    ).read_bytes()
    assert (app_root / "RefraTranslator.ico").read_bytes() == (
        installed_package / "gui" / "assets" / "refra-translator.ico"
    ).read_bytes()
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
    assert '#define PreviousAppDir "no"' in script
    assert '#define PreviousAppDir "yes"' in script
    assert 'UsePreviousAppDir={#PreviousAppDir}' in script
    assert 'DisableDirPage=no' in script
    assert 'Compression=lzma2/max' in script
    assert 'Uninstallable={#InstallUninstaller}' in script
    assert 'AppVersion={#AppVersion}' in script
    assert 'VersionInfoVersion={#WindowsVersion}' in script
    assert 'SetupIconFile={#AppSourceDir}\\RefraTranslator.ico' in script
    assert 'UninstallDisplayIcon={app}\\RefraTranslator.exe' in script
    assert '[Languages]' in script
    assert 'Name: "chinesesimplified"; MessagesFile: "ChineseSimplified.isl"' in script
    language_file = (
        (_BUILDER_PATH.parent / "ChineseSimplified.isl")
        .read_text(encoding="utf-8")
    )
    assert "LanguageName=简体中文" in language_file
    assert "LanguageID=$0804" in language_file
    assert "WizardInstalling=正在安装" in language_file
    assert "ConfirmUninstall=您确认要完全移除 %1 及其所有组件吗？" in language_file
    launch_entries = [
        line for line in script.splitlines() if 'Filename: "{app}\\' in line
    ]
    assert len(launch_entries) == 3
    assert all('Filename: "{app}\\RefraTranslator.exe"' in line for line in launch_entries)
    assert all('pythonw.exe' not in line and 'Parameters:' not in line for line in launch_entries)


def test_application_staging_includes_simplified_chinese_translation_license(
    tmp_path: Path,
    monkeypatch,
) -> None:
    embed_zip = tmp_path / "python-embed.zip"
    with zipfile.ZipFile(embed_zip, "w") as archive:
        archive.writestr("LICENSE.txt", "CPython license")
        archive.writestr("python.exe", "not a real executable")
    monkeypatch.setattr(
        builder,
        "PYTHON_EMBED_SHA256",
        hashlib.sha256(embed_zip.read_bytes()).hexdigest(),
    )
    monkeypatch.setattr(builder, "_resolve_core_distributions", lambda: ())
    monkeypatch.setattr(builder, "sysconfig_path", lambda: str(tmp_path / "site-packages"))
    manifest = tmp_path / "ocr-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "platform": "win_amd64",
                "wheels": [{"size_bytes": 1, "installed_size_bytes": 1}],
            }
        ),
        encoding="utf-8",
    )
    app_root = tmp_path / "staged-app"

    builder._copy_application(app_root, python_embed=embed_zip, ocr_manifest=manifest)

    packaged_license = (
        app_root
        / "THIRD_PARTY_LICENSES"
        / "InnoSetup-ChineseSimplified.LICENSE"
    )
    assert packaged_license.read_text(encoding="utf-8").startswith("MIT License")


def test_launcher_build_reports_a_missing_compiler(tmp_path: Path) -> None:
    with pytest.raises(builder.BuildError, match="compiler not found"):
        builder._build_launcher(tmp_path / "app", tmp_path / "missing-csc.exe")


def test_launcher_compilation_embeds_the_staged_brand_icon(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app_root = tmp_path / "app"
    app_root.mkdir()
    icon = app_root / "RefraTranslator.ico"
    shutil.copy2(
        _BUILDER_PATH.parents[1]
        / "src"
        / "game_screen_translator"
        / "gui"
        / "assets"
        / "refra-translator.ico",
        icon,
    )
    compiler = tmp_path / "csc.exe"
    compiler.write_bytes(b"test compiler")
    captured: list[str] = []

    def fake_run(command, **_kwargs):
        captured.extend(command)
        output = next(argument.split(":", 1)[1] for argument in command if argument.startswith("/out:"))
        Path(output).write_bytes(b"compiled launcher")
        return type("Result", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    monkeypatch.setattr(builder.subprocess, "run", fake_run)

    launcher = builder._build_launcher(app_root, compiler)

    assert launcher.read_bytes() == b"compiled launcher"
    assert f"/win32icon:{icon.resolve()}" in captured


@pytest.mark.parametrize("icon_name", ("refra-translator.ico", "refra-prism.ico"))
def test_runtime_and_executable_icons_have_all_alpha_frames(icon_name: str) -> None:
    from PIL import Image

    icon_path = (
        _BUILDER_PATH.parents[1]
        / "src"
        / "game_screen_translator"
        / "gui"
        / "assets"
        / icon_name
    )
    expected_sizes = {
        (16, 16),
        (20, 20),
        (24, 24),
        (32, 32),
        (48, 48),
        (64, 64),
        (128, 128),
        (256, 256),
    }
    with Image.open(icon_path) as icon:
        assert set(icon.ico.sizes()) == expected_sizes
        for size in expected_sizes:
            frame = icon.ico.getimage(size).convert("RGBA")
            alpha = frame.getchannel("A")
            corners = (
                (0, 0),
                (size[0] - 1, 0),
                (0, size[1] - 1),
                (size[0] - 1, size[1] - 1),
            )
            assert max(alpha.getpixel(point) for point in corners) <= 16
            assert alpha.getextrema() == (0, 255)


def test_launcher_source_uses_the_single_project_version(tmp_path: Path) -> None:
    fixture_root = tmp_path / "project"
    packaging_dir = fixture_root / "packaging"
    version_dir = fixture_root / "src" / "game_screen_translator"
    packaging_dir.mkdir(parents=True)
    version_dir.mkdir(parents=True)
    shutil.copy2(_BUILDER_PATH.parent / "windows_launcher.cs", packaging_dir)
    (version_dir / "_version.py").write_text('__version__ = "4.5.6"\n', encoding="utf-8")

    source = builder._render_launcher_source(fixture_root)

    assert '[assembly: AssemblyVersion("4.5.6.0")]' in source
    assert '[assembly: AssemblyFileVersion("4.5.6.0")]' in source
    assert '[assembly: AssemblyInformationalVersion("4.5.6")]' in source
    assert "@@" not in source


def test_inno_compile_receives_project_and_windows_versions(
    tmp_path: Path,
    monkeypatch,
) -> None:
    fixture_root = tmp_path / "project"
    packaging_dir = fixture_root / "packaging"
    version_dir = fixture_root / "src" / "game_screen_translator"
    packaging_dir.mkdir(parents=True)
    version_dir.mkdir(parents=True)
    shutil.copy2(_BUILDER_PATH.parent / "windows_installer.iss", packaging_dir)
    (version_dir / "_version.py").write_text('__version__ = "4.5.6"\n', encoding="utf-8")
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    captured: list[str] = []

    def fake_run(command, **_kwargs):
        captured.extend(command)
        (output_dir / "RefraTranslator-Setup.exe").write_bytes(b"setup")
        return type("Result", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    monkeypatch.setattr(builder, "ROOT", fixture_root)
    monkeypatch.setattr(builder.subprocess, "run", fake_run)

    builder._run_inno(Path("fake-iscc.exe"), tmp_path / "app", output_dir, portable=False)

    assert "/DAppVersion=4.5.6" in captured
    assert "/DWindowsVersion=4.5.6.0" in captured


@pytest.fixture(scope="module")
def compiled_launcher(tmp_path_factory: pytest.TempPathFactory) -> Path:
    if os.name != "nt":
        pytest.skip("The application launcher runs on Windows")
    app_root = tmp_path_factory.mktemp("launcher") / "安装目录 with spaces"
    app_root.mkdir()
    shutil.copy2(
        _BUILDER_PATH.parents[1]
        / "src"
        / "game_screen_translator"
        / "gui"
        / "assets"
        / "refra-translator.ico",
        app_root / "RefraTranslator.ico",
    )
    launcher = builder._build_launcher(app_root)
    runtime = app_root / "runtime"
    runtime.mkdir()
    probe_source = app_root / "runtime-probe.cs"
    probe_source.write_text(
        """using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
internal static class RuntimeProbe
{
    private static int Main(string[] arguments)
    {
        List<string> lines = new List<string>();
        lines.Add(Convert.ToBase64String(Encoding.UTF8.GetBytes(Environment.CurrentDirectory)));
        foreach (string argument in arguments)
            lines.Add(Convert.ToBase64String(Encoding.UTF8.GetBytes(argument)));
        File.WriteAllLines(Environment.GetEnvironmentVariable("REFRA_TEST_RECORD"), lines);
        return Int32.Parse(Environment.GetEnvironmentVariable("REFRA_TEST_EXIT_CODE"));
    }
}
""",
        encoding="utf-8",
    )
    compiler = Path(os.environ.get("WINDIR", r"C:\Windows")) / (
        "Microsoft.NET/Framework64/v4.0.30319/csc.exe"
    )
    result = subprocess.run(
        [str(compiler), "/nologo", "/target:winexe", "/platform:x64",
         f"/out:{runtime / 'pythonw.exe'}", str(probe_source)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return launcher


@pytest.mark.parametrize(
    "arguments",
    [
        [],
        ["--duration", "0.5"],
        ["", "字幕路径 with spaces", 'quoted "value"', "C:\\trailing path\\",
         'slashes\\\\"end', "literal & %PATH%"],
    ],
)
def test_compiled_launcher_uses_its_own_runtime_and_preserves_arguments(
    compiled_launcher: Path,
    tmp_path: Path,
    arguments: list[str],
) -> None:
    import base64

    record = tmp_path / "runtime-record.txt"
    environment = os.environ.copy()
    environment.update({
        "REFRA_TEST_RECORD": str(record),
        "REFRA_TEST_EXIT_CODE": "37",
        # No Python or development environment is available through PATH.
        "PATH": str(Path(environment.get("WINDIR", r"C:\Windows")) / "System32"),
    })
    (tmp_path / "config.toml").write_text("unrelated config", encoding="utf-8")
    result = subprocess.run(
        [str(compiled_launcher), *arguments],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 37
    assert result.stdout == result.stderr == b""
    decoded = [base64.b64decode(line).decode("utf-8")
               for line in record.read_text(encoding="utf-8-sig").splitlines()]
    assert Path(decoded[0]) == compiled_launcher.parent
    assert decoded[1:] == [
        "-s", "-X", "utf8", "-m", "game_screen_translator.gui_entry", "--installed",
        *arguments,
    ]


def test_compiled_launcher_is_a_gui_executable_and_survives_relocation(
    compiled_launcher: Path,
    tmp_path: Path,
) -> None:
    payload = compiled_launcher.read_bytes()
    pe_offset = struct.unpack_from("<I", payload, 0x3C)[0]
    assert payload[pe_offset:pe_offset + 4] == b"PE\0\0"
    assert struct.unpack_from("<H", payload, pe_offset + 4)[0] == 0x8664  # AMD64
    assert struct.unpack_from("<H", payload, pe_offset + 24 + 68)[0] == 2  # Windows GUI

    relocated = tmp_path / "另一目录 relocated app"
    shutil.copytree(compiled_launcher.parent, relocated)
    test_compiled_launcher_uses_its_own_runtime_and_preserves_arguments(
        relocated / "RefraTranslator.exe", tmp_path, [],
    )


def test_compiled_launcher_contains_a_windows_icon_resource(compiled_launcher: Path) -> None:
    extractor = ctypes.windll.shell32.ExtractIconExW
    extractor.argtypes = (
        ctypes.c_wchar_p,
        ctypes.c_int,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.c_uint,
    )
    extractor.restype = ctypes.c_uint
    large = ctypes.c_void_p()
    small = ctypes.c_void_p()

    count = extractor(str(compiled_launcher), 0, ctypes.byref(large), ctypes.byref(small), 1)
    try:
        assert count >= 1
        assert large.value or small.value
    finally:
        if large.value:
            ctypes.windll.user32.DestroyIcon(large)
        if small.value:
            ctypes.windll.user32.DestroyIcon(small)

    kernel32 = ctypes.windll.kernel32
    load_data = kernel32.LoadLibraryExW
    load_data.argtypes = (ctypes.c_wchar_p, ctypes.c_void_p, ctypes.c_uint)
    load_data.restype = ctypes.c_void_p
    module = load_data(str(compiled_launcher), None, 0x00000002)
    assert module
    kernel32.FreeLibrary.argtypes = (ctypes.c_void_p,)
    kernel32.FreeLibrary.restype = ctypes.c_int
    try:
        callback_type = ctypes.WINFUNCTYPE(
            ctypes.c_int,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
        )
        group_names: list[int] = []

        @callback_type
        def remember_group(_module, _resource_type, name, _parameter):
            group_names.append(ctypes.cast(name, ctypes.c_void_p).value)
            return 1

        enumerate_names = kernel32.EnumResourceNamesW
        enumerate_names.argtypes = (
            ctypes.c_void_p,
            ctypes.c_void_p,
            callback_type,
            ctypes.c_void_p,
        )
        enumerate_names.restype = ctypes.c_int
        assert enumerate_names(module, ctypes.c_void_p(14), remember_group, None)
        resource_name = ctypes.c_void_p(group_names[0])

        find_resource = kernel32.FindResourceW
        find_resource.argtypes = (ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)
        find_resource.restype = ctypes.c_void_p
        resource = find_resource(module, resource_name, ctypes.c_void_p(14))
        assert resource
        size_of_resource = kernel32.SizeofResource
        size_of_resource.argtypes = (ctypes.c_void_p, ctypes.c_void_p)
        size_of_resource.restype = ctypes.c_uint
        size = size_of_resource(module, resource)
        load_resource = kernel32.LoadResource
        load_resource.argtypes = (ctypes.c_void_p, ctypes.c_void_p)
        load_resource.restype = ctypes.c_void_p
        lock_resource = kernel32.LockResource
        lock_resource.argtypes = (ctypes.c_void_p,)
        lock_resource.restype = ctypes.c_void_p
        payload = ctypes.string_at(lock_resource(load_resource(module, resource)), size)
        reserved, resource_type, count = struct.unpack_from("<HHH", payload)
        assert (reserved, resource_type, count) == (0, 1, 8)
        sizes = {
            (
                width or 256,
                height or 256,
            )
            for width, height in (
                struct.unpack_from("<BB", payload, 6 + index * 14)
                for index in range(count)
            )
        }
        assert sizes == {
            (16, 16),
            (20, 20),
            (24, 24),
            (32, 32),
            (48, 48),
            (64, 64),
            (128, 128),
            (256, 256),
        }
    finally:
        kernel32.FreeLibrary(module)
