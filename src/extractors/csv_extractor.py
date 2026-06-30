"""
CSV extractor module.
Responsible for extracting candidate information from CSV exports.
"""
import csv
import json
import logging
import hashlib
from typing import Any
from src.models import RawExtraction, Provenance

logger = logging.getLogger(__name__)

def extract_from_csv(path: str, conf_config: dict | None = None) -> list[RawExtraction]:
    """
    Reads candidate data from a CSV file and produces RawExtractions.
    Handles missing files, empty rows, and malformed fields.
    """
    if conf_config is None:
        conf_config = {}
    base_conf = conf_config.get("recruiter.csv", 1.0)
    
    extractions = []
    
    try:
        with open(path, mode='r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # 2. Empty row / all columns blank -> skip the row, log it.
                if not any(v.strip() if v else False for v in row.values()):
                    logger.warning("Skipping fully empty row in %s", path)
                    continue
                
                row_str = json.dumps(row, sort_keys=True)
                candidate_id = hashlib.md5(row_str.encode('utf-8')).hexdigest()
                extraction = RawExtraction(candidate_id=candidate_id)
                
                # 5. Extra unknown columns are silently ignored by only requesting known keys.
                def get_val(key: str) -> str | None:
                    val = row.get(key)
                    if val is not None and val.strip():
                        return val.strip()
                    return None
                
                name = get_val('name')
                if name:
                    prov = Provenance("recruiter.csv", "name", "csv_row", base_conf)
                    extraction.full_name = (name, prov)
                
                email = get_val('email')
                if email:
                    # 3. Malformed email (no "@") -> lower confidence (0.4) rather than dropping it.
                    # Hardcoded relative penalty, scaled by base_conf
                    conf = base_conf if "@" in email else (base_conf * 0.4)
                    prov = Provenance("recruiter.csv", "email", "csv_row", conf)
                    extraction.emails.append((email, prov))
                
                phone = get_val('phone')
                if phone:
                    prov = Provenance("recruiter.csv", "phone", "csv_row", base_conf)
                    extraction.phones.append((phone, prov))
                
                company = get_val('current_company')
                title = get_val('title')
                if company or title:
                    exp_dict: dict[str, Any] = {
                        "company": company,
                        "title": title,
                        "start": None,
                        "end": None,
                        "summary": None
                    }
                    prov = Provenance("recruiter.csv", "current_company,title", "csv_row", base_conf)
                    extraction.experience.append((exp_dict, prov))
                
                github_url = get_val('github_url')
                if github_url:
                    links_dict: dict[str, Any] = {"github": github_url}
                    prov = Provenance("recruiter.csv", "github_url", "csv_row", base_conf)
                    extraction.links = (links_dict, prov)
                
                loc_str = get_val('location')
                if loc_str:
                    parts = [p.strip() for p in loc_str.split(',')]
                    if len(parts) >= 2:
                        loc_dict = {"city": parts[0], "region": None, "country": parts[-1]}
                    else:
                        loc_dict = {"city": loc_str, "region": None, "country": None}
                    prov = Provenance("recruiter.csv", "location", "csv_row", base_conf)
                    extraction.location = (loc_dict, prov)
                
                # If we didn't extract any known field (garbage row), skip it
                if not any([
                    extraction.full_name, extraction.emails, extraction.phones, 
                    extraction.experience, extraction.links, extraction.location
                ]):
                    logger.warning("No known fields found in row, skipping.")
                    continue
                    
                extractions.append(extraction)
                
    except FileNotFoundError as e:
        # 1. Missing file -> log warning and return empty list rather than letting the pipeline die
        logger.warning("CSV file not found: %s. Returning empty extractions list. Error: %s", path, e)
        return []

    return extractions
