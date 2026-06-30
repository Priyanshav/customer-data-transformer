from typing import List, Dict, Tuple
from models import FieldHit
import hashlib
from .normalize import normalize_phone

def match(records: List[List[FieldHit]]) -> List[List[FieldHit]]:
    """Group FieldHits that belong to the same person."""
    # Grouping by identity keys.
    # Priority: email > phone > name+corroborating(company)
    
    clusters: Dict[str, List[FieldHit]] = {}
    
    # We will build clusters. A cluster key is deterministic candidate_id.
    
    for hits in records:
        email = None
        phone = None
        first_name = None
        last_name = None
        company = None
        
        # Extract keys for this record
        for hit in hits:
            if hit.field == "email" and hit.value:
                email = hit.value.lower().strip()
            elif hit.field == "phone" and hit.value:
                # Phone should already be normalized by the normalize stage, but we ensure it's normalized for matching
                phone = normalize_phone(hit.value) or phone
            elif hit.field == "first_name":
                first_name = hit.value.lower().strip()
            elif hit.field == "last_name":
                last_name = hit.value.lower().strip()
            elif hit.field == "company":
                company = hit.value.lower().strip()
                
        full_name = f"{first_name} {last_name}".strip() if first_name else None
        
        # Determine key
        key = None
        if email:
            key = hashlib.sha256(email.encode('utf-8')).hexdigest()
        elif phone:
            key = hashlib.sha256(phone.encode('utf-8')).hexdigest()
        elif full_name and company:
            # Corroborating signal
            combined = f"{full_name}_{company}"
            key = hashlib.sha256(combined.encode('utf-8')).hexdigest()
        else:
            # Fuzzy name only is NOT merged. We generate a unique id for this record to avoid poisoning.
            # Using hash of all values + some salt
            salt = str(id(hits))
            key = hashlib.sha256(salt.encode('utf-8')).hexdigest()
            
        if key not in clusters:
            clusters[key] = []
        clusters[key].extend(hits)
        
    return list(clusters.values())
