# Multi-Source Candidate Data Transformer

Turns messy multi-source candidate data (recruiter CSV, ATS JSON, resume PDF/TXT)
into one clean, normalized, deduplicated profile per person -- with provenance,
confidence, and a runtime-configurable output shape.

## Requirements
- Python 3.10+
- CLI + engine + tests need NO third-party packages (standard library only).
- Web app needs:  pip install -r requirements.txt
- PDF parsing uses pypdf if installed; otherwise .txt resumes work out of the box.

## Quick start (CLI)

    # default canonical schema, auto-detect everything in samples/
    python main.py --inputs samples

    # explicit sources + custom output config, write to a file
    python main.py --csv samples/recruiter.csv \
                   --ats-json samples/ats.json \
                   --resume samples/resume.txt \
                   --config configs/custom_config.json \
                   --out output.json

Every source is optional -- pass any subset.

## Web app (localhost)

    pip install -r requirements.txt
    uvicorn web.app:app --reload --port 8000
    # open http://localhost:8000

Drag-drop your own files, tweak the config, view confidence badges, download JSON.
Everything is processed in memory; nothing is persisted.

## Tests

    python tests/test_pipeline.py     # zero-dependency runner
    # or, if you have pytest installed:
    pytest -q

## Assumptions / descoped
- Bare 10-digit phone numbers are treated as US/NANP (a documented default, not a per-record guess).
- Resume parsing assumes clean, text-based, single-column PDF/TXT; OCR/multi-column is out of scope.
- English-first; rule-based identity resolution (no fuzzy name-only merges).
- Stateless engine; no DB/persistence.
