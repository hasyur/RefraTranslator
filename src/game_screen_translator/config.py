from __future__ import annotations

import json
import os
import re
import tomllib
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Mapping


class ConfigError(ValueError):
    """Raised when a local configuration file is invalid."""


@dataclass(frozen=True, slots=True)
class TranslationConfig:
    provider: str
    base_url: str
    model: str
    target_language: str = "简体中文"
    timeout_seconds: float = 5.0
    max_concurrency: int = 2
    temperature: float = 0.7
    top_p: float = 0.6
    max_output_tokens: int = 2048
    api_key_env: str = "GAME_SCREEN_TRANSLATOR_API_KEY"

    def __post_init__(self) -> None:
        if self.provider != "openai_compatible":
            raise ConfigError(f"暂不支持 translation.provider={self.provider!r}")
        if not self.base_url.startswith(("http://", "https://")):
            raise ConfigError("translation.base_url 必须以 http:// 或 https:// 开头")
        if not self.model.strip():
            raise ConfigError("translation.model 不能为空")
        if self.timeout_seconds <= 0:
            raise ConfigError("translation.timeout_seconds 必须大于 0")
        if self.max_concurrency < 1:
            raise ConfigError("translation.max_concurrency 必须至少为 1")
        if not 0 <= self.temperature <= 2:
            raise ConfigError("translation.temperature 必须在 0 到 2 之间")
        if not 0 < self.top_p <= 1:
            raise ConfigError("translation.top_p 必须在 0 到 1 之间")
        if self.max_output_tokens < 1:
            raise ConfigError("translation.max_output_tokens 必须大于 0")

    @property
    def normalized_base_url(self) -> str:
        return self.base_url.rstrip("/") + "/"

    @property
    def api_key(self) -> str | None:
        value = os.getenv(self.api_key_env, "").strip()
        return value or None


@dataclass(frozen=True, slots=True)
class OcrConfig:
    language: str = "japan"
    min_score: float = 0.60
    cache_dir: str = ".cache/paddlex"
    detection_model: str = "PP-OCRv6_small_det"
    recognition_model: str = "PP-OCRv6_small_rec"
    model_source: str = "bos"
    cpu_threads: int = 2
    detection_max_side: int = 1280

    def __post_init__(self) -> None:
        if not self.language.strip():
            raise ConfigError("ocr.language 不能为空")
        if not 0 <= self.min_score <= 1:
            raise ConfigError("ocr.min_score 必须在 0 到 1 之间")
        if not self.cache_dir.strip():
            raise ConfigError("ocr.cache_dir 不能为空")
        if not self.detection_model.strip() or not self.recognition_model.strip():
            raise ConfigError("OCR 检测和识别模型名称均不能为空")
        if self.model_source not in {"bos", "huggingface", "modelscope", "aistudio"}:
            raise ConfigError("ocr.model_source 必须是 bos/huggingface/modelscope/aistudio")
        if not 1 <= self.cpu_threads <= 32:
            raise ConfigError("ocr.cpu_threads 必须在 1 到 32 之间")
        if not 320 <= self.detection_max_side <= 4096:
            raise ConfigError("ocr.detection_max_side 必须在 320 到 4096 之间")


@dataclass(frozen=True, slots=True)
class PreviewConfig:
    blur_radius: float = 8.0
    overlay_opacity: float = 0.55
    font_path: str = ""

    def __post_init__(self) -> None:
        if self.blur_radius < 0:
            raise ConfigError("preview.blur_radius 不能为负数")
        if not 0 <= self.overlay_opacity <= 1:
            raise ConfigError("preview.overlay_opacity 必须在 0 到 1 之间")


@dataclass(frozen=True, slots=True)
class LiveConfig:
    left: int = 0
    top: int = 0
    width: int = 0
    height: int = 0
    monitor_index: int = 0
    capture_fps: int = 15
    change_poll_fps: int = 6
    change_threshold: float = 3.0
    stable_observations: int = 2
    stable_ms: int = 150
    clear_after_ms: int = 900
    context_pairs: int = 8
    max_batch_size: int = 8
    capture_backend: str = "dxgi"
    ocr_cooldown_ms: int = 350

    def __post_init__(self) -> None:
        if self.left < 0 or self.top < 0:
            raise ConfigError("live.left/top 不能为负数")
        if self.width < 0 or self.height < 0:
            raise ConfigError("live.width/height 不能为负数")
        if self.monitor_index < 0:
            raise ConfigError("live.monitor_index 不能为负数")
        if not 1 <= self.capture_fps <= 240:
            raise ConfigError("live.capture_fps 必须在 1 到 240 之间")
        if not 1 <= self.change_poll_fps <= self.capture_fps:
            raise ConfigError("live.change_poll_fps 必须在 1 到 capture_fps 之间")
        if self.change_threshold < 0:
            raise ConfigError("live.change_threshold 不能为负数")
        if self.stable_observations < 1:
            raise ConfigError("live.stable_observations 必须至少为 1")
        if self.stable_ms < 0 or self.clear_after_ms < 0:
            raise ConfigError("live.stable_ms/clear_after_ms 不能为负数")
        if self.context_pairs < 0:
            raise ConfigError("live.context_pairs 不能为负数")
        if self.max_batch_size < 1:
            raise ConfigError("live.max_batch_size 必须至少为 1")
        if self.capture_backend not in {"dxgi", "winrt"}:
            raise ConfigError("live.capture_backend 必须是 dxgi 或 winrt")
        if not 0 <= self.ocr_cooldown_ms <= 10_000:
            raise ConfigError("live.ocr_cooldown_ms 必须在 0 到 10000 之间")


@dataclass(frozen=True, slots=True)
class ProfileConfig:
    root_dir: str = "profiles"

    def __post_init__(self) -> None:
        value = self.root_dir.strip()
        path = Path(value)
        if not value:
            raise ConfigError("profiles.root_dir 不能为空")
        if path.is_absolute() or ".." in path.parts:
            raise ConfigError("profiles.root_dir 必须是配置文件目录内的相对路径")


@dataclass(frozen=True, slots=True)
class AppConfig:
    translation: TranslationConfig
    ocr: OcrConfig = OcrConfig()
    preview: PreviewConfig = PreviewConfig()
    live: LiveConfig = LiveConfig()
    profiles: ProfileConfig = ProfileConfig()


def _section(data: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    section = data.get(name, {})
    if not isinstance(section, Mapping):
        raise ConfigError(f"[{name}] 必须是 TOML 表")
    return section


def _build(cls: type[Any], values: Mapping[str, Any], section_name: str) -> Any:
    try:
        return cls(**dict(values))
    except TypeError as exc:
        raise ConfigError(f"[{section_name}] 含有未知字段或字段类型错误：{exc}") from exc


def load_config(path: str | Path = "config.toml") -> AppConfig:
    config_path = Path(path)
    if not config_path.is_file():
        raise ConfigError(
            f"找不到配置文件：{config_path}。请复制 config.example.toml 为 config.toml。"
        )

    try:
        with config_path.open("rb") as handle:
            data = tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"TOML 格式错误：{exc}") from exc

    if not isinstance(data, Mapping):
        raise ConfigError("配置文件根节点必须是 TOML 表")

    translation_values = _section(data, "translation")
    if not translation_values:
        raise ConfigError("缺少必需的 [translation] 配置")

    return AppConfig(
        translation=_build(TranslationConfig, translation_values, "translation"),
        ocr=_build(OcrConfig, _section(data, "ocr"), "ocr"),
        preview=_build(PreviewConfig, _section(data, "preview"), "preview"),
        live=_build(LiveConfig, _section(data, "live"), "live"),
        profiles=_build(ProfileConfig, _section(data, "profiles"), "profiles"),
    )


_TOML_SECTION_RE = re.compile(
    r"^[ \t]*\[([^\[\]\r\n]+)\][ \t]*(?:#.*)?$"
)
_TRANSLATION_VALUE_RE = re.compile(
    r"^(?P<indent>[ \t]*)(?P<key>base_url|model)[ \t]*="
)


def save_translation_selection(
    path: str | Path,
    *,
    base_url: str,
    model: str,
) -> AppConfig:
    """Atomically update only the local translation endpoint and model."""
    config_path = Path(path).resolve()
    current = load_config(config_path)
    candidate_translation = replace(
        current.translation,
        base_url=base_url.strip(),
        model=model.strip(),
    )
    if candidate_translation == current.translation:
        return current

    with config_path.open("r", encoding="utf-8", newline="") as handle:
        lines = handle.readlines()
    current_section: str | None = None
    replaced_keys: set[str] = set()
    values = {
        "base_url": candidate_translation.base_url,
        "model": candidate_translation.model,
    }
    for index, line in enumerate(lines):
        if line.endswith("\r\n"):
            body, ending = line[:-2], "\r\n"
        elif line.endswith("\n"):
            body, ending = line[:-1], "\n"
        else:
            body, ending = line, ""
        section_match = _TOML_SECTION_RE.fullmatch(body)
        if section_match is not None:
            current_section = section_match.group(1).strip()
            continue
        if current_section != "translation":
            continue
        value_match = _TRANSLATION_VALUE_RE.match(body)
        if value_match is None:
            continue
        key = value_match.group("key")
        lines[index] = (
            f'{value_match.group("indent")}{key} = '
            f'{json.dumps(values[key], ensure_ascii=False)}{ending}'
        )
        replaced_keys.add(key)

    missing = {"base_url", "model"} - replaced_keys
    if missing:
        raise ConfigError(
            "[translation] 缺少无法更新的字段："
            + ", ".join(sorted(missing))
        )

    temporary = config_path.with_name(f"{config_path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="") as handle:
            handle.writelines(lines)
        validated = load_config(temporary)
        os.replace(temporary, config_path)
    finally:
        temporary.unlink(missing_ok=True)
    return validated
