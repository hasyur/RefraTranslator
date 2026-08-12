import numpy as np
import pytest

from game_screen_translator.live.change_detector import FrameChangeDetector


def test_first_frame_changes_identical_frame_does_not() -> None:
    detector = FrameChangeDetector(threshold=2.0, sample_size=(16, 9))
    frame = np.full((90, 160, 3), 30, dtype=np.uint8)

    assert detector.changed(frame)
    assert not detector.changed(frame.copy())
    assert detector.last_score == pytest.approx(0.0)


def test_luminance_change_above_threshold_triggers() -> None:
    detector = FrameChangeDetector(threshold=5.0, sample_size=(16, 9))
    dark = np.zeros((90, 160, 3), dtype=np.uint8)
    bright = np.full((90, 160, 3), 20, dtype=np.uint8)

    detector.changed(dark)

    assert detector.changed(bright)
    assert detector.last_score == pytest.approx(20.0, abs=0.01)


def test_invalid_frame_shape_is_rejected() -> None:
    detector = FrameChangeDetector()

    with pytest.raises(ValueError, match="灰度或 RGB"):
        detector.changed(np.zeros((2, 3, 4, 5), dtype=np.uint8))


def test_large_frame_is_sampled_before_luminance_conversion() -> None:
    detector = FrameChangeDetector(sample_size=(16, 9))
    frame = np.zeros((2160, 3840, 3), dtype=np.uint8)
    frame[..., 1] = 255

    sample = detector._sample(frame)

    assert sample.shape == (9, 16)
    assert sample.dtype == np.uint8
    assert np.all(sample == 149)
