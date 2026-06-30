"""
Normalizers module.
Responsible for standardizing extracted fields (e.g., parsing phone numbers, dates, locations).
"""
import logging
import re
import phonenumbers
from dateutil import parser as date_parser
from dateutil.parser import ParserError
import pycountry

logger = logging.getLogger(__name__)

DEFAULT_SKILL_TAXONOMY = {
    "js": "JavaScript",
    "javascript": "JavaScript",
    "reactjs": "React",
    "react.js": "React",
    "react": "React",
    "ts": "TypeScript",
    "typescript": "TypeScript",
    "golang": "Go",
    "go": "Go",
    "py": "Python",
    "python": "Python",
    "c++": "C++",
    "cpp": "C++",
    "c#": "C#",
    "csharp": "C#",
    "html5": "HTML",
    "html": "HTML",
    "css3": "CSS",
    "css": "CSS",
    "node": "Node.js",
    "nodejs": "Node.js",
    "node.js": "Node.js",
    "aws": "AWS",
    "amazon web services": "AWS",
    "k8s": "Kubernetes",
    "kubernetes": "Kubernetes",
    "java": "Java",
    "ruby": "Ruby",
    "php": "PHP"
}

def normalize_phone(raw: str, default_region: str = "IN") -> str | None:
    if not raw or not str(raw).strip():
        return None
    try:
        parsed = phonenumbers.parse(str(raw), default_region)
        if phonenumbers.is_valid_number(parsed):
            return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
        else:
            logger.debug("Parsed phone number is not valid: %s", raw)
            return None
    except phonenumbers.NumberParseException as e:
        logger.debug("Failed to parse phone number %s: %s", raw, e)
        return None

def normalize_date(raw: str) -> str | None:
    if not raw or not str(raw).strip():
        return None
    try:
        parsed = date_parser.parse(str(raw), default=None) 
        return parsed.strftime("%Y-%m")
    except (ParserError, ValueError, OverflowError, TypeError) as e:
        logger.debug("Failed to parse date %s: %s", raw, e)
        return None

def normalize_country(raw: str) -> str | None:
    if not raw or not str(raw).strip():
        return None
        
    raw_clean = str(raw).strip()
    
    aliases = {
        "usa": "US",
        "united states": "US",
        "united states of america": "US",
        "us": "US",
        "uk": "GB",
        "united kingdom": "GB",
        "great britain": "GB",
        "uae": "AE",
        "united arab emirates": "AE"
    }
    
    lower_raw = raw_clean.lower()
    if lower_raw in aliases:
        return aliases[lower_raw]
        
    try:
        country = pycountry.countries.get(name=raw_clean)
        if country:
            return country.alpha_2
            
        country = pycountry.countries.get(alpha_2=raw_clean.upper())
        if country:
            return country.alpha_2
            
        country = pycountry.countries.get(alpha_3=raw_clean.upper())
        if country:
            return country.alpha_2
            
        countries = pycountry.countries.search_fuzzy(raw_clean)
        if countries:
            return countries[0].alpha_2
    except LookupError:
        pass
    except Exception as e:
        logger.debug("Failed to normalize country %s: %s", raw, e)
        
    logger.debug("Could not match country: %s", raw)
    return None

def normalize_location(raw: str | dict) -> dict:
    """
    Returns {"city": str|None, "region": str|None, "country": str|None (ISO alpha-2)}.
    Rule-based split without geocoding API to keep it deterministic and dependency-free.
    """
    result = {"city": None, "region": None, "country": None}
    
    if not raw:
        return result
        
    if isinstance(raw, dict):
        city = raw.get("city")
        region = raw.get("region")
        country = raw.get("country")
        
        result["city"] = str(city).strip() if city else None
        result["region"] = str(region).strip() if region else None
        
        if country:
            norm_country = normalize_country(str(country))
            result["country"] = norm_country
        return result
        
    if isinstance(raw, str):
        parts = [p.strip() for p in raw.split(',') if p.strip()]
        if not parts:
            return result
            
        if len(parts) == 1:
            result["city"] = parts[0]
        elif len(parts) == 2:
            result["city"] = parts[0]
            result["country"] = normalize_country(parts[1])
            if not result["country"]:
                result["region"] = parts[1]
        else:
            result["city"] = parts[0]
            result["country"] = normalize_country(parts[-1])
            if result["country"]:
                result["region"] = ", ".join(parts[1:-1])
            else:
                result["region"] = ", ".join(parts[1:])
            
    return result

def normalize_skill(raw: str, taxonomy: dict[str, str] | None = None) -> str:
    if not raw or not str(raw).strip():
        return ""
        
    tax = taxonomy if taxonomy is not None else DEFAULT_SKILL_TAXONOMY
    
    clean = str(raw).strip().lower()
    if clean in tax:
        return tax[clean]
        
    # Title-Cased as a best-effort canonical form
    return str(raw).strip().title()

def normalize_name(raw: str) -> str:
    """
    Trim whitespace and collapse multiple spaces. 
    Leaves casing as provided by source because aggressive title-casing 
    risks corrupting names like "DeShawn" or "O'Brien".
    """
    if not raw:
        return ""
    return re.sub(r'\s+', ' ', str(raw)).strip()
