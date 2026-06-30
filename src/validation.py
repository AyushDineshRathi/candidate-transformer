"""
Validation module.
Uses jsonschema to validate final output structures against defined constraints.
"""
import jsonschema
from typing import Any

def validate_against_schema(output: dict, schema: dict) -> list[str]:
    """
    Validates a dictionary against a JSON Schema.
    Returns a list of human-readable error strings. Empty list means valid.
    Does not raise on invalid data, allowing caller to handle it safely.
    """
    errors = []
    validator = jsonschema.Draft7Validator(schema)
    for error in validator.iter_errors(output):
        path = ".".join([str(p) for p in error.path]) if error.path else "root"
        errors.append(f"{path}: {error.message}")
    return errors

def validate_pipeline_output(output: dict, schema: dict) -> dict:
    """
    Runs validation and returns a safe payload wrapper containing the validity status,
    errors, and the original output, preventing hard crashes.
    """
    errors = validate_against_schema(output, schema)
    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "output": output
    }
