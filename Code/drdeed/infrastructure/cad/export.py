"""DXF export services with separate layer, drawing, and annotation roles."""

from collections.abc import Sequence
from pathlib import Path

import ezdxf
from ezdxf.document import Drawing
from ezdxf.layouts import Modelspace

from ...contracts.interfaces import (
    ICadAnnotationRenderer,
    ICadDrawer,
    ICadExportService,
    ICadLayerManager,
)
from ...domain.models import (
    CadExportConfig,
    CallTypeEnum,
    ParsedCall,
    Point2D,
    TraverseModel,
)


class CurveCadExportNotSupportedError(NotImplementedError):
    """Raised until curve geometry can be exported without approximating it."""


class StandardCadLayerManager(ICadLayerManager):
    def initialize_standard_layers(
        self,
        document: Drawing,
        layer_prefix: str,
    ) -> None:
        # Create the two standard layers only if they are not already present.
        for name in (
            self.get_layer_name("traverse", layer_prefix),
            self.get_layer_name("annotations", layer_prefix),
        ):
            if name not in document.layers:
                document.layers.new(name)

    def get_layer_name(self, purpose: str, layer_prefix: str) -> str:
        # Keep layer naming in one place so it can be extended for new CAD purposes.
        layer_names = {
            "traverse": f"{layer_prefix}_TRAVERSE",
            "annotations": f"{layer_prefix}_ANNOTATIONS",
        }
        try:
            return layer_names[purpose]
        except KeyError as error:
            raise ValueError(f"Unknown CAD layer purpose: {purpose!r}.") from error


class SurveyAnnotationRenderer(ICadAnnotationRenderer):
    def __init__(self, layer_manager: ICadLayerManager) -> None:
        self._layer_manager = layer_manager

    def annotate_call(
        self,
        modelspace: Modelspace,
        start_point: Point2D,
        end_point: Point2D,
        call: ParsedCall,
        config: CadExportConfig,
    ) -> None:
        midpoint = (
            (start_point.easting + end_point.easting) / 2.0,
            (start_point.northing + end_point.northing) / 2.0,
        )
        if call.call_type is CallTypeEnum.LINE:
            if call.bearing is None or call.distance is None:
                raise ValueError(
                    f"Line call {call.sequence_index} is missing bearing or distance."
                )
            label = (
                f"{call.sequence_index}: {call.bearing.to_quadrant_text()} / "
                f"{call.distance.value:g}"
            )
        else:
            details = []
            if call.radius is not None:
                details.append(f"R {call.radius.value:g}")
            if call.arc_length is not None:
                details.append(f"L {call.arc_length.value:g}")
            if call.chord_bearing is not None:
                details.append(f"CHB {call.chord_bearing.to_quadrant_text()}")
            if call.chord_distance is not None:
                details.append(f"CHD {call.chord_distance.value:g}")
            if call.curve_direction is not None:
                details.append(f"TURN {call.curve_direction.value}")
            label = f"{call.sequence_index}: CURVE ({', '.join(details)})"

        modelspace.add_text(
            label,
            dxfattribs={
                "layer": self._layer_manager.get_layer_name(
                    "annotations",
                    config.layer_prefix,
                ),
                "height": config.text_height,
                "insert": midpoint,
            },
        )


class EzdxfCadDrawer(ICadDrawer):
    def __init__(
        self,
        layer_manager: ICadLayerManager,
        annotation_renderer: ICadAnnotationRenderer,
    ) -> None:
        self._layer_manager = layer_manager
        self._annotation_renderer = annotation_renderer

    def draw_traverse(
        self,
        document: Drawing,
        points: Sequence[Point2D],
        traverse: TraverseModel,
        config: CadExportConfig,
    ) -> None:
        if any(call.is_curve() for call in traverse.calls):
            raise CurveCadExportNotSupportedError(
                "Curve calls are retained in the parsed model, but the current "
                "DXF drawer cannot yet represent their arc geometry."
            )
        if len(points) != len(traverse.calls) + 1:
            raise ValueError("Provide one more coordinate point than traverse calls.")

        self._layer_manager.initialize_standard_layers(
            document,
            config.layer_prefix,
        )
        modelspace = document.modelspace()
        # Use one lightweight polyline for the ordered straight-line vertices.
        modelspace.add_lwpolyline(
            [(point.easting, point.northing) for point in points],
            dxfattribs={
                "layer": self._layer_manager.get_layer_name(
                    "traverse",
                    config.layer_prefix,
                ),
            },
        )

        if config.include_annotations:
            # Pair each call with its start and end points for its label.
            for call, start_point, end_point in zip(
                traverse.calls,
                points[:-1],
                points[1:],
                strict=True,
            ):
                self._annotation_renderer.annotate_call(
                    modelspace,
                    start_point,
                    end_point,
                    call,
                    config,
                )


class CadExportService(ICadExportService):
    def __init__(self, drawer: ICadDrawer | None = None) -> None:
        if drawer is None:
            layer_manager = StandardCadLayerManager()
            annotation_renderer = SurveyAnnotationRenderer(layer_manager)
            drawer = EzdxfCadDrawer(layer_manager, annotation_renderer)
        self._drawer = drawer

    def generate_dxf_file(
        self,
        points: Sequence[Point2D],
        traverse: TraverseModel,
        config: CadExportConfig,
    ) -> str:
        output_path = Path(config.output_file_path)
        document = ezdxf.new("R2010")
        # Delegate geometry and annotations; this service owns file creation.
        self._drawer.draw_traverse(document, points, traverse, config)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        document.saveas(output_path)
        return str(output_path)
