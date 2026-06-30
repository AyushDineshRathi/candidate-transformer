import argparse
import sys
import json
import logging
from src.pipeline import run_pipeline

def main():
    parser = argparse.ArgumentParser(description="Candidate Transformer Pipeline")
    parser.add_argument("--csv", required=True, help="Path to input CSV file")
    parser.add_argument("--config", help="Path to projection config JSON")
    parser.add_argument("--out", required=True, help="Path to output JSON")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, format="%(levelname)s: %(message)s")
    else:
        logging.basicConfig(level=logging.INFO, format="%(message)s")
        
    try:
        results = run_pipeline(args.csv, args.config)
        
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
