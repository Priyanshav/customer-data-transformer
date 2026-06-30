from __future__ import annotations
from .adapters import get_adapter
from .match import cluster
from .merge import merge_cluster
from .score import score
from .project import project, validate, ValidationError

class Pipeline:
    """INGEST is done by the caller; this runs DETECT->...->VALIDATE."""

    def run(self, sources, config=None):
        warnings, records = [], []
        for raw in sources:
            adapter = get_adapter(raw.type)
            if adapter is None:
                warnings.append(f"no adapter for '{raw.type}' ({raw.origin}); skipped")
                continue
            try:
                recs = adapter.extract(raw)
            except Exception as e:
                warnings.append(f"failed to parse {raw.origin}: {e}; skipped")
                continue
            if not recs:
                warnings.append(f"no usable data extracted from {raw.origin}")
            records.extend(recs)

        canonical = [score(merge_cluster(c)) for c in cluster(records)]
        canonical.sort(key=lambda r: (r.get("full_name") or "", r.get("candidate_id")))

        if config:
            profiles = []
            for rec in canonical:
                try:
                    profiles.append(validate(project(rec, config), config))
                except ValidationError as e:
                    warnings.append(f"record {rec.get('candidate_id')} dropped: {e}")
        else:
            profiles = canonical

        return {"count": len(profiles), "profiles": profiles, "warnings": warnings}
