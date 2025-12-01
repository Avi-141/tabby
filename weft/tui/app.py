"""Terminal UI for browsing a tab knowledge graph."""

import json
import os
import platform
import re
import subprocess
import webbrowser
from difflib import SequenceMatcher
from typing import Dict, List, Optional

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Footer, Header, Input, ListItem, ListView, Static


def load_graph(path: str) -> Dict:
    """Load graph from JSON file."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# Browser opening functions (from apply_groups.py)
def open_chrome_window(urls: List[str], chrome_path: Optional[str], dry_run: bool) -> None:
    """Open URLs in a new Chrome window."""
    if not urls:
        return
    system = platform.system().lower()
    if system == "darwin":
        if chrome_path and os.path.exists(chrome_path):
            cmd = [chrome_path, "--new-window"] + urls
        else:
            cmd = ["open", "-na", "Google Chrome", "--args", "--new-window"] + urls
    elif system == "windows":
        if not chrome_path:
            candidates = [
                os.path.join(os.environ.get("PROGRAMFILES", ""), "Google", "Chrome", "Application", "chrome.exe"),
                os.path.join(os.environ.get("PROGRAMFILES(X86)", ""), "Google", "Chrome", "Application", "chrome.exe"),
                os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "Chrome", "Application", "chrome.exe"),
            ]
            for candidate in candidates:
                if candidate and os.path.exists(candidate):
                    chrome_path = candidate
                    break
        if not chrome_path:
            raise FileNotFoundError("Chrome executable not found.")
        cmd = [chrome_path, "--new-window"] + urls
    else:
        raise RuntimeError("Unsupported OS for Chrome automation.")

    if dry_run:
        return
    subprocess.Popen(cmd)


def open_firefox_window(urls: List[str], firefox_path: Optional[str], dry_run: bool) -> None:
    """Open URLs in a new Firefox window."""
    if not urls:
        return

    # Build Firefox args
    args = []
    if urls:
        args = ["-new-window", urls[0]]
        for url in urls[1:]:
            args.extend(["-new-tab", url])

    system = platform.system().lower()
    if system == "darwin":
        if firefox_path and os.path.exists(firefox_path):
            cmd = [firefox_path] + args
        else:
            cmd = ["open", "-na", "Firefox", "--args"] + args
    elif system == "windows":
        if not firefox_path:
            candidates = [
                os.path.join(os.environ.get("PROGRAMFILES", ""), "Mozilla Firefox", "firefox.exe"),
                os.path.join(os.environ.get("PROGRAMFILES(X86)", ""), "Mozilla Firefox", "firefox.exe"),
                os.path.join(os.environ.get("LOCALAPPDATA", ""), "Mozilla Firefox", "firefox.exe"),
            ]
            for candidate in candidates:
                if candidate and os.path.exists(candidate):
                    firefox_path = candidate
                    break
        if not firefox_path:
            raise FileNotFoundError("Firefox executable not found.")
        cmd = [firefox_path] + args
    else:
        raise RuntimeError("Unsupported OS for Firefox automation.")

    if dry_run:
        return
    subprocess.Popen(cmd)


class TabGraphApp(App):
    """Main TUI application for browsing tab groups."""

    TITLE = "Weft"

    CSS = """
    Screen {
        background: #0b0f0e;
        color: #d6f5e3;
    }
    .pane {
        border: heavy #1f3a2e;
    }
    #groups, #tabs {
        height: 1fr;
    }
    #details, #graph_details {
        padding: 1 2;
    }
    #graph_text {
        padding: 1 2;
    }
    ListView {
        background: #0f1513;
    }
    ListItem {
        padding: 0 1;
    }
    ListItem.--highlight {
        background: #1f3a2e;
        color: #eafff4;
    }
    Input {
        background: #0f1513;
        border: heavy #1f3a2e;
        color: #eafff4;
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("o", "open_tab", "Open tab"),
        ("g", "open_group", "Open group"),
        ("c", "open_group_chrome", "Open Chrome"),
        ("f", "open_group_firefox", "Open Firefox"),
        ("[", "prev_group", "Prev group"),
        ("]", "next_group", "Next group"),
        ("{", "prev_tab", "Prev tab"),
        ("}", "next_tab", "Next tab"),
        ("v", "show_graph", "Graph view"),
    ]

    def __init__(self, graph: Dict):
        super().__init__()
        self.graph = graph
        self.groups = graph.get("groups", [])
        self.tabs = graph.get("tabs", [])
        self.edges = graph.get("edges", [])
        self.tab_by_id = {t.get("id"): t for t in self.tabs}
        self.group_by_id = {g.get("id"): g for g in self.groups}
        self.tab_to_group = {}
        for group in self.groups:
            gid = group.get("id")
            for tid in group.get("tab_ids", []):
                self.tab_to_group[tid] = gid
        self.selected_group_id = None
        self.selected_tab_id = None
        self.group_ids = []
        self.current_tab_ids = []
        self.selected_group_index = 0
        self.selected_tab_index = 0

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal():
            with Vertical(classes="pane", id="pane_groups"):
                yield Static("Groups", id="title_groups")
                yield ListView(id="groups")
            with Vertical(classes="pane", id="pane_tabs"):
                yield Static("Tabs", id="title_tabs")
                yield ListView(id="tabs")
            with Vertical(classes="pane", id="pane_details"):
                yield Static("Details", id="title_details")
                yield Static("Select a tab to view details.", id="details")
        yield Footer()

    async def on_mount(self) -> None:
        group_list = self.query_one("#groups", ListView)
        await group_list.clear()
        group_items = []
        for group in self.groups:
            label = f"{group.get('label', 'group')} ({len(group.get('tab_ids', []))})"
            group_items.append(ListItem(Static(label)))
        if group_items:
            await group_list.extend(group_items)
        self.group_ids = [g.get("id") for g in self.groups]
        if self.groups:
            await self.show_group(self.groups[0].get("id"))

    async def show_group(self, group_id: int) -> None:
        self.selected_group_id = group_id
        tab_list = self.query_one("#tabs", ListView)
        await tab_list.clear()
        group = self.group_by_id.get(group_id)
        if not group:
            return
        if group_id in self.group_ids:
            self.selected_group_index = self.group_ids.index(group_id)
        tab_items = []
        for tid in group.get("tab_ids", []):
            tab = self.tab_by_id.get(tid)
            if not tab:
                continue
            title = tab.get("title") or tab.get("url") or "(untitled)"
            tab_items.append(ListItem(Static(title)))
        if tab_items:
            await tab_list.extend(tab_items)
        self.current_tab_ids = list(group.get("tab_ids", []))
        if self.current_tab_ids:
            self.selected_tab_index = 0
            self.show_tab(self.current_tab_ids[0])

    def show_tab(self, tab_id: int) -> None:
        self.selected_tab_id = tab_id
        tab = self.tab_by_id.get(tab_id)
        if not tab:
            return
        if tab_id in self.current_tab_ids:
            self.selected_tab_index = self.current_tab_ids.index(tab_id)
        title = tab.get("title") or "(untitled)"
        url = tab.get("url") or ""
        summary = tab.get("summary") or ""
        keywords = ", ".join(tab.get("keywords", []))
        details = (
            f"[b]{title}[/b]\n"
            f"{url}\n\n"
            f"Summary:\n{summary or '(no summary)'}\n\n"
            f"Keywords: {keywords or '(none)'}"
        )
        self.query_one("#details", Static).update(details)

    async def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.list_view.id == "groups":
            if event.index is not None and 0 <= event.index < len(self.group_ids):
                await self.show_group(self.group_ids[event.index])
        elif event.list_view.id == "tabs":
            if event.index is not None and 0 <= event.index < len(self.current_tab_ids):
                self.show_tab(self.current_tab_ids[event.index])

    def action_open_tab(self) -> None:
        if self.selected_tab_id is None:
            return
        tab = self.tab_by_id.get(self.selected_tab_id)
        if tab and tab.get("url"):
            webbrowser.open(tab.get("url"))

    def action_open_group(self) -> None:
        if self.selected_group_id is None:
            return
        group = self.group_by_id.get(self.selected_group_id)
        if not group:
            return
        for tid in group.get("tab_ids", []):
            tab = self.tab_by_id.get(tid)
            if tab and tab.get("url"):
                webbrowser.open_new_tab(tab.get("url"))

    def action_open_group_chrome(self) -> None:
        self.open_group_in_browser("chrome")

    def action_open_group_firefox(self) -> None:
        self.open_group_in_browser("firefox")

    def open_group_in_browser(self, browser: str) -> None:
        if self.selected_group_id is None:
            return
        group = self.group_by_id.get(self.selected_group_id)
        if not group:
            return
        urls = [self.tab_by_id.get(tid, {}).get("url") for tid in group.get("tab_ids", [])]
        urls = [u for u in urls if u]
        if not urls:
            return
        try:
            if browser == "chrome":
                open_chrome_window(urls, None, False)
            else:
                open_firefox_window(urls, None, False)
        except Exception as exc:
            self.query_one("#details", Static).update(f"Open failed: {exc}")

    async def action_next_group(self) -> None:
        if not self.group_ids:
            return
        self.selected_group_index = min(self.selected_group_index + 1, len(self.group_ids) - 1)
        await self._select_group_by_index(self.selected_group_index)

    async def action_prev_group(self) -> None:
        if not self.group_ids:
            return
        self.selected_group_index = max(self.selected_group_index - 1, 0)
        await self._select_group_by_index(self.selected_group_index)

    def action_next_tab(self) -> None:
        if not self.current_tab_ids:
            return
        self.selected_tab_index = min(self.selected_tab_index + 1, len(self.current_tab_ids) - 1)
        self._select_tab_by_index(self.selected_tab_index)

    def action_prev_tab(self) -> None:
        if not self.current_tab_ids:
            return
        self.selected_tab_index = max(self.selected_tab_index - 1, 0)
        self._select_tab_by_index(self.selected_tab_index)

    async def _select_group_by_index(self, index: int) -> None:
        if not self.group_ids:
            return
        index = max(0, min(index, len(self.group_ids) - 1))
        group_id = self.group_ids[index]
        group_list = self.query_one("#groups", ListView)
        group_list.index = index
        await self.show_group(group_id)

    def _select_tab_by_index(self, index: int) -> None:
        if not self.current_tab_ids:
            return
        index = max(0, min(index, len(self.current_tab_ids) - 1))
        tab_id = self.current_tab_ids[index]
        tab_list = self.query_one("#tabs", ListView)
        if hasattr(tab_list, "index"):
            tab_list.index = index
        elif hasattr(tab_list, "highlighted"):
            tab_list.highlighted = index
        if hasattr(tab_list, "scroll_to_item"):
            tab_list.scroll_to_item(index)
        self.show_tab(tab_id)

    def action_show_graph(self) -> None:
        adjacency = self.build_group_adjacency()
        self.push_screen(GraphScreen(self.groups, self.group_by_id, self.tab_by_id, adjacency))

    def build_group_adjacency(self) -> Dict[int, List[tuple]]:
        weights: Dict[tuple, float] = {}
        for edge in self.edges:
            source = edge.get("source")
            target = edge.get("target")
            if source is None or target is None:
                continue
            ga = self.tab_to_group.get(source, self.tab_by_id.get(source, {}).get("group_id"))
            gb = self.tab_to_group.get(target, self.tab_by_id.get(target, {}).get("group_id"))
            if ga is None or gb is None or ga == gb:
                continue
            key = (min(ga, gb), max(ga, gb))
            weights[key] = weights.get(key, 0.0) + float(edge.get("weight", 0.0))
        adjacency: Dict[int, List[tuple]] = {gid: [] for gid in self.group_by_id}
        for (ga, gb), weight in weights.items():
            adjacency[ga].append((gb, weight))
            adjacency[gb].append((ga, weight))
        for gid in adjacency:
            adjacency[gid].sort(key=lambda t: t[1], reverse=True)
        return adjacency


class GraphScreen(Screen):
    """Secondary screen for graph visualization and search."""

    BINDINGS = [
        ("escape", "back", "Back"),
        ("q", "back", "Back"),
        ("/", "focus_search", "Search"),
        ("s", "focus_search", "Search"),
        ("g", "focus_groups", "Groups"),
        ("n", "focus_neighbors", "Neighbors"),
        ("m", "toggle_map", "Mini map"),
        ("c", "open_group_chrome", "Open Chrome"),
        ("f", "open_group_firefox", "Open Firefox"),
    ]

    def __init__(
        self,
        groups: List[Dict],
        group_by_id: Dict[int, Dict],
        tab_by_id: Dict[int, Dict],
        adjacency: Dict[int, List[tuple]],
    ):
        super().__init__()
        self.groups = groups
        self.group_by_id = group_by_id
        self.tab_by_id = tab_by_id
        self.adjacency = adjacency
        self.group_meta = self.build_group_meta()
        self.show_map = False
        self.group_ids = [
            g.get("id")
            for g in sorted(
                groups,
                key=lambda g: (len(g.get("tab_ids", [])), g.get("label", "")),
                reverse=True,
            )
        ]
        self.filtered_group_ids = list(self.group_ids)
        self.filtered_group_scores: Dict[int, float] = {}
        self.neighbor_ids: List[int] = []
        self.selected_group_id: Optional[int] = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal():
            with Vertical(classes="pane", id="graph_left"):
                yield Static("Graph Search", id="graph_title_search")
                yield Input(placeholder="Search (/). Use #tag and @domain.", id="graph_search")
                yield Static("Groups", id="graph_title_groups")
                yield ListView(id="graph_groups")
            with Vertical(classes="pane", id="graph_middle"):
                yield Static("Neighbors", id="graph_title_neighbors")
                yield ListView(id="graph_neighbors")
            with Vertical(classes="pane", id="graph_right"):
                yield Static("Details", id="graph_title_details")
                yield Static("Select a group to see details.", id="graph_details", markup=False)
        yield Footer()

    async def on_mount(self) -> None:
        await self.refresh_group_list()
        if self.filtered_group_ids:
            await self.set_group(self.filtered_group_ids[0])

    async def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id != "graph_search":
            return
        query = event.value.strip().lower()
        if not query:
            self.filtered_group_ids = list(self.group_ids)
            self.filtered_group_scores = {}
        else:
            self.filtered_group_ids = self.search_groups(query)
        await self.refresh_group_list()
        if self.filtered_group_ids:
            await self.set_group(self.filtered_group_ids[0])
        else:
            await self.clear_neighbors()
            self.selected_group_id = None
            self.query_one("#graph_details", Static).update("No groups match the search.")

    async def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.list_view.id == "graph_groups":
            if event.index is not None and 0 <= event.index < len(self.filtered_group_ids):
                await self.set_group(self.filtered_group_ids[event.index])
        elif event.list_view.id == "graph_neighbors":
            if event.index is not None and 0 <= event.index < len(self.neighbor_ids):
                await self.set_group(self.neighbor_ids[event.index])

    async def refresh_group_list(self) -> None:
        group_list = self.query_one("#graph_groups", ListView)
        await group_list.clear()
        items = []
        for gid in self.filtered_group_ids:
            group = self.group_by_id.get(gid, {})
            label = group.get("label", "group")
            size = len(group.get("tab_ids", []))
            score = self.filtered_group_scores.get(gid)
            if score is not None:
                items.append(ListItem(Static(f"[{gid}] {label} ({size})  score:{score:.2f}")))
            else:
                items.append(ListItem(Static(f"[{gid}] {label} ({size})")))
        if items:
            await group_list.extend(items)

    async def refresh_neighbors(self, gid: int) -> None:
        neighbor_list = self.query_one("#graph_neighbors", ListView)
        await neighbor_list.clear()
        self.neighbor_ids = []
        items = []
        for nb_gid, weight in self.adjacency.get(gid, [])[:30]:
            group = self.group_by_id.get(nb_gid, {})
            label = group.get("label", "group")
            size = len(group.get("tab_ids", []))
            items.append(ListItem(Static(f"{weight:.2f}  [{nb_gid}] {label} ({size})")))
            self.neighbor_ids.append(nb_gid)
        if items:
            await neighbor_list.extend(items)

    async def clear_neighbors(self) -> None:
        neighbor_list = self.query_one("#graph_neighbors", ListView)
        await neighbor_list.clear()
        self.neighbor_ids = []

    async def set_group(self, gid: int) -> None:
        self.selected_group_id = gid
        await self.refresh_neighbors(gid)
        self.update_details(gid)
        if gid in self.filtered_group_ids:
            group_list = self.query_one("#graph_groups", ListView)
            group_list.index = self.filtered_group_ids.index(gid)

    def update_details(self, gid: int) -> None:
        group = self.group_by_id.get(gid, {})
        label = group.get("label", "group")
        tab_ids = group.get("tab_ids", [])
        meta = self.group_meta.get(gid, {})
        sample_titles = []
        for tid in tab_ids[:5]:
            tab = self.tab_by_id.get(tid, {})
            title = tab.get("title") or tab.get("url") or "(untitled)"
            sample_titles.append(f"- {title}")
        neighbor_count = len(self.adjacency.get(gid, []))
        keywords = meta.get("keywords", [])
        domain = meta.get("domain", "")
        details = [
            f"Group [{gid}]",
            f"Label: {label}",
            f"Tabs: {len(tab_ids)}",
            f"Neighbors: {neighbor_count}",
            f"Domain: {domain or '(none)'}",
            f"Keywords: {', '.join(keywords[:6]) if keywords else '(none)'}",
            "",
            "Sample tabs:",
            *(sample_titles if sample_titles else ["- (none)"]),
        ]
        if self.show_map:
            details.append("")
            details.extend(self.render_mini_map(gid))
        self.query_one("#graph_details", Static).update("\n".join(details))

    def action_focus_search(self) -> None:
        self.query_one("#graph_search", Input).focus()

    def action_focus_groups(self) -> None:
        self.query_one("#graph_groups", ListView).focus()

    def action_focus_neighbors(self) -> None:
        self.query_one("#graph_neighbors", ListView).focus()

    def action_toggle_map(self) -> None:
        self.show_map = not self.show_map
        if self.selected_group_id is not None:
            self.update_details(self.selected_group_id)

    def action_back(self) -> None:
        self.app.pop_screen()

    def action_open_group_chrome(self) -> None:
        self.open_group_in_browser("chrome")

    def action_open_group_firefox(self) -> None:
        self.open_group_in_browser("firefox")

    def open_group_in_browser(self, browser: str) -> None:
        if self.selected_group_id is None:
            return
        group = self.group_by_id.get(self.selected_group_id)
        if not group:
            return
        urls = [self.tab_by_id.get(tid, {}).get("url") for tid in group.get("tab_ids", [])]
        urls = [u for u in urls if u]
        if not urls:
            return
        try:
            if browser == "chrome":
                open_chrome_window(urls, None, False)
            else:
                open_firefox_window(urls, None, False)
        except Exception as exc:
            self.query_one("#graph_details", Static).update(f"Open failed: {exc}")

    def build_group_meta(self) -> Dict[int, Dict]:
        meta: Dict[int, Dict] = {}
        for group in self.groups:
            gid = group.get("id")
            tab_ids = group.get("tab_ids", [])
            domains = []
            keywords = []
            titles = []
            for tid in tab_ids:
                tab = self.tab_by_id.get(tid, {})
                if tab.get("domain"):
                    domains.append(tab.get("domain"))
                keywords.extend(tab.get("keywords", []))
                title = tab.get("title") or tab.get("url") or ""
                if title:
                    titles.append(title)
            domain = ""
            if domains:
                counts = {}
                for d in domains:
                    counts[d] = counts.get(d, 0) + 1
                domain = max(counts.items(), key=lambda t: t[1])[0]
            keyword_counts = {}
            for k in keywords:
                keyword_counts[k] = keyword_counts.get(k, 0) + 1
            top_keywords = [k for k, _ in sorted(keyword_counts.items(), key=lambda t: t[1], reverse=True)[:12]]
            search_blob = " ".join([str(gid), group.get("label", ""), domain, " ".join(top_keywords), " ".join(titles[:10])]).lower()
            meta[gid] = {
                "domain": domain,
                "keywords": top_keywords,
                "search_blob": search_blob,
                "tokens": re.findall(r"[a-z0-9]+", search_blob),
            }
        return meta

    def parse_query(self, query: str) -> Dict[str, List[str]]:
        tags = re.findall(r"#([a-z0-9_-]+)", query)
        domains = re.findall(r"@([a-z0-9_.-]+)", query)
        cleaned = re.sub(r"[#@][a-z0-9_.-]+", " ", query)
        terms = [t for t in cleaned.split() if t]
        return {"tags": tags, "domains": domains, "terms": terms}

    def term_score(self, term: str, tokens: List[str], blob: str) -> float:
        if term in blob:
            return 1.0
        best = 0.0
        for token in tokens:
            score = SequenceMatcher(None, term, token).ratio()
            if score > best:
                best = score
        return best

    def search_groups(self, query: str) -> List[int]:
        parsed = self.parse_query(query)
        tags = parsed["tags"]
        domains = parsed["domains"]
        terms = parsed["terms"]

        results = []
        scores: Dict[int, float] = {}
        for gid in self.group_ids:
            meta = self.group_meta.get(gid, {})
            blob = meta.get("search_blob", "")
            tokens = meta.get("tokens", [])
            if domains:
                domain = meta.get("domain", "")
                if not any(d in domain or d in blob for d in domains):
                    continue
            if tags:
                keywords = set(meta.get("keywords", []))
                if not all(any(tag in kw for kw in keywords) for tag in tags):
                    continue
            if not terms:
                score = 1.0
            else:
                term_scores = [self.term_score(term, tokens, blob) for term in terms]
                if any(score < 0.45 for score in term_scores):
                    continue
                score = sum(term_scores) / len(term_scores)
            results.append(gid)
            scores[gid] = score

        results.sort(
            key=lambda g: (
                scores.get(g, 0.0),
                len(self.group_by_id.get(g, {}).get("tab_ids", [])),
            ),
            reverse=True,
        )
        self.filtered_group_scores = scores
        return results

    def render_mini_map(self, gid: int) -> List[str]:
        neighbors = self.adjacency.get(gid, [])[:8]
        label = self.group_by_id.get(gid, {}).get("label", "group")

        def weight_char(weight: float) -> str:
            if weight >= 0.8:
                return "#"
            if weight >= 0.6:
                return "+"
            if weight >= 0.4:
                return "-"
            return "."

        lines = ["Mini map:", f"* [{gid}] {label}"]
        if not neighbors:
            lines.append("  (no neighbors)")
            return lines
        for nb_gid, weight in neighbors:
            nb_label = self.group_by_id.get(nb_gid, {}).get("label", "group")
            lines.append(f"|--{weight_char(weight)}--> [{nb_gid}] {nb_label}")
        return lines
