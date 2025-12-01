"""CLI dispatcher for weft."""

import argparse
import json
import os
import sys

from weft import __version__


def cmd_weave(args):
    """Build knowledge graph from browser tabs."""
    from weft.export.browser import export_chrome, export_firefox
    from weft.export.graph import GraphOptions, build_tab_graph, load_tabs_from_windows

    # Export from browsers
    windows = []
    had_error = False

    if args.browser in ("chrome", "all"):
        try:
            chrome_windows = export_chrome()
            windows.extend(chrome_windows)
            if args.verbose:
                tab_count = sum(len(w.get("tabs", [])) for w in chrome_windows)
                print(f"[INFO] Exported {tab_count} tabs from Chrome", file=sys.stderr)
        except Exception as e:
            had_error = True
            print(f"[WARN] Chrome export failed: {e}", file=sys.stderr)

    if args.browser in ("firefox", "all"):
        try:
            firefox_windows = export_firefox(args.firefox_profile, args.verbose)
            windows.extend(firefox_windows)
            if args.verbose:
                tab_count = sum(len(w.get("tabs", [])) for w in firefox_windows)
                print(f"[INFO] Exported {tab_count} tabs from Firefox", file=sys.stderr)
        except Exception as e:
            had_error = True
            print(f"[WARN] Firefox export failed: {e}", file=sys.stderr)

    if not windows:
        print("[ERROR] No tabs exported from any browser.", file=sys.stderr)
        sys.exit(1)

    # Flatten to tabs
    tabs = load_tabs_from_windows(windows)

    if args.verbose:
        print(f"[INFO] Processing {len(tabs)} tabs...", file=sys.stderr)

    # Build graph options
    options = GraphOptions(
        out=args.out,
        cache=args.cache,
        refresh=args.refresh,
        no_crawl=args.no_crawl,
        max_chars=args.max_chars,
        embed_max_chars=args.embed_max_chars,
        user_agent=args.user_agent,
        timeout=args.timeout,
        js=args.js,
        summarize=args.summarize,
        llm_backend=args.llm_backend,
        ollama_model=args.ollama_model,
        ollama_url=args.ollama_url,
        ollama_timeout=args.ollama_timeout,
        embed_model=args.embed_model,
        embed_url=args.embed_url,
        embed_timeout=args.embed_timeout,
        no_embeddings=args.no_embeddings,
        store_embeddings=args.store_embeddings,
        gguf=args.gguf,
        llama_n_ctx=args.llama_n_ctx,
        llama_n_threads=args.llama_n_threads,
        llama_n_gpu_layers=args.llama_n_gpu_layers,
        edge_threshold=args.edge_threshold,
        group_threshold=args.group_threshold,
        domain_bonus=args.domain_bonus,
        no_domain_group=args.no_domain_group,
        domain_group_min=args.domain_group_min,
        knn_k=args.knn_k,
        no_mutual_knn=args.no_mutual_knn,
        dedupe_hamming=args.dedupe_hamming,
        keyword_count=args.keyword_count,
        verbose=args.verbose,
    )

    # Build graph
    graph = build_tab_graph(tabs, options)

    # Write output
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(graph, f, ensure_ascii=False, indent=2)

    stats = graph["stats"]
    mode = "with LLM summaries" if args.summarize else "lightweight (keywords only)"
    print(
        f"[OK] Wrote {args.out} {mode}\n"
        f"     {stats['tab_count']} tabs, {stats['group_count']} groups, "
        f"{stats['edge_count']} edges, {stats['duplicates']} duplicates"
    )
    if stats["errors"]:
        print(f"     {stats['errors']} errors during processing", file=sys.stderr)
    if had_error:
        print("[NOTE] Some browsers failed to export; see warnings above.", file=sys.stderr)


def cmd_explore(args):
    """Launch the terminal UI."""
    from weft.tui.app import TabGraphApp, load_graph

    if not os.path.exists(args.graph_json):
        print(f"[ERROR] Graph file not found: {args.graph_json}", file=sys.stderr)
        print("Run 'weft weave' first to generate the graph.", file=sys.stderr)
        sys.exit(1)

    graph = load_graph(args.graph_json)
    app = TabGraphApp(graph)
    app.run()


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="weft",
        description="A local-first knowledge graph for your browsing",
    )
    parser.add_argument("--version", action="version", version=f"weft {__version__}")

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Weave command
    weave_parser = subparsers.add_parser(
        "weave",
        help="Build knowledge graph from browser tabs",
        description="Extract tabs from Chrome/Firefox and weave them into a knowledge graph with clustering.",
    )

    # Browser options
    weave_parser.add_argument(
        "--browser",
        choices=["chrome", "firefox", "all"],
        default="all",
        help="Which browser(s) to export from (default: all)",
    )
    weave_parser.add_argument(
        "--firefox-profile",
        help="Override: path to a specific Firefox profile directory",
    )

    # Output options
    weave_parser.add_argument(
        "--out",
        default="weft_graph.json",
        help="Output graph JSON path (default: weft_graph.json)",
    )

    # LLM options
    weave_parser.add_argument(
        "--summarize",
        action="store_true",
        help="Enable LLM summarization (requires Ollama or GGUF model)",
    )
    weave_parser.add_argument(
        "--llm-backend",
        choices=["ollama", "gguf"],
        default="ollama",
        help="LLM backend (default: ollama)",
    )
    weave_parser.add_argument(
        "--ollama-model",
        default="llama3.1:8b",
        help="Ollama model name (default: llama3.1:8b)",
    )
    weave_parser.add_argument(
        "--ollama-url",
        default="http://localhost:11434",
        help="Ollama base URL",
    )
    weave_parser.add_argument(
        "--ollama-timeout",
        type=int,
        default=120,
        help="Ollama request timeout in seconds",
    )
    weave_parser.add_argument(
        "--gguf",
        help="Path to a GGUF model file (for --llm-backend=gguf)",
    )
    weave_parser.add_argument(
        "--llama-n-ctx",
        type=int,
        default=4096,
        help="Context size for llama-cpp",
    )
    weave_parser.add_argument(
        "--llama-n-threads",
        type=int,
        default=max(1, os.cpu_count() or 1),
        help="Threads for llama-cpp",
    )
    weave_parser.add_argument(
        "--llama-n-gpu-layers",
        type=int,
        default=0,
        help="GPU layers for llama-cpp",
    )

    # Embedding options
    weave_parser.add_argument(
        "--embed-model",
        default="nomic-embed-text",
        help="Ollama embedding model name",
    )
    weave_parser.add_argument(
        "--embed-url",
        help="Ollama base URL for embeddings (defaults to --ollama-url)",
    )
    weave_parser.add_argument(
        "--embed-timeout",
        type=int,
        default=60,
        help="Embedding request timeout",
    )
    weave_parser.add_argument(
        "--no-embeddings",
        action="store_true",
        help="Disable embeddings (use keyword similarity only)",
    )
    weave_parser.add_argument(
        "--store-embeddings",
        action="store_true",
        help="Include embeddings in output JSON",
    )

    # Crawling options
    weave_parser.add_argument(
        "--no-crawl",
        action="store_true",
        help="Skip URL crawling (use metadata only)",
    )
    weave_parser.add_argument(
        "--max-chars",
        type=int,
        default=6000,
        help="Max characters sent to LLM",
    )
    weave_parser.add_argument(
        "--embed-max-chars",
        type=int,
        default=2000,
        help="Max characters sent to embed model",
    )
    weave_parser.add_argument(
        "--user-agent",
        default="Mozilla/5.0",
        help="User-Agent for HTTP requests",
    )
    weave_parser.add_argument(
        "--timeout",
        type=int,
        default=20,
        help="HTTP timeout in seconds",
    )
    weave_parser.add_argument(
        "--js",
        action="store_true",
        help="Use Playwright to render JS-heavy pages",
    )

    # Caching options
    weave_parser.add_argument(
        "--cache",
        default=os.path.join("data", "weft_cache.json"),
        help="Cache file path",
    )
    weave_parser.add_argument(
        "--refresh",
        action="store_true",
        help="Ignore cache and re-fetch everything",
    )

    # Clustering options
    weave_parser.add_argument(
        "--edge-threshold",
        type=float,
        default=0.2,
        help="Edge weight threshold",
    )
    weave_parser.add_argument(
        "--group-threshold",
        type=float,
        default=0.25,
        help="Grouping similarity threshold",
    )
    weave_parser.add_argument(
        "--domain-bonus",
        type=float,
        default=0.25,
        help="Similarity bonus for same-domain tabs",
    )
    weave_parser.add_argument(
        "--no-domain-group",
        action="store_true",
        help="Disable auto-grouping by domain",
    )
    weave_parser.add_argument(
        "--domain-group-min",
        type=int,
        default=2,
        help="Min tabs per domain to auto-group",
    )
    weave_parser.add_argument(
        "--knn-k",
        type=int,
        default=6,
        help="Mutual KNN size for grouping",
    )
    weave_parser.add_argument(
        "--no-mutual-knn",
        action="store_true",
        help="Disable mutual-KNN grouping filter",
    )
    weave_parser.add_argument(
        "--dedupe-hamming",
        type=int,
        default=3,
        help="Simhash Hamming distance for dedupe",
    )
    weave_parser.add_argument(
        "--keyword-count",
        type=int,
        default=8,
        help="Number of keywords per tab",
    )

    # General options
    weave_parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Verbose logging",
    )

    # Explore command
    explore_parser = subparsers.add_parser(
        "explore",
        help="Launch terminal UI to explore the graph",
        description="Interactive terminal UI for browsing and searching grouped tabs.",
    )
    explore_parser.add_argument(
        "graph_json",
        nargs="?",
        default="weft_graph.json",
        help="Path to graph JSON file (default: weft_graph.json)",
    )

    # Parse and dispatch
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    if args.command == "weave":
        cmd_weave(args)
    elif args.command == "explore":
        cmd_explore(args)


if __name__ == "__main__":
    main()
