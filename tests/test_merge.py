"""
Tests for merge logic.
"""
from src.models import RawExtraction, Provenance
from src.merge import merge_candidates, resolve_field, cluster_extractions

def test_merge_same_person_github():
    e1 = RawExtraction(candidate_id="1")
    e1.links = ({"github": "https://github.com/torvalds"}, Provenance("recruiter.csv", "github_url", "csv", 1.0))
    e1.full_name = ("Linus Torvalds CSV", Provenance("recruiter.csv", "name", "csv", 1.0))
    
    e2 = RawExtraction(candidate_id="2")
    e2.links = ({"github": "https://github.com/torvalds"}, Provenance("github_api", "html_url", "api", 0.7))
    e2.full_name = ("Linus Torvalds GitHub", Provenance("github_api", "name", "api", 0.7))
    
    candidates = merge_candidates([e1, e2])
    
    assert len(candidates) == 1
    assert candidates[0].full_name.value == "Linus Torvalds CSV"
    assert "Linus Torvalds GitHub" in candidates[0].full_name.conflicting_values
    assert len(candidates[0].full_name.provenance) == 2
    
def test_merge_different_person():
    e1 = RawExtraction(candidate_id="1")
    e1.emails = [("alice@example.com", Provenance("csv", "email", "csv", 1.0))]
    
    e2 = RawExtraction(candidate_id="2")
    e2.emails = [("bob@example.com", Provenance("csv", "email", "csv", 1.0))]
    
    candidates = merge_candidates([e1, e2])
    assert len(candidates) == 2

def test_conflict_resolution():
    prov_csv = Provenance("recruiter.csv", "company", "csv", 1.0)
    prov_gh = Provenance("github_api", "company", "api", 0.7)
    
    values = [
        ("Startup Inc", prov_gh),
        ("Big Corp", prov_csv) 
    ]
    
    res = resolve_field(values, "headline") 
    assert res.value == "Big Corp"
    assert "Startup Inc" in res.conflicting_values

def test_list_field_union():
    prov1 = Provenance("recruiter.csv", "email", "csv", 1.0)
    prov2 = Provenance("github_api", "email", "api", 0.7)
    
    values = [
        ("alice@example.com", prov1),
        ("alice.personal@gmail.com", prov2)
    ]
    
    res = resolve_field(values, "emails")
    assert len(res) == 2
    assert {r.value for r in res} == {"alice@example.com", "alice.personal@gmail.com"}

def test_skills_merge():
    prov1 = Provenance("recruiter.csv", "skill", "csv", 1.0)
    prov2 = Provenance("github_api", "skill", "api", 0.5)
    
    values = [
        ("Python", prov1),
        ("Python", prov2)
    ]
    
    res = resolve_field(values, "skills")
    assert len(res) == 1
    assert res[0].value == "Python"
    assert len(res[0].provenance) == 2
