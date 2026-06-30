"""
Merge layer — resolves conflicts across sources into one CanonicalRecord.

Contract: match by email > phone > name; trust tier structured > prose;
union list fields; populate provenance.
"""

from typing import List, Dict, Any, Tuple
from models import FieldHit, CanonicalRecord, Location, Links, Skill, Experience, Provenance

# WHY: structured/official sources (ATS, CSV) are more trustworthy than
# free-text résumé parsing.
TRUST_TIER = {
    "ats": 3,
    "csv": 3,
    "linkedin": 2,
    "github": 2,
    "resume": 1,
    "recruiter_notes": 1,
}


def get_tier(source: str) -> int:
    return TRUST_TIER.get(source, 0)


def resolve_scalar(hits: List[FieldHit]) -> Tuple[FieldHit, List[FieldHit]]:
    """Pick a winner for a scalar field based on trust tier.

    WHY tie-break by last-in-list: we assume later sources are more recent.
    """
    if not hits:
        return None, []
    sorted_hits = sorted(hits, key=lambda h: get_tier(h.source))
    return sorted_hits[-1], sorted_hits


def merge(candidate_id: str, hits: List[FieldHit]) -> Tuple[CanonicalRecord, Dict[str, List[FieldHit]]]:
    """Resolve conflicts into one canonical record per person."""
    # ── group hits by field ──
    field_groups: Dict[str, List[FieldHit]] = {}
    for hit in hits:
        field_groups.setdefault(hit.field, []).append(hit)

    record = CanonicalRecord(candidate_id=candidate_id, full_name="")
    used_hits_by_field: Dict[str, List[FieldHit]] = {}

    # ── full_name ──
    fn_hits = field_groups.get("first_name", [])
    ln_hits = field_groups.get("last_name", [])
    fn_winner, _ = resolve_scalar(fn_hits)
    ln_winner, _ = resolve_scalar(ln_hits)

    if fn_winner or ln_winner:
        fn = fn_winner.value if fn_winner else ""
        ln = ln_winner.value if ln_winner else ""
        record.full_name = f"{fn} {ln}".strip()
        if fn_winner:
            used_hits_by_field["first_name"] = fn_hits
        if ln_winner:
            used_hits_by_field["last_name"] = ln_hits

    # ── emails (union, deduped, lowered) ──
    email_hits = field_groups.get("email", [])
    seen_emails = set()
    for h in email_hits:
        val = h.value.lower().strip()
        if val not in seen_emails:
            seen_emails.add(val)
            record.emails.append(val)
    used_hits_by_field["email"] = email_hits

    # ── phones (union, deduped) ──
    phone_hits = field_groups.get("phone", [])
    seen_phones = set()
    for h in phone_hits:
        if h.value and h.value not in seen_phones:
            seen_phones.add(h.value)
            record.phones.append(h.value)
    used_hits_by_field["phone"] = phone_hits

    # ── headline ──
    hl_hits = field_groups.get("headline", [])
    hl_winner, _ = resolve_scalar(hl_hits)
    if hl_winner:
        record.headline = hl_winner.value
        used_hits_by_field["headline"] = hl_hits

    # ── location ──
    city_win, _ = resolve_scalar(field_groups.get("loc_city", []))
    region_win, _ = resolve_scalar(field_groups.get("loc_region", []))
    country_win, _ = resolve_scalar(field_groups.get("loc_country", []))
    loc_winner, _ = resolve_scalar(field_groups.get("location", []))

    if city_win or region_win or country_win or loc_winner:
        if city_win or region_win or country_win:
            record.location = Location(
                city=city_win.value if city_win else None,
                region=region_win.value if region_win else None,
                country=country_win.value if country_win else None,
            )
            if city_win: used_hits_by_field["loc_city"] = [city_win]
            if region_win: used_hits_by_field["loc_region"] = [region_win]
            if country_win: used_hits_by_field["loc_country"] = [country_win]
        else:
            record.location = Location(country=loc_winner.value)
            used_hits_by_field["location"] = [loc_winner]

    # ── links ──
    link_in_win, _ = resolve_scalar(field_groups.get("link_linkedin", []))
    link_gh_win, _ = resolve_scalar(field_groups.get("link_github", []))
    link_pf_win, _ = resolve_scalar(field_groups.get("link_portfolio", []))

    other_hits = field_groups.get("link_other", [])
    other_urls = list(dict.fromkeys(h.value for h in other_hits))  # WHY: dedup preserving order

    # WHY: always populate a Links object so the schema is stable
    record.links = Links(
        linkedin=link_in_win.value if link_in_win else None,
        github=link_gh_win.value if link_gh_win else None,
        portfolio=link_pf_win.value if link_pf_win else None,
        other=other_urls,
    )
    if link_in_win: used_hits_by_field["link_linkedin"] = [link_in_win]
    if link_gh_win: used_hits_by_field["link_github"] = [link_gh_win]
    if link_pf_win: used_hits_by_field["link_portfolio"] = [link_pf_win]
    if other_hits: used_hits_by_field["link_other"] = other_hits

    # ── skills (union) ──
    skill_hits = field_groups.get("skill", [])
    skills_map: Dict[str, Skill] = {}
    for h in skill_hits:
        s_name = h.value
        if s_name not in skills_map:
            skills_map[s_name] = Skill(name=s_name, confidence=1.0, sources=[h.source])
        else:
            if h.source not in skills_map[s_name].sources:
                skills_map[s_name].sources.append(h.source)
    record.skills = list(skills_map.values())
    used_hits_by_field["skill"] = skill_hits

    # ── years_experience (explicit free-text) ──
    ye_hits = field_groups.get("years_experience", [])
    ye_winner, _ = resolve_scalar(ye_hits)
    if ye_winner:
        record.years_experience = float(ye_winner.value)
        used_hits_by_field["years_experience"] = ye_hits

    # ── experience ──
    # WHY: pair company/title/start/end from the same source by order of appearance.
    jobs_by_source: Dict[str, list] = {}
    for f in ("company", "job_title", "start_date", "end_date"):
        source_index: Dict[str, int] = {}
        for h in field_groups.get(f, []):
            jobs_by_source.setdefault(h.source, [])
            source_index.setdefault(h.source, 0)

            idx = source_index[h.source]
            while len(jobs_by_source[h.source]) <= idx:
                jobs_by_source[h.source].append(
                    {"company": None, "job_title": None, "start_date": None, "end_date": None, "hits": {}}
                )

            jobs_by_source[h.source][idx][f] = h.value
            jobs_by_source[h.source][idx]["hits"][f] = h
            source_index[h.source] += 1

            used_hits_by_field.setdefault(f, [])

    # WHY: group jobs across sources by first word of company name for dedup
    grouped_jobs: Dict[str, dict] = {}
    for src, jobs in jobs_by_source.items():
        for job in jobs:
            comp = job["company"] or ""
            key = comp.lower().split()[0] if comp else "unknown"
            if key not in grouped_jobs:
                grouped_jobs[key] = {"company": [], "job_title": [], "start_date": [], "end_date": []}
            for f in ("company", "job_title", "start_date", "end_date"):
                if job["hits"].get(f):
                    grouped_jobs[key][f].append(job["hits"][f])

    for key, field_hits in grouped_jobs.items():
        c_win, _ = resolve_scalar(field_hits["company"])
        t_win, _ = resolve_scalar(field_hits["job_title"])
        s_win, _ = resolve_scalar(field_hits["start_date"])
        e_win, _ = resolve_scalar(field_hits["end_date"])

        if c_win or t_win:
            record.experience.append(Experience(
                company=c_win.value if c_win else "",
                title=t_win.value if t_win else "",
                start=s_win.value if s_win else None,
                end=e_win.value if e_win else None,
            ))
            if c_win: used_hits_by_field["company"].append(c_win)
            if t_win: used_hits_by_field["job_title"].append(t_win)
            if s_win: used_hits_by_field["start_date"].append(s_win)
            if e_win: used_hits_by_field["end_date"].append(e_win)

    # ── education ──
    from models import Education
    edu_by_source: Dict[str, list] = {}
    for f in ("edu_institution", "edu_degree", "edu_end_year"):
        source_index: Dict[str, int] = {}
        for h in field_groups.get(f, []):
            edu_by_source.setdefault(h.source, [])
            source_index.setdefault(h.source, 0)

            idx = source_index[h.source]
            while len(edu_by_source[h.source]) <= idx:
                edu_by_source[h.source].append(
                    {"edu_institution": None, "edu_degree": None, "edu_end_year": None, "hits": {}}
                )

            edu_by_source[h.source][idx][f] = h.value
            edu_by_source[h.source][idx]["hits"][f] = h
            source_index[h.source] += 1

            used_hits_by_field.setdefault(f, [])

    grouped_edu: Dict[str, dict] = {}
    for src, edus in edu_by_source.items():
        for edu in edus:
            inst = edu["edu_institution"] or ""
            key = inst.lower().split()[0] if inst else "unknown"
            if key not in grouped_edu:
                grouped_edu[key] = {"edu_institution": [], "edu_degree": [], "edu_end_year": []}
            for f in ("edu_institution", "edu_degree", "edu_end_year"):
                if edu["hits"].get(f):
                    grouped_edu[key][f].append(edu["hits"][f])

    for key, field_hits in grouped_edu.items():
        i_win, _ = resolve_scalar(field_hits["edu_institution"])
        d_win, _ = resolve_scalar(field_hits["edu_degree"])
        e_win, _ = resolve_scalar(field_hits["edu_end_year"])

        if i_win or d_win:
            record.education.append(Education(
                institution=i_win.value if i_win else "",
                degree=d_win.value if d_win else "",
                field_of_study="",
                end_year=e_win.value if e_win else None,
            ))
            if i_win: used_hits_by_field["edu_institution"].append(i_win)
            if d_win: used_hits_by_field["edu_degree"].append(d_win)
            if e_win: used_hits_by_field["edu_end_year"].append(e_win)

    return record, used_hits_by_field
