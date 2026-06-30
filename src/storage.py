"""
SQLite-backed persistence layer for canonical candidates.
"""
import sqlite3
import json
import logging
from datetime import datetime, timezone
from src.models import CanonicalCandidate

logger = logging.getLogger(__name__)

def init_db(db_path: str) -> None:
    """
    Creates tables if they don't exist.
    """
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS candidates (
                candidate_id TEXT PRIMARY KEY,
                full_name TEXT,
                overall_confidence REAL,
                canonical_json TEXT,
                last_updated TEXT
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS candidate_skills (
                candidate_id TEXT,
                skill_name TEXT,
                confidence REAL,
                FOREIGN KEY(candidate_id) REFERENCES candidates(candidate_id) ON DELETE CASCADE
            )
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_candidate_skills 
            ON candidate_skills(candidate_id, skill_name)
        ''')
        
        conn.commit()

def upsert_candidate(db_path: str, candidate: CanonicalCandidate) -> None:
    """
    Inserts or updates a candidate in the database.
    """
    full_name = candidate.full_name.value if candidate.full_name else None
    overall_confidence = candidate.overall_confidence
    canonical_json = json.dumps(candidate.to_dict())
    last_updated = datetime.now(timezone.utc).isoformat()
    
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO candidates 
            (candidate_id, full_name, overall_confidence, canonical_json, last_updated)
            VALUES (?, ?, ?, ?, ?)
        ''', (candidate.candidate_id, full_name, overall_confidence, canonical_json, last_updated))
        
        cursor.execute('''
            DELETE FROM candidate_skills WHERE candidate_id = ?
        ''', (candidate.candidate_id,))
        
        for skill_fv in candidate.skills:
            skill_name = skill_fv.value
            confidence = skill_fv.confidence
            cursor.execute('''
                INSERT INTO candidate_skills (candidate_id, skill_name, confidence)
                VALUES (?, ?, ?)
            ''', (candidate.candidate_id, skill_name, confidence))
            
        conn.commit()

def get_candidate(db_path: str, candidate_id: str) -> dict | None:
    """
    Fetches a candidate by ID and deserializes the JSON blob.
    """
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT canonical_json FROM candidates WHERE candidate_id = ?', (candidate_id,))
        row = cursor.fetchone()
        
        if row:
            return json.loads(row[0])
        return None

def list_candidates(db_path: str, min_confidence: float | None = None) -> list[dict]:
    """
    Lists all candidates, optionally filtered by overall_confidence threshold.
    """
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        
        if min_confidence is not None:
            cursor.execute('SELECT canonical_json FROM candidates WHERE overall_confidence >= ?', (min_confidence,))
        else:
            cursor.execute('SELECT canonical_json FROM candidates')
            
        rows = cursor.fetchall()
        return [json.loads(row[0]) for row in rows]

def search_by_skill(db_path: str, skill_name: str) -> list[dict]:
    """
    Searches candidates by a specific skill (case-insensitive).
    Returns a list of full candidate dictionaries.
    """
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT DISTINCT c.canonical_json 
            FROM candidates c
            JOIN candidate_skills s ON c.candidate_id = s.candidate_id
            WHERE LOWER(s.skill_name) = ?
        ''', (skill_name.lower(),))
        
        rows = cursor.fetchall()
        return [json.loads(row[0]) for row in rows]
