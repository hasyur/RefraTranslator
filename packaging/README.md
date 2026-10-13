# Windows installer build

Builds the Windows x64 installer from the current source tree and the project `.venv`. The staged app is a relocatable CPython 3.13.5 runtime with the GUI/core wheels; the first-run manifest pins OCR wheel URLs, download sizes, SHA-256 values and installed sizes. Manifest generation reads installed package metadata and small PyPI release JSON responses. It does not download OCR wheels.

Prepare the build environment with the existing developer install (`install.bat`) and provide the official CPython 3.13.5 embeddable ZIP and Inno Setup 6 compiler as local build tools. The CPython ZIP is checked against SHA-256 `7d2650fd9d1b9d002d4a315d5f354247fd6a44f30517c7ef577b08f57a0fb6d9`.

The build also compiles `windows_launcher.cs` into the application-root `RefraTranslator.exe`, using the Windows .NET Framework C# compiler (`%WINDIR%\Microsoft.NET\Framework64\v4.0.30319\csc.exe` by default, or `--csc` to override it). The small GUI launcher uses the .NET Framework already included in Windows 10/11. It resolves `runtime\pythonw.exe` relative to its own location, sets the working directory to the installation root, and invokes the existing installed GUI entry point. It can be double-clicked directly; installer shortcuts and post-install launch also use this same EXE.

Generate the fixed OCR manifest, then build both installers:

```powershell
& .\.venv\Scripts\python.exe .\packaging\prepare_ocr_manifest.py --output .\.cache\exe-build-tools\ocr_wheel_manifest.json
& .\.venv\Scripts\python.exe .\packaging\build_windows_installer.py `
  --iscc .\.cache\exe-build-tools\iscc\ISCC.exe `
  --python-embed .\.cache\exe-build-tools\python-3.13.5-embed-amd64.zip `
  --ocr-manifest .\.cache\exe-build-tools\ocr_wheel_manifest.json `
  --output-dir .\dist\windows-installer
```

The normal user installer is `dist\windows-installer\RefraTranslator-Setup.exe`. The second output, `RefraTranslator-Portable-Smoke.exe`, is built without uninstaller registration, shortcuts, or automatic launch so it can be installed into an isolated test directory. Both use the same staged application under ignored `build\windows-installer\app`; build reports and generated manifests remain local build artifacts.

For an isolated installation smoke test:

```powershell
& .\dist\windows-installer\RefraTranslator-Portable-Smoke.exe /VERYSILENT /DIR="$PWD\.local-tools\output\exe-smoke-app"
$env:REFRATRANSLATOR_DATA_DIR = "$PWD\.local-tools\output\exe-smoke-data"
$env:QT_QPA_PLATFORM = "windows"
& .\.local-tools\output\exe-smoke-app\RefraTranslator.exe --duration 1
```

The data-root override isolates `config.toml`, profiles, caches and logs. The installed launcher runs the resource inventory before the normal workbench. It only begins downloads after the user confirms in the first-run window; `--duration` closes the inventory and workbench during smoke tests.

`MANIFEST.in` includes these official packaging sources and excludes `.cache`, `build`, `dist` and `.local-tools` from source packages.
