"""
Duplicate Suggestions module.
Provides an informational layer to surface possible duplicates that were not
auto-merged by the strict deterministic matching logic.
"""
import os
import json
import itertools
from collections import Counter
from rapidfuzz import fuzz, utils
from src.models import CanonicalCandidate

# Load generic value stoplist
STOPLIST_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "generic_value_stoplist.json")
try:
    with open(STOPLIST_PATH, "r") as f:
        GENERIC_STOPLIST = set(json.load(f))
except FileNotFoundError:
    GENERIC_STOPLIST = set()

def get_informativeness(value: str, counts: Counter, stoplist: set) -> float:
    if not value or value in stoplist:
        return 0.0
    count = counts.get(value, 1)
    if count == 0:
        return 1.0
    return max(0.05, 1.0 / count)

def find_possible_duplicates(candidates: list[CanonicalCandidate]) -> list[dict]:
    """
    Computes a bounded similarity score using simple, explainable signals to find
    candidates that might be duplicates but didn't have exact email/phone/github matches.
    Threshold is conservatively high (0.6) to prioritize precision over recall and avoid false positives.
    """
    SUGGESTION_THRESHOLD = 0.6
    suggestions = []
    
    # 1. Compute frequency counts across the entire current candidate pool
    company_counts = Counter()
    skill_counts = Counter()
    country_counts = Counter()
    
    for cand in candidates:
        # Tally companies
        cand_companies = set()
        for exp in cand.experience:
            comp = exp.get("company")
            if comp:
                cand_companies.add(str(comp).strip().lower())
        for c in cand_companies:
            company_counts[c] += 1
            
        # Tally skills
        cand_skills = {s.value.strip().lower() for s in cand.skills if s.value}
        for s in cand_skills:
            skill_counts[s] += 1
            
        # Tally countries
        country = cand.location.value.get("country") if cand.location and cand.location.value else None
        if country:
            country_counts[str(country).strip().lower()] += 1

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

        company_overlap = companies_a.intersection(companies_b)
        if company_overlap:
            overlap = list(company_overlap)[0]
            informativeness = get_informativeness(overlap, company_counts, GENERIC_STOPLIST)
            contribution = 0.3 * informativeness
            if contribution > 0:
                score += contribution
                if informativeness < 0.34:
                    signals.append(f"shared company: {overlap} (common — low signal, contributed {contribution:.2f})")
                else:
                    signals.append(f"shared company: {overlap} (contributed {contribution:.2f})")

        # 3. Shared location.country (weight 0.15)
        country_a = cand_a.location.value.get("country") if cand_a.location and cand_a.location.value else None
        country_b = cand_b.location.value.get("country") if cand_b.location and cand_b.location.value else None
        
        if country_a and country_b and str(country_a).strip().lower() == str(country_b).strip().lower():
            overlap_country = str(country_a).strip().lower()
            informativeness = get_informativeness(overlap_country, country_counts, GENERIC_STOPLIST)
            contribution = 0.15 * informativeness
            if contribution > 0:
                score += contribution
                if informativeness < 0.34:
                    signals.append(f"shared country: {country_a} (common — low signal, contributed {contribution:.2f})")
                else:
                    signals.append(f"shared country: {country_a} (contributed {contribution:.2f})")

        # 4. Shared canonical skill (weight 0.15)
        skills_a = {s.value.strip().lower() for s in cand_a.skills if s.value}
        skills_b = {s.value.strip().lower() for s in cand_b.skills if s.value}
        
        skill_overlap = skills_a.intersection(skills_b)
        if skill_overlap:
            overlap_skill = list(skill_overlap)[0]
            informativeness = get_informativeness(overlap_skill, skill_counts, GENERIC_STOPLIST)
            contribution = 0.15 * informativeness
            if contribution > 0:
                score += contribution
                if informativeness < 0.34:
                    signals.append(f"shared skill: {overlap_skill.title()} (common — low signal, contributed {contribution:.2f})")
                else:
                    signals.append(f"shared skill: {overlap_skill.title()} (contributed {contribution:.2f})")

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
