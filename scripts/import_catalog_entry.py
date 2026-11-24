#!/usr/bin/env python3
"""Import a skill catalog entry from an external URL and merge into catalog.json.

This script is used by the GitHub Actions workflow (.github/workflows/import-skill.yml)
to automatically import new skills from their individual repositories.

Usage:
    python scripts/import_catalog_entry.py \
        --url "https://github.com/peldrunai/peldrun-office-skills/releases/download/pdf_document-v1.0.0/pdf_document-catalog-entry.json" \
        --catalog catalog.json

The script will:
    1. Fetch the entry JSON from the provided URL
    2. Validate it against schema/catalog.schema.json
    3. Verify the SHA-256 checksum matches the actual package at download_url
    4. Merge it into the catalog (update if skill_id exists, add if new)
    5. Update the updated_at timestamp

Exit codes:
    0 - Success
    1 - Entry validation failed
    2 - Checksum verification failed
    3 - Network error or invalid URL
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from jsonschema import Draft7Validator, FormatChecker
except ImportError:
    print("Error: jsonschema not installed. Run: pip install jsonschema==4.23.0")
    sys.exit(3)


REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = REPO_ROOT / "schema" / "catalog.schema.json"
USER_AGENT = "PELDRUN-Catalog-Import/1.0"
TIMEOUT_SECONDS = 30


def fetch_json(url: str) -> dict[str, Any]:
    """Fetch JSON from a URL with proper error handling."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as response:
            data = response.read()
            return json.loads(data.decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"::error::HTTP error fetching {url}: {e.code} {e.reason}")
        sys.exit(3)
    except urllib.error.URLError as e:
        print(f"::error::Network error fetching {url}: {e.reason}")
        sys.exit(3)
    except json.JSONDecodeError as e:
        print(f"::error::Invalid JSON from {url}: {e}")
        sys.exit(3)


def fetch_and_hash(url: str) -> str:
    """Download a file and return its SHA-256 hash."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as response:
            data = response.read()
            if not data:
                raise ValueError("Downloaded file is empty")
            return hashlib.sha256(data).hexdigest()
    except Exception as e:
        print(f"::error::Failed to fetch package for hash verification: {e}")
        sys.exit(2)


def validate_entry(entry: dict[str, Any]) -> None:
    """Validate the entry against the catalog schema."""
    if not SCHEMA_PATH.is_file():
        print(f"::warning::Schema file not found: {SCHEMA_PATH}, skipping schema validation")
        return

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = Draft7Validator(schema, format_checker=FormatChecker())

    errors = list(validator.iter_errors(entry))
    if errors:
        print("::error::Entry validation failed:")
        for err in errors:
            location = ".".join(str(p) for p in err.absolute_path) or "<root>"
            print(f"  {location}: {err.message}")
        sys.exit(1)


def verify_checksum(entry: dict[str, Any]) -> None:
    """Verify the SHA-256 checksum matches the actual package."""
    download_url = entry.get("download_url")
    expected_hash = entry.get("checksum_sha256")

    if not download_url or not expected_hash:
        print("::warning::No download_url or checksum_sha256 in entry, skipping verification")
        return

    print(f"Verifying checksum for {download_url}...")
    actual_hash = fetch_and_hash(download_url)

    if actual_hash != expected_hash:
        print(f"::error::Checksum mismatch!")
        print(f"  Expected: {expected_hash}")
        print(f"  Actual:   {actual_hash}")
        sys.exit(2)

    print(f"Checksum verified: {actual_hash}")


def merge_into_catalog(catalog: dict[str, Any], entry: dict[str, Any]) -> bool:
    """
    Merge the entry into the catalog.
    Returns True if an existing item was updated, False if a new item was added.
    """
    items = catalog.get("items", [])
    entry_id = entry.get("id")

    # Find existing item by ID
    for i, item in enumerate(items):
        if item.get("id") == entry_id:
            print(f"Updating existing skill: {entry_id}")
            items[i] = entry
            return True

    # Add as new item
    print(f"Adding new skill: {entry_id}")
    items.append(entry)
    return False


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import a skill catalog entry from an external URL"
    )
    parser.add_argument(
        "--url",
        required=True,
        help="URL to the skill-catalog-entry.json file"
    )
    parser.add_argument(
        "--catalog",
        type=Path,
        default=Path("catalog.json"),
        help="Path to the catalog.json file (default: catalog.json)"
    )
    args = parser.parse_args()

    # Fetch the entry
    print(f"Fetching entry from {args.url}...")
    entry = fetch_json(args.url)

    # Validate against schema
    print("Validating entry against schema...")
    validate_entry(entry)

    # Verify checksum
    verify_checksum(entry)

    # Load catalog
    if not args.catalog.exists():
        print(f"::error::Catalog file not found: {args.catalog}")
        sys.exit(1)

    catalog = json.loads(args.catalog.read_text(encoding="utf-8"))

    # Merge entry into catalog
    was_update = merge_into_catalog(catalog, entry)

    # Update timestamp
    catalog["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Write back to catalog
    args.catalog.write_text(
        json.dumps(catalog, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8"
    )

    action = "updated" if was_update else "added"
    print(f"\nSuccess: Skill '{entry.get('id')}' has been {action} in {args.catalog}")

    return 0


if __name__ == "__main__":
    sys.exit(main())