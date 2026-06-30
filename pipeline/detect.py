from models import RawSource

def detect_source(source: RawSource) -> dict:
    """Identify source type and which group (structured/unstructured)."""
    # In a real app, this might inspect payload shape.
    # Here, we use the type derived from extension.
    
    if source.type == "csv":
        return {"source_type": "csv_export", "format": "structured"}
    elif source.type == "json":
        return {"source_type": "ats_json", "format": "structured"}
    elif source.type == "pdf":
        return {"source_type": "resume_pdf", "format": "unstructured"}
    
    return {"source_type": "unknown", "format": "unknown"}
