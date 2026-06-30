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
python cli.py run --csv sample_data/recruiter_export.csv --ats sample_data/ats_export.json --out output_default.json
```

**2. Custom Projection Configuration**
Run the pipeline passing a custom configuration payload to selectively map, rename, and standardize the final output:
```bash
python cli.py run --csv sample_data/recruiter_export.csv --config config/sample_projection_config.json --out output_custom.json
```

*Note: The generated examples are saved in `output_default.json` and `output_custom.json`. The output shape contains a top-level object wrapper `{ "candidates": [...], "possible_duplicates": [...], "run_metadata": {...} }`.*

```bash
python cli.py explain --db candidates.sqlite3 --all --flagged-only
```

## Evaluation

We maintain a rigorous gold-set evaluation harness to mathematically prove entity resolution and field-conflict resolution correctness against hand-verified truth.

```bash
python scripts/run_gold_eval.py
```
This runs the pipeline on controlled `tests/gold_eval/gold_input/` mock data and calculates field/entity accuracy against `tests/gold_eval/gold_expected.json`.

## Web UI Demo Tool

A minimal local Web UI is included for demonstration purposes. **Note:** This is a local demo tool built with Flask's development server, not a production WSGI service. It is designed specifically to visualize the pipeline's capabilities in a 2-minute demo format.

To launch the web interface locally on `localhost:5000`:
```bash
python cli.py serve
```

## Architecture

- **Extraction**: Clean functional interfaces per data source. Each returns raw tuples with Confidence and Provenance metadata attached immediately at birth.
- **Normalization**: Pure functions mapping ugly strings to consistent canonical structures.
- **Merge**: Smart conflict resolution utilizing provenance-based confidence decaying and source prioritization, structurally deduplicates matches via strict deterministic Join Keys (GitHub URL -> Primary Email -> Phone), and records granular confidence scores representing field-level agreements.
- **Confidence Model**: All confidence weights and disagreement penalties are externalized into `config/source_confidence.json`, ensuring the scoring system is transparent and tuneable.
- **Duplicate Suggestions**: An explicit secondary pass built on `rapidfuzz` scoring that flags probable duplicates for human review without mutating deterministic merge clusters.
- **Projection**: Resolves dot-notation JSON paths and array-maps to cleanly transform the heavy canonical object schema directly into flexible payload mappings per customer configurations.
- **Validation**: Absorbs the payloads natively asserting conformity against the JSON schema definitions while explicitly preventing ungraceful pipeline death on corrupt values.

## Identity Resolution & Persistence

By default, the pipeline operates in-memory for single-shot processing. When a SQLite database path is provided via `--db`, the system enables persistent cross-run identity resolution:
- **Stable IDs**: `candidate_id` is now stable across runs via the `identity_index` table. This maps every known exact identifier (GitHub URL, Email, Phone) to a canonical candidate.
- **Incremental Enrichment**: Candidates can be incrementally enriched by uploading new sources in separate sessions. New fields and provenance metrics are automatically injected alongside historical data, rather than overwriting previous runs.
- **Bridging Conflicts**: If a new extraction connects two previously separate candidates (e.g., an extraction containing Alice's email and Bob's phone number), it surfaces a bridging conflict alert for manual review rather than destructively auto-merging them. This fixes a core architectural flaw (silent cross-linking) at the right layer, rather than patching around it.

## Documented Edge Cases

- **Missing `github_url`**: A CSV row strictly omitted a GitHub URL; the external extraction phase was gracefully skipped, passing solely the CSV variables downstream for the candidate.
- **GitHub 404 Resolution**: A CSV row's `github_url` pointed to a deleted repository or user profile (404 Error); the network fetch was swallowed under the `try/except` wrapper and logged accordingly, producing a valid CSV candidate with no GitHub metrics appended.
- **Garbage Inputs**: Given an entirely corrupt CSV containing non-mapped metadata or fully empty rows, the parser automatically identified the absence of meaningful variables and silently stripped the extraction, returning safely without cascading death. 
- **Entity Resolution Conflict Preservation**: Two disjointed CSV rows identically mapping the same GitHub user merged effectively. Their unified structure logged explicitly `conflicting_values` when source data disagreed, dynamically recalculating their aggregated confidence score natively leveraging independent source probability.

## Descoped Functionality

- **Fuzzy Name Matching**: Specifically descoped intentionally to strictly enforce precision over recall. Implementing ML clustering or fuzzy Jaro-Winkler analysis frequently corrupts disparate contacts sharing similar generic titles. The merge strictly requires a hard GitHub, Email, or Phone Join Key. Entity resolution beyond exact-match keys is surfaced as a reviewable suggestion inside the `possible_duplicates` key, never auto-applied.
- **Resume Parsing**: Restricted strictly to rule-based logic to preserve deterministic behavior and transparency over stochastic NLP / ML extraction.
- **Database / Queue Infrastructure**: Operates cleanly as a stateless CLI utilizing single-process extraction for scope alignment instead of distributed workers, allowing instantaneous deployment mapping without dependencies.

## Known Limitations

- **Rule-Based Entity Resolution Boundaries**: Auto-merge logic aggressively relies on matching Emails, GitHub links, and normalized Phone numbers. Highly isolated legacy profiles sharing zero determinable keys (but sharing matching generic names and job experience) will purposefully not cluster to prevent collateral corruption.
- **Duplicates Panel Uncertainty**: The Duplicate Suggestions UI acts as a safety layer flagging non-auto-merged candidates. It bounds scores between 0-1, yet since it is rule-based and lacks semantic vectors, extremely generic names may yield lower-confidence false positives or rank true matches lower based on incomplete structured signals. This remains explicitly designed for human-in-the-loop review.
