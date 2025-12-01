"""Main graph building orchestrator."""

import os
import sys
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from weft.export.cache import get_cache_entry, load_cache, save_cache
from weft.export.crawl import extract_text, fetch_html_requests, truncate_text
from weft.export.llm import (
    build_embedding_text,
    build_llama,
    build_prompt,
    embed_ollama,
    summarize_llama,
    summarize_ollama,
)
from weft.export.similarity import (
    build_edges,
    build_groups,
    build_similarity_matrix,
    compute_idf,
    dedupe_tabs,
    label_group,
)
from weft.utils.text import (
    extract_keywords,
    fallback_summary,
    simhash_from_tokens,
    tokenize,
)
from weft.utils.url import (
    canonicalize_url,
    extract_canonical_url,
    is_http_url,
    normalize_domain,
)


@dataclass
class GraphOptions:
    """Options for graph building."""

    # Output
    out: str = "weft_graph.json"

    # Caching
    cache: str = field(default_factory=lambda: os.path.join("data", "weft_cache.json"))
    refresh: bool = False

    # Crawling
    no_crawl: bool = False
    max_chars: int = 6000
    embed_max_chars: int = 2000
    user_agent: str = "Mozilla/5.0"
    timeout: int = 20
    js: bool = False

    # LLM (only used with --summarize)
    summarize: bool = False
    llm_backend: str = "ollama"
    ollama_model: str = "llama3.1:8b"
    ollama_url: str = "http://localhost:11434"
    ollama_timeout: int = 120
    embed_model: str = "nomic-embed-text"
    embed_url: Optional[str] = None
    embed_timeout: int = 60
    no_embeddings: bool = False
    store_embeddings: bool = False
    gguf: Optional[str] = None
    llama_n_ctx: int = 4096
    llama_n_threads: int = field(default_factory=lambda: max(1, os.cpu_count() or 1))
    llama_n_gpu_layers: int = 0

    # Similarity/Clustering
    edge_threshold: float = 0.2
    group_threshold: float = 0.25
    domain_bonus: float = 0.25
    no_domain_group: bool = False
    domain_group_min: int = 2
    knn_k: int = 6
    no_mutual_knn: bool = False
    dedupe_hamming: int = 3
    keyword_count: int = 8

    # Verbose
    verbose: bool = False


def load_tabs_from_windows(windows: List[Dict]) -> List[Dict]:
    """Flatten window/tab structure into a list of tabs with metadata."""
    tabs: List[Dict] = []
    for w in windows:
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


def build_tab_graph(tabs: List[Dict], options: GraphOptions) -> Dict:
    """Build knowledge graph from tabs.

    With options.summarize=False (default): Lightweight mode using keywords only.
    With options.summarize=True: Full mode with LLM summaries and embeddings.
    """
    use_llm = options.summarize
    embed_enabled = use_llm and not options.no_embeddings
    embed_url = options.embed_url or options.ollama_url

    # Load cache
    cache = load_cache(options.cache) if not options.refresh else {}

    # Build LLM if needed
    llm = None
    if use_llm and options.llm_backend == "gguf":
        if not options.gguf:
            print("[ERROR] --gguf is required when --llm-backend=gguf", file=sys.stderr)
            sys.exit(1)
        llm = build_llama(
            options.gguf,
            options.llama_n_ctx,
            options.llama_n_threads,
            options.llama_n_gpu_layers,
        )

    # Setup Playwright if needed
    playwright = None
    browser = None
    context = None
    if options.js and not options.no_crawl:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            print(
                "[ERROR] Playwright is required for --js. Install with: pip install playwright",
                file=sys.stderr,
            )
            raise
        playwright = sync_playwright().start()
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(user_agent=options.user_agent)

    # Stats
    errors = 0
    embed_errors = 0
    embed_requests = 0
    embed_reused = 0
    embed_skipped = 0

    # Process each tab
    for tab in tabs:
        url = tab.get("url")

        if not url or not is_http_url(url):
            tab["summary"] = ""
            tab["error"] = "unsupported_url"
            continue

        # Check cache
        cached, _ = get_cache_entry(cache, url)
        used_cache = False
        text = ""

        if cached and not options.refresh:
            tab["summary"] = cached.get("summary", "")
            tab["text_excerpt"] = cached.get("text_excerpt", "")
            tab["keywords"] = cached.get("keywords", [])
            tab["summary_source"] = cached.get("summary_source", "")
            tab["canonical_url"] = cached.get("canonical_url") or tab.get("canonical_url")
            tab["simhash"] = cached.get("simhash")
            if embed_enabled and cached.get("embedding") and cached.get("embedding_model") == options.embed_model:
                tab["embedding"] = cached.get("embedding")
                embed_reused += 1
            text = tab.get("text_excerpt", "")
            used_cache = True

        # Crawl if not cached and not skipping crawl
        if not used_cache and not options.no_crawl:
            try:
                if options.js and context:
                    page = context.new_page()
                    page.goto(url, wait_until="networkidle", timeout=options.timeout * 1000)
                    html = page.content()
                    page.close()
                else:
                    html = fetch_html_requests(url, options.timeout, options.user_agent)
            except Exception as exc:
                errors += 1
                tab["summary"] = ""
                tab["error"] = f"fetch_failed: {exc}"
                if options.verbose:
                    print(f"[WARN] Fetch failed for {url}: {exc}", file=sys.stderr)
                continue

            # Extract canonical URL
            canonical = extract_canonical_url(html, url)
            if canonical:
                tab["canonical_url"] = canonicalize_url(canonical)
            else:
                tab["canonical_url"] = tab.get("canonical_url") or canonicalize_url(url)

            # Extract text
            text = extract_text(html, url).strip()
            clipped = truncate_text(text, options.max_chars)

            # Generate summary
            summary = ""
            summary_source = ""

            if use_llm:
                prompt = build_prompt(tab.get("title", ""), clipped)
                try:
                    if options.llm_backend == "ollama":
                        summary = summarize_ollama(
                            prompt, options.ollama_model, options.ollama_url, options.ollama_timeout
                        )
                        summary_source = f"ollama:{options.ollama_model}"
                    else:
                        summary = summarize_llama(llm, prompt)
                        summary_source = f"gguf:{os.path.basename(options.gguf or '')}"
                except Exception as exc:
                    errors += 1
                    summary = fallback_summary(text)
                    summary_source = "fallback"
                    tab["error"] = f"summary_failed: {exc}"
                    if options.verbose:
                        print(f"[WARN] Summary failed for {url}: {exc}", file=sys.stderr)

            if not summary:
                summary = fallback_summary(text)
                summary_source = summary_source or "fallback"

            tab["summary"] = summary
            tab["summary_source"] = summary_source
            tab["text_excerpt"] = text[:400]
            tab["keywords"] = extract_keywords(
                f"{tab.get('title', '')} {summary}", options.keyword_count
            )

        # Handle no-crawl mode
        if options.no_crawl and not used_cache:
            tab["summary"] = ""
            tab["summary_source"] = "none"
            tab["text_excerpt"] = ""
            tab["keywords"] = extract_keywords(tab.get("title", ""), options.keyword_count)

        # Ensure canonical URL
        if not tab.get("canonical_url"):
            tab["canonical_url"] = canonicalize_url(url)

        # Ensure keywords
        if not tab.get("keywords"):
            tab["keywords"] = extract_keywords(
                f"{tab.get('title', '')} {tab.get('summary', '')}", options.keyword_count
            )

        # Compute tokens and simhash
        if "tokens" not in tab:
            base_text = f"{tab.get('title', '')} {tab.get('summary', '')} {tab.get('text_excerpt', '')}"
            tab["tokens"] = tokenize(base_text)

        if tab.get("simhash") is None:
            tab["simhash"] = simhash_from_tokens(tab.get("tokens", []))

        # Generate embeddings if enabled
        if embed_enabled and tab.get("embedding") is None:
            embed_text = build_embedding_text(
                tab.get("title", ""),
                tab.get("summary", ""),
                tab.get("domain", ""),
                tab.get("text_excerpt", ""),
            )
            embed_text = truncate_text(embed_text, options.embed_max_chars)
            if embed_text:
                try:
                    embed_requests += 1
                    tab["embedding"] = embed_ollama(
                        embed_text, options.embed_model, embed_url, options.embed_timeout
                    )
                except Exception as exc:
                    embed_errors += 1
                    tab["embedding"] = None
                    tab["embedding_error"] = str(exc)
                    if options.verbose:
                        print(f"[WARN] Embedding failed for {url}: {exc}", file=sys.stderr)
            else:
                embed_skipped += 1

        # Update cache
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
                "embedding_model": options.embed_model,
            }
            cache[cache_key] = entry
            if alt_key and alt_key != cache_key:
                cache[alt_key] = entry

    # Cleanup Playwright
    if context:
        context.close()
    if browser:
        browser.close()
    if playwright:
        playwright.stop()

    # Deduplicate tabs
    primary_map, duplicates = dedupe_tabs(tabs, options.dedupe_hamming)
    primary_tabs = [t for t in tabs if t.get("duplicate_of") is None]

    # Compute IDF
    primary_docs = [t.get("tokens", []) for t in primary_tabs]
    idf = compute_idf(primary_docs) if primary_docs else {}

    # Build similarity matrix and edges
    similarity_matrix = build_similarity_matrix(primary_tabs, options.domain_bonus)
    edges = build_edges(primary_tabs, similarity_matrix, options.edge_threshold)

    # Build groups
    groups_primary, tab_to_group_primary = build_groups(
        primary_tabs,
        similarity_matrix,
        options.group_threshold,
        domain_group=not options.no_domain_group,
        domain_group_min=options.domain_group_min,
        mutual_knn=not options.no_mutual_knn,
        knn_k=options.knn_k,
    )

    # Assign groups to all tabs (including duplicates)
    groups_map: Dict[int, List[int]] = {g.get("id"): [] for g in groups_primary}
    tab_by_id = {t.get("id"): t for t in tabs}
    for tab in tabs:
        primary_id = primary_map.get(tab.get("id"), tab.get("id"))
        group_id = tab_to_group_primary.get(primary_id, -1)
        tab["group_id"] = group_id
        if group_id in groups_map:
            groups_map[group_id].append(tab.get("id"))

    # Build final groups with labels
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

    # Clean up tabs for output
    for tab in tabs:
        tab.pop("tokens", None)
        if not options.store_embeddings:
            tab.pop("embedding", None)

    # Build graph
    graph = {
        "schema_version": 1,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": "weft",
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

    # Save cache
    save_cache(options.cache, cache)

    return graph
