"""
SQLite-backed persistence layer for canonical candidates.
"""
import sqlite3
import json
import logging
import uuid
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
        
        cursor.execute('''
            CREATE VIRTUAL TABLE IF NOT EXISTS candidates_fts USING fts5(
                candidate_id UNINDEXED,
                searchable_text
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS identity_index (
                identifier_value TEXT,
                identifier_type TEXT,
                candidate_id TEXT,
                PRIMARY KEY (identifier_value, identifier_type)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS identity_bridge_alerts (
                alert_id TEXT PRIMARY KEY,
                primary_candidate_id TEXT,
                bridged_candidate_ids TEXT,
                reason TEXT,
                score REAL
            )
        ''')
        
        conn.commit()

def lookup_candidate_by_identifiers(db_path: str, emails: list[str], phones: list[str], github_url: str | None) -> str | None:
    """
    Checks identity_index for ANY of these normalized identifiers, in priority order
    (github > email > phone), and returns the first matching candidate_id found.
    """
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        
        if github_url:
            cursor.execute('SELECT candidate_id FROM identity_index WHERE identifier_value = ? AND identifier_type = "github"', (github_url,))
            row = cursor.fetchone()
            if row:
                return row[0]
                
        for email in emails:
            cursor.execute('SELECT candidate_id FROM identity_index WHERE identifier_value = ? AND identifier_type = "email"', (email,))
            row = cursor.fetchone()
            if row:
                return row[0]
                
        for phone in phones:
            cursor.execute('SELECT candidate_id FROM identity_index WHERE identifier_value = ? AND identifier_type = "phone"', (phone,))
            row = cursor.fetchone()
            if row:
                return row[0]
                
    return None

def find_bridging_conflicts(db_path: str, emails: list[str], phones: list[str], github_url: str | None) -> list[str]:
    """
    Returns a list of DISTINCT candidate_ids if the new extraction's identifiers 
    point to MORE THAN ONE existing candidate.
    """
    found_candidates = set()
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        
        if github_url:
            cursor.execute('SELECT candidate_id FROM identity_index WHERE identifier_value = ? AND identifier_type = "github"', (github_url,))
            row = cursor.fetchone()
            if row:
                found_candidates.add(row[0])
                
        for email in emails:
            cursor.execute('SELECT candidate_id FROM identity_index WHERE identifier_value = ? AND identifier_type = "email"', (email,))
            row = cursor.fetchone()
            if row:
                found_candidates.add(row[0])
                
        for phone in phones:
            cursor.execute('SELECT candidate_id FROM identity_index WHERE identifier_value = ? AND identifier_type = "phone"', (phone,))
            row = cursor.fetchone()
            if row:
                found_candidates.add(row[0])
                
    if len(found_candidates) > 1:
        return list(found_candidates)
    return []

def register_identifiers(db_path: str, candidate_id: str, emails: list[str], phones: list[str], github_url: str | None) -> None:
    """
    Upserts rows into identity_index for every identifier this candidate now has.
    """
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        if github_url:
            cursor.execute('INSERT OR REPLACE INTO identity_index (identifier_value, identifier_type, candidate_id) VALUES (?, ?, ?)', (github_url, "github", candidate_id))
        for email in emails:
            cursor.execute('INSERT OR REPLACE INTO identity_index (identifier_value, identifier_type, candidate_id) VALUES (?, ?, ?)', (email, "email", candidate_id))
        for phone in phones:
            cursor.execute('INSERT OR REPLACE INTO identity_index (identifier_value, identifier_type, candidate_id) VALUES (?, ?, ?)', (phone, "phone", candidate_id))
        conn.commit()

def log_bridge_alert(db_path: str, primary_id: str, bridged_ids: list[str]) -> None:
    """
    Logs an identity bridging alert for manual review.
    """
    alert_id = str(uuid.uuid4())
    bridged_str = ",".join(bridged_ids)
    reason = "exact_identifier_bridge"
    score = 0.95
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO identity_bridge_alerts 
            (alert_id, primary_candidate_id, bridged_candidate_ids, reason, score)
            VALUES (?, ?, ?, ?, ?)
        ''', (alert_id, primary_id, bridged_str, reason, score))
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
            
        # Build searchable text
        search_parts = []
        if full_name:
            search_parts.append(full_name)
        if candidate.headline and candidate.headline.value:
            search_parts.append(candidate.headline.value)
        for skill_fv in candidate.skills:
            if skill_fv.value:
                search_parts.append(skill_fv.value)
        for exp in candidate.experience:
            if exp.get("company"):
                search_parts.append(str(exp["company"]))
            if exp.get("title"):
                search_parts.append(str(exp["title"]))
                
        searchable_text = " ".join(search_parts)
        
        cursor.execute('''
            DELETE FROM candidates_fts WHERE candidate_id = ?
        ''', (candidate.candidate_id,))
        
        cursor.execute('''
            INSERT INTO candidates_fts (candidate_id, searchable_text)
            VALUES (?, ?)
        ''', (candidate.candidate_id, searchable_text))
            
        conn.commit()

    # Register identifiers for persistent cross-run matching
    github_url = None
    if candidate.links and candidate.links.get("github"):
        github_url = candidate.links.get("github").strip().lower()

    emails = [e.value.strip().lower() for e in candidate.emails if e.value]
    phones = [p.value for p in candidate.phones if p.value]
    
    register_identifiers(db_path, candidate.candidate_id, emails, phones, github_url)

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

def full_text_search(db_path: str, query: str) -> list[dict]:
    """
    Searches candidates using FTS5 virtual table.
    Returns matching candidates ranked by bm25 relevance.
    """
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                SELECT c.canonical_json 
                FROM candidates_fts f
                JOIN candidates c ON f.candidate_id = c.candidate_id
                WHERE candidates_fts MATCH ?
                ORDER BY bm25(candidates_fts)
            ''', (query,))
        except sqlite3.OperationalError:
            # E.g. syntax error in FTS5 query string
            return []
            
        rows = cursor.fetchall()
        return [json.loads(row[0]) for row in rows]
