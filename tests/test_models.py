import json
from src.models import CanonicalCandidate, FieldValue, Provenance


def test_canonical_candidate_to_dict():
    prov = Provenance(source="csv", source_field="Name", method="direct", confidence=1.0)
    name_field = FieldValue(value="John Doe", confidence=0.9, provenance=[prov])
    candidate = CanonicalCandidate(
        candidate_id="c-123",
        full_name=name_field
    )
    
    d = candidate.to_dict()
    assert d["candidate_id"] == "c-123"
    assert d["full_name"]["value"] == "John Doe"
    assert d["full_name"]["confidence"] == 0.9
    assert d["full_name"]["provenance"][0]["source"] == "csv"


def test_json_serialization():
    prov = Provenance(source="github", source_field="email", method="api", confidence=0.8)
    email_field = FieldValue(value="john@example.com", confidence=0.8, provenance=[prov])
    candidate = CanonicalCandidate(
        candidate_id="c-456",
        emails=[email_field],
        links={"linkedin": "linkedin.com/in/johndoe", "github": "github.com/johndoe", "portfolio": None, "other": []}
    )
    
    d = candidate.to_dict()
    json_str = json.dumps(d)
    recovered = json.loads(json_str)
    
    assert recovered["candidate_id"] == "c-456"
    assert recovered["emails"][0]["value"] == "john@example.com"
    assert recovered["links"]["linkedin"] == "linkedin.com/in/johndoe"


def test_complex_fields_serialization():
    exp = {
        "company": "Acme Corp",
        "title": "Software Engineer",
        "start": "2020",
        "end": "2023",
        "summary": "Did things"
    }
    edu = {
        "institution": "University of Tech",
        "degree": "B.S.",
        "field": "Computer Science",
        "end_year": "2020"
    }
    candidate = CanonicalCandidate(
        candidate_id="c-789",
        experience=[exp],
        education=[edu],
        overall_confidence=0.95
    )
    
    d = candidate.to_dict()
    assert len(d["experience"]) == 1
    assert d["experience"][0]["company"] == "Acme Corp"
    assert len(d["education"]) == 1
    assert d["education"][0]["degree"] == "B.S."
    
    json_str = json.dumps(d)
    assert "Acme Corp" in json_str
    assert "University of Tech" in json_str
