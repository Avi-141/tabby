#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'''Export open tabs from Google Chrome (all windows) and Firefox (current session) on macOS.
Outputs: tabs_backup.json next to this script (or --out path).
Chrome: Uses AppleScript (JXA) via `osascript -l JavaScript` (no deps).
Firefox: Reads sessionstore-backups/*.jsonlz4 (requires `pip install lz4`).

Usage:
  python3 export_tabs.py [--chrome] [--firefox] [--out tabs_backup.json]
  # optional overrides:
  python3 export_tabs.py --firefox-profile "/Users/me/Library/Application Support/Firefox/Profiles/xyz.default-release" -v

If no browser flags provided, both are attempted (errors are non-fatal).
'''
import argparse, json, os, subprocess, sys, configparser, glob, time
from pathlib import Path
from typing import List, Tuple, Optional

def run_jxa(script: str) -> str:
    try:
        p = subprocess.run(
            ['osascript', '-l', 'JavaScript', '-e', script],
            check=True, capture_output=True, text=True
        )
        return p.stdout.strip()
    except subprocess.CalledProcessError as e:
        raise RuntimeError(e.stderr.strip() or str(e))

def export_chrome():
    jxa = '''
    function run() {
      var app = Application.currentApplication();
      app.includeStandardAdditions = true;
      var output = [];
      try {
        var chrome = Application('Google Chrome');
        chrome.windows().forEach(function(w){
          var tabs = w.tabs().map(function(t){ return {title: t.title(), url: t.url()}; });
          if (tabs.length > 0) {
            output.push({browser: 'chrome', windowId: w.id(), tabs: tabs});
          }
        });
      } catch (e) {
        // Chrome not running or AppleScript disabled
      }
      return JSON.stringify(output);
    }
    '''
    out = run_jxa(jxa)
    return json.loads(out) if out else []

# ---------- Firefox helpers: scan all profiles, pick freshest sessionstore ----------

FF_BASE = Path.home() / 'Library' / 'Application Support' / 'Firefox' / 'Profiles'

def find_all_firefox_profiles() -> List[Path]:
    if not FF_BASE.exists():
        return []
    return [p for p in FF_BASE.iterdir() if p.is_dir()]

def best_sessionstore_for_profile(prof: Path) -> Optional[Tuple[Path, float]]:
    """Return (path, mtime) of the freshest sessionstore candidate or None."""
    candidates = []
    ssb = prof / 'sessionstore-backups'
    for name in ('recovery.jsonlz4', 'previous.jsonlz4'):
        p = ssb / name
        if p.exists():
            candidates.append(p)
    candidates.extend((ssb).glob('upgrade.jsonlz4*'))  # historical upgrades
    p_root = prof / 'sessionstore.jsonlz4'
    if p_root.exists():
        candidates.append(p_root)
    if not candidates:
        return None
    candidates = [(p, p.stat().st_mtime) for p in candidates if p.is_file()]
    if not candidates:
        return None
    candidates.sort(key=lambda t: t[1], reverse=True)
    return candidates[0]  # (path, mtime)

def choose_firefox_profile_with_fresh_session() -> Optional[Tuple[Path, Path]]:
    """Return (profile_dir, sessionstore_path) with the freshest valid session across all profiles."""
    profiles = find_all_firefox_profiles()
    scored = []
    for prof in profiles:
        best = best_sessionstore_for_profile(prof)
        if best:
            scored.append((prof, best[0], best[1]))  # (profile, path, mtime)
    if not scored:
        return None
    scored.sort(key=lambda t: t[2], reverse=True)
    return scored[0][0], scored[0][1]

def export_firefox(profile_override: Optional[str] = None, verbose: bool = False):
    try:
        from lz4.block import decompress as lz4_decompress
    except Exception as e:
        raise RuntimeError("Python package 'lz4' is required for Firefox export. Install with: pip install lz4") from e

    session_path: Optional[Path] = None
    selected_profile: Optional[Path] = None

    if profile_override:
        p = Path(profile_override).expanduser()
        if not p.exists():
            raise FileNotFoundError(f'Provided --firefox-profile does not exist: {p}')
        best = best_sessionstore_for_profile(p)
        if not best:
            raise FileNotFoundError(f'No sessionstore files found in provided profile: {p}')
        selected_profile, session_path = p, best[0]
    else:
        chosen = choose_firefox_profile_with_fresh_session()
        if not chosen:
            raise FileNotFoundError('No Firefox sessionstore *.jsonlz4 files found in ANY profile. '
                                    'Open Firefox (non-private window), ensure tabs are open, wait 10s, and try again.')
        selected_profile, session_path = chosen

    if verbose:
        print(f'[INFO] Using Firefox profile: {selected_profile}')
        print(f'[INFO] Sessionstore file:    {session_path} (mtime={time.ctime(session_path.stat().st_mtime)})')

    raw = session_path.read_bytes()
    if raw[:8] != b'mozLz40\x00':
        raise RuntimeError('Unexpected Firefox sessionstore header; not mozlz4.')

    from lz4.block import decompress as lz4_decompress  # local import kept above for error message
    decomp = lz4_decompress(raw[8:])
    session = json.loads(decomp.decode('utf-8'))

    windows = session.get('windows', [])
    payload = []
    for w in windows:
        tabs = []
        for t in w.get('tabs', []):
            idx = t.get('index', 1)
            entries = t.get('entries', [])
            if 1 <= idx <= len(entries):
                e = entries[idx-1]
                url = e.get('url', '')
                title = e.get('title', '')
                if url:
                    tabs.append({'title': title, 'url': url})
        if tabs:
            payload.append({'browser': 'firefox', 'windowId': None, 'tabs': tabs})
    return payload

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--chrome', action='store_true', help='Export Chrome windows/tabs')
    ap.add_argument('--firefox', action='store_true', help='Export Firefox windows/tabs')
    ap.add_argument('--firefox-profile', help='Override: path to a specific Firefox profile directory')
    ap.add_argument('--out', default='tabs_backup.json', help='Output JSON file path')
    ap.add_argument('-v', '--verbose', action='store_true', help='Verbose logging')
    args = ap.parse_args()

    if not args.chrome and not args.firefox:
        args.chrome = True
        args.firefox = True

    all_data = []
    had_error = False

    if args.chrome:
        try:
            all_data.extend(export_chrome())
        except Exception as e:
            had_error = True
            print(f'[WARN] Chrome export failed: {e}', file=sys.stderr)

    if args.firefox:
        try:
            all_data.extend(export_firefox(args.firefox_profile, args.verbose))
        except Exception as e:
            had_error = True
            print(f'[WARN] Firefox export failed: {e}', file=sys.stderr)

    with open(args.out, 'w', encoding='utf-8') as f:
        json.dump(all_data, f, ensure_ascii=False, indent=2)

    print(f'[OK] Wrote {args.out} with {sum(len(w.get("tabs", [])) for w in all_data)} tabs across {len(all_data)} windows.')
    if had_error:
        print('[NOTE] Some browsers failed to export; see warnings above.', file=sys.stderr)

if __name__ == '__main__':
    main()
