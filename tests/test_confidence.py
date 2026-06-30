"""
Tests for confidence.py
"""
from src.confidence import combine_confidence, field_confidence, overall_confidence
from src.models import Provenance, CanonicalCandidate, FieldValue

def test_combine_confidence():
    assert combine_confidence([]) == 0.0
    assert combine_confidence([0.5]) == 0.5
    assert combine_confidence([0.5, 0.5]) == 0.75

def test_field_confidence_single():
    prov = Provenance("csv", "name", "csv", 0.8)
    assert field_confidence([("Alice", prov)], "Alice") == 0.8

def test_field_confidence_agreeing():
    prov1 = Provenance("csv", "name", "csv", 0.5)
    prov2 = Provenance("api", "name", "api", 0.5)
    
    res = field_confidence([
        ("Alice", prov1),
        ("Alice", prov2)
    ], "Alice")
    assert res == 0.75

import pytest

def test_field_confidence_conflict():
    prov1 = Provenance("csv", "name", "csv", 0.8)
    prov2 = Provenance("api", "name", "api", 0.7)
    
    res = field_confidence([
        ("Alice", prov1),
        ("Bob", prov2)
    ], "Alice")
    
    assert res == pytest.approx(0.72)

def test_overall_confidence_missing_core():
    name_field = FieldValue(value="Alice", confidence=0.8, provenance=[])
    cand = CanonicalCandidate(
        candidate_id="123",
        full_name=name_field
    )
    
    # core fields: full_name (0.8), emails (0.0), phones (0.0), skills (0.0)
    # average = 0.8 / 4 = 0.2
    assert overall_confidence(cand) == 0.2

def test_overall_confidence_does_not_silently_floor_to_zero():
    cand = CanonicalCandidate(
        candidate_id="124",
        full_name=FieldValue(value="Bob", confidence=1.0, provenance=[]),
        emails=[FieldValue(value="bob@example.com", confidence=1.0, provenance=[])],
        phones=[],
        skills=[FieldValue(value="Python", confidence=0.5, provenance=[])]
    )
    
    # core fields: full_name (1.0), emails (1.0), phones (0.0), skills (0.5)
    # average = 2.5 / 4 = 0.625
    res = overall_confidence(cand)
    assert res > 0.5
    assert res == 0.625
