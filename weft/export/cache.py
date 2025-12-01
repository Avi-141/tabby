"""Cache management for tab graph building."""

import json
import os
from typing import Dict, Optional, Tuple

from weft.utils.url import canonicalize_url


def load_cache(path: Optional[str]) -> Dict[str, Dict]:
    """Load cache from JSON file."""
    if not path or not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_cache_entry(
    cache: Dict[str, Dict], url: str
) -> Tuple[Optional[Dict], Optional[str]]:
    """Get cache entry for URL, trying both original and canonical forms."""
    if not cache:
        return None, None
    for key in (url, canonicalize_url(url)):
        if key in cache:
            return cache[key], key
    return None, None


def save_cache(path: Optional[str], cache: Dict[str, Dict]) -> None:
    """Save cache to JSON file."""
    if not path:
        return
    dir_name = os.path.dirname(path)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)
