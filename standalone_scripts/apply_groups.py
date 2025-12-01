#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Open grouped tabs from a tab_graph.json file.

By default, groups open as new browser windows (one window per group).
"""
import argparse
import json
import os
import platform
import subprocess
import sys
from typing import Dict, List, Optional, Tuple


def load_graph(path: str) -> Dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def find_chrome_path() -> Optional[str]:
    system = platform.system().lower()
    if system == "darwin":
        candidate = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
        return candidate if os.path.exists(candidate) else None
    if system == "windows":
        candidates = [
            os.path.join(os.environ.get("PROGRAMFILES", ""), "Google", "Chrome", "Application", "chrome.exe"),
            os.path.join(os.environ.get("PROGRAMFILES(X86)", ""), "Google", "Chrome", "Application", "chrome.exe"),
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "Chrome", "Application", "chrome.exe"),
        ]
        for candidate in candidates:
            if candidate and os.path.exists(candidate):
                return candidate
    return None


def find_firefox_path() -> Optional[str]:
    system = platform.system().lower()
    if system == "darwin":
        candidate = "/Applications/Firefox.app/Contents/MacOS/firefox"
        return candidate if os.path.exists(candidate) else None
    if system == "windows":
        candidates = [
            os.path.join(os.environ.get("PROGRAMFILES", ""), "Mozilla Firefox", "firefox.exe"),
            os.path.join(os.environ.get("PROGRAMFILES(X86)", ""), "Mozilla Firefox", "firefox.exe"),
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Mozilla Firefox", "firefox.exe"),
        ]
        for candidate in candidates:
            if candidate and os.path.exists(candidate):
                return candidate
    return None


def build_firefox_args(urls: List[str]) -> List[str]:
    if not urls:
        return []
    args = ["-new-window", urls[0]]
    for url in urls[1:]:
        args.extend(["-new-tab", url])
    return args


def open_chrome_window(urls: List[str], chrome_path: Optional[str], dry_run: bool) -> None:
    if not urls:
        return
    system = platform.system().lower()
    if system == "darwin":
        if chrome_path and os.path.exists(chrome_path):
            cmd = [chrome_path, "--new-window"] + urls
        else:
            cmd = ["open", "-na", "Google Chrome", "--args", "--new-window"] + urls
    elif system == "windows":
        chrome_path = chrome_path or find_chrome_path()
        if not chrome_path:
            raise FileNotFoundError("Chrome executable not found. Use --chrome-path to set it.")
        cmd = [chrome_path, "--new-window"] + urls
    else:
        raise RuntimeError("Unsupported OS for Chrome automation.")

    if dry_run:
        print("[DRY]", " ".join(cmd))
        return
    subprocess.Popen(cmd)


def open_firefox_window(urls: List[str], firefox_path: Optional[str], dry_run: bool) -> None:
    if not urls:
        return
    system = platform.system().lower()
    args = build_firefox_args(urls)
    if system == "darwin":
        if firefox_path and os.path.exists(firefox_path):
            cmd = [firefox_path] + args
        else:
            cmd = ["open", "-na", "Firefox", "--args"] + args
    elif system == "windows":
        firefox_path = firefox_path or find_firefox_path()
        if not firefox_path:
            raise FileNotFoundError("Firefox executable not found. Use --firefox-path to set it.")
        cmd = [firefox_path] + args
    else:
        raise RuntimeError("Unsupported OS for Firefox automation.")

    if dry_run:
        print("[DRY]", " ".join(cmd))
        return
    subprocess.Popen(cmd)


def iter_group_tabs(graph: Dict, browser: Optional[str], group_id: Optional[int]) -> List[Tuple[Dict, List[Dict]]]:
    tabs = graph.get("tabs", [])
    tab_by_id = {t.get("id"): t for t in tabs}
    output = []
    for group in graph.get("groups", []):
        if group_id is not None and group.get("id") != group_id:
            continue
        tab_ids = group.get("tab_ids", [])
        group_tabs = [tab_by_id.get(tid) for tid in tab_ids]
        group_tabs = [t for t in group_tabs if t]
        if browser:
            group_tabs = [t for t in group_tabs if t.get("browser") == browser]
        urls = [t.get("url") for t in group_tabs if t.get("url")]
        if urls:
            output.append((group, group_tabs))
    return output


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("graph_json", help="Path to tab_graph.json from build_graph.py")
    ap.add_argument("--chrome", action="store_true", help="Open groups in Chrome")
    ap.add_argument("--firefox", action="store_true", help="Open groups in Firefox")
    ap.add_argument("--chrome-path", help="Override Chrome executable path")
    ap.add_argument("--firefox-path", help="Override Firefox executable path")
    ap.add_argument("--group", type=int, help="Open a single group by id")
    ap.add_argument("--all-tabs", action="store_true", help="Open all tabs in the selected browser(s)")
    ap.add_argument("--dry-run", action="store_true", help="Print commands without launching")
    args = ap.parse_args()

    if not args.chrome and not args.firefox:
        args.chrome = True
        args.firefox = True

    graph = load_graph(args.graph_json)

    if args.chrome:
        groups = iter_group_tabs(graph, None if args.all_tabs else "chrome", args.group)
        for group, tabs in groups:
            urls = [t.get("url") for t in tabs if t.get("url")]
            open_chrome_window(urls, args.chrome_path, args.dry_run)

    if args.firefox:
        groups = iter_group_tabs(graph, None if args.all_tabs else "firefox", args.group)
        for group, tabs in groups:
            urls = [t.get("url") for t in tabs if t.get("url")]
            open_firefox_window(urls, args.firefox_path, args.dry_run)

    print("[OK] Opened groups.")


if __name__ == "__main__":
    main()
