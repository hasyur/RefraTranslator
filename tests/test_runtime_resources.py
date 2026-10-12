from __future__ import annotations

import base64
import csv
import hashlib
import importlib
import importlib.metadata
import io
import json
import os
import queue
import subprocess
import sys
import threading
import time
import venv
import zipfile
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from game_screen_translator import runtime_resources as resources


def _write_config(directory: Path) -> Path:
    source = Path(__file__).resolve().parents[1] / "config.example.toml"
    target = directory / "config.toml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(source.read_bytes())
    return target


def _write_manifest(path: Path, *, content: bytes = b"wheel-data") -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "python": "3.13",
                "platform": "win_amd64",
                "wheels": [
                    {
                        "name": "refra-test-wheel",
                        "version": "1.0",
                        "url": "https://example.invalid/refra_test_wheel-1.0-py3-none-any.whl",
                        "sha256": hashlib.sha256(content).hexdigest(),
                        "size_bytes": len(content),
                        "installed_size_bytes": len(content) * 2,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def _make_tiny_wheel(config_path: Path) -> resources.WheelResource:
    name = "refra-retry-probe"
    version = "1.0"
    normalized_name = "refra_retry_probe"
    dist_info = f"{normalized_name}-{version}.dist-info"
    files = {
        f"{dist_info}/METADATA": (
            "Metadata-Version: 2.1\nName: refra-retry-probe\nVersion: 1.0\n\n"
        ).encode(),
        f"{normalized_name}/__init__.py": b"from .version import __version__\n",
        f"{normalized_name}/version.py": b'__version__ = "1.0"\n',
        f"{normalized_name}/runtime_probe.dll": b"tiny test payload, not a loadable DLL",
        f"{dist_info}/WHEEL": (
            "Wheel-Version: 1.0\nGenerator: runtime-resource-tests\n"
            "Root-Is-Purelib: true\nTag: py3-none-any\n\n"
        ).encode(),
    }
    record = io.StringIO(newline="")
    rows = csv.writer(record, lineterminator="\n")
    for filename, content in files.items():
        digest = base64.urlsafe_b64encode(hashlib.sha256(content).digest())
        rows.writerow(
            (filename, f"sha256={digest.decode().rstrip('=')}", str(len(content)))
        )
    rows.writerow((f"{dist_info}/RECORD", "", ""))
    files[f"{dist_info}/RECORD"] = record.getvalue().encode()

    filename = f"{normalized_name}-{version}-py3-none-any.whl"
    wheelhouse = resources._wheelhouse(config_path)
    wheelhouse.mkdir(parents=True, exist_ok=True)
    wheel_path = wheelhouse / filename
    with zipfile.ZipFile(wheel_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path, content in files.items():
            archive.writestr(path, content)
    digest = hashlib.sha256(wheel_path.read_bytes()).hexdigest()
    return resources.WheelResource(
        name,
        version,
        f"https://example.invalid/{filename}",
        digest,
        wheel_path.stat().st_size,
        sum(map(len, files.values())),
    )


def _private_python(tmp_path: Path) -> tuple[Path, Path]:
    environment = tmp_path / "private-python"
    venv.EnvBuilder(with_pip=True).create(environment)
    interpreter = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    site_packages = Path(
        subprocess.check_output(
            [str(interpreter), "-c", "import sysconfig; print(sysconfig.get_path('purelib'))"],
            text=True,
        ).strip()
    )
    return interpreter, site_packages


def test_inventory_uses_three_resource_groups_and_deducts_cached_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = _write_config(tmp_path)
    manifest_path = tmp_path / "manifest.json"
    _write_manifest(manifest_path)
    monkeypatch.setenv("REFRATRANSLATOR_OCR_MANIFEST_PATH", str(manifest_path))

    wheel = resources._read_wheel_manifest()[0]
    wheel_part = resources._wheel_path(config_path, wheel).with_name(
        resources._wheel_path(config_path, wheel).name + ".part"
    )
    wheel_part.parent.mkdir(parents=True, exist_ok=True)
    wheel_part.write_bytes(b"wheel")

    det_name = "PP-OCRv6_small_det"
    det_path = (
        config_path.parent
        / resources.DOWNLOAD_RELATIVE_PATH
        / f"{det_name}_infer.tar.part"
    )
    det_path.parent.mkdir(parents=True, exist_ok=True)
    det_path.write_bytes(b"det")

    inventory = resources.inspect_ocr_resources(config_path)

    assert [item.name for item in inventory.resources] == [
        "GPU OCR 运行依赖",
        "文字检测模型",
        "文字识别模型",
    ]
    assert inventory.resources[0].downloaded_bytes == 5
    assert inventory.resources[1].downloaded_bytes == 3
    assert inventory.download_size_bytes == (
        len(b"wheel-data")
        - 5
        + resources.MODEL_ARTIFACTS[det_name][1]
        - 3
        + resources.MODEL_ARTIFACTS["PP-OCRv6_small_rec"][1]
    )
    assert "PaddleOCR 3.7.0" in inventory.resources[0].detail


def test_complete_partial_download_is_hash_checked_and_reused_without_http(
    tmp_path: Path,
) -> None:
    body = b"the complete but not yet renamed artifact"
    target = tmp_path / "artifact.tar"
    partial = target.with_name(target.name + ".part")
    partial.write_bytes(body)

    def fail_if_requested(request: httpx.Request) -> httpx.Response:
        pytest.fail(f"complete partial should not request HTTP: {request!r}")

    progress: list[tuple[str, str, int, int]] = []
    with httpx.Client(transport=httpx.MockTransport(fail_if_requested)) as client:
        result = resources._download_file(
            "https://example.invalid/artifact.tar",
            target,
            len(body),
            expected_sha256=hashlib.sha256(body).hexdigest(),
            client=client,
            progress=lambda *values: progress.append(values),
            cancel=threading.Event(),
            label="artifact",
        )

    assert result == target
    assert target.read_bytes() == body
    assert not partial.exists()
    assert progress[-1] == ("ready", "artifact", len(body), len(body))


def test_bad_complete_partial_is_discarded_and_redownloaded(tmp_path: Path) -> None:
    body = b"new"
    target = tmp_path / "artifact.whl"
    target.with_name(target.name + ".part").write_bytes(b"bad")
    requests: list[httpx.Request] = []

    def serve(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, content=body)

    with httpx.Client(transport=httpx.MockTransport(serve)) as client:
        resources._download_file(
            "https://example.invalid/artifact.whl",
            target,
            len(body),
            expected_sha256=hashlib.sha256(body).hexdigest(),
            client=client,
            progress=lambda *_values: None,
            cancel=threading.Event(),
            label="artifact",
        )

    assert len(requests) == 1
    assert "Range" not in requests[0].headers
    assert target.read_bytes() == body
    assert not target.with_name(target.name + ".part").exists()


def test_same_version_wheel_with_missing_record_or_payload_is_repaired(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = _write_config(tmp_path / "data")
    interpreter, site_packages = _private_python(tmp_path)
    monkeypatch.setattr(resources.sys, "executable", str(interpreter))
    monkeypatch.setattr(sys, "path", [str(site_packages), *sys.path])
    importlib.invalidate_caches()

    wheel = _make_tiny_wheel(config_path)
    commands: list[list[str]] = []
    pip_popen = resources.subprocess.Popen

    def capture_popen(command: list[str], **kwargs: object) -> subprocess.Popen[str]:
        commands.append(command)
        return pip_popen(command, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(resources.subprocess, "Popen", capture_popen)

    def install() -> None:
        resources._install_wheelhouse(
            config_path,
            (wheel,),
            all_wheels=(wheel,),
            progress=lambda *_values: None,
            cancel=threading.Event(),
        )

    install()
    assert resources._wheel_is_installed(wheel)

    distribution = importlib.metadata.distribution(wheel.name)
    record = next(
        entry for entry in distribution.files or () if entry.name == "RECORD"
    )
    Path(distribution.locate_file(record)).unlink()
    assert not resources._wheel_is_installed(wheel)
    assert resources._pending_wheels((wheel,)) == (wheel,)
    install()
    assert resources._wheel_is_installed(wheel)

    probe_dll = site_packages / "refra_retry_probe" / "runtime_probe.dll"
    probe_dll.unlink()
    assert not resources._wheel_is_installed(wheel)
    assert resources._pending_wheels((wheel,)) == (wheel,)
    install()

    expected_dll = b"tiny test payload, not a loadable DLL"
    probe_dll.write_bytes(expected_dll[:8])
    assert probe_dll.is_file()
    assert not resources._wheel_is_installed(wheel)
    assert resources._pending_wheels((wheel,)) == (wheel,)
    install()

    importlib.invalidate_caches()
    sys.modules.pop("refra_retry_probe", None)
    probe = importlib.import_module("refra_retry_probe")
    assert probe.__version__ == "1.0"
    assert probe_dll.is_file()
    assert probe_dll.read_bytes() == expected_dll
    assert resources._wheel_is_installed(wheel)
    assert sum("--ignore-installed" in command for command in commands) == 3


def test_interrupted_real_wheel_install_is_repaired_on_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = _write_config(tmp_path / "data")
    interpreter, site_packages = _private_python(tmp_path)
    monkeypatch.setattr(resources.sys, "executable", str(interpreter))
    monkeypatch.setattr(sys, "path", [str(site_packages), *sys.path])
    importlib.invalidate_caches()
    wheel = _make_tiny_wheel(config_path)

    hook_dir = tmp_path / "pip-hook"
    hook_dir.mkdir()
    marker = tmp_path / "metadata-written.marker"
    (hook_dir / "sitecustomize.py").write_text(
        "import os\n"
        "import time\n"
        "from pathlib import Path\n"
        "from pip._internal.operations.install.wheel import ZipBackedFile\n"
        "_save = ZipBackedFile.save\n"
        "def _pause_after_metadata(self):\n"
        "    _save(self)\n"
        "    if Path(self.dest_path).name == 'METADATA':\n"
        f"        Path({str(marker)!r}).write_text('written')\n"
        "        time.sleep(30)\n"
        "ZipBackedFile.save = _pause_after_metadata\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("PYTHONPATH", str(hook_dir))
    cancel = threading.Event()

    def cancel_after_metadata_write() -> None:
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if marker.is_file():
                cancel.set()
                return
            time.sleep(0.02)
        cancel.set()

    canceller = threading.Thread(target=cancel_after_metadata_write, daemon=True)
    canceller.start()
    with pytest.raises(resources.OcrPreparationCancelled):
        resources._install_wheelhouse(
            config_path,
            (wheel,),
            all_wheels=(wheel,),
            progress=lambda *_values: None,
            cancel=cancel,
        )
    canceller.join(timeout=1)
    assert marker.is_file()

    dist_info = site_packages / "refra_retry_probe-1.0.dist-info"
    assert (dist_info / "METADATA").is_file()
    assert not (dist_info / "RECORD").exists()
    assert not (site_packages / "refra_retry_probe" / "version.py").exists()
    assert not resources._wheel_is_installed(wheel)
    assert resources._pending_wheels((wheel,)) == (wheel,)

    monkeypatch.delenv("PYTHONPATH")
    resources._install_wheelhouse(
        config_path,
        (wheel,),
        all_wheels=(wheel,),
        progress=lambda *_values: None,
        cancel=threading.Event(),
    )
    importlib.invalidate_caches()
    sys.modules.pop("refra_retry_probe", None)
    probe = importlib.import_module("refra_retry_probe")
    assert probe.__version__ == "1.0"
    assert (dist_info / "RECORD").is_file()
    assert (site_packages / "refra_retry_probe" / "runtime_probe.dll").is_file()
    assert resources._wheel_is_installed(wheel)


def test_quiet_pip_process_responds_to_cancellation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = _write_config(tmp_path)
    wheel = resources.WheelResource(
        "refra-test-wheel",
        "1.0",
        "https://example.invalid/refra_test_wheel-1.0-py3-none-any.whl",
        "0" * 64,
        1,
        2,
    )

    class QuietPipe:
        def __init__(self) -> None:
            self.lines: queue.Queue[str | None] = queue.Queue()

        def __iter__(self):
            while True:
                line = self.lines.get(timeout=2)
                if line is None:
                    return
                yield line

        def close(self) -> None:
            self.lines.put(None)

    class QuietProcess:
        def __init__(self) -> None:
            self.stdout = QuietPipe()
            self.return_code: int | None = None
            self.terminated = False

        def poll(self) -> int | None:
            return self.return_code

        def terminate(self) -> None:
            self.terminated = True
            self.return_code = -15
            self.stdout.close()

        def wait(self, timeout: float | None = None) -> int:
            del timeout
            return self.return_code or 0

        def kill(self) -> None:
            self.return_code = -9
            self.stdout.close()

    process = QuietProcess()
    monkeypatch.setattr(resources.subprocess, "Popen", lambda *_args, **_kwargs: process)
    cancel = threading.Event()
    threading.Timer(0.05, cancel.set).start()
    started = time.monotonic()

    with pytest.raises(resources.OcrPreparationCancelled):
        resources._install_wheelhouse(
            config_path,
            (wheel,),
            all_wheels=(wheel,),
            progress=lambda *_values: None,
            cancel=cancel,
        )

    assert process.terminated
    assert time.monotonic() - started < 2
    assert not (config_path.parent / resources.PIP_TEMP_RELATIVE_PATH).exists()


def test_disk_preflight_rejects_insufficient_space_before_download(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = _write_config(tmp_path)
    wheel = resources.WheelResource(
        "refra-test-wheel",
        "1.0",
        "https://example.invalid/refra_test_wheel-1.0-py3-none-any.whl",
        "0" * 64,
        20,
        40,
    )
    monkeypatch.setattr(resources.shutil, "disk_usage", lambda _path: SimpleNamespace(free=1))

    with pytest.raises(resources.OcrPreparationError, match="磁盘空间不足"):
        resources._check_disk_space(config_path, (wheel,), ())
