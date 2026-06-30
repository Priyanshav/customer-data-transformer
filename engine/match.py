from __future__ import annotations
import re
from .models import Record
from .normalize import normalize_email, normalize_phone

def _keys(record: Record) -> set[str]:
    """Identity keys for a record. Name-only never produces a merge key."""
    keys, name, company, institution = set(), None, None, None
    for h in record:
        if h.field in ("emails", "email"):
            for v in (h.value if isinstance(h.value, list) else re.split(r"[;,]", str(h.value))):
                e = normalize_email(v)
                if e:
                    keys.add("e:" + e)
        elif h.field in ("phones", "phone"):
            for v in (h.value if isinstance(h.value, list) else re.split(r"[;,]", str(h.value))):
                p = normalize_phone(v)
                if p:
                    keys.add("p:" + p)
        elif h.field == "full_name":
            name = str(h.value).strip().lower()
        elif h.field == "company":
            company = str(h.value).strip().lower()
        elif h.field == "education" and isinstance(h.value, dict) and h.value.get("institution"):
            institution = str(h.value["institution"]).strip().lower()
    if name and company:
        keys.add("nc:" + name + "|" + company)
    if name and institution:
        keys.add("ni:" + name + "|" + institution)
    return keys

def cluster(records: list[Record]) -> list[list[Record]]:
    """Union-find clustering on shared identity keys."""
    parent = list(range(len(records)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    seen = {}
    for i, rec in enumerate(records):
        for k in _keys(rec):
            if k in seen:
                union(i, seen[k])
            else:
                seen[k] = i

    groups = {}
    for i in range(len(records)):
        groups.setdefault(find(i), []).append(records[i])
    return list(groups.values())
