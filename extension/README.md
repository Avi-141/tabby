# Weft Browser Extension

Chrome extension for real-time browser tab knowledge graph.

## Features

- **Live Tab Tracking** - Automatically tracks tabs as you browse
- **Navigation Edges** - Captures link clicks to build explicit connections
- **Keyword Extraction** - Extracts keywords from page content
- **Smart Clustering** - Groups related tabs using Union-Find + Mutual KNN
- **Graph Visualization** - Interactive Cytoscape.js graph view
- **Search** - Fuzzy text, `#keyword`, and `@domain` filters
- **Import/Export** - Compatible with weft CLI JSON format

## Installation

### Development Mode

1. Open Chrome and navigate to `chrome://extensions/`
2. Enable "Developer mode" (toggle in top right)
3. Click "Load unpacked"
4. Select the `extension` directory

### Icon Generation (Optional)

The extension includes SVG icons but Chrome prefers PNG. To generate PNGs:

```bash
# Using ImageMagick
convert icons/icon16.svg icons/icon16.png
convert icons/icon48.svg icons/icon48.png
convert icons/icon128.svg icons/icon128.png
```

Then update `manifest.json` to include the icons section.

## Usage

1. Click the Weft icon in Chrome toolbar to open the side panel
2. Browse normally - tabs are tracked automatically
3. Click "Refresh" to rebuild the graph with clustering
4. Use search to filter by text, `#keyword`, or `@domain`
5. Switch between Groups and Graph views
6. Click on tabs/nodes to see details
7. Import/Export to share with the CLI tool

## Architecture

```
extension/
├── manifest.json        # Extension configuration
├── background.js        # Service worker (tab tracking, clustering)
├── content.js           # Content script (text extraction)
├── lib/
│   ├── text.js          # Tokenization, SimHash, keywords
│   ├── url.js           # URL canonicalization
│   ├── clustering.js    # Union-Find, similarity, grouping
│   └── storage.js       # IndexedDB wrapper
└── sidepanel/
    ├── index.html       # Side panel UI
    ├── styles.css       # Styling
    └── app.js           # UI logic, Cytoscape graph
```

## Data Storage

All data is stored locally in IndexedDB:
- **tabs** - Tab metadata, keywords, simhash
- **edges** - Similarity and navigation connections
- **groups** - Clustered tab groups
- **navigations** - Raw navigation events

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `/` | Focus search |
| `Esc` | Close details panel |

## Compatibility

- Chrome 114+ (Side Panel API)
- Chromium-based browsers (Edge, Brave, etc.)

## Permissions

- `tabs` - Access tab URLs and titles
- `activeTab` - Inject content script
- `storage` - Local settings
- `sidePanel` - Side panel UI
- `webNavigation` - Track navigation events
- `<all_urls>` - Extract content from pages
