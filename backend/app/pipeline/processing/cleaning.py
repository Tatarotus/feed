import html
import re

# Regex patterns compiled once for performance
HTML_TAG_RE = re.compile(r'<[^>]+>')
WHITESPACE_RE = re.compile(r'\s+')

def strip_html_tags(text: str) -> str:
    """Strip standard HTML tags from strings."""
    if not text:
        return ""
    # Unescape HTML entities first (e.g. &amp; -> &)
    unescaped = html.unescape(text)
    return HTML_TAG_RE.sub(' ', unescaped)

def clean_and_normalize_text(text: str) -> str:
    """
    Strips markup, normalizes extra spaces/linebreaks,
    and sanitizes input text to support high-quality semantic vectors.
    """
    if not text:
        return ""

    # Strip HTML tags
    cleaned = strip_html_tags(text)

    # Strip non-printable/control chars but keep standard punctuation
    # (e.g. strip byte orders, excessive emoji strings if wanted, keep standard alphanumeric)
    # We normalize spacing here
    normalized = WHITESPACE_RE.sub(' ', cleaned)

    return normalized.strip()
