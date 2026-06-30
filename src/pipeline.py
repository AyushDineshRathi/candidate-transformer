"""
Pipeline module.
Orchestrates the entire candidate processing flow: extract -> normalize -> merge -> project -> validate.
"""
import json
import logging

import copy
from src.extractors.csv_extractor import extract_from_csv
from src.extractors.github_extractor import extract_from_github
from src.extractors.ats_extractor import extract_from_ats_json
from src.extractors.resume_extractor import extract_from_resume
from src import normalizers
from src.merge import merge_candidates
from src.projection import project, project_default
from src.validation import validate_pipeline_output
from src.storage import init_db, upsert_candidate
from src.duplicate_suggestions import find_possible_duplicates
from src.normalizers import SkillCanonicalizer

logger = logging.getLogger(__name__)

def run_pipeline(csv_path: str | None = None, projection_config_path: str | None = None, ats_path: str | None = None, resume_paths: list[str] | None = None, github_url: str | None = None, db_path: str | None = None) -> dict:
    """
    Runs the full extraction, normalization, merge, projection, and validation pipeline.
    Normalization is performed here to keep extractors focused strictly on parsing.
    Returns a dict containing validation_results and stats.
    """
    import os
    
    # Load source confidence config
    conf_config = {}
    conf_path = "config/source_confidence.json"
    if os.path.exists(conf_path):
        with open(conf_path, "r", encoding="utf-8") as f:
            conf_config = json.load(f)
            
    if db_path:
        logger.info("Initializing database: %s", db_path)
        init_db(db_path)
        
    all_extractions = []
    
    canonicalizer = SkillCanonicalizer()
    
    if csv_path:
        csv_extractions = extract_from_csv(csv_path, conf_config=conf_config)
        all_extractions.extend(csv_extractions)
    
    if ats_path:
        ats_extractions = extract_from_ats_json(ats_path, conf_config=conf_config, canonicalizer=canonicalizer)
        all_extractions.extend(ats_extractions)
        
    if resume_paths:
        for r_path in resume_paths:
            res_ext = extract_from_resume(r_path, conf_config=conf_config, canonicalizer=canonicalizer)
            if res_ext:
                all_extractions.append(res_ext)
                
    if github_url:
        username = github_url.rstrip('/').split('/')[-1]
        try:
            logger.debug("Fetching Standalone GitHub profile for: %s", username)
            gh_ext = extract_from_github(username, conf_config=conf_config)
            if gh_ext:
                all_extractions.append(gh_ext)
        except Exception as e:
            logger.warning("Failed to extract standalone GitHub for %s: %s", username, e)
    
    seen_githubs = set()
    for ext in list(all_extractions):
        if ext.links and ext.links[0]:
            gh_url = ext.links[0].get("github")
            if gh_url:
                username = gh_url.rstrip('/').split('/')[-1]
                if username not in seen_githubs:
                    seen_githubs.add(username)
                    try:
                        logger.debug("Fetching GitHub profile for: %s", username)
                        gh_ext = extract_from_github(username, conf_config=conf_config)
                        if gh_ext:
                            all_extractions.append(gh_ext)
                    except Exception as e:
                        logger.warning("Failed to extract from GitHub for %s: %s", username, e)
                        
    logger.info("Stage 2: Normalize")
    import dataclasses
    skill_canonicalizer = normalizers.SkillCanonicalizer()
    
    fuzzy_penalty = conf_config.get("fuzzy_skill_match_penalty_multiplier", 0.95)
    
    for ext in all_extractions:
        if ext.full_name:
            val, prov = ext.full_name
            ext.full_name = (normalizers.normalize_name(val), prov)
            
        normalized_emails = []
        for val, prov in ext.emails:
            if val:
                normalized_emails.append((val.strip().lower(), prov))
        ext.emails = normalized_emails
        
        normalized_phones = []
        for val, prov in ext.phones:
            norm_val = normalizers.normalize_phone(val)
            if norm_val:
                normalized_phones.append((norm_val, prov))
        ext.phones = normalized_phones
        
        if ext.location:
            val, prov = ext.location
            ext.location = (normalizers.normalize_location(val), prov)
            
        normalized_skills = []
        for val, prov in ext.skills:
            norm_val, match_path = skill_canonicalizer.normalize(val)
            if norm_val:
                if match_path == "fuzzy_match":
                    prov = dataclasses.replace(prov, confidence=prov.confidence * fuzzy_penalty)
                normalized_skills.append((norm_val, prov))
        ext.skills = normalized_skills
        
    logger.info("Stage 3: Merge")
    candidates = merge_candidates(all_extractions, conf_config=conf_config, db_path=db_path)
    
    logger.info("Stage 4 & 5: Project & Validate")
    config = None
    schema = None
    custom_props = {}
    if projection_config_path:
        with open(projection_config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
            
        schema = {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "properties": {
                "candidates": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": custom_props,
                        "required": []
                    }
                },
                "possible_duplicates": { "type": "array" },
                "run_metadata": { "type": "object" }
            },
            "required": ["candidates"]
        }
        for field_cfg in config.get("fields", []):
            f_path = field_cfg["path"]
            f_type = field_cfg["type"]
            if field_cfg.get("required"):
                schema["properties"]["candidates"]["items"]["required"].append(f_path)
                
            if f_type == "string":
                schema["properties"][f_path] = {"type": ["string", "null"]}
            elif f_type == "string[]":
                schema["properties"][f_path] = {"type": ["array", "null"], "items": {"type": "string"}}
            else:
                schema["properties"][f_path] = {}
    else:
        with open("config/default_schema.json", "r", encoding="utf-8") as f:
            schema = json.load(f)
            
    results = []
    warnings = 0
    
    for cand in candidates:
        if db_path:
            upsert_candidate(db_path, cand)
            
        if config:
            proj_out = project(cand, config)
        else:
            proj_out = project_default(cand)
            
        results.append({"output": proj_out, "valid": True, "errors": []})
            
    stats = {
        "processed": len(all_extractions),
        "merged": len(candidates),
        "warnings": 0
    }
    
    if db_path:
        from src.storage import list_candidates
        from src.models import CanonicalCandidate
        all_cands_dicts = list_candidates(db_path)
        all_candidates_pool = [CanonicalCandidate.from_dict(d) for d in all_cands_dicts]
        suggestions = find_possible_duplicates(all_candidates_pool)
    else:
        suggestions = find_possible_duplicates(candidates)
    
    final_output = {
        "candidates": [r["output"] for r in results],
        "possible_duplicates": suggestions,
        "run_metadata": stats
    }
    
    val_res = validate_pipeline_output(final_output, schema)
    if not val_res["valid"]:
        logger.warning("Top-level validation failed: %s", val_res["errors"])
        
    for r in results:
        r["valid"] = val_res["valid"]
        r["errors"] = val_res["errors"]
    
    return {
        "candidates": results,
        "possible_duplicates": suggestions,
        "run_metadata": stats,
        "valid": val_res["valid"]
    }
