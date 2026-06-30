"""
Tests for SQLite storage layer.
"""
import sqlite3
import pytest
from src.models import CanonicalCandidate, FieldValue
from src.storage import init_db, upsert_candidate, get_candidate, list_candidates, search_by_skill, full_text_search

@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "test.sqlite3"
    return str(path)

def test_init_db(db_path):
    init_db(db_path)
    # Check tables created
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}
        assert "candidates" in tables
        assert "candidate_skills" in tables

def test_upsert_and_get(db_path):
    init_db(db_path)
    
    cand = CanonicalCandidate(
        candidate_id="test-1",
        full_name=FieldValue("Alice", 1.0),
        skills=[FieldValue("Python", 1.0), FieldValue("Java", 0.9)],
        overall_confidence=0.8
    )
    
    upsert_candidate(db_path, cand)
    
    retrieved = get_candidate(db_path, "test-1")
    assert retrieved is not None
    assert retrieved["candidate_id"] == "test-1"
    assert retrieved["full_name"]["value"] == "Alice"
    assert retrieved["overall_confidence"] == 0.8
    assert len(retrieved["skills"]) == 2
    
def test_upsert_idempotent(db_path):
    init_db(db_path)
    
    cand = CanonicalCandidate(
        candidate_id="test-2",
        full_name=FieldValue("Bob", 1.0),
        skills=[FieldValue("C++", 1.0)]
    )
    
    upsert_candidate(db_path, cand)
    upsert_candidate(db_path, cand) # Second time
    
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM candidates")
        assert cursor.fetchone()[0] == 1
        
        cursor.execute("SELECT COUNT(*) FROM candidate_skills")
        assert cursor.fetchone()[0] == 1

def test_search_by_skill(db_path):
    init_db(db_path)
    
    cand1 = CanonicalCandidate(
        candidate_id="test-1",
        full_name=FieldValue("Alice", 1.0),
        skills=[FieldValue("Python", 1.0), FieldValue("Java", 0.9)]
    )
    cand2 = CanonicalCandidate(
        candidate_id="test-2",
        full_name=FieldValue("Bob", 1.0),
        skills=[FieldValue("Python", 1.0), FieldValue("C++", 1.0)]
    )
    cand3 = CanonicalCandidate(
        candidate_id="test-3",
        full_name=FieldValue("Charlie", 1.0),
        skills=[FieldValue("Go", 1.0)]
    )
    
    upsert_candidate(db_path, cand1)
    upsert_candidate(db_path, cand2)
    upsert_candidate(db_path, cand3)
    
    # Case insensitive
    python_devs = search_by_skill(db_path, "pYtHoN")
    assert len(python_devs) == 2
    names = {d["full_name"]["value"] for d in python_devs}
    assert names == {"Alice", "Bob"}
    
    go_devs = search_by_skill(db_path, "go")
    assert len(go_devs) == 1
    assert go_devs[0]["full_name"]["value"] == "Charlie"
    
    # Not found
    rust_devs = search_by_skill(db_path, "rust")
    assert len(rust_devs) == 0

def test_list_candidates_filtered(db_path):
    init_db(db_path)
    
    cand1 = CanonicalCandidate(candidate_id="test-1", overall_confidence=0.9)
    cand2 = CanonicalCandidate(candidate_id="test-2", overall_confidence=0.5)
    
    upsert_candidate(db_path, cand1)
    upsert_candidate(db_path, cand2)
    
    all_cands = list_candidates(db_path)
    assert len(all_cands) == 2
    
    high_conf = list_candidates(db_path, min_confidence=0.8)
    assert len(high_conf) == 1
    assert high_conf[0]["candidate_id"] == "test-1"

def test_full_text_search(db_path):
    init_db(db_path)
    
    cand1 = CanonicalCandidate(
        candidate_id="test-1",
        full_name=FieldValue("Alice Hacker", 1.0),
        headline=FieldValue("Senior Kernel Engineer", 1.0),
        experience=[{"company": "Linux Foundation", "title": "Maintainer"}],
        skills=[FieldValue("C", 1.0)]
    )
    cand2 = CanonicalCandidate(
        candidate_id="test-2",
        full_name=FieldValue("Bob Frontend", 1.0),
        headline=FieldValue("React Developer", 1.0),
        skills=[FieldValue("JavaScript", 1.0)]
    )
    
    upsert_candidate(db_path, cand1)
    upsert_candidate(db_path, cand2)
    
    # Matching query
    results = full_text_search(db_path, "kernel")
    assert len(results) == 1
    assert results[0]["full_name"]["value"] == "Alice Hacker"
    
    # Matches multiple fields across name and experience
    results2 = full_text_search(db_path, "alice linux")
    assert len(results2) == 1
    
    # Doesn't match
    results3 = full_text_search(db_path, "missingword")
    assert len(results3) == 0
    
    # Syntax error in FTS5 query should not crash but return empty
    results4 = full_text_search(db_path, "linux OR OR")
    assert len(results4) == 0
