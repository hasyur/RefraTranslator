from __future__ import annotations

import os
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from game_screen_translator.branding import API_KEY_ENV, LEGACY_API_KEY_ENV


class ConfigError(ValueError):
    """Raised when a local configuration file is invalid."""


DEFAULT_DARK_OVERLAY_OPACITY = 0.55
DEFAULT_BROWSER_OVERLAY_PORT = 47831
CAPTURE_FPS_PER_CHANGE_POLL = 2
MAX_CAPTURE_FPS = 240
MAX_CHANGE_POLL_FPS = MAX_CAPTURE_FPS // CAPTURE_FPS_PER_CHANGE_POLL
BUILTIN_CUDA_DEVICE_FOLLOW_OCR = "follow_ocr"
BUILTIN_CONTEXT_PER_SLOT = 2048
BUILTIN_MAX_OUTPUT_TOKENS = 512
BUILTIN_PARALLEL_MAX = 32
BUILTIN_KV_CACHE_TYPES = frozenset({"f16", "q8_0"})


@dataclass(frozen=True, slots=True)
class TranslationConfig:
    base_url: str
    model: str
    target_language: str = "简体中文"
    timeout_seconds: float = 5.0
    max_concurrency: int = 2
    temperature: float = 0.7
    top_p: float = 0.6
    max_output_tokens: int = 2048
    api_key: str = field(default="", repr=False)
    api_key_env: str = API_KEY_ENV
    backend: str = "external"
    builtin_model: str = "Hy-MT2-1.8B-Q8_0.gguf"
    builtin_cuda_device: str = BUILTIN_CUDA_DEVICE_FOLLOW_OCR
    builtin_parallel: int = 1
    builtin_kv_cache_type: str = "f16"
    builtin_temperature: float = 0.2

    def __post_init__(self) -> None:
        if not isinstance(self.backend, str) or self.backend not in {
            "external",
            "builtin",
        }:
            raise ConfigError("translation.backend 必须是 external 或 builtin")
        if not isinstance(self.builtin_model, str) or not self.builtin_model.strip():
            raise ConfigError("translation.builtin_model 不能为空")
        if not isinstance(self.builtin_cuda_device, str) or (
            self.builtin_cuda_device != BUILTIN_CUDA_DEVICE_FOLLOW_OCR
            and re.fullmatch(r"gpu:\d+", self.builtin_cuda_device) is None
        ):
            raise ConfigError(
                "translation.builtin_cuda_device 必须是 follow_ocr 或 gpu:N"
            )
        if (
            not isinstance(self.builtin_parallel, int)
            or isinstance(self.builtin_parallel, bool)
            or not 1 <= self.builtin_parallel <= BUILTIN_PARALLEL_MAX
        ):
            raise ConfigError(
                "translation.builtin_parallel 必须在 "
                f"1 到 {BUILTIN_PARALLEL_MAX} 之间"
            )
        if (
            not isinstance(self.builtin_kv_cache_type, str)
            or self.builtin_kv_cache_type not in BUILTIN_KV_CACHE_TYPES
        ):
            raise ConfigError(
                "translation.builtin_kv_cache_type 必须是 f16 或 q8_0"
            )
        if not isinstance(self.builtin_temperature, (int, float)) or isinstance(
            self.builtin_temperature, bool
        ):
            raise ConfigError("translation.builtin_temperature 必须是数字")
        if not 0 <= self.builtin_temperature <= 2:
            raise ConfigError("translation.builtin_temperature 必须在 0 到 2 之间")
        if not self.base_url.startswith(("http://", "https://")):
            raise ConfigError("translation.base_url 必须以 http:// 或 https:// 开头")
        if not self.model.strip():
            raise ConfigError("translation.model 不能为空")
        if self.timeout_seconds <= 0:
            raise ConfigError("translation.timeout_seconds 必须大于 0")
        if not 1 <= self.max_concurrency <= 32:
            raise ConfigError("translation.max_concurrency 必须在 1 到 32 之间")
        if not 0 <= self.temperature <= 2:
            raise ConfigError("translation.temperature 必须在 0 到 2 之间")
        if not 0 < self.top_p <= 1:
            raise ConfigError("translation.top_p 必须在 0 到 1 之间")
        if self.max_output_tokens < 1:
            raise ConfigError("translation.max_output_tokens 必须大于 0")
        if not isinstance(self.api_key, str):
            raise ConfigError("translation.api_key 必须是字符串")
        if not isinstance(self.api_key_env, str) or not self.api_key_env.strip():
            raise ConfigError("translation.api_key_env 不能为空")
        object.__setattr__(self, "api_key", self.api_key.strip())
        object.__setattr__(self, "api_key_env", self.api_key_env.strip())
        object.__setattr__(self, "builtin_model", self.builtin_model.strip())
        object.__setattr__(
            self,
            "builtin_cuda_device",
            self.builtin_cuda_device.strip(),
        )
        object.__setattr__(
            self,
            "builtin_kv_cache_type",
            self.builtin_kv_cache_type.strip(),
        )

    @property
    def builtin_total_context(self) -> int:
        return self.builtin_parallel * BUILTIN_CONTEXT_PER_SLOT

    @property
    def builtin_max_output_tokens(self) -> int:
        return BUILTIN_MAX_OUTPUT_TOKENS

    @property
    def normalized_base_url(self) -> str:
        return self.base_url.rstrip("/") + "/"

    @property
    def resolved_api_key(self) -> str | None:
        if self.api_key:
            return self.api_key
        value = os.getenv(self.api_key_env, "").strip()
        if not value and self.api_key_env == API_KEY_ENV:
            value = os.getenv(LEGACY_API_KEY_ENV, "").strip()
        return value or None


@dataclass(frozen=True, slots=True)
class OcrConfig:
    language: str = "japan"
    min_score: float = 0.60
    cache_dir: str = ".cache/paddlex"
    detection_model: str = "PP-OCRv6_small_det"
    recognition_model: str = "PP-OCRv6_small_rec"
    model_source: str = "bos"
    device: str = "gpu:0"
    detection_max_side: int = 1280
    text_filter_enabled: bool = True
    text_merge_enabled: bool = True
    text_merge_llm_arbitration_enabled: bool = True
    translate_latin: bool = True
    translate_han_only: bool = False

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
        if re.fullmatch(r"gpu:\d+", self.device) is None:
            raise ConfigError(
                "ocr.device 仅支持 NVIDIA GPU，必须是 gpu:N（例如 gpu:0）"
            )
        if not 320 <= self.detection_max_side <= 4096:
            raise ConfigError("ocr.detection_max_side 必须在 320 到 4096 之间")
        for key, value in (
            ("text_filter_enabled", self.text_filter_enabled),
            ("text_merge_enabled", self.text_merge_enabled),
            (
                "text_merge_llm_arbitration_enabled",
                self.text_merge_llm_arbitration_enabled,
            ),
            ("translate_latin", self.translate_latin),
            ("translate_han_only", self.translate_han_only),
        ):
            if type(value) is not bool:
                raise ConfigError(f"ocr.{key} 必须是 true 或 false")


@dataclass(frozen=True, slots=True)
class PreviewConfig:
    # A positive value is the minimum radius. Rendering raises it adaptively
    # to 8-18 pixels from the OCR-region height so existing configs also hide
    # source glyphs strongly enough after switching to direct frame blur.
    blur_radius: float = 8.0
    # 0 means blur only. The launcher exposes 0 and the historical 0.55 dark
    # layer as two named modes instead of asking users to tune this number.
    overlay_opacity: float = DEFAULT_DARK_OVERLAY_OPACITY
    font_path: str = ""

    def __post_init__(self) -> None:
        if self.blur_radius < 0:
            raise ConfigError("preview.blur_radius 不能为负数")
        if not 0 <= self.overlay_opacity <= 1:
            raise ConfigError("preview.overlay_opacity 必须在 0 到 1 之间")


@dataclass(frozen=True, slots=True)
class RecordingConfig:
    browser_overlay_enabled: bool = False
    browser_overlay_port: int = DEFAULT_BROWSER_OVERLAY_PORT

    def __post_init__(self) -> None:
        if type(self.browser_overlay_enabled) is not bool:
            raise ConfigError("recording.browser_overlay_enabled 必须是 true 或 false")
        if (
            type(self.browser_overlay_port) is not int
            or not 1024 <= self.browser_overlay_port <= 65_535
        ):
            raise ConfigError(
                "recording.browser_overlay_port 必须在 1024 到 65535 之间"
            )

    @property
    def browser_overlay_url(self) -> str:
        return f"http://127.0.0.1:{self.browser_overlay_port}/overlay"


@dataclass(frozen=True, slots=True)
class LiveConfig:
    left: int = 0
    top: int = 0
    width: int = 0
    height: int = 0
    monitor_index: int = 0
    # Retained as a load-compatible field for older config.toml files.  The
    # effective value is always derived from change_poll_fps in __post_init__.
    capture_fps: int = 12
    change_poll_fps: int = 6
    change_threshold: float = 3.0
    stable_observations: int = 1
    stable_ms: int = 0
    clear_after_ms: int = 900
    context_pairs: int = 8
    max_batch_size: int = 8
    capture_backend: str = "dxgi"
    ocr_cooldown_ms: int = 0
    settle_rescan_ms: int = 500
    idle_rescan_ms: int = 2000
    dynamic_roi_enabled: bool = False
    debug_border: bool = False
    dynamic_roi_response_target_ms: int = 500
    # Load-compatible legacy tuning fields. The adaptive response target is
    # the user-facing control; these values remain accepted for old configs.
    dynamic_roi_settle_ms: int = 180
    dynamic_roi_ocr_interval_ms: int = 333
    dynamic_roi_max_coalesce_ms: int = 333

    def __post_init__(self) -> None:
        if self.left < 0 or self.top < 0:
            raise ConfigError("live.left/top 不能为负数")
        if self.width < 0 or self.height < 0:
            raise ConfigError("live.width/height 不能为负数")
        if self.monitor_index < 0:
            raise ConfigError("live.monitor_index 不能为负数")
        if (
            type(self.change_poll_fps) is not int
            or not 1 <= self.change_poll_fps <= MAX_CHANGE_POLL_FPS
        ):
            raise ConfigError(
                f"live.change_poll_fps 必须在 1 到 {MAX_CHANGE_POLL_FPS} 之间"
            )
        object.__setattr__(
            self,
            "capture_fps",
            self.change_poll_fps * CAPTURE_FPS_PER_CHANGE_POLL,
        )
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
        if not 0 <= self.settle_rescan_ms <= 60_000:
            raise ConfigError("live.settle_rescan_ms 必须在 0 到 60000 之间")
        if not 0 <= self.idle_rescan_ms <= 60_000:
            raise ConfigError("live.idle_rescan_ms 必须在 0 到 60000 之间")
        if type(self.dynamic_roi_enabled) is not bool:
            raise ConfigError("live.dynamic_roi_enabled 必须是 true 或 false")
        if type(self.debug_border) is not bool:
            raise ConfigError("live.debug_border 必须是 true 或 false")
        if not 100 <= self.dynamic_roi_response_target_ms <= 5_000:
            raise ConfigError(
                "live.dynamic_roi_response_target_ms 必须在 100 到 5000 之间"
            )
        if not 0 <= self.dynamic_roi_settle_ms <= 10_000:
            raise ConfigError("live.dynamic_roi_settle_ms 必须在 0 到 10000 之间")
        if not 50 <= self.dynamic_roi_ocr_interval_ms <= 10_000:
            raise ConfigError(
                "live.dynamic_roi_ocr_interval_ms 必须在 50 到 10000 之间"
            )
        if not 50 <= self.dynamic_roi_max_coalesce_ms <= 10_000:
            raise ConfigError(
                "live.dynamic_roi_max_coalesce_ms 必须在 50 到 10000 之间"
            )


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
    recording: RecordingConfig = RecordingConfig()
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

    translation_values = dict(_section(data, "translation"))
    if not translation_values:
        raise ConfigError("缺少必需的 [translation] 配置")
    # `provider` was formerly a single-value selector. Keep loading old
    # config files, but do not carry this dead setting into runtime state.
    legacy_provider = translation_values.pop("provider", None)
    if legacy_provider is not None and (
        not isinstance(legacy_provider, str)
        or legacy_provider != "openai_compatible"
    ):
        raise ConfigError(
            f"暂不支持 translation.provider={legacy_provider!r}"
        )

    return AppConfig(
        translation=_build(TranslationConfig, translation_values, "translation"),
        ocr=_build(OcrConfig, _section(data, "ocr"), "ocr"),
        preview=_build(PreviewConfig, _section(data, "preview"), "preview"),
        recording=_build(RecordingConfig, _section(data, "recording"), "recording"),
        live=_build(LiveConfig, _section(data, "live"), "live"),
        profiles=_build(ProfileConfig, _section(data, "profiles"), "profiles"),
    )
