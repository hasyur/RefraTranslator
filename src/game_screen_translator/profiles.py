from __future__ import annotations

import hashlib
import json
import os
import tempfile
import tomllib
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

from game_screen_translator.config import AppConfig, LiveConfig
from game_screen_translator.domain import GlossaryEntry
from game_screen_translator.translation.cache import (
    TranslationCache,
    normalize_source_text,
)


PROFILE_VERSION = 1
_WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}


class ProfileError(ValueError):
    """Raised when a per-game profile is invalid or unavailable."""


@dataclass(frozen=True, slots=True)
class ProfileCaptureSettings:
    monitor_index: int | None = None
    region: tuple[int, int, int, int] | None = None

    def __post_init__(self) -> None:
        if self.monitor_index is not None:
            if type(self.monitor_index) is not int or self.monitor_index < 0:
                raise ProfileError("Profile 显示器索引必须是非负整数")
        if self.region is not None:
            if (
                len(self.region) != 4
                or any(type(value) is not int for value in self.region)
                or any(value < 0 for value in self.region)
            ):
                raise ProfileError("Profile 捕获区域必须是四个非负整数")


def validate_profile_id(profile_id: str) -> str:
    value = profile_id.strip()
    if not value or len(value) > 80:
        raise ProfileError("Profile ID 必须为 1 到 80 个字符")
    if not all(character.isalnum() or character in {"-", "_"} for character in value):
        raise ProfileError("Profile ID 只能包含文字、数字、连字符和下划线")
    if value.upper() in _WINDOWS_RESERVED_NAMES:
        raise ProfileError(f"Profile ID 不能使用 Windows 保留名称：{value}")
    return value


def resolve_profiles_root(config_path: Path, config: AppConfig) -> Path:
    base = config_path.resolve().parent
    root = (base / config.profiles.root_dir).resolve()
    try:
        root.relative_to(base)
    except ValueError as exc:
        raise ProfileError("Profile 根目录必须位于配置文件目录内") from exc
    return root


@dataclass(frozen=True, slots=True)
class GameProfile:
    profile_id: str
    display_name: str
    directory: Path
    glossary: tuple[GlossaryEntry, ...]
    glossary_revision: str
    capture_settings: ProfileCaptureSettings
    cache: TranslationCache

    @property
    def manifest_path(self) -> Path:
        return self.directory / "profile.toml"

    @property
    def glossary_path(self) -> Path:
        return self.directory / "glossary.toml"

    @property
    def database_path(self) -> Path:
        return self.directory / "translations.sqlite3"

    @property
    def settings_path(self) -> Path:
        return self.directory / "settings.toml"


def _read_toml(path: Path, label: str) -> Mapping[str, Any]:
    if not path.is_file():
        raise ProfileError(f"{label}不存在：{path}")
    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise ProfileError(f"{label} TOML 格式错误：{exc}") from exc
    if not isinstance(data, Mapping):
        raise ProfileError(f"{label}根节点必须是 TOML 表")
    return data


def _load_glossary(path: Path) -> tuple[tuple[GlossaryEntry, ...], str]:
    data = _read_toml(path, "术语表")
    unknown_root = set(data) - {"terms"}
    if unknown_root:
        raise ProfileError(f"术语表包含未知字段：{sorted(unknown_root)}")
    raw_terms = data.get("terms", [])
    if not isinstance(raw_terms, list):
        raise ProfileError("glossary.toml 的 [[terms]] 必须是数组表")

    entries: list[GlossaryEntry] = []
    seen: set[str] = set()
    for index, raw_entry in enumerate(raw_terms, start=1):
        if not isinstance(raw_entry, Mapping):
            raise ProfileError(f"第 {index} 个术语必须是 TOML 表")
        unknown = set(raw_entry) - {"source", "target"}
        if unknown:
            raise ProfileError(f"第 {index} 个术语包含未知字段：{sorted(unknown)}")
        source = raw_entry.get("source")
        target = raw_entry.get("target")
        if not isinstance(source, str) or not isinstance(target, str):
            raise ProfileError(f"第 {index} 个术语必须包含字符串 source/target")
        try:
            entry = GlossaryEntry(source, target)
        except ValueError as exc:
            raise ProfileError(f"第 {index} 个术语无效：{exc}") from exc
        source_key = normalize_source_text(entry.source)
        if source_key in seen:
            raise ProfileError(f"术语表原文重复：{entry.source}")
        seen.add(source_key)
        entries.append(entry)

    canonical = json.dumps(
        [[entry.source, entry.target] for entry in entries],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    revision = hashlib.sha256(canonical).hexdigest()
    return tuple(entries), revision


def _load_capture_settings(path: Path) -> ProfileCaptureSettings:
    if not path.exists():
        return ProfileCaptureSettings()
    data = _read_toml(path, "Profile 设置")
    unknown_root = set(data) - {"capture"}
    if unknown_root:
        raise ProfileError(f"settings.toml 包含未知字段：{sorted(unknown_root)}")
    capture = data.get("capture")
    if capture is None:
        return ProfileCaptureSettings()
    if not isinstance(capture, Mapping):
        raise ProfileError("settings.toml 的 [capture] 必须是 TOML 表")
    allowed = {"monitor_index", "left", "top", "width", "height"}
    unknown = set(capture) - allowed
    if unknown:
        raise ProfileError(f"[capture] 包含未知字段：{sorted(unknown)}")

    monitor_index = capture.get("monitor_index")
    if monitor_index is not None and type(monitor_index) is not int:
        raise ProfileError("capture.monitor_index 必须是整数")
    region_keys = ("left", "top", "width", "height")
    present = [key in capture for key in region_keys]
    if any(present) and not all(present):
        raise ProfileError("capture.left/top/width/height 必须同时提供")
    region = None
    if all(present):
        raw_region = tuple(capture[key] for key in region_keys)
        if any(type(value) is not int for value in raw_region):
            raise ProfileError("Profile 捕获区域必须是整数")
        region = raw_region
    return ProfileCaptureSettings(monitor_index=monitor_index, region=region)


def _atomic_write_text(path: Path, text: str) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        os.replace(temporary_path, path)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise


def _ensure_profile_file(profile: GameProfile, path: Path) -> None:
    if path.resolve().parent != profile.directory:
        raise ProfileError("Profile 文件路径越出了当前游戏目录")


def load_game_profile(
    config_path: Path,
    config: AppConfig,
    profile_id: str,
) -> GameProfile:
    normalized_id = validate_profile_id(profile_id)
    root = resolve_profiles_root(config_path, config)
    directory = (root / normalized_id).resolve()
    if directory.parent != root or not directory.is_dir():
        raise ProfileError(
            f"找不到游戏 Profile {normalized_id!r}；请先运行 profile init"
        )

    manifest = _read_toml(directory / "profile.toml", "Profile 清单")
    if set(manifest) - {"version", "id", "display_name", "created_at"}:
        raise ProfileError("profile.toml 包含未知字段")
    if manifest.get("version") != PROFILE_VERSION:
        raise ProfileError(f"不支持的 Profile 版本：{manifest.get('version')!r}")
    if manifest.get("id") != normalized_id:
        raise ProfileError("profile.toml 的 id 与目录名不一致")
    display_name = manifest.get("display_name")
    if not isinstance(display_name, str) or not display_name.strip():
        raise ProfileError("profile.toml 的 display_name 必须是非空字符串")

    glossary_path = directory / "glossary.toml"
    if glossary_path.resolve().parent != directory:
        raise ProfileError("术语表路径越出了当前游戏 Profile")
    glossary, glossary_revision = _load_glossary(glossary_path)
    settings_path = directory / "settings.toml"
    if settings_path.exists() and settings_path.resolve().parent != directory:
        raise ProfileError("设置文件路径越出了当前游戏 Profile")
    capture_settings = _load_capture_settings(settings_path)
    database_path = (directory / "translations.sqlite3").resolve()
    if database_path.parent != directory:
        raise ProfileError("翻译缓存路径越出了当前游戏 Profile")
    cache = TranslationCache(database_path)
    return GameProfile(
        profile_id=normalized_id,
        display_name=display_name.strip(),
        directory=directory,
        glossary=glossary,
        glossary_revision=glossary_revision,
        capture_settings=capture_settings,
        cache=cache,
    )


def create_game_profile(
    config_path: Path,
    config: AppConfig,
    profile_id: str,
    *,
    display_name: str | None = None,
) -> GameProfile:
    normalized_id = validate_profile_id(profile_id)
    name = (display_name or normalized_id).strip()
    if not name:
        raise ProfileError("Profile 显示名称不能为空")
    root = resolve_profiles_root(config_path, config)
    root.mkdir(parents=True, exist_ok=True)
    directory = (root / normalized_id).resolve()
    if directory.parent != root:
        raise ProfileError("Profile 路径越出了资料库根目录")
    try:
        directory.mkdir()
    except FileExistsError as exc:
        raise ProfileError(f"游戏 Profile {normalized_id!r} 已存在") from exc

    created_at = datetime.now(UTC).isoformat(timespec="seconds")
    manifest = (
        f"version = {PROFILE_VERSION}\n"
        f"id = {json.dumps(normalized_id, ensure_ascii=False)}\n"
        f"display_name = {json.dumps(name, ensure_ascii=False)}\n"
        f"created_at = {json.dumps(created_at)}\n"
    )
    glossary = (
        "# 每个游戏独立维护；修改后会自动形成新的术语表版本。\n"
        "# 示例：\n"
        "# [[terms]]\n"
        "# source = \"フィクサー\"\n"
        "# target = \"中间人\"\n"
    )
    (directory / "profile.toml").write_text(manifest, encoding="utf-8")
    (directory / "glossary.toml").write_text(glossary, encoding="utf-8")
    (directory / "settings.toml").write_text(
        "# 由图形化启动器保存每个游戏自己的显示器和字幕区域。\n",
        encoding="utf-8",
    )
    TranslationCache(directory / "translations.sqlite3")
    return load_game_profile(config_path, config, normalized_id)


def list_game_profiles(config_path: Path, config: AppConfig) -> tuple[GameProfile, ...]:
    root = resolve_profiles_root(config_path, config)
    if not root.is_dir():
        return ()
    profiles = [
        load_game_profile(config_path, config, child.name)
        for child in root.iterdir()
        if child.is_dir() and (child / "profile.toml").is_file()
    ]
    return tuple(
        sorted(profiles, key=lambda profile: (profile.display_name.casefold(), profile.profile_id))
    )


def save_profile_capture_settings(
    profile: GameProfile,
    settings: ProfileCaptureSettings,
) -> None:
    path = profile.settings_path
    _ensure_profile_file(profile, path)
    lines = ["# 每个游戏独立的屏幕捕获设置。"]
    if settings.monitor_index is not None or settings.region is not None:
        lines.extend(("", "[capture]"))
    if settings.monitor_index is not None:
        lines.append(f"monitor_index = {settings.monitor_index}")
    if settings.region is not None:
        left, top, width, height = settings.region
        lines.extend(
            (
                f"left = {left}",
                f"top = {top}",
                f"width = {width}",
                f"height = {height}",
            )
        )
    _atomic_write_text(path, "\n".join(lines) + "\n")


def save_profile_glossary(
    profile: GameProfile,
    entries: Iterable[GlossaryEntry],
) -> None:
    validated: list[GlossaryEntry] = []
    seen: set[str] = set()
    for entry in entries:
        checked = GlossaryEntry(entry.source, entry.target)
        source_key = normalize_source_text(checked.source)
        if source_key in seen:
            raise ProfileError(f"术语表原文重复：{checked.source}")
        seen.add(source_key)
        validated.append(checked)

    lines = ["# 每个游戏独立维护；保存后会形成新的术语表版本。"]
    for entry in validated:
        lines.extend(
            (
                "",
                "[[terms]]",
                f"source = {json.dumps(entry.source.strip(), ensure_ascii=False)}",
                f"target = {json.dumps(entry.target.strip(), ensure_ascii=False)}",
            )
        )
    path = profile.glossary_path
    _ensure_profile_file(profile, path)
    _atomic_write_text(path, "\n".join(lines) + "\n")


def apply_profile_capture_settings(
    live: LiveConfig,
    settings: ProfileCaptureSettings,
) -> LiveConfig:
    updated = live
    if settings.monitor_index is not None:
        updated = replace(updated, monitor_index=settings.monitor_index)
    if settings.region is not None:
        left, top, width, height = settings.region
        updated = replace(
            updated,
            left=left,
            top=top,
            width=width,
            height=height,
        )
    return updated
