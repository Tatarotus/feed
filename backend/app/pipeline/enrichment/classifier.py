import re
from typing import Tuple, List

# Core technology acronyms that are allowed to be uppercase without triggering flags
ALLOWED_ACRONYMS = {
    "AI", "LLM", "CPU", "GPU", "OS", "PC", "IP", "CLI", "UI", "API", "RSS",
    "DB", "SQL", "ASR", "VHF", "RAM", "ROM", "SSD", "HDD", "URL", "JSON",
    "HTML", "CSS", "YAML", "CWD", "URI", "XML", "AWS", "NVIDIA", "AMD"
}

# Flashy emoji triggers
FLASHY_EMOJIS = {"🚨", "🔥", "🤯", "⚠️", "😱", "💥", "👇", "👀", "❌", "💯"}

# Case-insensitive sensational regex triggers
SENSATIONAL_PATTERNS = [
    re.compile(r"\bthis changes everything\b", re.IGNORECASE),
    re.compile(r"\byou won't believe\b", re.IGNORECASE),
    re.compile(r"\bstop doing\b", re.IGNORECASE),
    re.compile(r"\bdo this now\b", re.IGNORECASE),
    re.compile(r"\bnever do this\b", re.IGNORECASE),
    re.compile(r"\bthe death of\b", re.IGNORECASE),
    re.compile(r"\bkilled the\b", re.IGNORECASE),
    re.compile(r"\bcritical warning\b", re.IGNORECASE),
    re.compile(r"\bshocked me\b", re.IGNORECASE),
    re.compile(r"\bi was wrong\b", re.IGNORECASE),
    re.compile(r"\bsecrets they don't want you to know\b", re.IGNORECASE),
    re.compile(r"\bexposed\b", re.IGNORECASE),
    re.compile(r"\bgame changer\b", re.IGNORECASE)
]

PUNCTUATION_ABUSE_PATTERN = re.compile(r"!{2,}|(?:\?!|\!?){1,}")

def evaluate_all_caps(title: str) -> bool:
    """
    Check if the title has a high ratio of ALL CAPS letters, 
    excluding spaces, numbers, punctuation, and allowed tech acronyms.
    """
    if not title:
        return False
        
    # Strip known tech acronyms to prevent false positives
    words = title.split()
    filtered_words = [w for w in words if w.upper() not in ALLOWED_ACRONYMS]
    clean_title = " ".join(filtered_words)
    
    # Filter to alphabetic characters only
    alpha_chars = [c for c in clean_title if c.isalpha()]
    if not alpha_chars:
        return False
        
    uppercase_chars = [c for c in alpha_chars if c.isupper()]
    ratio = len(uppercase_chars) / len(alpha_chars)
    
    # Trigger if more than 30% of the remaining letters are uppercase
    return ratio > 0.30

def analyze_clickbait(title: str) -> Tuple[float, List[str]]:
    """
    Analyzes a video title against clickbait heuristic criteria.
    
    Returns:
        Tuple of (clickbait_score float from 0.0 to 1.0, reasons list of strings)
    """
    if not title:
        return 0.0, []

    reasons: List[str] = []
    score = 0.0

    # 1. Rule: High ratio of ALL CAPS letters
    if evaluate_all_caps(title):
        reasons.append("ALL_CAPS")
        score += 0.35

    # 2. Rule: Sensational/Exaggerated patterns
    sensational_match = False
    for pattern in SENSATIONAL_PATTERNS:
        if pattern.search(title):
            sensational_match = True
            break
    if sensational_match:
        reasons.append("SENSATIONAL_PHRASE")
        score += 0.40

    # 3. Rule: Multiple exclamation marks or exclamation/question hybrids (?! or !!)
    if PUNCTUATION_ABUSE_PATTERN.search(title):
        reasons.append("PUNCTUATION_ABUSE")
        score += 0.20

    # 4. Rule: Flashy emoji clutter (2 or more flashy emojis)
    emoji_count = sum(1 for char in title if char in FLASHY_EMOJIS)
    if emoji_count >= 2:
        reasons.append("EMOJI_CLUTTER")
        score += 0.25

    # 5. Rule: Shorts formatting indicators in titling (e.g. #shorts)
    if "#shorts" in title.lower() or "#short" in title.lower():
        reasons.append("SHORTS_FORMAT")
        score += 0.80

    # Cap score at 1.0
    final_score = min(score, 1.0)
    
    return final_score, reasons
