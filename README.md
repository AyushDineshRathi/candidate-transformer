# Candidate Transformer

A robust, type-safe data engineering pipeline in Python that extracts, normalizes, deduplicates, and projects candidate profiles from fragmented CSV and GitHub REST API sources into a unified, clean, and highly-configurable output format.

## Setup Instructions

1. Ensure you are running Python 3.11+.
2. Install the required dependencies:
```bash
pip install -r requirements.txt
```
3. Optionally configure your `.env` or set the `GITHUB_API` environment variable with your personal access token to prevent rate-limiting during GitHub extraction:
```bash
export GITHUB_API="your_token_here"
```

## Running the Pipeline

**1. Default Output (No custom config)**
Run the pipeline falling back on the standard exhaustive schema:
```bash
python cli.py --csv sample_data/recruiter_export.csv --out output_default.json
```

**2. Custom Projection Configuration**
Run the pipeline passing a custom configuration payload to selectively map, rename, and standardize the final output:
```bash
python cli.py --csv sample_data/recruiter_export.csv --config config/sample_projection_config.json --out output_custom.json
```

*Note: The generated examples are saved in `output_default.json` and `output_custom.json`.*

```bash
python cli.py explain --db candidates.sqlite3 --all --flagged-only
```

## Web UI Demo Tool

A minimal local Web UI is included for demonstration purposes. **Note:** This is a local demo tool built with Flask's development server, not a production WSGI service. It is designed specifically to visualize the pipeline's capabilities in a 2-minute demo format.

To launch the web interface locally on `localhost:5000`:
```bash
python cli.py serve
```

## Architecture

- **Extraction**: Clean functional interfaces per data source. Each returns raw tuples with Confidence and Provenance metadata attached immediately at birth.
- **Normalization**: Pure functions mapping ugly strings to consistent canonical structures.
- **Merge**: Smart conflict resolution utilizing provenance-based confidence decaying and source prioritization, structurally deduplicates matches via strict deterministic Join Keys (GitHub URL -> Primary Email), and records granular confidence scores representing field-level agreements.
- **Projection**: Resolves dot-notation JSON paths and array-maps to cleanly transform the heavy canonical object schema directly into flexible payload mappings per customer configurations.
- **Validation**: Absorbs the payloads natively asserting conformity against the JSON schema definitions while explicitly preventing ungraceful pipeline death on corrupt values.

## Documented Edge Cases

- **Missing `github_url`**: A CSV row strictly omitted a GitHub URL; the external extraction phase was gracefully skipped, passing solely the CSV variables downstream for the candidate.
- **GitHub 404 Resolution**: A CSV row's `github_url` pointed to a deleted repository or user profile (404 Error); the network fetch was swallowed under the `try/except` wrapper and logged accordingly, producing a valid CSV candidate with no GitHub metrics appended.
- **Garbage Inputs**: Given an entirely corrupt CSV containing non-mapped metadata or fully empty rows, the parser automatically identified the absence of meaningful variables and silently stripped the extraction, returning safely without cascading death. 
- **Entity Resolution Conflict Preservation**: Two disjointed CSV rows identically mapping the same GitHub user merged effectively. Their unified structure logged explicitly `conflicting_values` when source data disagreed, dynamically recalculating their aggregated confidence score natively leveraging independent source probability.

## Descoped Functionality

- **Fuzzy Name Matching**: Specifically descoped intentionally to strictly enforce precision over recall. Implementing ML clustering or fuzzy Jaro-Winkler analysis frequently corrupts disparate contacts sharing similar generic titles. The merge strictly requires a hard GitHub or Email Join Key.
- **Resume Parsing**: Excluded due to the unreliability of zero-shot parsing against fragmented PDF variants without a robust cloud OCR layer.
- **Database / Queue Infrastructure**: Operates cleanly as a stateless CLI utilizing single-process extraction for scope alignment instead of distributed workers, allowing instantaneous deployment mapping without dependencies.
