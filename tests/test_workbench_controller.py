import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtWidgets import QApplication
from PySide6.QtWidgets import QWidget

from game_screen_translator.branding import (
    API_KEY_ENV,
    LEGACY_API_KEY_ENV,
    PRODUCT_NAME,
)
from game_screen_translator.config import load_config
from game_screen_translator.domain import GlossaryEntry
from game_screen_translator.gui import workbench_controller as controller_module
from game_screen_translator.gui.theme import (
    THEME_DARK,
    THEME_LIGHT,
    gui_settings_path,
    load_gui_preferences,
)
from game_screen_translator.gui.workbench_controller import WorkbenchController
from game_screen_translator.live.snapshot import CacheHit, SnapshotEntry, new_snapshot, save_snapshot
from game_screen_translator.live.runtime import LiveControlWindow
from game_screen_translator.profiles import (
    ProfileCaptureSettings,
    create_game_profile,
    load_game_profile,
    save_profile_capture_settings,
    save_profile_custom_prompt,
    save_profile_glossary,
)


def _write_config(path: Path) -> None:
    path.write_text(
        """
[translation]
provider = "openai_compatible"
base_url = "http://127.0.0.1:1234/v1"
model = "hy-mt1.5-7b"

[live]
left = 1
top = 2
width = 3
height = 4
""",
        encoding="utf-8",
    )


def _controller_with_profile(tmp_path: Path) -> tuple[WorkbenchController, Path]:
    QApplication.instance() or QApplication([])
    config_path = tmp_path / "config.toml"
    _write_config(config_path)
    create_game_profile(
        config_path,
        load_config(config_path),
        "game",
        display_name="测试游戏",
    )
    return WorkbenchController(config_path, probe_ocr_devices=False), config_path


def test_controller_projects_real_profile_data_and_truthful_telemetry_empty_state(
    tmp_path: Path,
) -> None:
    QApplication.instance() or QApplication([])
    config_path = tmp_path / "config.toml"
    _write_config(config_path)
    config = load_config(config_path)
    profile = create_game_profile(
        config_path,
        config,
        "game",
        display_name="测试游戏",
    )
    save_profile_capture_settings(
        profile,
        ProfileCaptureSettings(monitor_index=0, region=(100, 200, 800, 300)),
    )
    save_profile_glossary(profile, (GlossaryEntry("仕事", "委托"),))
    profile.cache.set_manual_correction(
        "待て。",
        "等等。",
        source_language=config.ocr.language,
        target_language=config.translation.target_language,
    )

    controller = WorkbenchController(config_path, probe_ocr_devices=False)

    assert controller.profileIds == ["game"]
    assert controller.currentProfileName == "测试游戏"
    assert controller.captureLeft == 100
    assert controller.captureTop == 200
    assert controller.captureWidth == 800
    assert controller.captureHeight == 300
    assert controller.glossaryEntries == [{"source": "仕事", "target": "委托"}]
    assert controller.correctionEntries == [{"source": "待て。", "target": "等等。"}]
    assert controller.manualCorrections == 1
    assert controller.telemetryAvailable is False
    assert "未向设置工作台提供结构化遥测" in controller.telemetryUnavailableText
    assert controller.lastRunAvailable is False
    assert "尚无上次正常且有效运行结果" in controller.lastRunStatus
    assert "测试游戏" in controller.infoText

    controller.shutdown()


def test_controller_exposes_selected_display_size_in_capture_pixels(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller, _config_path = _controller_with_profile(tmp_path)

    screen = SimpleNamespace(
        geometry=lambda: SimpleNamespace(width=lambda: 1707, height=lambda: 960),
        devicePixelRatio=lambda: 1.5,
    )
    application = SimpleNamespace(screens=lambda: [screen])
    monkeypatch.setattr(
        controller_module,
        "QApplication",
        SimpleNamespace(instance=lambda: application),
    )

    assert controller.captureDisplayWidth == 2560
    assert controller.captureDisplayHeight == 1440
    assert controller._selected_display_long_side() == 2560
    controller.shutdown()


def test_controller_loads_last_run_snapshot_and_reloads_on_profile_switch(
    tmp_path: Path,
) -> None:
    QApplication.instance() or QApplication([])
    config_path = tmp_path / "config.toml"
    _write_config(config_path)
    config = load_config(config_path)
    first = create_game_profile(config_path, config, "first", display_name="第一组")
    second = create_game_profile(config_path, config, "second", display_name="第二组")
    save_snapshot(
        first.directory,
        new_snapshot(
            (SnapshotEntry("a", 1, "第一条", "First", 0.9, (1, 2, 30, 40)),),
            (CacheHit("第一条", 2),),
            ocr_peak_seconds=0.2,
            llm_peak_seconds=1.2,
            canvas_size=(100, 80),
        ),
    )

    controller = WorkbenchController(config_path, probe_ocr_devices=False)
    assert controller.lastRunAvailable is True
    assert controller.lastRunTranslationResults[0]["translatedText"] == "First"
    assert controller.lastRunCacheHits == [{"sourceText": "第一条", "hits": 2}]
    assert controller.lastRunOcrPeakText == "200 ms"
    assert controller.lastRunLlmPeakText == "1.20 s"
    assert controller.lastRunCanvasWidth == 100
    assert controller.lastRunCanvasHeight == 80

    second_index = controller.profileIds.index("second")
    controller.selectProfile(second_index)
    assert controller.lastRunAvailable is False
    assert controller.lastRunOcrResults == []
    controller.shutdown()


def test_controller_reloads_snapshot_when_live_process_finishes(
    tmp_path: Path,
) -> None:
    controller, _ = _controller_with_profile(tmp_path)

    class _FinishedProcess:
        def poll(self) -> int:
            return 0

    save_snapshot(
        controller._profile.directory,
        new_snapshot(
            (SnapshotEntry("a", 1, "结束后原文", "结束后译文", 1.0, (0, 0, 20, 20)),),
            (),
            ocr_peak_seconds=0.1,
            llm_peak_seconds=None,
        ),
    )
    controller._live_process = _FinishedProcess()
    controller._live_stop_requested = True
    controller._check_live_process()

    assert controller.lastRunAvailable is True
    assert controller.lastRunOcrResults[0]["sourceText"] == "结束后原文"
    controller.shutdown()


def test_select_profile_reloads_owned_state_and_saves_only_selected_profile(
    tmp_path: Path,
) -> None:
    QApplication.instance() or QApplication([])
    config_path = tmp_path / "config.toml"
    _write_config(config_path)
    config = load_config(config_path)
    game = create_game_profile(
        config_path,
        config,
        "game",
        display_name="游戏配置",
    )
    web = create_game_profile(
        config_path,
        config,
        "web",
        display_name="网页配置",
    )
    save_profile_custom_prompt(game, "保持游戏角色口吻。")
    save_profile_custom_prompt(web, "保持技术文档术语。")
    save_profile_capture_settings(
        game,
        ProfileCaptureSettings(monitor_index=0, region=(10, 20, 800, 300)),
    )
    save_profile_capture_settings(
        web,
        ProfileCaptureSettings(monitor_index=0, region=(30, 40, 900, 320)),
    )

    controller = WorkbenchController(config_path, probe_ocr_devices=False)
    controller.selectProfile(controller.profileIds.index("game"))
    assert controller.customPrompt == "保持游戏角色口吻。"
    assert (
        controller.captureLeft,
        controller.captureTop,
        controller.captureWidth,
        controller.captureHeight,
    ) == (10, 20, 800, 300)

    revision = controller.profileRevision
    controller.selectProfile(controller.profileIds.index("web"))
    assert controller.profileRevision > revision
    assert controller.customPrompt == "保持技术文档术语。"
    assert (
        controller.captureLeft,
        controller.captureTop,
        controller.captureWidth,
        controller.captureHeight,
    ) == (30, 40, 900, 320)

    controller.setCustomPrompt("改为简洁书面语。")
    assert controller.saveCustomPrompt() is True
    assert load_game_profile(config_path, load_config(config_path), "web").custom_prompt == (
        "改为简洁书面语。"
    )
    assert load_game_profile(config_path, load_config(config_path), "game").custom_prompt == (
        "保持游戏角色口吻。"
    )
    controller.shutdown()


def test_controller_preserves_runtime_prompt_and_capture_save_boundaries(
    tmp_path: Path,
) -> None:
    controller, config_path = _controller_with_profile(tmp_path)

    controller.setBaseUrl("https://example.test/v1")
    controller.setModel("real-model")
    controller.setCustomPrompt("保持角色口吻。")
    controller.setCaptureRegion(10, 20, 800, 300)
    assert controller.settingsDirty is True

    assert controller.saveRuntimeSettings() is True
    saved_config = load_config(config_path)
    saved_profile = load_game_profile(config_path, saved_config, "game")
    assert saved_config.translation.base_url == "https://example.test/v1"
    assert saved_config.translation.model == "real-model"
    assert saved_profile.custom_prompt == ""
    assert saved_profile.capture_settings.region is None
    assert controller.settingsDirty is True

    assert controller.saveCustomPrompt() is True
    saved_profile = load_game_profile(config_path, load_config(config_path), "game")
    assert saved_profile.custom_prompt == "保持角色口吻。"
    assert saved_profile.capture_settings.region is None
    assert controller.settingsDirty is True

    assert controller.saveCapture() is True
    saved_profile = load_game_profile(config_path, load_config(config_path), "game")
    assert saved_profile.capture_settings.region == (10, 20, 800, 300)
    assert controller.settingsDirty is False

    controller.shutdown()


def test_overlay_opacity_draft_round_trips_exactly_only_after_save(
    tmp_path: Path,
) -> None:
    QApplication.instance() or QApplication([])
    config_path = tmp_path / "config.toml"
    _write_config(config_path)
    config_path.write_text(
        config_path.read_text(encoding="utf-8")
        + "\n[preview]\noverlay_opacity = 0.375\n",
        encoding="utf-8",
    )
    create_game_profile(
        config_path,
        load_config(config_path),
        "game",
        display_name="测试游戏",
    )
    controller = WorkbenchController(config_path, probe_ocr_devices=False)

    assert controller.overlayOpacity == 0.375
    assert controller.settingsDirty is False
    assert controller.saveRuntimeSettings() is True
    assert load_config(config_path).preview.overlay_opacity == 0.375

    controller.setOverlayOpacity(1.2)
    assert controller.overlayOpacity == 1.0
    controller.setOverlayOpacity(-0.2)
    assert controller.overlayOpacity == 0.0
    controller.setOverlayOpacity(0.37000000000000005)

    assert controller.overlayOpacity == 0.37
    assert controller.blurMode == "dark_blur"
    assert controller.settingsDirty is True
    assert load_config(config_path).preview.overlay_opacity == 0.375

    assert controller.saveRuntimeSettings() is True
    assert load_config(config_path).preview.overlay_opacity == 0.37
    controller.shutdown()

    restored = WorkbenchController(config_path, probe_ocr_devices=False)
    assert restored.overlayOpacity == 0.37
    assert restored.blurMode == "dark_blur"
    restored.setOverlayOpacity(0.0)
    assert restored.overlayOpacity == 0.0
    assert restored.blurMode == "blur_only"
    restored.shutdown()


def test_controller_round_trips_complete_runtime_settings_and_preserves_external_api(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller, config_path = _controller_with_profile(tmp_path)
    controller._set_ocr_device_choices(
        (
            ("gpu:0", "GPU 0 · NVIDIA RTX 4070"),
            ("gpu:1", "GPU 1 · NVIDIA RTX 4090"),
        ),
        None,
    )
    monkeypatch.setattr(controller, "_selected_display_long_side", lambda: 2560)

    controller.setBaseUrl("https://external.test/v1")
    controller.setApiKey("external-secret")
    controller.setModel("external-model")
    controller.setMaxConcurrency(6)
    controller.setBackend("builtin")
    controller.setBuiltinModel("Hy-MT2-7B-Q4_K_M.gguf")
    controller.setBuiltinCudaDevice("gpu:1")
    controller.setBuiltinParallel(4)
    controller.setBuiltinKvCacheType("q8_0")
    controller.setOcrDevice("gpu:1")
    controller.setOcrFilterEnabled(False)
    controller.setDetectionQualityIndex(2)
    controller.setOcrMergeEnabled(True)
    controller.setBlurMode("blur_only")
    controller.setBrowserOverlayEnabled(True)
    controller.setDynamicRoiEnabled(True)
    controller.setChangePollFps(10)
    controller.setRoiResponseTargetMs(700)
    controller.setClearAfterMs(750)
    controller.setSettleRescanMs(800)
    controller.setIdleRescanMs(4000)
    controller.setOcrCooldownMs(125)

    assert controller.saveRuntimeSettings() is True
    saved = load_config(config_path)
    assert saved.translation.backend == "builtin"
    assert saved.translation.builtin_model == "Hy-MT2-7B-Q4_K_M.gguf"
    assert saved.translation.builtin_cuda_device == "gpu:1"
    assert saved.translation.builtin_parallel == 4
    assert saved.translation.builtin_total_context == 8192
    assert saved.translation.builtin_max_output_tokens == 512
    assert saved.translation.builtin_kv_cache_type == "q8_0"
    assert saved.translation.builtin_temperature == 0.2
    assert saved.translation.base_url == "https://external.test/v1"
    assert saved.translation.api_key == "external-secret"
    assert saved.translation.model == "external-model"
    assert saved.translation.max_concurrency == 6
    assert saved.ocr.device == "gpu:1"
    assert saved.ocr.detection_max_side == 1920
    assert saved.ocr.text_filter_enabled is False
    assert saved.ocr.text_merge_enabled is True
    assert saved.preview.overlay_opacity == 0.0
    assert saved.recording.browser_overlay_enabled is True
    assert saved.recording.browser_overlay_port == 47831
    assert saved.live.dynamic_roi_enabled is True
    assert saved.live.change_poll_fps == 10
    assert saved.live.capture_fps == 20
    assert saved.live.dynamic_roi_response_target_ms == 700
    assert saved.live.clear_after_ms == 750
    assert saved.live.settle_rescan_ms == 800
    assert saved.live.idle_rescan_ms == 4000
    assert saved.live.ocr_cooldown_ms == 125

    controller.shutdown()
    monkeypatch.setattr(
        WorkbenchController,
        "_selected_display_long_side",
        lambda _self: 2560,
    )
    restored = WorkbenchController(config_path, probe_ocr_devices=False)
    assert restored.backend == "builtin"
    assert restored.builtinModel == "Hy-MT2-7B-Q4_K_M.gguf"
    assert restored.builtinCudaDevice == "gpu:1"
    assert restored.builtinParallel == 4
    assert restored.builtinKvCacheType == "q8_0"
    assert restored.baseUrl == "https://external.test/v1"
    assert restored.model == "external-model"
    assert restored.apiKeyConfigured is True
    assert restored.maxConcurrency == 6
    assert restored.ocrDevice == "gpu:1"
    assert restored.detectionQualityIndex == 2
    assert restored.ocrFilterEnabled is False
    assert restored.ocrMergeEnabled is True
    assert restored.blurMode == "blur_only"
    assert restored.browserOverlayEnabled is True
    assert restored.dynamicRoiEnabled is True
    assert restored.changePollFps == 10
    assert restored.roiResponseTargetMs == 700
    assert restored.clearAfterMs == 750
    assert restored.settleRescanMs == 800
    assert restored.idleRescanMs == 4000
    assert restored.ocrCooldownMs == 125
    restored.shutdown()


def test_detection_quality_scaling_alignment_and_merge_guard(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolve = controller_module._detection_max_side_for_display
    assert resolve(2560, 0.375) == 960
    assert resolve(2560, 0.5) == 1280
    assert resolve(2560, 0.75) == 1920
    assert resolve(1920, 0.375) == 736
    assert resolve(7680, 0.75) == 4096

    controller, _config_path = _controller_with_profile(tmp_path)
    monkeypatch.setattr(controller, "_selected_display_long_side", lambda: 2560)
    controller.setDetectionQualityIndex(1)
    controller.setOcrMergeEnabled(True)
    assert controller.textMergeAllowed is True
    assert controller._ocr_candidate().text_merge_enabled is True

    controller.setDetectionQualityIndex(0)
    assert controller.detectionQualitySummary.endswith("960 px")
    assert controller.textMergeAllowed is False
    assert controller.ocrMergeEnabled is False
    assert controller._ocr_candidate().text_merge_enabled is False

    controller.setDetectionQualityIndex(2)
    assert controller.detectionQualitySummary.endswith("1920 px")
    assert controller.textMergeAllowed is True
    assert controller.ocrMergeEnabled is False
    controller.setOcrMergeEnabled(True)
    assert controller._ocr_candidate().text_merge_enabled is True
    controller.shutdown()


def test_runtime_save_projects_normalized_values_back_to_qml_state(
    tmp_path: Path,
) -> None:
    controller, _config_path = _controller_with_profile(tmp_path)
    controller.setBaseUrl("  https://example.test/v1  ")
    controller.setModel("  normalized-model  ")
    controller.setApiKey("  secret  ")

    assert controller.saveRuntimeSettings() is True

    assert controller.baseUrl == "https://example.test/v1"
    assert controller.model == "normalized-model"
    assert controller.modelNames[0] == "normalized-model"
    assert controller.apiKeyConfigured is True
    assert controller.settingsDirty is False
    controller.shutdown()


def test_theme_preference_persists_next_to_config_and_restores(
    tmp_path: Path,
) -> None:
    controller, config_path = _controller_with_profile(tmp_path)
    settings_path = gui_settings_path(config_path)
    assert settings_path.parent == tmp_path
    assert not settings_path.exists()

    controller.setTheme(THEME_DARK)
    assert controller.themePreference == THEME_DARK
    assert controller.effectiveTheme == THEME_DARK
    assert load_gui_preferences(config_path).theme == THEME_DARK
    assert settings_path.is_file()
    controller.shutdown()

    restored = WorkbenchController(config_path, probe_ocr_devices=False)
    assert restored.themePreference == THEME_DARK
    assert restored.effectiveTheme == THEME_DARK
    restored.setTheme(THEME_LIGHT)
    assert restored.themePreference == THEME_LIGHT
    assert restored.effectiveTheme == THEME_LIGHT
    assert load_gui_preferences(config_path).theme == THEME_LIGHT
    restored.shutdown()


def test_theme_preference_does_not_change_when_project_save_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller, config_path = _controller_with_profile(tmp_path)
    initial_preference = controller.themePreference
    initial_effective = controller.effectiveTheme
    errors: list[tuple[str, str]] = []
    controller.errorRaised.connect(lambda title, message: errors.append((title, message)))
    monkeypatch.setattr(
        controller_module,
        "save_gui_preferences",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("disk full")),
    )

    controller.setTheme(THEME_DARK)

    assert controller.themePreference == initial_preference
    assert controller.effectiveTheme == initial_effective
    assert not gui_settings_path(config_path).exists()
    assert errors == [("保存界面主题失败", "disk full")]
    controller.shutdown()


def test_controller_save_all_keeps_existing_order_and_short_circuit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller, _config_path = _controller_with_profile(tmp_path)
    calls: list[str] = []

    monkeypatch.setattr(
        controller,
        "_save_runtime_settings",
        lambda *, announce: calls.append("runtime") or True,
    )
    monkeypatch.setattr(
        controller,
        "_save_custom_prompt",
        lambda *, announce: calls.append("prompt") or False,
    )
    monkeypatch.setattr(
        controller,
        "_save_capture",
        lambda *, announce: calls.append("capture") or True,
    )

    assert controller.saveAll() is False
    assert calls == ["runtime", "prompt"]

    controller.shutdown()


def test_controller_create_profile_selects_the_new_profile(tmp_path: Path) -> None:
    controller, _config_path = _controller_with_profile(tmp_path)

    controller.createProfile("第二个游戏")

    assert controller.currentProfileName == "第二个游戏"
    assert controller.currentProfileId != "game"
    assert controller.currentProfileIndex == controller.profileIds.index(
        controller.currentProfileId
    )

    controller.shutdown()


def test_empty_profile_list_clears_profile_owned_drafts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller, _config_path = _controller_with_profile(tmp_path)
    controller.setCustomPrompt("不应泄漏")
    controller.setCaptureRegion(10, 20, 300, 200)
    monkeypatch.setattr(controller_module, "list_game_profiles", lambda *_args: ())

    controller.refreshProfiles()

    assert controller.hasProfile is False
    assert controller.currentProfileIndex == -1
    assert controller.customPrompt == ""
    assert controller.customRegion is False
    assert (
        controller.captureLeft,
        controller.captureTop,
        controller.captureWidth,
        controller.captureHeight,
    ) == (0, 0, 0, 0)
    assert controller.glossaryEntries == []
    assert controller.correctionEntries == []
    controller.shutdown()


def test_region_selector_stays_in_the_native_host_boundary(tmp_path: Path) -> None:
    controller, config_path = _controller_with_profile(tmp_path)
    requested: list[int] = []
    controller.regionSelectionRequested.connect(requested.append)

    controller.selectRegion()
    assert requested == [controller.monitorIndex]

    controller.acceptRegionSelection(20, 30, 900, 320)
    profile = load_game_profile(config_path, load_config(config_path), "game")
    assert profile.capture_settings.region == (20, 30, 900, 320)

    controller.shutdown()


def test_use_full_screen_clears_and_persists_profile_region(tmp_path: Path) -> None:
    controller, config_path = _controller_with_profile(tmp_path)
    controller.acceptRegionSelection(20, 30, 900, 320)
    assert controller.customRegion is True

    controller.useFullScreen()

    assert controller.customRegion is False
    assert (
        controller.captureLeft,
        controller.captureTop,
        controller.captureWidth,
        controller.captureHeight,
    ) == (0, 0, 0, 0)
    profile = load_game_profile(config_path, load_config(config_path), "game")
    assert profile.capture_settings.region == (0, 0, 0, 0)
    controller.shutdown()


def test_missing_profile_monitor_falls_back_without_resaving_stale_index(
    tmp_path: Path,
) -> None:
    QApplication.instance() or QApplication([])
    config_path = tmp_path / "config.toml"
    _write_config(config_path)
    profile = create_game_profile(
        config_path,
        load_config(config_path),
        "game",
        display_name="测试游戏",
    )
    save_profile_capture_settings(
        profile,
        ProfileCaptureSettings(monitor_index=99, region=(1, 2, 300, 200)),
    )

    controller = WorkbenchController(config_path, probe_ocr_devices=False)

    assert controller.monitorIndex == 0
    assert "显示器 99 当前不存在" in controller.statusText
    assert controller.saveAll() is True
    saved = load_game_profile(config_path, load_config(config_path), "game")
    assert saved.capture_settings.monitor_index == 0
    controller.shutdown()


def test_model_download_saves_only_runtime_scope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller, config_path = _controller_with_profile(tmp_path)
    controller.setCustomPrompt("尚未保存的提示词")
    controller.setCaptureRegion(30, 40, 700, 260)
    controller.setModel("runtime-model")
    monkeypatch.setattr(
        controller_module,
        "install_local_backend",
        lambda *_args, **_kwargs: None,
    )

    controller.downloadBuiltinModel()
    assert controller._local_install_thread is not None
    controller._local_install_thread.join(timeout=2)
    controller._check_local_install_events()

    profile = load_game_profile(config_path, load_config(config_path), "game")
    assert load_config(config_path).translation.model == "runtime-model"
    assert profile.custom_prompt == ""
    assert profile.capture_settings.region is None
    assert controller.settingsDirty is True

    controller.shutdown()


def test_controller_emits_live_ready_without_owning_window_visibility(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller, config_path = _controller_with_profile(tmp_path)
    controller.setBackend("external")
    controller.setCustomPrompt("启动前保存的提示词")
    controller.setCaptureRegion(20, 30, 800, 300)
    controller.setDebugEnabled(True)
    ready: list[bool] = []
    controller.liveReady.connect(lambda: ready.append(True))
    fake_process = SimpleNamespace(pid=4321, poll=lambda: None, terminate=lambda: None)
    popen_calls = []
    monkeypatch.setattr(
        controller_module,
        "_validate_ocr_device_isolated",
        lambda _device: "gpu:0 · test",
    )
    monkeypatch.setattr(
        controller_module.subprocess,
        "Popen",
        lambda *args, **kwargs: popen_calls.append(
            (
                args,
                {
                    **kwargs,
                    "stdout_name": Path(kwargs["stdout"].name),
                },
            )
        )
        or fake_process,
    )

    controller.startLive()

    assert ready == [True]
    assert controller.runPhase == "running"
    arguments = popen_calls[0][0][0]
    options = popen_calls[0][1]
    assert arguments == [
        sys.executable,
        "-m",
        "game_screen_translator",
        "--config",
        str(config_path.resolve()),
        "live",
        "--profile",
        "game",
        "--debug-border",
    ]
    assert options["cwd"] == tmp_path
    assert options["stdin"] is controller_module.subprocess.DEVNULL
    assert options["stderr"] is controller_module.subprocess.STDOUT
    assert options["stdout_name"] == tmp_path / "output" / "live.log"
    assert options["close_fds"] is True
    assert options["env"]["PYTHONFAULTHANDLER"] == "1"
    assert options["env"]["PYTHONUNBUFFERED"] == "1"
    assert options["env"]["PYTHONUTF8"] == "1"
    assert (tmp_path / "output" / "live.log").read_text(encoding="utf-8").startswith(
        f"{PRODUCT_NAME} live diagnostics"
    )
    saved_profile = load_game_profile(config_path, load_config(config_path), "game")
    assert saved_profile.custom_prompt == "启动前保存的提示词"
    assert saved_profile.capture_settings.region == (20, 30, 800, 300)

    controller._live_process = None
    controller.shutdown()


def test_stop_live_requests_graceful_close_then_allows_explicit_force_stop(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller, _config_path = _controller_with_profile(tmp_path)
    terminated: list[bool] = []
    exit_code: list[int | None] = [None]

    def terminate() -> None:
        terminated.append(True)
        exit_code[0] = 1

    controller._live_process = SimpleNamespace(
        poll=lambda: exit_code[0],
        terminate=terminate,
    )
    controller._set_run_state("正在翻译", "success", True)
    graceful_calls: list[object] = []
    monkeypatch.setattr(
        controller_module,
        "_request_live_graceful_shutdown",
        lambda process: graceful_calls.append(process) or True,
    )
    finished: list[bool] = []
    controller.liveFinished.connect(lambda: finished.append(True))

    controller.stopLive()

    assert terminated == []
    assert len(graceful_calls) == 1
    assert controller.runPhase == "stopping"
    assert controller.canStart is False
    assert controller.startButtonText == "正在保存并停止…"
    controller._live_stop_started_at = time.monotonic() - 6
    controller._check_live_process()
    assert controller.startButtonText == "强制停止"
    controller.stopLive()
    assert terminated == [True]
    assert len(graceful_calls) == 1
    assert controller.startButtonText == "正在强制停止…"
    controller._check_live_process()
    assert controller._live_process is None
    assert controller.runPhase == "stopped"
    assert controller.canStart is True
    assert controller.startButtonText == "开始翻译"
    assert controller.runState == "已强制停止"
    assert "保留上次快照" in controller.statusText
    assert finished == [True]
    controller.shutdown()


def test_stop_live_helper_failure_keeps_process_running_and_can_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller, _config_path = _controller_with_profile(tmp_path)
    process = SimpleNamespace(poll=lambda: None, terminate=lambda: pytest.fail("不得强杀"))
    controller._live_process = process
    controller._set_run_state("正在翻译", "success", True)
    graceful_calls: list[object] = []
    monkeypatch.setattr(
        controller_module,
        "_request_live_graceful_shutdown",
        lambda current: graceful_calls.append(current) or False,
    )

    controller.stopLive()

    assert graceful_calls == [process]
    assert controller.running is True
    assert controller.runPhase == "running"
    assert controller._live_stop_requested is False
    assert "无法请求" in controller.statusText
    controller.shutdown()


def test_live_exit_code_zero_is_the_only_normal_snapshot_refresh_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller, _config_path = _controller_with_profile(tmp_path)
    controller._live_process = SimpleNamespace(poll=lambda: 0)
    controller._set_run_state("正在翻译", "success", True)
    reloads: list[bool] = []
    finished: list[bool] = []
    monkeypatch.setattr(controller, "_reload_last_run_snapshot", lambda: reloads.append(True))
    controller.liveFinished.connect(lambda: finished.append(True))

    controller._check_live_process()

    assert controller.runState == "已停止"
    assert reloads == [True]
    assert finished == [True]
    controller.shutdown()


def test_graceful_close_requested_but_nonzero_exit_is_unexpected_failure(
    tmp_path: Path,
) -> None:
    controller, _config_path = _controller_with_profile(tmp_path)
    controller._live_process = SimpleNamespace(poll=lambda: 7)
    controller._set_run_state("正在保存并停止", "warning", True)
    controller._live_force_stop_requested = False
    controller._live_log_path.parent.mkdir(parents=True, exist_ok=True)
    controller._live_log_path.write_text("close path failed", encoding="utf-8")
    failures: list[bool] = []
    errors: list[tuple[str, str]] = []
    controller.liveFailed.connect(lambda: failures.append(True))
    controller.errorRaised.connect(lambda title, message: errors.append((title, message)))

    controller._check_live_process()

    assert controller.runState == "异常退出"
    assert controller.statusTone == "error"
    assert failures == [True]
    assert errors and "退出码：7" in errors[0][1]
    assert "强制停止" not in controller.statusText
    controller.shutdown()


@pytest.mark.skipif(
    os.name != "nt" or os.environ.get("QT_QPA_PLATFORM", "").lower() != "windows",
    reason="requires the native Windows Qt platform and real HWNDs",
)
def test_native_shutdown_targets_real_control_hwnd_and_reaches_qt_close_event() -> None:
    app = QApplication.instance() or QApplication([])
    callbacks: list[str] = []
    about_to_quit: list[bool] = []

    def quit_callback() -> None:
        callbacks.append("quit")
        app.quit()

    overlay = QWidget()
    overlay.setWindowTitle(f"{PRODUCT_NAME} · Overlay")
    overlay.show()
    control = LiveControlWindow(quit_callback)
    control.show()
    app.processEvents()
    app.aboutToQuit.connect(lambda: about_to_quit.append(True))
    process = SimpleNamespace(pid=os.getpid())
    assert controller_module._request_live_graceful_shutdown(process) is True

    QTimer.singleShot(1000, app.quit)
    app.exec()
    assert callbacks == ["quit"]
    assert about_to_quit == [True]
    assert not control.isVisible()
    assert controller_module._request_live_graceful_shutdown(process) is False
    overlay.close()
    app.processEvents()
    control.close()
    app.processEvents()
    assert callbacks == ["quit"]


def test_missing_builtin_model_fails_before_ocr_probe_or_spawn(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller, _config_path = _controller_with_profile(tmp_path)
    controller.setBackend("builtin")
    errors: list[tuple[str, str]] = []
    controller.errorRaised.connect(lambda title, message: errors.append((title, message)))
    monkeypatch.setattr(controller_module, "local_backend_is_ready", lambda *_args: False)
    monkeypatch.setattr(
        controller_module,
        "_validate_ocr_device_isolated",
        lambda _device: pytest.fail("missing model must fail before OCR validation"),
    )
    monkeypatch.setattr(
        controller_module.subprocess,
        "Popen",
        lambda *_args, **_kwargs: pytest.fail("missing model must fail before spawn"),
    )

    controller.startLive()

    assert controller._live_process is None
    assert errors == [("启动实时翻译失败", "请先下载并校验内置模型")]
    controller.shutdown()


def test_shutdown_does_not_terminate_an_existing_live_process(tmp_path: Path) -> None:
    controller, _config_path = _controller_with_profile(tmp_path)
    terminated: list[bool] = []
    controller._live_process = SimpleNamespace(
        poll=lambda: None,
        terminate=lambda: terminated.append(True),
    )

    controller.shutdown()

    assert terminated == []


class _FakeReply:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload
        self.deleted = False

    def error(self):
        return controller_module.QNetworkReply.NetworkError.NoError

    def readAll(self) -> bytes:
        return self._payload

    def deleteLater(self) -> None:
        self.deleted = True


def test_api_reply_uses_real_payload_and_keeps_the_typed_model(
    tmp_path: Path,
) -> None:
    controller, _config_path = _controller_with_profile(tmp_path)
    controller.setModel("manually-entered")
    reply = _FakeReply(b'{"data":[{"id":"server-model"}]}')
    controller._model_reply = reply

    controller._models_loaded(reply, "https://example.test/v1/models")

    assert controller.modelNames == ["manually-entered", "server-model"]
    assert controller.connectionState.startswith("已从 https://example.test")
    assert reply.deleted is True
    controller.shutdown()


def test_empty_model_is_rejected_for_save_but_allowed_for_api_probe(
    tmp_path: Path,
) -> None:
    controller, config_path = _controller_with_profile(tmp_path)
    controller.setModel("")

    assert controller.saveRuntimeSettings() is False
    assert "translation.model 不能为空" in controller.statusText
    assert controller._translation_candidate(require_model=False).model == "hy-mt1.5-7b"
    assert load_config(config_path).translation.model == "hy-mt1.5-7b"
    controller.shutdown()


def test_api_key_is_write_only_to_qml_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(API_KEY_ENV, raising=False)
    monkeypatch.delenv(LEGACY_API_KEY_ENV, raising=False)
    controller, _config_path = _controller_with_profile(tmp_path)

    assert controller.metaObject().indexOfProperty("apiKey") == -1
    assert controller.apiKeyConfigured is False
    controller.setApiKey("secret-value")
    assert controller.apiKeyConfigured is True
    assert "secret-value" not in controller.infoText
    assert "secret-value" not in controller.statusText
    controller.clearApiKey()
    assert controller.apiKeyConfigured is False
    controller.shutdown()


def test_api_key_status_reports_environment_source_without_exposing_secret(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(API_KEY_ENV, "environment-secret")
    monkeypatch.delenv(LEGACY_API_KEY_ENV, raising=False)
    controller, _config_path = _controller_with_profile(tmp_path)

    assert controller.apiKeyConfigured is True
    assert controller.apiKeyOverrideConfigured is False
    assert API_KEY_ENV in controller.apiKeyStatusText
    assert "environment-secret" not in controller.apiKeyStatusText

    controller.setApiKey("local-secret")
    assert controller.apiKeyOverrideConfigured is True
    assert "本地配置" in controller.apiKeyStatusText
    controller.clearApiKey()
    assert controller.apiKeyConfigured is True
    assert controller.apiKeyOverrideConfigured is False
    assert API_KEY_ENV in controller.apiKeyStatusText
    controller.shutdown()


def test_ocr_preflight_uses_current_interpreter_and_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[tuple[str, ...], dict[str, object]]] = []

    def fake_run(arguments, **kwargs):
        calls.append((arguments, kwargs))
        return SimpleNamespace(
            returncode=0,
            stdout="Paddle diagnostic\ngpu:1 · Paddle 3.3.1 · CUDA 12.9\n",
            stderr="",
        )

    monkeypatch.setattr(controller_module.subprocess, "run", fake_run)

    description = controller_module._validate_ocr_device_isolated("gpu:1")

    arguments, kwargs = calls[0]
    assert description == "gpu:1 · Paddle 3.3.1 · CUDA 12.9"
    assert arguments[0] == sys.executable
    assert arguments[-1] == "gpu:1"
    assert kwargs["timeout"] == 20
    assert kwargs["check"] is False
    assert kwargs["capture_output"] is True
    assert kwargs["text"] is True


def test_ocr_probe_parser_ignores_diagnostics_and_rejects_non_gpu_devices() -> None:
    output = """Paddle diagnostic line
REFRA_OCR_DEVICES=[["gpu:0", "GPU 0 · NVIDIA RTX"], ["gpu:0", "duplicate"]]
"""

    assert controller_module._parse_ocr_device_probe_output(output) == (
        ("gpu:0", "GPU 0 · NVIDIA RTX"),
    )
    with pytest.raises(RuntimeError, match="未知设备"):
        controller_module._parse_ocr_device_probe_output(
            'REFRA_OCR_DEVICES=[["cpu", "CPU"]]'
        )


def test_unavailable_ocr_and_builtin_devices_remain_distinct_and_unselectable(
    tmp_path: Path,
) -> None:
    controller, _config_path = _controller_with_profile(tmp_path)
    controller._ocr_device = "gpu:9"
    controller._builtin_cuda_device = "gpu:8"

    controller._set_ocr_device_choices((("gpu:0", "GPU 0"),), None)

    assert controller.ocrDeviceValues == ["gpu:0", "gpu:9"]
    assert controller.builtinDeviceValues == ["follow_ocr", "gpu:0", "gpu:8"]
    assert "gpu:9" not in controller.builtinDeviceValues
    controller.setOcrDevice("gpu:9")
    controller.setBuiltinCudaDevice("gpu:8")
    assert controller.ocrDevice == "gpu:9"
    assert controller.builtinCudaDevice == "gpu:8"
    controller.setOcrDevice("gpu:0")
    controller.setBuiltinCudaDevice("gpu:0")
    assert controller.ocrDevice == "gpu:0"
    assert controller.builtinCudaDevice == "gpu:0"

    controller.setOcrDevice("gpu:9")
    controller.setBuiltinCudaDevice("gpu:8")
    assert controller.ocrDevice == "gpu:0"
    assert controller.builtinCudaDevice == "gpu:0"

    controller._set_ocr_device_choices((), None)
    assert controller.ocrDeviceValues == ["gpu:0"]
    assert controller.ocrDeviceAvailability == [False]
    assert "当前不可用" in controller.ocrDeviceNames[0]
    assert controller.builtinDeviceValues == ["follow_ocr", "gpu:0"]
    assert controller.builtinDeviceAvailability == [True, False]
    assert "未检测到可用的 NVIDIA GPU" in controller.statusText
    controller.shutdown()


def test_model_delete_requires_confirmation_and_rejects_active_download(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller, _config_path = _controller_with_profile(tmp_path)
    removed: list[str] = []
    monkeypatch.setattr(
        controller_module,
        "remove_builtin_model",
        lambda _root, model_id: removed.append(model_id) or 1024,
    )

    controller.deleteBuiltinModel(False)
    assert removed == []
    controller._local_install_thread = SimpleNamespace(is_alive=lambda: True)
    controller.deleteBuiltinModel(True)
    assert removed == []
    controller._local_install_thread = None
    monkeypatch.setattr(controller, "_local_model_capabilities", lambda: (False, True))
    controller.deleteBuiltinModel(True)
    assert removed == [controller.builtinModel]
    controller.shutdown()


def test_model_capabilities_and_install_lock_follow_real_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller, _config_path = _controller_with_profile(tmp_path)
    model_file = tmp_path / "model.gguf"
    monkeypatch.setattr(controller_module, "model_path", lambda *_args: model_file)
    monkeypatch.setattr(controller_module, "model_is_ready", lambda *_args: True)
    monkeypatch.setattr(controller_module, "runtime_is_ready", lambda *_args: True)

    assert controller.localModelReady is True
    assert controller.modelFilesExist is False
    assert controller.canDownloadBuiltinModel is False
    assert controller.canDeleteBuiltinModel is False
    assert controller.modelInstallActionText == "已下载"

    model_file.write_bytes(b"verified model")
    assert controller.modelFilesExist is True
    assert controller.canDeleteBuiltinModel is True

    original_backend = controller.backend
    original_model = controller.builtinModel
    controller._local_install_thread = SimpleNamespace(is_alive=lambda: True)
    controller.setBackend("builtin" if original_backend == "external" else "external")
    controller.setBuiltinModel(
        next(model for model in controller.builtinModelIds if model != original_model)
    )
    assert controller.backend == original_backend
    assert controller.builtinModel == original_model
    assert controller.canDeleteBuiltinModel is False
    assert controller.modelInstallActionText == "取消下载"
    controller._local_install_thread = None
    controller.shutdown()


def test_qml_arrays_reach_glossary_and_correction_slots(tmp_path: Path) -> None:
    controller, config_path = _controller_with_profile(tmp_path)
    engine = QQmlEngine()
    engine.rootContext().setContextProperty("workbench", controller)
    component = QQmlComponent(engine)
    component.setData(
        b"""import QtQml
QtObject {
  Component.onCompleted: {
    workbench.saveGlossary([{"source": "quest", "target": "mission"}])
    workbench.saveCorrections([{"source": "wait", "target": "hold"}])
  }
}
""",
        QUrl(),
    )

    root = component.create()

    assert root is not None, [error.toString() for error in component.errors()]
    profile = load_game_profile(config_path, load_config(config_path), "game")
    assert [(entry.source, entry.target) for entry in profile.glossary] == [
        ("quest", "mission")
    ]
    corrections = profile.cache.list_manual_corrections(
        source_language=controller._config.ocr.language,
        target_language=controller._config.translation.target_language,
    )
    assert [(entry.source_text, entry.translated_text) for entry in corrections] == [
        ("wait", "hold")
    ]
    root.deleteLater()
    controller.shutdown()


def test_pair_validation_ignores_blank_rows_and_rejects_half_rows(
    tmp_path: Path,
) -> None:
    controller, config_path = _controller_with_profile(tmp_path)
    errors: list[tuple[str, str]] = []
    controller.errorRaised.connect(lambda title, message: errors.append((title, message)))
    initial_revision = controller.profileRevision

    controller.saveGlossary(
        [
            {"source": "   ", "target": ""},
            {"source": "quest", "target": "mission"},
        ]
    )
    assert controller.glossaryEntries == [{"source": "quest", "target": "mission"}]
    assert controller.profileRevision == initial_revision + 1

    successful_revision = controller.profileRevision
    controller.saveGlossary([{"source": "only-source", "target": ""}])
    assert errors[-1][0] == "保存术语表失败"
    assert "必须同时填写" in errors[-1][1]
    assert controller.profileRevision == successful_revision
    profile = load_game_profile(config_path, load_config(config_path), "game")
    assert [(entry.source, entry.target) for entry in profile.glossary] == [
        ("quest", "mission")
    ]

    controller.saveCorrections([{"source": "", "target": "only-target"}])
    assert errors[-1][0] == "保存人工修订失败"
    assert "必须同时填写" in errors[-1][1]
    assert controller.profileRevision == successful_revision
    controller.shutdown()


def test_pair_drafts_survive_refresh_and_failed_save_until_persisted(
    tmp_path: Path,
) -> None:
    controller, config_path = _controller_with_profile(tmp_path)
    errors: list[tuple[str, str]] = []
    controller.errorRaised.connect(lambda title, message: errors.append((title, message)))
    glossary_draft = [{"source": "unsaved", "target": ""}]
    correction_draft = [{"source": "draft source", "target": "draft target"}]

    controller.setGlossaryDraft(glossary_draft)
    controller.setCorrectionsDraft(correction_draft)
    revision = controller.profileRevision
    assert controller.glossaryDirty is True
    assert controller.correctionsDirty is True
    assert controller.glossaryEntries == glossary_draft
    assert controller.correctionEntries == correction_draft

    controller.refreshStats()
    controller.refreshProfiles()
    assert controller.glossaryEntries == glossary_draft
    assert controller.correctionEntries == correction_draft
    assert controller.glossaryDirty is True
    assert controller.correctionsDirty is True

    controller.saveGlossary(glossary_draft)
    assert errors[-1][0] == "保存术语表失败"
    assert controller.profileRevision == revision
    assert controller.glossaryEntries == glossary_draft
    assert controller.glossaryDirty is True

    saved_glossary = [{"source": "unsaved", "target": "preserved"}]
    controller.setGlossaryDraft(saved_glossary)
    controller.saveGlossary(saved_glossary)
    controller.saveCorrections(correction_draft)
    assert controller.glossaryDirty is False
    assert controller.correctionsDirty is False
    assert controller.profileRevision == revision + 2
    profile = load_game_profile(config_path, load_config(config_path), "game")
    assert [(entry.source, entry.target) for entry in profile.glossary] == [
        ("unsaved", "preserved")
    ]
    controller.shutdown()


def test_stale_api_reply_cannot_replace_current_models(tmp_path: Path) -> None:
    controller, _config_path = _controller_with_profile(tmp_path)
    current = _FakeReply(b'{"data":[{"id":"current"}]}')
    stale = _FakeReply(b'{"data":[{"id":"stale"}]}')
    controller._model_reply = current

    controller._models_loaded(stale, "https://stale.test/v1/models")

    assert controller.modelNames == ["hy-mt1.5-7b"]
    assert controller._model_reply is current
    assert stale.deleted is True
    controller.shutdown()


def test_model_install_events_report_real_progress_and_terminal_error(
    tmp_path: Path,
) -> None:
    controller, _config_path = _controller_with_profile(tmp_path)
    errors: list[tuple[str, str]] = []
    controller.errorRaised.connect(lambda title, message: errors.append((title, message)))
    controller._local_install_thread = SimpleNamespace(is_alive=lambda: True)
    controller._local_install_events.put(
        ("progress", "download", "model.gguf", 50, 100)
    )
    controller._local_install_events.put(("error", "network unavailable"))

    controller._check_local_install_events()

    assert controller.downloadProgress == 50
    assert errors == [("内置模型下载失败", "network unavailable")]
    assert controller._local_install_thread is None
    controller.shutdown()


def test_builtin_live_ready_marker_is_the_only_ready_signal(
    tmp_path: Path,
) -> None:
    controller, _config_path = _controller_with_profile(tmp_path)
    ready: list[bool] = []
    controller.liveReady.connect(lambda: ready.append(True))
    controller._live_process = SimpleNamespace(poll=lambda: None)
    controller._live_waiting_for_ready = True
    controller._live_log_path.parent.mkdir(parents=True, exist_ok=True)
    controller._live_log_path.write_text(
        f"[{PRODUCT_NAME} Live] ready\n",
        encoding="utf-8",
    )

    controller._check_live_process()

    assert controller.runPhase == "running"
    assert ready == [True]
    controller._live_process = None
    controller.shutdown()


def test_live_failure_restores_host_through_signal_and_real_log(
    tmp_path: Path,
) -> None:
    controller, _config_path = _controller_with_profile(tmp_path)
    failures: list[bool] = []
    errors: list[tuple[str, str]] = []
    controller.liveFailed.connect(lambda: failures.append(True))
    controller.errorRaised.connect(lambda title, message: errors.append((title, message)))
    controller._live_process = SimpleNamespace(poll=lambda: 7)
    controller._live_log_path.parent.mkdir(parents=True, exist_ok=True)
    controller._live_log_path.write_text("real child failure", encoding="utf-8")

    controller._check_live_process()

    assert controller.runPhase == "failed"
    assert failures == [True]
    assert errors and "退出码：7" in errors[0][1]
    assert "real child failure" in errors[0][1]
    controller.shutdown()
