from __future__ import annotations
import os
from .models import RawSource

# Extension -> (source type, group). PDF and TXT both route to the résumé adapter.
EXT_MAP = {
    ".csv": ("csv", "structured"),
    ".json": ("ats_json", "structured"),
    ".pdf": ("resume_pdf", "unstructured"),
    ".txt": ("resume_pdf", "unstructured"),
}

def _read(path: str, binary: bool):
    if binary:
        with open(path, "rb") as f:
            return f.read()
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()

def make_source(type_: str, group: str, path: str) -> RawSource:
    binary = type_ == "resume_pdf" and path.lower().endswith(".pdf")
    return RawSource(type=type_, group=group,
                     payload=_read(path, binary), origin=os.path.basename(path))

def load_sources_from_args(args) -> list[RawSource]:
    """Every source is OPTIONAL. Missing ones are simply skipped."""
    sources: list[RawSource] = []
    if getattr(args, "csv", None):
        sources.append(make_source("csv", "structured", args.csv))
    if getattr(args, "ats_json", None):
        sources.append(make_source("ats_json", "structured", args.ats_json))
    if getattr(args, "resume", None):
        sources.append(make_source("resume_pdf", "unstructured", args.resume))
    if getattr(args, "inputs", None):
        for name in sorted(os.listdir(args.inputs)):
            ext = os.path.splitext(name)[1].lower()
            if ext in EXT_MAP:
                t, g = EXT_MAP[ext]
                sources.append(make_source(t, g, os.path.join(args.inputs, name)))
    return sources
