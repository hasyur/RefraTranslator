"""Read the existing end-of-run log statistics without collecting new timings."""

from __future__ import annotations

import re
from pathlib import Path

MAX_LOG_TAIL_BYTES = 128 * 1024
_DURATION = r"\d+(?:\.\d+)?(?:ms|s)"
_PHASES = ("变化持续", "调度", "准备", "线程", "OCR", "接收", "更新")
_METRICS = ("OCR", "稳定", "排队", "LLM", "总计")
_PHASE_NAMES = {"线程": "线程排队", "接收": "结果接收", "更新": "结果更新"}
_SCOPE = "运行结束后生成 · 所有 Profile 共用"


def _values(text: str, names: tuple[str, ...]) -> dict[str, str]:
    values: dict[str, str] = {}
    for part in text.split(" · "):
        match = re.fullmatch(rf"({'|'.join(names)})\s+({_DURATION}|缓存命中)", part.strip())
        if match and (match[2] != "缓存命中" or match[1] == "LLM"):
            values[match[1]] = match[2]
    return values


def _phase_lines(values: dict[str, str]) -> list[str]:
    fields = [f"{_PHASE_NAMES.get(name, name)}：{values.get(name, '未产生')}" for name in _PHASES]
    return [" · ".join(fields[index:index + 2]) for index in range(0, len(fields), 2)]


def parse_latency_diagnostics(log_text: str) -> dict[str, str | bool]:
    """Project only recorded latest/peak values and OCR window statistics.

    Latest OCR and translation timings belong to independent completions.
    Peaks are also independent; this projection never sums them or infers a
    translation percentile. The file is shared across all Profiles.
    """
    lines = log_text.splitlines()
    # startLive replaces the log. If a concatenated diagnostic file is read,
    # never merge an older completion with the final completion's partial data.
    boundaries = [index for index, line in enumerate(lines) if line.startswith("实时统计：")]
    if boundaries:
        lines = lines[boundaries[-1]:]
    latency_lines = [line for line in lines if line.startswith("延迟统计：")]
    sections = latency_lines[-1][len("延迟统计："):].split("；") if latency_lines else []
    latest: dict[str, str] = {}
    peaks: dict[str, str] = {}
    recent_ocr: list[str] = []
    for section in sections:
        if re.match(r"最近(?:（\d+ 条）)?：", section):
            latest = _values(section.split("：", 1)[1], _METRICS)
        elif section.startswith("峰值："):
            peaks = _values(section[len("峰值："):], _METRICS)
        else:
            match = re.fullmatch(r"画面最近［([^\]\n]+)］：(.+)", section)
            if match:
                values = _values(match[2], ("总计", *_PHASES))
                if values:
                    recent_ocr = [f"最近扫描 · {match[1]}", f"流程总计：{values.get('总计', '未产生')}", *_phase_lines(values)]

    ocr_blocks: list[str] = []
    if recent_ocr:
        ocr_blocks.append("\n".join(recent_ocr))
    elif "OCR" in latest:
        ocr_blocks.append(f"最近 OCR 计算：{latest['OCR']}\n扫描阶段统计未产生。")
    window_blocks: list[str] = []
    for kind in ("局部 ROI", "整帧"):
        candidates = [line for line in lines if line.startswith(f"{kind}累计 ")]
        if not candidates:
            continue
        match = re.fullmatch(
            rf"{kind}累计 (\d+) 次（统计 (最近 )?(\d+) 个）："
            rf"总计 P50 ({_DURATION})/P95 ({_DURATION})，"
            rf"OCR P50 ({_DURATION})/P95 ({_DURATION})；阶段均值 (.+)",
            candidates[-1],
        )
        if not match:
            continue
        phases = _values(match[8], _PHASES)
        if not phases:
            continue
        window = f"{'最近 ' if match[2] else ''}{match[3]} 个样本"
        window_blocks.append("\n".join([
            f"{kind} · 累计 {match[1]} 次 / {window}",
            f"流程 P50：{match[4]} · P95：{match[5]}",
            f"OCR P50：{match[6]} · P95：{match[7]}",
            "阶段均值", *_phase_lines(phases),
        ]))

    available = bool(ocr_blocks or window_blocks or latest or peaks)
    translation = "\n".join([
        f"稳定确认：{latest.get('稳定', '未产生')}",
        f"翻译排队：{latest.get('排队', '未产生')}",
        f"LLM 请求：{latest.get('LLM', '未产生')}",
        "最近翻译批次；与最近 OCR 扫描各自独立。",
    ]) if latest else "尚无翻译流程统计，等待运行结束后刷新。"
    summary = "\n".join([
        f"最近总延迟：{latest.get('总计', '未产生')}",
        "画面变化至翻译处理；不表示显示完成。",
        "各项独立峰值",
        *[f"{name}：{peaks.get(name, '未产生')}" for name in _METRICS],
    ]) if latest or peaks else ""
    summary = "\n\n".join([block for block in (summary, *window_blocks) if block])
    if not summary:
        summary = "尚无延迟汇总，等待运行结束后刷新。"
    return {
        "available": available,
        "scope": _SCOPE,
        "status": "读取最近一次运行结束统计。" if available else "尚无运行结束后的延迟统计。",
        "ocr": "\n\n".join(ocr_blocks) if ocr_blocks else "尚无 OCR 流程统计，等待运行结束后刷新。",
        "translation": translation,
        "summary": summary,
    }


def read_latency_diagnostics(log_path: Path) -> dict[str, str | bool]:
    """Read at most the bounded end of the one existing shared log file."""
    try:
        with log_path.open("rb") as handle:
            size = handle.seek(0, 2)
            start = max(0, size - MAX_LOG_TAIL_BYTES)
            handle.seek(start)
            tail = handle.read(MAX_LOG_TAIL_BYTES)
        if start:
            tail = tail.partition(b"\n")[2]  # Discard a clipped first line.
        return parse_latency_diagnostics(tail.decode("utf-8", errors="replace"))
    except OSError:
        result = parse_latency_diagnostics("")
        result["status"] = "日志暂不可读取，等待运行结束后刷新。"
        return result
