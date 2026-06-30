import os
from typing import List, Union
from models import RawSource
import json
import csv
import io

def ingest_buffer(filename: str, content: bytes) -> RawSource:
    """Read from an in-memory buffer and wrap it in a RawSource."""
    ext = os.path.splitext(filename)[1].lower()
    
    try:
        if ext == ".json":
            payload = json.loads(content.decode('utf-8'))
        elif ext == ".csv":
            text = content.decode('utf-8')
            reader = csv.DictReader(io.StringIO(text))
            payload = list(reader)
        elif ext == ".pdf":
            # Pass BytesIO for pdfplumber
            payload = io.BytesIO(content)
        else:
            payload = content.decode('utf-8')
            
        return RawSource(type=ext[1:], payload=payload, origin=filename)
    except Exception as e:
        print(f"WARNING: Failed to ingest in-memory file {filename}: {e}")
        return RawSource(type="error", payload=None, origin=filename)

def ingest_file(filepath: str) -> RawSource:
    """Read a raw file and wrap it in a RawSource. Never trusts the shape."""
    ext = os.path.splitext(filepath)[1].lower()
    
    try:
        if ext == ".json":
            with open(filepath, 'r', encoding='utf-8') as f:
                payload = json.load(f)
        elif ext == ".csv":
            with open(filepath, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                payload = list(reader)
        elif ext == ".pdf":
            # Just pass the filepath for pdfplumber to handle
            payload = filepath
        else:
            with open(filepath, 'r', encoding='utf-8') as f:
                payload = f.read()
                
        return RawSource(type=ext[1:], payload=payload, origin=filepath)
    except Exception as e:
        print(f"WARNING: Failed to ingest {filepath}: {e}")
        return RawSource(type="error", payload=None, origin=filepath)

def ingest_directory(dirpath: str) -> List[RawSource]:
    sources = []
    for root, _, files in os.walk(dirpath):
        for file in files:
            sources.append(ingest_file(os.path.join(root, file)))
    return sources
