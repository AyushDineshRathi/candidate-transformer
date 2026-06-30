"""
Resume PDF/DOCX extractor module.
Responsible for extracting candidate information from unstructured resumes via rule-based heuristics.
NOTE: This uses fragile heuristics (e.g. regex for emails/phones, assumes first line is name, scans for 'Skills'/'Education' headers).
It deliberately avoids ML/NLP/Transformers for scope alignment.
"""

import os
import re
import logging
import pdfplumber
import docx

from src.models import RawExtraction, Provenance
from src import normalizers

logger = logging.getLogger(__name__)

EMAIL_REGEX = r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+'
LOOSE_PHONE_REGEX = r'(?:\+?\d{1,3}[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}'

def extract_text(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    text = ""
    if ext == ".pdf":
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
    elif ext == ".docx":
        doc = docx.Document(path)
        for para in doc.paragraphs:
            text += para.text + "\n"
    else:
        logger.warning(f"Unsupported resume format: {ext}")
    return text

def extract_from_resume(path: str, conf_config: dict | None = None, canonicalizer=None) -> RawExtraction | None:
    try:
        text = extract_text(path)
    except Exception as e:
        logger.warning(f"Failed to parse resume {path}: {e}")
        return None

    cand_id = "RESUME-" + os.path.basename(path).replace(" ", "_")

    if not text.strip():
        # Scanned or empty file -> return Nones
        return RawExtraction(candidate_id=cand_id)

    ext_type = os.path.splitext(path)[1].lower().strip(".")
    source_name = "resume_" + ext_type
    
    if conf_config is None:
        conf_config = {}
    base_conf = conf_config.get(source_name, 0.6)
    skill_conf = conf_config.get("resume_skill_section", 0.4)
    
    prov_high = Provenance(source=source_name, source_field="raw_text", method="regex_heuristic_parser", confidence=base_conf)
    prov_low = Provenance(source=source_name, source_field="raw_text", method="regex_heuristic_parser", confidence=skill_conf)

    ext = RawExtraction(candidate_id=cand_id)

    lines = [line.strip() for line in text.split('\n') if line.strip()]

    # Extract Emails
    found_emails = re.findall(EMAIL_REGEX, text)
    if found_emails:
        ext.emails = [(email, prov_high) for email in set(found_emails)]

    # Extract Phones
    found_phones = re.findall(LOOSE_PHONE_REGEX, text)
    valid_phones = []
    for ph in set(found_phones):
        norm_ph = normalizers.normalize_phone(ph)
        if norm_ph:
            valid_phones.append((norm_ph, prov_high))
    if valid_phones:
        ext.phones = valid_phones

    # Full name heuristic: First short line with no digits and no email/phone match
    name_val = None
    for line in lines:
        if len(line.split()) > 4 or any(char.isdigit() for char in line):
            continue
        if re.search(EMAIL_REGEX, line) or re.search(LOOSE_PHONE_REGEX, line):
            continue
        # It's a plausible name
        name_val = line
        break
    
    if name_val:
        ext.full_name = (name_val, prov_high)

    # Section extraction
    in_skills = False
    in_edu = False
    skills_raw = []
    edu_raw = []

    KNOWN_SECTION_HEADERS = [
        "skills", "technical skills", "experience", "work experience", 
        "projects", "education", "achievements", "certifications", 
        "publications", "summary", "objective", "contact"
    ]

    def is_section_header(l: str) -> str | None:
        l_clean = re.sub(r'^[^a-zA-Z0-9]+', '', l).strip().lower().rstrip(":")
        if l_clean in KNOWN_SECTION_HEADERS:
            return l_clean
        return None

    for line in lines:
        header = is_section_header(line)
        if header:
            if header in ["skills", "technical skills"]:
                in_skills = True
                in_edu = False
            elif header == "education":
                in_edu = True
                in_skills = False
            else:
                in_skills = False
                in_edu = False
            continue

        if in_skills:
            if ':' in line:
                parts = line.split(':', 1)
                content = parts[1].strip()
            else:
                content = line.strip()

            if content:
                tokens = re.split(r'[,•|;]', content)
                for t in tokens:
                    t = t.strip()
                    if t:
                        skills_raw.append(t)
        elif in_edu:
            if len(line.split()) < 15:
                edu_raw.append(line)

    if skills_raw:
        valid_skills = []
        for s in set(skills_raw):
            if canonicalizer:
                from src.normalizers import normalize_skill_with_path
                canon_s, match_path = normalize_skill_with_path(s, canonicalizer)
                if not canon_s:
                    continue
                norm_s = canon_s
                prov_to_use = Provenance(
                    source=prov_low.source, 
                    source_field=prov_low.source_field, 
                    method=f"regex_heuristic_parser ({match_path})", 
                    confidence=prov_low.confidence
                )
            else:
                norm_s = normalizers.normalize_skill(s)
                prov_to_use = prov_low
                
            if not norm_s:
                continue
            
            words = norm_s.split()
            if len(words) > 4:
                logger.debug("Discarding skill (too long): %s", norm_s)
                continue
                
            if re.search(r'\d{3,}', norm_s):
                logger.debug("Discarding skill (digits-heavy): %s", norm_s)
                continue
                
            valid_skills.append((norm_s, prov_to_use))
            
        ext.skills = valid_skills
        
    if edu_raw:
        ext.education = [({"institution": edu}, prov_low) for edu in set(edu_raw)]

    return ext
