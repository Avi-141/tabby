#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build a small knowledge graph from exported tabs.

Usage:
  python3 build_graph.py tabs_backup.json --out tab_graph.json --llm-backend ollama --ollama-model llama3.1:8b
"""
import argparse
import hashlib
import json
import math
import os
import re
import sys
import time
from collections import Counter
from html.parser import HTMLParser
from typing import Dict, List, Optional, Tuple
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

import requests

try:
    import trafilatura
except Exception as exc:
    print("[ERROR] Missing dependency: trafilatura. Install with: pip install trafilatura", file=sys.stderr)
    raise

STOPWORDS = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and", "any", "are",
    "as", "at", "be", "because", "been", "before", "being", "below", "between", "both", "but",
    "by", "can", "did", "do", "does", "doing", "down", "during", "each", "few", "for", "from",
    "further", "had", "has", "have", "having", "he", "her", "here", "hers", "herself", "him",
    "himself", "his", "how", "i", "if", "in", "into", "is", "it", "its", "itself", "just",
    "me", "more", "most", "my", "myself", "no", "nor", "not", "now", "of", "off", "on",
    "once", "only", "or", "other", "our", "ours", "ourselves", "out", "over", "own", "same",
    "she", "should", "so", "some", "such", "than", "that", "the", "their", "theirs", "them",
    "themselves", "then", "there", "these", "they", "this", "those", "through", "to", "too",
    "under", "until", "up", "very", "was", "we", "were", "what", "when", "where", "which",
    "while", "who", "whom", "why", "with", "would", "you", "your", "yours", "yourself",
    "yourselves",
}

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
    parser = CanonicalLinkParser()
    try:
        parser.feed(html)
    except Exception:
        return None
    if parser.canonical_href:
        return urljoin(base_url, parser.canonical_href)
    return None


def is_http_url(url: str) -> bool:
    return url.startswith("http://") or url.startswith("https://")


def normalize_domain(url: str) -> str:
    parsed = urlparse(url)
    domain = parsed.netloc.lower().split(":")[0]
    if domain.startswith("www."):
        domain = domain[4:]
    return domain


def load_tabs(path: str) -> List[Dict]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    tabs: List[Dict] = []
    for w in data:
        browser = w.get("browser")
        window_id = w.get("windowId")
        for t in w.get("tabs", []):
            url = (t.get("url") or "").strip()
            if not url:
                continue
            title = (t.get("title") or "").strip()
            tab_id = len(tabs)
            canonical_url = canonicalize_url(url)
            tabs.append(
                {
                    "id": tab_id,
                    "url": url,
                    "title": title,
                    "browser": browser,
                    "window_id": window_id,
                    "domain": normalize_domain(url),
                    "canonical_url": canonical_url,
                }
            )
    return tabs


def fetch_html_requests(url: str, timeout: int, user_agent: Optional[str]) -> str:
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
    text = trafilatura.extract(
        html,
        url=url,
        include_comments=False,
        include_tables=False,
        include_links=False,
    )
    if text:
        return text
    # Fallback for edge cases where trafilatura fails.
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def truncate_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    clipped = text[: max_chars - 1]
    last_space = clipped.rfind(" ")
    if last_space > 200:
        clipped = clipped[:last_space]
    return clipped


def build_prompt(title: str, text: str) -> str:
    return (
        "Summarize the page in 2-3 sentences. Focus on what it is about and why it matters.\n"
        f"Title: {title or 'Untitled'}\n"
        f"Content:\n{text}\n\n"
        "Summary:"
    )


def build_embedding_text(title: str, summary: str, domain: str, fallback: str) -> str:
    parts = []
    if title:
        parts.append(f"Title: {title}")
    if summary:
        parts.append(f"Summary: {summary}")
    if domain:
        parts.append(f"Domain: {domain}")
    if not parts and fallback:
        parts.append(fallback)
    return "\n".join(parts)


def summarize_ollama(prompt: str, model: str, base_url: str, timeout: int) -> str:
    url = base_url.rstrip("/") + "/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.2, "num_predict": 200},
    }
    resp = requests.post(url, json=payload, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    return (data.get("response") or "").strip()


def embed_ollama(text: str, model: str, base_url: str, timeout: int) -> Optional[List[float]]:
    url = base_url.rstrip("/") + "/api/embeddings"
    payload = {"model": model, "prompt": text}
    resp = requests.post(url, json=payload, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    if "embedding" in data:
        return data.get("embedding")
    if "data" in data and data["data"]:
        return data["data"][0].get("embedding")
    return None


def build_llama(model_path: str, n_ctx: int, n_threads: int, n_gpu_layers: int):
    try:
        from llama_cpp import Llama
    except Exception as exc:
        print("[ERROR] Missing dependency: llama-cpp-python. Install with: pip install llama-cpp-python", file=sys.stderr)
        raise
    return Llama(
        model_path=model_path,
        n_ctx=n_ctx,
        n_threads=n_threads,
        n_gpu_layers=n_gpu_layers,
    )


def summarize_llama(llm, prompt: str) -> str:
    out = llm(prompt, max_tokens=220, temperature=0.2, stop=["\n\n", "Summary:"])
    return (out.get("choices") or [{}])[0].get("text", "").strip()


def cosine_similarity(a: Optional[List[float]], b: Optional[List[float]]) -> float:
    if not a or not b:
        return 0.0
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def fallback_summary(text: str, max_sentences: int = 3) -> str:
    if not text:
        return ""
    sentences = re.split(r"(?<=[.!?])\s+", text)
    sentences = [s.strip() for s in sentences if s.strip()]
    return " ".join(sentences[:max_sentences])


def tokenize(text: str) -> List[str]:
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    tokens = [t for t in text.split() if len(t) >= 3 and t not in STOPWORDS]
    return tokens


def simhash_from_tokens(tokens: List[str]) -> Optional[int]:
    if not tokens:
        return None
    vector = [0] * 64
    for token in tokens:
        digest = hashlib.md5(token.encode("utf-8")).digest()
        h = int.from_bytes(digest[:8], "big")
        for i in range(64):
            if (h >> i) & 1:
                vector[i] += 1
            else:
                vector[i] -= 1
    value = 0
    for i, score in enumerate(vector):
        if score > 0:
            value |= 1 << i
    return value


def hamming_distance(a: int, b: int) -> int:
    return (a ^ b).bit_count()


def extract_keywords(text: str, max_keywords: int) -> List[str]:
    tokens = tokenize(text)
    counts = Counter(tokens)
    return [w for w, _ in counts.most_common(max_keywords)]


def jaccard(a: List[str], b: List[str]) -> float:
    set_a, set_b = set(a), set(b)
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / len(set_a | set_b)


def similarity_score(ta: Dict, tb: Dict, domain_bonus: float) -> float:
    similarity = cosine_similarity(ta.get("embedding"), tb.get("embedding"))
    if similarity == 0.0:
        similarity = jaccard(ta.get("keywords", []), tb.get("keywords", []))
    if ta.get("domain") and ta.get("domain") == tb.get("domain"):
        similarity += domain_bonus
    return similarity


def build_similarity_matrix(tabs: List[Dict], domain_bonus: float) -> List[List[float]]:
    count = len(tabs)
    matrix = [[0.0 for _ in range(count)] for _ in range(count)]
    for i in range(count):
        for j in range(i + 1, count):
            score = similarity_score(tabs[i], tabs[j], domain_bonus)
            matrix[i][j] = score
            matrix[j][i] = score
    return matrix


def build_edges(
    tabs: List[Dict],
    similarity_matrix: List[List[float]],
    threshold: float,
) -> List[Dict]:
    edges: List[Dict] = []
    for i in range(len(tabs)):
        for j in range(i + 1, len(tabs)):
            weight = similarity_matrix[i][j]
            if weight >= threshold:
                reason = "similarity"
                if tabs[i].get("domain") == tabs[j].get("domain"):
                    reason = "similarity+domain"
                edges.append(
                    {
                        "source": tabs[i]["id"],
                        "target": tabs[j]["id"],
                        "weight": round(weight, 3),
                        "reason": reason,
                    }
                )
    return edges


def build_groups(
    tabs: List[Dict],
    similarity_matrix: List[List[float]],
    threshold: float,
    domain_group: bool,
    domain_group_min: int,
    mutual_knn: bool,
    knn_k: int,
) -> Tuple[List[Dict], Dict[int, int]]:
    parent = list(range(len(tabs)))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    if domain_group:
        domain_map: Dict[str, List[int]] = {}
        for idx, tab in enumerate(tabs):
            domain = tab.get("domain")
            if domain:
                domain_map.setdefault(domain, []).append(idx)
        for indices in domain_map.values():
            if len(indices) >= max(2, domain_group_min):
                root = indices[0]
                for idx in indices[1:]:
                    union(root, idx)

    if mutual_knn:
        neighbors = []
        for i in range(len(tabs)):
            scored = [(j, similarity_matrix[i][j]) for j in range(len(tabs)) if j != i]
            scored.sort(key=lambda t: t[1], reverse=True)
            filtered = [j for j, score in scored if score >= threshold]
            if knn_k > 0:
                filtered = filtered[:knn_k]
            neighbors.append(set(filtered))
        for i in range(len(tabs)):
            for j in neighbors[i]:
                if i in neighbors[j]:
                    union(i, j)
    else:
        for i in range(len(tabs)):
            for j in range(i + 1, len(tabs)):
                if similarity_matrix[i][j] >= threshold:
                    union(i, j)

    groups_map: Dict[int, List[int]] = {}
    for idx in range(len(tabs)):
        root = find(idx)
        groups_map.setdefault(root, []).append(idx)

    groups: List[Dict] = []
    tab_to_group: Dict[int, int] = {}
    for gid, (root, indices) in enumerate(groups_map.items()):
        group_tabs = [tabs[i] for i in indices]
        tab_ids = [t["id"] for t in group_tabs]
        groups.append(
            {
                "id": gid,
                "tab_ids": tab_ids,
                "size": len(tab_ids),
            }
        )
        for tid in tab_ids:
            tab_to_group[tid] = gid
    return groups, tab_to_group


def compute_idf(docs_tokens: List[List[str]]) -> Dict[str, float]:
    doc_count = len(docs_tokens)
    df = Counter()
    for tokens in docs_tokens:
        for token in set(tokens):
            df[token] += 1
    idf = {}
    for token, count in df.items():
        idf[token] = math.log((1 + doc_count) / (1 + count)) + 1.0
    return idf


def top_tfidf_terms(tokens: List[str], idf: Dict[str, float], max_terms: int) -> List[str]:
    tf = Counter(tokens)
    scored = []
    for token, count in tf.items():
        scored.append((token, count * idf.get(token, 0.0)))
    scored.sort(key=lambda t: t[1], reverse=True)
    return [token for token, _ in scored[:max_terms]]


def label_group(group_tabs: List[Dict], idf: Dict[str, float]) -> str:
    domains = [t.get("domain") for t in group_tabs if t.get("domain")]
    if domains:
        counts = Counter(domains)
        domain, count = counts.most_common(1)[0]
        if count / max(1, len(group_tabs)) >= 0.55:
            return domain
    tokens: List[str] = []
    for tab in group_tabs:
        tokens.extend(tab.get("tokens", []))
    top_terms = top_tfidf_terms(tokens, idf, 3)
    if top_terms:
        return " / ".join(top_terms)
    return "group"


def dedupe_tabs(tabs: List[Dict], hamming_threshold: int) -> Tuple[Dict[int, int], int]:
    parent = list(range(len(tabs)))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    canonical_map: Dict[str, int] = {}
    for idx, tab in enumerate(tabs):
        canonical = tab.get("canonical_url") or canonicalize_url(tab.get("url", ""))
        if not canonical:
            continue
        tab["canonical_url"] = canonical
        if canonical in canonical_map:
            union(idx, canonical_map[canonical])
        else:
            canonical_map[canonical] = idx

    for i in range(len(tabs)):
        sim_a = tabs[i].get("simhash")
        if sim_a is None:
            continue
        for j in range(i + 1, len(tabs)):
            sim_b = tabs[j].get("simhash")
            if sim_b is None:
                continue
            if tabs[i].get("domain") and tabs[i].get("domain") == tabs[j].get("domain"):
                if hamming_distance(sim_a, sim_b) <= hamming_threshold:
                    union(i, j)

    groups: Dict[int, List[int]] = {}
    for idx in range(len(tabs)):
        root = find(idx)
        groups.setdefault(root, []).append(idx)

    duplicates = 0
    primary_map: Dict[int, int] = {}
    for indices in groups.values():
        primary = min(indices)
        aliases = []
        for idx in indices:
            if idx != primary:
                duplicates += 1
                primary_map[idx] = primary
                aliases.append(tabs[idx].get("url"))
            else:
                primary_map[idx] = primary
        if aliases:
            primary_tab = tabs[primary]
            existing = set(primary_tab.get("aliases", []))
            for url in aliases:
                if url:
                    existing.add(url)
            primary_tab["aliases"] = sorted(existing)
            for idx in indices:
                if idx != primary:
                    tabs[idx]["duplicate_of"] = primary
                    if not tabs[idx].get("canonical_url"):
                        tabs[idx]["canonical_url"] = primary_tab.get("canonical_url")
    return primary_map, duplicates


def load_cache(path: Optional[str]) -> Dict[str, Dict]:
    if not path or not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_cache_entry(cache: Dict[str, Dict], url: str) -> Tuple[Optional[Dict], Optional[str]]:
    if not cache:
        return None, None
    for key in (url, canonicalize_url(url)):
        if key in cache:
            return cache[key], key
    return None, None


def save_cache(path: Optional[str], cache: Dict[str, Dict]) -> None:
    if not path:
        return
    dir_name = os.path.dirname(path)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("backup_json", help="Path to tabs_backup.json from export_tabs.py")
    ap.add_argument("--out", default="tab_graph.json", help="Output graph JSON path")
    ap.add_argument("--cache", default=os.path.join("data", "tab_graph_cache.json"), help="Cache file path")
    ap.add_argument("--refresh", action="store_true", help="Ignore cache and re-fetch")
    ap.add_argument("--limit", type=int, default=0, help="Limit number of tabs (0 = all)")
    ap.add_argument("--max-chars", type=int, default=6000, help="Max characters sent to LLM")
    ap.add_argument("--embed-max-chars", type=int, default=2000, help="Max characters sent to embed model")
    ap.add_argument("--edge-threshold", type=float, default=0.2, help="Edge weight threshold")
    ap.add_argument("--group-threshold", type=float, default=0.25, help="Grouping similarity threshold")
    ap.add_argument("--domain-bonus", type=float, default=0.25, help="Similarity bonus for same-domain tabs")
    ap.add_argument("--no-domain-group", action="store_true", help="Disable auto-grouping by domain")
    ap.add_argument("--domain-group-min", type=int, default=2, help="Min tabs per domain to auto-group")
    ap.add_argument("--knn-k", type=int, default=6, help="Mutual KNN size for grouping")
    ap.add_argument("--no-mutual-knn", action="store_true", help="Disable mutual-KNN grouping filter")
    ap.add_argument("--dedupe-hamming", type=int, default=3, help="Simhash Hamming distance for dedupe")
    ap.add_argument("--keyword-count", type=int, default=8, help="Number of keywords per tab")
    ap.add_argument("--user-agent", default="Mozilla/5.0", help="User-Agent for crawling")
    ap.add_argument("--timeout", type=int, default=20, help="HTTP timeout seconds")
    ap.add_argument("--llm-backend", choices=["ollama", "gguf"], default="ollama", help="LLM backend")
    ap.add_argument("--ollama-model", default="llama3.1:8b", help="Ollama model name")
    ap.add_argument("--ollama-url", default="http://localhost:11434", help="Ollama base URL")
    ap.add_argument("--ollama-timeout", type=int, default=120, help="Ollama request timeout")
    ap.add_argument("--embed-model", default="nomic-embed-text", help="Ollama embedding model name")
    ap.add_argument("--embed-url", default=None, help="Ollama base URL for embeddings")
    ap.add_argument("--embed-timeout", type=int, default=60, help="Embedding request timeout")
    ap.add_argument("--no-embeddings", action="store_true", help="Disable embeddings for similarity")
    ap.add_argument("--store-embeddings", action="store_true", help="Include embeddings in output JSON")
    ap.add_argument("--gguf", help="Path to a GGUF model file for llama-cpp-python")
    ap.add_argument("--llama-n-ctx", type=int, default=4096, help="Context size for llama-cpp")
    ap.add_argument("--llama-n-threads", type=int, default=max(1, os.cpu_count() or 1), help="Threads for llama-cpp")
    ap.add_argument("--llama-n-gpu-layers", type=int, default=0, help="GPU layers for llama-cpp")
    ap.add_argument("--js", action="store_true", help="Use Playwright to render JS-heavy pages")
    args = ap.parse_args()

    embed_url = args.embed_url or args.ollama_url
    embed_enabled = not args.no_embeddings

    tabs = load_tabs(args.backup_json)
    if args.limit and args.limit > 0:
        tabs = tabs[: args.limit]

    cache = load_cache(args.cache)

    llm = None
    if args.llm_backend == "gguf":
        if not args.gguf:
            print("[ERROR] --gguf is required when --llm-backend=gguf", file=sys.stderr)
            sys.exit(1)
        llm = build_llama(args.gguf, args.llama_n_ctx, args.llama_n_threads, args.llama_n_gpu_layers)

    playwright = None
    browser = None
    context = None
    if args.js:
        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:
            print("[ERROR] Playwright is required for --js. Install with: pip install playwright", file=sys.stderr)
            raise
        playwright = sync_playwright().start()
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(user_agent=args.user_agent)

    errors = 0
    embed_errors = 0
    embed_requests = 0
    embed_reused = 0
    embed_skipped = 0
    for tab in tabs:
        url = tab.get("url")
        if not url or not is_http_url(url):
            tab["summary"] = ""
            tab["error"] = "unsupported_url"
            continue

        cached, _ = get_cache_entry(cache, url)
        used_cache = False
        text = ""

        if cached and not args.refresh:
            tab["summary"] = cached.get("summary", "")
            tab["text_excerpt"] = cached.get("text_excerpt", "")
            tab["keywords"] = cached.get("keywords", [])
            tab["summary_source"] = cached.get("summary_source", "")
            tab["canonical_url"] = cached.get("canonical_url") or tab.get("canonical_url")
            tab["simhash"] = cached.get("simhash")
            if embed_enabled and cached.get("embedding") and cached.get("embedding_model") == args.embed_model:
                tab["embedding"] = cached.get("embedding")
                embed_reused += 1
            text = tab.get("text_excerpt", "")
            used_cache = True

        if not used_cache:
            try:
                if args.js and context:
                    page = context.new_page()
                    page.goto(url, wait_until="networkidle", timeout=args.timeout * 1000)
                    html = page.content()
                    page.close()
                else:
                    html = fetch_html_requests(url, args.timeout, args.user_agent)
            except Exception as exc:
                errors += 1
                tab["summary"] = ""
                tab["error"] = f"fetch_failed: {exc}"
                continue

            canonical = extract_canonical_url(html, url)
            if canonical:
                tab["canonical_url"] = canonicalize_url(canonical)
            else:
                tab["canonical_url"] = tab.get("canonical_url") or canonicalize_url(url)

            text = extract_text(html, url)
            text = text.strip()
            clipped = truncate_text(text, args.max_chars)
            prompt = build_prompt(tab.get("title", ""), clipped)
            summary = ""
            summary_source = ""

            try:
                if args.llm_backend == "ollama":
                    summary = summarize_ollama(prompt, args.ollama_model, args.ollama_url, args.ollama_timeout)
                    summary_source = f"ollama:{args.ollama_model}"
                else:
                    summary = summarize_llama(llm, prompt)
                    summary_source = f"gguf:{os.path.basename(args.gguf or '')}"
            except Exception as exc:
                errors += 1
                summary = fallback_summary(text)
                summary_source = "fallback"
                tab["error"] = f"summary_failed: {exc}"

            if not summary:
                summary = fallback_summary(text)
                summary_source = summary_source or "fallback"

            tab["summary"] = summary
            tab["summary_source"] = summary_source
            tab["text_excerpt"] = text[:400]
            tab["keywords"] = extract_keywords(f"{tab.get('title', '')} {summary}", args.keyword_count)

        if not tab.get("canonical_url"):
            tab["canonical_url"] = canonicalize_url(url)

        if not tab.get("keywords"):
            tab["keywords"] = extract_keywords(f"{tab.get('title', '')} {tab.get('summary', '')}", args.keyword_count)

        if "tokens" not in tab:
            base_text = f"{tab.get('title', '')} {tab.get('summary', '')} {tab.get('text_excerpt', '')}"
            tab["tokens"] = tokenize(base_text)

        if tab.get("simhash") is None:
            tab["simhash"] = simhash_from_tokens(tab.get("tokens", []))

        if embed_enabled and tab.get("embedding") is None:
            embed_text = build_embedding_text(
                tab.get("title", ""),
                tab.get("summary", ""),
                tab.get("domain", ""),
                tab.get("text_excerpt", ""),
            )
            embed_text = truncate_text(embed_text, args.embed_max_chars)
            if embed_text:
                try:
                    embed_requests += 1
                    tab["embedding"] = embed_ollama(embed_text, args.embed_model, embed_url, args.embed_timeout)
                except Exception as exc:
                    embed_errors += 1
                    tab["embedding"] = None
                    tab["embedding_error"] = str(exc)
            else:
                embed_skipped += 1

        cache_key = tab.get("canonical_url") or canonicalize_url(url)
        alt_key = canonicalize_url(url)
        if cache_key:
            entry = {
                "summary": tab.get("summary", ""),
                "summary_source": tab.get("summary_source", ""),
                "text_excerpt": tab.get("text_excerpt", ""),
                "keywords": tab.get("keywords", []),
                "canonical_url": tab.get("canonical_url"),
                "simhash": tab.get("simhash"),
                "embedding": tab.get("embedding"),
                "embedding_model": args.embed_model,
            }
            cache[cache_key] = entry
            if alt_key and alt_key != cache_key:
                cache[alt_key] = entry

    if context:
        context.close()
    if browser:
        browser.close()
    if playwright:
        playwright.stop()

    primary_map, duplicates = dedupe_tabs(tabs, args.dedupe_hamming)
    primary_tabs = [t for t in tabs if t.get("duplicate_of") is None]
    primary_docs = [t.get("tokens", []) for t in primary_tabs]
    idf = compute_idf(primary_docs) if primary_docs else {}

    similarity_matrix = build_similarity_matrix(primary_tabs, args.domain_bonus)
    edges = build_edges(primary_tabs, similarity_matrix, args.edge_threshold)
    groups_primary, tab_to_group_primary = build_groups(
        primary_tabs,
        similarity_matrix,
        args.group_threshold,
        domain_group=not args.no_domain_group,
        domain_group_min=args.domain_group_min,
        mutual_knn=not args.no_mutual_knn,
        knn_k=args.knn_k,
    )

    groups_map: Dict[int, List[int]] = {g.get("id"): [] for g in groups_primary}
    tab_by_id = {t.get("id"): t for t in tabs}
    for tab in tabs:
        primary_id = primary_map.get(tab.get("id"), tab.get("id"))
        group_id = tab_to_group_primary.get(primary_id, -1)
        tab["group_id"] = group_id
        if group_id in groups_map:
            groups_map[group_id].append(tab.get("id"))

    groups = []
    for group in groups_primary:
        gid = group.get("id")
        tab_ids = groups_map.get(gid, [])
        group_primary_tabs = [tab_by_id.get(tid) for tid in tab_ids if tab_by_id.get(tid)]
        group_primary_tabs = [t for t in group_primary_tabs if t.get("duplicate_of") is None]
        label = label_group(group_primary_tabs, idf)
        groups.append(
            {
                "id": gid,
                "label": label,
                "tab_ids": tab_ids,
                "size": len(tab_ids),
            }
        )

    for tab in tabs:
        tab.pop("tokens", None)
        if not args.store_embeddings:
            tab.pop("embedding", None)

    graph = {
        "schema_version": 1,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": os.path.basename(args.backup_json),
        "stats": {
            "tab_count": len(tabs),
            "group_count": len(groups),
            "edge_count": len(edges),
            "errors": errors,
            "embed_errors": embed_errors,
            "embed_requests": embed_requests,
            "embed_reused": embed_reused,
            "embed_skipped": embed_skipped,
            "duplicates": duplicates,
        },
        "tabs": tabs,
        "groups": groups,
        "edges": edges,
    }

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(graph, f, ensure_ascii=False, indent=2)

    save_cache(args.cache, cache)
    print(
        f"[OK] Wrote {args.out} with {len(tabs)} tabs, {len(groups)} groups, "
        f"{len(edges)} edges, {duplicates} duplicates, "
        f"{embed_requests} embeddings requested ({embed_reused} reused)."
    )


if __name__ == "__main__":
    main()
