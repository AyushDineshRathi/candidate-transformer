# Candidate Transformer

A robust, type-safe data engineering pipeline in Python that extracts, normalizes, deduplicates, and projects candidate profiles from fragmented CSV, JSON ATS exports, and GitHub REST API sources into a unified, clean, and highly configurable canonical format.

**[Demo Video Link](https://drive.google.com/file/d/1XaMDutzGM_jlPfPxQlnV_HotyyCLAeq9/view?usp=sharing)**

## Setup Instructions

1. Ensure you are running **Python 3.11+**.
2. Create and activate a virtual environment (recommended).
3. Install the required dependencies:
```bash
pip install -r requirements.txt
```
4. *(Optional)* Create a `.env` file or export the `GITHUB_API` environment variable with your personal access token to prevent rate-limiting during GitHub extraction:
```bash
export GITHUB_API="your_token_here"
```

## Running the Pipeline

The pipeline exposes a clean Command Line Interface (CLI) for batch processing and generating the final output JSON files.

### 1. Default Output Schema
Run the pipeline against the sample inputs to generate the strictly formatted default output schema:
```bash
python cli.py run --csv sample_data/recruiter_export.csv --ats sample_data/ats_export.json --out output_default.json
```
*Note: The generated output is saved to `output_default.json` and committed in this repository.*

### 2. Custom Projection Configuration
Run the pipeline passing a custom configuration payload to selectively map, rename, and standardize the final output:
```bash
python cli.py run --csv sample_data/recruiter_export.csv --ats sample_data/ats_export.json --config sample_data/custom_config.json --out output_custom.json
```
*Note: The generated output is saved to `output_custom.json` and committed in this repository.*

### 3. Explanation and Debugging
You can interrogate the merge decisions and trace the provenance of every data point:
```bash
python cli.py explain --db candidates.sqlite3 --all
```

## Running Tests & Evaluation

The system is fully tested with Pytest (76 passing tests).
```bash
pytest tests
```

We also maintain a rigorous gold-set evaluation harness to mathematically prove entity resolution correctness against hand-verified truth.
```bash
python scripts/run_gold_eval.py
```

## Web UI Demo Tool

A premium local Web UI is included for demonstration purposes. This interface allows you to upload sources, visualize the confidence scores, inspect provenance logs dynamically, and download projected JSON payloads.

To launch the web interface locally on `localhost:5000`:
```bash
python cli.py serve
```

## Architecture & Design Decisions

- **Extraction**: Clean functional interfaces per data source. Each returns raw tuples with Confidence and Provenance metadata attached immediately at birth.
- **Normalization**: Pure functions mapping unstructured data (e.g., E.164 phone parsing, ISO-3166 alpha-2 country codes, canonical skill sets) to consistent structures.
- **Merge**: Smart conflict resolution utilizing provenance-based confidence accumulation. Structurally deduplicates matches via strict deterministic Join Keys (GitHub URL -> Primary Email -> Phone), and records granular confidence scores.
- **Confidence Model**: Confidence weights are transparent and tunable (`config/source_confidence.json`). Consecutive identical data sources are cleanly deduplicated to ensure perfectly idempotent scoring.
- **Duplicate Suggestions**: An explicit heuristic pass built on `rapidfuzz` scoring that flags probable duplicates for human review (discounting heavily for common shared traits like "Python" or "Student") without destructively auto-merging ambiguous profiles.
- **Projection Layer**: Enforces a strict separation between the heavy internal canonical record (which tracks rich provenance for every field) and the cleanly flattened JSON output structure. 

## Identity Resolution & Persistence

By default, the pipeline operates in-memory for single-shot processing. When a SQLite database path is provided via `--db` (which the Web UI uses by default), the system enables persistent cross-run identity resolution:
- **Stable IDs**: `candidate_id` is stable across runs via the `identity_index` table. This maps every known exact identifier (GitHub URL, Email, Phone) to a canonical candidate.
- **Incremental Enrichment**: Candidates can be incrementally enriched across multiple runs. New fields and provenance metrics are automatically injected alongside historical data, strictly preserving idempotency.

## Documented Edge Cases Handled

1. **GitHub 404 Resolution**: A CSV row's `github_url` pointed to a deleted repository or user profile (404 Error); the network fetch is swallowed gracefully and logged, producing a valid candidate from the remaining CSV data.
2. **Missing/Garbage Inputs**: Given an entirely corrupt CSV or fully empty rows, the parser automatically identifies the absence of meaningful variables and silently strips the extraction, safely avoiding cascading failures. 
3. **Empty Source Degradation**: Missing fields intelligently fall back to `null` while preserving the requested output JSON structure instead of failing projection validation.

## Descoped Functionality & Assumptions

- **Fuzzy Auto-Merging**: Specifically descoped intentionally to strictly enforce precision over recall. The merge strictly requires a hard GitHub, Email, or Phone Join Key. Merging based purely on similar names + skills is surfaced as a reviewable suggestion inside the `possible_duplicates` UI/API response, never auto-applied.
- **Resume Parsing NLP**: Restricted strictly to rule-based logic and regex to preserve deterministic behavior and transparency over stochastic NLP / ML extraction tools.
- **Database / Queue Infrastructure**: Operates cleanly as a stateless CLI utilizing single-process extraction for scope alignment instead of distributed workers, allowing instantaneous deployment mapping without dependencies.
