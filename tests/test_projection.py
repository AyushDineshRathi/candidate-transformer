"""
Tests for projection module.
"""
import pytest
from src.projection import project, project_default, ProjectionError
from src.models import CanonicalCandidate, FieldValue, Provenance

def get_candidate():
    return CanonicalCandidate(
        candidate_id="c-1",
        full_name=FieldValue(value="Alice", confidence=0.9, provenance=[]),
        emails=[FieldValue(value="alice@example.com", confidence=0.8, provenance=[])],
        phones=[],
        skills=[FieldValue(value="js", confidence=0.7, provenance=[])]
    )

def test_project_default():
    c = get_candidate()
    out = project_default(c)
    assert out["candidate_id"] == "c-1"
    assert out["full_name"]["value"] == "Alice"

def test_project_config_subset():
    c = get_candidate()
    config = {
        "fields": [
            {"path": "name", "from": "full_name.value"},
            {"path": "email", "from": "emails[0].value"}
        ],
        "on_missing": "omit"
    }
    out = project(c, config)
    assert out == {"name": "Alice", "email": "alice@example.com"}

def test_project_missing_omit():
    c = get_candidate()
    config = {
        "fields": [
            {"path": "name", "from": "full_name.value", "required": True},
            {"path": "phone", "from": "phones[0].value", "required": True}
        ],
        "on_missing": "omit"
    }
    out = project(c, config)
    assert "phone" not in out
    assert out["name"] == "Alice"
    
def test_project_missing_error():
    c = get_candidate()
    config = {
        "fields": [
            {"path": "phone", "from": "phones[0].value", "required": True}
        ],
        "on_missing": "error"
    }
    with pytest.raises(ProjectionError):
        project(c, config)

def test_project_missing_not_required_fallback():
    c = get_candidate()
    config = {
        "fields": [
            {"path": "phone", "from": "phones[0].value", "required": False}
        ],
        "on_missing": "error"
    }
    # Should fall back to null
    out = project(c, config)
    assert out["phone"] is None

def test_project_array_and_normalize():
    c = get_candidate()
    config = {
        "fields": [
            {"path": "skills", "from": "skills[].value", "normalize": "canonical"}
        ]
    }
    out = project(c, config)
    assert out["skills"] == ["JavaScript"]
    
def test_project_confidence_sibling():
    c = get_candidate()
    config = {
        "fields": [
            {"path": "name", "from": "full_name.value"}
        ],
        "include_confidence": True
    }
    out = project(c, config)
    assert out["name"] == "Alice"
    assert out["name_confidence"] == 0.9
