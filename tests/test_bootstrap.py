from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def installer_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    # Pytest's default per-test directory includes the long test name. On CI,
    # that plus runneradmin's temp path trips the installer's MAX_PATH guard.
    return tmp_path_factory.mktemp("bi")


# Replace only the package manager in a temporary copy. The real PowerShell
# installer, Python probe, config migration and cache cleanup still execute.
PIP_STUB = r'''
function Invoke-VenvPython {
    $arguments = @($args)
    Add-Content -LiteralPath (Join-Path $projectRoot "pip-calls.txt") -Value ($arguments -join " ")
    if ($arguments[2] -eq "download") {
        if ($env:TEST_PADDLE_SCENARIO -eq "download_failure") {
            throw "Simulated GPU download failure"
        }
        $wheelDir = $arguments[[Array]::IndexOf($arguments, "--dest") + 1]
        Set-Content -LiteralPath (Join-Path $wheelDir "paddlepaddle_gpu-3.3.1-cp313-cp313-win_amd64.whl") -Value "fixture"
    }
}
'''

# No Paddle import, actual package installation or GPU allocation is needed in
# CI. A separate smoke check can run the same probe against real hardware.
PADDLE_STUB = '''
import importlib.metadata as metadata
import os
import sys
from types import SimpleNamespace
import warnings

scenario = os.environ["TEST_PADDLE_SCENARIO"]
version = {
    "old": "3.3.0", "new": "3.4.0", "patch": "3.3.2",
    "prerelease": "3.3.2rc1",
}.get(scenario, "3.3.1")
def distribution_version(name):
    if name == "paddlepaddle-gpu" and scenario not in {"missing", "download_failure"}:
        return version
    if name == "paddlepaddle" and scenario == "cpu_conflict":
        return version
    raise metadata.PackageNotFoundError(name)
metadata.version = distribution_version

class Tensor:
    def __add__(self, other):
        if scenario == "broken_cuda":
            raise RuntimeError("CUDA computation failed")
        return self
    def numpy(self):
        return [0.0 if scenario == "wrong_result" else 2.0]

def to_tensor(data, dtype, place):
    assert data == [1.0] and dtype == "float32" and place == "gpu:0"
    if scenario == "warning":
        warnings.warn("Harmless Paddle warning")
    return Tensor()

sys.modules["paddle"] = SimpleNamespace(
    device=SimpleNamespace(
        is_compiled_with_cuda=lambda: scenario != "cpu",
        cuda=SimpleNamespace(device_count=lambda: 0 if scenario == "no_device" else 1),
    ),
    version=SimpleNamespace(cuda=lambda: "12.6" if scenario == "other_cuda" else "12.9"),
    CUDAPlace=lambda index: "gpu:" + str(index),
    to_tensor=to_tensor,
)
'''


def _run_installer(
    tmp_path: Path, scenario: str, *arguments: str,
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    powershell = shutil.which("powershell.exe")
    if powershell is None:
        pytest.skip("requires Windows PowerShell 5.1")
    script = (PROJECT_ROOT / "bootstrap.ps1").read_text(encoding="ascii")
    interpreter = sys.executable.replace("'", "''")
    script = script.replace(
        '$venvPython = Join-Path $projectRoot ".venv\\Scripts\\python.exe"',
        f"$venvPython = '{interpreter}'",
    )
    script, count = re.subn(
        r"(?ms)^function Invoke-VenvPython \{.*?^\}", lambda _: PIP_STUB.strip(), script,
    )
    assert count == 1
    fixture_script = tmp_path / "bootstrap.ps1"
    fixture_script.write_text(script, encoding="ascii")
    shutil.copy2(PROJECT_ROOT / "config.example.toml", tmp_path / "config.example.toml")
    (tmp_path / "config.toml").write_text('[ocr]\ndevice = "gpu:0"\n', encoding="ascii")
    for relative_path in (
        ".venv/keep.txt", ".cache/local-llm/models/keep.gguf",
        ".cache/paddlex/keep.txt", "profiles/game/keep.txt", "output/keep.txt",
    ):
        path = tmp_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("preserved", encoding="ascii")
    shim = tmp_path / "python-shim"
    shim.mkdir()
    (shim / "sitecustomize.py").write_text(PADDLE_STUB, encoding="ascii")
    completed = subprocess.run(
        [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
         str(fixture_script), "-WithGui", *arguments],
        env={**os.environ, "PYTHONPATH": str(shim), "TEST_PADDLE_SCENARIO": scenario},
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    calls_path = tmp_path / "pip-calls.txt"
    # Early installer failures may happen before pip runs. Return its output
    # to the assertions instead of hiding the real error with FileNotFoundError.
    calls = calls_path.read_text(encoding="ascii").splitlines() if calls_path.exists() else []
    for path in (tmp_path / ".venv/keep.txt", tmp_path / ".cache/local-llm/models/keep.gguf",
                 tmp_path / ".cache/paddlex/keep.txt", tmp_path / "profiles/game/keep.txt",
                 tmp_path / "output/keep.txt"):
        assert path.read_text(encoding="ascii") == "preserved"
    assert (tmp_path / "config.toml").read_text(encoding="ascii") == '[ocr]\ndevice = "gpu:0"\n'
    return completed, calls


@pytest.mark.parametrize("scenario", ["ready", "patch", "other_cuda", "warning"])
def test_installer_reuses_usable_paddle_without_gpu_download(
    installer_root: Path, scenario: str,
) -> None:
    completed, calls = _run_installer(installer_root, scenario)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "Reusing existing Paddle GPU and CUDA" in completed.stdout
    assert not any("download" in call or "uninstall" in call or ".whl" in call for call in calls)
    assert any("--editable" in call and "[ocr-gpu,gui]" in call for call in calls)
    assert not (installer_root / ".cache/pip").exists()


@pytest.mark.parametrize("scenario", [
    "missing", "old", "new", "prerelease", "cpu", "cpu_conflict", "no_device",
    "broken_cuda", "wrong_result",
])
def test_installer_installs_gpu_when_existing_runtime_is_not_usable(
    installer_root: Path, scenario: str,
) -> None:
    completed, calls = _run_installer(installer_root, scenario)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "Reusing existing" not in completed.stdout
    downloads = [call for call in calls if "pip download" in call]
    assert len(downloads) == 1 and "/cu129/" in downloads[0]
    uninstall = next(index for index, call in enumerate(calls) if "uninstall --yes paddlepaddle" in call)
    install = next(index for index, call in enumerate(calls) if ".whl" in call)
    editable = next(index for index, call in enumerate(calls) if "--editable" in call)
    assert uninstall < install < editable
    assert "--force-reinstall --no-deps" in calls[install]
    assert not (installer_root / ".cache/pip").exists()


@pytest.mark.parametrize("scenario,reuse", [("other_cuda", True), ("ready", False)])
def test_installer_honors_explicit_cuda_version(
    installer_root: Path, scenario: str, reuse: bool,
) -> None:
    completed, calls = _run_installer(installer_root, scenario, "-GpuCuda", "cu126")
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert ("Reusing existing" in completed.stdout) is reuse
    downloads = [call for call in calls if "pip download" in call]
    assert len(downloads) == (0 if reuse else 1)
    if downloads:
        assert "/cu126/" in downloads[0]
        assert "gpu\\cu126" in downloads[0]


def test_installer_preserves_cache_and_stops_on_gpu_download_failure(installer_root: Path) -> None:
    completed, calls = _run_installer(installer_root, "download_failure")
    assert completed.returncode != 0
    assert not any("uninstall" in call or "--editable" in call for call in calls)
    assert (installer_root / ".cache/pip/gpu/cu129").is_dir()
    assert "Isolated environment is ready" not in completed.stdout


def test_installer_rejects_long_paths_before_running_pip(installer_root: Path) -> None:
    long_root = installer_root / ("x" * 100)
    long_root.mkdir()
    completed, calls = _run_installer(long_root, "ready")
    assert completed.returncode != 0
    assert "Project path is too long" in completed.stdout + completed.stderr
    assert calls == []
    assert "Isolated environment is ready" not in completed.stdout
