#!/usr/bin/env python3
"""Clone or remove repositories listed in a JSON file into category folders.

Usage examples:
  python clone_repos.py                  # uses git_links_de1.json in cwd
  python clone_repos.py path/to/file.json --base-dir repos
    python clone_repos.py --remove-all
  python clone_repos.py --help
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import shutil
import stat
from typing import Dict, Any


def clone_repo(url: str, dest: str) -> bool:
    try:
        subprocess.run(["git", "clone", url, dest], check=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Failed to clone {url}: {e}", file=sys.stderr)
        return False


def load_links(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def iter_destinations(data: Dict[str, Any], base_dir: str):
    for category, repos in data.items():
        if not isinstance(repos, dict):
            print(f"Skipping category {category}: expected object of numbered entries", file=sys.stderr)
            continue
        for key in sorted(repos.keys(), key=lambda k: int(k) if str(k).isdigit() else str(k)):
            url = repos[key]
            dest_dir = os.path.join(base_dir, category, str(key))
            yield category, key, url, dest_dir


def remove_repo(dest: str) -> bool:
    def _on_rm_error(func, path, exc_info):
        try:
            os.chmod(path, stat.S_IWRITE)
            func(path)
        except OSError:
            raise exc_info[1]

    try:
        if os.path.isdir(dest):
            shutil.rmtree(dest, onerror=_on_rm_error)
        elif os.path.exists(dest):
            try:
                os.chmod(dest, stat.S_IWRITE)
            except OSError:
                pass
            os.remove(dest)
        return True
    except OSError as e:
        print(f"Failed to remove {dest}: {e}", file=sys.stderr)
        return False


def main() -> int:
    p = argparse.ArgumentParser(description="Clone git repos from a JSON index into category folders")
    p.add_argument("json_file", nargs="?", default="git_links_de1.json", help="JSON file with links")
    p.add_argument("--base-dir", "-d", default=".", help="Base directory to create category folders in")
    p.add_argument("--skip-existing", action="store_true", help="Skip cloning when destination exists and is not empty")
    p.add_argument("--remove-all", action="store_true", help="Remove all cloned repository folders from the JSON index")
    args = p.parse_args()

    if not os.path.isfile(args.json_file):
        print(f"JSON file not found: {args.json_file}", file=sys.stderr)
        return 2

    try:
        data = load_links(args.json_file)
    except Exception as e:
        print(f"Failed to read JSON: {e}", file=sys.stderr)
        return 3

    if args.remove_all:
        for category, key, url, dest_dir in iter_destinations(data, args.base_dir):
            if os.path.exists(dest_dir):
                print(f"Removing {dest_dir}")
                ok = remove_repo(dest_dir)
                if not ok:
                    print(f"Error removing {dest_dir}; continuing", file=sys.stderr)
        print("All done.")
        return 0

    for category, key, url, dest_dir in iter_destinations(data, args.base_dir):
        if os.path.exists(dest_dir):
            if args.skip_existing:
                print(f"Skipping existing {dest_dir}")
                continue
            if os.path.isdir(dest_dir) and os.listdir(dest_dir):
                print(f"Destination {dest_dir} exists and not empty; skipping")
                continue

        os.makedirs(os.path.dirname(dest_dir), exist_ok=True)
        print(f"Cloning {url} -> {dest_dir}")
        ok = clone_repo(url, dest_dir)
        if not ok:
            print(f"Error cloning {url}; continuing", file=sys.stderr)

    print("All done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
