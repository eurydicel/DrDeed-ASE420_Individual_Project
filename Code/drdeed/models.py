"""Domain models for a straight-line survey traverse."""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import math
import re


@dataclass(frozen=True)
class Point2D: #points with checks to make sure they are valid
    easting: float
    northing: float

    def __post_init__(self) -> None: 
        if not math.isfinite(self.easting) or not math.isfinite(self.northing):
            raise ValueError("Point coordinates must be finite.")


@dataclass(frozen=True)
class Bearing:
    """A legal quadrant bearing with degrees, minutes, and decimal seconds."""

    quadrant: str
    degrees: int
    minutes: int
    seconds: Decimal

    def __post_init__(self) -> None:
        if self.quadrant not in {"NE", "SE", "SW", "NW"}: #four quadrants
            raise ValueError("Bearing quadrant must be NE, SE, SW, or NW.")
        if not isinstance(self.degrees, int) or not 0 <= self.degrees <= 90: #degree limiter
            raise ValueError("Bearing degrees must be an integer in [0, 90].")
        if not isinstance(self.minutes, int) or not 0 <= self.minutes < 60: #minute limiter
            raise ValueError("Bearing minutes must be an integer in [0, 60).")
        try:
            seconds = Decimal(str(self.seconds)) #ensure seconds is a decimal and not float
        except InvalidOperation as error:
            raise ValueError("Bearing seconds must be a finite number in [0, 60).") from error
        if not seconds.is_finite() or not 0 <= seconds < 60: #second limiter
            raise ValueError("Bearing seconds must be a finite number in [0, 60).")
        if self.degrees == 90 and (self.minutes != 0 or seconds != 0): #90 degree edge case
            raise ValueError("A 90-degree bearing cannot have minutes or seconds.")
        object.__setattr__(self, "seconds", seconds)

    @classmethod
    def from_quadrant_text(cls, text: str) -> "Bearing":
        """Parse notation such as N12°30'15.5\"E."""
        match = re.fullmatch( #regex the bearing
            r"""\s*([NS])\s*(\d{1,2})\s*°\s*(\d{1,2})\s*'\s*
                (\d{1,2}(?:\.\d+)?)\s*"\s*([EW])\s*""",
            text,
            flags=re.VERBOSE,
        )
        if match is None:
            raise ValueError(
                "Bearing must use quadrant DMS notation, such as N12°30'15\"E."
            )
        north_south, degrees, minutes, seconds, east_west = match.groups()
        return cls( #return the bearing parts as class attributes
            quadrant=north_south + east_west,
            degrees=int(degrees),
            minutes=int(minutes),
            seconds=Decimal(seconds),
        )

    @classmethod
    def from_azimuth_degrees(cls, azimuth_degrees: float) -> "Bearing": #convert to bearing for things like closures
        """Convert an azimuth to a quadrant bearing rounded to the nearest second."""
        if not math.isfinite(azimuth_degrees):
            raise ValueError("Bearing azimuth must be finite.")
        azimuth = azimuth_degrees % 360.0 #normalize to standard 0-360 range
        if azimuth <= 90.0: #match quadrants
            quadrant, angle = "NE", azimuth
        elif azimuth <= 180.0:
            quadrant, angle = "SE", 180.0 - azimuth
        elif azimuth <= 270.0:
            quadrant, angle = "SW", azimuth - 180.0
        else:
            quadrant, angle = "NW", 360.0 - azimuth

        total_seconds = ( #round to nearest second avoiding pesky floating errors
            Decimal(str(angle)) * Decimal(3600)
        ).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        degrees, remainder = divmod(total_seconds, Decimal(3600))
        minutes, seconds = divmod(remainder, Decimal(60))
        return cls(quadrant, int(degrees), int(minutes), seconds)

    @property
    def azimuth_degrees(self) -> float:
        """Return the clockwise-from-north azimuth used by coordinate math."""
        angle = ( #convert to decimal degrees
            self.degrees
            + self.minutes / 60.0
            + float(self.seconds) / 3600.0 #while float isn't always perfect, it is within one second of precision, which is generally fine for deed drawings
        )
        if self.quadrant == "NE": #quadrant interpretation
            return angle
        if self.quadrant == "SE":
            return 180.0 - angle
        if self.quadrant == "SW":
            return 180.0 + angle
        return (360.0 - angle) % 360.0

    def to_quadrant_text(self) -> str:
        """Return a string in quadrant DMS notation, such as N12°30'15.5\"E."""
        seconds = format(self.seconds, "f")
        whole_seconds, separator, fractional_seconds = seconds.partition(".")
        seconds = f"{int(whole_seconds):02d}"
        if separator:
            seconds += f".{fractional_seconds}"
        return (
            f"{self.quadrant[0]}{self.degrees}°{self.minutes:02d}'"
            f'{seconds}"{self.quadrant[1]}'
        )


@dataclass(frozen=True)
class Distance:
    """A positive distance, using the same unspecified unit throughout a traverse."""

    value: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.value) or self.value <= 0.0:
            raise ValueError("Distance must be a finite positive number.")


@dataclass(frozen=True)
class ParsedCall: #a line in bearing format
    sequence_index: int
    bearing: Bearing
    distance: Distance
    raw_text: str = ""

    def __post_init__(self) -> None:
        if self.sequence_index < 1:
            raise ValueError("Call sequence index must be at least 1.")


@dataclass(frozen=True)
class ClosureReport: #closure report, important for double checking 
    total_perimeter: float
    closure_error_distance: float
    precision_ratio: float
    closure_error_bearing: Bearing | None
    acceptable: bool

    def is_acceptable(self) -> bool:
        return self.acceptable


@dataclass(frozen=True)
class TraverseModel: #a series of calls with a POB location description
    calls: tuple[ParsedCall, ...]
    point_of_beginning_desc: str = ""
    source_text: str = ""

    def __post_init__(self) -> None:
        if not self.calls:
            raise ValueError("A traverse must contain at least one call.")
        expected_indices = tuple(range(1, len(self.calls) + 1))
        actual_indices = tuple(call.sequence_index for call in self.calls)
        if actual_indices != expected_indices:
            raise ValueError("Call sequence indices must be contiguous and start at 1.")
