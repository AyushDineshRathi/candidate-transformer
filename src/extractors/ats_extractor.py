"""
ATS JSON extractor module.
Responsible for extracting candidate information from ATS JSON exports.
"""
import json
import logging
import uuid
from typing import Any
from src.models import RawExtraction, Provenance

logger = logging.getLogger(__name__)

def extract_from_ats_json(path: str) -> list[RawExtraction]:
    """
    Reads candidate data from an ATS JSON file and produces RawExtractions.
    Handles missing files, missing candidates array, and malformed fields gracefully.
    """
    extractions = []
    
    try:
        with open(path, mode='r', encoding='utf-8') as f:
            data = json.load(f)
            
        candidates = data.get("candidates")
        if not isinstance(candidates, list):
            logger.warning("No valid 'candidates' array found in %s", path)
            return []
            
        for record in candidates:
            if not isinstance(record, dict):
                continue
                
            candidate_id = record.get("ats_record_id")
            if not candidate_id:
                candidate_id = uuid.uuid4().hex
                
            extraction = RawExtraction(candidate_id=candidate_id)
            
            # Helper for nested gets
            def safe_get(d: dict, *keys: str) -> Any:
                for key in keys:
                    if isinstance(d, dict):
                        d = d.get(key)
                    else:
                        return None
                return d
                
            personal = record.get("personal") or {}
            
            name = safe_get(personal, "displayName")
            if name and isinstance(name, str) and name.strip():
                prov = Provenance("ats.json", "personal.displayName", "ats_json_parser", 0.95)
                extraction.full_name = (name.strip(), prov)
                
            email = safe_get(personal, "contact", "primaryEmail")
            if email and isinstance(email, str) and email.strip():
                prov = Provenance("ats.json", "personal.contact.primaryEmail", "ats_json_parser", 0.95)
                extraction.emails.append((email.strip(), prov))
                
            mobile = safe_get(personal, "contact", "mobile")
            if mobile and isinstance(mobile, str) and mobile.strip():
                prov = Provenance("ats.json", "personal.contact.mobile", "ats_json_parser", 0.95)
                extraction.phones.append((mobile.strip(), prov))
                
            employment = record.get("employment") or {}
            employer = employment.get("employer")
            job_title = employment.get("jobTitle")
            start_date = employment.get("startDate")
            
            if employer or job_title or start_date:
                exp_dict: dict[str, Any] = {
                    "company": employer if employer and str(employer).strip() else None,
                    "title": job_title if job_title and str(job_title).strip() else None,
                    "start": start_date if start_date and str(start_date).strip() else None,
                    "end": None,
                    "summary": None
                }
                source_fields = []
                if employer: source_fields.append("employment.employer")
                if job_title: source_fields.append("employment.jobTitle")
                if start_date: source_fields.append("employment.startDate")
                
                prov = Provenance("ats.json", ",".join(source_fields), "ats_json_parser", 0.95)
                extraction.experience.append((exp_dict, prov))
                
            tags = record.get("tags")
            if isinstance(tags, list):
                for tag in tags:
                    if tag and isinstance(tag, str) and tag.strip():
                        prov = Provenance("ats.json", "tags", "ats_json_parser", 0.95)
                        extraction.skills.append((tag.strip(), prov))
                        
            geo = record.get("geo")
            if geo and isinstance(geo, str) and geo.strip():
                prov = Provenance("ats.json", "geo", "ats_json_parser", 0.95)
                extraction.location = (geo.strip(), prov)
                
            if not any([
                extraction.full_name, extraction.emails, extraction.phones, 
                extraction.experience, extraction.skills, extraction.location
            ]):
                logger.warning("No known fields found in ATS record %s, skipping.", candidate_id)
                continue
                
            extractions.append(extraction)
            
    except FileNotFoundError as e:
        logger.warning("ATS JSON file not found: %s. Returning empty extractions list. Error: %s", path, e)
        return []
    except json.JSONDecodeError as e:
        logger.warning("Invalid JSON in ATS file: %s. Error: %s", path, e)
        return []

    return extractions
