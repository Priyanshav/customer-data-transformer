import os
import json
from typing import List, Optional
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
import uvicorn
from pydantic import BaseModel

from pipeline.ingest import ingest_buffer
from pipeline.detect import detect_source
from pipeline.extract import extract
from pipeline.match import match
from pipeline.merge import merge
from pipeline.score import score_and_provenance
from pipeline.project import project
from pipeline.validate import validate, ValidationError
from models import OutputConfig, ConfigField

app = FastAPI(title="Candidate Data Transformer API")

# Default Config embedded for fallback
DEFAULT_CONFIG = {
  "fields": [
    { "path": "candidate_id", "type": "string", "required": True },
    { "path": "full_name", "type": "string", "required": True },
    { "path": "emails", "type": "string[]" },
    { "path": "phones", "type": "string[]" },
    { "path": "location", "type": "object" },
    { "path": "skills", "type": "object[]" },
    { "path": "experience", "type": "object[]" },
    { "path": "years_experience", "type": "number" }
  ],
  "include_confidence": True,
  "on_missing": "null"
}

def parse_config(config_dict: dict) -> OutputConfig:
    fields = []
    for f in config_dict.get("fields", []):
        fields.append(ConfigField(
            path=f.get("path"),
            type=f.get("type"),
            required=f.get("required", False),
            from_path=f.get("from_path", None) or f.get("from", None),
            normalize=f.get("normalize", None)
        ))
    return OutputConfig(
        fields=fields,
        include_confidence=config_dict.get("include_confidence", True),
        on_missing=config_dict.get("on_missing", "null")
    )

@app.get("/api/health")
def health_check():
    return {"status": "ok"}

@app.post("/api/transform")
async def transform(
    files: List[UploadFile] = File(default=[]),
    config: Optional[str] = Form(None)
):
    """
    Accepts any number of multipart files (CSV, JSON, PDF) and an optional JSON config.
    Returns the transformed canonical profile(s).
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded.")

    # 1. Parse Config
    config_obj = DEFAULT_CONFIG
    if config:
        try:
            config_obj = json.loads(config)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid JSON config provided.")
    
    parsed_config = parse_config(config_obj)
    
    # 2. Ingest In-Memory
    raw_sources = []
    allowed_exts = {".csv", ".json", ".pdf"}
    
    for file in files:
        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in allowed_exts:
            # Skip bad files gracefully
            print(f"Skipping unsupported file extension: {file.filename}")
            continue
            
        content = await file.read()
        src = ingest_buffer(file.filename, content)
        if src.type != "error":
            raw_sources.append(src)

    if not raw_sources:
        raise HTTPException(status_code=400, detail="No valid files processed.")

    # 3-4. Detect, Extract, Normalize
    from pipeline.normalize import normalize_hits
    all_hits = []
    for src in raw_sources:
        meta = detect_source(src)
        extracted_candidates_hits = extract(src, meta)
        for hits in extracted_candidates_hits:
            all_hits.append(normalize_hits(hits))

    # 5. Match
    clusters = match(all_hits)
    
    final_outputs = []
    import hashlib
    for cluster in clusters:
        emails = [h.value for h in cluster if h.field == "email" and h.value]
        phones = [h.value for h in cluster if h.field == "phone" and h.value]
        
        # Deterministic Candidate ID based on normalized email, then phone
        candidate_id = "unknown"
        if emails:
            candidate_id = hashlib.sha256(emails[0].lower().strip().encode('utf-8')).hexdigest()
        elif phones:
            candidate_id = hashlib.sha256(phones[0].lower().strip().encode('utf-8')).hexdigest()
        else:
            # Fallback for resumes with no contact info but a name
            names = [h.value for h in cluster if h.field == "first_name" and h.value]
            if names:
                candidate_id = hashlib.sha256(names[0].lower().strip().encode('utf-8')).hexdigest()

        # 6. Merge
        canonical_record, used_hits = merge(candidate_id, cluster)
        
        # 7. Score
        score_and_provenance(canonical_record, used_hits)
        
        # 8. Project
        projected = project(canonical_record, parsed_config)
        
        # 9. Validate
        try:
            validated = validate(projected, parsed_config)
            final_outputs.append(validated)
        except ValidationError as e:
            # Add to output as an error node rather than crashing the whole batch
            final_outputs.append({"candidate_id": candidate_id, "error": str(e)})

    return final_outputs

# Mount static frontend
os.makedirs("static", exist_ok=True)
app.mount("/", StaticFiles(directory="static", html=True), name="static")

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=True)
