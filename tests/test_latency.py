import pytest

from game_screen_translator.live.latency import LiveLatencyStats


def test_latency_stats_render_latest_and_peaks() -> None:
    stats = LiveLatencyStats()

    assert stats.render() == "延迟统计：等待首个 OCR 样本……"

    stats.record_ocr(0.876)
    stats.record_translation(
        stability_seconds=1.25,
        queue_seconds=0.012,
        llm_seconds=2.5,
        total_seconds=4.9,
        batch_size=8,
    )

    rendered = stats.render()
    assert "最近（8 条）：OCR 876ms" in rendered
    assert "稳定 1.25s" in rendered
    assert "排队 12ms" in rendered
    assert "LLM 2.50s" in rendered
    assert "总计 4.90s" in rendered

    stats.record_ocr(0.5)
    stats.record_translation(
        stability_seconds=0.4,
        queue_seconds=0.001,
        llm_seconds=None,
        total_seconds=0.7,
        batch_size=1,
    )

    rendered = stats.render()
    assert "最近（1 条）" in rendered
    assert "LLM 缓存命中" in rendered
    assert "峰值：OCR 876ms · 稳定 1.25s · 排队 12ms · LLM 2.50s · 总计 4.90s" in rendered


def test_latency_stats_reject_invalid_measurements() -> None:
    stats = LiveLatencyStats()

    with pytest.raises(ValueError, match="OCR"):
        stats.record_ocr(-0.1)
    with pytest.raises(ValueError, match="batch_size"):
        stats.record_translation(
            stability_seconds=0,
            queue_seconds=0,
            llm_seconds=None,
            total_seconds=0,
            batch_size=0,
        )


def test_ocr_pipeline_latency_separates_roi_and_full_frame_samples() -> None:
    stats = LiveLatencyStats()

    latest = stats.record_ocr_pipeline(
        scan_kind="roi",
        scan_label="局部 ROI",
        change_activity_seconds=0.10,
        scheduling_seconds=0.20,
        preparation_seconds=0.03,
        worker_queue_seconds=0.01,
        ocr_seconds=0.40,
        collection_seconds=0.02,
        processing_seconds=0.04,
    )
    stats.record_ocr_pipeline(
        scan_kind="roi",
        scan_label="局部 ROI",
        change_activity_seconds=0.20,
        scheduling_seconds=0.30,
        preparation_seconds=0.05,
        worker_queue_seconds=0.02,
        ocr_seconds=0.80,
        collection_seconds=0.03,
        processing_seconds=0.20,
    )
    stats.record_ocr_pipeline(
        scan_kind="full",
        scan_label="整帧回退",
        change_activity_seconds=0.25,
        scheduling_seconds=0.15,
        preparation_seconds=0.05,
        worker_queue_seconds=0.01,
        ocr_seconds=1.20,
        collection_seconds=0.04,
        processing_seconds=0.10,
    )

    assert latest.total_seconds == pytest.approx(0.80)
    assert stats.latest_ocr_breakdown is not None
    assert stats.latest_ocr_breakdown.scan_kind == "full"
    assert "画面最近［整帧回退］" in stats.render()
    summary = stats.render_ocr_summary()
    assert "局部 ROI累计 2 次" in summary
    assert "总计 P50 800ms/P95 1.60s" in summary
    assert "整帧累计 1 次" in summary
    assert "OCR P50 1.20s/P95 1.20s" in summary
    assert "阶段均值" in summary


def test_ocr_pipeline_latency_rejects_unknown_or_invalid_phases() -> None:
    stats = LiveLatencyStats()
    valid = dict(
        scan_label="局部 ROI",
        change_activity_seconds=0,
        scheduling_seconds=0,
        preparation_seconds=0,
        worker_queue_seconds=0,
        ocr_seconds=0.1,
        collection_seconds=0,
        processing_seconds=0,
    )

    with pytest.raises(ValueError, match="scan_kind"):
        stats.record_ocr_pipeline(scan_kind="unknown", **valid)
    with pytest.raises(ValueError, match="OCR 调度"):
        stats.record_ocr_pipeline(
            scan_kind="roi",
            **{**valid, "scheduling_seconds": float("nan")},
        )
