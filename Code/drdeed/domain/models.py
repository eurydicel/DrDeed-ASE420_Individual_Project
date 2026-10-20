"""Domain models shared by survey processing services."""

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from enum import Enum
import math
from pathlib import Path
import re
from typing import Any


class FileTypeEnum(str, Enum):
    PDF = "pdf"
    PNG = "png"
    JPEG = "jpeg"
    TIFF = "tiff"
    DOCX = "docx"
    DOC = "doc"
    TXT = "txt"


class CallTypeEnum(str, Enum):
    LINE = "line"
    CURVE = "curve"


class CurveDirection(str, Enum):
    CLOCKWISE = "clockwise"
    COUNTERCLOCKWISE = "counterclockwise"


@dataclass(frozen=True)
class Document:
    file_path: str
    file_type: FileTypeEnum
    raw_bytes: bytes = field(repr=False)

    def get_file_path(self) -> str:
        return self.file_path

    def get_file_type(self) -> FileTypeEnum:
        return self.file_type


@dataclass(frozen=True)
class OcrResult:
    extracted_text: str
    page_count: int
    confidence_score: float
    metadata: dict[str, Any] = field(default_factory=dict)

    def get_extracted_text(self) -> str:
        return self.extracted_text

    def get_confidence_score(self) -> float:
        return self.confidence_score


@dataclass(frozen=True)
class OcrQualityScore:
    engine_confidence: float
    domain_lexicon_score: float
    regex_hit_count: int
    overall_score: float

    def is_acceptable(self, threshold: float) -> bool:
        return self.overall_score >= threshold

    def get_overall_score(self) -> float:
        return self.overall_score


@dataclass(frozen=True)
class Point2D:  # stores coordinates and checks they are finite
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
        if self.quadrant not in {"NE", "SE", "SW", "NW"}:  # four quadrants
            raise ValueError("Bearing quadrant must be NE, SE, SW, or NW.")
        if not isinstance(self.degrees, int) or not 0 <= self.degrees <= 90:  # degree limit
            raise ValueError("Bearing degrees must be an integer in [0, 90].")
        if not isinstance(self.minutes, int) or not 0 <= self.minutes < 60:  # minute limit
            raise ValueError("Bearing minutes must be an integer in [0, 60).")
        try:
            seconds = Decimal(str(self.seconds))  # use decimal seconds for DMS handling
        except InvalidOperation as error:
            raise ValueError(
                "Bearing seconds must be a finite number in [0, 60)."
            ) from error
        if not seconds.is_finite() or not 0 <= seconds < 60:  # second limit
            raise ValueError("Bearing seconds must be a finite number in [0, 60).")
        if self.degrees == 90 and (self.minutes != 0 or seconds != 0):  # 90-degree edge case
            raise ValueError("A 90-degree bearing cannot have minutes or seconds.")
        object.__setattr__(self, "seconds", seconds)

    @classmethod
    def from_quadrant_text(cls, text: str) -> "Bearing":
        """Parse notation such as N12°30'15.5\"E."""
        match = re.fullmatch(  # match the expected quadrant DMS format
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
        return cls(  # store the parsed bearing parts
            quadrant=north_south + east_west,
            degrees=int(degrees),
            minutes=int(minutes),
            seconds=Decimal(seconds),
        )

    @classmethod
    def from_azimuth_degrees(cls, azimuth_degrees: float) -> "Bearing":
        """Convert an azimuth to a quadrant bearing rounded to the nearest second."""
        if not math.isfinite(azimuth_degrees):
            raise ValueError("Bearing azimuth must be finite.")
        azimuth = azimuth_degrees % 360.0  # normalize to 0-360 degrees
        if azimuth <= 90.0:  # choose the quadrant and within-quadrant angle
            quadrant, angle = "NE", azimuth
        elif azimuth <= 180.0:
            quadrant, angle = "SE", 180.0 - azimuth
        elif azimuth <= 270.0:
            quadrant, angle = "SW", azimuth - 180.0
        else:
            quadrant, angle = "NW", 360.0 - azimuth

        total_seconds = (  # round to whole seconds using decimal rounding
            Decimal(str(angle)) * Decimal(3600)
        ).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        degrees, remainder = divmod(total_seconds, Decimal(3600))
        minutes, seconds = divmod(remainder, Decimal(60))
        if degrees == 90 and (minutes != 0 or seconds != 0):
            degrees, minutes, seconds = 90, 0, Decimal(0)
        return cls(quadrant, int(degrees), int(minutes), seconds)

    @property
    def azimuth_degrees(self) -> float:
        """Convert the quadrant bearing to clockwise-from-north decimal degrees."""
        angle = (  # convert DMS to decimal degrees for coordinate calculations
            self.degrees
            + self.minutes / 60.0
            + float(self.seconds) / 3600.0
        )
        if self.quadrant == "NE":  # apply quadrant to get clockwise azimuth
            return angle
        if self.quadrant == "SE":
            return 180.0 - angle
        if self.quadrant == "SW":
            return 180.0 + angle
        return (360.0 - angle) % 360.0

    def to_quadrant_text(self) -> str:
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
    """A positive distance using the traverse's common, unspecified unit."""

    value: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.value) or self.value <= 0.0:
            raise ValueError("Distance must be a finite positive number.")


@dataclass(frozen=True)
class ParsedCall:  # one line or curve call in a traverse
    sequence_index: int
    bearing: Bearing | None
    distance: Distance | None
    raw_text: str = ""
    call_type: CallTypeEnum = CallTypeEnum.LINE
    radius: Distance | None = None
    arc_length: Distance | None = None
    chord_bearing: Bearing | None = None
    chord_distance: Distance | None = None
    curve_direction: CurveDirection | None = None

    def __post_init__(self) -> None:
        if self.sequence_index < 1:
            raise ValueError("Call sequence index must be at least 1.")
        if self.call_type is CallTypeEnum.LINE:
            if self.bearing is None or self.distance is None:
                raise ValueError("A line call requires a bearing and distance.")
        elif self.call_type is not CallTypeEnum.CURVE:
            raise ValueError(f"Unsupported call type: {self.call_type!r}.")

    def is_curve(self) -> bool:
        return self.call_type is CallTypeEnum.CURVE


@dataclass(frozen=True)
class ClosureReport:  # holds closure results for review
    total_perimeter: float
    closure_error_distance: float
    precision_ratio: float
    closure_error_bearing: Bearing | None
    acceptable: bool

    def get_precision_ratio(self) -> float:
        return self.precision_ratio

    def is_acceptable(self) -> bool:
        return self.acceptable


@dataclass(frozen=True)
class ParsingCorrectionFeedback:
    closure_error_distance: float
    precision_ratio: float
    flagged_call_indices: tuple[int, ...]
    correction_hint: str

    def get_flagged_indices(self) -> tuple[int, ...]:
        return self.flagged_call_indices

    def get_correction_hint(self) -> str:
        return self.correction_hint


@dataclass(frozen=True)
class CadExportConfig:
    output_file_path: Path
    layer_prefix: str = "SURVEY"
    text_height: float = 1.0
    include_annotations: bool = True

    def __post_init__(self) -> None:
        if not self.layer_prefix.strip():
            raise ValueError("Layer prefix must not be empty.")
        if not math.isfinite(self.text_height) or self.text_height <= 0:
            raise ValueError("Text height must be finite and positive.")

    def get_output_file_path(self) -> str:
        return str(self.output_file_path)


@dataclass(frozen=True)
class TraverseModel:  # groups ordered calls and the POB description
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

    def get_calls(self) -> tuple[ParsedCall, ...]:
        return self.calls


@dataclass(frozen=True)
class SurveyProcessingResult:
    traverse: TraverseModel
    closure_report: ClosureReport
    points: tuple[Point2D, ...]
    output_file_path: str | None
    correction_attempts: int

    def get_traverse(self) -> TraverseModel:
        return self.traverse
