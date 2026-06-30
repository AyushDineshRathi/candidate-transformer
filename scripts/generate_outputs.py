import os
import json
from src.pipeline import run_pipeline
from src.storage import list_candidates
from src.models import CanonicalCandidate
from src.projection import project_default, project
from src.duplicate_suggestions import find_possible_duplicates

DB_PATH = "candidates_final.sqlite3"
if os.path.exists(DB_PATH):
    os.remove(DB_PATH)

# Run 1: CSV + GitHub
run_pipeline(csv_path="sample_data/recruiter_export.csv", db_path=DB_PATH)

# Run 2: ATS
run_pipeline(ats_path="sample_data/ats_export.json", db_path=DB_PATH)

# Run 3: Mock ATS to simulate resume match
run_pipeline(ats_path="sample_data/ats_ayush.json", db_path=DB_PATH)

# Now generate outputs
cand_dicts = list_candidates(DB_PATH)
candidates = [CanonicalCandidate.from_dict(d) for d in cand_dicts]

# DEFAULT
default_outputs = [project_default(c) for c in candidates]
suggestions = find_possible_duplicates(candidates)
stats = {
    "processed": len(candidates),  # approximation
    "merged": len(candidates),
    "warnings": 0
}
with open("output_default.json", "w", encoding="utf-8") as f:
    json.dump({
        "candidates": default_outputs,
        "possible_duplicates": suggestions,
        "run_metadata": stats
    }, f, indent=2)

# CUSTOM
with open("config/sample_projection_config.json", "r", encoding="utf-8") as f:
    custom_config = json.load(f)

custom_outputs = [project(c, custom_config) for c in candidates]
with open("output_custom.json", "w", encoding="utf-8") as f:
    json.dump({
        "candidates": custom_outputs,
        "possible_duplicates": suggestions,
        "run_metadata": stats
    }, f, indent=2)

print("Regenerated output_default.json and output_custom.json")
