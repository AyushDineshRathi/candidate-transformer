"""
Tests for github_extractor.
"""
import pytest
from unittest.mock import patch, MagicMock
from requests.exceptions import Timeout
from src.extractors.github_extractor import extract_from_github

@patch("src.extractors.github_extractor.requests.get")
def test_extract_successful(mock_get):
    mock_profile_resp = MagicMock()
    mock_profile_resp.status_code = 200
    mock_profile_resp.json.return_value = {
        "name": "Linus Torvalds",
        "bio": "Creator of Linux",
        "location": "Portland, OR",
        "html_url": "https://github.com/torvalds",
        "blog": "http://torvalds-family.blogspot.com",
        "company": "Linux Foundation"
    }

    mock_repos_resp = MagicMock()
    mock_repos_resp.status_code = 200
    mock_repos_resp.json.return_value = [
        {"language": "C"},
        {"language": "C"},
        {"language": "Makefile"},
        {"language": "Python"},
        {"language": "python"},
        {"language": None},
        {"language": ""}
    ]

    mock_get.side_effect = [mock_profile_resp, mock_repos_resp]
    
    extraction = extract_from_github("torvalds")
    
    assert extraction is not None
    assert extraction.full_name[0] == "Linus Torvalds"
    assert extraction.full_name[1].confidence == 0.7
    assert extraction.headline[0] == "Creator of Linux"
    assert extraction.location[0]["city"] == "Portland, OR"
    assert extraction.links[0]["github"] == "https://github.com/torvalds"
    assert extraction.links[0]["portfolio"] == "http://torvalds-family.blogspot.com"
    assert extraction.experience[0][0]["company"] == "Linux Foundation"
    
    skills = [s[0].lower() for s in extraction.skills]
    assert len(skills) == 3
    assert "c" in skills
    assert "python" in skills
    assert "makefile" in skills
    
    assert extraction.skills[0][1].confidence == 0.5


@patch("src.extractors.github_extractor.requests.get")
def test_extract_not_found(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    mock_get.return_value = mock_resp
    
    extraction = extract_from_github("unknown_user_12345")
    assert extraction is None


@patch("src.extractors.github_extractor.requests.get")
def test_extract_no_repos(mock_get):
    mock_profile_resp = MagicMock()
    mock_profile_resp.status_code = 200
    mock_profile_resp.json.return_value = {
        "name": "Octocat"
    }
    
    mock_repos_resp = MagicMock()
    mock_repos_resp.status_code = 200
    mock_repos_resp.json.return_value = []
    
    mock_get.side_effect = [mock_profile_resp, mock_repos_resp]
    
    extraction = extract_from_github("octocat")
    assert extraction is not None
    assert extraction.full_name[0] == "Octocat"
    assert len(extraction.skills) == 0


@patch("src.extractors.github_extractor.requests.get")
def test_extract_rate_limit(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 403
    mock_resp.headers = {"X-RateLimit-Remaining": "0"}
    mock_get.return_value = mock_resp
    
    extraction = extract_from_github("octocat")
    assert extraction is None


@patch("src.extractors.github_extractor.requests.get")
def test_extract_timeout(mock_get):
    mock_get.side_effect = Timeout("Timeout occurred")
    
    extraction = extract_from_github("octocat")
    assert extraction is None
