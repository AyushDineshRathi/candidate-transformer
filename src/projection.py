"""
Projection module.
Responsible for transforming the canonical model into specific output formats for external systems.
"""
import logging
from typing import Any
from src.models import CanonicalCandidate
from src import normalizers

logger = logging.getLogger(__name__)

class ProjectionError(Exception):
    pass

def resolve_path(data: Any, path: str) -> Any:
    """
    Resolves a path in a nested dictionary/list structure.
    Supports dot notation (a.b.c) and array indexing (a[0], a[]).
    """
    if not path:
        return data
        
    parts = path.replace('[', '.[').split('.')
    parts = [p for p in parts if p]
    
    current = data
    for i, part in enumerate(parts):
        if current is None:
            return None
            
        if part.startswith('[') and part.endswith(']'):
            idx_str = part[1:-1]
            if idx_str == '':
                if not isinstance(current, list):
                    return None
                remaining_path = '.'.join(parts[i+1:]).replace('.[', '[')
                if not remaining_path:
                    return current
                return [resolve_path(item, remaining_path) for item in current]
            else:
                try:
                    idx = int(idx_str)
                    if isinstance(current, list) and 0 <= idx < len(current):
                        current = current[idx]
                    else:
                        return None
                except ValueError:
                    return None
        else:
            if isinstance(current, dict):
                current = current.get(part)
            else:
                return None
                
    return current

def _apply_normalize(value: Any, norm_func_name: str) -> Any:
    if value is None:
        return None
        
    func_name = f"normalize_{norm_func_name.lower()}"
    if norm_func_name == "E164":
        func_name = "normalize_phone"
    elif norm_func_name == "canonical":
        func_name = "normalize_skill"
        
    func = getattr(normalizers, func_name, None)
    if not func:
        func = getattr(normalizers, norm_func_name, None)
        
    if func:
        if isinstance(value, list):
            return [func(v) for v in value]
        return func(value)
    
    logger.warning("Normalizer function not found for %s", norm_func_name)
    return value

def project(candidate: CanonicalCandidate, config: dict) -> dict:
    cand_dict = candidate.to_dict()
    output = {}
    
    fields = config.get("fields", [])
    include_confidence = config.get("include_confidence", False)
    include_provenance = config.get("include_provenance", False)
    on_missing = config.get("on_missing", "null")
    
    for f in fields:
        out_path = f.get("path")
        from_path = f.get("from")
        is_required = f.get("required", False)
        norm = f.get("normalize")
        
        val = resolve_path(cand_dict, from_path)
        
        conf_val = None
        prov_val = None
        if include_confidence and from_path:
            conf_path = from_path.replace('.value', '.confidence')
            conf_val = resolve_path(cand_dict, conf_path)
            
        if include_provenance and from_path:
            prov_path = from_path.replace('.value', '.provenance')
            prov_val = resolve_path(cand_dict, prov_path)
            
        if val is None or (isinstance(val, list) and len(val) == 0):
            # If the resolved value is an empty list from a '[]' query, it is effectively missing
            val = None

        if val is None:
            # Precedence rule: If required is false/absent, fall back to "null" behavior regardless of on_missing
            if not is_required:
                output[out_path] = None
                if include_confidence:
                    output[f"{out_path}_confidence"] = None
                if include_provenance:
                    output[f"{out_path}_provenance"] = None
            else:
                if on_missing == "error":
                    raise ProjectionError(f"Missing required field: {out_path} (from {from_path})")
                elif on_missing == "null":
                    output[out_path] = None
                    if include_confidence:
                        output[f"{out_path}_confidence"] = None
                    if include_provenance:
                        output[f"{out_path}_provenance"] = None
                elif on_missing == "omit":
                    pass
        else:
            if norm:
                val = _apply_normalize(val, norm)
                
            output[out_path] = val
            if include_confidence:
                output[f"{out_path}_confidence"] = conf_val
            if include_provenance:
                output[f"{out_path}_provenance"] = prov_val
                
    return output

def project_default(candidate: CanonicalCandidate) -> dict:
    out = {}
    out["candidate_id"] = candidate.candidate_id
    out["full_name"] = candidate.full_name.value if candidate.full_name else None
    out["emails"] = [e.value for e in candidate.emails]
    out["phones"] = [p.value for p in candidate.phones]
    
    if candidate.location and candidate.location.value:
        loc = candidate.location.value
        out["location"] = {
            "city": loc.get("city"),
            "region": loc.get("region"),
            "country": loc.get("country")
        }
    else:
        out["location"] = None
        
    out["links"] = candidate.links
    out["headline"] = candidate.headline.value if candidate.headline else None
    out["years_experience"] = candidate.years_experience.value if candidate.years_experience else None
    
    out["skills"] = []
    for s in candidate.skills:
        sources = [p.source for p in s.provenance]
        out["skills"].append({
            "name": s.value,
            "confidence": s.confidence,
            "sources": sources
        })
        
    out["experience"] = candidate.experience
    out["education"] = candidate.education
    
    prov_list = []
    def extract_prov(field_name, field_val_or_list):
        if not field_val_or_list:
            return
        if isinstance(field_val_or_list, list):
            for item in field_val_or_list:
                if hasattr(item, 'provenance'):
                    for p in item.provenance:
                        prov_list.append({"field": field_name, "source": p.source, "method": p.method})
        else:
            if hasattr(field_val_or_list, 'provenance'):
                for p in field_val_or_list.provenance:
                    prov_list.append({"field": field_name, "source": p.source, "method": p.method})

    extract_prov("full_name", candidate.full_name)
    extract_prov("emails", candidate.emails)
    extract_prov("phones", candidate.phones)
    extract_prov("location", candidate.location)
    extract_prov("headline", candidate.headline)
    extract_prov("years_experience", candidate.years_experience)
    
    out["provenance"] = prov_list
    out["overall_confidence"] = candidate.overall_confidence
    return out
