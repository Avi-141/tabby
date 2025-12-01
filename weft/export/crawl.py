"""HTML fetching and text extraction functions."""

import re
from typing import Optional

import requests

try:
    import trafilatura
except ImportError:
    trafilatura = None


def fetch_html_requests(url: str, timeout: int, user_agent: Optional[str] = None) -> str:
    """Fetch HTML content from URL using requests library."""
    headers = {}
    if user_agent:
        headers["User-Agent"] = user_agent
    resp = requests.get(url, headers=headers, timeout=timeout)
    resp.raise_for_status()
    content_type = resp.headers.get("content-type", "")
    if "text/html" not in content_type and "application/xhtml+xml" not in content_type:
        return ""
    return resp.text


def extract_text(html: str, url: str) -> str:
    """Extract readable text from HTML using trafilatura."""
    if trafilatura is None:
        raise ImportError("trafilatura is required. Install with: pip install trafilatura")

    text = trafilatura.extract(
        html,
        url=url,
        include_comments=False,
        include_tables=False,
        include_links=False,
    )
    if text:
        return text
    # Fallback for edge cases where trafilatura fails
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def truncate_text(text: str, max_chars: int) -> str:
    """Truncate text to max_chars, breaking at word boundary."""
    if len(text) <= max_chars:
        return text
    clipped = text[: max_chars - 1]
    last_space = clipped.rfind(" ")
    if last_space > 200:
        clipped = clipped[:last_space]
    return clipped
