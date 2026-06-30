from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, List

@dataclass
class RawSource:
    """A raw, untrusted input supplied at runtime."""
    type: str       # "csv" | "ats_json" | "resume_pdf"
    group: str      # "structured" | "unstructured"
    payload: Any    # str (text) or bytes (binary PDF)
    origin: str     # filename / label, for logging & provenance

@dataclass
class FieldHit:
    """One extracted (field, value) observation from one source."""
    field: str          # canonical-ish field name
    value: Any          # raw value (normalized later)
    source: str         # source type
    method: str = "direct"   # direct | parsed | inferred
    tier: int = 1       # trust tier (higher = more trusted)

# A "record" is the set of hits believed to describe ONE person within ONE source.
Record = List[FieldHit]
