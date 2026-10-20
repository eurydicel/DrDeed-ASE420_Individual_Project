"""DXF export using ezdxf."""

from collections.abc import Sequence
from dataclasses import dataclass
import math
from pathlib import Path

import ezdxf

from .models import Point2D, TraverseModel


@dataclass(frozen=True) #hold output settings for the DXF file
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


class CadExportService: #check the math and generate the actual DXF
    def generate_dxf_file( 
        self,
        points: Sequence[Point2D],
        traverse: TraverseModel,
        config: CadExportConfig,
    ) -> str:
        if len(points) != len(traverse.calls) + 1: #legals never close perfectly, make sure there is one more point than lines
            raise ValueError("Provide one more coordinate point than traverse calls.")

        output_path = Path(config.output_file_path) #where is this saved
        traverse_layer = f"{config.layer_prefix}_TRAVERSE" #linetype layer
        annotation_layer = f"{config.layer_prefix}_ANNOTATIONS" #text layer

        document = ezdxf.new("R2010") #type of file (readable by most CAD programs)
        document.layers.new(traverse_layer) #make the line layer
        if config.include_annotations:
            document.layers.new(annotation_layer) #make the text layer (if any)

        modelspace = document.modelspace() #modelspace is the area of a drawing where lines are drawn, not presented
        modelspace.add_lwpolyline( #create the polyline using all provided points and put it on the traverse layer
            [(point.easting, point.northing) for point in points],
            dxfattribs={"layer": traverse_layer},
        )

        if config.include_annotations: #if the user wants text
            for call, start, end in zip(traverse.calls, points, points[1:]):
                midpoint = ( #find the center of the line
                    (start.easting + end.easting) / 2.0,
                    (start.northing + end.northing) / 2.0,
                )
                label = ( #create text in format "sequence_index: quadrant bearing / distance"
                    f"{call.sequence_index}: "
                    f"{call.bearing.to_quadrant_text()} / "
                    f"{call.distance.value:g}"
                )
                modelspace.add_text( #add the calculated text to the modelspace
                    label,
                    dxfattribs={
                        "layer": annotation_layer,
                        "height": config.text_height,
                        "insert": midpoint,
                    },
                )

        output_path.parent.mkdir(parents=True, exist_ok=True) #make sure the output directory exists
        document.saveas(output_path) 
        return str(output_path) #output path as a string
