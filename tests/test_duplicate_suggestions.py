import pytest
from unittest.mock import patch
from src.models import CanonicalCandidate, FieldValue
from src.duplicate_suggestions import find_possible_duplicates

def test_find_possible_duplicates_above_threshold():
    # Similar name (token_sort_ratio handles minor diffs) + shared company (weight 0.4 + 0.3*0.5 = 0.55) + shared skill (0.15*0.5 = 0.075) = 0.625 > 0.6
    cand1 = CanonicalCandidate(
        candidate_id="1",
        full_name=FieldValue(value="Johnathan Doe", confidence=1.0),
        experience=[{"company": "Google", "title": "SWE"}],
        skills=[FieldValue(value="Java", confidence=1.0)]
    )
    cand2 = CanonicalCandidate(
        candidate_id="2",
        full_name=FieldValue(value="Jonathan Doe", confidence=1.0),
        experience=[{"company": "Google", "title": "Software Engineer"}],
        skills=[FieldValue(value="Java", confidence=1.0)]
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
    assert "shared company: google" in signals
    assert "shared skill: Java" in signals

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

def test_generic_shared_attributes_do_not_inflate_score():
    pool = []
    for i in range(10):
        pool.append(
            CanonicalCandidate(
                candidate_id=f"dummy_{i}",
                full_name=FieldValue(value=f"Dummy User {i}", confidence=1.0),
                experience=[{"company": "student", "title": "student"}],
                location=FieldValue(value={"country": "US"}, confidence=1.0),
                skills=[FieldValue(value="Python", confidence=1.0)]
            )
        )
    
    cand_a = CanonicalCandidate(
        candidate_id="ayush_1",
        full_name=FieldValue(value="Ayush Rathi", confidence=1.0),
        experience=[{"company": "student", "title": "student"}],
        location=FieldValue(value={"country": "US"}, confidence=1.0),
        skills=[FieldValue(value="Python", confidence=1.0)]
    )
    cand_b = CanonicalCandidate(
        candidate_id="abhijeet_1",
        full_name=FieldValue(value="Abhijeet Waghmare", confidence=1.0),
        experience=[{"company": "student", "title": "student"}],
        location=FieldValue(value={"country": "US"}, confidence=1.0),
        skills=[FieldValue(value="Python", confidence=1.0)]
    )
    
    pool.extend([cand_a, cand_b])
    
    suggestions = find_possible_duplicates(pool)
    
    ayush_abhijeet = [s for s in suggestions if {s["candidate_a_id"], s["candidate_b_id"]} == {"ayush_1", "abhijeet_1"}]
    assert len(ayush_abhijeet) == 0

def test_rare_shared_attributes_still_flag_correctly():
    pool = []
    for i in range(10):
        pool.append(
            CanonicalCandidate(
                candidate_id=f"dummy_{i}",
                full_name=FieldValue(value=f"Dummy User {i}", confidence=1.0),
                experience=[{"company": f"Generic Corp {i}", "title": "SWE"}]
            )
        )
        
    cand_a = CanonicalCandidate(
        candidate_id="rare_1",
        full_name=FieldValue(value="Johnathan Doe", confidence=1.0),
        experience=[{"company": "Eightfold AI", "title": "SWE"}],
        skills=[FieldValue(value="Go", confidence=1.0)]
    )
    cand_b = CanonicalCandidate(
        candidate_id="rare_2",
        full_name=FieldValue(value="Jonathan Doe", confidence=1.0),
        experience=[{"company": "Eightfold AI", "title": "SWE"}],
        skills=[FieldValue(value="Go", confidence=1.0)]
    )
    
    pool.extend([cand_a, cand_b])
    
    suggestions = find_possible_duplicates(pool)
    
    rare_sug = [s for s in suggestions if {s["candidate_a_id"], s["candidate_b_id"]} == {"rare_1", "rare_2"}]
    assert len(rare_sug) == 1
    assert rare_sug[0]["similarity_score"] > 0.6

def test_stoplist_values_never_contribute():
    cand_a = CanonicalCandidate(
        candidate_id="stop_1",
        full_name=FieldValue(value="Alice Smith", confidence=1.0),
        experience=[{"company": "unemployed", "title": "none"}]
    )
    cand_b = CanonicalCandidate(
        candidate_id="stop_2",
        full_name=FieldValue(value="Bob Jones", confidence=1.0),
        experience=[{"company": "unemployed", "title": "none"}]
    )
    
    suggestions = find_possible_duplicates([cand_a, cand_b])
    assert len(suggestions) == 0
