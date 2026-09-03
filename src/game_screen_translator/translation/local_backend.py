from __future__ import annotations

import hashlib
import json
import os
import platform
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import zipfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath
from typing import Any

import httpx

from game_screen_translator.config import (
    AppConfig,
    BUILTIN_CONTEXT_PER_SLOT,
    BUILTIN_CUDA_DEVICE_FOLLOW_OCR,
    BUILTIN_KV_CACHE_TYPES,
    BUILTIN_MAX_OUTPUT_TOKENS,
    BUILTIN_PARALLEL_MAX,
    TranslationConfig,
)


LLAMA_CPP_VERSION = "b10621"
LLAMA_CPP_STABLE_VERSION = "v0.3.0"
HY_MT2_1_8B_REVISION = "00451019639c4214392db1f02a9ee824e223f1e4"
HY_MT2_7B_REVISION = "47b1dd35c1f984e23ec7b3c72e5d01620dce8f40"
LOCAL_BACKEND_DIRECTORY = ".cache/local-llm"
_DOWNLOAD_SAFETY_BYTES = 512 * 1024 * 1024
_RUNTIME_EXPANSION_ALLOWANCE_BYTES = 2 * 1024**3


class LocalBackendError(RuntimeError):
    """Raised when the managed local translation backend cannot be used."""


class LocalBackendDownloadCancelled(LocalBackendError):
    """Raised when the user cancels a managed download."""


@dataclass(frozen=True, slots=True)
class DownloadArtifact:
    label: str
    filename: str
    url: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True, slots=True)
class BuiltinModel:
    model_id: str
    display_name: str
    tier: str
    artifact: DownloadArtifact

    @property
    def size_gib(self) -> float:
        return self.artifact.size_bytes / (1024**3)


LLAMA_CPP_ARTIFACTS = (
    DownloadArtifact(
        label=f"llama.cpp {LLAMA_CPP_VERSION} CUDA 12.4",
        filename=f"llama-{LLAMA_CPP_VERSION}-bin-win-cuda-12.4-x64.zip",
        url=(
            "https://github.com/ggml-org/llama.cpp/releases/download/"
            f"{LLAMA_CPP_VERSION}/"
            f"llama-{LLAMA_CPP_VERSION}-bin-win-cuda-12.4-x64.zip"
        ),
        size_bytes=250_464_283,
        sha256="81c2ff62e14b549cd5c766ccdd5c61f09e821a171655c3047bdccfddc2d1a1e2",
    ),
    DownloadArtifact(
        label="CUDA 12.4 运行库",
        filename="cudart-llama-bin-win-cuda-12.4-x64.zip",
        url=(
            "https://github.com/ggml-org/llama.cpp/releases/download/"
            f"{LLAMA_CPP_VERSION}/cudart-llama-bin-win-cuda-12.4-x64.zip"
        ),
        size_bytes=391_443_627,
        sha256="8c79a9b226de4b3cacfd1f83d24f962d0773be79f1e7b75c6af4ded7e32ae1d6",
    ),
)


BUILTIN_MODELS = (
    BuiltinModel(
        model_id="Hy-MT2-1.8B-Q8_0.gguf",
        display_name="Hy-MT2 1.8B · Q8_0",
        tier="低显存 / 快速",
        artifact=DownloadArtifact(
            label="Hy-MT2 1.8B Q8_0 模型",
            filename="Hy-MT2-1.8B-Q8_0.gguf",
            url=(
                "https://www.modelscope.cn/models/Tencent-Hunyuan/"
                "Hy-MT2-1.8B-GGUF/resolve/"
                f"{HY_MT2_1_8B_REVISION}/Hy-MT2-1.8B-Q8_0.gguf"
            ),
            size_bytes=1_908_528_192,
            sha256="5c3fe0b1408a5ceb0143184ef247b11b579c525f4b02b060e6c851bb76fef1a4",
        ),
    ),
    BuiltinModel(
        model_id="Hy-MT2-7B-Q4_K_M.gguf",
        display_name="Hy-MT2 7B · Q4_K_M",
        tier="高显存 / 质量",
        artifact=DownloadArtifact(
            label="Hy-MT2 7B Q4_K_M 模型",
            filename="Hy-MT2-7B-Q4_K_M.gguf",
            url=(
                "https://www.modelscope.cn/models/Tencent-Hunyuan/"
                "Hy-MT2-7B-GGUF/resolve/"
                f"{HY_MT2_7B_REVISION}/Hy-MT2-7B-Q4_K_M.gguf"
            ),
            size_bytes=4_624_648_896,
            sha256="9f96256500f3fc1ab4d64336b58f52a949a95ad7516b0c229476eef782f9f77b",
        ),
    ),
)
_MODELS_BY_ID = {model.model_id: model for model in BUILTIN_MODELS}


ProgressCallback = Callable[[str, str, int, int], None]


def get_builtin_model(model_id: str) -> BuiltinModel:
    try:
        return _MODELS_BY_ID[model_id]
    except KeyError as exc:
        raise LocalBackendError(f"未知的内置模型：{model_id}") from exc


def local_backend_root(config_path: str | Path) -> Path:
    return Path(config_path).resolve().parent / LOCAL_BACKEND_DIRECTORY


def _downloads_directory(root: Path) -> Path:
    return root / "downloads"


def _models_directory(root: Path) -> Path:
    return root / "models"


def _runtime_directory(root: Path) -> Path:
    return root / "runtime" / LLAMA_CPP_VERSION


def model_path(root: Path, model: BuiltinModel | str) -> Path:
    resolved = get_builtin_model(model) if isinstance(model, str) else model
    return _models_directory(root) / resolved.artifact.filename


def _verification_path(path: Path) -> Path:
    return path.with_name(f"{path.name}.verified.json")


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _artifact_is_verified(path: Path, artifact: DownloadArtifact) -> bool:
    if not path.is_file():
        return False
    try:
        stat = path.stat()
        if stat.st_size != artifact.size_bytes:
            return False
    except OSError:
        return False
    marker = _read_json(_verification_path(path))
    return bool(
        marker
        and marker.get("size_bytes") == artifact.size_bytes
        and marker.get("sha256") == artifact.sha256
        and marker.get("mtime_ns") == stat.st_mtime_ns
    )


def model_is_ready(root: Path, model: BuiltinModel | str) -> bool:
    resolved = get_builtin_model(model) if isinstance(model, str) else model
    return _artifact_is_verified(model_path(root, resolved), resolved.artifact)


def _runtime_marker(root: Path) -> Path:
    return _runtime_directory(root) / "runtime.json"


def runtime_executable(root: Path) -> Path | None:
    marker = _read_json(_runtime_marker(root))
    if not marker or marker.get("version") != LLAMA_CPP_VERSION:
        return None
    if marker.get("artifacts") != {
        artifact.filename: artifact.sha256 for artifact in LLAMA_CPP_ARTIFACTS
    }:
        return None
    relative = marker.get("server_executable")
    if not isinstance(relative, str) or not relative:
        return None
    runtime = _runtime_directory(root).resolve()
    executable = (runtime / relative).resolve()
    try:
        executable.relative_to(runtime)
    except ValueError:
        return None
    return executable if executable.is_file() else None


def runtime_is_ready(root: Path) -> bool:
    return runtime_executable(root) is not None


def local_backend_is_ready(root: Path, model_id: str) -> bool:
    return runtime_is_ready(root) and model_is_ready(root, model_id)


def _partial_size(directory: Path, artifact: DownloadArtifact) -> int:
    path = directory / f"{artifact.filename}.part"
    try:
        size = path.stat().st_size
    except OSError:
        return 0
    return size if 0 <= size <= artifact.size_bytes else 0


def _remaining_download_bytes(directory: Path, artifact: DownloadArtifact) -> int:
    destination = directory / artifact.filename
    try:
        if destination.is_file() and destination.stat().st_size == artifact.size_bytes:
            return 0
    except OSError:
        pass
    return artifact.size_bytes - _partial_size(directory, artifact)


def required_install_space(root: Path, model_id: str) -> int:
    model = get_builtin_model(model_id)
    required = _DOWNLOAD_SAFETY_BYTES
    if not runtime_is_ready(root):
        downloads = _downloads_directory(root)
        required += _RUNTIME_EXPANSION_ALLOWANCE_BYTES
        required += sum(
            _remaining_download_bytes(downloads, artifact)
            for artifact in LLAMA_CPP_ARTIFACTS
        )
    if not model_is_ready(root, model):
        required += _remaining_download_bytes(
            _models_directory(root),
            model.artifact,
        )
    return required


def _format_gib(size_bytes: int) -> str:
    return f"{size_bytes / (1024**3):.2f} GiB"


def _check_free_space(root: Path, required_bytes: int) -> None:
    root.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(root).free
    if free < required_bytes:
        raise LocalBackendError(
            "磁盘空间不足："
            f"至少还需要 {_format_gib(required_bytes)}，"
            f"当前可用 {_format_gib(free)}"
        )


def _write_verification_marker(path: Path, artifact: DownloadArtifact) -> None:
    marker = _verification_path(path)
    temporary = marker.with_name(f"{marker.name}.{os.getpid()}.tmp")
    payload = {
        "filename": artifact.filename,
        "size_bytes": artifact.size_bytes,
        "sha256": artifact.sha256,
        "mtime_ns": path.stat().st_mtime_ns,
    }
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, marker)
    finally:
        temporary.unlink(missing_ok=True)


def _sha256_file(
    path: Path,
    artifact: DownloadArtifact,
    progress: ProgressCallback,
    cancel: threading.Event,
) -> str:
    digest = hashlib.sha256()
    completed = 0
    with path.open("rb") as handle:
        while chunk := handle.read(4 * 1024 * 1024):
            if cancel.is_set():
                raise LocalBackendDownloadCancelled("下载已取消")
            digest.update(chunk)
            completed += len(chunk)
            progress("verify", artifact.label, completed, artifact.size_bytes)
    return digest.hexdigest()


def _verify_downloaded_file(
    path: Path,
    artifact: DownloadArtifact,
    progress: ProgressCallback,
    cancel: threading.Event,
) -> None:
    try:
        actual_size = path.stat().st_size
    except OSError as exc:
        raise LocalBackendError(f"无法读取下载文件：{path}（{exc}）") from exc
    if actual_size != artifact.size_bytes:
        raise LocalBackendError(
            f"{artifact.label} 文件大小不符："
            f"预期 {artifact.size_bytes}，实际 {actual_size}"
        )
    actual_hash = _sha256_file(path, artifact, progress, cancel)
    if actual_hash != artifact.sha256:
        raise LocalBackendError(
            f"{artifact.label} SHA-256 校验失败；已拒绝使用该文件"
        )


def _parse_content_range(value: str) -> tuple[int, int, int] | None:
    # Expected form: bytes START-END/TOTAL
    if not value.startswith("bytes ") or "/" not in value or "-" not in value:
        return None
    try:
        interval, total = value[6:].split("/", 1)
        start, end = interval.split("-", 1)
        return int(start), int(end), int(total)
    except ValueError:
        return None


def _download_artifact(
    directory: Path,
    artifact: DownloadArtifact,
    client: httpx.Client,
    progress: ProgressCallback,
    cancel: threading.Event,
) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / artifact.filename
    if _artifact_is_verified(destination, artifact):
        progress("ready", artifact.label, artifact.size_bytes, artifact.size_bytes)
        return destination

    if destination.is_file() and destination.stat().st_size == artifact.size_bytes:
        try:
            _verify_downloaded_file(destination, artifact, progress, cancel)
        except LocalBackendDownloadCancelled:
            raise
        except LocalBackendError:
            destination.unlink(missing_ok=True)
            _verification_path(destination).unlink(missing_ok=True)
        else:
            _write_verification_marker(destination, artifact)
            progress("ready", artifact.label, artifact.size_bytes, artifact.size_bytes)
            return destination

    partial = directory / f"{artifact.filename}.part"
    try:
        offset = partial.stat().st_size
    except OSError:
        offset = 0
    if offset < 0 or offset > artifact.size_bytes:
        partial.unlink(missing_ok=True)
        offset = 0

    if offset < artifact.size_bytes:
        headers = {"Range": f"bytes={offset}-"} if offset else {}
        try:
            with client.stream("GET", artifact.url, headers=headers) as response:
                if offset and response.status_code == 206:
                    content_range = _parse_content_range(
                        response.headers.get("Content-Range", "")
                    )
                    if content_range is None or content_range != (
                        offset,
                        artifact.size_bytes - 1,
                        artifact.size_bytes,
                    ):
                        raise LocalBackendError(
                            f"{artifact.label} 下载服务器返回了无效的续传范围"
                        )
                    mode = "ab"
                elif response.status_code == 200:
                    offset = 0
                    mode = "wb"
                else:
                    response.raise_for_status()
                    raise LocalBackendError(
                        f"{artifact.label} 下载服务器不支持预期的续传响应"
                    )
                with partial.open(mode) as handle:
                    completed = offset
                    last_reported = 0.0
                    for chunk in response.iter_bytes(chunk_size=1024 * 1024):
                        if cancel.is_set():
                            raise LocalBackendDownloadCancelled("下载已取消")
                        handle.write(chunk)
                        completed += len(chunk)
                        if completed > artifact.size_bytes:
                            raise LocalBackendError(
                                f"{artifact.label} 下载内容超过预期大小"
                            )
                        now = time.monotonic()
                        if now - last_reported >= 0.1 or completed == artifact.size_bytes:
                            progress(
                                "download",
                                artifact.label,
                                completed,
                                artifact.size_bytes,
                            )
                            last_reported = now
        except LocalBackendError:
            raise
        except (httpx.HTTPError, OSError) as exc:
            raise LocalBackendError(f"下载 {artifact.label} 失败：{exc}") from exc

    try:
        _verify_downloaded_file(partial, artifact, progress, cancel)
    except LocalBackendDownloadCancelled:
        raise
    except LocalBackendError:
        partial.unlink(missing_ok=True)
        raise
    os.replace(partial, destination)
    _write_verification_marker(destination, artifact)
    progress("ready", artifact.label, artifact.size_bytes, artifact.size_bytes)
    return destination


def _safe_zip_members(archive: zipfile.ZipFile, destination: Path) -> Iterator[zipfile.ZipInfo]:
    destination = destination.resolve()
    for member in archive.infolist():
        relative = PurePosixPath(member.filename)
        if (
            relative.is_absolute()
            or ".." in relative.parts
            or any(":" in part for part in relative.parts)
        ):
            raise LocalBackendError(f"运行时压缩包包含不安全路径：{member.filename}")
        target = (destination / Path(*relative.parts)).resolve()
        try:
            target.relative_to(destination)
        except ValueError as exc:
            raise LocalBackendError(
                f"运行时压缩包路径越界：{member.filename}"
            ) from exc
        yield member


def _extract_runtime(
    root: Path,
    archives: tuple[Path, ...],
    *,
    cancel: threading.Event | None = None,
) -> None:
    runtime = _runtime_directory(root)
    runtime.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{LLAMA_CPP_VERSION}-", dir=runtime.parent))
    cancelled = cancel or threading.Event()
    try:
        for archive_path in archives:
            if cancelled.is_set():
                raise LocalBackendDownloadCancelled("下载已取消")
            try:
                with zipfile.ZipFile(archive_path) as archive:
                    for member in _safe_zip_members(archive, staging):
                        if cancelled.is_set():
                            raise LocalBackendDownloadCancelled("下载已取消")
                        relative = Path(*PurePosixPath(member.filename).parts)
                        target = staging / relative
                        if member.is_dir():
                            target.mkdir(parents=True, exist_ok=True)
                            continue
                        target.parent.mkdir(parents=True, exist_ok=True)
                        with archive.open(member) as source, target.open("wb") as output:
                            while chunk := source.read(4 * 1024 * 1024):
                                if cancelled.is_set():
                                    raise LocalBackendDownloadCancelled("下载已取消")
                                output.write(chunk)
            except (OSError, zipfile.BadZipFile) as exc:
                raise LocalBackendError(
                    f"无法解压 llama.cpp 运行时：{archive_path.name}（{exc}）"
                ) from exc

        executables = sorted(
            staging.rglob("llama-server.exe"),
            key=lambda path: (len(path.parts), str(path).casefold()),
        )
        if not executables:
            raise LocalBackendError("llama.cpp 运行时中没有 llama-server.exe")
        executable = executables[0]
        marker = {
            "version": LLAMA_CPP_VERSION,
            "stable_version": LLAMA_CPP_STABLE_VERSION,
            "server_executable": executable.relative_to(staging).as_posix(),
            "artifacts": {
                artifact.filename: artifact.sha256 for artifact in LLAMA_CPP_ARTIFACTS
            },
        }
        (staging / "runtime.json").write_text(
            json.dumps(marker, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        if runtime.exists():
            shutil.rmtree(runtime)
        os.replace(staging, runtime)
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)


def install_local_backend(
    root: Path,
    model_id: str,
    *,
    progress: ProgressCallback | None = None,
    cancel: threading.Event | None = None,
    http_transport: httpx.BaseTransport | None = None,
) -> None:
    """Download, verify and install the pinned runtime and one curated model."""
    assert_supported_platform()
    model = get_builtin_model(model_id)
    callback = progress or (lambda _phase, _label, _done, _total: None)
    cancelled = cancel or threading.Event()
    _check_free_space(root, required_install_space(root, model_id))
    if cancelled.is_set():
        raise LocalBackendDownloadCancelled("下载已取消")

    timeout = httpx.Timeout(connect=15.0, read=60.0, write=30.0, pool=30.0)
    with httpx.Client(
        follow_redirects=True,
        timeout=timeout,
        transport=http_transport,
        headers={
            "Accept-Encoding": "identity",
            "User-Agent": "RefraTranslator local backend downloader",
        },
    ) as client:
        if not runtime_is_ready(root):
            archives = tuple(
                _download_artifact(
                    _downloads_directory(root),
                    artifact,
                    client,
                    callback,
                    cancelled,
                )
                for artifact in LLAMA_CPP_ARTIFACTS
            )
            if cancelled.is_set():
                raise LocalBackendDownloadCancelled("下载已取消")
            callback("extract", "llama.cpp CUDA 运行时", 0, 1)
            _extract_runtime(root, archives, cancel=cancelled)
            callback("extract", "llama.cpp CUDA 运行时", 1, 1)
            for archive in archives:
                archive.unlink(missing_ok=True)
                _verification_path(archive).unlink(missing_ok=True)

        _download_artifact(
            _models_directory(root),
            model.artifact,
            client,
            callback,
            cancelled,
        )


def remove_builtin_model(root: Path, model_id: str) -> int:
    model = get_builtin_model(model_id)
    path = model_path(root, model)
    released = 0
    for candidate in (
        path,
        _verification_path(path),
        path.with_name(f"{path.name}.part"),
    ):
        try:
            released += candidate.stat().st_size
        except FileNotFoundError:
            continue
        candidate.unlink()
    return released


def assert_supported_platform() -> None:
    machine = platform.machine().lower()
    if sys.platform != "win32" or machine not in {"amd64", "x86_64"}:
        raise LocalBackendError("内置本地模型第一版仅支持 Windows x64")


def _free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


class ManagedLocalServer:
    """Own one loopback-only llama-server process for a single app run."""

    def __init__(
        self,
        root: Path,
        model_id: str,
        ocr_device: str,
        *,
        cuda_device: str = BUILTIN_CUDA_DEVICE_FOLLOW_OCR,
        parallel: int = 1,
        kv_cache_type: str = "f16",
        temperature: float = 0.2,
        startup_timeout_seconds: float = 180.0,
    ) -> None:
        self.root = root.resolve()
        self.model = get_builtin_model(model_id)
        self.ocr_device = ocr_device
        self.cuda_device = cuda_device
        self.parallel = parallel
        self.kv_cache_type = kv_cache_type
        self.temperature = temperature
        self.startup_timeout_seconds = startup_timeout_seconds
        self.port: int | None = None
        self.api_key = secrets.token_urlsafe(32)
        self.process: subprocess.Popen[bytes] | None = None

        if not 1 <= self.parallel <= BUILTIN_PARALLEL_MAX:
            raise LocalBackendError(
                f"内置 CUDA 并发必须在 1 到 {BUILTIN_PARALLEL_MAX} 之间"
            )
        if self.kv_cache_type not in BUILTIN_KV_CACHE_TYPES:
            raise LocalBackendError("内置 CUDA KV 缓存类型必须是 f16 或 q8_0")
        if not 0 <= self.temperature <= 2:
            raise LocalBackendError("内置 CUDA 温度必须在 0 到 2 之间")

    @property
    def total_context(self) -> int:
        return self.parallel * BUILTIN_CONTEXT_PER_SLOT

    @property
    def max_output_tokens(self) -> int:
        return BUILTIN_MAX_OUTPUT_TOKENS

    def _physical_cuda_device(self) -> str:
        device = (
            self.ocr_device
            if self.cuda_device == BUILTIN_CUDA_DEVICE_FOLLOW_OCR
            else self.cuda_device
        )
        prefix, separator, index = device.partition(":")
        if prefix != "gpu" or separator != ":" or not index.isdigit():
            raise LocalBackendError(
                "内置 CUDA 设备必须跟随 OCR 或指定为 gpu:N"
            )
        return device

    @property
    def command(self) -> tuple[str, ...]:
        executable = runtime_executable(self.root)
        if executable is None:
            raise LocalBackendError("llama.cpp CUDA 运行时尚未下载或校验失败")
        if not model_is_ready(self.root, self.model):
            raise LocalBackendError(f"内置模型尚未下载：{self.model.display_name}")
        if self.port is None:
            raise LocalBackendError("尚未分配本地服务端口")
        return (
            str(executable),
            "--model",
            str(model_path(self.root, self.model)),
            "--alias",
            self.model.model_id,
            "--host",
            "127.0.0.1",
            "--port",
            str(self.port),
            "--no-webui",
            "--jinja",
            "--offline",
            "--parallel",
            str(self.parallel),
            "--device",
            "CUDA0",
            "--gpu-layers",
            "all",
            "--ctx-size",
            str(self.total_context),
            "--no-kv-unified",
            "--cache-ram",
            "0",
            "--cache-type-k",
            self.kv_cache_type,
            "--cache-type-v",
            self.kv_cache_type,
            "--fit",
            "on",
            "--fit-target",
            "1024",
            "--split-mode",
            "none",
            "--main-gpu",
            "0",
            "--spec-type",
            "none",
            "--reasoning",
            "off",
            "--temp",
            str(self.temperature),
            "--top-k",
            "20",
            "--top-p",
            "0.6",
            "--repeat-penalty",
            "1.05",
        )

    def start(self) -> None:
        assert_supported_platform()
        if self.process is not None:
            raise LocalBackendError("内置本地模型服务已经启动")
        physical_cuda_device = self._physical_cuda_device()
        gpu_index = int(physical_cuda_device.split(":", 1)[1])

        self.port = _free_loopback_port()
        executable = runtime_executable(self.root)
        if executable is None:
            raise LocalBackendError("llama.cpp CUDA 运行时尚未下载或校验失败")
        environment = os.environ.copy()
        dll_directories = sorted(
            {str(path.parent) for path in _runtime_directory(self.root).rglob("*.dll")},
            key=str.casefold,
        )
        environment["PATH"] = os.pathsep.join(
            [*dll_directories, environment.get("PATH", "")]
        )
        environment["CUDA_VISIBLE_DEVICES"] = str(gpu_index)
        environment["LLAMA_API_KEY"] = self.api_key
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            self.process = subprocess.Popen(
                self.command,
                cwd=executable.parent,
                stdin=subprocess.DEVNULL,
                stdout=None,
                stderr=subprocess.STDOUT,
                env=environment,
                creationflags=creation_flags,
                close_fds=True,
            )
            self._wait_until_ready()
        except OSError as exc:
            self.close()
            raise LocalBackendError(f"无法启动 llama-server：{exc}") from exc
        except subprocess.SubprocessError as exc:
            self.close()
            raise LocalBackendError(f"llama-server 进程错误：{exc}") from exc
        except LocalBackendError:
            self.close()
            raise

    def _wait_until_ready(self) -> None:
        if self.process is None or self.port is None:
            raise LocalBackendError("内置本地模型服务没有成功创建")
        deadline = time.monotonic() + self.startup_timeout_seconds
        health_url = f"http://127.0.0.1:{self.port}/health"
        with httpx.Client(timeout=1.0) as client:
            while time.monotonic() < deadline:
                exit_code = self.process.poll()
                if exit_code is not None:
                    raise LocalBackendError(
                        f"llama-server 启动失败（退出码 {exit_code}），请查看实时日志"
                    )
                try:
                    response = client.get(health_url)
                except httpx.RequestError:
                    time.sleep(0.1)
                    continue
                if response.status_code == 200:
                    return
                if response.status_code != 503:
                    raise LocalBackendError(
                        "llama-server 健康检查失败："
                        f"HTTP {response.status_code} {response.text[:200]}"
                    )
                time.sleep(0.1)
        raise LocalBackendError(
            f"llama-server 在 {self.startup_timeout_seconds:g} 秒内未完成模型加载"
        )

    def effective_translation(self, original: TranslationConfig) -> TranslationConfig:
        if self.port is None or self.process is None or self.process.poll() is not None:
            raise LocalBackendError("内置本地模型服务尚未就绪")
        return replace(
            original,
            base_url=f"http://127.0.0.1:{self.port}/v1",
            model=self.model.model_id,
            timeout_seconds=max(original.timeout_seconds, 60.0),
            max_concurrency=self.parallel,
            max_output_tokens=self.max_output_tokens,
            temperature=self.temperature,
            top_p=0.6,
            api_key=self.api_key,
        )

    def close(self) -> None:
        process = self.process
        self.process = None
        if process is None or process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5.0)

    def __enter__(self) -> ManagedLocalServer:
        self.start()
        return self

    def __exit__(self, _exc_type, _exc, _traceback) -> None:
        self.close()


@contextmanager
def managed_translation_backend(
    config: AppConfig,
    config_path: str | Path,
) -> Iterator[AppConfig]:
    if config.translation.backend == "external":
        yield config
        return
    root = local_backend_root(config_path)
    server = ManagedLocalServer(
        root,
        config.translation.builtin_model,
        config.ocr.device,
        cuda_device=config.translation.builtin_cuda_device,
        parallel=config.translation.builtin_parallel,
        kv_cache_type=config.translation.builtin_kv_cache_type,
        temperature=config.translation.builtin_temperature,
    )
    with server:
        yield replace(
            config,
            translation=server.effective_translation(config.translation),
        )
