#!/usr/bin/env python3
"""Download web-sized copies of explicitly reusable Wikimedia Commons images listed in data/media.json.

Uses Python standard library only. It resolves the original file URL through
the MediaWiki API, saves the binary under each asset's local_target, and writes
media/ATTRIBUTION.md.

It deliberately skips:
- OOPT images pending permission;
- entries whose reuse field does not start with "allowed";
- entries without a Wikimedia Commons source page;
- entries whose exact license still needs verification.
"""
from __future__ import annotations

import json
import sys
import time
import socket
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MEDIA_JSON = ROOT / "data" / "media.json"
ATTRIBUTION = ROOT / "media" / "ATTRIBUTION.md"
API = "https://commons.wikimedia.org/w/api.php"
USER_AGENT = "PeresheekGO-media-downloader/0.3 (licensed media import; contact via GitHub DariaZamotina/peresheek-go-data)"
REQUEST_DELAY = 3
MAX_RETRIES = 5
THUMB_WIDTH = 1600

ALLOWED_LICENSES = (
    "Public domain",
    "CC0",
    "CC BY ",
    "CC BY-SA ",
)


def commons_title(source_page: str) -> str:
    parsed = urllib.parse.urlparse(source_page)
    slug = urllib.parse.unquote(parsed.path.rsplit("/", 1)[-1])
    if not slug.startswith("File:"):
        raise ValueError("Not a Commons File page")
    return slug.replace("_", " ")


def open_with_retry(req, timeout=30):
    for attempt in range(MAX_RETRIES):
        try:
            return urllib.request.urlopen(req, timeout=timeout)
        except urllib.error.HTTPError as exc:
            if exc.code == 429 or 500 <= exc.code < 600:
                retry_after = exc.headers.get("Retry-After")
                wait = int(retry_after) if retry_after and retry_after.isdigit() else min(60, 5 * (2 ** attempt))
                print(f"WAIT HTTP {exc.code}; retry in {wait}s")
                time.sleep(wait)
                continue
            raise
        except (urllib.error.URLError, TimeoutError, socket.timeout):
            if attempt == MAX_RETRIES - 1:
                raise
            wait = min(60, 5 * (2 ** attempt))
            print(f"WAIT network error; retry in {wait}s")
            time.sleep(wait)
    raise RuntimeError("Retry limit exceeded")


def resolve_original(title: str) -> dict:
    query = urllib.parse.urlencode({
        "action": "query",
        "format": "json",
        "prop": "imageinfo",
        "iiprop": "url|extmetadata",
        "iiurlwidth": str(THUMB_WIDTH),
        "titles": title,
    })
    req = urllib.request.Request(f"{API}?{query}", headers={"User-Agent": USER_AGENT})
    with open_with_retry(req, timeout=30) as response:
        payload = json.load(response)
    page = next(iter(payload["query"]["pages"].values()))
    info = page.get("imageinfo", [None])[0]
    if not info or not (info.get("thumburl") or info.get("url")):
        raise RuntimeError(f"Commons did not return an image URL for {title}")
    return info


def download(url: str, target: Path) -> str:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and target.stat().st_size >= 1024:
        return "existing"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    tmp = target.with_suffix(target.suffix + ".part")
    try:
        with open_with_retry(req, timeout=45) as response, tmp.open("wb") as out:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                out.write(chunk)
        if tmp.stat().st_size < 1024:
            raise RuntimeError(f"Downloaded file is unexpectedly small: {tmp.stat().st_size} bytes")
        tmp.replace(target)
        return "downloaded"
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)


def main() -> int:
    data = json.loads(MEDIA_JSON.read_text(encoding="utf-8"))
    assets = data.get("reusable_assets", [])
    imported = []
    skipped = []
    failed = []

    for asset in assets:
        aid = asset.get("asset_id", "<unknown>")
        source = asset.get("source_page", "")
        license_name = asset.get("license", "")
        reuse = asset.get("reuse", "")
        local_target = asset.get("local_target")

        if not (
            source.startswith("https://commons.wikimedia.org/wiki/File:")
            and reuse.startswith("allowed")
            and local_target
            and any(license_name.startswith(x) for x in ALLOWED_LICENSES)
        ):
            skipped.append((aid, "license/source not eligible for automatic import"))
            continue

        try:
            target = ROOT / local_target
            if target.exists() and target.stat().st_size >= 1024:
                status = "existing"
            else:
                time.sleep(REQUEST_DELAY)
                title = commons_title(source)
                info = resolve_original(title)
                time.sleep(REQUEST_DELAY)
                status = download(info.get("thumburl") or info["url"], target)
            imported.append((asset, target.relative_to(ROOT).as_posix()))
            print(f"OK   {aid} ({status}) -> {target.relative_to(ROOT)}")
        except Exception as exc:
            failed.append((aid, str(exc)))
            print(f"FAIL {aid}: {exc}", file=sys.stderr)

    ATTRIBUTION.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Photo attribution",
        "",
        "This file is generated by `scripts/download_media.py`.",
        "Always keep this attribution information with redistributed images.",
        "",
    ]
    for asset, path in imported:
        place_ids = asset.get("place_ids") or [asset.get("place_id")]
        lines += [
            f"## {asset.get('asset_id')}",
            f"- Local file: `{path}`",
            f"- Place IDs: {', '.join(x for x in place_ids if x)}",
            f"- Author: {asset.get('author', 'See source page')}",
            f"- License: {asset.get('license')}",
            f"- License URL: {asset.get('license_url') or 'See source page'}",
            f"- Source: {asset.get('source_page')}",
            "",
        ]
    ATTRIBUTION.write_text("\n".join(lines), encoding="utf-8")

    print(f"\nImported: {len(imported)}; skipped: {len(skipped)}; failed: {len(failed)}")
    print(f"Attribution: {ATTRIBUTION.relative_to(ROOT)}")
    if skipped:
        print("\nSkipped:")
        for aid, why in skipped:
            print(f"  - {aid}: {why}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
