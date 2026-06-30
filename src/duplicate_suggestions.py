"""
Duplicate Suggestions module.
Provides an informational layer to surface possible duplicates that were not
auto-merged by the strict deterministic matching logic.
"""
import itertools
from rapidfuzz import fuzz, utils
from src.models import CanonicalCandidate

def find_possible_duplicates(candidates: list[CanonicalCandidate]) -> list[dict]:
    """
    Computes a bounded similarity score using simple, explainable signals to find
    candidates that might be duplicates but didn't have exact email/phone/github matches.
    Threshold is conservatively high (0.6) to prioritize precision over recall and avoid false positives.
    """
    SUGGESTION_THRESHOLD = 0.6
    suggestions = []

    for cand_a, cand_b in itertools.combinations(candidates, 2):
        score = 0.0
        signals = []

        name_a = cand_a.full_name.value if cand_a.full_name else ""
        name_b = cand_b.full_name.value if cand_b.full_name else ""
        
        name_a_clean = str(name_a).strip().lower()
        name_b_clean = str(name_b).strip().lower()
        
        # 1. Normalized full_name similarity (weight 0.4)
        if name_a_clean and name_b_clean:
            name_sim = fuzz.token_sort_ratio(name_a_clean, name_b_clean, processor=utils.default_process) / 100.0
            if name_sim > 0:
                score += name_sim * 0.4
                signals.append(f"name similarity ({name_sim:.2f})")

        # 2. Shared/overlapping current company (weight 0.3)
        # Current company: any company in experience (exact normalized string match)
        companies_a = set()
        for exp in cand_a.experience:
            comp = exp.get("company")
            if comp:
                companies_a.add(str(comp).strip().lower())
                
        companies_b = set()
        for exp in cand_b.experience:
            comp = exp.get("company")
            if comp:
                companies_b.add(str(comp).strip().lower())

        if companies_a.intersection(companies_b):
            score += 0.3
            overlap = list(companies_a.intersection(companies_b))[0]
            signals.append(f"shared company ({overlap})")

        # 3. Shared location.country (weight 0.15)
        country_a = cand_a.location.value.get("country") if cand_a.location and cand_a.location.value else None
        country_b = cand_b.location.value.get("country") if cand_b.location and cand_b.location.value else None
        
        if country_a and country_b and str(country_a).strip().lower() == str(country_b).strip().lower():
            score += 0.15
            signals.append(f"shared country ({country_a})")

        # 4. Shared canonical skill (weight 0.15)
        skills_a = {s.value.strip().lower() for s in cand_a.skills if s.value}
        skills_b = {s.value.strip().lower() for s in cand_b.skills if s.value}
        
        skill_overlap = skills_a.intersection(skills_b)
        if skill_overlap:
            score += 0.15
            signals.append(f"shared skill: {list(skill_overlap)[0].title()}")

        if score > SUGGESTION_THRESHOLD:
            suggestions.append({
                "candidate_a_id": cand_a.candidate_id,
                "candidate_a_name": name_a,
                "candidate_b_id": cand_b.candidate_id,
                "candidate_b_name": name_b,
                "similarity_score": round(score, 2),
                "matching_signals": signals,
                "suggested_action": "review — possible duplicate, not auto-merged (no exact email/phone/github match found)"
            })

    # Sort descending by score
    suggestions.sort(key=lambda x: x["similarity_score"], reverse=True)
    return suggestions
