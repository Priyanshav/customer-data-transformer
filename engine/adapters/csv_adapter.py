from __future__ import annotations
import csv
import io
from ..models import RawSource, FieldHit

HEADER_ALIASES = {
    "name": "full_name", "full name": "full_name", "candidate": "full_name",
    "candidate name": "full_name",
    "email": "emails", "email address": "emails", "e-mail": "emails",
    "phone": "phones", "phone number": "phones", "mobile": "phones", "tel": "phones",
    "company": "company", "current_company": "company", "current company": "company",
    "employer": "company",
    "title": "title", "job title": "title", "role": "title", "current title": "title",
    "location": "location_raw", "city": "city", "country": "country", "state": "region",
    "linkedin": "linkedin", "github": "github", "portfolio": "portfolio",
    "skills": "skills_raw",
}

TIER = 3  # structured / official

def extract(raw: RawSource):
    """Return a list of records (each record = list[FieldHit]). Garbage -> []."""
    try:
        text = raw.payload if isinstance(raw.payload, str) else raw.payload.decode("utf-8", "replace")
        reader = csv.DictReader(io.StringIO(text))
        records = []
        for row in reader:
            hits = []
            for col, val in row.items():
                if col is None or val is None:
                    continue
                key = HEADER_ALIASES.get(col.strip().lower())
                val = str(val).strip()
                if not key or not val:
                    continue
                hits.append(FieldHit(field=key, value=val, source=raw.type,
                                     method="direct", tier=TIER))
            if hits:
                records.append(hits)
        return records
    except Exception:
        return []  # malformed CSV: skip, never crash the run
