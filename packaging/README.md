# Windows installer build

The release runtime is Windows x64 CPython 3.13.5 with the GUI/core wheels. It does not include GPU OCR wheels or translation models; the first-run dialog prepares OCR resources after the user confirms.

## Version and dependency sources

Edit `src/game_screen_translator/_version.py` to change the application version. Setuptools reads it for wheel/source metadata, and the Windows builder generates C# assembly/file/product version attributes and Inno Setup version defines from it. Use numeric `MAJOR.MINOR.PATCH`.

Development requirements remain ranges in `pyproject.toml`. Release inputs are:

- `packaging/requirements-core.txt`: the full fixed core/GUI dependency closure, including optional WinRT packages;
- `packaging/ocr_wheel_manifest.json`: fixed OCR roots and all wheel versions, URLs, SHA-256 values, download sizes and installed sizes. This official release data is tracked in Git.

Check the release inputs without installing or downloading OCR:

```powershell
& .\.venv\Scripts\python.exe .\packaging\release_metadata.py --check
```

The check rejects missing, duplicate or non-exact pins, versions outside the development ranges, inconsistent core/OCR overlap, and invalid wheel metadata. Windows/CPython 3.13 marker contexts apply regardless of the Python used to run the static check. The builder additionally checks the installed core dependency graph against every fixed pin before replacing staging files.

## Build and verify

Use a Windows x64 CPython 3.13 environment. For a fresh release environment, install `packaging/requirements-core.txt` with pip; a compatible development `.venv` also works. Supply the official CPython 3.13.5 embeddable ZIP and Inno Setup 6 compiler as local tools. The ZIP is checked against SHA-256 `7d2650fd9d1b9d002d4a315d5f354247fd6a44f30517c7ef577b08f57a0fb6d9`.

The builder compiles `windows_launcher.cs` with the Windows .NET Framework C# compiler (`%WINDIR%\Microsoft.NET\Framework64\v4.0.30319\csc.exe`, or `--csc`). The launcher resolves its own `runtime\pythonw.exe` and uses the installation root as its working directory.

```powershell
& .\.venv\Scripts\python.exe .\packaging\build_windows_installer.py `
  --iscc .\.cache\exe-build-tools\iscc\ISCC.exe `
  --python-embed .\.cache\exe-build-tools\python-3.13.5-embed-amd64.zip
& .\.venv\Scripts\python.exe .\packaging\verify_windows_install.py `
  --installer .\dist\windows-installer\RefraTranslator-Portable-Smoke.exe
```

The builder uses the tracked OCR manifest by default; `--ocr-manifest` allows a validated candidate manifest. It produces `RefraTranslator-Setup.exe` and `RefraTranslator-Portable-Smoke.exe` from the same staged application. Smoke setup omits uninstaller registration, shortcuts and automatic launch so automated installation leaves no OS integration entries. The normal setup retains those features.

Verification creates a fresh run directory under `build/windows-install-validation` (override with `--work-dir`), installs into a path containing Chinese characters and spaces, and starts the actual installed EXE with `--duration 1`. It removes development Python/Qt paths and isolates user data and temporary files. It checks installed package/version provenance, all core pins, `pip check`, the exact OCR manifest, first-run execution, a visible QML event loop, normal exit and configuration creation. It also rejects unexpected resource downloads. Timeouts terminate the owned Windows process tree. This verifies installation and GUI startup; it does not validate NVIDIA OCR computation or translation.

Each run retains installer/runtime/launcher logs and `verification-report.json`, including failures. These ignored build artifacts can be removed when no longer needed.

## Updating dependencies

Change development ranges and the fixed core pins together as needed, install the candidate fixed environment, then rerun the check/build/verification commands. Transitive core packages must also be fixed; the builder rejects any dependency absent from the list or installed at a different version.

To refresh OCR release data, use an explicit OCR-equipped development environment and a source manifest containing the intended fixed roots and Paddle GPU wheel URL/hash/size:

```powershell
& .\.venv\Scripts\python.exe .\packaging\prepare_ocr_manifest.py `
  --source-manifest .\packaging\ocr_wheel_manifest.json `
  --output .\packaging\ocr_wheel_manifest.json
& .\.venv\Scripts\python.exe .\packaging\release_metadata.py --check
```

The generator reads the installed OCR dependency graph and small PyPI JSON responses; it does not download OCR wheels. Review and commit the resulting complete manifest. Ordinary builds and CI reuse the tracked release manifest, avoiding GPU dependency downloads merely to package the application.

## CI

`.github/workflows/ci.yml` checks release metadata in the existing Python test matrix. A separate Windows installer job installs the exact core pins, downloads checksum-verified CPython 3.13.5 and [Inno Setup 6.7.3](https://jrsoftware.org/isdl.php) build tools, builds both EXEs and runs isolated installation verification. It uploads the build report, verification report and diagnostic logs even on failure. The job requires network access for the fixed core dependencies and build tools, but does not install/download the approximately 3.23 GB OCR wheel set.

`MANIFEST.in` includes all official packaging sources and release inputs. Private tools and experiments under `.local-tools`, caches and generated build/install outputs are excluded from source packages.
