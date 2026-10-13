"""First-run inventory and installer for the packaged NVIDIA OCR runtime.

The product runtime is a relocatable CPython distribution.  Its OCR wheels and
the two configured PaddleX models stay in the user's data directory/runtime,
so an installation can be prepared without a system Python installation.
"""

from __future__ import annotations

import hashlib
import csv
import io
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Callable
from urllib.parse import unquote, urlsplit

import httpx

from game_screen_translator.config import load_config


MODEL_HOST = (
    "https://paddle-model-ecology.bj.bcebos.com/paddlex/"
    "official_inference_model/paddle3.0.0"
)
MODEL_ARTIFACTS = {
    "PP-OCRv6_small_det": (
        f"{MODEL_HOST}/PP-OCRv6_small_det_infer.tar",
        10_055_680,
        "bfb7c1e59f0faa6b540ebdca93aea3f4b1f2477805b389fbee117820d68fe9f5",
        {
            "inference.json": "89240f689a4a77aad75ef55a8df0a15c8e1d4980a327d17e58f24bbadde5aeab",
            "inference.pdiparams": "5043d4ccc8d63402ccea8feefcee4db57077431a873e78d2191836a178a492da",
            "inference.yml": "193f435274bf9f0b5f71a929bbfbcf148282df7e633b34e7c373e8f44741b516",
        },
    ),
    "PP-OCRv6_small_rec": (
        f"{MODEL_HOST}/PP-OCRv6_small_rec_infer.tar",
        21_442_560,
        "da460f968ce9f88325ac3a34fa302077d6e9b0dcefb16ba3137cd7796f879d06",
        {
            "inference.json": "f0bf53c853937a917affdd74467472167727f8ab0f0f7bded01c4a16c27e46e6",
            "inference.pdiparams": "406e1e689c9a7fbb04178007a3fe10cf852afe7bf8bb3bc6dbb9d532b13bd907",
            "inference.yml": "ab078671bb49f06228eadccd34f1bb501e157f7a047095ffb943ba81512c77d1",
        },
    ),
}
WHEELHOUSE_RELATIVE_PATH = Path(".cache") / "ocr-wheelhouse"
DOWNLOAD_RELATIVE_PATH = Path(".cache") / "paddlex" / "downloads"
PIP_TEMP_RELATIVE_PATH = Path(".cache") / "ocr-install-tmp"
_CONTENT_RANGE = re.compile(r"^bytes (\d+)-(\d+)/(\d+)$")


class OcrPreparationError(RuntimeError):
    """Raised when an OCR resource cannot be inspected, downloaded or installed."""


class OcrPreparationCancelled(OcrPreparationError):
    """Raised when a user cancels first-run resource preparation."""


ProgressCallback = Callable[[str, str, int, int], None]


@dataclass(frozen=True, slots=True)
class WheelResource:
    name: str
    version: str
    url: str
    sha256: str
    size_bytes: int
    installed_size_bytes: int = 0

    @property
    def filename(self) -> str:
        return unquote(Path(urlsplit(self.url).path).name)


def _manifest_path() -> Path:
    override = os.environ.get("REFRATRANSLATOR_OCR_MANIFEST_PATH", "").strip()
    return (
        Path(override).expanduser().resolve()
        if override
        else Path(__file__).with_name("ocr_wheel_manifest.json")
    )


def _read_wheel_manifest() -> tuple[WheelResource, ...]:
    path = _manifest_path()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OcrPreparationError(
            f"安装包缺少可读的 Paddle GPU OCR 资源清单：{path}（{exc}）"
        ) from exc
    try:
        wheels = tuple(WheelResource(**item) for item in payload["wheels"])
    except (KeyError, TypeError, ValueError) as exc:
        raise OcrPreparationError(f"Paddle GPU OCR 资源清单格式错误：{exc}") from exc
    if not wheels:
        raise OcrPreparationError("Paddle GPU OCR 资源清单为空")
    seen_names: set[str] = set()
    for wheel in wheels:
        if (
            not wheel.name
            or not wheel.version
            or not wheel.url.startswith("https://")
            or not re.fullmatch(r"[0-9a-f]{64}", wheel.sha256)
            or wheel.size_bytes <= 0
            or not wheel.filename.lower().endswith(".whl")
            or wheel.name.casefold() in seen_names
        ):
            raise OcrPreparationError(
                f"Paddle GPU OCR 资源清单包含无效 wheel：{wheel.name}"
            )
        seen_names.add(wheel.name.casefold())
    return wheels


@dataclass(frozen=True, slots=True)
class OcrResource:
    name: str
    size_bytes: int | None
    available: bool
    detail: str = ""
    downloaded_bytes: int = 0

    @property
    def remaining_download_bytes(self) -> int | None:
        if self.available:
            return 0
        if self.size_bytes is None:
            return None
        return max(0, self.size_bytes - self.downloaded_bytes)


@dataclass(frozen=True, slots=True)
class OcrResourceInventory:
    resources: tuple[OcrResource, ...]
    errors: tuple[str, ...] = ()

    @property
    def ready(self) -> bool:
        return bool(self.resources) and all(item.available for item in self.resources)

    @property
    def download_size_bytes(self) -> int | None:
        sizes = [
            item.remaining_download_bytes
            for item in self.resources
            if not item.available
        ]
        if any(size is None for size in sizes):
            return None
        return sum(size or 0 for size in sizes)


def _data_root(config_path: str | Path) -> Path:
    return Path(config_path).resolve().parent


def _model_cache_root(config_path: str | Path) -> Path:
    config = load_config(config_path)
    return _data_root(config_path) / config.ocr.cache_dir / "official_models"


def _model_is_ready(config_path: str | Path, model_name: str) -> bool:
    model_dir = _model_cache_root(config_path) / model_name
    artifact = MODEL_ARTIFACTS.get(model_name)
    if artifact is None:
        return False
    expected_hashes = artifact[3]
    for filename, expected_hash in expected_hashes.items():
        path = model_dir / filename
        if not path.is_file():
            return False
        try:
            if _sha256_path(path) != expected_hash:
                return False
        except OSError:
            return False
    return True


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _wheel_is_installed(wheel: WheelResource) -> bool:
    from importlib import metadata

    try:
        distribution = metadata.distribution(wheel.name)
    except metadata.PackageNotFoundError:
        return False
    return (
        distribution.version == wheel.version
        and _distribution_files_are_complete(distribution)
    )


def _distribution_files_are_complete(distribution: object) -> bool:
    """Check the installed RECORD payload, ignoring external launchers/pycache."""

    try:
        record_text = distribution.read_text("RECORD")  # type: ignore[attr-defined]
        metadata_text = distribution.read_text("METADATA")  # type: ignore[attr-defined]
        root = Path(distribution.locate_file("")).resolve()  # type: ignore[attr-defined]
        if not record_text or not metadata_text or not root.is_dir():
            return False

        has_record = False
        has_metadata = False
        checked_files = 0
        for row in csv.reader(io.StringIO(record_text)):
            if len(row) != 3:
                return False
            filename, _recorded_hash, size_text = row
            relative = PurePosixPath(filename.replace("\\", "/"))
            path = Path(distribution.locate_file(relative)).resolve()  # type: ignore[attr-defined]
            try:
                path.relative_to(root)
            except ValueError:
                # Console launchers in .data/scripts are rebuilt by pip and are
                # intentionally not part of the private runtime's vendored core.
                continue

            is_dist_info_file = relative.parent.name.endswith(".dist-info")
            if is_dist_info_file and relative.name == "RECORD":
                has_record = path.is_file()
            elif is_dist_info_file and relative.name == "METADATA":
                has_metadata = path.is_file()
            if is_dist_info_file:
                continue

            if relative.suffix.lower() == ".pyc" or "__pycache__" in relative.parts:
                continue
            checked_files += 1
            if not path.is_file():
                return False
            if size_text:
                if path.stat().st_size != int(size_text):
                    return False
            else:
                return False

        return has_record and has_metadata and checked_files > 0
    except (OSError, RuntimeError, TypeError, ValueError):
        return False


def _wheel_has_incomplete_same_version_install(wheel: WheelResource) -> bool:
    from importlib import metadata

    try:
        distribution = metadata.distribution(wheel.name)
    except metadata.PackageNotFoundError:
        return False
    return (
        distribution.version == wheel.version
        and not _distribution_files_are_complete(distribution)
    )


def _ocr_packages_are_ready(wheels: tuple[WheelResource, ...] | None = None) -> bool:
    from importlib import metadata

    if wheels is None:
        wheels = _read_wheel_manifest()
    if not all(_wheel_is_installed(wheel) for wheel in wheels):
        return False
    try:
        metadata.version("paddlepaddle")
    except metadata.PackageNotFoundError:
        return True
    # The CPU and GPU distributions share the same import package.  Keep the
    # NVIDIA-only product invariant explicit if a custom runtime was modified.
    return False


def _wheelhouse(config_path: str | Path) -> Path:
    return _data_root(config_path) / WHEELHOUSE_RELATIVE_PATH


def _pending_wheels(wheels: tuple[WheelResource, ...]) -> tuple[WheelResource, ...]:
    return tuple(wheel for wheel in wheels if not _wheel_is_installed(wheel))


def _model_size(
    config_path: str | Path,
    model_name: str,
    *,
    http_transport: httpx.BaseTransport | None = None,
) -> int:
    artifact = MODEL_ARTIFACTS.get(model_name)
    if artifact is None:
        raise OcrPreparationError(
            f"当前安装器无法清单化 OCR 模型 {model_name}；保留现有配置并联系维护者。"
        )
    return artifact[1]


def inspect_ocr_resources(
    config_path: str | Path,
    *,
    http_transport: httpx.BaseTransport | None = None,
) -> OcrResourceInventory:
    """Return exact remaining wheel/model sizes and whether each item is present."""

    config = load_config(config_path)
    resources: list[OcrResource] = []
    errors: list[str] = []
    try:
        wheels = _read_wheel_manifest()
        pending = _pending_wheels(wheels)
        if not pending:
            resources.append(
                OcrResource(
                    "GPU OCR 运行依赖",
                    0,
                    True,
                    f"Paddle GPU 3.3.1 · PaddleOCR 3.7.0 · PaddleX 3.7.2；"
                    f"{len(wheels)} 项已安装",
                )
            )
        else:
            total_bytes = sum(wheel.size_bytes for wheel in pending)
            downloaded_bytes = sum(
                _cached_download_bytes(_wheel_path(config_path, wheel), wheel.size_bytes)
                for wheel in pending
            )
            details = (
                "Paddle GPU 3.3.1 · PaddleOCR 3.7.0 · PaddleX 3.7.2；"
                f"缺少 {len(pending)} 项，共 {len(wheels)} 个固定版本 wheel"
            )
            resources.append(
                OcrResource(
                    "GPU OCR 运行依赖",
                    total_bytes,
                    False,
                    details,
                    downloaded_bytes,
                )
            )
    except (OcrPreparationError, OSError) as exc:
        errors.append(str(exc))
        resources.append(
            OcrResource("GPU OCR 运行依赖", None, False, "清单不可用")
        )

    for row_name, model_name in (
        ("文字检测模型", config.ocr.detection_model),
        ("文字识别模型", config.ocr.recognition_model),
    ):
        available = _model_is_ready(config_path, model_name)
        if available:
            resources.append(OcrResource(row_name, 0, True, f"{model_name} · 已校验缓存"))
            continue
        try:
            size_bytes = _model_size(
                config_path,
                model_name,
                http_transport=http_transport,
            )
            archive = (
                _data_root(config_path)
                / DOWNLOAD_RELATIVE_PATH
                / f"{model_name}_infer.tar"
            )
            downloaded = _cached_download_bytes(archive, size_bytes)
            detail = (
                f"{model_name} · 已缓存，待校验/解压"
                if downloaded == size_bytes
                else f"{model_name} · 已缓存 {downloaded:,} 字节，可续传"
                if downloaded
                else f"{model_name} · OCR 模型包，SHA-256 已锁定"
            )
            resources.append(
                OcrResource(row_name, size_bytes, False, detail, downloaded)
            )
        except (OcrPreparationError, OSError, subprocess.SubprocessError) as exc:
            errors.append(str(exc))
            resources.append(OcrResource(row_name, None, False, f"{model_name} · 大小获取失败"))
    return OcrResourceInventory(tuple(resources), tuple(errors))


def _sha256_file(path: Path, cancel: threading.Event) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            if cancel.is_set():
                raise OcrPreparationCancelled("OCR 资源准备已取消")
            digest.update(chunk)
    return digest.hexdigest()


def _download_file(
    url: str,
    destination: Path,
    expected_size: int,
    *,
    expected_sha256: str | None,
    client: httpx.Client,
    progress: ProgressCallback,
    cancel: threading.Event,
    label: str,
) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_file() and destination.stat().st_size == expected_size:
        if expected_sha256 is None or _sha256_file(destination, cancel) == expected_sha256:
            progress("ready", label, expected_size, expected_size)
            return destination
        destination.unlink()
    elif destination.exists():
        destination.unlink()

    partial = destination.with_name(destination.name + ".part")
    try:
        offset = partial.stat().st_size
    except OSError:
        offset = 0
    if offset < 0 or offset > expected_size:
        partial.unlink(missing_ok=True)
        offset = 0
    if offset == expected_size:
        actual_hash = _sha256_file(partial, cancel) if expected_sha256 else None
        if expected_sha256 is None or actual_hash == expected_sha256:
            os.replace(partial, destination)
            progress("ready", label, expected_size, expected_size)
            return destination
        partial.unlink(missing_ok=True)
        offset = 0
    headers = {"Range": f"bytes={offset}-"} if offset else {}
    try:
        with client.stream("GET", url, headers=headers) as response:
            if offset and response.status_code == 206:
                content_range = _CONTENT_RANGE.fullmatch(
                    response.headers.get("Content-Range", "")
                )
                if content_range is None or tuple(map(int, content_range.groups())) != (
                    offset,
                    expected_size - 1,
                    expected_size,
                ):
                    raise OcrPreparationError(f"{label} 续传范围与资源清单不符")
                mode = "ab"
            elif response.status_code == 200:
                offset = 0
                mode = "wb"
            else:
                response.raise_for_status()
                raise OcrPreparationError(f"{label} 下载源返回了无效续传响应")
            with partial.open(mode) as handle:
                completed = offset
                last_update = 0.0
                for chunk in response.iter_bytes(chunk_size=1024 * 1024):
                    if cancel.is_set():
                        raise OcrPreparationCancelled("OCR 资源准备已取消")
                    handle.write(chunk)
                    completed += len(chunk)
                    if completed > expected_size:
                        raise OcrPreparationError(f"{label} 下载内容超过清单大小")
                    now = time.monotonic()
                    if now - last_update >= 0.1 or completed == expected_size:
                        progress("download", label, completed, expected_size)
                        last_update = now
    except OcrPreparationError:
        raise
    except (httpx.HTTPError, OSError) as exc:
        raise OcrPreparationError(f"下载 {label} 失败：{exc}") from exc

    if partial.stat().st_size != expected_size:
        raise OcrPreparationError(
            f"{label} 下载不完整：收到 {partial.stat().st_size}，预期 {expected_size} 字节"
        )
    if expected_sha256 is not None:
        actual_hash = _sha256_file(partial, cancel)
        if actual_hash != expected_sha256:
            partial.unlink(missing_ok=True)
            raise OcrPreparationError(f"{label} SHA-256 校验失败；请重试下载")
    os.replace(partial, destination)
    progress("ready", label, expected_size, expected_size)
    return destination


def _wheel_path(config_path: str | Path, wheel: WheelResource) -> Path:
    return _wheelhouse(config_path) / wheel.filename


def _model_archive_path(config_path: str | Path, model_name: str) -> Path:
    return (
        _data_root(config_path)
        / DOWNLOAD_RELATIVE_PATH
        / f"{model_name}_infer.tar"
    )


def _unlink_known_download(config_path: str | Path, path: Path) -> None:
    """Remove one known download and its resumable sidecar, never directories."""

    data_root = _data_root(config_path).resolve()
    try:
        path.parent.resolve().relative_to(data_root)
    except (OSError, ValueError):
        return

    for candidate in (path, path.with_name(path.name + ".part")):
        try:
            if candidate.is_file() or candidate.is_symlink():
                candidate.unlink()
        except OSError:
            # Resource cleanup is opportunistic; a locked cache must not make
            # already-installed OCR resources unusable.
            continue


def _cleanup_wheelhouse_if_ready(
    config_path: str | Path,
    wheels: tuple[WheelResource, ...],
) -> bool:
    if not _ocr_packages_are_ready(wheels):
        return False
    for wheel in wheels:
        _unlink_known_download(config_path, _wheel_path(config_path, wheel))
    return True


def _cleanup_ready_model_archives(config_path: str | Path) -> None:
    config = load_config(config_path)
    model_names = dict.fromkeys(
        (config.ocr.detection_model, config.ocr.recognition_model)
    )
    for model_name in model_names:
        if model_name in MODEL_ARTIFACTS and _model_is_ready(config_path, model_name):
            _unlink_known_download(
                config_path,
                _model_archive_path(config_path, model_name),
            )


def cleanup_prepared_downloads(
    config_path: str | Path,
    wheels: tuple[WheelResource, ...] | None = None,
) -> None:
    """Delete known downloads whose installed OCR payloads already pass health checks.

    This local-only cleanup is safe to call when startup finds all resources ready.
    It does not download, install, or remove unknown files from cache directories.
    """

    known_wheels = _read_wheel_manifest() if wheels is None else wheels
    _cleanup_wheelhouse_if_ready(config_path, known_wheels)
    _cleanup_ready_model_archives(config_path)


def _cached_download_bytes(path: Path, expected_size: int) -> int:
    """Count reusable bytes for the inventory without doing network I/O."""

    try:
        if path.is_file() and path.stat().st_size == expected_size:
            return expected_size
    except OSError:
        pass
    partial = path.with_name(path.name + ".part")
    try:
        size = partial.stat().st_size
    except OSError:
        return 0
    return size if 0 < size <= expected_size else 0


def _install_wheelhouse(
    config_path: str | Path,
    wheels: tuple[WheelResource, ...],
    *,
    all_wheels: tuple[WheelResource, ...],
    progress: ProgressCallback,
    cancel: threading.Event,
) -> None:
    repair_wheels = tuple(
        wheel for wheel in wheels if _wheel_has_incomplete_same_version_install(wheel)
    )
    repair_names = {wheel.name.casefold() for wheel in repair_wheels}
    regular_wheels = tuple(
        wheel for wheel in wheels if wheel.name.casefold() not in repair_names
    )
    batches = tuple(
        (batch, ignore_installed)
        for batch, ignore_installed in (
            (repair_wheels, True),
            (regular_wheels, False),
        )
        if batch
    )
    progress("install", "安装已校验的 Paddle GPU OCR wheel", 0, 1)
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    temp_root = _data_root(config_path) / PIP_TEMP_RELATIVE_PATH
    temp_root.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    environment["TEMP"] = str(temp_root)
    environment["TMP"] = str(temp_root)
    output: list[str] = []
    try:
        for batch, ignore_installed in batches:
            command = [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--no-index",
                "--no-deps",
                "--disable-pip-version-check",
                *( ["--ignore-installed"] if ignore_installed else [] ),
                *(str(_wheel_path(config_path, wheel)) for wheel in batch),
            ]
            try:
                process = subprocess.Popen(
                    command,
                    cwd=_data_root(config_path),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    creationflags=creation_flags,
                    env=environment,
                )
            except OSError as exc:
                raise OcrPreparationError(f"无法启动内置 pip：{exc}") from exc
            assert process.stdout is not None
            lines: queue.Queue[str | None] = queue.Queue()

            def collect_output() -> None:
                try:
                    for line in process.stdout:
                        lines.put(line.rstrip())
                finally:
                    lines.put(None)

            reader = threading.Thread(
                target=collect_output, name="ocr-pip-output", daemon=True
            )
            reader.start()
            stream_finished = False
            while process.poll() is None:
                if cancel.wait(0.1):
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)
                    reader.join(timeout=1)
                    raise OcrPreparationCancelled("OCR 资源准备已取消")
                while True:
                    try:
                        line = lines.get_nowait()
                    except queue.Empty:
                        break
                    if line is None:
                        stream_finished = True
                        break
                    output.append(line)
                    progress("install", line, 0, 1)
            return_code = process.wait()
            reader.join(timeout=1)
            while not stream_finished:
                try:
                    line = lines.get_nowait()
                except queue.Empty:
                    break
                if line is None:
                    stream_finished = True
                else:
                    output.append(line)
                    progress("install", line, 0, 1)
            if return_code != 0:
                raise OcrPreparationError(
                    "安装已校验的 Paddle GPU OCR 资源失败。可重试。\n"
                    + "\n".join(output[-80:])
                )
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)
    if not _cleanup_wheelhouse_if_ready(config_path, all_wheels):
        raise OcrPreparationError("Paddle GPU OCR wheel 已安装，但运行依赖检查未通过。")
    _cleanup_ready_model_archives(config_path)
    progress("ready", "Paddle GPU OCR 运行依赖", 1, 1)


def _safe_extract_model(
    archive_path: Path,
    destination: Path,
    model_name: str,
) -> None:
    stage = Path(tempfile.mkdtemp(prefix=f".{destination.name}-", dir=destination.parent))
    backup = destination.with_name(f".{destination.name}.previous")
    try:
        try:
            with tarfile.open(archive_path, mode="r:*") as archive:
                members = archive.getmembers()
                for member in members:
                    relative = PurePosixPath(member.name)
                    if (
                        relative.is_absolute()
                        or ".." in relative.parts
                        or any(":" in part for part in relative.parts)
                        or "\\" in member.name
                        or not (member.isfile() or member.isdir())
                    ):
                        raise OcrPreparationError(
                            f"OCR 模型包包含不安全路径：{member.name}"
                        )
                archive.extractall(stage, members=members)
        except (OSError, tarfile.TarError) as exc:
            raise OcrPreparationError(f"无法解压 OCR 模型：{exc}") from exc

        model_root: Path | None = None
        for params in stage.rglob("inference.pdiparams"):
            candidate = params.parent
            if all((candidate / name).is_file() for name in ("inference.json", "inference.yml")):
                model_root = candidate
                break
        if model_root is None:
            raise OcrPreparationError("OCR 模型包缺少 inference.json/yml/pdiparams")
        expected_hashes = MODEL_ARTIFACTS[model_name][3]
        for filename, expected_hash in expected_hashes.items():
            if _sha256_path(model_root / filename) != expected_hash:
                raise OcrPreparationError(
                    f"{model_name} 模型文件 SHA-256 校验失败：{filename}"
                )

        if backup.exists():
            shutil.rmtree(backup)
        if destination.exists():
            os.replace(destination, backup)
        try:
            os.replace(model_root, destination)
        except OSError:
            if backup.exists() and not destination.exists():
                os.replace(backup, destination)
            raise
        if backup.exists():
            shutil.rmtree(backup)
    finally:
        if stage.exists():
            shutil.rmtree(stage, ignore_errors=True)


def prepare_ocr_resources(
    config_path: str | Path,
    *,
    progress: ProgressCallback | None = None,
    cancel: threading.Event | None = None,
    http_transport: httpx.BaseTransport | None = None,
) -> OcrResourceInventory:
    """Download, hash-check, install and extract every missing OCR resource."""

    config = load_config(config_path)
    callback = progress or (lambda _phase, _label, _done, _total: None)
    cancelled = cancel or threading.Event()
    if cancelled.is_set():
        raise OcrPreparationCancelled("OCR 资源准备已取消")

    wheels = _read_wheel_manifest()
    wheel_plan = _pending_wheels(wheels)
    if not wheel_plan:
        cleanup_prepared_downloads(config_path, wheels)
    model_plan = tuple(
        dict.fromkeys(
            name
            for name in (config.ocr.detection_model, config.ocr.recognition_model)
            if not _model_is_ready(config_path, name)
        )
    )
    _check_disk_space(config_path, wheel_plan, model_plan)
    if wheel_plan:
        timeout = httpx.Timeout(connect=15.0, read=60.0, write=30.0, pool=30.0)
        with httpx.Client(
            follow_redirects=True,
            timeout=timeout,
            transport=http_transport,
            headers={
                "Accept-Encoding": "identity",
                "User-Agent": "RefraTranslator setup",
            },
        ) as client:
            for wheel in wheel_plan:
                if cancelled.is_set():
                    raise OcrPreparationCancelled("OCR 资源准备已取消")
                _download_file(
                    wheel.url,
                    _wheel_path(config_path, wheel),
                    wheel.size_bytes,
                    expected_sha256=wheel.sha256,
                    client=client,
                    progress=callback,
                    cancel=cancelled,
                    label=f"{wheel.name} {wheel.version}",
                )
        _install_wheelhouse(
            config_path,
            wheel_plan,
            all_wheels=wheels,
            progress=callback,
            cancel=cancelled,
        )

    cache_root = _model_cache_root(config_path)
    cache_root.mkdir(parents=True, exist_ok=True)
    timeout = httpx.Timeout(connect=15.0, read=60.0, write=30.0, pool=30.0)
    with httpx.Client(
        follow_redirects=True,
        timeout=timeout,
        transport=http_transport,
        headers={
            "Accept-Encoding": "identity",
            "User-Agent": "RefraTranslator PaddleX model setup",
        },
    ) as client:
        for model_name in (config.ocr.detection_model, config.ocr.recognition_model):
            if cancelled.is_set():
                raise OcrPreparationCancelled("OCR 资源准备已取消")
            if _model_is_ready(config_path, model_name):
                _unlink_known_download(
                    config_path,
                    _model_archive_path(config_path, model_name),
                )
                callback("ready", model_name, 1, 1)
                continue
            model_artifact = MODEL_ARTIFACTS.get(model_name)
            if model_artifact is None:
                raise OcrPreparationError(
                    f"当前安装器无法准备 OCR 模型 {model_name}。"
                )
            size_bytes = _model_size(
                config_path,
                model_name,
                http_transport=http_transport,
            )
            archive = _download_file(
                model_artifact[0],
                _model_archive_path(config_path, model_name),
                size_bytes,
                expected_sha256=model_artifact[2],
                client=client,
                progress=callback,
                cancel=cancelled,
                label=model_name,
            )
            _safe_extract_model(archive, cache_root / model_name, model_name)
            if not _model_is_ready(config_path, model_name):
                raise OcrPreparationError(
                    f"{model_name} 模型已解压，但运行文件检查未通过。可重试。"
                )
            _unlink_known_download(
                config_path,
                _model_archive_path(config_path, model_name),
            )
            callback("ready", model_name, 1, 1)

    inventory = inspect_ocr_resources(config_path, http_transport=http_transport)
    if not inventory.ready:
        raise OcrPreparationError(
            "OCR 资源准备结束后仍有缺项。\n" + "\n".join(inventory.errors)
        )
    return inventory


def _model_unpacked_size(model_name: str) -> int:
    sizes = {
        "PP-OCRv6_small_det": (229_307, 9_817_888, 885),
        "PP-OCRv6_small_rec": (208_004, 21_074_618, 150_579),
    }
    try:
        return sum(sizes[model_name])
    except KeyError as exc:
        raise OcrPreparationError(
            f"当前安装器无法准备 OCR 模型 {model_name}。"
        ) from exc


def _check_disk_space(
    config_path: str | Path,
    pending_wheels: tuple[WheelResource, ...],
    missing_models: tuple[str, ...],
) -> None:
    data_root = _data_root(config_path)
    runtime_root = Path(sys.executable).resolve().parent
    data_required = sum(
        max(
            0,
            wheel.size_bytes
            - _cached_download_bytes(_wheel_path(config_path, wheel), wheel.size_bytes),
        )
        for wheel in pending_wheels
    )
    runtime_required = 0
    for wheel in pending_wheels:
        expanded = wheel.installed_size_bytes or wheel.size_bytes
        runtime_required += max(expanded, wheel.size_bytes)
        # pip unpacks wheels into TEMP before it installs them. The service
        # pins TEMP to the data volume and accounts for that peak separately.
        data_required += expanded
    for model_name in missing_models:
        archive_size = _model_size(config_path, model_name)
        archive = (
            data_root
            / DOWNLOAD_RELATIVE_PATH
            / f"{model_name}_infer.tar"
        )
        data_required += max(
            0,
            archive_size - _cached_download_bytes(archive, archive_size),
        )
        data_required += _model_unpacked_size(model_name)

    requirements = (
        (data_root, data_required, "资源下载、临时解包和 OCR 模型缓存"),
        (runtime_root, runtime_required, "内置 OCR 运行依赖安装"),
    )
    grouped: dict[str, tuple[Path, int, list[str]]] = {}
    for path, required, label in requirements:
        resolved = path.resolve()
        key = resolved.drive.casefold() or resolved.anchor.casefold()
        prior = grouped.get(key)
        if prior is None:
            grouped[key] = (path, required, [label])
        else:
            grouped[key] = (
                prior[0],
                prior[1] + required,
                [*prior[2], label],
            )
    for path, required, labels in grouped.values():
        try:
            free = shutil.disk_usage(path).free
        except OSError as exc:
            raise OcrPreparationError(f"无法检查磁盘空间 {path}：{exc}") from exc
        if free < required:
            raise OcrPreparationError(
                f"磁盘空间不足（{', '.join(labels)}）：{path} 需要至少 "
                f"{required:,} 字节，可用 {free:,} 字节。释放空间后可以重试。"
            )
