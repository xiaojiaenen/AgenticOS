"""Sync design systems from nexu-io/open-design repository.

Usage:
    uv run python scripts/sync_design_systems.py              # sync all
    uv run python scripts/sync_design_systems.py --brands stripe,linear-app,apple  # specific brands
    uv run python scripts/sync_design_systems.py --list       # list available brands
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
from pathlib import Path
from urllib import request
from urllib.error import HTTPError, URLError

REPO = "nexu-io/open-design"
BRANCH = "main"
API_BASE = f"https://api.github.com/repos/{REPO}"

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TARGET_DIR = PROJECT_ROOT / "data" / "design-systems"

# Brands known to be complete (have both DESIGN.md and tokens.css)
CURATED_BRANDS = [
    "stripe", "linear-app", "vercel", "apple", "notion", "airbnb",
    "supabase", "cursor", "figma", "spotify", "github", "claude",
    "tesla", "nike", "shopify", "framer", "raycast", "coinbase",
    "posthog", "sentry", "replicate", "mistral", "elevenlabs",
    "intercom", "superhuman", "miro", "airtable", "zapier",
    "warp", "discord", "canva", "binance", "mastercard",
    "playstation", "uber", "pinterest", "webflow", "lamborghini",
    "ferrari", "bugatti", "bmw", "spacex", "nvidia", "ibm",
    "hashicorp", "mongodb", "clickhouse", "expo", "lovable",
    "sanity", "mintlify", "composio", "cal", "clay",
    "default", "brutalism", "corporate", "creative", "clean",
    "bold", "bento", "cosmic", "dithered", "claymorphism",
    "dashboard", "colorful", "contemporary", "artistic",
    "cafe", "atelier-zero", "ant", "application", "agentic",
    "arc",
]


def api_get(path: str) -> dict | list:
    url = f"{API_BASE}/{path}"
    headers = {"Accept": "application/vnd.github.v3+json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = request.Request(url, headers=headers)
    with request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def fetch_file(path: str) -> str:
    """Fetch a single file's content from the repo via contents API."""
    data = api_get(f"contents/{path}?ref={BRANCH}")
    if isinstance(data, dict) and "content" in data:
        return base64.b64decode(data["content"]).decode("utf-8")
    raise ValueError(f"Unexpected response for {path}")


def fetch_design_system_dir(brand: str) -> list[dict]:
    """List files in a design system brand directory."""
    try:
        return api_get(f"contents/design-systems/{brand}?ref={BRANCH}")  # type: ignore[return-value]
    except HTTPError as e:
        if e.code == 404:
            return []
        raise


def list_available_brands() -> list[str]:
    """List all brand directories in the open-design repo."""
    try:
        data = api_get(f"contents/design-systems?ref={BRANCH}")
        brands = []
        for item in data:  # type: ignore[union-attr]
            if isinstance(item, dict) and item.get("type") == "dir" and not item["name"].startswith("_"):
                brands.append(item["name"])
        return sorted(brands)
    except Exception as e:
        print(f"Error listing brands: {e}")
        return CURATED_BRANDS


def download_brand(brand: str) -> bool:
    """Download DESIGN.md and tokens.css for a brand. Returns True on success."""
    brand_dir = TARGET_DIR / brand
    brand_dir.mkdir(parents=True, exist_ok=True)

    # Check which files exist
    try:
        files = fetch_design_system_dir(brand)
    except Exception as e:
        print(f"  ✗ Cannot list {brand}: {e}")
        return False

    file_names = {f["name"] for f in files if isinstance(f, dict)}
    downloaded = False

    for fname in ("DESIGN.md", "tokens.css"):
        if fname not in file_names:
            continue
        try:
            content = fetch_file(f"design-systems/{brand}/{fname}")
            (brand_dir / fname).write_text(content, encoding="utf-8")
            size = len(content)
            print(f"    ✓ {fname} ({size:,} bytes)")
            downloaded = True
        except Exception as e:
            print(f"    ✗ {fname}: {e}")

    # Also try components.html (optional)
    if "components.html" in file_names:
        try:
            content = fetch_file(f"design-systems/{brand}/components.html")
            (brand_dir / "components.html").write_text(content, encoding="utf-8")
            print(f"    ✓ components.html ({len(content):,} bytes)")
        except Exception:
            pass

    return downloaded


def sync(brands: list[str] | None = None, delay: float = 0.3) -> tuple[int, int]:
    """Sync design systems. Returns (success_count, fail_count)."""
    TARGET_DIR.mkdir(parents=True, exist_ok=True)

    if brands is None:
        print("Listing available brands...")
        brands = list_available_brands()
        print(f"Found {len(brands)} brands. Starting sync...\n")

    success = 0
    fail = 0

    for i, brand in enumerate(brands):
        print(f"[{i + 1}/{len(brands)}] {brand}")
        if download_brand(brand):
            success += 1
        else:
            fail += 1
        if delay > 0 and i < len(brands) - 1:
            time.sleep(delay)

    return success, fail


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync design systems from open-design")
    parser.add_argument("--brands", help="Comma-separated brand names to sync")
    parser.add_argument("--list", action="store_true", help="List available brands")
    parser.add_argument("--delay", type=float, default=0.3, help="Delay between API calls (seconds)")
    args = parser.parse_args()

    if args.list:
        print("Available brands (from curated list):")
        for b in CURATED_BRANDS:
            print(f"  - {b}")
        print(f"\n{len(CURATED_BRANDS)} brands total.")
        print("\nTo fetch the full list from GitHub, run without --list and without --brands.")
        return

    if args.brands:
        brands = [b.strip() for b in args.brands.split(",")]
    else:
        print("No --brands specified. Using curated list.\n")
        brands = CURATED_BRANDS

    print(f"Will sync {len(brands)} brands to {TARGET_DIR}\n")
    ok, failed = sync(brands, delay=args.delay)
    print(f"\nDone: {ok} succeeded, {failed} failed.")

    # Validate
    sys.path.insert(0, str(PROJECT_ROOT))
    from app.services.design_system import DesignSystemRegistry
    registry = DesignSystemRegistry(TARGET_DIR)
    loaded = registry.scan()
    print(f"Registry loaded {loaded} design systems.")


if __name__ == "__main__":
    main()
