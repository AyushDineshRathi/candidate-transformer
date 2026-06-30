"""
End-to-end integration tests for the full pipeline.
"""
import json
import pytest
from unittest.mock import patch, MagicMock

from src.pipeline import run_pipeline

@pytest.fixture
def temp_csv(tmp_path):
    def _create_csv(content):
        p = tmp_path / "test.csv"
        p.write_text(content, encoding="utf-8")
        return str(p)
    return _create_csv

@patch("src.extractors.github_extractor.requests.get")
def test_pipeline_no_github_url(mock_get, temp_csv):
    """A CSV row with no github_url at all (GitHub-only path skipped, candidate still produced)."""
    csv_content = "name,email,github_url\nJohn Doe,john@example.com,\n"
    csv_path = temp_csv(csv_content)
    
    results = run_pipeline(csv_path)
    
    mock_get.assert_not_called()
    
    candidates = results["candidates"]
    stats = results["stats"]
    assert len(candidates) == 1
    assert stats["processed"] == 1
    assert stats["merged"] == 1
    
    out = candidates[0]["output"]
    assert out["full_name"]["value"] == "John Doe"
    assert out["emails"][0]["value"] == "john@example.com"

@patch("src.extractors.github_extractor.requests.get")
def test_pipeline_github_404(mock_get, temp_csv):
    """A CSV row whose github_url points to a username that returns 404 -> candidate still produced, no crash."""
    csv_content = "name,email,github_url\nJane Doe,jane@example.com,https://github.com/missinguser\n"
    csv_path = temp_csv(csv_content)
    
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    mock_get.return_value = mock_resp
    
    results = run_pipeline(csv_path)
    
    candidates = results["candidates"]
    assert len(candidates) == 1
    out = candidates[0]["output"]
    
    assert out["full_name"]["value"] == "Jane Doe"

@patch("src.extractors.github_extractor.requests.get")
def test_pipeline_garbage_csv(mock_get, temp_csv):
    """A completely empty/garbage CSV file -> pipeline returns empty result, doesn't crash, logs clearly."""
    csv_content = "some_random_garbage_column1,col2\nfoo,bar\n"
    csv_path = temp_csv(csv_content)
    
    results = run_pipeline(csv_path)
    
    assert len(results["candidates"]) == 0
    assert results["stats"]["merged"] == 0

@patch("src.extractors.github_extractor.requests.get")
def test_pipeline_entity_resolution_conflict(mock_get, temp_csv):
    """Two CSV rows linking to the same github_url -> verify they merge into ONE candidate, conflict preserved."""
    csv_content = (
        "name,email,github_url\n"
        "Alice Smith,alice1@test.com,https://github.com/alicesmith\n"
        "Alice S.,alice2@test.com,https://github.com/alicesmith\n"
    )
    csv_path = temp_csv(csv_content)
    
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    mock_get.return_value = mock_resp
    
    results = run_pipeline(csv_path)
    
    candidates = results["candidates"]
    stats = results["stats"]
    
    assert stats["processed"] == 2
    assert stats["merged"] == 1
    assert len(candidates) == 1
    
    out = candidates[0]["output"]
    assert len(out["emails"]) == 2
    
    # Verify conflict preservation - 'conflicting_values' will be in the output since to_dict extracts it
    assert "conflicting_values" in out["full_name"]
    assert out["full_name"]["conflicting_values"] == ["Alice S."]

def test_pipeline_default_vs_custom_config(temp_csv, tmp_path):
    """Run with default config vs custom config on the SAME input -> assert outputs differ exactly as configured."""
    csv_content = "name,email,phone,github_url\nBob,bob@example.com,555-1234,\n"
    csv_path = temp_csv(csv_content)
    
    custom_cfg = {
        "fields": [
            {"path": "given_name", "from": "full_name.value", "type": "string"},
            {"path": "contact_email", "from": "emails[0].value", "type": "string"}
        ],
        "include_confidence": False,
        "on_missing": "null"
    }
    
    cfg_path = tmp_path / "custom.json"
    cfg_path.write_text(json.dumps(custom_cfg), encoding="utf-8")
    
    # Run default
    results_default = run_pipeline(csv_path, None)
    out_def = results_default["candidates"][0]["output"]
    
    assert "full_name" in out_def
    assert isinstance(out_def["full_name"], dict)
    
    # Run custom
    results_custom = run_pipeline(csv_path, str(cfg_path))
    out_cust = results_custom["candidates"][0]["output"]
    
    assert "given_name" in out_cust
    assert "contact_email" in out_cust
    assert "full_name" not in out_cust
    assert out_cust["given_name"] == "Bob"
    assert out_cust["contact_email"] == "bob@example.com"
