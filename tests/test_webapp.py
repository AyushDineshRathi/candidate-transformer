"""
Smoke test for the Flask Web UI.
"""
import pytest
from src.webapp import app
import src.webapp
import os

@pytest.fixture
def client(tmp_path):
    app.config['TESTING'] = True
    
    # Patch DB_PATH to use a temp file so we don't mess up the real DB
    db_path = str(tmp_path / "test.sqlite3")
    src.webapp.DB_PATH = db_path
    
    with app.test_client() as client:
        yield client

def test_index_route(client):
    response = client.get('/')
    assert response.status_code == 200
    assert b"Run Pipeline" in response.data

def test_run_route_smoke(client):
    csv_path = "sample_data/recruiter_export.csv"
    if not os.path.exists(csv_path):
        pytest.skip("Sample CSV not found")
        
    with open(csv_path, "rb") as f:
        data = {
            'csv_file': (f, 'recruiter_export.csv'),
            'schema_type': 'default'
        }
        
        response = client.post('/run', data=data, content_type='multipart/form-data', follow_redirects=True)
        
    assert response.status_code == 200
    # We expect 'Torvalds' or 'Octocat' from the CSV
    assert b"Torvalds" in response.data or b"Octocat" in response.data
