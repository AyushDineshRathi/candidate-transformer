"""
Tests for csv_extractor.
"""
import os
import tempfile
import csv
from src.extractors.csv_extractor import extract_from_csv

def test_extract_from_csv():
    # 3-4 rows covering: a clean row, a row missing phone, a row with a malformed email, and a fully empty row
    data = [
        {
            "name": "Alice Smith", 
            "email": "alice@example.com", 
            "phone": "555-1234", 
            "current_company": "Acme", 
            "title": "Engineer", 
            "github_url": "https://github.com/alicesmith", 
            "location": "New York, USA", 
            "notes": "Great candidate"
        },
        {
            "name": "Bob Jones", 
            "email": "bob@example.com", 
            "phone": "", 
            "current_company": "Tech Corp", 
            "title": "Developer", 
            "github_url": "", 
            "location": "London", 
            "notes": ""
        },
        {
            "name": "Charlie Brown", 
            "email": "charlie_no_at_domain.com", 
            "phone": "555-5678", 
            "current_company": "", 
            "title": "", 
            "github_url": "", 
            "location": "", 
            "notes": ""
        },
        {
            "name": "", 
            "email": "", 
            "phone": "", 
            "current_company": "", 
            "title": "", 
            "github_url": "", 
            "location": "", 
            "notes": ""
        }
    ]
    
    with tempfile.NamedTemporaryFile(mode='w', delete=False, newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=list(data[0].keys()))
        writer.writeheader()
        writer.writerows(data)
        temp_path = f.name
        
    try:
        extractions = extract_from_csv(temp_path)
        
        # 3 extractions should come out (the empty one is skipped)
        assert len(extractions) == 3
        
        e1, e2, e3 = extractions
        
        # Clean row
        assert e1.full_name[0] == "Alice Smith"
        assert e1.emails[0][0] == "alice@example.com"
        assert e1.emails[0][1].confidence == 1.0
        assert e1.phones[0][0] == "555-1234"
        assert e1.experience[0][0]["company"] == "Acme"
        assert e1.links[0]["github"] == "https://github.com/alicesmith"
        assert e1.location[0]["city"] == "New York"
        assert e1.location[0]["country"] == "USA"
        
        # Row missing phone
        assert e2.full_name[0] == "Bob Jones"
        assert len(e2.phones) == 0
        assert e2.location[0]["city"] == "London"
        assert e2.location[0]["country"] is None
        
        # Row with malformed email
        assert e3.full_name[0] == "Charlie Brown"
        assert e3.emails[0][0] == "charlie_no_at_domain.com"
        assert e3.emails[0][1].confidence == 0.4
        
    finally:
        os.remove(temp_path)

def test_extract_missing_file():
    # Should not crash, should return empty list
    extractions = extract_from_csv("non_existent_file_12345.csv")
    assert extractions == []
