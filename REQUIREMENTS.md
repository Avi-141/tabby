# Functional and Non-Functional Requirements

This document captures the functional requirements (FRs) and non-functional requirements (NFRs)
for the tab migrator + knowledge graph app.

## Functional Requirements (FRs)
- Export open tabs from Chrome and Firefox into a JSON backup file.
- Import/restore tabs from a JSON backup into Chrome and Firefox.
- Ingest tab JSON and normalize fields (url, title, browser, window, domain).
- Crawl URLs and extract readable text for each tab.
- Generate summaries with a local LLM (Ollama or GGUF backend).
- Generate embeddings with a local model to power similarity and clustering.
- Build a knowledge graph JSON with tabs, groups, and edges.
- Deduplicate tabs using canonical URLs and near-duplicate text (simhash).
- Cluster tabs into groups using similarity, with configurable thresholds.
- Label groups with domain-aware or keyword-based labels.
- Cache summaries/embeddings for reuse across runs.
- Provide a TUI to browse groups, tabs, and summaries.
- Provide a graph view in the TUI with neighbor navigation.
- Support fuzzy search, #tag filtering, and @domain filtering in the graph view.
- Open grouped tabs in Chrome and Firefox on demand.
- Optional JS rendering for JS-heavy pages.

## Non-Functional Requirements (NFRs)
- Local-first processing: summaries and embeddings run locally by default.
- Privacy: no telemetry; network access only for fetching the URLs supplied by the user.
- Cross-platform: graph build and TUI run on macOS and Windows; browser open actions on both.
- Performance: handle ~100 tabs comfortably; cache results to avoid repeat work.
- Reliability: continue on partial failures (fetch/summary/embed); record errors per tab.
- Usability: CLI commands are simple and discoverable; TUI is fully keyboard-driven.
- Maintainability: graph output is JSON with a stable schema and versioning.
- Security: do not execute page scripts unless JS mode is explicitly enabled.
