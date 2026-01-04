# Weft

A local-first knowledge graph for your browsing.

Weft turns your browser tabs into a searchable, clustered knowledge graph. Instead of drowning in hundreds of tabs or flat bookmark lists, Weft groups related pages, removes duplicates, and lets you explore your browsing context visually.

**Think:** Obsidian graph view, but for the web you already opened.

## Two Ways to Use Weft

| | Chrome Extension | CLI (Python) |
|---|------------------|--------------|
| **Best for** | Live tracking, visual exploration | Batch processing, scripting |
| **Graph View** | Interactive sidepanel | Terminal UI |
| **Navigation Tracking** | Automatic | Manual export |
| **Install** | Load unpacked extension | `pip install weft-graph` |

---

## Chrome Extension

Live knowledge graph that tracks your browsing in real-time.

![Weft Extension Demo](https://raw.githubusercontent.com/Avi-141/weft/main/extension-demo.gif)

### Features

- **Live Tab Tracking** - Automatically captures tabs as you browse
- **Navigation Edges** - Tracks how you move between pages (including SPAs)
- **Graph Visualization** - Interactive Cytoscape.js graph with zoom/pan
- **Smart Grouping** - Clusters related pages by content similarity
- **Keyword Extraction** - Automatic keyword detection from page content
- **Search** - Fuzzy text, `#keyword`, and `@domain` filters
- **Import/Export** - Compatible with CLI JSON format

### Install Extension

1. Clone or download this repo
2. Open Chrome → `chrome://extensions`
3. Enable "Developer mode" (top right)
4. Click "Load unpacked" → select the `extension/` folder
5. Click the Weft icon or open sidepanel

### Extension Usage

**Views:**
- **Groups** - Browse tabs organized by topic clusters
- **Graph** - Visual knowledge graph with similarity and navigation edges

**Search Syntax:**
- Fuzzy: `distributed systems`
- Keyword: `#database`
- Domain: `@github.com`

**Actions:**
- Click any tab to see details (URL, keywords, group)
- Click "Open Tab" to open in browser
- Use refresh button to rebuild graph after browsing
- Export/Import for backup or CLI compatibility

---

## CLI Tool

Batch processing and terminal UI for exploring your knowledge graph.

![Weft CLI Demo](https://raw.githubusercontent.com/Avi-141/weft/main/demo.gif)

### Install CLI

```bash
pip install weft-graph
```

Or from source:

```bash
git clone https://github.com/Avi-141/weft.git
cd weft
pip install -e .
```

### Quick Start

```bash
# Build knowledge graph from your browser tabs
weft weave

# Explore in terminal UI
weft explore
```

### Commands

#### `weft weave`

Extracts tabs from browsers and weaves them into a knowledge graph.

```bash
# From all browsers (default)
weft weave

# Chrome only
weft weave --browser chrome

# Firefox only
weft weave --browser firefox

# With LLM summaries (requires Ollama)
weft weave --summarize

# Fast mode (tab titles only, no crawling)
weft weave --no-crawl
```

#### `weft explore`

Interactive TUI for exploring your knowledge graph.

```bash
# Default graph
weft explore

# Specific file
weft explore my_graph.json
```

#### Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `[` / `]` | Navigate groups |
| `{` / `}` | Navigate tabs in group |
| `o` | Open tab in browser |
| `g` | Open all tabs in group |
| `v` | Switch to graph view |
| `s` | Focus search |
| `q` | Quit |

---

## How It Works

```
Tabs → Extract → Analyze → Dedupe → Cluster → Graph → Explore
         │          │         │         │        │
         ▼          ▼         ▼         ▼        ▼
      Browser    Keywords   SimHash   Union   Similarity
       Tabs      Content    Matching   Find    + Navigation
```

1. **Extract** - Captures tabs from browser (live or batch)
2. **Analyze** - Extracts keywords from page content
3. **Deduplicate** - Canonical URL matching + SimHash for near-duplicates
4. **Cluster** - Groups by similarity using Union-Find algorithm
5. **Graph** - Builds similarity edges + navigation edges between pages
6. **Explore** - Visual graph or terminal UI for discovery

### Edge Types

| Type | Description | Visual |
|------|-------------|--------|
| **Similarity** | Pages with related content | Light edges |
| **Navigation** | You clicked from A to B | Bold edges |

### Similarity Computation

| Mode | Method |
|------|--------|
| Default | Jaccard similarity on keywords |
| With `--summarize` | Cosine similarity on embeddings |

A **domain bonus** (default: 0.25) is added when tabs share the same domain.

### Clustering Algorithm

Uses **Union-Find** with two strategies:

1. **Domain Pre-grouping** - Tabs from the same domain grouped together
2. **Mutual KNN** - Two tabs cluster only if they mutually consider each other neighbors

---

## Requirements

### Extension
- Chrome/Chromium browser

### CLI
- Python 3.9+
- macOS (browser export uses AppleScript)
- Chrome and/or Firefox

### Optional: LLM Summaries (CLI)

```bash
# Install Ollama
brew install ollama

# Pull models
ollama pull llama3.1:8b
ollama pull nomic-embed-text

# Use with summarization
weft weave --summarize
```

---

## Privacy

Weft is **fully local**. Your browsing data never leaves your machine:
- Extension uses IndexedDB (browser local storage)
- CLI stores data in local JSON files
- No analytics, no cloud sync, no external requests

## License

MIT
