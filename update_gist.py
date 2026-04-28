"""Publish daily records to a GitHub Gist.

External upload is disabled unless --confirm-upload is provided.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import urllib.request


def collect_records(records_dir: str | Path = "records") -> dict[str, str]:
    directory = Path(records_dir)
    files: dict[str, str] = {}
    if not directory.exists():
        return files
    for path in sorted(directory.glob("*.json")):
        files[path.name] = path.read_text(encoding="utf-8")
    return files


def update_gist(gist_id: str, token: str, files: dict[str, str]) -> dict:
    body = {
        "files": {
            name: {"content": content}
            for name, content in files.items()
        }
    }
    request = urllib.request.Request(
        f"https://api.github.com/gists/{gist_id}",
        data=json.dumps(body).encode("utf-8"),
        method="PATCH",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "User-Agent": "qqq-trading-system",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync records/*.json to a GitHub Gist")
    parser.add_argument("--records", default="records")
    parser.add_argument("--gist-id", default=os.environ.get("GIST_ID"))
    parser.add_argument("--token", default=os.environ.get("GITHUB_TOKEN"))
    parser.add_argument("--confirm-upload", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    files = collect_records(args.records)
    if not files:
        print("No record files found")
        return 0
    if not args.confirm_upload:
        print(f"Dry-run: {len(files)} files ready. Re-run with --confirm-upload to publish.")
        return 0
    if not args.gist_id or not args.token:
        raise SystemExit("GIST_ID and GITHUB_TOKEN are required")
    result = update_gist(args.gist_id, args.token, files)
    print(result.get("html_url", "Gist updated"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
