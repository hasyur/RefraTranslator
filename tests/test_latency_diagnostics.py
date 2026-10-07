from pathlib import Path

import pytest

from game_screen_translator.gui.latency_diagnostics import (
    MAX_LOG_TAIL_BYTES,
    parse_latency_diagnostics,
    read_latency_diagnostics,
)
from game_screen_translator.live.latency import LiveLatencyStats


def completed_log(*, cached: bool = False) -> str:
    stats = LiveLatencyStats()
    for kind, seconds in (("roi", 0.04), ("full", 0.8)):
        stats.record_ocr_pipeline(
            scan_kind=kind,
            scan_label="局部 ROI" if kind == "roi" else "整帧回退",
            change_activity_seconds=0.1,
            scheduling_seconds=0.02,
            preparation_seconds=0.003,
            worker_queue_seconds=0,
            ocr_seconds=seconds,
            collection_seconds=0.004,
            processing_seconds=0.005,
        )
    stats.record_translation(
        stability_seconds=0.08,
        queue_seconds=0.002,
        llm_seconds=None if cached else 1.25,
        total_seconds=1.8,
        batch_size=3,
    )
    return (
        "RefraTranslator live diagnostics\n实时统计：OCR 2 次\n"
        + "延迟统计：" + stats.render().replace("\n", "；") + "\n"
        + stats.render_ocr_summary() + "\n"
    )


def test_projects_existing_runtime_generated_statistics_without_deriving_values() -> None:
    result = parse_latency_diagnostics(completed_log())
    assert result["available"] is True
    assert result["scope"] == "运行结束后生成 · 所有 Profile 共用"
    assert "最近扫描 · 整帧回退" in result["ocr"]
    assert "流程总计：932ms" in result["ocr"]
    assert "线程排队：0ms" in result["ocr"]
    assert "结果接收：4ms" in result["ocr"]
    assert "局部 ROI · 累计 1 次 / 1 个样本" in result["summary"]
    assert "整帧 · 累计 1 次 / 1 个样本" in result["summary"]
    assert "OCR P50：800ms · P95：800ms" in result["summary"]
    assert "阶段均值" in result["summary"]
    assert "P50" not in result["ocr"]
    assert "稳定确认：80ms\n翻译排队：2ms\nLLM 请求：1.25s" in result["translation"]
    assert "各自独立" in result["translation"]
    assert "最近总延迟：1.80s" in result["summary"]
    assert "OCR：800ms" in result["summary"]
    assert "LLM：1.25s" in result["summary"]
    assert "P50" not in result["translation"]
    assert "平均" not in result["translation"]
    assert "不表示显示完成" in result["summary"]


def test_cached_translation_is_not_reported_as_zero_llm_duration() -> None:
    result = parse_latency_diagnostics(completed_log(cached=True))
    assert "LLM 请求：缓存命中" in result["translation"]
    assert "LLM：未产生" in result["summary"]
    assert "LLM：0ms" not in result["summary"]


@pytest.mark.parametrize("text", ["", "initializing OCR\n[RefraTranslator Live] ready\n", "延迟统计：broken\n"])
def test_unfinished_missing_or_invalid_statistics_remain_unavailable(text: str) -> None:
    result = parse_latency_diagnostics(text)
    assert result["available"] is False
    assert "尚无" in result["status"]
    assert all("等待运行结束后刷新" in result[key] for key in ("ocr", "translation", "summary"))


def test_partial_logs_preserve_only_recorded_metrics() -> None:
    result = parse_latency_diagnostics("实时统计：OCR 1 次\n延迟统计：最近：OCR 23ms · 总计 1.01s\n")
    assert result["available"] is True
    assert "最近 OCR 计算：23ms" in result["ocr"]
    assert "稳定确认：未产生" in result["translation"]
    assert "LLM 请求：未产生" in result["translation"]
    assert "最近总延迟：1.01s" in result["summary"]
    assert "总计：未产生" in result["summary"]


def test_final_completion_does_not_reuse_an_older_runs_missing_statistics() -> None:
    result = parse_latency_diagnostics(completed_log() + "实时统计：OCR 0 次\n")
    assert result["available"] is False
    assert "P95" not in result["ocr"]


def test_projects_the_recorded_ocr_window_without_recalculating_percentiles() -> None:
    stats = LiveLatencyStats()
    for _ in range(300):
        stats.record_ocr_pipeline(
            scan_kind="roi", scan_label="局部 ROI",
            change_activity_seconds=0, scheduling_seconds=0,
            preparation_seconds=0, worker_queue_seconds=0,
            ocr_seconds=0.123, collection_seconds=0, processing_seconds=0,
        )
    result = parse_latency_diagnostics(stats.render_ocr_summary())
    assert "累计 300 次 / 最近 256 个样本" in result["summary"]
    assert "流程 P50：123ms · P95：123ms" in result["summary"]
    assert "尚无翻译流程统计" in result["translation"]


def test_bounded_file_read_and_shared_scope_do_not_modify_the_log(tmp_path: Path) -> None:
    log_path = tmp_path / "live.log"
    assert read_latency_diagnostics(log_path)["available"] is False
    assert not log_path.exists()
    content = "x" * (MAX_LOG_TAIL_BYTES * 2) + "\n" + completed_log()
    log_path.write_text(content, encoding="utf-8")
    result = read_latency_diagnostics(log_path)
    assert result["available"] is True
    assert "所有 Profile 共用" in result["scope"]
    assert log_path.read_text(encoding="utf-8") == content


def test_rejects_nonfinite_negative_and_unrelated_log_fragments() -> None:
    result = parse_latency_diagnostics(
        "原文：延迟统计：最近：OCR 5ms\n"
        "延迟统计：最近：OCR -1ms · LLM infs · 总计 nans\n"
    )
    assert result["available"] is False
