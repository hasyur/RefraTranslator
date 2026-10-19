import pytest

from game_screen_translator.live.mouse_dwell import MouseDwellGate


def test_first_position_triggers_after_configured_dwell():
    gate = MouseDwellGate(300)

    assert gate.poll((100, 100), 1.0) is None
    assert gate.poll((100, 100), 1.299) is None
    request = gate.poll((100, 100), 1.3)

    assert request is not None
    assert request.position == (100.0, 100.0)
    assert gate.in_flight


def test_new_trigger_requires_thirty_pixel_motion_then_dwell():
    gate = MouseDwellGate(100)
    gate.poll((100, 100), 0.0)
    first = gate.poll((100, 100), 0.1)
    assert first is not None
    assert gate.complete(first)

    assert gate.poll((129, 100), 1.0) is None
    assert gate.poll((129, 100), 1.2) is None
    second = gate.poll((130, 100), 2.0)

    assert second is not None
    assert second.request_id == first.request_id + 1


def test_two_pixel_jitter_restarts_stability_and_small_jitter_does_not():
    gate = MouseDwellGate(100)
    gate.poll((0, 0), 0.0)
    gate.poll((1, 0), 0.05)
    assert gate.poll((1, 0), 0.1) is not None

    gate = MouseDwellGate(100)
    gate.poll((0, 0), 0.0)
    gate.poll((2, 0), 0.05)
    assert gate.poll((2, 0), 0.149) is None
    assert gate.poll((2, 0), 0.151) is not None


def test_in_flight_request_waits_for_completion_and_stale_request_does_not_anchor():
    gate = MouseDwellGate(0)
    gate.poll((0, 0), 0.0)
    request = gate.poll((0, 0), 0.02)
    assert request is not None
    assert gate.poll((50, 0), 0.04) is None
    assert not gate.request_is_current(request)
    assert not gate.complete(request)

    # The motion during the prior transaction already exceeded the threshold
    # and settled for longer than the configured zero dwell.
    next_request = gate.poll((50, 0), 0.06)
    assert next_request is not None


def test_gate_does_not_reserve_while_capture_is_unavailable():
    gate = MouseDwellGate(0)
    gate.poll((10, 10), 0.0)
    assert gate.poll((10, 10), 0.1, ready=False) is None
    request = gate.poll((10, 10), 0.2, ready=True)
    assert request is not None


@pytest.mark.parametrize("value", [-1, 10_001, True, 1.5])
def test_gate_rejects_invalid_dwell_ms(value):
    with pytest.raises(ValueError, match="dwell_ms"):
        MouseDwellGate(value)
