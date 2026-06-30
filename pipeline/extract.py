"""
Extraction layer — converts raw sources into flat FieldHit lists.

Design contract:
  • Each field group (contact, links, headline, skills, experience, education)
    is extracted by its OWN function on its OWN slice of lines.
  • One extractor crashing or changing can NEVER blank out another.
  • No résumé-specific logic; everything is driven by the synonym map
    in constants.py and the regexes in this file.
"""

from typing import List, Dict, Any, Optional, Tuple
from models import RawSource, FieldHit
import pdfplumber
import re

from pipeline.constants import SECTION_MAPPING

# ---------------------------------------------------------------------------
# Section detection
# ---------------------------------------------------------------------------

def is_section_header(line: str) -> Optional[str]:
    """Return canonical section name if *line* is a section header, else None.

    WHY a header must be short + match a known synonym OR be all-caps:
    this avoids treating normal prose (e.g. "B. Tech in CSE-AI") as headers.
    """
    orig = line.strip()
    if not orig:
        return None

    clean = orig
    if clean.endswith(":"):
        clean = clean[:-1].strip()

    # WHY: real section headers are short (≤5 words)
    if len(clean.split()) > 5:
        return None

    lower = clean.lower()
    if lower in SECTION_MAPPING:
        return SECTION_MAPPING[lower]

    # WHY: all-caps short lines are likely unknown section headers even if
    # they aren't in our synonym map — keep them aside so they don't pollute
    # experience/education. But ONLY if they contain no digits (a line like
    # "JULY 2024 - AUGUST 2024" is a date, not a section header).
    if clean.isupper() and any(c.isalpha() for c in clean) and not any(c.isdigit() for c in clean):
        return "unknown"

    return None


def partition_sections(lines: List[str]) -> Dict[str, List[str]]:
    """Split *lines* into {canonical_section: [content_lines]}.

    WHY we preserve blank lines: the experience/education extractors need
    adjacency (previous line) context, and skipping blanks breaks that.
    """
    sections: Dict[str, List[str]] = {"header": []}
    current = "header"
    for line in lines:
        header = is_section_header(line)
        if header:
            current = header
            if current not in sections:
                sections[current] = []
            # WHY: the header line itself is NOT appended — it's metadata,
            # not content. Prevents "EDUCATION" from becoming an institution.
        else:
            sections[current].append(line)
    return sections

# ---------------------------------------------------------------------------
# Date range parser (shared by experience + education)
# ---------------------------------------------------------------------------

def extract_date_range(line: str) -> Optional[Tuple[str, Optional[str], int]]:
    """Find a date or date range in *line*.

    Returns (start_str, end_str_or_None, char_index_of_match_start).
    WHY we require a month for single dates: bare "2000" in "team of 2000"
    must NOT be parsed as a date. Ranges like "2018 – 2023" are fine because
    two adjacent year-like tokens separated by a dash constitute unambiguous
    date context.
    """
    month_pattern = r'(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*'
    strict_date = r'(?:' + month_pattern + r'\s+(?:19|20)\d{2}|\d{1,2}/(?:19|20)\d{2})'
    year_only = r'(?:19|20)\d{2}'

    date_expr = f'(?:{strict_date}|{year_only})'
    end_expr = f'(?:{strict_date}|{year_only}|Present|Current|Now)'
    # WHY: \ufffd is the Unicode replacement character — PDFs with encoding
    # issues often emit it instead of an en-dash or em-dash.
    separator = r'\s*(?:-|–|—|\ufffd|to)\s*'

    # WHY range first: "Jan 2020 - Present" must match as a range, not as a
    # single date "Jan 2020" with trailing noise.
    range_pattern = f'\\b({date_expr}){separator}({end_expr})\\b'
    m = re.search(range_pattern, line, re.IGNORECASE)
    if m:
        end_val = m.group(2).strip()
        if end_val.lower() in ("present", "current", "now"):
            end_val = None  # WHY: open-ended; caller stores null
        return m.group(1).strip(), end_val, m.start()

    # WHY single strict only: requires a month word, so "2000" alone is rejected.
    single_strict = f'\\b({strict_date})\\b'
    m = re.search(single_strict, line, re.IGNORECASE)
    if m:
        return m.group(1).strip(), None, m.start()

    return None

# ---------------------------------------------------------------------------
# Link classifier
# ---------------------------------------------------------------------------

def classify_link(url: str) -> str:
    """Categorise a URL into link_linkedin / link_github / link_portfolio / link_other."""
    lower = url.lower()
    if "linkedin.com" in lower:
        return "link_linkedin"
    if "github.com" in lower:
        return "link_github"
    # WHY: personal domains often use these TLDs or the word "portfolio"
    if any(kw in lower for kw in ("portfolio", "personal", ".me/", ".dev/")):
        return "link_portfolio"
    # WHY: check TLD-only for .me and .dev (end of URL, no trailing path)
    if re.search(r'\.(me|dev)/?$', lower):
        return "link_portfolio"
    return "link_other"

# ---------------------------------------------------------------------------
# Contact extraction (emails, phones, name, location) — header block only
# ---------------------------------------------------------------------------

# WHY this regex: we need a domain with ≥2-char TLD and a path component
# OR a known multi-part domain (github.com, linkedin.com) to distinguish
# real URLs from things like "Node.js" or "harish.pal".
_URL_RE = re.compile(
    r'(https?://[^\s]+|www\.[^\s]+|[a-zA-Z0-9][\w.-]*\.[a-zA-Z]{2,}(?:/[^\s]+))',
    re.IGNORECASE,
)

# WHY: email domains like "example.com" from "user@example.com" should not
# become link_other entries.
_EMAIL_RE = re.compile(r'[\w.+-]+@[\w.-]+\.\w+')

# WHY: require ≥7 actual digits so short numbers (pin codes, ratings) don't match.
_PHONE_RE = re.compile(r'\+?\d[\d\s\-().]{6,}\d')


def _extract_emails(text: str) -> List[str]:
    return list(set(m.lower() for m in _EMAIL_RE.findall(text)))


def _extract_phones(text: str) -> List[str]:
    """Return raw phone strings (normalisation happens later)."""
    found = []
    for m in _PHONE_RE.finditer(text):
        digits = re.sub(r'\D', '', m.group())
        # WHY: real phone numbers have 7-15 digits (ITU-T E.164)
        if 7 <= len(digits) <= 15:
            found.append(m.group().strip())
    return found


def extract_contact_info(header_lines: List[str], all_lines: List[str]) -> List[FieldHit]:
    """Extract name, emails, phones, location from the résumé.

    WHY emails/phones scan ALL lines: they can appear anywhere (footer, etc.).
    WHY location scans ONLY header: avoids grabbing "Remote" from experience.
    """
    hits: List[FieldHit] = []
    full_text = "\n".join(all_lines)

    # ── name: first non-blank line ──
    if all_lines:
        name_parts = all_lines[0].split()
        if len(name_parts) >= 2:
            hits.append(FieldHit("first_name", name_parts[0], "resume", "inferred"))
            hits.append(FieldHit("last_name", " ".join(name_parts[1:]), "resume", "inferred"))
        elif name_parts:
            hits.append(FieldHit("first_name", all_lines[0].strip(), "resume", "inferred"))

    # ── emails: all occurrences, deduped ──
    for email in _extract_emails(full_text):
        hits.append(FieldHit("email", email, "resume", "parsed"))

    # ── phones: all occurrences ──
    for phone in _extract_phones(full_text):
        hits.append(FieldHit("phone", phone, "resume", "parsed"))

    # ── location: header only, after stripping emails/phones/URLs ──
    for line in header_lines:
        cleaned = line
        cleaned = _EMAIL_RE.sub('', cleaned)
        cleaned = _PHONE_RE.sub('', cleaned)
        cleaned = _URL_RE.sub('', cleaned)
        # WHY: strip pipe/bullet separators so "email | phone | City, ST" works
        cleaned = re.sub(r'[|•·]', ' ', cleaned)
        cleaned = cleaned.strip()
        if not cleaned:
            continue

        # WHY: location pattern = CapWord, CapWord[, CapWord]
        loc_match = re.search(
            r'\b([A-Z][a-zA-Z .-]+(?:,\s*[A-Z][a-zA-Z .-]+){1,2})\b', cleaned
        )
        if loc_match:
            parts = [p.strip() for p in loc_match.group(1).split(',')]
            if len(parts) == 3:
                hits.append(FieldHit("loc_city", parts[0], "resume", "parsed"))
                hits.append(FieldHit("loc_region", parts[1], "resume", "parsed"))
                hits.append(FieldHit("loc_country", parts[2], "resume", "parsed"))
            elif len(parts) == 2:
                hits.append(FieldHit("loc_city", parts[0], "resume", "parsed"))
                hits.append(FieldHit("loc_region", parts[1], "resume", "parsed"))
            break  # WHY: only the first location match in the header counts

    return hits

# ---------------------------------------------------------------------------
# Link extraction — header text + whole-doc PDF annotations
# ---------------------------------------------------------------------------

def extract_text_links(header_lines: List[str]) -> List[FieldHit]:
    """Extract URLs written out in header text.

    WHY header-only: running on all lines produces false positives from skill
    names like "Node.js" or "React.js" which match the URL regex.
    """
    hits: List[FieldHit] = []
    # WHY: collect email domains so we can skip them (e.g. "example.com")
    header_text = " ".join(header_lines)
    email_domains = set()
    for em in _EMAIL_RE.findall(header_text):
        email_domains.add(em.split("@")[1].lower())

    for line in header_lines:
        for m in _URL_RE.finditer(line):
            url_str = m.group(1)
            if "@" in url_str:
                continue  # WHY: email, not URL

            # WHY: skip if the match is just an email domain (e.g. "example.com")
            bare = url_str.lower().rstrip('/')
            if bare in email_domains:
                continue

            norm = url_str if url_str.startswith("http") else "https://" + url_str
            hits.append(FieldHit(classify_link(norm), norm, "resume", "parsed"))

    return hits

# ---------------------------------------------------------------------------
# Headline extraction
# ---------------------------------------------------------------------------

def extract_headline(header_lines: List[str]) -> List[FieldHit]:
    """The headline is the role/title line under the name in the header.

    WHY: it's NOT the first experience row — it's the short tagline like
    "Backend Developer" or "Cybersecurity Intern" that appears in the
    contact block before any section header.
    """
    # WHY: skip the first line (name) and any lines that are clearly
    # contact info (contain @ or phone digits or URLs).
    for line in header_lines[1:]:  # skip name (line 0)
        stripped = line.strip()
        if not stripped:
            continue
        # WHY: skip if it's contact info
        if _EMAIL_RE.search(stripped):
            continue
        if _PHONE_RE.search(stripped):
            continue
        if _URL_RE.search(stripped):
            continue
        # WHY: skip if it looks like a location (has comma + caps pattern)
        if re.search(r'[A-Z][a-z]+,\s*[A-Z]', stripped):
            continue
        # WHY: skip pipe-separated contact lines ("email | phone | link")
        if '|' in stripped:
            continue
        # WHY: what remains and is short is likely the headline
        if len(stripped.split()) <= 8:
            return [FieldHit("headline", stripped, "resume", "inferred")]
    return []

# ---------------------------------------------------------------------------
# Skills extraction
# ---------------------------------------------------------------------------

def extract_skills(skills_lines: List[str]) -> List[FieldHit]:
    """Parse both flat lists and 'Category: a, b, c' lines."""
    hits: List[FieldHit] = []
    for line in skills_lines:
        text = line.strip()
        if not text:
            continue
        # WHY: strip category label before the colon
        if ":" in text:
            text = text.split(":", 1)[1]
        for item in re.split(r'[,;•|]', text):
            val = item.strip().lstrip('-*•').strip()
            if val:
                hits.append(FieldHit("skill", val, "resume", "parsed"))
    return hits

# ---------------------------------------------------------------------------
# Experience extraction
# ---------------------------------------------------------------------------

def extract_experience(experience_lines: List[str]) -> List[FieldHit]:
    """Extract job entries from the experience/internship section lines.

    Layout heuristic (covers most résumés):
      Line N-1:  Company Name          Location
      Line N  :  Job Title             Mon YYYY – Mon YYYY
    OR:
      Line N  :  Title – Company       Mon YYYY – Mon YYYY
    """
    hits: List[FieldHit] = []
    i = 0
    while i < len(experience_lines):
        line = experience_lines[i]

        # WHY: check for "N years of experience" free-text first
        years_match = re.search(r'(\d+)\s+years?\s+of\s+(?:relevant\s+)?(?:industry\s+)?experience', line, re.IGNORECASE)
        if years_match:
            hits.append(FieldHit("years_experience", float(years_match.group(1)), "resume", "parsed"))
            i += 1
            continue

        date_res = extract_date_range(line)
        if not date_res:
            i += 1
            continue

        start_str, end_str, date_idx = date_res
        hits.append(FieldHit("start_date", start_str, "resume", "parsed"))
        if end_str:
            hits.append(FieldHit("end_date", end_str, "resume", "parsed"))

        # WHY: text BEFORE the date on this line is the title (or title–company)
        pre_date = line[:date_idx].strip()
        title = ""
        company = ""
        exp_location = ""

        # WHY: look at previous line for company + location (multi-space split)
        if i > 0:
            prev = experience_lines[i - 1].strip()
            if prev:
                # WHY: ≥2 spaces separate the company/title block from the location column
                parts = re.split(r'\s{2,}', prev)
                prev_main = parts[0].strip()
                if len(parts) > 1:
                    exp_location = parts[-1].strip()

                if not pre_date:
                    # WHY: if there's no pre_date, the previous line holds both title and company
                    dash_m = re.split(r'\s+[-–—\ufffd]\s+', prev_main, maxsplit=1)
                    if len(dash_m) == 2 and dash_m[0] and dash_m[1]:
                        title = dash_m[0].strip()
                        company = dash_m[1].strip()
                    else:
                        company = prev_main  # Default to company if no separator
                else:
                    # pre_date exists, so previous line is just company
                    company = prev_main

        if pre_date:
            # WHY: if pre_date itself contains a space-padded dash, it's "Title – Company"
            # WHY \ufffd: PDFs with encoding issues emit replacement char instead of dash
            dash_m = re.split(r'\s+[-–—\ufffd]\s+', pre_date, maxsplit=1)
            if len(dash_m) == 2 and dash_m[0] and dash_m[1]:
                title = dash_m[0].strip()
                company = dash_m[1].strip()
            else:
                title = pre_date

        if company:
            hits.append(FieldHit("company", company, "resume", "parsed"))
        if title:
            hits.append(FieldHit("job_title", title, "resume", "parsed"))
        if exp_location:
            hits.append(FieldHit("exp_location", exp_location, "resume", "parsed"))

        i += 1

    return hits

# ---------------------------------------------------------------------------
# Education extraction
# ---------------------------------------------------------------------------

def extract_education(education_lines: List[str]) -> List[FieldHit]:
    """Extract education entries.

    Layout heuristic:
      Line N:  B. Tech in CSE-AI  2023-Present
      Line N+1: Noida Institute of Engineering Technology
    OR:
      Line N:  B.S. Computer Science - University of Tech
      Line N+1: Sep 2017 – May 2021
    """
    hits: List[FieldHit] = []
    consumed = set()  # WHY: track lines we've used as institution so we don't re-process
    i = 0

    while i < len(education_lines):
        if i in consumed:
            i += 1
            continue

        line = education_lines[i]
        date_res = extract_date_range(line)

        if date_res:
            start_str, end_str, date_idx = date_res
            edu_end = end_str if end_str else start_str
            hits.append(FieldHit("edu_end_year", edu_end, "resume", "parsed"))

            pre_date = line[:date_idx].strip()
            degree = ""
            institution = ""

            if pre_date:
                # WHY: only split on SPACE-PADDED dash (" - ") to separate
                # "degree - institution".  A dash inside a degree like "CSE-AI"
                # has no surrounding spaces and must NOT be split.
                dash_parts = re.split(r'\s+-\s+', pre_date, maxsplit=1)
                if len(dash_parts) == 2 and dash_parts[0] and dash_parts[1]:
                    degree = dash_parts[0].strip()
                    institution = dash_parts[1].strip()
                else:
                    degree = pre_date

            # WHY: also check previous line if this line only had a date
            if not degree and not institution and i > 0 and (i - 1) not in consumed:
                prev = education_lines[i - 1].strip()
                if prev:
                    dash_parts = re.split(r'\s+-\s+', prev, maxsplit=1)
                    if len(dash_parts) == 2:
                        degree = dash_parts[0].strip()
                        institution = dash_parts[1].strip()
                    else:
                        degree = prev
                    consumed.add(i - 1)

            # WHY: if we still have no institution, the NEXT non-blank line
            # might be it (e.g. institution on its own line after the date line).
            if not institution:
                j = i + 1
                while j < len(education_lines) and not education_lines[j].strip():
                    j += 1
                if j < len(education_lines) and j not in consumed:
                    candidate = education_lines[j].strip()
                    # WHY: only take it if it has no date (otherwise it's a new entry)
                    if candidate and not extract_date_range(candidate):
                        institution = candidate
                        consumed.add(j)

            if degree:
                hits.append(FieldHit("edu_degree", degree, "resume", "parsed"))
            if institution:
                hits.append(FieldHit("edu_institution", institution, "resume", "parsed"))

        i += 1

    return hits

# ---------------------------------------------------------------------------
# Orchestrator — calls all extractors independently
# ---------------------------------------------------------------------------

def extract_hits_from_lines(lines: List[str]) -> List[FieldHit]:
    """Top-level extractor for résumé text lines.

    WHY each extractor gets its OWN slice: decoupling guarantees that a bug
    in experience parsing can never blank out skills or education.
    """
    sections = partition_sections(lines)
    header = sections.get("header", [])

    hits: List[FieldHit] = []
    hits.extend(extract_contact_info(header, lines))
    hits.extend(extract_text_links(header))
    hits.extend(extract_headline(header))
    hits.extend(extract_skills(sections.get("skills", [])))
    hits.extend(extract_experience(sections.get("experience", [])))
    hits.extend(extract_education(sections.get("education", [])))
    return hits

# ---------------------------------------------------------------------------
# CSV extractor
# ---------------------------------------------------------------------------

def extract_csv(source: RawSource) -> List[List[FieldHit]]:
    """Extract fields from CSV source. Returns a list of hit lists (one per row)."""
    candidates = []
    if not isinstance(source.payload, list):
        print(f"WARNING: CSV payload is not a list in {source.origin}")
        return []

    for row in source.payload:
        hits = []
        for key, value in row.items():
            if not key or not value or not value.strip():
                continue

            val = value.strip()
            k = key.lower().strip()

            if "first" in k and "name" in k:
                hits.append(FieldHit("first_name", val, "csv", "direct"))
            elif "last" in k and "name" in k:
                hits.append(FieldHit("last_name", val, "csv", "direct"))
            elif k == "name":
                # WHY: a bare "Name" column gets split into first + last
                parts = val.split(None, 1)
                hits.append(FieldHit("first_name", parts[0], "csv", "direct"))
                if len(parts) > 1:
                    hits.append(FieldHit("last_name", parts[1], "csv", "direct"))
            elif "email" in k or "e-mail" in k:
                hits.append(FieldHit("email", val, "csv", "direct"))
            elif "phone" in k or "mobile" in k:
                hits.append(FieldHit("phone", val, "csv", "direct"))
            elif "location" in k or "city" in k or "country" in k:
                hits.append(FieldHit("location", val, "csv", "direct"))
            elif "skill" in k:
                for s in val.split(','):
                    s = s.strip()
                    if s:
                        hits.append(FieldHit("skill", s, "csv", "direct"))
            elif "company" in k or "employer" in k:
                hits.append(FieldHit("company", val, "csv", "direct"))
            elif "title" in k or "role" in k:
                hits.append(FieldHit("job_title", val, "csv", "direct"))
            elif "start" in k:
                hits.append(FieldHit("start_date", val, "csv", "direct"))
            elif "end" in k:
                hits.append(FieldHit("end_date", val, "csv", "direct"))

        if hits:
            # WHY: same fix as ATS JSON — if company looks like a job title and
            # there's no actual title, swap it. Handles CSV data like
            # Company="Data Analyst", Title="".
            has_company = any(h.field == "company" for h in hits)
            has_title = any(h.field == "job_title" for h in hits)
            if has_company and not has_title:
                for h in hits:
                    if h.field == "company" and _TITLE_KEYWORDS.search(h.value):
                        h.field = "job_title"
                        break

            candidates.append(hits)

    return candidates

# ---------------------------------------------------------------------------
# ATS JSON extractor
# ---------------------------------------------------------------------------

# WHY: when source JSON has "company": "Java Backend Developer" with no title,
# these keywords help detect that the value is actually a job title.
_TITLE_KEYWORDS = re.compile(
    r'\b(developer|engineer|analyst|manager|designer|intern|architect|consultant'
    r'|scientist|administrator|specialist|lead|director|coordinator|officer)\b',
    re.IGNORECASE,
)


def extract_json(source: RawSource) -> List[List[FieldHit]]:
    """Extract fields from ATS JSON. Uses fuzzy key matching for resilience."""
    candidates = []
    if not isinstance(source.payload, list):
        print(f"WARNING: JSON payload is not a list in {source.origin}")
        return []

    for item in source.payload:
        hits = []
        if not isinstance(item, dict):
            continue

        try:
            for key, value in item.items():
                if not value:
                    continue
                k = key.lower().strip()

                if "first" in k and "name" in k:
                    hits.append(FieldHit("first_name", str(value), "ats", "mapped"))
                elif ("last" in k and "name" in k) or "family" in k:
                    hits.append(FieldHit("last_name", str(value), "ats", "mapped"))
                elif "given" in k and "name" in k:
                    hits.append(FieldHit("first_name", str(value), "ats", "mapped"))
                elif "email" in k or "e-mail" in k:
                    hits.append(FieldHit("email", str(value), "ats", "mapped"))
                elif "phone" in k or "mobile" in k:
                    hits.append(FieldHit("phone", str(value), "ats", "mapped"))
                elif "location" in k or "city" in k:
                    hits.append(FieldHit("location", str(value), "ats", "mapped"))
                elif "skill" in k:
                    if isinstance(value, list):
                        for s in value:
                            hits.append(FieldHit("skill", str(s), "ats", "mapped"))
                    else:
                        for s in str(value).split(','):
                            s = s.strip()
                            if s:
                                hits.append(FieldHit("skill", s, "ats", "mapped"))

                elif "work" in k or "experience" in k or "history" in k:
                    if not isinstance(value, list):
                        print(f"WARNING: {key} not a list for a record in {source.origin}")
                    else:
                        for work in value:
                            if not isinstance(work, dict):
                                continue
                            w_company = None
                            w_title = None
                            for w_key, w_val in work.items():
                                if not w_val:
                                    continue
                                wk = w_key.lower().strip()
                                if "company" in wk or "employer" in wk:
                                    w_company = str(w_val)
                                elif "title" in wk or "role" in wk:
                                    w_title = str(w_val)
                                elif "start" in wk:
                                    hits.append(FieldHit("start_date", str(w_val), "ats", "mapped"))
                                elif "end" in wk:
                                    hits.append(FieldHit("end_date", str(w_val), "ats", "mapped"))

                            # WHY: detect misplaced job title in the company field.
                            # If company looks like a title (has title keywords) and
                            # there's no actual title, swap it.
                            if w_company and not w_title and _TITLE_KEYWORDS.search(w_company):
                                w_title = w_company
                                w_company = None

                            if w_company:
                                hits.append(FieldHit("company", w_company, "ats", "mapped"))
                            if w_title:
                                hits.append(FieldHit("job_title", w_title, "ats", "mapped"))

        except Exception as e:
            print(f"WARNING: Failed to parse a JSON record: {e}")

        if hits:
            candidates.append(hits)

    return candidates

# ---------------------------------------------------------------------------
# PDF extractor
# ---------------------------------------------------------------------------

def extract_pdf(source: RawSource) -> List[List[FieldHit]]:
    """Extract fields from PDF using a robust, structural parser."""
    hits: List[FieldHit] = []
    filepath = source.payload

    try:
        text = ""
        with pdfplumber.open(filepath) as pdf:
            for page in pdf.pages:
                extracted = page.extract_text(layout=True)
                if extracted:
                    text += extracted + "\n"

                # WHY: PDF hyperlink annotations carry the real URL behind
                # anchor text like "LinkedIn" / "GitHub". pdfplumber exposes
                # them via page.hyperlinks.
                if hasattr(page, 'hyperlinks') and page.hyperlinks:
                    for hl in page.hyperlinks:
                        uri = hl.get('uri')
                        if uri and not uri.startswith('mailto:'):
                            norm = uri if uri.startswith("http") else "https://" + uri
                            hits.append(FieldHit(classify_link(norm), norm, "resume", "parsed"))

        lines = [line.strip() for line in text.split('\n') if line.strip()]
        hits.extend(extract_hits_from_lines(lines))

    except Exception as e:
        print(f"WARNING: Failed to parse PDF {filepath}: {e}")

    return [hits] if hits else []

# ---------------------------------------------------------------------------
# Top-level dispatcher
# ---------------------------------------------------------------------------

def extract(source: RawSource, meta: dict) -> List[List[FieldHit]]:
    if meta["source_type"] == "csv_export":
        return extract_csv(source)
    elif meta["source_type"] == "ats_json":
        return extract_json(source)
    elif meta["source_type"] == "resume_pdf":
        return extract_pdf(source)
    return []
