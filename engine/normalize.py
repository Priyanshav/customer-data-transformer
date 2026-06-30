from __future__ import annotations
import re
from datetime import datetime

# Documented assumption (not a per-record guess): a bare 10-digit number is
# treated as US/NANP. Anything we cannot resolve becomes None (never invented).
DEFAULT_REGION_CC = "1"

def current_year() -> int:
    return datetime.now().year

def normalize_email(v):
    if v is None:
        return None
    s = str(v).strip().lower()
    return s if re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", s) else None

def normalize_phone(v):
    """Best-effort E.164. Unresolvable -> None."""
    if v is None:
        return None
    s = str(v).strip()
    has_plus = s.startswith("+")
    digits = re.sub(r"\D", "", s)
    if not digits:
        return None
    if has_plus:
        return "+" + digits if 8 <= len(digits) <= 15 else None
    if len(digits) == 11 and digits[0] == "1":
        return "+" + digits
    if len(digits) == 10:
        return "+" + DEFAULT_REGION_CC + digits
    return None

COUNTRY_MAP = {
    "us": "US", "usa": "US", "u.s.a": "US", "united states": "US",
    "united states of america": "US", "america": "US",
    "uk": "GB", "united kingdom": "GB", "england": "GB",
    "india": "IN", "bharat": "IN", "canada": "CA",
    "germany": "DE", "deutschland": "DE", "france": "FR",
    "australia": "AU", "singapore": "SG", "netherlands": "NL", "spain": "ES",
}

def normalize_country(v):
    if v is None:
        return None
    s = str(v).strip().lower().rstrip(".")
    if len(s) == 2 and s.isalpha():
        return s.upper()
    return COUNTRY_MAP.get(s)

SKILL_ALIASES = {
    "js": "JavaScript", "javascript": "JavaScript", "ecmascript": "JavaScript",
    "ts": "TypeScript", "typescript": "TypeScript",
    "py": "Python", "python": "Python", "python3": "Python",
    "golang": "Go", "go": "Go",
    "react": "React", "reactjs": "React", "react.js": "React",
    "node": "Node.js", "nodejs": "Node.js", "node.js": "Node.js",
    "postgres": "PostgreSQL", "postgresql": "PostgreSQL",
    "k8s": "Kubernetes", "kubernetes": "Kubernetes",
    "sql": "SQL", "ml": "Machine Learning", "machine learning": "Machine Learning",
    "aws": "AWS", "gcp": "Google Cloud", "tf": "Terraform", "terraform": "Terraform",
}

def canonical_skill(v):
    """Map aliases to a canonical name; unknown skills kept verbatim."""
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    return SKILL_ALIASES.get(s.lower(), s)

_MONTH_NAMES = ["january", "february", "march", "april", "may", "june",
                "july", "august", "september", "october", "november", "december"]
MONTHS = {}
for _i, _name in enumerate(_MONTH_NAMES, start=1):
    MONTHS[_name] = _i
    MONTHS[_name[:3]] = _i

def normalize_date(v):
    """Return canonical YYYY-MM, or None if unparseable.
    Ongoing markers (present/current) -> None. Year-only -> YYYY-01."""
    if v is None:
        return None
    s = str(v).strip().lower()
    if not s or s in ("present", "current", "now", "ongoing"):
        return None
    m = re.match(r"^(\d{4})-/", s)
    if m:
        y, mo = int(m.group(1)), int(m.group(2))
        if 1 <= mo <= 12:
            return f"{y:04d}-{mo:02d}"
    m = re.match(r"^(\d{1,2})-/$", s)
    if m:
        mo, y = int(m.group(1)), int(m.group(2))
        if 1 <= mo <= 12:
            return f"{y:04d}-{mo:02d}"
    m = re.match(r"^([a-z]+)\.?\s+(\d{4})$", s)
    if m and m.group(1) in MONTHS:
        return f"{int(m.group(2)):04d}-{MONTHS[m.group(1)]:02d}"
    m = re.match(r"^(\d{4})$", s)
    if m:
        return f"{int(m.group(1)):04d}-01"
    return None
