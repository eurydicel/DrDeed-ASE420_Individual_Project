import json
from collections.abc import Sequence
from io import BytesIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import ezdxf

from drdeed import (
    Bearing,
    CadExportConfig,
    CadExportService,
    CallTypeEnum,
    CurveCalculationNotSupportedError,
    CurveCadExportNotSupportedError,
    Distance,
    LlmSurveyParser,
    ParsedCall,
    ParsingCorrectionFeedback,
    Point2D,
    StandardTraverseCalculator,
    SurveyClosureValidator,
    SurveyProcessingApplicationService,
    TraverseModel,
)
from drdeed.application.parsing import TRAVERSE_JSON_SCHEMA
from drdeed.infrastructure.llm.ollama_client import OllamaChatClient


def square_traverse() -> TraverseModel:
    return TraverseModel(
        calls=(
            ParsedCall(1, Bearing.from_quadrant_text("N90°00'00\"E"), Distance(100)),
            ParsedCall(2, Bearing.from_quadrant_text("N0°00'00\"E"), Distance(50)),
            ParsedCall(3, Bearing.from_quadrant_text("N90°00'00\"W"), Distance(100)),
            ParsedCall(4, Bearing.from_quadrant_text("S0°00'00\"E"), Distance(50)),
        )
    )


class FakeChatClient:
    def __init__(self, response: str) -> None:
        self.response = response
        self.schema: dict[str, object] | None = None
        self.user_prompt = ""
        self.system_prompt = ""

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        response_schema: dict[str, object],
    ) -> str:
        self.system_prompt = system_prompt
        self.schema = response_schema
        self.user_prompt = user_prompt
        return self.response


class FailingChatClient:
    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        response_schema: dict[str, object],
    ) -> str:
        raise AssertionError(
            "The strict word-bearing example should not need an LLM: "
            f"{system_prompt!r}, {user_prompt!r}, {response_schema!r}"
        )


class FakeParsingService:
    def __init__(
        self,
        first: TraverseModel,
        retry: TraverseModel | None = None,
    ) -> None:
        self.first = first
        self.retry = retry or first
        self.retry_feedback: ParsingCorrectionFeedback | None = None
        self.source_text = ""

    def parse(self, _raw_text: str) -> TraverseModel:
        self.source_text = _raw_text
        return self.first

    def retry_with_feedback(
        self,
        _raw_text: str,
        feedback: ParsingCorrectionFeedback,
    ) -> TraverseModel:
        self.source_text = _raw_text
        self.retry_feedback = feedback
        return self.retry


class RecordingExporter:
    def __init__(self) -> None:
        self.exported = False
        self.points: tuple[Point2D, ...] | None = None
        self.traverse: TraverseModel | None = None

    def generate_dxf_file(
        self,
        _points: Sequence[Point2D],
        _traverse: TraverseModel,
        config: CadExportConfig,
    ) -> str:
        self.exported = True
        self.points = tuple(_points)
        self.traverse = _traverse
        return str(config.output_file_path)


class ParsingTests(unittest.TestCase):
    def test_example_legal_parses_all_word_bearings_without_llm(self) -> None:
        legal_path = Path(__file__).with_name("example_legal.txt")
        legal_text = legal_path.read_text(encoding="utf-8")

        traverse = LlmSurveyParser(FailingChatClient()).parse(legal_text)

        self.assertEqual(len(traverse.calls), 17)
        self.assertEqual(traverse.point_of_beginning_desc, "")
        self.assertEqual(traverse.source_text, legal_text)
        self.assertEqual(
            traverse.calls[0].bearing.to_quadrant_text(),
            "S88°49'50\"E",
        )
        self.assertEqual(traverse.calls[0].distance, Distance(645.35))
        self.assertEqual(
            traverse.calls[-1].bearing.to_quadrant_text(),
            "N0°42'09\"E",
        )
        self.assertEqual(traverse.calls[-1].distance, Distance(454.05))
        self.assertIn("Section Three (3)", traverse.calls[0].raw_text)
        self.assertIn("point of beginning", traverse.calls[-1].raw_text.lower())

    def test_parser_recognizes_single_letter_bearing_indicators(self) -> None:
        source_text = (
            'N12°30\'15"E, 100 feet; then S0°17\'48"W, 34.77 ft.'
        )

        traverse = LlmSurveyParser(FailingChatClient()).parse(source_text)

        self.assertEqual(len(traverse.calls), 2)
        self.assertEqual(
            traverse.calls[0].bearing.to_quadrant_text(),
            "N12°30'15\"E",
        )
        self.assertEqual(traverse.calls[0].distance, Distance(100))
        self.assertEqual(
            traverse.calls[1].bearing.to_quadrant_text(),
            "S0°17'48\"W",
        )
        self.assertEqual(traverse.calls[1].distance, Distance(34.77))

    def test_parser_uses_llm_for_calls_outside_conventional_structure(self) -> None:
        source_text = (
            'From the iron pin, go 100 feet on a bearing of '
            'North 12°30\'15" East; then proceed 75 feet on a bearing of '
            'South 10°00\'00" East '
            "to the road."
        )
        client = FakeChatClient(
            json.dumps(
                {
                    "point_of_beginning_desc": "From the iron pin.",
                    "calls": [
                        {
                            "call_type": "line",
                            "raw_text": (
                                'go 100 feet on a bearing of '
                                'North 12°30\'15" East'
                            ),
                            "bearing": {
                                "north_south": "North",
                                "degrees": 12,
                                "minutes": 30,
                                "seconds": 15,
                                "east_west": "East",
                            },
                            "distance": 100,
                            "radius": None,
                            "arc_length": None,
                            "chord_bearing": None,
                            "chord_distance": None,
                            "curve_direction": None,
                        },
                        {
                            "call_type": "line",
                            "raw_text": (
                                'proceed 75 feet on a bearing of '
                                'South 10°00\'00" East '
                                "to the road"
                            ),
                            "bearing": {
                                "north_south": "South",
                                "degrees": 10,
                                "minutes": 0,
                                "seconds": 0,
                                "east_west": "East",
                            },
                            "distance": 75,
                            "radius": None,
                            "arc_length": None,
                            "chord_bearing": None,
                            "chord_distance": None,
                            "curve_direction": None,
                        },
                    ],
                }
            )
        )

        traverse = LlmSurveyParser(client).parse(source_text)

        self.assertEqual(client.user_prompt.count("SOURCE TEXT:"), 1)
        self.assertIn(source_text, client.user_prompt)
        self.assertEqual(len(traverse.calls), 2)
        self.assertEqual(
            traverse.calls[0].bearing.to_quadrant_text(),
            "N12°30'15\"E",
        )
        self.assertEqual(traverse.calls[0].distance, Distance(100))
        self.assertEqual(
            traverse.calls[1].bearing.to_quadrant_text(),
            "S10°00'00\"E",
        )
        self.assertEqual(traverse.calls[1].distance, Distance(75))

    def test_ollama_client_sends_schema_and_reads_chat_content(self) -> None:
        response = BytesIO(b'{"message":{"content":"structured result"}}')
        schema = {"type": "object"}
        with patch(
            "drdeed.infrastructure.llm.ollama_client.urlopen",
            return_value=response,
        ) as request:
            content = OllamaChatClient().complete("system", "user", schema)

        self.assertEqual(content, "structured result")
        sent_request = request.call_args.args[0]
        self.assertEqual(sent_request.full_url, "http://localhost:11434/api/chat")
        self.assertEqual(json.loads(sent_request.data)["format"], schema)

    def test_parser_converts_schema_response_into_domain_models(self) -> None:
        client = FakeChatClient(
            json.dumps(
                {
                    "point_of_beginning_desc": "Beginning at the iron pin.",
                    "calls": [
                        {
                            "call_type": "line",
                            "raw_text": "thence N12°30'15\"E 100 feet",
                            "bearing": {
                                "north_south": "North",
                                "degrees": 12,
                                "minutes": 30,
                                "seconds": 15,
                                "east_west": "East",
                            },
                            "distance": 100,
                            "radius": None,
                            "arc_length": None,
                            "chord_bearing": None,
                            "chord_distance": None,
                            "curve_direction": None,
                        }
                    ],
                }
            )
        )

        traverse = LlmSurveyParser(client).parse("Beginning at the iron pin...")

        self.assertEqual(client.schema, TRAVERSE_JSON_SCHEMA)
        self.assertTrue(client.system_prompt)
        self.assertIn("Beginning at the iron pin...", client.user_prompt)
        self.assertEqual(
            client.schema["properties"]["calls"]["items"]["properties"]["bearing"],
            TRAVERSE_JSON_SCHEMA["properties"]["calls"]["items"]["properties"]["bearing"],
        )
        self.assertEqual(traverse.point_of_beginning_desc, "Beginning at the iron pin.")
        self.assertEqual(traverse.calls[0].bearing.to_quadrant_text(), "N12°30'15\"E")
        self.assertEqual(traverse.calls[0].distance, Distance(100))
        self.assertEqual(traverse.source_text, "Beginning at the iron pin...")

    def test_parser_preserves_curve_data_without_claiming_curve_support(self) -> None:
        client = FakeChatClient(
            json.dumps(
                {
                    "point_of_beginning_desc": "",
                    "calls": [
                        {
                            "call_type": "curve",
                            "raw_text": "along a curve to the right, radius 200 feet",
                            "bearing": None,
                            "distance": None,
                            "radius": 200,
                            "arc_length": None,
                            "chord_bearing": None,
                            "chord_distance": None,
                            "curve_direction": "clockwise",
                        }
                    ],
                }
            )
        )

        traverse = LlmSurveyParser(client).parse("Along a curve...")

        self.assertTrue(traverse.calls[0].is_curve())
        self.assertEqual(traverse.calls[0].call_type, CallTypeEnum.CURVE)
        self.assertEqual(traverse.calls[0].radius, Distance(200))
        with self.assertRaises(CurveCalculationNotSupportedError):
            StandardTraverseCalculator().compute_coordinates(
                traverse,
                Point2D(0, 0),
            )

    def test_parser_rejects_malformed_model_output(self) -> None:
        with self.assertRaisesRegex(ValueError, "invalid traverse JSON"):
            LlmSurveyParser(FakeChatClient("{not-json")).parse("source text")

    def test_parser_rejects_incomplete_structured_bearing(self) -> None:
        response = json.dumps(
            {
                "point_of_beginning_desc": "",
                "calls": [
                    {
                        "call_type": "line",
                        "raw_text": "South 88 degrees 49 minutes 50 seconds East, 645.35 feet",
                        "bearing": {
                            "north_south": "South",
                            "degrees": 88,
                            "minutes": 49,
                            "seconds": 50,
                            "east_west": None,
                        },
                        "distance": 645.35,
                        "radius": None,
                        "arc_length": None,
                        "chord_bearing": None,
                        "chord_distance": None,
                        "curve_direction": None,
                    }
                ],
            }
        )

        with self.assertRaisesRegex(ValueError, "east_west must be East or West"):
            LlmSurveyParser(FakeChatClient(response)).parse("source text")


class ApplicationWorkflowTests(unittest.TestCase):
    def test_closed_parse_is_checked_and_exported(self) -> None:
        parser = FakeParsingService(square_traverse())
        exporter = RecordingExporter()
        service = SurveyProcessingApplicationService(
            parser,
            StandardTraverseCalculator(),
            SurveyClosureValidator(),
            exporter,
        )

        result = service.process_survey_text(
            "source legal text",
            Point2D(0, 0),
            5000,
            CadExportConfig(Path("unused.dxf")),
        )

        self.assertTrue(result.closure_report.is_acceptable())
        self.assertEqual(result.output_file_path, "unused.dxf")
        self.assertTrue(exporter.exported)
        self.assertEqual(len(exporter.points), 5)
        self.assertIs(exporter.traverse, parser.first)
        self.assertEqual(result.correction_attempts, 0)

    def test_bad_closure_retries_once_and_prevents_export(self) -> None:
        open_traverse = TraverseModel(
            calls=(
                ParsedCall(
                    1,
                    Bearing.from_quadrant_text("N90°00'00\"E"),
                    Distance(100),
                ),
                ParsedCall(
                    2,
                    Bearing.from_quadrant_text("N0°00'00\"E"),
                    Distance(50),
                ),
            )
        )
        parser = FakeParsingService(open_traverse)
        exporter = RecordingExporter()
        service = SurveyProcessingApplicationService(
            parser,
            StandardTraverseCalculator(),
            SurveyClosureValidator(),
            exporter,
        )

        result = service.process_survey_text(
            "source legal text",
            Point2D(0, 0),
            5000,
            CadExportConfig(Path("unused.dxf")),
        )

        self.assertFalse(result.closure_report.is_acceptable())
        self.assertEqual(result.correction_attempts, 1)
        self.assertIsNotNone(parser.retry_feedback)
        self.assertIsNone(result.output_file_path)
        self.assertFalse(exporter.exported)

    def test_corrected_traverse_is_the_one_sent_to_dxf_export(self) -> None:
        open_traverse = TraverseModel(
            calls=(
                ParsedCall(
                    1,
                    Bearing.from_quadrant_text("N90°00'00\"E"),
                    Distance(100),
                ),
            )
        )
        corrected_traverse = square_traverse()
        parser = FakeParsingService(open_traverse, corrected_traverse)
        exporter = RecordingExporter()
        service = SurveyProcessingApplicationService(
            parser,
            StandardTraverseCalculator(),
            SurveyClosureValidator(),
            exporter,
        )

        result = service.process_survey_text(
            "source legal text",
            Point2D(0, 0),
            5000,
            CadExportConfig(Path("unused.dxf")),
        )

        self.assertTrue(result.closure_report.is_acceptable())
        self.assertEqual(result.correction_attempts, 1)
        self.assertIs(result.traverse, corrected_traverse)
        self.assertIs(exporter.traverse, corrected_traverse)
        self.assertTrue(exporter.exported)

    def test_dxf_drawer_refuses_curve_calls_instead_of_drawing_chords(self) -> None:
        curve = TraverseModel(
            calls=(
                ParsedCall(
                    sequence_index=1,
                    bearing=None,
                    distance=None,
                    raw_text="along a curve",
                    call_type=CallTypeEnum.CURVE,
                    radius=Distance(200),
                ),
            )
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            output_path = Path(temporary_directory) / "curve.dxf"
            with self.assertRaises(CurveCadExportNotSupportedError):
                CadExportService().generate_dxf_file(
                    [Point2D(0, 0), Point2D(10, 10)],
                    curve,
                    CadExportConfig(output_path),
                )
            self.assertFalse(output_path.exists())

    def test_cad_layer_prefix_is_used_and_dxf_can_be_reopened(self) -> None:
        traverse = square_traverse()
        points = StandardTraverseCalculator().compute_coordinates(
            traverse,
            Point2D(0, 0),
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            output_path = Path(temporary_directory) / "survey.dxf"
            result = CadExportService().generate_dxf_file(
                points,
                traverse,
                CadExportConfig(output_path, layer_prefix="BOUNDARY"),
            )
            document = ezdxf.readfile(result)

            self.assertIn("BOUNDARY_TRAVERSE", document.layers)
            self.assertIn("BOUNDARY_ANNOTATIONS", document.layers)
            self.assertEqual(len(list(document.modelspace().query("LWPOLYLINE"))), 1)


if __name__ == "__main__":
    unittest.main()
