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
