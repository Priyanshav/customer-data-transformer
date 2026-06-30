"""
Projection layer — reshapes a CanonicalRecord into the user-requested output schema.
"""

from models import CanonicalRecord, OutputConfig
from .normalize import normalize_date, normalize_phone, normalize_country, normalize_skill, derive_years_experience
from typing import Any, Dict


def resolve_path(record_dict: Dict[str, Any], path: str) -> Any:
    """Resolve a path like 'emails[0]' or 'skills[].name' against the canonical dict."""
    parts = path.split('.')
    current = record_dict

    for part in parts:
        if not current:
            return None

        if '[' in part and ']' in part:
            name, idx_str = part.split('[')
            idx_str = idx_str.rstrip(']')

            if name in current and isinstance(current[name], list):
                if idx_str == "":
                    arr = current[name]
                    if part == parts[-1]:
                        return arr
                    remaining_path = ".".join(parts[parts.index(part) + 1:])
                    return [resolve_path(item, remaining_path) for item in arr]
                else:
                    idx = int(idx_str)
                    if 0 <= idx < len(current[name]):
                        current = current[name][idx]
                    else:
                        return None
            else:
                return None
        else:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return None

    return current


def project(record: CanonicalRecord, config: OutputConfig) -> Dict[str, Any]:
    """Reshape the canonical record into the requested output via runtime config."""
    # WHY: derive years_experience from dated spans only if not explicitly provided
    derived_ye = derive_years_experience(record.experience)
    final_ye = record.years_experience if record.years_experience is not None else derived_ye

    # WHY: safe defaults for location and links so the schema is always stable
    loc_dict = vars(record.location) if record.location else None
    links_dict = vars(record.links) if record.links else {
        "linkedin": None, "github": None, "portfolio": None, "other": []
    }

    record_dict = {
        "candidate_id": record.candidate_id,
        "full_name": record.full_name,
        "primary_email": record.emails[0] if record.emails else None,
        "emails": record.emails,
        "phone": record.phones[0] if record.phones else None,
        "phones": record.phones,
        "location": loc_dict,
        "links": links_dict,
        "headline": record.headline,
        "years_experience": final_ye,
        "skills": [{"name": s.name, "confidence": s.confidence} for s in record.skills],
        "experience": [vars(e) for e in record.experience],
        "education": [vars(e) for e in record.education],
        "overall_confidence": record.overall_confidence,
        "provenance": [vars(p) for p in record.provenance],
    }

    output = {}

    for field in config.fields:
        source_path = field.from_path if field.from_path else field.path
        val = resolve_path(record_dict, source_path)

        # Apply normalization requested in config
        if field.normalize == "E164" and val:
            val = normalize_phone(str(val))
        elif field.normalize == "canonical" and val and isinstance(val, list):
            val = [normalize_skill(str(v)) for v in val]
        elif field.normalize == "ISO-3166" and val:
            val = normalize_country(str(val))
        elif field.normalize == "YYYY-MM" and val:
            val = normalize_date(str(val))

        output[field.path] = val

    # WHY: confidence and provenance are only emitted when the config asks for them
    if config.include_confidence:
        output["overall_confidence"] = record.overall_confidence
        output["provenance"] = record_dict["provenance"]

    return output
