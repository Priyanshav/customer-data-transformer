"""
Normalization layer — cleans extracted FieldHits into canonical forms.

Contract: every hit that passes through here is safe to merge. Invalid
hits (bad emails, unparseable phones) are DROPPED, not guessed.
"""

from typing import Optional, List
import re
from dateutil import parser as date_parser
import phonenumbers
import models
from pipeline.constants import SKILL_ALIASES

# WHY: centralised country alias map → ISO-3166 alpha-2.
# Never guess a country; if it isn't here, return None.
COUNTRY_MAP = {
    "usa": "US",
    "united states": "US",
    "united states of america": "US",
    "us": "US",
    "u.s.a.": "US",
    "u.s.": "US",
    "india": "IN",
    "ind": "IN",
    "in": "IN",
    "uk": "GB",
    "united kingdom": "GB",
    "great britain": "GB",
    "canada": "CA",
    "australia": "AU",
    "germany": "DE",
    "france": "FR",
    "singapore": "SG",
    "japan": "JP",
    "china": "CN",
    "uae": "AE",
    "united arab emirates": "AE",
}


def normalize_date(date_str: str) -> Optional[str]:
    """Normalize date to YYYY-MM or YYYY. Returns None if unparseable.

    WHY YYYY-MM only when a month is present: we must NEVER invent a month.
    """
    if not date_str:
        return None
    clean = date_str.strip()

    # WHY: pure 4-digit year → return as-is without dateutil (which would
    # fabricate a month/day)
    if re.fullmatch(r'\d{4}', clean):
        return clean

    try:
        # WHY: check if the original string actually contains a month indicator
        has_month = bool(re.search(r'[a-zA-Z]{3,}|/', clean))

        dt = date_parser.parse(clean, fuzzy=True)
        if has_month:
            return dt.strftime("%Y-%m")
        return dt.strftime("%Y")
    except Exception:
        return None


def normalize_phone(phone_str: str, default_region: str = "IN") -> Optional[str]:
    """Normalize phone to E.164. Returns None if unparseable or invalid.

    WHY default_region="IN": the assignment specifies Indian numbers as default.
    """
    if not phone_str:
        return None
    try:
        parsed = phonenumbers.parse(phone_str, default_region)
        if phonenumbers.is_valid_number(parsed):
            return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
        return None
    except Exception:
        return None


def normalize_country(country_str: str) -> Optional[str]:
    """Normalize country text to ISO-3166 alpha-2. Returns None if unknown.

    WHY None instead of a guess: "wrong-but-confident is worse than empty".
    """
    if not country_str:
        return None
    clean = country_str.lower().strip()
    # WHY: also check for 2-letter uppercase codes passed through
    if len(clean) == 2 and clean.upper() in {v for v in COUNTRY_MAP.values()}:
        return clean.upper()
    return COUNTRY_MAP.get(clean, None)


def normalize_skill(skill_str: str) -> str:
    """Normalize skill to canonical name if found, else return stripped title-case.

    WHY title-case fallback: unknown skills should look presentable in output.
    """
    clean = skill_str.lower().strip()
    if clean in SKILL_ALIASES:
        return SKILL_ALIASES[clean]
    return skill_str.strip()  # WHY: preserve original casing for unknowns


def derive_years_experience(experiences: List[models.Experience]) -> Optional[float]:
    """Derive total years of experience from a list of Experience spans.

    WHY we merge overlapping spans: two concurrent roles should not double-count.
    """
    if not experiences:
        return None

    spans = []
    for exp in experiences:
        if exp.start and exp.end:
            try:
                start_dt = date_parser.parse(exp.start)
                end_dt = date_parser.parse(exp.end)
                if start_dt <= end_dt:
                    spans.append((start_dt, end_dt))
            except Exception:
                continue

    if not spans:
        return None

    spans.sort(key=lambda x: x[0])
    merged = [spans[0]]
    for current in spans[1:]:
        prev = merged[-1]
        if current[0] <= prev[1]:
            merged[-1] = (prev[0], max(prev[1], current[1]))
        else:
            merged.append(current)

    total_days = sum((span[1] - span[0]).days for span in merged)
    years = total_days / 365.25
    return round(years, 1)


def normalize_hits(hits: List[models.FieldHit]) -> List[models.FieldHit]:
    """Applies normalizers to extracted hits. Drops hits that are invalid."""

    # WHY Pass 1: determine default phone region from location data BEFORE
    # normalizing phones, so Indian numbers don't get a +1 prefix.
    default_region = "IN"
    for hit in hits:
        if hit.field in ("location", "loc_country"):
            country = normalize_country(str(hit.value))
            if country:
                default_region = country
                break

    normalized = []
    for hit in hits:
        val = hit.value

        if hit.field == "email":
            if not re.match(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$", str(val)):
                continue
            val = str(val).lower().strip()

        elif hit.field == "phone":
            val = normalize_phone(str(val), default_region=default_region)
            if not val:
                continue

        elif hit.field in ("location", "loc_country"):
            val = normalize_country(str(val))
            if not val:
                continue

        elif hit.field == "skill":
            val = normalize_skill(str(val))

        elif hit.field in ("start_date", "end_date", "edu_end_year"):
            # WHY: edu_end_year also needs date normalization (was missing before)
            val = normalize_date(str(val))
            if not val:
                continue

        hit.value = val
        normalized.append(hit)

    return normalized
