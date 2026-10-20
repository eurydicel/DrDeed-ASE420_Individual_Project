from pathlib import Path
import tempfile
import unittest
from decimal import Decimal

import ezdxf

from drdeed import (
    Bearing,
    CadExportConfig,
    CadExportService,
    Distance,
    ParsedCall,
    Point2D,
    StandardTraverseCalculator,
    SurveyClosureValidator,
    TraverseModel,
)


def square_traverse() -> TraverseModel:
    return TraverseModel(
        calls=(
            ParsedCall(1, Bearing.from_quadrant_text("N90°00'00\"E"), Distance(100)),
            ParsedCall(2, Bearing.from_quadrant_text("N0°00'00\"E"), Distance(50)),
            ParsedCall(3, Bearing.from_quadrant_text("N90°00'00\"W"), Distance(100)),
            ParsedCall(4, Bearing.from_quadrant_text("S0°00'00\"E"), Distance(50)),
        )
    )


class TraverseGeometryTests(unittest.TestCase):
    def test_parses_and_formats_quadrant_dms_bearing(self) -> None:
        bearing = Bearing.from_quadrant_text("N12°30'15\"E")

        self.assertEqual(bearing.quadrant, "NE")
        self.assertEqual(bearing.degrees, 12)
        self.assertEqual(bearing.minutes, 30)
        self.assertEqual(bearing.seconds, Decimal("15"))
        self.assertEqual(bearing.to_quadrant_text(), "N12°30'15\"E")
        self.assertAlmostEqual(bearing.azimuth_degrees, 12.5041666667)

    def test_converts_each_quadrant_to_clockwise_azimuth(self) -> None:
        cases = (
            ("N12°30'15\"E", 12.5041666667),
            ("S12°30'15\"E", 167.4958333333),
            ("S12°30'15\"W", 192.5041666667),
            ("N12°30'15\"W", 347.4958333333),
        )
        for text, expected_azimuth in cases:
            with self.subTest(text=text):
                bearing = Bearing.from_quadrant_text(text)
                self.assertAlmostEqual(bearing.azimuth_degrees, expected_azimuth)

    def test_rounds_azimuth_derived_bearings_to_nearest_second(self) -> None:
        below_half_second = Bearing.from_azimuth_degrees(12 + 30 / 60 + 15.4 / 3600)
        above_half_second = Bearing.from_azimuth_degrees(12 + 30 / 60 + 15.6 / 3600)

        self.assertEqual(below_half_second.to_quadrant_text(), "N12°30'15\"E")
        self.assertEqual(above_half_second.to_quadrant_text(), "N12°30'16\"E")

    def test_rejects_invalid_quadrant_dms_bearing(self) -> None:
        for text in ("E12°30'15\"N", "N91°00'00\"E", "N12°60'00\"E", "N12°30'60\"E"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                Bearing.from_quadrant_text(text)

    def test_calculates_vertices_from_easting_northing_azimuths(self) -> None:
        points = StandardTraverseCalculator().compute_coordinates(
            square_traverse(),
            Point2D(5000, 10000),
        )

        self.assertEqual(len(points), 5)
        self.assertAlmostEqual(points[1].easting, 5100)
        self.assertAlmostEqual(points[1].northing, 10000)
        self.assertAlmostEqual(points[-1].easting, 5000)
        self.assertAlmostEqual(points[-1].northing, 10000)

    def test_reports_acceptable_closure_for_square(self) -> None:
        report = SurveyClosureValidator().evaluate_closure(
            square_traverse(),
            Point2D(0, 0),
            min_precision_threshold=5000,
        )

        self.assertTrue(report.is_acceptable())
        self.assertLess(report.closure_error_distance, 1e-10)
        self.assertGreater(report.precision_ratio, 5000)
        self.assertAlmostEqual(report.total_perimeter, 300)

    def test_reports_low_precision_for_open_traverse(self) -> None:
        open_traverse = TraverseModel(
            calls=(
                ParsedCall(1, Bearing.from_quadrant_text("N90°00'00\"E"), Distance(100)),
                ParsedCall(2, Bearing.from_quadrant_text("N0°00'00\"E"), Distance(50)),
            )
        )

        report = SurveyClosureValidator().evaluate_closure(
            open_traverse,
            Point2D(0, 0),
            min_precision_threshold=5000,
        )

        self.assertFalse(report.is_acceptable())
        self.assertLess(report.precision_ratio, 5000)
        self.assertIsNotNone(report.closure_error_bearing)


class CadExportTests(unittest.TestCase):
    def test_exports_polyline_and_call_annotations_to_dxf(self) -> None:
        traverse = square_traverse()
        points = StandardTraverseCalculator().compute_coordinates(
            traverse,
            Point2D(0, 0),
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            output_path = Path(temporary_directory) / "nested" / "traverse.dxf"
            result = CadExportService().generate_dxf_file(
                points,
                traverse,
                CadExportConfig(output_path),
            )

            document = ezdxf.readfile(result)
            modelspace = document.modelspace()
            self.assertEqual(len(list(modelspace.query("LWPOLYLINE"))), 1)
            annotations = list(modelspace.query("TEXT"))
            self.assertEqual(len(annotations), 4)
            self.assertEqual(annotations[0].dxf.text, "1: N90°00'00\"E / 100")


if __name__ == "__main__":
    unittest.main()
