"""
Tests for explainability module.
"""
from src.explain import explain_to_review_flag, explain_candidate

def test_explain_to_review_flag():
    # High confidence, no missing fields
    good = {
        "overall_confidence": 0.8,
        "full_name": {"value": "Alice"},
        "emails": [{"value": "alice@example.com"}],
        "phones": [{"value": "123-456-7890"}]
    }
    assert not explain_to_review_flag(good)
    
    # Low confidence
    low_conf = dict(good)
    low_conf["overall_confidence"] = 0.4
    assert explain_to_review_flag(low_conf)
    
    # Missing full name
    no_name = dict(good)
    no_name["full_name"] = None
    assert explain_to_review_flag(no_name)
    
    # Missing emails
    no_emails = dict(good)
    no_emails["emails"] = []
    assert explain_to_review_flag(no_emails)

def test_explain_candidate_high_confidence():
    cand = {
        "overall_confidence": 0.87,
        "full_name": {
            "value": "Linus Torvalds",
            "confidence": 1.0,
            "provenance": [
                {"source": "recruiter.csv", "confidence": 1.0},
                {"source": "github_api", "confidence": 0.7}
            ]
        },
        "emails": [
            {
                "value": "linus@linux.org",
                "confidence": 1.0,
                "provenance": [{"source": "recruiter.csv", "confidence": 1.0}]
            }
        ],
        "location": {
            "value": {"city": "Portland", "country": "US"},
            "confidence": 0.9,
            "conflicting_values": [{"value": {"city": "Portland", "state": "OR"}, "source": "github_api"}]
        },
        "skills": [
            {"value": "C", "confidence": 0.5, "provenance": [{"source": "github_api"}]},
            {"value": "C++", "confidence": 0.5, "provenance": [{"source": "github_api"}]}
        ],
        "phones": [{"value": "123"}]
    }
    
    output = explain_candidate(cand)
    assert "Candidate: Linus Torvalds (confidence: 0.87)" in output
    assert "agreed by recruiter.csv (1.00) and github_api (0.70)" in output
    assert "from recruiter.csv (1.00) only" in output
    assert "penalized: conflicting value" in output
    assert "Portland, US" in output
    assert "all derived from github_api repo languages" in output
    assert "no flags" in output
    assert "FLAGGED FOR REVIEW" not in output

def test_explain_candidate_flagged():
    cand = {
        "overall_confidence": 0.31,
        "full_name": {
            "value": "Ghost",
            "confidence": 0.4
        },
        # missing emails entirely
    }
    
    output = explain_candidate(cand)
    assert "FLAGGED FOR REVIEW" in output
    assert "missing: emails" in output
