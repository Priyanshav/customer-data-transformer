from __future__ import annotations

REQUIRED = ["full_name", "emails", "phones"]

def score(rec: dict) -> dict:
    """overall_confidence = weighted mean of present required-field confidences."""
    fconf = rec.get("field_confidence", {})
    present = [fconf.get(k, 0.0) for k in REQUIRED if rec.get(k)]
    rec["overall_confidence"] = round(sum(present) / len(present), 2) if present else 0.0
    return rec
