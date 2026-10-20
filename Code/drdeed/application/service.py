"""Application workflow for parsing, closure checking, and DXF export.""" #orchestrator

import math

from ..contracts.interfaces import (
    ICadExportService,
    ITraverseCalculator,
    ITraverseValidationService,
    ISurveyParsingService,
)
from ..domain.models import (
    CadExportConfig,
    ClosureReport,
    Point2D,
    SurveyProcessingResult,
    TraverseModel,
)
from .parsing import SurveyFeedbackService


class SurveyProcessingApplicationService: #orchestrate the process
    def __init__( 
        self,
        parsing_service: ISurveyParsingService,
        calculator: ITraverseCalculator,
        validation_service: ITraverseValidationService,
        export_service: ICadExportService,
        feedback_service: SurveyFeedbackService | None = None,
    ) -> None:
        self._parsing_service = parsing_service
        self._calculator = calculator
        self._validation_service = validation_service
        self._export_service = export_service
        self._feedback_service = feedback_service or SurveyFeedbackService()

    def process_survey_text( #the workflow
        self,
        raw_text: str,
        pob: Point2D,
        min_precision_threshold: float,
        export_config: CadExportConfig,
    ) -> SurveyProcessingResult:
        if not raw_text.strip(): #validate user inputs
            raise ValueError("Legal-description text must not be empty.")
        if (
            not math.isfinite(min_precision_threshold)
            or min_precision_threshold <= 0
        ):
            raise ValueError("Minimum precision threshold must be finite and positive.")

        traverse = self._parsing_service.parse(raw_text) #parse using classes in parsing.py
        points, report = self._calculate_and_validate(#check and validate within minimum threshold
            traverse,
            pob,
            min_precision_threshold,
        )
        correction_attempts = 0

        if not report.is_acceptable(): #try to correct
            feedback = self._feedback_service.generate_feedback(traverse, report)
            traverse = self._parsing_service.retry_with_feedback(raw_text, feedback)
            points, report = self._calculate_and_validate(
                traverse,
                pob,
                min_precision_threshold,
            )
            correction_attempts = 1

        output_path = None
        if report.is_acceptable(): #if unacceptable, don't output
            output_path = self._export_service.generate_dxf_file(
                points,
                traverse,
                export_config,
            )

        return SurveyProcessingResult(
            traverse=traverse,
            closure_report=report,
            points=tuple(points),
            output_file_path=output_path,
            correction_attempts=correction_attempts,
        )

    def _calculate_and_validate( #get the closure
        self,
        traverse: TraverseModel,
        pob: Point2D,
        min_precision_threshold: float,
    ) -> tuple[list[Point2D], ClosureReport]:
        points = self._calculator.compute_coordinates(traverse, pob)
        report = self._validation_service.evaluate_closure(
            traverse,
            pob,
            min_precision_threshold,
        )
        return points, report
