# Python implementation

This implementation provides an initial plain-text-to-DXF workflow:

1. Qwen3 parses pasted legal-description text into structured calls through a
   local Ollama server.
2. The application service converts calls to coordinates and evaluates closure.
3. If the requested closure threshold is missed, it asks the model for one
   source-grounded correction and checks again.
4. A DXF is exported only when the closure threshold is met.

This is a development prototype, not a survey certification or recordability
check. Confirm tolerance and interpretation rules with the project’s
surveying professionals.

## Run the application

Install [Ollama](https://ollama.com/download), then download the model:

```powershell
ollama pull qwen3:8b
```

From the repository root, install the Python dependency and launch the desktop
UI:

```powershell
.\.venv\Scripts\python.exe -m pip install -r Code\requirements.txt
.\.venv\Scripts\python.exe Code\run_app.py
```

Ollama must be running locally and the `qwen3:8b` model must be available.
This local setup does not require a hosted API key. The UI accepts plain text,
starting easting/northing coordinates, a minimum precision denominator, and an
output DXF path. Model calls run in a background thread so the interface remains
responsive while Ollama works.

## Architecture

- `drdeed/domain/models.py` contains domain models, including legal quadrant DMS
  bearings and curve-call fields.
- `drdeed/contracts/interfaces.py` defines Python `Protocol` service contracts
  matching the UML interfaces. OCR-related contracts exist, but OCR is not
  implemented in this text-only workflow.
- `drdeed/application/parsing.py` contains a source-grounded parser for complete
  word-quadrant DMS line calls, plus the Qwen3 parser, prompt builder, and
  one-retry feedback path. The conventional parser is preferred when every
  course has a complete bearing and one stated feet distance; unsupported,
  curve, or ambiguous text is sent to Qwen3 instead.
- `drdeed/infrastructure/llm/ollama_client.py` calls Ollama's local chat
  endpoint using a JSON schema for structured output.
- `drdeed/application/service.py` orchestrates parsing, coordinate calculation,
  closure validation, optional correction, and DXF export.
- `drdeed/geometry/calculator.py` calculates straight-line call coordinates;
  `drdeed/geometry/validation.py` computes closure error and precision ratio.
- `drdeed/infrastructure/cad/export.py` delegates DXF work through a CAD export
  service, drawer, layer manager, and annotation renderer.
- `drdeed/ui/window.py` provides a Tkinter desktop interface; `run_app.py`
  launches it.

The validation interface accepts a point of beginning because closure
calculation requires coordinates; the UML signature omits that parameter.
Curve call metadata can be parsed and retained, but curve coordinate and DXF
arc geometry are deliberately not approximated or exported yet. The model and
CAD delegation boundaries provide extension points for implementing and
testing curve math later.

## Conventions and limitations

- Bearings use quadrant degrees-minutes-seconds notation, such as
  `N12°30'15"E`. Parsed seconds are retained. Coordinate math converts bearings
  to floating-point azimuths; bearings calculated from closure vectors are
  rounded to the nearest whole second.
- Distances and coordinates are unit-agnostic. The caller must use one
  consistent unit for the traverse and point of beginning.
- Closure precision is perimeter divided by closure error. A threshold of
  `5000` means a requested minimum ratio of `1:5000`; the application does not
  assert that this threshold is appropriate for a particular jurisdiction or
  firm.
- The DXF exporter uses easting as X and northing as Y. Drawing units remain
  unspecified.
- The model is asked not to infer omitted values or force closure, but LLM
  output still requires human review against the source text.
- Structured Qwen3 bearings use separate compass-direction and numeric DMS
  fields rather than a single formatted string. This avoids losing the final
  East/West direction to quote escaping in model-generated bearing strings.

## Run tests

From the repository root:

```powershell
$env:PYTHONPATH = "Code"
.\.venv\Scripts\python.exe -m unittest discover -s Code\tests -v
```
