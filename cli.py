import argparse
import sys
import json
import logging
from src.pipeline import run_pipeline

def main():
    parser = argparse.ArgumentParser(description="Candidate Transformer CLI")
    subparsers = parser.add_subparsers(dest="command", help="Subcommands")
    
    # Run Subcommand
    run_parser = subparsers.add_parser("run", help="Run the candidate transformer pipeline")
    run_parser.add_argument("--csv", help="Path to input CSV file")
    run_parser.add_argument("--config", help="Path to projection config JSON")
    run_parser.add_argument("--out", help="Path to output JSON")
    run_parser.add_argument("--ats", help="Path to input ATS JSON file")
    run_parser.add_argument("--resume", nargs="*", help="Paths to input Resume PDF/DOCX files or directories")
    run_parser.add_argument("--db", help="Path to SQLite database for persistence")
    run_parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    
    # Search Subcommand
    search_parser = subparsers.add_parser("search", help="Search candidates in the database")
    search_parser.add_argument("--db", required=True, help="Path to SQLite database")
    
    search_group = search_parser.add_mutually_exclusive_group(required=True)
    search_group.add_argument("--skill", help="Exact skill to search for")
    search_group.add_argument("--query", help="Free-text FTS query")
    
    # Explain Subcommand
    explain_parser = subparsers.add_parser("explain", help="Explain candidate confidence and provenance")
    explain_parser.add_argument("--db", required=True, help="Path to SQLite database")
    explain_group = explain_parser.add_mutually_exclusive_group(required=True)
    explain_group.add_argument("--candidate-id", help="Explain a specific candidate by ID")
    explain_group.add_argument("--all", action="store_true", help="Explain all candidates")
    explain_parser.add_argument("--flagged-only", action="store_true", help="Only explain flagged candidates")
    
    # Serve Subcommand
    serve_parser = subparsers.add_parser("serve", help="Start the minimal local web UI")
    
    # Summary Subcommand
    summary_parser = subparsers.add_parser("summary", help="Print a system health metrics report")
    summary_parser.add_argument("--db", required=True, help="Path to SQLite database")

    # Suggest Duplicates Subcommand
    suggest_parser = subparsers.add_parser("suggest-duplicates", help="Suggest possible duplicates that were not auto-merged")
    suggest_parser.add_argument("--db", required=True, help="Path to SQLite database")
    
    # Top-level args for backward compatibility (no subcommand provided)
    parser.add_argument("--csv", help="Path to input CSV file")
    parser.add_argument("--config", help="Path to projection config JSON")
    parser.add_argument("--out", help="Path to output JSON")
    parser.add_argument("--ats", help="Path to input ATS JSON file")
    parser.add_argument("--resume", nargs="*", help="Paths to input Resume PDF/DOCX files or directories")
    parser.add_argument("--github-url", help="Standalone GitHub URL to fetch")
    parser.add_argument("--db", help="Path to SQLite database for persistence")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    
    args = parser.parse_args()
    
    if args.command == "search":
        from src.storage import search_by_skill, full_text_search
        
        if args.skill:
            candidates = search_by_skill(args.db, args.skill)
            print(f"--- Exact Skill Search Results for '{args.skill}' ---")
        elif args.query:
            candidates = full_text_search(args.db, args.query)
            print(f"--- Full-Text Search Results for '{args.query}' ---")
            
        print(f"{'Name':<30} | {'Email':<30} | {'Confidence'}")
        print("-" * 75)
        for cand in candidates:
            name = cand.get("full_name", {}).get("value") if cand.get("full_name") else "Unknown"
            emails = cand.get("emails", [])
            email = emails[0].get("value") if emails else "Unknown"
            conf = cand.get("overall_confidence", 0.0)
            print(f"{name:<30} | {email:<30} | {conf:.2f}")
        return
        
    if args.command == "explain":
        from src.storage import get_candidate, list_candidates
        from src.explain import explain_candidate
        
        candidates_to_explain = []
        if args.candidate_id:
            cand = get_candidate(args.db, args.candidate_id)
            if cand:
                candidates_to_explain.append(cand)
            else:
                print(f"Candidate {args.candidate_id} not found.")
                return
        elif args.all:
            candidates_to_explain = list_candidates(args.db)
            if args.flagged_only:
                candidates_to_explain = [c for c in candidates_to_explain if c.get("needs_human_review")]
                
        for i, c in enumerate(candidates_to_explain):
            if i > 0:
                print("\n" + "="*50 + "\n")
            print(explain_candidate(c))
        return
        
    if args.command == "serve":
        from src.webapp import app
        app.run(debug=True, port=5000)
        return
        
    if args.command == "summary":
        from src.storage import list_candidates
        candidates = list_candidates(args.db)
        
        total = len(candidates)
        if total == 0:
            print("No candidates found in database.")
            return
            
        with_email = sum(1 for c in candidates if c.get("emails"))
        with_github = sum(1 for c in candidates if c.get("links", {}).get("github"))
        total_conf = sum(c.get("overall_confidence", 0.0) for c in candidates)
        flagged = sum(1 for c in candidates if c.get("needs_human_review"))
        
        def check_prov(field_val):
            if isinstance(field_val, dict):
                sources = {p.get("source") for p in field_val.get("provenance", [])}
                return {"recruiter.csv", "github_api", "ats.json"}.issubset(sources)
            return False
            
        three_way = 0
        for cand in candidates:
            has_three_way = check_prov(cand.get("full_name")) or check_prov(cand.get("location"))
            for em in cand.get("emails", []):
                if check_prov(em): has_three_way = True
            for ph in cand.get("phones", []):
                if check_prov(ph): has_three_way = True
            for sk in cand.get("skills", []):
                if check_prov(sk): has_three_way = True
            if has_three_way:
                three_way += 1
                
        print("--- System Health Metrics ---")
        print(f"Total Candidates: {total}")
        print(f"% with Email: {(with_email/total)*100:.1f}%")
        print(f"% with GitHub: {(with_github/total)*100:.1f}%")
        print(f"Avg Confidence: {total_conf/total:.2f}")
        print(f"Flagged for Review: {flagged}")
        print(f"3-Way Source Agreement: {three_way}")
        return
        
    if args.command == "suggest-duplicates":
        from src.storage import list_candidates
        from src.duplicate_suggestions import find_possible_duplicates
        from src.models import CanonicalCandidate
        
        cand_dicts = list_candidates(args.db)
        candidates = [CanonicalCandidate.from_dict(d) for d in cand_dicts]
        
        suggestions = find_possible_duplicates(candidates)
        if not suggestions:
            print("No possible duplicates found above the threshold.")
            return
            
        print(f"--- Possible Duplicates (Threshold > 0.6) ---")
        for s in suggestions:
            print(f"Score: {s['similarity_score']:.2f} | {s['candidate_a_name']} ({s['candidate_a_id'][:8]}) <-> {s['candidate_b_name']} ({s['candidate_b_id'][:8]})")
            print(f"  Signals: {', '.join(s['matching_signals'])}")
            print()
        return
        
    # If not search, we run the pipeline
    if not args.csv and not args.resume and not args.ats and not getattr(args, "github_url", None):
        parser.error("At least one input source (--csv, --ats, --resume, or --github-url) is required for pipeline run.")
        
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, format="%(levelname)s: %(message)s")
    else:
        logging.basicConfig(level=logging.INFO, format="%(message)s")
        
    resume_paths = []
    if args.resume:
        import os
        import glob
        for r_path in args.resume:
            if os.path.isdir(r_path):
                resume_paths.extend(glob.glob(os.path.join(r_path, "*.pdf")))
                resume_paths.extend(glob.glob(os.path.join(r_path, "*.docx")))
            else:
                resume_paths.append(r_path)
                
    try:
        results = run_pipeline(args.csv, args.config, ats_path=args.ats, resume_paths=resume_paths, github_url=getattr(args, "github_url", None), db_path=args.db)
        
        candidates = results["candidates"]
        final_outputs = []
        any_invalid = False
        for res in candidates:
            if not res["valid"]:
                any_invalid = True
                
        if args.out:
            with open(args.out, "w", encoding="utf-8") as f:
                out_data = {
                    "candidates": [c["output"] for c in results["candidates"]],
                    "possible_duplicates": results["possible_duplicates"],
                    "run_metadata": results["run_metadata"]
                }
                json.dump(out_data, f, indent=2)
            print(f"Results written to {args.out}")
        
        stats = results["run_metadata"]
        print("\n--- Pipeline Summary ---")
        print(f"Extractions Processed: {stats['processed']}")
        print(f"Candidates Merged: {stats['merged']}")
        print(f"Validation Warnings: {stats['warnings']}")
        
        if any_invalid:
            sys.exit(1)
        else:
            sys.exit(0)
            
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(2)

if __name__ == "__main__":
    main()
