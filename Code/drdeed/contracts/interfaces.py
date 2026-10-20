"""Service contracts corresponding to the UML interfaces."""

from collections.abc import Sequence
from typing import Protocol

from ezdxf.document import Drawing
from ezdxf.layouts import Modelspace

from ..domain.models import (
    CadExportConfig,
    ClosureReport,
    Document,
    OcrQualityScore,
    OcrResult,
    ParsedCall,
    ParsingCorrectionFeedback,
    Point2D,
    TraverseModel,
)


class IDocumentIngestionService(Protocol):
    def ingest(self, file_path: str) -> Document: ...


class ITextExtractor(Protocol):
    def supports(self, doc: Document) -> bool: ...

    def extract_text(self, doc: Document) -> OcrResult: ...


class IOcrPreProcessor(Protocol):
    def process(self, doc: Document) -> Document: ...


class IOcrQualityEvaluator(Protocol):
    def evaluate(self, result: OcrResult) -> OcrQualityScore: ...


class IOcrRetryPolicy(Protocol):
    def should_retry(self, score: OcrQualityScore, attempt_count: int) -> bool: ...

    def get_next_extractor(
        self,
        candidates: Sequence[ITextExtractor],
        attempt_count: int,
    ) -> ITextExtractor: ...


class ITextExtractorRegistry(Protocol):
    def register_extractor(self, extractor: ITextExtractor) -> None: ...

    def find_supported_extractors(self, doc: Document) -> list[ITextExtractor]: ...


class IOcrExtractionService(Protocol):
    def extract(self, doc: Document) -> OcrResult: ...


class ISurveyParser(Protocol):
    def parse(self, raw_text: str) -> TraverseModel: ...


class IParsingRecoveryService(Protocol):
    def retry_with_feedback(
        self,
        raw_text: str,
        feedback: ParsingCorrectionFeedback,
    ) -> TraverseModel: ...


class ISurveyParsingService(Protocol):
    def parse(self, raw_text: str) -> TraverseModel: ...

    def retry_with_feedback(
        self,
        raw_text: str,
        feedback: ParsingCorrectionFeedback,
    ) -> TraverseModel: ...


class ITraverseCalculator(Protocol):
    def compute_coordinates(
        self,
        traverse: TraverseModel,
        pob: Point2D,
    ) -> list[Point2D]: ...


class ITraverseValidationService(Protocol):
    def evaluate_closure(
        self,
        traverse: TraverseModel,
        pob: Point2D,
        min_precision_threshold: float,
    ) -> ClosureReport: ...


class ICadLayerManager(Protocol):
    def initialize_standard_layers(
        self,
        document: Drawing,
        layer_prefix: str,
    ) -> None: ...

    def get_layer_name(self, purpose: str, layer_prefix: str) -> str: ...


class ICadAnnotationRenderer(Protocol):
    def annotate_call(
        self,
        modelspace: Modelspace,
        start_point: Point2D,
        end_point: Point2D,
        call: ParsedCall,
        config: CadExportConfig,
    ) -> None: ...


class ICadDrawer(Protocol):
    def draw_traverse(
        self,
        document: Drawing,
        points: Sequence[Point2D],
        traverse: TraverseModel,
        config: CadExportConfig,
    ) -> None: ...


class ICadExportService(Protocol):
    def generate_dxf_file(
        self,
        points: Sequence[Point2D],
        traverse: TraverseModel,
        config: CadExportConfig,
    ) -> str: ...


class IChatModelClient(Protocol):
    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        response_schema: dict[str, object],
    ) -> str: ...
