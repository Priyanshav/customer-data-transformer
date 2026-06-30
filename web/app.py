from __future__ import annotations
import json
import os
from typing import List
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import JSONResponse, FileResponse
from engine.pipeline import Pipeline
from engine.models import RawSource

app = FastAPI(title="Candidate Data Transformer")
HERE = os.path.dirname(__file__)
MAX_BYTES = 10 * 1024 * 1024

EXT = {".csv": ("csv", "structured"), ".json": ("ats_json", "structured"),
       ".pdf": ("resume_pdf", "unstructured"), ".txt": ("resume_pdf", "unstructured")}

@app.get("/")
def index():
    return FileResponse(os.path.join(HERE, "static", "index.html"))

@app.post("/api/transform")
async def transform(files: List[UploadFile] = File(default=[]), config: str = Form(default="")):
    sources = []
    for f in files:
        ext = os.path.splitext(f.filename or "")[1].lower()
        if ext not in EXT:
            continue
        data = await f.read()
        if len(data) > MAX_BYTES:
            return JSONResponse({"error": f"{f.filename} exceeds 10MB"}, status_code=400)
        t, g = EXT[ext]
        payload = data if ext == ".pdf" else data.decode("utf-8", "replace")
        sources.append(RawSource(type=t, group=g, payload=payload, origin=f.filename))

    if not sources:
        return JSONResponse({"error": "Upload at least one CSV, ATS JSON, or resume file."},
                            status_code=400)

    cfg = None
    if config.strip():
        try:
            cfg = json.loads(config)
        except Exception as e:
            return JSONResponse({"error": f"Invalid config JSON: {e}"}, status_code=400)

    try:
        result = Pipeline().run(sources, cfg)
    except Exception as e:
        return JSONResponse({"error": f"Processing failed: {e}"}, status_code=500)
    # Privacy: nothing is persisted; uploads & results live only in memory.
    return JSONResponse(result)
