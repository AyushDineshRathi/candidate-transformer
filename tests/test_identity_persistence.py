import json
import os
import sqlite3
import pytest
from src.pipeline import run_pipeline
from src.storage import list_candidates, init_db

@pytest.fixture
def test_db(tmp_path):
    db_path = str(tmp_path / "test_identity.sqlite3")
    return db_path

def test_cross_run_email_merge(tmp_path, test_db):
    csv_content = "name,email,phone,current_company,title,github_url,location\nLinus Torvalds,linus@linux.org,,,https://github.com/torvalds,"
    csv_path = str(tmp_path / "run1.csv")
    with open(csv_path, "w") as f:
        f.write(csv_content)
        
    run_pipeline(csv_path=csv_path, db_path=test_db)
    
    cands_run1 = list_candidates(test_db)
    assert len(cands_run1) == 1
    linus_id = cands_run1[0]["candidate_id"]
    
    # Run 2: ATS with Email (no GitHub)
    ats_content = {
        "export_date": "2024-01-01",
        "candidates": [
            {
                "ats_record_id": "ATS-123",
                "personal": {
                    "displayName": "Linus Torvalds",
                    "contact": {"primaryEmail": "linus@linux.org"}
                }
            }
        ]
    }
    ats_path = str(tmp_path / "run2.json")
    with open(ats_path, "w") as f:
        json.dump(ats_content, f)
        
    run_pipeline(ats_path=ats_path, db_path=test_db)
    
    cands_run2 = list_candidates(test_db)
    assert len(cands_run2) == 1  # Should still be 1!
    assert cands_run2[0]["candidate_id"] == linus_id
    
    # Verify provenance accumulated
    emails_provs = [p["source"] for p in cands_run2[0]["emails"][0]["provenance"]]
    assert "recruiter.csv" in emails_provs
    assert "ats.json" in emails_provs

def test_cross_run_phone_merge(tmp_path, test_db):
    csv_content = "name,email,phone,current_company,title,github_url,location\nAyush Rathi,ayush@example.com,7249381902,,,,"
    csv_path = str(tmp_path / "ayush1.csv")
    with open(csv_path, "w") as f:
        f.write(csv_content)
        
    run_pipeline(csv_path=csv_path, db_path=test_db)
    cands_run1 = list_candidates(test_db)
    assert len(cands_run1) == 1
    ayush_id = cands_run1[0]["candidate_id"]
    
    # Run 2: Resume with phone
    ats_content = {
        "export_date": "2024-01-01",
        "candidates": [
            {
                "ats_record_id": "ATS-456",
                "personal": {
                    "displayName": "Ayush Rathi",
                    "contact": {"mobile": "+917249381902"}
                }
            }
        ]
    }
    ats_path = str(tmp_path / "ayush2.json")
    with open(ats_path, "w") as f:
        json.dump(ats_content, f)
        
    run_pipeline(ats_path=ats_path, db_path=test_db)
    
    cands_run2 = list_candidates(test_db)
    assert len(cands_run2) == 1
    assert cands_run2[0]["candidate_id"] == ayush_id

def test_bridging_conflict_detected_not_auto_merged(tmp_path, test_db):
    csv1 = "name,email,phone,current_company,title,github_url,location\nAlice,alice@test.com,1111111111,,,,"
    csv_path1 = str(tmp_path / "a.csv")
    with open(csv_path1, "w") as f:
        f.write(csv1)
    run_pipeline(csv_path=csv_path1, db_path=test_db)
    
    csv2 = "name,email,phone,current_company,title,github_url,location\nBob,bob@test.com,2222222222,,,,"
    csv_path2 = str(tmp_path / "b.csv")
    with open(csv_path2, "w") as f:
        f.write(csv2)
    run_pipeline(csv_path=csv_path2, db_path=test_db)
    
    cands_before = list_candidates(test_db)
    assert len(cands_before) == 2
    
    # New extraction bridging A (email) and B (phone)
    ats_bridge = {
        "export_date": "2024-01-01",
        "candidates": [
            {
                "ats_record_id": "ATS-BRIDGE",
                "personal": {
                    "displayName": "Alice Bob",
                    "contact": {"primaryEmail": "alice@test.com", "mobile": "2222222222"}
                }
            }
        ]
    }
    ats_path = str(tmp_path / "bridge.json")
    with open(ats_path, "w") as f:
        json.dump(ats_bridge, f)
        
    run_pipeline(ats_path=ats_path, db_path=test_db)
    
    # They should NOT be merged. Still 2 canonical candidates.
    cands_after = list_candidates(test_db)
    assert len(cands_after) == 2
    
    # Check alerts table
    with sqlite3.connect(test_db) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM identity_bridge_alerts")
        alerts = cursor.fetchall()
        assert len(alerts) == 1
        assert "exact_identifier_bridge" in alerts[0][3]

def test_single_run_still_works_without_db(tmp_path):
    csv1 = "name,email,phone,current_company,title,github_url,location\nAlice,alice@test.com,1111111111,,,,"
    csv_path1 = str(tmp_path / "a.csv")
    with open(csv_path1, "w") as f:
        f.write(csv1)
        
    res = run_pipeline(csv_path=csv_path1, db_path=None)
    assert len(res["candidates"]) == 1
