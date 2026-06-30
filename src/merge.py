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
from src.normalizers import normalize_phone

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
    3. Exact match on normalized phone (no fuzzy matching - this is a deliberate scope boundary to avoid false-positive merges across different people who happen to share a truncated number pattern).
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
                
        phones = set()
        for phone_val, prov in ext.phones:
            if phone_val:
                norm_p = normalize_phone(phone_val)
                if norm_p:
                    phones.add(norm_p)
                
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
                    
                c_phones = set()
                for p_val, _ in c_ext.phones:
                    if p_val:
                        norm_c_p = normalize_phone(p_val)
                        if norm_c_p:
                            c_phones.add(norm_c_p)
                            
                if not cluster_match and phones.intersection(c_phones):
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

def resolve_field(values: list[tuple[Any, Provenance]], field_name: str, conf_config: dict | None = None) -> Any:
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
            combined_conf = field_confidence(fake_values_and_prov, actual_val, conf_config)
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
        
    combined_conf = field_confidence(fake_values_and_prov, winner["value"], conf_config)
        
    return FieldValue(
        value=winner["value"],
        confidence=combined_conf,
        provenance=all_provs,
        conflicting_values=conflicting_values
    )

def merge_candidates(extractions: list[RawExtraction], conf_config: dict | None = None, db_path: str | None = None) -> list[CanonicalCandidate]:
    clusters = cluster_extractions(extractions)
    candidates = []
    
    NAMESPACE_OID = uuid.NAMESPACE_OID
    
    for cluster in clusters:
        cluster_github = None
        cluster_emails = []
        cluster_phones = []
        for ext in cluster:
            if ext.links and ext.links[0]:
                github = ext.links[0].get("github")
                if github and not cluster_github:
                    cluster_github = github.strip().lower()
            if ext.emails:
                for email, _ in ext.emails:
                    if email: cluster_emails.append(email.strip().lower())
            if ext.phones:
                for phone, _ in ext.phones:
                    if phone:
                        norm_p = normalize_phone(phone)
                        if norm_p: cluster_phones.append(norm_p)
                        
        candidate_id = None
        
        if db_path:
            from src.storage import find_bridging_conflicts, log_bridge_alert, lookup_candidate_by_identifiers
            
            conflicts = find_bridging_conflicts(db_path, cluster_emails, cluster_phones, cluster_github)
            if len(conflicts) > 1:
                # Bridging conflict: determine primary using priority rules and log the rest
                primary_id = lookup_candidate_by_identifiers(db_path, cluster_emails, cluster_phones, cluster_github)
                if primary_id in conflicts:
                    conflicts.remove(primary_id)
                log_bridge_alert(db_path, primary_id, conflicts)
                candidate_id = primary_id
            else:
                candidate_id = lookup_candidate_by_identifiers(db_path, cluster_emails, cluster_phones, cluster_github)

        if not candidate_id:
            join_key = None
            if cluster_github:
                join_key = f"github:{cluster_github}"
            elif cluster_emails:
                join_key = f"email:{cluster_emails[0]}"
            elif cluster_phones:
                join_key = f"phone:{cluster_phones[0]}"
            else:
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
        
        if db_path and candidate_id:
            from src.storage import get_candidate
            existing_cand_dict = get_candidate(db_path, candidate_id)
            if existing_cand_dict:
                if existing_cand_dict.get("full_name") and existing_cand_dict["full_name"].get("value"):
                    for p in existing_cand_dict["full_name"].get("provenance", []):
                        full_names.append((existing_cand_dict["full_name"]["value"], Provenance(**p)))
                        
                for e_dict in existing_cand_dict.get("emails", []):
                    if e_dict.get("value"):
                        for p in e_dict.get("provenance", []):
                            emails.append((e_dict["value"], Provenance(**p)))
                
                for p_dict in existing_cand_dict.get("phones", []):
                    if p_dict.get("value"):
                        for p in p_dict.get("provenance", []):
                            phones.append((p_dict["value"], Provenance(**p)))
                            
                if existing_cand_dict.get("location") and existing_cand_dict["location"].get("value"):
                    for p in existing_cand_dict["location"].get("provenance", []):
                        locations.append((existing_cand_dict["location"]["value"], Provenance(**p)))
                        
                if existing_cand_dict.get("headline") and existing_cand_dict["headline"].get("value"):
                    for p in existing_cand_dict["headline"].get("provenance", []):
                        headlines.append((existing_cand_dict["headline"]["value"], Provenance(**p)))
                        
                if existing_cand_dict.get("years_experience") and existing_cand_dict["years_experience"].get("value") is not None:
                    for p in existing_cand_dict["years_experience"].get("provenance", []):
                        years_exp.append((existing_cand_dict["years_experience"]["value"], Provenance(**p)))
                        
                for s_dict in existing_cand_dict.get("skills", []):
                    if s_dict.get("value"):
                        for p in s_dict.get("provenance", []):
                            skills.append((s_dict["value"], Provenance(**p)))
                            
                if existing_cand_dict.get("experience"):
                    for exp in existing_cand_dict["experience"]:
                        experiences.append((exp, Provenance("db", "db", "db", 1.0)))
                if existing_cand_dict.get("education"):
                    for edu in existing_cand_dict["education"]:
                        educations.append((edu, Provenance("db", "db", "db", 1.0)))
                
                if existing_cand_dict.get("links"):
                    valid_links = {k: v for k, v in existing_cand_dict["links"].items() if v}
                    if valid_links:
                        links_list.append((valid_links, Provenance("db", "db", "db", 1.0)))
        
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
            
        resolved_full_name = resolve_field(full_names, "full_name", conf_config)
        resolved_emails = resolve_field(emails, "emails", conf_config)
        resolved_phones = resolve_field(phones, "phones", conf_config)
        resolved_location = resolve_field(locations, "location", conf_config)
        resolved_headline = resolve_field(headlines, "headline", conf_config)
        resolved_years_experience = resolve_field(years_exp, "years_experience", conf_config)
        resolved_skills = resolve_field(skills, "skills", conf_config)
        
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
