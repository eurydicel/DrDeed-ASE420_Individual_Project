"""Closure calculations for survey traverses."""

import math

from ..contracts.interfaces import ITraverseCalculator, ITraverseValidationService
from ..domain.models import Bearing, ClosureReport, Point2D, TraverseModel
from .calculator import StandardTraverseCalculator


class SurveyClosureValidator(ITraverseValidationService): #handle closure creation
    def __init__(self, calculator: ITraverseCalculator | None = None) -> None:
        self._calculator = (
            calculator if calculator is not None else StandardTraverseCalculator()
        )

    def evaluate_closure( #populates a closure report
        self,
        traverse: TraverseModel,
        pob: Point2D,
        min_precision_threshold: float,
    ) -> ClosureReport:
        """Evaluate closure against a minimum precision denominator (for example, 5000 for 1:5000)."""
        if not math.isfinite(min_precision_threshold) or min_precision_threshold <= 0:
            raise ValueError("Minimum precision threshold must be finite and positive.")

        points = self._calculator.compute_coordinates(traverse, pob)
        endpoint = points[-1]
        delta_easting = endpoint.easting - pob.easting
        delta_northing = endpoint.northing - pob.northing
        closure_error = math.hypot(delta_easting, delta_northing)
        perimeter = math.fsum(call.distance.value for call in traverse.calls)
        precision_ratio = math.inf if closure_error == 0.0 else perimeter / closure_error

        closure_bearing = None
        if closure_error > 0.0:
            closure_bearing = Bearing.from_azimuth_degrees(
                math.degrees(math.atan2(delta_easting, delta_northing))
            )

        return ClosureReport(
            total_perimeter=perimeter,
            closure_error_distance=closure_error,
            precision_ratio=precision_ratio,
            closure_error_bearing=closure_bearing,
            acceptable=precision_ratio >= min_precision_threshold,
        )
