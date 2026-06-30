"""
GitHub extractor module.
Responsible for extracting candidate information from GitHub profiles or API.
"""
import os
import uuid
import logging
from collections import Counter
from typing import Any
import requests
from requests.exceptions import RequestException, Timeout

from src.models import RawExtraction, Provenance

logger = logging.getLogger(__name__)

def _get_github_token() -> str | None:
    token = os.environ.get("GITHUB_API")
    if token:
        return token
    # Fallback to simple .env parsing if dotenv is not used
    try:
        with open(".env", "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("GITHUB_API="):
                    return line.strip().split("=", 1)[1].strip("'\"")
    except Exception:
        pass
    return None

def extract_from_github(username: str) -> RawExtraction | None:
    """
    Extracts candidate data from GitHub REST API.
    """
    headers = {"Accept": "application/vnd.github.v3+json"}
    token = _get_github_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"

    base_url = f"https://api.github.com/users/{username}"
    
    try:
        resp = requests.get(base_url, headers=headers, timeout=5.0)
        
        # Handle 404
        if resp.status_code == 404:
            logger.warning("GitHub username not found: %s", username)
            return None
            
        # Handle Rate Limit (403)
        elif resp.status_code == 403:
            if "X-RateLimit-Remaining" in resp.headers and resp.headers["X-RateLimit-Remaining"] == "0":
                logger.warning("GitHub rate limit hit")
            else:
                logger.warning("GitHub 403 Forbidden: %s", resp.text)
            return None
            
        resp.raise_for_status()
        profile_data = resp.json()
        
    except Timeout:
        logger.warning("Timeout while fetching GitHub profile for %s", username)
        return None
    except RequestException as e:
        logger.warning("Network error while fetching GitHub profile for %s: %s", username, e)
        return None

    # Fetch repos
    repos_url = f"{base_url}/repos?per_page=100"
    repos_data = []
    try:
        resp_repos = requests.get(repos_url, headers=headers, timeout=5.0)
        if resp_repos.status_code == 200:
            repos_data = resp_repos.json()
        elif resp_repos.status_code == 403:
            logger.warning("GitHub rate limit hit on repos request")
    except RequestException as e:
        logger.warning("Network error while fetching repos for %s: %s", username, e)
        # We proceed with empty repos_data if repos fetch fails
    
    candidate_id = uuid.uuid4().hex
    extraction = RawExtraction(candidate_id=candidate_id)
    
    def get_val(data: dict, key: str) -> str | None:
        val = data.get(key)
        if val is not None and str(val).strip():
            return str(val).strip()
        return None

    name = get_val(profile_data, 'name')
    if name:
        prov = Provenance("github_api", "name", "github_rest_api", 0.7)
        extraction.full_name = (name, prov)
        
    bio = get_val(profile_data, 'bio')
    if bio:
        prov = Provenance("github_api", "bio", "github_rest_api", 0.7)
        extraction.headline = (bio, prov)
        
    location = get_val(profile_data, 'location')
    if location:
        prov = Provenance("github_api", "location", "github_rest_api", 0.7)
        loc_dict: dict[str, Any] = {"city": location, "region": None, "country": None}
        extraction.location = (loc_dict, prov)
        
    profile_url = get_val(profile_data, 'html_url') or f"https://github.com/{username}"
    links_dict: dict[str, Any] = {"github": profile_url}
    
    blog = get_val(profile_data, 'blog')
    if blog:
        links_dict["portfolio"] = blog
        
    links_prov = Provenance("github_api", "html_url/blog", "github_rest_api", 0.7)
    extraction.links = (links_dict, links_prov)
    
    company = get_val(profile_data, 'company')
    if company:
        exp_dict: dict[str, Any] = {
            "company": company,
            "title": None,
            "start": None,
            "end": None,
            "summary": None
        }
        prov = Provenance("github_api", "company", "github_rest_api", 0.7)
        extraction.experience.append((exp_dict, prov))
        
    # Process skills
    if repos_data:
        languages = []
        for r in repos_data:
            lang = r.get('language')
            if lang and str(lang).strip():
                languages.append(str(lang).strip().lower())
        
        if languages:
            counter = Counter(languages)
            top_10 = [item[0] for item in counter.most_common(10)]
            
            for lang in top_10:
                prov = Provenance("github_api", "repos[].language", "github_rest_api", 0.5)
                # Keep proper casing logic for known languages if desired, but title() works for now.
                # Actually, some languages like "JavaScript" vs "javascript".
                # For simplicity, let's just title case. E.g. python -> Python, html -> Html.
                skill_name = lang.title() 
                if skill_name == "Javascript": skill_name = "JavaScript"
                if skill_name == "Typescript": skill_name = "TypeScript"
                if skill_name == "Html": skill_name = "HTML"
                if skill_name == "Css": skill_name = "CSS"
                
                extraction.skills.append((skill_name, prov))
                
    return extraction
