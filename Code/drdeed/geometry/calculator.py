"""Coordinate calculation for straight-line survey traverses."""

import math

from ..contracts.interfaces import ITraverseCalculator
from ..domain.models import Point2D, TraverseModel


class CurveCalculationNotSupportedError(NotImplementedError):
    """Raised when curve calls reach the straight-line coordinate calculator."""


class StandardTraverseCalculator(ITraverseCalculator):
    def compute_coordinates(
        self,
        traverse: TraverseModel, #essentially a list of line calls
        pob: Point2D,
    ) -> list[Point2D]:
        """Return the point of beginning followed by each successive endpoint."""
        points = [pob]
        current = pob

        for call in traverse.calls: #loop through each line
            if call.is_curve():
                raise CurveCalculationNotSupportedError(
                    f"Curve call {call.sequence_index} is parsed but curve "
                    "coordinate calculations are not implemented."
                )
            if call.bearing is None or call.distance is None:
                raise ValueError(
                    f"Line call {call.sequence_index} is missing bearing or distance."
                )
            azimuth_radians = math.radians(call.bearing.azimuth_degrees) #convert to radians
            distance = call.distance.value 
            current = Point2D( #use the fun triangle math to figure out where the next point is
                easting=current.easting + distance * math.sin(azimuth_radians),
                northing=current.northing + distance * math.cos(azimuth_radians),
            )
            points.append(current)

        return points
