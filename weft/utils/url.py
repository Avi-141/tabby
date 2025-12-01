"""URL utility functions for canonicalization and normalization."""

from html.parser import HTMLParser
from typing import List, Optional, Tuple
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

TRACKING_PARAMS = {
    "fbclid",
    "gclid",
    "igshid",
    "mc_cid",
    "mc_eid",
    "msclkid",
    "ref",
    "ref_src",
    "utm_campaign",
    "utm_content",
    "utm_medium",
    "utm_source",
    "utm_term",
}


class CanonicalLinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.canonical_href: Optional[str] = None

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        if tag.lower() != "link":
            return
        attr_map = {k.lower(): v for k, v in attrs if k}
        rel = (attr_map.get("rel") or "").lower()
        if "canonical" not in rel.split():
            return
        href = attr_map.get("href")
        if href and not self.canonical_href:
            self.canonical_href = href.strip()


def canonicalize_url(url: str) -> str:
    """Normalize URL by removing tracking params, www prefix, trailing slashes."""
    try:
        parsed = urlparse(url)
    except Exception:
        return url
    scheme = (parsed.scheme or "https").lower()
    netloc = (parsed.netloc or "").lower()
    if ":" in netloc:
        host, port = netloc.rsplit(":", 1)
        if (scheme == "http" and port == "80") or (scheme == "https" and port == "443"):
            netloc = host
    if netloc.startswith("www."):
        netloc = netloc[4:]
    path = parsed.path or "/"
    if path != "/" and path.endswith("/"):
        path = path[:-1]
    params = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        key_l = key.lower()
        if key_l in TRACKING_PARAMS or key_l.startswith("utm_"):
            continue
        params.append((key, value))
    params.sort()
    query = urlencode(params, doseq=True)
    return urlunparse((scheme, netloc, path, "", query, ""))


def extract_canonical_url(html: str, base_url: str) -> Optional[str]:
    """Extract canonical URL from HTML link tag."""
    parser = CanonicalLinkParser()
    try:
        parser.feed(html)
    except Exception:
        return None
    if parser.canonical_href:
        return urljoin(base_url, parser.canonical_href)
    return None


def is_http_url(url: str) -> bool:
    """Check if URL is HTTP or HTTPS."""
    return url.startswith("http://") or url.startswith("https://")


def normalize_domain(url: str) -> str:
    """Extract and normalize domain from URL."""
    parsed = urlparse(url)
    domain = parsed.netloc.lower().split(":")[0]
    if domain.startswith("www."):
        domain = domain[4:]
    return domain
