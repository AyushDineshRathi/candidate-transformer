"""
Confidence module.
Responsible for scoring and assigning confidence metrics to merged candidate data points.
"""
from typing import Any
from src.models import Provenance, CanonicalCandidate

DISAGREEMENT_PENALTY = 0.9  # Tunable constant

def combine_confidence(confidences: list[float]) -> float:
    """
    Combines multiple confidences using the evidence accumulation formula:
    combined = 1 - product(1 - c_i for each c_i)
    
    This rewards agreement from multiple sources. Note: this assumes rough 
    independence between sources, which is a known simplification/approximation.
    """
    if not confidences:
        return 0.0
        
    prob_all_wrong = 1.0
    for c in confidences:
        clamped = max(0.0, min(1.0, c))
        prob_all_wrong *= (1.0 - clamped)
        
    combined = 1.0 - prob_all_wrong
    return max(0.0, min(1.0, combined))

def field_confidence(values_and_provenance: list[tuple[Any, Provenance]], winning_value: Any) -> float:
    """
    Computes final confidence for a resolved field value.
    - Uses evidence accumulation if multiple sources support the exact same value.
    - Applies a penalty if there was disagreement (conflicting values existed).
    """
    if not values_and_provenance:
        return 0.0
        
    supporting_confidences = []
    disagreement_exists = False
    
    for val, prov in values_and_provenance:
        if val == winning_value:
            supporting_confidences.append(prov.confidence)
        elif val is not None:
            disagreement_exists = True
            
    if not supporting_confidences:
        return 0.0
        
    if len(supporting_confidences) == 1:
        base_conf = supporting_confidences[0]
    else:
        base_conf = combine_confidence(supporting_confidences)
        
    if disagreement_exists:
        base_conf *= DISAGREEMENT_PENALTY
        
    return max(0.0, min(1.0, base_conf))

def overall_confidence(candidate: CanonicalCandidate) -> float:
    """
    Computes overall confidence for the candidate as an average of core fields:
    full_name, emails, phones, skills.
    
    Missing core fields pull the average down (treated as 0 confidence) because a profile
    missing a name (or other core info) should never score as "high confidence" overall
    just because the fields it DOES have look strong.
    """
    core_scores = []
    
    # 1. full_name
    if candidate.full_name:
        core_scores.append(candidate.full_name.confidence)
    else:
        core_scores.append(0.0)
        
    # 2. emails
    if candidate.emails:
        core_scores.append(max(e.confidence for e in candidate.emails))
    else:
        core_scores.append(0.0)
        
    # 3. phones
    if candidate.phones:
        core_scores.append(max(p.confidence for p in candidate.phones))
    else:
        core_scores.append(0.0)
        
    # 4. skills
    if candidate.skills:
        avg_skill = sum(s.confidence for s in candidate.skills) / len(candidate.skills)
        core_scores.append(avg_skill)
    else:
        core_scores.append(0.0)
        
    avg = sum(core_scores) / len(core_scores)
    return round(max(0.0, min(1.0, avg)), 3)
