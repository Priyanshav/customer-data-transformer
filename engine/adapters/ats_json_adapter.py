from __future__ import annotations
import json
import re
from ..models import RawSource, FieldHit

TIER = 3  # structured / official

def _norm(k: str) -> str:
    """Lowercase and strip all non-alphanumeric chars."""
    return re.sub(r"[^a-z0-9]", "", str(k).lower())

def _val(d: dict, *aliases: str):
    """Find the first value in d where the normalized key matches any alias."""
    if not isinstance(d, dict):
        return None
    for k, v in d.items():
        if _norm(k) in aliases and v not in (None, "", [], {}):
            return v
    return None

def _is_candidate(d: dict) -> bool:
    """Check if dict resembles a candidate (has name or contact fields)."""
    if not isinstance(d, dict):
        return False
    keys = {_norm(k) for k in d.keys()}
    names = {"name", "fullname", "candidatename", "applicantname", "firstname", "first", "lastname", "last"}
    contacts = {"email", "emailaddress", "mail", "phone", "phonenumber", "mobile", "cell"}
    return bool(keys & names) or bool(keys & contacts)

def _find_candidates(data):
    """Find candidates anywhere in the JSON. If a dict is a candidate, take it whole."""
    found = []
    if isinstance(data, dict):
        if _is_candidate(data):
            found.append(data)
        else:
            for v in data.values():
                found.extend(_find_candidates(v))
    elif isinstance(data, list):
        for item in data:
            found.extend(_find_candidates(item))
    return found

def extract(raw: RawSource):
    try:
        p = raw.payload
        data = json.loads(p) if isinstance(p, (str, bytes, bytearray)) else p
    except Exception:
        return []

    candidates = _find_candidates(data)
    if not candidates:
        return []

    records = []
    for obj in candidates:
        hits = []

        def add(field, value, method="direct"):
            if value not in (None, "", [], {}):
                hits.append(FieldHit(field=field, value=value, source=raw.type,
                                     method=method, tier=TIER))

        # ── Identity ──
        name = _val(obj, "name", "fullname", "candidatename", "applicantname", "displayname")
        if not name:
            first = _val(obj, "firstname", "first", "givenname") or ""
            last = _val(obj, "lastname", "last", "familyname", "surname") or ""
            if first or last:
                name = f"{first} {last}".strip()
        add("full_name", name)

        contact = _val(obj, "contact", "contactinfo", "contactinformation") or obj
        add("emails", _val(contact, "email", "emailaddress", "primaryemail", "mail"))
        add("phones", _val(contact, "phone", "phonenumber", "mobile", "cell", "telephone", "contactnumber"))
        
        # ── Headline / Location ──
        add("title", _val(obj, "title", "jobtitle", "position", "currentrole", "role", "designation"))
        add("company", _val(obj, "company", "employer", "organization", "currentcompany", "companyname"))

        loc = _val(obj, "location", "address", "residence")
        if isinstance(loc, dict):
            add("city", _val(loc, "city", "town", "locality"))
            add("country", _val(loc, "country", "countrycode", "nation"))
            add("region", _val(loc, "region", "state", "province"))
        elif isinstance(loc, str):
            add("location_raw", loc)
        elif not loc:
            # Maybe location fields are directly on the candidate object
            add("city", _val(obj, "city", "town", "locality"))
            add("country", _val(obj, "country", "countrycode", "nation"))
            add("region", _val(obj, "region", "state", "province"))

        # ── Skills ──
        skills = _val(obj, "skills", "skillset", "competencies", "tags", "technologies", "techstack")
        if isinstance(skills, str):
            skills = re.split(r"[;,|]", skills)
        if isinstance(skills, list):
            for s in skills:
                if isinstance(s, str):
                    add("skill", s.strip())
                elif isinstance(s, dict):
                    name = _val(s, "name", "skillname", "title")
                    if name:
                        add("skill", str(name).strip())

        # ── Experience ──
        exp_list = _val(obj, "experience", "workexperience", "workhistory", "positions", "jobs", "employment", "internship", "internships", "history") or []
        if isinstance(exp_list, list):
            for w in exp_list:
                if not isinstance(w, dict):
                    continue
                add("experience", {
                    "company": _val(w, "company", "organization", "employer", "companyname"),
                    "title": _val(w, "title", "position", "role", "jobtitle", "designation"),
                    "start": _val(w, "start", "startdate", "from", "fromdate"),
                    "end": _val(w, "end", "enddate", "to", "todate"),
                    "summary": _val(w, "summary", "description", "details", "responsibilities"),
                })

        # ── Education ──
        edu_list = _val(obj, "education", "schools", "degrees", "academics", "academicbackground", "university", "qualifications") or []
        if isinstance(edu_list, list):
            for e in edu_list:
                if not isinstance(e, dict):
                    continue
                score = _val(e, "gpa", "cgpa", "score", "percentage", "grade")
                add("education", {
                    "institution": _val(e, "school", "institution", "university", "college", "schoolname"),
                    "degree": _val(e, "degree", "qualification", "program"),
                    "field": _val(e, "field", "fieldofstudy", "major", "specialization", "course"),
                    "end_year": _val(e, "year", "endyear", "graduationyear", "passingyear"),
                    "score": score,
                })

        # ── Links ──
        links = _val(obj, "links", "socials", "urls", "profiles", "websites") or obj
        add("linkedin", _val(links, "linkedin", "linkedinurl"))
        add("github", _val(links, "github", "githuburl"))
        add("portfolio", _val(links, "portfolio", "portfoliourl", "website", "personalwebsite"))

        if hits:
            records.append(hits)
    return records
