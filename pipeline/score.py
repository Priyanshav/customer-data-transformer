from typing import List, Dict, Tuple
from models import CanonicalRecord, FieldHit, Provenance
from .merge import get_tier

def score_and_provenance(record: CanonicalRecord, used_hits_by_field: Dict[str, List[FieldHit]]):
    """Assign per-field + overall confidence; build provenance."""
    
    total_conf = 0.0
    field_count = 0
    
    for field_name, hits in used_hits_by_field.items():
        if not hits:
            continue
            
        # Determine base based on max tier of sources that provided this field
        max_tier = max(get_tier(h.source) for h in hits)
        if max_tier == 3:
            base = 1.0
        elif max_tier == 2:
            base = 0.8
        else:
            base = 0.6
            
        # Agreement factor: do they agree?
        values = set(h.value for h in hits if h.value)
        if len(values) == 1 and len(hits) > 1:
            agreement_factor = 1.1 # Agree
        elif len(values) > 1:
            agreement_factor = 0.8 # Conflict
        else:
            agreement_factor = 1.0 # Only one value
            
        # Normalization factor
        # If any hit was 'inferred' or 'mapped', it might be less confident than 'direct'
        methods = set(h.method for h in hits)
        normalization_factor = 0.9 if "inferred" in methods else 1.0
        
        confidence = min(1.0, base * agreement_factor * normalization_factor)
        
        total_conf += confidence
        field_count += 1
        
        # Build provenance
        for h in hits:
            record.provenance.append(Provenance(field=field_name, source=h.source, method=h.method))
            
    # Score skills based on sources
    for skill in record.skills:
        max_tier = max(get_tier(s) for s in skill.sources)
        base = 1.0 if max_tier == 3 else (0.8 if max_tier == 2 else 0.6)
        agreement_factor = 1.1 if len(skill.sources) > 1 else 1.0
        
        # Check if skill name matches a canonical alias perfectly or was title cased
        # We know if it's canonical if it's in the values of our SKILL_ALIASES map
        from .normalize import SKILL_ALIASES
        canonical_names = set(SKILL_ALIASES.values())
        normalization_factor = 1.0 if skill.name in canonical_names else 0.9
        
        skill.confidence = round(min(1.0, base * agreement_factor * normalization_factor), 2)
            
    record.overall_confidence = round(total_conf / field_count, 2) if field_count > 0 else 0.0
    
    # Deduplicate provenance
    unique_prov = []
    seen = set()
    for p in record.provenance:
        key = f"{p.field}_{p.source}_{p.method}"
        if key not in seen:
            seen.add(key)
            unique_prov.append(p)
    record.provenance = unique_prov
