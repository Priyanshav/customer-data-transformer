from __future__ import annotations
import re
from .normalize import normalize_phone, canonical_skill

class ValidationError(Exception):
    pass

def _resolve(value, segments):
    """Resolve a dotted path with [n] indexing and [] map-over-list support."""
    if not segments:
        return value
    seg, rest = segments[0], segments[1:]
    m = re.match(r"^([^\[\]]*)(\[(\d*)\])?$", seg)
    if not m:
        return None
    key, has_index, idx = m.group(1), m.group(2), m.group(3)
    if key:
        value = value.get(key) if isinstance(value, dict) else None
    if has_index is not None:
        if not isinstance(value, list):
            return None
        if idx == "":
            return [_resolve(v, rest) for v in value]
        i = int(idx)
        if i >= len(value):
            return None
        return _resolve(value[i], rest)
    return _resolve(value, rest)

def resolve_path(record, path):
    return _resolve(record, path.split("."))

def _apply_norm(value, norm):
    if norm is None or value is None:
        return value
    if isinstance(value, list):
        return [_apply_norm(v, norm) for v in value]
    if norm == "E164":
        return normalize_phone(value)
    if norm == "canonical":
        return canonical_skill(value)
    if norm == "lower":
        return str(value).lower()
    return value

def project(record, config):
    out = {}
    for fdef in config.get("fields", []):
        path = fdef.get("from", fdef["path"])
        out[fdef["path"]] = _apply_norm(resolve_path(record, path), fdef.get("normalize"))
    if config.get("include_confidence", True):
        out["_confidence"] = {"overall": record.get("overall_confidence"),
                              "fields": record.get("field_confidence", {})}
    if config.get("include_provenance", True):
        out["_provenance"] = record.get("provenance")
    return out

def _ok(value, t):
    if t is None:
        return True
    if t == "string":
        return isinstance(value, str)
    if t == "string[]":
        return isinstance(value, list) and all(isinstance(x, str) for x in value)
    if t == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if t == "boolean":
        return isinstance(value, bool)
    if t == "object":
        return isinstance(value, dict)
    return True

def validate(projected, config):
    on_missing = config.get("on_missing", "null")
    result = dict(projected)
    for fdef in config.get("fields", []):
        path = fdef["path"]
        val = result.get(path)
        missing = val is None or (isinstance(val, (list, str)) and len(val) == 0)
        if missing:
            if fdef.get("required") and on_missing == "error":
                raise ValidationError(f"required field '{path}' is missing")
            if on_missing == "omit":
                result.pop(path, None)
            else:
                result[path] = None
            continue
        if not _ok(val, fdef.get("type")):
            result[path] = None  # type mismatch -> degrade to null, never invent
    return result
