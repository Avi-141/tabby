"""Process raw tab export into a weft graph."""

import json
import sys
sys.path.insert(0, '.')

from weft.export.graph import GraphOptions, build_tab_graph, load_tabs_from_windows

def main():
    # Load raw export
    with open("weft_graph.json", "r") as f:
        windows = json.load(f)

    print(f"Loaded {len(windows)} windows")

    # Flatten to tabs
    tabs = load_tabs_from_windows(windows)
    print(f"Found {len(tabs)} tabs")

    # Build graph with default options (no crawl for speed)
    options = GraphOptions(
        out="weft_graph_processed.json",
        no_crawl=True,  # Use titles only, fast
        verbose=True,
    )

    graph = build_tab_graph(tabs, options)

    # Write output
    with open(options.out, "w", encoding="utf-8") as f:
        json.dump(graph, f, ensure_ascii=False, indent=2)

    stats = graph["stats"]
    print(f"\n[OK] Wrote {options.out}")
    print(f"     {stats['tab_count']} tabs, {stats['group_count']} groups, "
          f"{stats['edge_count']} edges, {stats['duplicates']} duplicates")

if __name__ == "__main__":
    main()
