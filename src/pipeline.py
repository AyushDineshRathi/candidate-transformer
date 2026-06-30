"""
Pipeline module.
Orchestrates the entire candidate processing flow: extract -> normalize -> merge -> project -> validate.
"""
import json
import logging
from typing import Any

from src.extractors.csv_extractor import extract_from_csv
from src.extractors.github_extractor import extract_from_github
from src import normalizers
from src.merge import merge_candidates
from src.projection import project, project_default
from src.validation import validate_pipeline_output

logger = logging.getLogger(__name__)

def run_pipeline(csv_path: str, projection_config_path: str | None = None) -> dict:
    """
    Runs the full extraction, normalization, merge, projection, and validation pipeline.
    Normalization is performed here to keep extractors focused strictly on parsing.
    Returns a dict containing validation_results and stats.
    """
    logger.info("Stage 1: Extract")
    csv_extractions = extract_from_csv(csv_path)
    all_extractions = []
    all_extractions.extend(csv_extractions)
    
    seen_githubs = set()
    for ext in csv_extractions:
        if ext.links and ext.links[0]:
            github_url = ext.links[0].get("github")
            if github_url:
                username = github_url.rstrip('/').split('/')[-1]
                if username not in seen_githubs:
                    seen_githubs.add(username)
                    try:
                        logger.debug("Fetching GitHub profile for: %s", username)
                        gh_ext = extract_from_github(username)
                        if gh_ext:
                            all_extractions.append(gh_ext)
                    except Exception as e:
                        logger.warning("Failed to extract from GitHub for %s: %s", username, e)
                        
    logger.info("Stage 2: Normalize")
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
            norm_val = normalizers.normalize_skill(val)
            normalized_skills.append((norm_val, prov))
        ext.skills = normalized_skills
        
    logger.info("Stage 3: Merge")
    candidates = merge_candidates(all_extractions)
    
    logger.info("Stage 4 & 5: Project & Validate")
    config = None
    schema = None
    if projection_config_path:
        with open(projection_config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
            
        schema = {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "properties": {},
            "required": []
        }
        for field_cfg in config.get("fields", []):
            f_path = field_cfg["path"]
            f_type = field_cfg["type"]
            if field_cfg.get("required"):
                schema["required"].append(f_path)
                
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
        if config:
            proj_out = project(cand, config)
        else:
            proj_out = project_default(cand)
            
        val_res = validate_pipeline_output(proj_out, schema)
        if not val_res["valid"]:
            warnings += 1
            logger.warning("Validation failed for %s: %s", cand.candidate_id, val_res["errors"])
                
        results.append(val_res)
        
        logger.debug("Decisions for %s:", cand.candidate_id)
        if cand.full_name and getattr(cand.full_name, 'conflicting_values', None):
            logger.debug(" - Name conflict resolved: won=%s, lost=%s", cand.full_name.value, cand.full_name.conflicting_values)
        if cand.headline and getattr(cand.headline, 'conflicting_values', None):
            logger.debug(" - Headline conflict resolved: won=%s, lost=%s", cand.headline.value, cand.headline.conflicting_values)
        
    stats = {
        "processed": len(all_extractions),
        "merged": len(candidates),
        "warnings": warnings
    }
    
    return {
        "candidates": results,
        "stats": stats
    }
