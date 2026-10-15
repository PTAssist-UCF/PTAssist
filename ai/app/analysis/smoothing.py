"""Time-based exponential smoothing of scalar measurements."""

import math


class ExponentialSmoother:
    """Smooth one signal; use a separate instance for each angle or other metric."""

    def __init__(
        self, tau_seconds: float = 0.12, max_gap_seconds: float = 0.75
    ) -> None:
        """Set the time constant and tracking-gap limit, following the prototype."""
        if not math.isfinite(tau_seconds) or tau_seconds <= 0:
            raise ValueError("tau_seconds must be finite and positive")
        if not math.isfinite(max_gap_seconds) or max_gap_seconds <= 0:
            raise ValueError("max_gap_seconds must be finite and positive")
        self._tau_seconds = tau_seconds
        self._max_gap_seconds = max_gap_seconds
        self.reset()

    def reset(self) -> None:
        """Clear history before another clip or a change of tracked side."""
        self._value: float | None = None
        self._last_valid_time: float | None = None
        self._last_time: float | None = None

    def update(self, value: float | None, timestamp_seconds: float) -> float | None:
        """Smooth a finite value at a strictly increasing, nonnegative timestamp.

        None marks a rejected frame and returns None, never an invented measurement.
        A gap longer than max_gap_seconds clears the previous signal. Timestamps
        refer to video time, so the smoothing strength is independent of frame rate.
        """
        if not math.isfinite(timestamp_seconds) or timestamp_seconds < 0:
            raise ValueError("Timestamp must be finite and nonnegative")
        if self._last_time is not None and timestamp_seconds <= self._last_time:
            raise ValueError("Timestamps must be strictly increasing")
        if value is not None and not math.isfinite(value):
            raise ValueError("Measurement must be finite or None")

        self._last_time = timestamp_seconds
        if value is None:
            return None
        if self._value is not None and self._last_valid_time is not None:
            gap = timestamp_seconds - self._last_valid_time
            if gap <= self._max_gap_seconds:
                # expm1 preserves accuracy for short intervals.
                alpha = -math.expm1(-gap / self._tau_seconds)
                value = (1 - alpha) * self._value + alpha * value
        self._value = value
        self._last_valid_time = timestamp_seconds
        return value
