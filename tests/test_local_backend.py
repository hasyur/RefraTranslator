from __future__ import annotations

import hashlib
import io
import json
import threading
import zipfile
from pathlib import Path

import httpx
import pytest

from game_screen_translator.config import TranslationConfig
from game_screen_translator.translation import local_backend
from game_screen_translator.translation.local_backend import (
    BUILTIN_MODELS,
    HY_MT2_1_8B_REVISION,
    HY_MT2_7B_REVISION,
    LLAMA_CPP_ARTIFACTS,
    LLAMA_CPP_STABLE_VERSION,
    LLAMA_CPP_VERSION,
    DownloadArtifact,
    LocalBackendError,
    ManagedLocalServer,
)


def _artifact(label: str, filename: str, content: bytes) -> DownloadArtifact:
    return DownloadArtifact(
        label=label,
        filename=filename,
        url=f"https://downloads.test/{filename}",
        size_bytes=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
    )


def _zip_bytes(files: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return output.getvalue()


def test_curated_catalog_pins_stable_cuda_runtime_and_modelscope_models() -> None:
    assert LLAMA_CPP_VERSION == "b10621"
    assert LLAMA_CPP_STABLE_VERSION == "v0.3.0"
    assert HY_MT2_1_8B_REVISION == "00451019639c4214392db1f02a9ee824e223f1e4"
    assert HY_MT2_7B_REVISION == "47b1dd35c1f984e23ec7b3c72e5d01620dce8f40"
    assert [artifact.size_bytes for artifact in LLAMA_CPP_ARTIFACTS] == [
        250_464_283,
        391_443_627,
    ]
    assert [model.model_id for model in BUILTIN_MODELS] == [
        "Hy-MT2-1.8B-Q8_0.gguf",
        "Hy-MT2-7B-Q4_K_M.gguf",
    ]
    assert [model.artifact.size_bytes for model in BUILTIN_MODELS] == [
        1_908_528_192,
        4_624_648_896,
    ]
    assert all(
        model.artifact.url.startswith(
            "https://www.modelscope.cn/models/Tencent-Hunyuan/"
        )
        for model in BUILTIN_MODELS
    )
    assert all("/resolve/master/" not in model.artifact.url for model in BUILTIN_MODELS)
    assert all(len(item.sha256) == 64 for item in LLAMA_CPP_ARTIFACTS)
    assert all(len(model.artifact.sha256) == 64 for model in BUILTIN_MODELS)


def test_artifact_download_resumes_and_marks_verified(tmp_path: Path) -> None:
    content = b"abcdefgh"
    artifact = _artifact("fixture", "fixture.bin", content)
    partial = tmp_path / "fixture.bin.part"
    partial.write_bytes(content[:4])
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            206,
            headers={"Content-Range": "bytes 4-7/8"},
            content=content[4:],
        )

    events = []
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        destination = local_backend._download_artifact(
            tmp_path,
            artifact,
            client,
            lambda *event: events.append(event),
            threading.Event(),
        )

    assert requests[0].headers["Range"] == "bytes=4-"
    assert destination.read_bytes() == content
    assert not partial.exists()
    marker = json.loads(
        destination.with_name("fixture.bin.verified.json").read_text(
            encoding="utf-8"
        )
    )
    assert marker["sha256"] == artifact.sha256
    assert {event[0] for event in events} >= {"download", "verify", "ready"}

    destination.write_bytes(b"abcdEfgh")
    assert not local_backend._artifact_is_verified(destination, artifact)


def test_artifact_download_rejects_bad_hash_and_discards_partial(
    tmp_path: Path,
) -> None:
    artifact = _artifact("fixture", "fixture.bin", b"expected")

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"corrupt!")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(LocalBackendError, match="SHA-256"):
            local_backend._download_artifact(
                tmp_path,
                artifact,
                client,
                lambda *_event: None,
                threading.Event(),
            )

    assert not (tmp_path / "fixture.bin").exists()
    assert not (tmp_path / "fixture.bin.part").exists()


def test_artifact_download_cancellation_keeps_partial_for_resume(
    tmp_path: Path,
) -> None:
    chunk_size = 1024 * 1024
    content = b"a" * chunk_size + b"b" * chunk_size
    artifact = _artifact("fixture", "fixture.bin", content)
    cancel = threading.Event()

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=content)

    def progress(phase: str, _label: str, completed: int, _total: int) -> None:
        if phase == "download" and completed == chunk_size:
            cancel.set()

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(local_backend.LocalBackendDownloadCancelled):
            local_backend._download_artifact(
                tmp_path,
                artifact,
                client,
                progress,
                cancel,
            )

    partial = tmp_path / "fixture.bin.part"
    assert partial.stat().st_size == chunk_size
    assert partial.read_bytes() == content[:chunk_size]


def test_runtime_extraction_merges_archives_and_rejects_path_traversal(
    tmp_path: Path,
) -> None:
    server_zip = tmp_path / "server.zip"
    cuda_zip = tmp_path / "cuda.zip"
    server_zip.write_bytes(
        _zip_bytes(
            {
                "bin/llama-server.exe": b"server",
                "bin/ggml.dll": b"ggml",
            }
        )
    )
    cuda_zip.write_bytes(_zip_bytes({"bin/cudart64_12.dll": b"cuda"}))

    local_backend._extract_runtime(tmp_path / "store", (server_zip, cuda_zip))

    executable = local_backend.runtime_executable(tmp_path / "store")
    assert executable is not None
    assert executable.read_bytes() == b"server"
    assert (executable.parent / "cudart64_12.dll").read_bytes() == b"cuda"

    unsafe_zip = tmp_path / "unsafe.zip"
    unsafe_zip.write_bytes(_zip_bytes({"../outside.txt": b"no"}))
    with pytest.raises(LocalBackendError, match="不安全路径"):
        local_backend._extract_runtime(tmp_path / "unsafe-store", (unsafe_zip,))
    assert not (tmp_path / "outside.txt").exists()


def test_runtime_extraction_honors_cancellation(tmp_path: Path) -> None:
    server_zip = tmp_path / "server.zip"
    server_zip.write_bytes(_zip_bytes({"llama-server.exe": b"server"}))
    cancel = threading.Event()
    cancel.set()

    with pytest.raises(local_backend.LocalBackendDownloadCancelled):
        local_backend._extract_runtime(
            tmp_path / "store",
            (server_zip,),
            cancel=cancel,
        )

    assert not local_backend._runtime_directory(tmp_path / "store").exists()


def test_remove_builtin_model_deletes_completed_and_partial_files(
    tmp_path: Path,
) -> None:
    model = BUILTIN_MODELS[0]
    path = local_backend.model_path(tmp_path, model)
    path.parent.mkdir(parents=True)
    path.write_bytes(b"complete")
    local_backend._verification_path(path).write_bytes(b"marker")
    path.with_name(f"{path.name}.part").write_bytes(b"partial")

    released = local_backend.remove_builtin_model(tmp_path, model.model_id)

    assert released == len(b"complete") + len(b"marker") + len(b"partial")
    assert not path.exists()
    assert not local_backend._verification_path(path).exists()
    assert not path.with_name(f"{path.name}.part").exists()


def test_managed_server_is_loopback_only_cuda_scoped_and_ephemeral(
    tmp_path: Path,
    monkeypatch,
) -> None:
    executable = tmp_path / "runtime" / "llama-server.exe"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"")
    model_file = tmp_path / "model.gguf"
    model_file.write_bytes(b"")
    process_calls = []

    class FakeProcess:
        def __init__(self) -> None:
            self.return_code = None
            self.terminated = False

        def poll(self):
            return self.return_code

        def terminate(self) -> None:
            self.terminated = True
            self.return_code = 0

        def wait(self, timeout=None):
            return self.return_code

        def kill(self) -> None:
            self.return_code = -9

    process = FakeProcess()

    def fake_popen(command, **kwargs):
        process_calls.append((command, kwargs))
        return process

    class FakeHealthClient:
        def __init__(self, **_kwargs) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            pass

        def get(self, url: str) -> httpx.Response:
            assert url == "http://127.0.0.1:54321/health"
            return httpx.Response(200)

    monkeypatch.setattr(local_backend, "assert_supported_platform", lambda: None)
    monkeypatch.setattr(local_backend, "runtime_executable", lambda _root: executable)
    monkeypatch.setattr(local_backend, "model_is_ready", lambda _root, _model: True)
    monkeypatch.setattr(local_backend, "model_path", lambda _root, _model: model_file)
    monkeypatch.setattr(local_backend, "_free_loopback_port", lambda: 54321)
    monkeypatch.setattr(local_backend.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(local_backend.httpx, "Client", FakeHealthClient)

    server = ManagedLocalServer(
        tmp_path,
        "Hy-MT2-1.8B-Q8_0.gguf",
        "gpu:2",
    )
    server.start()

    command, kwargs = process_calls[0]
    assert command[command.index("--host") + 1] == "127.0.0.1"
    assert command[command.index("--port") + 1] == "54321"
    assert command[command.index("--parallel") + 1] == "1"
    assert command[command.index("--device") + 1] == "CUDA0"
    assert command[command.index("--gpu-layers") + 1] == "all"
    assert command[command.index("--ctx-size") + 1] == "8192"
    assert "--no-webui" in command
    assert "--offline" in command
    assert "--jinja" in command
    assert "--fit-target" in command
    assert "--top-k" in command
    assert server.api_key not in command
    assert kwargs["env"]["LLAMA_API_KEY"] == server.api_key
    assert kwargs["env"]["CUDA_VISIBLE_DEVICES"] == "2"

    effective = server.effective_translation(
        TranslationConfig(
            provider="openai_compatible",
            base_url="https://external.test/v1",
            model="external-model",
            api_key="external-secret",
            temperature=1.5,
            top_p=0.9,
        )
    )
    assert effective.base_url == "http://127.0.0.1:54321/v1"
    assert effective.model == "Hy-MT2-1.8B-Q8_0.gguf"
    assert effective.max_concurrency == 1
    assert effective.max_output_tokens == 4096
    assert effective.temperature == 0.7
    assert effective.top_p == 0.6
    assert effective.api_key == server.api_key

    server.close()
    assert process.terminated
