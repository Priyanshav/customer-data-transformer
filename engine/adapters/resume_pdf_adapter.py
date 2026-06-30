"""Adapter for résumé files (PDF or plain-text).

Extracts candidate data from unstructured prose using regex heuristics.
PDF parsing uses pypdf if installed; otherwise falls back to UTF-8 decode.
This is intentionally rule-based and English-first — no ML, no OCR.
"""
from __future__ import annotations
import io
import re
from ..models import RawSource, FieldHit

TIER = 2  # parsed unstructured prose (lower trust than structured)

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"\+?\d[\d\-\(\)\s]{7,}\d")
GITHUB_RE = re.compile(r"github\.com/([A-Za-z0-9_-]+)")
LINKEDIN_RE = re.compile(r"linkedin\.com/in/[A-Za-z0-9_-]+")

# Tolerant section-header patterns.  Match real-world variants:
#   "Skills", "SKILLS", "Technical Skills", "Skills & Tools:", "CORE SKILLS"
#   "Experience", "WORK EXPERIENCE", "Professional Experience:", "EMPLOYMENT"
#   "Education", "EDUCATION & CERTIFICATIONS", "Academic Background"
# Each pattern captures everything between the header and the next section or EOF.
_SKILLS_RE = re.compile(
    r"(?im)^[ \t]*(?:technical\s+|core\s+|key\s+)?"
    r"skills(?:\s*(?:&|and)\s*\w+)?[ \t]*:?[ \t]*\n"
    r"(.*?)"
    r"(?=^[ \t]*(?:experience|education|employment|work|projects|certifications|references|$))",
    re.DOTALL,
)

_EXP_RE = re.compile(
    r"(?im)^[ \t]*(?:work\s+|professional\s+)?"
    r"(?:experience|employment|work\s+history|internship(?:s)?)[ \t]*:?[ \t]*\n"
    r"(.*?)"
    r"(?=^[ \t]*(?:education|skills|projects|certifications|references|awards|experience|employment|work\s+history|internship(?:s)?|$))",
    re.DOTALL,
)

_EDU_RE = re.compile(
    r"(?im)^[ \t]*education(?:\s*(?:&|and)\s*\w+)?[ \t]*:?[ \t]*\n"
    r"(.*?)"
    r"(?=^[ \t]*(?:experience|skills|projects|certifications|references|awards|$)|(?:\Z))",
    re.DOTALL,
)

# Location heuristic: a segment that looks like "City, State" or "City, Country"
# Must contain a comma and be alphabetic (we strip postal codes before testing).
_LOCATION_SEGMENT_RE = re.compile(
    r"^([A-Za-z\s.]+),\s*([A-Za-z\s.]+?)(?:,\s*([A-Za-z\s.]+))?$"
)


def _text(raw: RawSource) -> str:
    """Extract plain text from the raw payload (PDF bytes or string)."""
    if isinstance(raw.payload, str):
        return raw.payload
    data = raw.payload
    try:
        from pypdf import PdfReader  # optional dependency
        reader = PdfReader(io.BytesIO(data))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception:
        try:
            return data.decode("utf-8", "replace")
        except Exception:
            return ""


# ── Date-range patterns used to find "Jun 2023 – Present" etc. ──────
# Matches month-year or year-only, with various separators (–, -, to, —).
_DATE_RE = re.compile(
    r"(?i)"
    r"("                                               # start date
    r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{4}"
    r"|\d{1,2}/\d{4}"
    r"|\d{4}"
    r")"
    r"\s*(?:[\u2013\u2014\-]+|to)\s*"                  # separator
    r"("                                               # end date
    r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{4}"
    r"|\d{1,2}/\d{4}"
    r"|\d{4}"
    r"|present|current|now|ongoing"
    r")"
)


def _parse_experience_section(section_text, add):
    """Date-anchored experience parser.

    1. Scan the section line by line. Only a line with a date range starts an entry.
    2. Read title from the nearest valid line above, and company from the line above that.
    3. Stop walking upward at bullets, lowercase continuation lines, or other date lines.
    4. Don't create an entry from a bullet or description line.
    """
    lines = [ln.strip() for ln in section_text.splitlines()]

    for i, line in enumerate(lines):
        if not line:
            continue

        dm = _DATE_RE.search(line)
        if not dm:
            continue

        start = dm.group(1).strip()
        end = dm.group(2).strip()

        # Walk upward to find title and company
        title = None
        company = None
        valid_lines = []

        for j in range(i - 1, -1, -1):
            prev = lines[j]
            if not prev:
                continue
            
            # Stop at bullet points or lowercase continuation lines
            if prev.startswith(("-", "•", "*")) or prev[0].islower():
                break
                
            # Stop if we hit another date line (it belongs to the previous entry)
            if _DATE_RE.search(prev):
                break

            valid_lines.append(prev)
            if len(valid_lines) == 2:
                break

        if len(valid_lines) >= 1:
            title = valid_lines[0]
            # If title line has a separator, try to split it
            parts = re.split(r"\s*[\u2014\u2013]\s*|\s+-\s+|\s*\|\s*|\s+at\s+", title, maxsplit=1)
            if len(parts) == 2:
                company = parts[0].strip()
                title = parts[1].strip()
            elif len(valid_lines) == 2:
                company = valid_lines[1]
        
        # If no title found above, try extracting from the date line itself
        if not title:
            heading = line[:dm.start()] + line[dm.end():]
            heading = re.sub(r"[|()\[\]]", " ", heading).strip()
            heading = re.sub(r"\s{2,}", " ", heading).strip()
            heading = heading.strip(" ,-–—|")
            
            if heading and not heading.startswith(("-", "•", "*")) and not heading[0].islower():
                parts = re.split(r"\s*[\u2014\u2013]\s*|\s+-\s+|\s*\|\s*|\s+at\s+", heading, maxsplit=1)
                if len(parts) == 2:
                    company = parts[0].strip()
                    title = parts[1].strip()
                else:
                    title = heading.strip()

        if not title or title.startswith(("-", "•", "*")):
            continue

        add("experience", {
            "company": company,
            "title": title,
            "start": start,
            "end": end,
            "summary": None,
        })

def extract(raw: RawSource):
    text = _text(raw)
    if not text.strip():
        return []
    hits = []

    def add(field, value, method="parsed"):
        if value:
            hits.append(FieldHit(field=field, value=value, source=raw.type,
                                 method=method, tier=TIER))

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

    # ── Name: first non-blank line ──────────────────────────────────
    if lines:
        add("full_name", lines[0])

    # ── Headline: second line if it's short and not an email/phone ──
    if len(lines) > 1 and len(lines[1]) < 60 and "@" not in lines[1]:
        # Make sure it doesn't look like a location line (has comma + short parts)
        if not _LOCATION_SEGMENT_RE.match(lines[1]):
            add("headline", lines[1])

    # ── Location: scan the first ~15 lines for a "City, Region, Country" pattern ─
    for ln in lines[:15]:
        # Stop scanning if we hit a major section header
        if re.match(r"(?i)^(experience|employment|work history|education|skills|projects|certifications|awards|internship)", ln):
            break
            
        # Split on pipes and bullets
        segments = re.split(r"[|\u2022\u2023\u25E6\u25AA*·•▪]", ln)
        found_loc = False
        
        for seg in segments:
            # Strip postal codes (4-6 consecutive digits, optionally with a space)
            clean_seg = re.sub(r"\b\d{4,6}\b|\b\d{3}\s\d{3}\b", "", seg)
            clean_seg = clean_seg.strip(" \t,-")
            
            lm = _LOCATION_SEGMENT_RE.match(clean_seg)
            if lm:
                city = lm.group(1).strip()
                # Could be "City, Country" (2 parts) or "City, State, Country" (3 parts)
                if lm.group(3):
                    add("city", city)
                    add("region", lm.group(2).strip())
                    add("country", lm.group(3).strip())
                else:
                    add("city", city)
                    add("country", lm.group(2).strip())
                add("location_raw", clean_seg)
                found_loc = True
                break
                
        if found_loc:
            break

    # ── Email, phone, GitHub, LinkedIn ──────────────────────────────
    for e in dict.fromkeys(EMAIL_RE.findall(text)):
        add("emails", e)
    for p in PHONE_RE.findall(text):
        add("phones", p)
    g = GITHUB_RE.search(text)
    if g:
        add("github", "github.com/" + g.group(1))
    li = LINKEDIN_RE.search(text)
    if li:
        add("linkedin", li.group(0))

    # ── Skills ──────────────────────────────────────────────────────
    sm = _SKILLS_RE.search(text)
    if sm:
        # Split on commas, semicolons, pipes, bullets, or newlines
        for s in re.split(r"[;,|\n\u2022\u2023\u25E6\u25AA\u2013\u2014•·]", sm.group(1)):
            s = s.strip().strip("-").strip("*").strip()
            if s and len(s) < 50 and not s.lower().startswith("experience"):
                add("skill", s)

    # ── Experience ──────────────────────────────────────────────────
    # Tolerant parser: split section into entries (by blank lines or per-line),
    # extract a date range and a heading, split heading into title/company.
    # We use finditer to capture multiple sections (e.g. Experience and Internships)
    for em in _EXP_RE.finditer(text):
        _parse_experience_section(em.group(1), add)

    # ── Education ───────────────────────────────────────────────────
    edm = _EDU_RE.search(text)
    if edm:
        for line in edm.group(1).splitlines():
            line = line.strip()
            if not line:
                continue
            ym = re.search(r"(\d{4})", line)
            # Try to split "Institution - Degree in Field" or "Institution, Degree"
            parts = re.split(r"[\u2014\-\u2013]", line, maxsplit=1)
            institution = parts[0].strip().rstrip(",")
            degree_part = parts[1].strip() if len(parts) > 1 else None
            degree, field_of_study = None, None
            if degree_part:
                # Try "BS in Computer Science, 2018"
                dm = re.match(r"(.+?)\s+in\s+(.+?)(?:,\s*\d{4})?$", degree_part)
                if dm:
                    degree = dm.group(1).strip()
                    field_of_study = dm.group(2).strip().rstrip(",").strip()
                else:
                    degree = re.sub(r",?\s*\d{4}$", "", degree_part).strip() or None
            add("education", {
                "institution": institution,
                "degree": degree,
                "field": field_of_study,
                "end_year": int(ym.group(1)) if ym else None,
            })

    return [hits] if hits else []
