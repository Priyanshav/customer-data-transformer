from dataclasses import dataclass, field
from typing import Any, List, Optional, Dict
import hashlib

@dataclass
class RawSource:
    type: str
    payload: Any
    origin: str

@dataclass
class FieldHit:
    field: str
    value: Any
    source: str
    method: str

@dataclass
class Location:
    city: Optional[str] = None
    region: Optional[str] = None
    country: Optional[str] = None

@dataclass
class Links:
    linkedin: Optional[str] = None
    github: Optional[str] = None
    portfolio: Optional[str] = None
    other: List[str] = field(default_factory=list)

@dataclass
class Skill:
    name: str
    confidence: float
    sources: List[str] = field(default_factory=list)

@dataclass
class Experience:
    company: str
    title: str
    start: Optional[str] = None # YYYY-MM
    end: Optional[str] = None # YYYY-MM
    summary: Optional[str] = None

@dataclass
class Education:
    institution: str
    degree: str
    field_of_study: str
    end_year: Optional[str] = None

@dataclass
class Provenance:
    field: str
    source: str
    method: str

@dataclass
class CanonicalRecord:
    candidate_id: str
    full_name: str
    emails: List[str] = field(default_factory=list)
    phones: List[str] = field(default_factory=list)
    location: Optional[Location] = None
    links: Optional[Links] = field(default_factory=Links)
    headline: Optional[str] = None
    years_experience: Optional[float] = None
    skills: List[Skill] = field(default_factory=list)
    experience: List[Experience] = field(default_factory=list)
    education: List[Education] = field(default_factory=list)
    provenance: List[Provenance] = field(default_factory=list)
    overall_confidence: float = 0.0

    @staticmethod
    def generate_id(email: str) -> str:
        """Deterministic hash based on normalized email."""
        return hashlib.sha256(email.lower().strip().encode('utf-8')).hexdigest()

@dataclass
class ConfigField:
    path: str
    type: str
    required: bool = False
    from_path: Optional[str] = None
    normalize: Optional[str] = None

@dataclass
class OutputConfig:
    fields: List[ConfigField]
    include_confidence: bool = True
    on_missing: str = "null" # null, omit, error
