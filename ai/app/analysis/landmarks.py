"""Plain normalized image landmarks, following the AI team's prototype."""

from dataclasses import dataclass


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
