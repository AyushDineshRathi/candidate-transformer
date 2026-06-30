import os
import json
import sys
from unittest.mock import patch
import requests

# Adjust path so we can import from src
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.pipeline import run_pipeline

def mock_requests_get(url, *args, **kwargs):
    with open("tests/gold_eval/gold_input/gold_github_mocks.json", "r") as f:
        mocks = json.load(f)
        
    class MockResponse:
        def __init__(self, json_data, status_code):
            self.json_data = json_data
            self.status_code = status_code
            self.headers = {}
            self.text = json.dumps(json_data)
            
        def json(self):
            return self.json_data
            
        def raise_for_status(self):
            if self.status_code >= 400:
                raise requests.RequestException(f"Error {self.status_code}")
                
    if url in mocks:
        m = mocks[url]
        return MockResponse(m["json"], m["status"])
    return MockResponse({}, 404)

def run_eval():
    print("Running Gold-Set Evaluation...")
    
    csv_path = "tests/gold_eval/gold_input/gold_csv.csv"
    ats_path = "tests/gold_eval/gold_input/gold_ats.json"
    expected_path = "tests/gold_eval/gold_expected.json"
    
    # We will use an in-memory DB or temporary DB just in case, but pipeline returns results.
    with patch("requests.get", side_effect=mock_requests_get):
        pipeline_output = run_pipeline(
            csv_path=csv_path,
            ats_path=ats_path,
            db_path=None
        )
        
    actual_candidates = pipeline_output["candidates"]
    
    if not os.path.exists(expected_path):
        print(f"Expected path {expected_path} not found. Dumping actual output to it for manual review.")
        with open(expected_path, "w", encoding="utf-8") as f:
            json.dump([c["output"] for c in actual_candidates], f, indent=2)
        print("Please review and hand-verify the gold expected file.")
        return
        
    with open(expected_path, "r", encoding="utf-8") as f:
        expected_candidates = json.load(f)
        
    # Build maps by some stable key, e.g., emails[0] or github
    def get_key(cand_dict):
        if cand_dict.get("emails") and len(cand_dict["emails"]) > 0:
            return cand_dict["emails"][0].get("value")
        if cand_dict.get("full_name") and isinstance(cand_dict["full_name"], dict):
            return cand_dict["full_name"].get("value")
        return "UNKNOWN"
        
    actual_map = {get_key(c["output"]): c["output"] for c in actual_candidates}
    expected_map = {get_key(c): c for c in expected_candidates}
    
    # Entity Resolution Accuracy
    actual_keys = set(actual_map.keys())
    expected_keys = set(expected_map.keys())
    
    correct_entities = actual_keys.intersection(expected_keys)
    entity_accuracy = (len(correct_entities) / max(len(expected_keys), 1)) * 100
    
    print(f"Entity Resolution Accuracy: {entity_accuracy:.1f}%")
    
    if actual_keys != expected_keys:
        print(f"  Missing entities: {expected_keys - actual_keys}")
        print(f"  Extra entities: {actual_keys - expected_keys}")
        
    # Field Accuracy
    total_fields = 0
    correct_fields = 0
    
    for key in correct_entities:
        expected = expected_map[key]
        actual = actual_map[key]
        
        print(f"\n--- Candidate: {key} ---")
        passed = True
        
        fields_to_check = ["full_name", "emails", "phones", "location", "skills", "experience", "education", "links"]
        for f in fields_to_check:
            total_fields += 1
            if actual.get(f) == expected.get(f):
                correct_fields += 1
            else:
                passed = False
                print(f"  FAIL: field '{f}' - expected {expected.get(f)}, got {actual.get(f)}")
                
        if passed:
            print("  PASS")
            
    field_accuracy = (correct_fields / max(total_fields, 1)) * 100
    print(f"\nField Accuracy: {field_accuracy:.1f}%")

if __name__ == "__main__":
    run_eval()
