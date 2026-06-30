"""
Explainability module to demystify candidate confidence and data merging.
"""

def explain_to_review_flag(candidate_dict: dict, threshold: float = 0.5) -> bool:
    """
    Returns True if overall_confidence is below threshold OR a core field
    (full_name, emails) is entirely missing.
    """
    overall_conf = candidate_dict.get("overall_confidence", 0.0)
    if overall_conf < threshold:
        return True
        
    full_name = candidate_dict.get("full_name")
    if not full_name or not full_name.get("value"):
        return True
        
    emails = candidate_dict.get("emails")
    if not emails or len(emails) == 0:
        return True
        
    return False

def format_provenance(prov_list: list) -> str:
    """
    Formats the provenance list into a human-readable string.
    """
    if not prov_list:
        return ""
    
    parts = []
    for p in prov_list:
        source = p.get("source", "unknown")
        conf = p.get("confidence", 0.0)
        parts.append(f"{source} ({conf:.2f})")
        
    if len(parts) == 1:
        return f"from {parts[0]} only"
    elif len(parts) == 2:
        return f"agreed by {parts[0]} and {parts[1]}"
    else:
        return f"agreed by {', '.join(parts[:-1])}, and {parts[-1]}"

def format_conflicts(conflicts: list) -> str:
    """
    Formats conflicting values into a readable string.
    """
    if not conflicts:
        return ""
        
    conflict_strs = []
    for c in conflicts:
        val = c.get("value")
        src = c.get("source", "unknown")
        if isinstance(val, dict):
            # Try to format dicts nicely (e.g. location dicts)
            val_str = ", ".join([str(v) for k, v in val.items() if v])
        else:
            val_str = str(val)
        conflict_strs.append(f'conflicting value "{val_str}" also seen from {src}')
        
    return "(penalized: " + "; ".join(conflict_strs) + ")"

def explain_candidate(candidate_dict: dict, all_candidates: list[dict] = None) -> str:
    """
    Generates a human-readable explanation of how a candidate's fields were decided.
    """
    name = candidate_dict.get("full_name", {}).get("value") if candidate_dict.get("full_name") else "Unknown"
    overall_conf = candidate_dict.get("overall_confidence", 0.0)
    
    lines = []
    lines.append(f"Candidate: {name} (confidence: {overall_conf:.2f})")
    lines.append("-" * 47)
    
    # full_name
    fn_field = candidate_dict.get("full_name")
    if fn_field and fn_field.get("value"):
        conf = fn_field.get("confidence", 0.0)
        prov = format_provenance(fn_field.get("provenance", []))
        confl = format_conflicts(fn_field.get("conflicting_values", []))
        
        detail = ""
        if confl:
            detail = confl
        else:
            detail = prov
            
        lines.append(f"full_name: \"{fn_field['value']}\"")
        lines.append(f"  - confidence {conf:.2f} - {detail}\n")
        
    # primary email
    emails = candidate_dict.get("emails", [])
    if emails:
        primary = emails[0]
        conf = primary.get("confidence", 0.0)
        prov = format_provenance(primary.get("provenance", []))
        confl = format_conflicts(primary.get("conflicting_values", []))
        
        detail = ""
        if confl:
            detail = confl
        else:
            detail = prov
            
        lines.append(f"primary email: \"{primary['value']}\"")
        lines.append(f"  - confidence {conf:.2f} - {detail}\n")
        
    # location
    loc_field = candidate_dict.get("location")
    if loc_field and loc_field.get("value"):
        val = loc_field["value"]
        if isinstance(val, dict):
            parts = [v for k, v in val.items() if v]
            loc_str = ", ".join(parts)
        else:
            loc_str = str(val)
            
        conf = loc_field.get("confidence", 0.0)
        prov = format_provenance(loc_field.get("provenance", []))
        confl = format_conflicts(loc_field.get("conflicting_values", []))
        
        detail = ""
        if confl:
            detail = confl
        else:
            detail = prov
            
        lines.append(f"location: {loc_str}")
        lines.append(f"  - confidence {conf:.2f} - {detail}\n")
        
    # skills
    skills = candidate_dict.get("skills", [])
    if skills:
        skill_strs = []
        for s in skills:
            skill_strs.append(f"{s['value']} ({s.get('confidence', 0.0):.2f})")
        lines.append(f"skills ({len(skills)}): {', '.join(skill_strs)}")
        
        all_sources = set()
        for s in skills:
            for p in s.get("provenance", []):
                all_sources.add(p.get("source"))
        
        if all_sources == {"github_api"}:
            lines.append("  - all derived from github_api repo languages - lower confidence by design,")
            lines.append("    since \"wrote code in X\" is weaker evidence than a stated/verified skill\n")
        else:
            lines.append(f"  - derived from {len(all_sources)} sources\n")
            
    # Final review flag
    is_flagged = explain_to_review_flag(candidate_dict)
    if is_flagged:
        reasons = []
        if not candidate_dict.get("full_name") or not candidate_dict.get("full_name", {}).get("value"):
            reasons.append("missing: full_name")
        if not candidate_dict.get("emails"):
            reasons.append("missing: emails")
        if not candidate_dict.get("phones"):
            reasons.append("missing: phone")
            
        # check low agreement fields
        for k in ["location", "full_name", "emails"]:
            f = candidate_dict.get(k)
            if isinstance(f, list) and f:
                f = f[0]
            if f and isinstance(f, dict) and f.get("conflicting_values"):
                reasons.append(f"low-agreement: {k}")
                
        reason_str = "; ".join(reasons)
        lines.append(f"! overall_confidence {overall_conf:.2f} - FLAGGED FOR REVIEW ({reason_str})")
    else:
        lines.append(f"! overall_confidence {overall_conf:.2f} - no flags")
        
    if all_candidates:
        from src.duplicate_suggestions import find_possible_duplicates
        from src.models import CanonicalCandidate
        
        cands = [CanonicalCandidate.from_dict(c) for c in all_candidates]
        suggestions = find_possible_duplicates(cands, threshold=0.4)
        
        my_id = candidate_dict.get("candidate_id")
        for s in suggestions:
            if s["candidate_a_id"] == my_id or s["candidate_b_id"] == my_id:
                other_name = s["candidate_b_name"] if s["candidate_a_id"] == my_id else s["candidate_a_name"]
                score = s["similarity_score"]
                if score >= 0.6:
                    lines.append(f"  ! Possible duplicate of \"{other_name}\" (score {score:.2f} — flagged for review)")
                else:
                    lines.append(f"  ! Possible duplicate of \"{other_name}\" (score {score:.2f}, below review threshold after informativeness discount — see /suggest-duplicates for full breakdown)")
                    
    return "\n".join(lines)
