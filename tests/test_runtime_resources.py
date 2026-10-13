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
    wheel_path = resources._wheel_path(config_path, wheel)
    wheel_part = wheel_path.with_name(wheel_path.name + ".part")
    commands: list[list[str]] = []
    pip_popen = resources.subprocess.Popen

    def capture_popen(command: list[str], **kwargs: object) -> subprocess.Popen[str]:
        commands.append(command)
        return pip_popen(command, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(resources.subprocess, "Popen", capture_popen)

    def install() -> None:
        nonlocal wheel
        if not wheel_path.is_file():
            # A successful installation now purges its verified download. Rebuild
            # the tiny wheel to model a fresh retry after the installed payload is damaged.
            wheel = _make_tiny_wheel(config_path)
        wheel_part.write_bytes(b"obsolete partial download")
        resources._install_wheelhouse(
            config_path,
            (wheel,),
            all_wheels=(wheel,),
            progress=lambda *_values: None,
            cancel=threading.Event(),
        )

    install()
    assert resources._wheel_is_installed(wheel)
    assert not wheel_path.exists()
    assert not wheel_part.exists()
    assert (site_packages / "refra_retry_probe" / "runtime_probe.dll").is_file()

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
    assert not wheel_path.exists()
    assert not wheel_part.exists()
    assert sum("--ignore-installed" in command for command in commands) == 3


@pytest.mark.parametrize(
    ("pip_return_code", "expected_error"),
    [
        (1, "安装已校验的 Paddle GPU OCR 资源失败"),
        (0, "运行依赖检查未通过"),
    ],
)
def test_failed_wheel_install_keeps_download_and_partial_for_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    pip_return_code: int,
    expected_error: str,
) -> None:
    config_path = _write_config(tmp_path)
    wheel = resources.WheelResource(
        "refra-test-wheel",
        "1.0",
        "https://example.invalid/refra_test_wheel-1.0-py3-none-any.whl",
        "0" * 64,
        12,
        24,
    )
    wheel_path = resources._wheel_path(config_path, wheel)
    wheel_path.parent.mkdir(parents=True, exist_ok=True)
    wheel_path.write_bytes(b"verified wheel")
    wheel_part = wheel_path.with_name(wheel_path.name + ".part")
    wheel_part.write_bytes(b"resumable fragment")

    class CompletedProcess:
        stdout = io.StringIO("pip output\n")

        def poll(self) -> int:
            return pip_return_code

        def wait(self, timeout: float | None = None) -> int:
            del timeout
            return pip_return_code

    monkeypatch.setattr(
        resources.subprocess, "Popen", lambda *_args, **_kwargs: CompletedProcess()
    )
    if pip_return_code == 0:
        monkeypatch.setattr(resources, "_ocr_packages_are_ready", lambda _wheels: False)

    with pytest.raises(resources.OcrPreparationError, match=expected_error):
        resources._install_wheelhouse(
            config_path,
            (wheel,),
            all_wheels=(wheel,),
            progress=lambda *_values: None,
            cancel=threading.Event(),
        )

    assert wheel_path.read_bytes() == b"verified wheel"
    assert wheel_part.read_bytes() == b"resumable fragment"
    assert not (config_path.parent / resources.PIP_TEMP_RELATIVE_PATH).exists()


def test_prepare_ready_resources_cleans_only_known_downloads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = _write_config(tmp_path / "data")
    manifest_path = tmp_path / "manifest.json"
    _write_manifest(manifest_path)
    monkeypatch.setenv("REFRATRANSLATOR_OCR_MANIFEST_PATH", str(manifest_path))
    wheel = resources._read_wheel_manifest()[0]
    wheel_path = resources._wheel_path(config_path, wheel)
    wheel_path.parent.mkdir(parents=True, exist_ok=True)
    wheel_path.write_bytes(b"old verified wheel")
    wheel_part = wheel_path.with_name(wheel_path.name + ".part")
    wheel_part.write_bytes(b"old partial")
    unknown_wheelhouse_file = wheel_path.parent / "keep-me.txt"
    unknown_wheelhouse_file.write_text("unknown", encoding="utf-8")

    download_root = config_path.parent / resources.DOWNLOAD_RELATIVE_PATH
    download_root.mkdir(parents=True, exist_ok=True)
    archives: list[Path] = []
    for model_name in ("PP-OCRv6_small_det", "PP-OCRv6_small_rec"):
        archive = download_root / f"{model_name}_infer.tar"
        archive.write_bytes(b"old verified archive")
        archive.with_name(archive.name + ".part").write_bytes(b"old partial")
        archives.append(archive)
    unknown_download = download_root / "keep-me.bin"
    unknown_download.write_bytes(b"unknown")

    final_model_payloads: list[Path] = []
    for model_name in ("PP-OCRv6_small_det", "PP-OCRv6_small_rec"):
        model_dir = resources._model_cache_root(config_path) / model_name
        model_dir.mkdir(parents=True, exist_ok=True)
        payload = model_dir / "inference.pdiparams"
        payload.write_bytes(b"installed model payload")
        final_model_payloads.append(payload)

    monkeypatch.setattr(resources, "_wheel_is_installed", lambda _wheel: True)
    monkeypatch.setattr(resources, "_ocr_packages_are_ready", lambda _wheels: True)
    monkeypatch.setattr(resources, "_model_is_ready", lambda _path, _name: True)

    def fail_if_requested(request: httpx.Request) -> httpx.Response:
        pytest.fail(f"ready resources must not request HTTP: {request!r}")

    inventory = resources.prepare_ocr_resources(
        config_path,
        http_transport=httpx.MockTransport(fail_if_requested),
    )

    assert inventory.ready
    assert not wheel_path.exists()
    assert not wheel_part.exists()
    assert unknown_wheelhouse_file.read_text(encoding="utf-8") == "unknown"
    for archive in archives:
        assert not archive.exists()
        assert not archive.with_name(archive.name + ".part").exists()
    assert unknown_download.read_bytes() == b"unknown"
    assert all(
        payload.read_bytes() == b"installed model payload"
        for payload in final_model_payloads
    )


@pytest.mark.parametrize("invalid_payload", ["wrong_hash", "missing_file"])
def test_model_cache_cleanup_uses_real_hash_health_and_preserves_unknown_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    invalid_payload: str,
) -> None:
    config_path = _write_config(tmp_path / "data")
    model_payloads = {
        "inference.json": b'{"model":"tiny-test"}',
        "inference.pdiparams": b"tiny-model-weights",
        "inference.yml": b"Global:\n  model_name: tiny-test\n",
    }
    artifacts: dict[str, tuple[str, int, str, dict[str, str]]] = {}
    for model_name in ("PP-OCRv6_small_det", "PP-OCRv6_small_rec"):
        artifacts[model_name] = (
            f"https://example.invalid/{model_name}_infer.tar",
            32,
            "0" * 64,
            {
                filename: hashlib.sha256(content).hexdigest()
                for filename, content in model_payloads.items()
            },
        )
    monkeypatch.setattr(resources, "MODEL_ARTIFACTS", artifacts)
    monkeypatch.setattr(resources, "_ocr_packages_are_ready", lambda _wheels: True)

    detection_dir = resources._model_cache_root(config_path) / "PP-OCRv6_small_det"
    detection_dir.mkdir(parents=True, exist_ok=True)
    for filename, content in model_payloads.items():
        (detection_dir / filename).write_bytes(content)
    permanent_model_file = detection_dir / "user-owned-note.txt"
    permanent_model_file.write_text("keep", encoding="utf-8")

    recognition_dir = resources._model_cache_root(config_path) / "PP-OCRv6_small_rec"
    recognition_dir.mkdir(parents=True, exist_ok=True)
    for filename, content in model_payloads.items():
        if invalid_payload == "missing_file" and filename == "inference.yml":
            continue
        if invalid_payload == "wrong_hash" and filename == "inference.pdiparams":
            content = b"wrong model weights"
        (recognition_dir / filename).write_bytes(content)

    download_root = config_path.parent / resources.DOWNLOAD_RELATIVE_PATH
    download_root.mkdir(parents=True, exist_ok=True)
    archives: dict[str, Path] = {}
    for model_name in artifacts:
        archive = download_root / f"{model_name}_infer.tar"
        archive.write_bytes(b"temporary model archive")
        archive.with_name(archive.name + ".part").write_bytes(b"resume fragment")
        archives[model_name] = archive
    unknown_file = download_root / "keep-unknown.bin"
    unknown_file.write_bytes(b"unknown cache data")

    resources.cleanup_prepared_downloads(config_path, wheels=())

    detection_archive = archives["PP-OCRv6_small_det"]
    assert resources._model_is_ready(config_path, "PP-OCRv6_small_det")
    assert not detection_archive.exists()
    assert not detection_archive.with_name(detection_archive.name + ".part").exists()
    assert all(
        (detection_dir / filename).read_bytes() == content
        for filename, content in model_payloads.items()
    )
    assert permanent_model_file.read_text(encoding="utf-8") == "keep"

    recognition_archive = archives["PP-OCRv6_small_rec"]
    assert not resources._model_is_ready(config_path, "PP-OCRv6_small_rec")
    assert recognition_archive.read_bytes() == b"temporary model archive"
    recognition_part = recognition_archive.with_name(recognition_archive.name + ".part")
    assert recognition_part.read_bytes() == b"resume fragment"
    assert unknown_file.read_bytes() == b"unknown cache data"


def test_prepare_keeps_archive_when_extracted_model_fails_hash_check(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = _write_config(tmp_path / "data")
    manifest_path = tmp_path / "manifest.json"
    _write_manifest(manifest_path)
    monkeypatch.setenv("REFRATRANSLATOR_OCR_MANIFEST_PATH", str(manifest_path))
    model_name = "PP-OCRv6_small_det"
    expected_payloads = {
        "inference.json": b'{"model":"expected"}',
        "inference.pdiparams": b"expected weights",
        "inference.yml": b"Global:\n  model_name: expected\n",
    }
    artifacts = dict(resources.MODEL_ARTIFACTS)
    artifacts[model_name] = (
        "https://example.invalid/PP-OCRv6_small_det_infer.tar",
        32,
        "0" * 64,
        {
            filename: hashlib.sha256(content).hexdigest()
            for filename, content in expected_payloads.items()
        },
    )
    monkeypatch.setattr(resources, "MODEL_ARTIFACTS", artifacts)
    monkeypatch.setattr(resources, "_wheel_is_installed", lambda _wheel: True)
    monkeypatch.setattr(resources, "_ocr_packages_are_ready", lambda _wheels: True)

    archive_path = resources._model_archive_path(config_path, model_name)
    partial_path = archive_path.with_name(archive_path.name + ".part")

    def fake_download(
        _url: str,
        destination: Path,
        _expected_size: int,
        **_kwargs: object,
    ) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"downloaded model archive")
        partial_path.write_bytes(b"resumable fragment")
        return destination

    def fake_extract(
        _archive_path: Path,
        destination: Path,
        _model_name: str,
    ) -> None:
        destination.mkdir(parents=True, exist_ok=True)
        (destination / "inference.json").write_bytes(b"wrong hash")

    monkeypatch.setattr(resources, "_download_file", fake_download)
    monkeypatch.setattr(resources, "_safe_extract_model", fake_extract)

    with pytest.raises(resources.OcrPreparationError, match="运行文件检查未通过"):
        resources.prepare_ocr_resources(
            config_path,
            http_transport=httpx.MockTransport(
                lambda request: pytest.fail(
                    f"mocked download must not use HTTP: {request!r}"
                )
            ),
        )

    assert not resources._model_is_ready(config_path, model_name)
    assert archive_path.read_bytes() == b"downloaded model archive"
    assert partial_path.read_bytes() == b"resumable fragment"


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
    wheel_path = resources._wheel_path(config_path, wheel)
    wheel_path.parent.mkdir(parents=True, exist_ok=True)
    wheel_path.write_bytes(b"downloaded wheel")
    wheel_part = wheel_path.with_name(wheel_path.name + ".part")
    wheel_part.write_bytes(b"partial retry data")

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
    assert wheel_path.read_bytes() == b"downloaded wheel"
    assert wheel_part.read_bytes() == b"partial retry data"


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
