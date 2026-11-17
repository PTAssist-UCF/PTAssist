"""Plain normalized image landmarks, following the AI team's prototype."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class Landmark:
    """Image coordinates and pose-provider confidence scores, normally in [0, 1]."""

    x: float
    y: float
    visibility: float = 1.0
    presence: float = 1.0

    @property
    def confidence(self) -> float:
        """Both visibility and presence must support a measurement."""
        return min(self.visibility, self.presence)


def frame_landmarks(frame: Mapping[str, Any]) -> dict[str, Landmark]:
    """One keypoint frame's landmarks by name; empty when nobody was found."""
    landmarks = frame["landmarks"] or {}
    return {name: Landmark(*values) for name, values in landmarks.items()}
