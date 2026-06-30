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
    run_parser.add_argument("--csv", required=True, help="Path to input CSV file")
    run_parser.add_argument("--config", help="Path to projection config JSON")
    run_parser.add_argument("--out", required=True, help="Path to output JSON")
    run_parser.add_argument("--ats", help="Path to input ATS JSON file")
    run_parser.add_argument("--db", help="Path to SQLite database for persistence")
    run_parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    
    # Search Subcommand
    search_parser = subparsers.add_parser("search", help="Search candidates in the database")
    search_parser.add_argument("--db", required=True, help="Path to SQLite database")
    search_parser.add_argument("--skill", required=True, help="Skill to search for")
    
    # Top-level args for backward compatibility (no subcommand provided)
    parser.add_argument("--csv", help="Path to input CSV file")
    parser.add_argument("--config", help="Path to projection config JSON")
    parser.add_argument("--out", help="Path to output JSON")
    parser.add_argument("--ats", help="Path to input ATS JSON file")
    parser.add_argument("--db", help="Path to SQLite database for persistence")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    
    args = parser.parse_args()
    
    if args.command == "search":
        from src.storage import search_by_skill
        candidates = search_by_skill(args.db, args.skill)
        print(f"--- Search Results for skill '{args.skill}' ---")
        print(f"{'Name':<30} | {'Email':<30} | {'Confidence'}")
        print("-" * 75)
        for cand in candidates:
            name = cand.get("full_name", {}).get("value") if cand.get("full_name") else "Unknown"
            emails = cand.get("emails", [])
            email = emails[0].get("value") if emails else "Unknown"
            conf = cand.get("overall_confidence", 0.0)
            print(f"{name:<30} | {email:<30} | {conf:.2f}")
        return
        
    # If not search, we run the pipeline
    if not args.csv or not args.out:
        parser.error("The following arguments are required for pipeline run: --csv, --out")
        
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, format="%(levelname)s: %(message)s")
    else:
        logging.basicConfig(level=logging.INFO, format="%(message)s")
        
    try:
        results = run_pipeline(args.csv, args.config, ats_path=args.ats, db_path=args.db)
        
        candidates = results["candidates"]
        stats = results["stats"]
        
        final_outputs = []
        any_invalid = False
        
        for res in candidates:
            final_outputs.append(res["output"])
            if not res["valid"]:
                any_invalid = True
                
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(final_outputs, f, indent=2)
            
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
