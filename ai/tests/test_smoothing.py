"""Time-based smoothing and abstention across synthetic tracking gaps."""

import math

import pytest

from app.analysis.smoothing import ExponentialSmoother


def test_first_sample_and_constant_signal() -> None:
    smoother = ExponentialSmoother()
    for timestamp in (0, 0.1, 0.3, 0.5):
        assert smoother.update(90, timestamp) == pytest.approx(90)


def test_step_response_at_one_time_constant() -> None:
    smoother = ExponentialSmoother(tau_seconds=0.2)
    assert smoother.update(0, 0) == 0
    assert smoother.update(100, 0.2) == pytest.approx(63.2120558829)


def test_response_is_independent_of_frame_rate() -> None:
    coarse, fine = ExponentialSmoother(), ExponentialSmoother()
    coarse.update(0, 0)
    fine.update(0, 0)
    coarse_result = coarse.update(100, 0.5)
    for index in range(1, 16):
        fine_result = fine.update(100, index / 30)
    assert fine_result == pytest.approx(coarse_result)


def test_short_missing_gap_abstains_and_preserves_elapsed_time() -> None:
    smoother = ExponentialSmoother(tau_seconds=0.2)
    assert smoother.update(None, 0) is None
    assert smoother.update(0, 0.1) == 0
    assert smoother.update(None, 0.2) is None
    assert smoother.update(100, 0.3) == pytest.approx(63.2120558829)


@pytest.mark.parametrize("report_missing_frame", [True, False])
def test_long_gap_restarts_from_the_new_measurement(
    report_missing_frame: bool,
) -> None:
    smoother = ExponentialSmoother(max_gap_seconds=0.75)
    smoother.update(10, 0)
    if report_missing_frame:
        assert smoother.update(None, 0.8) is None
    assert smoother.update(100, 1) == 100


def test_gap_at_limit_keeps_history() -> None:
    smoother = ExponentialSmoother(tau_seconds=1, max_gap_seconds=0.75)
    smoother.update(0, 0)
    assert smoother.update(100, 0.75) == pytest.approx(52.7633447259)


def test_reset_starts_another_clip() -> None:
    smoother = ExponentialSmoother()
    smoother.update(10, 5)
    smoother.reset()
    assert smoother.update(100, 0) == 100


@pytest.mark.parametrize("bad", [0, -1, math.nan, math.inf])
@pytest.mark.parametrize("option", ["tau_seconds", "max_gap_seconds"])
def test_invalid_options_are_rejected(option: str, bad: float) -> None:
    with pytest.raises(ValueError, match="finite and positive"):
        ExponentialSmoother(**{option: bad})


@pytest.mark.parametrize("timestamp", [0, -1, math.nan, math.inf])
def test_invalid_timestamps_do_not_change_history(timestamp: float) -> None:
    smoother = ExponentialSmoother(tau_seconds=0.2)
    smoother.update(0, 0)
    with pytest.raises(ValueError):
        smoother.update(100, timestamp)
    assert smoother.update(100, 0.2) == pytest.approx(63.2120558829)


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_invalid_values_do_not_poison_the_signal(bad: float) -> None:
    smoother = ExponentialSmoother()
    smoother.update(10, 0)
    with pytest.raises(ValueError, match="Measurement"):
        smoother.update(bad, 0.1)
    assert smoother.update(10, 0.1) == 10
