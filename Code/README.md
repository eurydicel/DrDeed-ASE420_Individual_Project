# Python implementation

The first implementation slice supports a manually specified straight-line
traverse, coordinate calculation, closure evaluation, and DXF export through
[ezdxf](https://ezdxf.readthedocs.io/). OCR, document parsing, curve calls, and
LLM integration are intentionally not included yet.

## Conventions

- Bearings are stored in quadrant degrees-minutes-seconds notation, such as
  `N12°30'15"E`. For coordinate calculations, they convert to azimuths clockwise
  from north (`0` north, `90` east, `180` south, `270` west). Bearings parsed
  from legal text retain their entered seconds; bearings calculated from closure
  vectors are rounded to the nearest whole second.
- Distances and coordinates are unit-agnostic. Use the same unit for every
  distance and for the point-of-beginning coordinates.
- Closure precision is reported as perimeter divided by closure error; a
  threshold of `5000` means a minimum precision of `1:5000`.
- DXF coordinates use easting as X and northing as Y. The export currently
  leaves DXF drawing units unspecified.

## Install and run tests

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m pip install -r Code\requirements.txt
$env:PYTHONPATH = "Code"
.\.venv\Scripts\python.exe -m unittest discover -s Code\tests -v
```

## Minimal example

```python
from pathlib import Path

from drdeed import (
    Bearing,
    CadExportConfig,
    CadExportService,
    Distance,
    ParsedCall,
    Point2D,
    StandardTraverseCalculator,
    TraverseModel,
)

traverse = TraverseModel(
    calls=(
        ParsedCall(1, Bearing.from_quadrant_text("N90°00'00\"E"), Distance(100)),
        ParsedCall(2, Bearing.from_quadrant_text("N0°00'00\"E"), Distance(50)),
        ParsedCall(3, Bearing.from_quadrant_text("N90°00'00\"W"), Distance(100)),
        ParsedCall(4, Bearing.from_quadrant_text("S0°00'00\"E"), Distance(50)),
    )
)
# Bearings can also be parsed directly with Bearing.from_quadrant_text("N12°30'15\"E").
pob = Point2D(easting=5000, northing=10000)
points = StandardTraverseCalculator().compute_coordinates(traverse, pob)

output = CadExportService().generate_dxf_file(
    points,
    traverse,
    CadExportConfig(Path("traverse.dxf")),
)
print(f"Created {output}")
```
