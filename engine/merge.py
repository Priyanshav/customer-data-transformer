from __future__ import annotations
import hashlib
import re
from .models import Record
from .normalize import (normalize_email, normalize_phone, normalize_country,
                        canonical_skill, normalize_date, current_year)

BASE_CONF = {3: 0.9, 2: 0.7, 1: 0.5}

def _by_field(records: list[Record]):
    d = {}
    for rec in records:
        for hit in rec:
            d.setdefault(hit.field, []).append(hit)
    return d

def _conf(hits, norm_factor=1.0):
    if not hits:
        return 0.0
    base = max(BASE_CONF.get(h.tier, 0.5) for h in hits)
    vals = {str(h.value).strip().lower() for h in hits if h.value is not None}
    if len(hits) > 1 and len(vals) == 1:
        agreement = 1.1          # independent agreement boosts confidence
    elif len(vals) > 1:
        agreement = 0.85         # conflict lowers it
    else:
        agreement = 1.0
    return round(min(1.0, base * agreement * norm_factor), 2)

def _pick(hits):
    return sorted(hits, key=lambda h: (h.tier, len(str(h.value)) if h.value else 0,
                                       str(h.value)), reverse=True)[0]

def _collect(hits, norm):
    out, seen, contrib = [], set(), []
    for h in sorted(hits, key=lambda x: -x.tier):
        raw = h.value if isinstance(h.value, list) else re.split(r"[;,/|]", str(h.value))
        for v in raw:
            nv = norm(v) if norm else (v.strip() if isinstance(v, str) else v)
            if nv and nv not in seen:
                seen.add(nv)
                out.append(nv)
                contrib.append(h)
    return out, contrib

def merge_cluster(records: list[Record]) -> dict:
    f = _by_field(records)
    rec, prov, fconf = {}, [], {}

    def addprov(field, hits, method=None):
        for h in hits:
            prov.append({"field": field, "source": h.source, "method": method or h.method})

    for sf in ("full_name", "headline"):
        if f.get(sf):
            h = _pick(f[sf])
            rec[sf] = h.value.strip() if isinstance(h.value, str) else h.value
            addprov(sf, [h])
            fconf[sf] = _conf(f[sf])
        else:
            rec[sf] = None

    emails, ec = _collect(f.get("emails", []) + f.get("email", []), normalize_email)
    rec["emails"] = emails
    if emails:
        addprov("emails", ec)
        fconf["emails"] = _conf(ec)

    phones, pc = _collect(f.get("phones", []) + f.get("phone", []), normalize_phone)
    rec["phones"] = phones
    if phones:
        addprov("phones", pc)
        fconf["phones"] = _conf(pc, 0.9)

    city = _pick(f["city"]).value if f.get("city") else None
    region = _pick(f["region"]).value if f.get("region") else None
    country = normalize_country(_pick(f["country"]).value) if f.get("country") else None
    if not (city or country) and f.get("location_raw"):
        parts = [p.strip() for p in re.split(r"[,/]", str(_pick(f["location_raw"]).value)) if p.strip()]
        if parts:
            city = city or parts[0]
            if len(parts) > 2:
                region = region or parts[1]
            if len(parts) > 1:
                country = country or normalize_country(parts[-1])
    rec["location"] = {"city": city, "region": region, "country": country}
    loc_srcs = f.get("city", []) + f.get("country", []) + f.get("location_raw", [])
    if city or region or country:
        addprov("location", loc_srcs)
        fconf["location"] = _conf(loc_srcs, 0.9)

    links = {"linkedin": None, "github": None, "portfolio": None, "other": []}
    for lk in ("linkedin", "github", "portfolio"):
        if f.get(lk):
            h = _pick(f[lk])
            links[lk] = str(h.value).strip()
            addprov("links." + lk, [h])
    rec["links"] = links

    skill_hits = f.get("skill", []) + f.get("skills_raw", [])
    smap = {}
    for h in skill_hits:
        raw = h.value if isinstance(h.value, list) else re.split(r"[;,/|]", str(h.value))
        for v in raw:
            name = canonical_skill(v)
            if not name:
                continue
            entry = smap.setdefault(name, {"sources": set()})
            entry["sources"].add(h.source)
    # No per-skill confidence: listing a skill on a résumé is not evidence of
    # proficiency, and the source trust tier is not meaningful at skill level.
    rec["skills"] = [{"name": k, "sources": sorted(v["sources"])}
                     for k, v in sorted(smap.items())]
    if rec["skills"]:
        addprov("skills", skill_hits, "parsed")

    exp = []
    for h in f.get("experience", []):
        v = h.value
        if isinstance(v, dict):
            exp.append({
                "company": v.get("company"),
                "title": v.get("title"),
                "start": normalize_date(v.get("start")),
                "end": normalize_date(v.get("end")),
                "summary": v.get("summary"),
            })
    if not exp and (f.get("company") or f.get("title")):
        exp.append({
            "company": _pick(f["company"]).value if f.get("company") else None,
            "title": _pick(f["title"]).value if f.get("title") else None,
            "start": None, "end": None, "summary": None,
        })
    # Dedup experience: same title (ignoring case) → keep the entry
    # that has more date info and company info. This avoids duplicates when one source has
    # dates (e.g. ATS) and another doesn't, or one has company and another doesn't.
    seen_exp: dict[str, dict] = {}
    for e in exp:
        key = (e["title"] or "").lower()
        existing = seen_exp.get(key)
        if existing is None:
            seen_exp[key] = e
        else:
            # Prefer the entry with more non-None date/company fields
            def score(entry):
                return (entry["start"] is not None) + (entry["end"] is not None) + (entry["company"] is not None)
            
            if score(e) > score(existing):
                seen_exp[key] = e
    dedup = list(seen_exp.values())
    rec["experience"] = dedup
    if dedup:
        addprov("experience", f.get("experience", []) or f.get("company", []), "parsed")

    # Dedup education: same institution+degree (ignoring case) → keep richer entry.
    seen_edu: dict[tuple, dict] = {}
    for h in f.get("education", []):
        v = h.value
        if isinstance(v, dict):
            entry = {"institution": v.get("institution"), "degree": v.get("degree"),
                     "field": v.get("field"), "end_year": v.get("end_year")}
            key = ((entry["institution"] or "").lower(), (entry["degree"] or "").lower())
            existing = seen_edu.get(key)
            if existing is None:
                seen_edu[key] = entry
            else:
                # Prefer the entry with more non-None fields
                new_filled = sum(1 for fv in entry.values() if fv is not None)
                old_filled = sum(1 for fv in existing.values() if fv is not None)
                if new_filled > old_filled:
                    seen_edu[key] = entry
    edu = list(seen_edu.values())
    rec["education"] = edu
    if edu:
        addprov("education", f.get("education", []), "parsed")

    starts = [int(e["start"][:4]) for e in dedup if e["start"]]
    ends = []
    for e in dedup:
        if e["end"]:
            ends.append(int(e["end"][:4]))
        elif e["start"]:
            ends.append(current_year())
    rec["years_experience"] = max(0, max(ends) - min(starts)) if starts and ends else None

    ident = emails[0] if emails else (phones[0] if phones else (rec.get("full_name") or "unknown"))
    rec["candidate_id"] = hashlib.sha1(ident.encode("utf-8")).hexdigest()[:16]

    rec["provenance"] = prov
    rec["field_confidence"] = fconf
    return rec
