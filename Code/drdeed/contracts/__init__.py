"""Protocols defining the service boundaries."""

from .interfaces import (
    ICadAnnotationRenderer,
    ICadDrawer,
    ICadExportService,
    ICadLayerManager,
    IDocumentIngestionService,
    IOcrExtractionService,
    IOcrPreProcessor,
    IOcrQualityEvaluator,
    IOcrRetryPolicy,
    IParsingRecoveryService,
    ISurveyParser,
    ISurveyParsingService,
    ITextExtractor,
    ITextExtractorRegistry,
    ITraverseCalculator,
    ITraverseValidationService,
)

__all__ = [
    "ICadAnnotationRenderer",
    "ICadDrawer",
    "ICadExportService",
    "ICadLayerManager",
    "IDocumentIngestionService",
    "IOcrExtractionService",
    "IOcrPreProcessor",
    "IOcrQualityEvaluator",
    "IOcrRetryPolicy",
    "IParsingRecoveryService",
    "ISurveyParser",
    "ISurveyParsingService",
    "ITextExtractor",
    "ITextExtractorRegistry",
    "ITraverseCalculator",
    "ITraverseValidationService",
]
