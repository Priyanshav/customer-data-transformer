from . import csv_adapter, ats_json_adapter, resume_pdf_adapter

_REGISTRY = {
    "csv": csv_adapter,
    "ats_json": ats_json_adapter,
    "resume_pdf": resume_pdf_adapter,
}

def get_adapter(source_type: str):
    return _REGISTRY.get(source_type)
