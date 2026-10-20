"""Coordinate calculation for straight-line survey traverses."""

import math

from .models import Point2D, TraverseModel


class StandardTraverseCalculator:
    def compute_coordinates(
        self,
        traverse: TraverseModel, #essentially a list of line calls
        pob: Point2D,
    ) -> list[Point2D]:
        """Return the point of beginning followed by each successive endpoint."""
        points = [pob]
        current = pob

        for call in traverse.calls: #loop through each line
            azimuth_radians = math.radians(call.bearing.azimuth_degrees) #convert to radians
            distance = call.distance.value 
            current = Point2D( #use the fun triangle math to figure out where the next point is
                easting=current.easting + distance * math.sin(azimuth_radians),
                northing=current.northing + distance * math.cos(azimuth_radians),
            )
            points.append(current)

        return points
