"""
Tests for normalizers.
"""
from src.normalizers import (
    normalize_phone,
    normalize_date,
    normalize_country,
    normalize_location,
    normalize_skill,
    normalize_name
)

def test_normalize_phone():
    assert normalize_phone("+1 415 555 2671") == "+14155552671"
    assert normalize_phone("invalid phone") is None
    assert normalize_phone("") is None
    assert normalize_phone(None) is None

def test_normalize_date():
    assert normalize_date("Jan 2025") == "2025-01"
    assert normalize_date("2025-01") == "2025-01"
    assert normalize_date("01/2025") == "2025-01"
    assert normalize_date("January 2025") == "2025-01"
    assert normalize_date("invalid date") is None
    assert normalize_date("") is None
    assert normalize_date(None) is None

def test_normalize_country():
    assert normalize_country("USA") == "US"
    assert normalize_country("United States") == "US"
    assert normalize_country("India") == "IN"
    assert normalize_country("Canada") == "CA"
    assert normalize_country("GarbageCountryName") is None
    assert normalize_country("") is None
    assert normalize_country(None) is None

def test_normalize_location():
    # Valid Cases string
    assert normalize_location("San Francisco, CA, USA") == {"city": "San Francisco", "region": "CA", "country": "US"}
    assert normalize_location("Bangalore, India") == {"city": "Bangalore", "region": None, "country": "IN"}
    assert normalize_location("London") == {"city": "London", "region": None, "country": None}
    assert normalize_location("United States") == {"city": "United States", "region": None, "country": None}
    
    # Dict input
    assert normalize_location({"city": " Austin ", "region": "TX", "country": "usa"}) == {"city": "Austin", "region": "TX", "country": "US"}
    
    # Garbage input
    assert normalize_location("") == {"city": None, "region": None, "country": None}
    assert normalize_location(None) == {"city": None, "region": None, "country": None}

def test_normalize_skill():
    assert normalize_skill("js") == "JavaScript"
    assert normalize_skill("react.js") == "React"
    assert normalize_skill("GOLANG") == "Go"
    assert normalize_skill("unknown_skill") == "Unknown_Skill"
    assert normalize_skill("") == ""
    assert normalize_skill(None) == ""

def test_normalize_name():
    assert normalize_name("  John   Doe  ") == "John Doe"
    assert normalize_name("O'Brien") == "O'Brien"
    assert normalize_name("DeShawn") == "DeShawn"
    assert normalize_name("") == ""
    assert normalize_name(None) == ""

from src.normalizers import SkillCanonicalizer

def test_skill_canonicalizer():
    canonicalizer = SkillCanonicalizer()
    
    # Exact match from taxonomy
    canon, path = canonicalizer.normalize("react.js")
    assert canon == "React"
    assert path == "exact_alias"
    
    # Fuzzy match (react js should fuzzy match the canonical "React")
    canon, path = canonicalizer.normalize("React JS")
    assert canon == "React"
    assert path == "fuzzy_match"
    
    # Title-Case fallback (never seen before)
    canon, path = canonicalizer.normalize("Redux")
    assert canon == "Redux"
    assert path == "title_case_fallback"
    
    # Near-miss below threshold (React and Redux)
    # Even if "React" is in seen canonicals, "Redux" should not fuzzy match "React"
    # Wait, "Redux" was just added to seen_canonical above. Let's try something else.
    canon, path = canonicalizer.normalize("Reacta") 
    # Token sort ratio between 'Reacta' and 'React' is 90.9, which is > 90!
    # So "Reacta" will fuzzy match "React".
    # We need a near-miss BELOW 90. 
    # "Redux" vs "React" ratio is 40.0. Let's test "Redux" again after "React" is known.
    
    canonicalizer = SkillCanonicalizer()
    canonicalizer.normalize("react.js") # establishes "React"
    canon, path = canonicalizer.normalize("Redux")
    assert canon == "Redux"
    assert path == "title_case_fallback" # NOT fuzzy match to React
    
    # Test confidence penalty logic (simulating pipeline.py)
    from src.models import Provenance
    import dataclasses
    prov = Provenance(source="test", source_field="skills", method="test", confidence=1.0)
    
    canon, path = canonicalizer.normalize("React JS")
    if path == "fuzzy_match":
        prov = dataclasses.replace(prov, confidence=prov.confidence * 0.95)
    
    assert prov.confidence == 0.95
    assert path == "fuzzy_match"
