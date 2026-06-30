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

def test_explain_candidate_with_duplicates():
    # Setup candidate with duplicate
    cand_a = {
        "candidate_id": "1",
        "overall_confidence": 0.8,
        "full_name": {"value": "Ayush Rathi", "confidence": 1.0},
        "experience": [{"company": "student", "title": "student"}],
        "emails": [{"value": "a@example.com", "confidence": 1.0}],
        "phones": [{"value": "123", "confidence": 1.0}],
        "skills": [{"value": "Rare Skill", "confidence": 1.0}]
    }
    cand_b = {
        "candidate_id": "2",
        "overall_confidence": 0.8,
        "full_name": {"value": "Abhijeet Waghmare", "confidence": 1.0},
        "experience": [{"company": "student", "title": "student"}],
        "emails": [{"value": "b@example.com", "confidence": 1.0}],
        "phones": [{"value": "456", "confidence": 1.0}]
    }
    
    # Fill in the rest of the pool with 10 dummy candidates to trigger the informativeness penalty
    pool = [cand_a, cand_b]
    for i in range(10):
        pool.append({
            "candidate_id": f"dummy_{i}",
            "overall_confidence": 0.8,
            "full_name": {"value": f"Dummy User {i}", "confidence": 1.0},
            "experience": [{"company": "student", "title": "student"}],
            "emails": [{"value": f"dummy{i}@example.com", "confidence": 1.0}],
            "phones": [{"value": f"999{i}", "confidence": 1.0}]
        })
        
    cand_c = dict(cand_b)
    cand_c["candidate_id"] = "3"
    cand_c["full_name"] = {"value": "Ayush Rath", "confidence": 1.0} # Similar name
    cand_c["skills"] = [{"value": "Rare Skill", "confidence": 1.0}] # Shared rare skill adds 0.075
    
    pool.append(cand_c)
    
    # Testing near miss (cand_a vs cand_c)
    output_a = explain_candidate(cand_a, pool)
    
    assert "Possible duplicate of \"Ayush Rath\"" in output_a
    assert "below review threshold after informativeness discount" in output_a
    
    # Testing flagged duplicate
    cand_d = dict(cand_a)
    cand_d["candidate_id"] = "4"
    cand_d["full_name"] = {"value": "Ayush Rathi", "confidence": 1.0} # Exact name (0.4 score)
    cand_d["experience"] = [{"company": "Rare Corp", "title": "student"}] # Rare company (0.3 score)
    
    cand_e = dict(cand_d)
    cand_e["candidate_id"] = "5"
    cand_e["emails"] = [{"value": "e@example.com", "confidence": 1.0}]
    
    pool_2 = [cand_d, cand_e]
    output_d = explain_candidate(cand_d, pool_2)
    
    assert "Possible duplicate of \"Ayush Rathi\"" in output_d
    assert "flagged for review" in output_d
