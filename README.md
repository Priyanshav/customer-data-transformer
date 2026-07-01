# Multi-Source Candidate Data Transformer

**Live Demo URL:** https://customer-data-transformer.onrender.com/

Turns messy multi-source candidate data (recruiter CSV, ATS JSON, resume PDF/TXT) into one clean, normalized, deduplicated profile per person -- with provenance, confidence, and a runtime-configurable output shape.

## Requirements
- Python 3.10+
- The core engine, CLI, and test suite require **zero third-party dependencies** (standard library only) for portability.
- The optional Web UI requires: `pip install -r requirements.txt` (FastAPI/Uvicorn).
- PDF parsing uses `pypdf` if installed; otherwise, `.txt` resumes work out of the box using our custom flexible text parsers.

## Quick start (CLI)

```bash
# default canonical schema, auto-detect everything in samples/
python main.py --inputs samples

# explicit sources + custom output config, write to a file
python main.py --csv samples/recruiter.csv \
               --ats-json samples/ats.json \
               --resume samples/resume.txt \
               --config configs/custom_config.json \
               --out output.json
```
*Note: Every source is optional -- you can pass any subset.*

## Web App / Visual Config Builder

Try the live application instantly at **[https://customer-data-transformer.onrender.com/](https://customer-data-transformer.onrender.com/)**, or run it locally:

```bash
pip install -r requirements.txt
uvicorn web.app:app --reload --port 8000
```
Open `http://localhost:8000` in your browser. 
You can drag-drop files, visually build a custom JSON output config (to test the Required Twist), view confidence scoring, and export the deduplicated JSON directly. Everything is processed instantly in memory; nothing is persisted to disk.

## Tests

```bash
python tests/test_pipeline.py     # zero-dependency runner
# or, if you have pytest installed:
pytest -q
```
*Tests verify robust degradation (garbage sources do not crash the run), merging across multiple files, and strict schema projections.*

## Architecture & Design Decisions
- **Flexible Ingestion**: The `ats_json_adapter` recursively searches arbitrary JSON trees for candidate-like structures, bypassing brittle schema lock-in. The `resume_pdf_adapter` uses date-anchored upward scanning rather than strict regex to reliably extract Experience across varying resume formats.
- **Merge & Confidence**: Deduplication clusters candidates by exact email, E.164 phone, or exact full name. Conflicts are resolved via a deterministic scoring heuristic (preferring sources that provide the most granular start/end dates for experience, for instance). 
- **Configurable Projection Layer**: The internal canonical record is strictly separated from the output representation. The `engine/project.py` layer filters, reshapes, conditionally normalizes (e.g. `canonical` skills or `E164` phones), and applies missing-value behaviors (`omit`/`null`/`error`) strictly at runtime based on the config payload.

## Assumptions / Descoped
- Bare 10-digit phone numbers are treated as US/NANP (a documented default, not a per-record guess).
- Resume parsing assumes clean, text-based, single-column PDF/TXT; OCR/multi-column is out of scope.
- English-first; rule-based identity resolution (no fuzzy name-only merges).
- Stateless engine; no DB/persistence.
