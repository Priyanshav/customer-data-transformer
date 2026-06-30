from models import OutputConfig
from typing import Dict, Any

class ValidationError(Exception):
    pass

def validate(output: Dict[str, Any], config: OutputConfig) -> Dict[str, Any]:
    """Check the projected output against the requested schema before returning."""
    validated = {}
    
    for field in config.fields:
        val = output.get(field.path)
        
        # Check required
        is_missing = val is None or (isinstance(val, list) and len(val) == 0)
        
        if is_missing and field.required:
            if config.on_missing == "error":
                raise ValidationError(f"Required field '{field.path}' is missing.")
            elif config.on_missing == "omit":
                continue # Omit from output
            elif config.on_missing == "null":
                validated[field.path] = None
        elif is_missing:
            # Not required, but missing
            if config.on_missing == "omit":
                continue
            else:
                validated[field.path] = None
        else:
            validated[field.path] = val
            
    # Include confidences
    if config.include_confidence:
        validated["overall_confidence"] = output.get("overall_confidence")
        validated["provenance"] = output.get("provenance")
            
    return validated
