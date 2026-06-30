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
    conflict = candidates[0].full_name.conflicting_values[0]
    assert conflict["value"] == "Linus Torvalds GitHub"
    assert conflict["source"] == "github_api"
    assert conflict["confidence"] == 0.7
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
    conflict = res.conflicting_values[0]
    assert conflict["value"] == "Startup Inc"
    assert conflict["source"] == "github_api"
    assert conflict["confidence"] == 0.7

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

def test_conflicting_values_consistent_shape():
    prov_csv = Provenance("recruiter.csv", "name", "csv", 1.0)
    prov_gh = Provenance("github_api", "name", "api", 0.7)
    
    # Scalar string
    res_str = resolve_field([("Alice", prov_csv), ("Bob", prov_gh)], "full_name")
    assert len(res_str.conflicting_values) == 1
    assert res_str.conflicting_values[0] == {"value": "Bob", "source": "github_api", "confidence": 0.7}
    
    # Dict field (location)
    loc_csv = {"city": "Portland, OR"}
    loc_gh = {"city": "Portland"}
    res_dict = resolve_field([(loc_csv, prov_csv), (loc_gh, prov_gh)], "location")
    assert len(res_dict.conflicting_values) == 1
    assert res_dict.conflicting_values[0] == {"value": loc_gh, "source": "github_api", "confidence": 0.7}

def test_disagreement_applies_confidence_penalty():
    prov_csv = Provenance("recruiter.csv", "name", "csv", 1.0)
    prov_gh = Provenance("github_api", "name", "api", 0.7)
    
    # With conflict
    values_with_conflict = [("Alice", prov_csv), ("Bob", prov_gh)]
    res_with = resolve_field(values_with_conflict, "full_name")
    
    # Without conflict
    values_without = [("Alice", prov_csv)]
    res_without = resolve_field(values_without, "full_name")
    
    assert res_with.confidence < res_without.confidence

def test_phone_match_merges_candidates_with_no_shared_email_or_github():
    e1 = RawExtraction(candidate_id="1")
    e1.full_name = ("Ayush Rathi", Provenance("csv", "name", "csv", 1.0))
    e1.emails = [("ayush@example.com", Provenance("csv", "email", "csv", 1.0))]
    e1.phones = [("+91 7249381902", Provenance("csv", "phone", "csv", 1.0))]
    
    e2 = RawExtraction(candidate_id="2")
    e2.full_name = ("Ayush Rathi", Provenance("resume", "name", "regex", 0.6))
    e2.phones = [("7249381902", Provenance("resume", "phone", "regex", 0.6))]
    
    candidates = cluster_extractions([e1, e2])
    assert len(candidates) == 1
    
    merged = merge_candidates([e1, e2])
    assert len(merged) == 1
    assert merged[0].full_name.value == "Ayush Rathi"
    
    phones = [p.value for p in merged[0].phones]
    assert "+91 7249381902" in phones
