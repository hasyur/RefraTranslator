import numpy as np
import pytest

from game_screen_translator.ocr.roi import (
    crop_ocr_roi,
    offset_ocr_texts,
    recognize_ocr_roi,
    recognize_ocr_rois,
)
from game_screen_translator.ocr.types import OcrText


def test_crop_ocr_roi_uses_width_height_coordinates() -> None:
    frame = np.arange(8 * 10 * 3, dtype=np.uint8).reshape(8, 10, 3)

    crop, origin = crop_ocr_roi(frame, (2, 3, 4, 2))

    assert origin == (2, 3)
    assert crop.shape == (2, 4, 3)
    assert crop.flags.c_contiguous
    assert np.array_equal(crop, frame[3:5, 2:6])


def test_crop_ocr_roi_rejects_out_of_bounds() -> None:
    frame = np.zeros((100, 200, 3), dtype=np.uint8)

    with pytest.raises(ValueError, match="超出图像"):
        crop_ocr_roi(frame, (150, 20, 100, 40))


def test_offset_ocr_texts_maps_back_to_full_frame() -> None:
    item = OcrText(
        "hello",
        0.9,
        ((1.0, 2.0), (11.0, 2.0), (11.0, 7.0), (1.0, 7.0)),
    )

    result = offset_ocr_texts((item,), left=100, top=200)

    assert result[0].bounds == (101, 202, 111, 207)


def test_recognize_ocr_roi_includes_crop_and_coordinate_mapping() -> None:
    frame = np.zeros((80, 120, 3), dtype=np.uint8)

    class FakeEngine:
        def recognize_frame(self, crop):
            assert crop.shape == (20, 40, 3)
            return (
                OcrText(
                    "text",
                    1.0,
                    ((2.0, 3.0), (12.0, 3.0), (12.0, 9.0), (2.0, 9.0)),
                ),
            )

    result = recognize_ocr_roi(FakeEngine(), frame, (30, 40, 40, 20))

    assert result[0].bounds == (32, 43, 42, 49)


def test_recognize_ocr_rois_preserves_full_frame_reading_order() -> None:
    frame = np.zeros((100, 200, 3), dtype=np.uint8)

    class FakeEngine:
        def recognize_frame(self, crop):
            return (
                OcrText(
                    str(crop.shape[1]),
                    1.0,
                    ((2.0, 3.0), (12.0, 3.0), (12.0, 9.0), (2.0, 9.0)),
                ),
            )

    result = recognize_ocr_rois(
        FakeEngine(), frame, ((100, 60, 50, 20), (20, 10, 40, 20))
    )

    assert [item.text for item in result] == ["40", "50"]
    assert [item.bounds for item in result] == [
        (22, 13, 32, 19),
        (102, 63, 112, 69),
    ]


def test_recognize_ocr_rois_discards_text_clipped_by_internal_edge() -> None:
    frame = np.zeros((100, 200, 3), dtype=np.uint8)

    class FakeEngine:
        def recognize_frame(self, crop):
            return (
                OcrText(
                    "clipped",
                    1.0,
                    ((1.0, 5.0), (20.0, 5.0), (20.0, 15.0), (1.0, 15.0)),
                ),
                OcrText(
                    "safe",
                    1.0,
                    ((20.0, 20.0), (50.0, 20.0), (50.0, 30.0), (20.0, 30.0)),
                ),
            )

    result = recognize_ocr_rois(
        FakeEngine(), frame, ((50, 20, 100, 60),), edge_margin=8
    )

    assert [item.text for item in result] == ["safe"]


def test_recognize_ocr_rois_allows_text_at_original_frame_edge() -> None:
    frame = np.zeros((100, 200, 3), dtype=np.uint8)

    class FakeEngine:
        def recognize_frame(self, crop):
            return (
                OcrText(
                    "screen edge",
                    1.0,
                    ((1.0, 2.0), (30.0, 2.0), (30.0, 12.0), (1.0, 12.0)),
                ),
            )

    result = recognize_ocr_rois(
        FakeEngine(), frame, ((0, 0, 100, 60),), edge_margin=8
    )

    assert [item.text for item in result] == ["screen edge"]
