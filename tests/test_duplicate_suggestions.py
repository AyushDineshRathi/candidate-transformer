import pytest
from unittest.mock import patch
from src.models import CanonicalCandidate, FieldValue
from src.duplicate_suggestions import find_possible_duplicates

def test_find_possible_duplicates_above_threshold():
    # Similar name (token_sort_ratio handles minor diffs) + shared company (weight 0.4 + 0.3 = 0.7 > 0.6)
    cand1 = CanonicalCandidate(
        candidate_id="1",
        full_name=FieldValue(value="Johnathan Doe", confidence=1.0),
        experience=[{"company": "Google", "title": "SWE"}]
    )
    cand2 = CanonicalCandidate(
        candidate_id="2",
        full_name=FieldValue(value="Jonathan Doe", confidence=1.0),
        experience=[{"company": "Google", "title": "Software Engineer"}]
    )
    
    with patch('src.storage.upsert_candidate') as mock_upsert:
        suggestions = find_possible_duplicates([cand1, cand2])
        
        # Verify it doesn't write to DB
        mock_upsert.assert_not_called()
        
    assert len(suggestions) == 1
    s = suggestions[0]
    assert s["candidate_a_id"] == "1"
    assert s["candidate_b_id"] == "2"
    assert s["similarity_score"] >= 0.6
    
    signals = " ".join(s["matching_signals"])
    assert "name similarity" in signals
    assert "shared company (google)" in signals

def test_find_possible_duplicates_below_threshold():
    # Similar name ONLY (weight 0.4 < 0.6)
    cand1 = CanonicalCandidate(
        candidate_id="1",
        full_name=FieldValue(value="Jane Smith", confidence=1.0),
        experience=[{"company": "Microsoft", "title": "SWE"}]
    )
    cand2 = CanonicalCandidate(
        candidate_id="2",
        full_name=FieldValue(value="Jane Smith", confidence=1.0),
        experience=[{"company": "Apple", "title": "PM"}]
    )
    
    with patch('src.storage.upsert_candidate') as mock_upsert:
        suggestions = find_possible_duplicates([cand1, cand2])
        
        # Verify it doesn't write to DB
        mock_upsert.assert_not_called()
        
    # Should not trigger suggestion since 0.4 < 0.6
    assert len(suggestions) == 0
