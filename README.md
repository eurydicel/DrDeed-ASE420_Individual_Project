# DrDeed-ASE420_Individual_Project

## Purpose
Surveyors spend a lot of time drawing recorded deeds which adds unnecessary work to a time sensitive process.

## Solution
Utilize OCR and LLMs to interpret and create intelliCAD drawings.

## Implementation
The initial Python implementation is in the [Code](./Code) folder. It accepts
plain legal-description text for local Qwen3 parsing through Ollama, checks
straight-line traverse closure, and exports DXF files with ezdxf. OCR and curve
geometry are not implemented yet. See [Code/README.md](./Code/README.md) for
setup, architecture, and limitations.

https://nku.instructure.com/courses/91834/pages/individual-project-page-of-eurydice-lunnemann
