"""
Minimal local Flask web UI for Candidate Transformer.
"""
from flask import Flask, render_template, request, redirect, url_for
import tempfile
import os
import logging
from src.pipeline import run_pipeline
from src.storage import list_candidates, full_text_search
from src.explain import explain_candidate

app = Flask(__name__, template_folder='../templates')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024 # 16 MB max upload

DB_PATH = "candidates.sqlite3"

@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")

@app.route("/run", methods=["POST"])
def run_pipeline_route():
    csv_file = request.files.get("csv_file")
    ats_file = request.files.get("ats_file")
    schema_type = request.form.get("schema_type")
    custom_config = request.form.get("custom_config")
    
    if not csv_file or csv_file.filename == '':
        return "CSV file is required.", 400
        
    # Save files to temp directory
    temp_dir = tempfile.mkdtemp()
    
    csv_path = os.path.join(temp_dir, "input.csv")
    csv_file.save(csv_path)
    
    ats_path = None
    if ats_file and ats_file.filename != '':
        ats_path = os.path.join(temp_dir, "ats.json")
        ats_file.save(ats_path)
        
    config_path = None
    if schema_type == "custom" and custom_config:
        config_path = os.path.join(temp_dir, "config.json")
        with open(config_path, "w", encoding="utf-8") as f:
            f.write(custom_config)
            
    try:
        # Run the same pipeline CLI uses
        # This will write to candidates.sqlite3 in the CWD
        run_pipeline(csv_path=csv_path, projection_config_path=config_path, ats_path=ats_path, db_path=DB_PATH)
    except Exception as e:
        logging.exception("Pipeline failed")
        return f"Pipeline execution failed: {e}", 500
        
    return redirect(url_for('results'))

@app.route("/results", methods=["GET"])
def results():
    candidates = list_candidates(DB_PATH)
    return render_template("results.html", candidates=candidates, explain_candidate=explain_candidate)

@app.route("/search", methods=["GET"])
def search():
    query = request.args.get("q", "")
    if not query:
        return redirect(url_for('results'))
        
    candidates = full_text_search(DB_PATH, query)
    return render_template("results.html", candidates=candidates, query=query, explain_candidate=explain_candidate)

if __name__ == "__main__":
    app.run(debug=True, port=5000)
