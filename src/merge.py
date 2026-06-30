"""
Merge module.
Responsible for combining multiple sources of candidate data into a single canonical model.
"""
import uuid
import logging
from collections import defaultdict
from typing import Any

from src.models import RawExtraction, CanonicalCandidate, FieldValue, Provenance
from src.confidence import field_confidence, overall_confidence

logger = logging.getLogger(__name__)

SOURCE_PRIORITY = {
    "recruiter.csv": 2,
    "ats.json": 1.5,
    "github_api": 1
}

def cluster_extractions(extractions: list[RawExtraction]) -> list[list[RawExtraction]]:
    """
    Groups RawExtractions that belong to the same person.
    Matching policy:
    1. Exact match on links.github (normalized URL/username)
    2. Exact match on normalized email
    3. Treat as separate (no fuzzy matching) - Precision over recall. A wrong merge corrupts the record.
    """
    clusters = []
    
    for ext in extractions:
        matched_cluster = None
        
        github_link = None
        if ext.links and ext.links[0]:
            github_link = ext.links[0].get("github")
            if github_link:
                github_link = github_link.strip().lower()
                
        emails = set()
        for email_val, prov in ext.emails:
            if email_val:
                emails.add(email_val.strip().lower())
                
        for cluster in clusters:
            cluster_match = False
            for c_ext in cluster:
                c_github = None
                if c_ext.links and c_ext.links[0]:
                    c_github = c_ext.links[0].get("github")
                    if c_github:
                        c_github = c_github.strip().lower()
                
                if github_link and c_github and github_link == c_github:
                    cluster_match = True
                    break
                
                c_emails = set()
                for e_val, _ in c_ext.emails:
                    if e_val:
                        c_emails.add(e_val.strip().lower())
                        
                if not cluster_match and emails.intersection(c_emails):
                    cluster_match = True
                    break
            
            if cluster_match:
                matched_cluster = cluster
                break
                
        if matched_cluster is not None:
            matched_cluster.append(ext)
        else:
            clusters.append([ext])
            
    return clusters

def get_source_priority(provs: list[Provenance]) -> int:
    if not provs:
        return 0
    return max((SOURCE_PRIORITY.get(p.source, 0) for p in provs), default=0)

def resolve_field(values: list[tuple[Any, Provenance]], field_name: str) -> Any:
    """
    Resolves conflicts for a given field across multiple extractions.
    Returns FieldValue for scalar fields, and list[FieldValue] for list fields.
    """
    if not values:
        if field_name in ["emails", "phones", "skills"]:
            return []
        return None
        
    list_fields = ["emails", "phones", "skills"]
    
    if field_name in list_fields:
        val_map = defaultdict(list)
        actual_vals = {}
        for val, prov in values:
            if val is not None:
                if isinstance(val, dict):
                    key = str(sorted(val.items()))
                elif isinstance(val, str):
                    key = val.strip().lower()
                else:
                    key = str(val)
                val_map[key].append(prov)
                actual_vals[key] = val
                
        results = []
        for k, provs in val_map.items():
            actual_val = actual_vals[k]
            fake_values_and_prov = [(actual_val, p) for p in provs]
            combined_conf = field_confidence(fake_values_and_prov, actual_val)
            results.append(FieldValue(
                value=actual_val,
                confidence=combined_conf,
                provenance=provs
            ))
        return results

    val_map = defaultdict(list)
    actual_vals = {}
    for val, prov in values:
        if val is not None:
            if isinstance(val, dict):
                if not any(v for v in val.values()):
                    continue
                key = str(sorted(val.items()))
            elif isinstance(val, str):
                key = val.strip().lower()
            else:
                key = str(val)
            val_map[key].append(prov)
            actual_vals[key] = val
                
    if not val_map:
        return None
        
    candidates = []
    for k, provs in val_map.items():
        priority = get_source_priority(provs)
        actual_val = actual_vals[k]
        candidates.append({
            "value": actual_val,
            "provs": provs,
            "priority": priority,
            "confidence": max((p.confidence for p in provs), default=0.0)
        })
        
    candidates.sort(key=lambda c: c["priority"], reverse=True)
    winner = candidates[0]
    
    conflicting_values = []
    fake_values_and_prov = []
    
    for c in candidates:
        for p in c["provs"]:
            fake_values_and_prov.append((c["value"], p))
            if c != winner:
                conflicting_values.append({
                    "value": c["value"],
                    "source": p.source,
                    "confidence": p.confidence
                })
            
    all_provs = []
    for c in candidates:
        all_provs.extend(c["provs"])
        
    combined_conf = field_confidence(fake_values_and_prov, winner["value"])
        
    return FieldValue(
        value=winner["value"],
        confidence=combined_conf,
        provenance=all_provs,
        conflicting_values=conflicting_values
    )

def merge_candidates(extractions: list[RawExtraction]) -> list[CanonicalCandidate]:
    clusters = cluster_extractions(extractions)
    candidates = []
    
    NAMESPACE_OID = uuid.NAMESPACE_OID
    
    for cluster in clusters:
        join_key = None
        for ext in cluster:
            if ext.links and ext.links[0]:
                github = ext.links[0].get("github")
                if github:
                    join_key = f"github:{github.strip().lower()}"
                    break
        
        if not join_key:
            for ext in cluster:
                if ext.emails:
                    for email, _ in ext.emails:
                        if email:
                            join_key = f"email:{email.strip().lower()}"
                            break
                if join_key:
                    break
                    
        if not join_key:
            join_key = f"ext:{cluster[0].candidate_id}"
            
        candidate_id = str(uuid.uuid5(NAMESPACE_OID, join_key))
        
        full_names = []
        emails = []
        phones = []
        locations = []
        links_list = []
        headlines = []
        years_exp = []
        skills = []
        experiences = []
        educations = []
        
        for ext in cluster:
            if ext.full_name: full_names.append(ext.full_name)
            if ext.emails: emails.extend(ext.emails)
            if ext.phones: phones.extend(ext.phones)
            if ext.location: locations.append(ext.location)
            if ext.links: links_list.append(ext.links)
            if ext.headline: headlines.append(ext.headline)
            if ext.years_experience: years_exp.append(ext.years_experience)
            if ext.skills: skills.extend(ext.skills)
            if ext.experience: experiences.extend(ext.experience)
            if ext.education: educations.extend(ext.education)
            
        resolved_full_name = resolve_field(full_names, "full_name")
        resolved_emails = resolve_field(emails, "emails")
        resolved_phones = resolve_field(phones, "phones")
        resolved_location = resolve_field(locations, "location")
        resolved_headline = resolve_field(headlines, "headline")
        resolved_years_experience = resolve_field(years_exp, "years_experience")
        resolved_skills = resolve_field(skills, "skills")
        
        final_links = {"linkedin": None, "github": None, "portfolio": None, "other": []}
        links_list_sorted = []
        for val, prov in links_list:
            priority = SOURCE_PRIORITY.get(prov.source, 0)
            links_list_sorted.append((priority, val))
        links_list_sorted.sort(key=lambda x: x[0])
        
        for _, links_dict in links_list_sorted:
            for k, v in links_dict.items():
                if v:
                    if k == "other":
                        final_links["other"].extend(v if isinstance(v, list) else [v])
                    else:
                        final_links[k] = v
                        
        final_experience = []
        for val, _ in experiences:
            if val not in final_experience:
                final_experience.append(val)
                
        final_education = []
        for val, _ in educations:
            if val not in final_education:
                final_education.append(val)
        
        c = CanonicalCandidate(
            candidate_id=candidate_id,
            full_name=resolved_full_name,
            emails=resolved_emails if resolved_emails else [],
            phones=resolved_phones if resolved_phones else [],
            location=resolved_location,
            links=final_links,
            headline=resolved_headline,
            years_experience=resolved_years_experience,
            skills=resolved_skills if resolved_skills else [],
            experience=final_experience,
            education=final_education,
            overall_confidence=0.0
        )
        c.overall_confidence = overall_confidence(c)
        candidates.append(c)
        
    return candidates
