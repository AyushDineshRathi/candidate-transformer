"""
Tests for validation module.
"""
from src.validation import validate_against_schema, validate_pipeline_output

schema = {
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["candidates"],
  "properties": {
    "candidates": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["candidate_id", "phone"],
        "properties": {
          "candidate_id": { "type": "string" },
          "phone": { 
            "type": "object",
            "properties": {
                "value": { "type": "string", "pattern": "^\\+?[1-9]\\d{1,14}$" }
            }
          }
        }
      }
    }
  }
}

def test_validation_valid():
    output = {"candidates": [{"candidate_id": "c-1", "phone": {"value": "+1234567890"}}]}
    res = validate_pipeline_output(output, schema)
    assert res["valid"] is True
    assert len(res["errors"]) == 0

def test_validation_malformed_phone():
    output = {"candidates": [{"candidate_id": "c-1", "phone": {"value": "not-a-phone"}}]}
    res = validate_pipeline_output(output, schema)
    assert res["valid"] is False
    assert len(res["errors"]) > 0
    assert "phone" in res["errors"][0]

def test_validation_missing_required():
    output = {"candidates": [{"candidate_id": "c-1"}]}
    res = validate_pipeline_output(output, schema)
    assert res["valid"] is False
    assert len(res["errors"]) > 0
    assert "phone" in res["errors"][0]
