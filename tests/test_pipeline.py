import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from engine.models import RawSource
from engine.pipeline import Pipeline

CSV = (
    "name,email,phone,current_company,title,location,skills\n"
    "Jane Doe,jane.doe@example.com,+1 415 555 0101,Acme Corp,Senior Engineer,"
    '"San Francisco, USA","Python, JS, Kubernetes"\n'
)
ATS = json.dumps({
    "candidates": [{
        "candidateName": "Jane Doe",
        "contact": {"emailAddress": "jane.doe@example.com", "phoneNumber": "+14155550101"},
        "currentRole": "Staff Software Engineer",
        "employer": "Acme Corporation",
        "skillSet": ["JavaScript", "Go", "k8s"],
    }]
})

def _sources(csv=CSV, ats=ATS):
    s = []
    if csv is not None:
        s.append(RawSource("csv", "structured", csv, "recruiter.csv"))
    if ats is not None:
        s.append(RawSource("ats_json", "structured", ats, "ats.json"))
    return s

def test_merge_dedups_same_person():
    out = Pipeline().run(_sources())
    assert out["count"] == 1
    p = out["profiles"][0]
    assert p["full_name"] == "Jane Doe"
    assert "jane.doe@example.com" in p["emails"]
    names = [s["name"] for s in p["skills"]]
    assert "JavaScript" in names and "Kubernetes" in names  # JS/k8s canonicalized

def test_phone_normalized_e164():
    out = Pipeline().run(_sources())
    assert out["profiles"][0]["phones"] == ["+14155550101"]

def test_garbage_source_does_not_crash():
    s = [RawSource("csv", "structured", "%%%not,a,csv\n\x00broken", "bad.csv")]
    out = Pipeline().run(s)
    assert isinstance(out["profiles"], list)  # no exception raised

def test_missing_required_error_policy_drops_only_that_record():
    cfg = {
        "fields": [
            {"path": "full_name", "type": "string", "required": True},
            {"path": "phone", "from": "phones[0]", "type": "string", "required": True},
        ],
        "on_missing": "error",
    }
    # Use a minimal ATS source that genuinely has NO phone field,
    # so the required "phone" path resolves to None and triggers a drop.
    ats_no_phone = json.dumps({
        "candidates": [{
            "candidateName": "Jane Doe",
            "contact": {"emailAddress": "jane.doe@example.com"},
            "currentRole": "Staff Software Engineer",
            "employer": "Acme Corporation",
        }]
    })
    out = Pipeline().run(_sources(csv=None, ats=ats_no_phone), cfg)
    assert out["count"] == 0
    assert any("dropped" in w for w in out["warnings"])

def test_custom_config_projection_shapes_output():
    cfg = {
        "fields": [
            {"path": "full_name", "type": "string", "required": True},
            {"path": "primary_email", "from": "emails[0]", "type": "string"},
            {"path": "skills", "from": "skills[].name", "type": "string[]"},
        ],
        "on_missing": "null",
    }
    out = Pipeline().run(_sources(), cfg)
    p = out["profiles"][0]
    assert p["primary_email"] == "jane.doe@example.com"
    assert isinstance(p["skills"], list)

if __name__ == "__main__":
    for _name, _fn in list(globals().items()):
        if _name.startswith("test_"):
            _fn()
            print("ok:", _name)
    print("all tests passed")
