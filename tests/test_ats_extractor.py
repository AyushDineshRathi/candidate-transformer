"""
Tests for ATS JSON extractor.
"""
import json
import pytest
from src.extractors.ats_extractor import extract_from_ats_json

def test_extract_clean_record(tmp_path):
    ats_content = {
        "candidates": [
            {
                "ats_record_id": "ATS-1001",
                "personal": {
                    "displayName": "Linus Torvalds",
                    "contact": {"primaryEmail": "linus@linux.org", "mobile": "+1-503-555-0142"}
                },
                "employment": {"employer": "Linux Foundation", "jobTitle": "Fellow", "startDate": "2007-01-01"},
                "tags": ["kernel", "c-programming", "open-source"],
                "geo": "Portland, Oregon, United States"
            }
        ]
    }
    file_path = tmp_path / "clean_ats.json"
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(ats_content, f)
        
    extractions = extract_from_ats_json(str(file_path))
    assert len(extractions) == 1
    
    ext = extractions[0]
    assert ext.candidate_id == "ATS-1001"
    assert ext.full_name[0] == "Linus Torvalds"
    assert ext.full_name[1].source == "ats.json"
    assert ext.emails[0][0] == "linus@linux.org"
    assert ext.phones[0][0] == "+1-503-555-0142"
    assert len(ext.skills) == 3
    assert ext.skills[0][0] == "kernel"
    assert ext.location[0] == "Portland, Oregon, United States"
    assert ext.experience[0][0]["company"] == "Linux Foundation"

def test_extract_missing_personal_contact(tmp_path):
    ats_content = {
        "candidates": [
            {
                "ats_record_id": "ATS-1002",
                "personal": {
                    "displayName": "Incomplete Person"
                },
                "geo": "Unknown"
            }
        ]
    }
    file_path = tmp_path / "missing_contact.json"
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(ats_content, f)
        
    extractions = extract_from_ats_json(str(file_path))
    assert len(extractions) == 1
    
    ext = extractions[0]
    assert ext.full_name[0] == "Incomplete Person"
    assert not ext.emails
    assert not ext.phones
    assert ext.location[0] == "Unknown"

def test_extract_malformed_or_empty_file(tmp_path):
    # Missing completely
    extractions = extract_from_ats_json("nonexistent_file.json")
    assert extractions == []
    
    # Invalid JSON
    file_path = tmp_path / "invalid.json"
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("{ invalid json")
        
    extractions = extract_from_ats_json(str(file_path))
    assert extractions == []
    
    # Missing candidates array
    file_path2 = tmp_path / "no_candidates.json"
    with open(file_path2, "w", encoding="utf-8") as f:
        json.dump({"other_key": []}, f)
        
    extractions2 = extract_from_ats_json(str(file_path2))
    assert extractions2 == []
