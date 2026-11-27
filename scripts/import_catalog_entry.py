#!/usr/bin/env python3
# scripts/import_catalog_entry.py
"""Import a PELDRUN catalog entry (a catalog document with items[]) into catalog.json.

Fetches a remote catalog-entry.json, validates it against the official catalog
schema, verifies the SHA-256 checksum of each item, then merges the items into
the local catalog.json (idempotent by skill id).

Exit codes:
    0 - Success
    1 - Validation or merge failure
    2 - Network or file error
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

import jsonschema

REPO_ROOT = Path(__file__).resolve().parent.parent
CATALOG_PATH = REPO_ROOT / "catalog.json"
SCHEMA_PATH = REPO_ROOT / "schema" / "catalog.schema.json"


def load_json(path: Path) -> Any:
    """Load JSON from a local file."""
    return json.loads(path.read_text(encoding="utf-8"))


def fetch_json(url: str) -> Any:
    """Fetch and parse JSON from a URL."""
    with urllib.request.urlopen(url, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def compute_sha256(data: bytes) -> str:
    """Compute SHA-256 hex digest of bytes."""
    return hashlib.sha256(data).hexdigest()


def download_and_hash(url: str) -> str:
    """Download a file from URL and return its SHA-256 hex digest."""
    with urllib.request.urlopen(url, timeout=60) as resp:
        return compute_sha256(resp.read())


def validate_entry(entry: Any, schema: dict[str, Any]) -> None:
    """Validate the catalog document against the official schema."""
    jsonschema.validate(instance=entry, schema=schema)


def verify_item_checksums(entry: dict[str, Any]) -> None:
    """For each item in entry['items'], download the referenced ZIP and verify
    its SHA-256 matches item['checksum_sha256'].

    Raises ValueError on mismatch or missing field.
    """
    for idx, item in enumerate(entry["items"]):
        checksum = item.get("checksum_sha256")
        if not checksum:
            raise ValueError(f"items[{idx}] missing checksum_sha256")

        download_url = item.get("download_url")
        if not download_url:
            raise ValueError(f"items[{idx}] missing download_url")

        print(f"  Verifying checksum for item[{idx}] ({item.get('id')}) ...")
        actual = download_and_hash(download_url)
        if actual != checksum:
            raise ValueError(
                f"items[{idx}] checksum mismatch: expected {checksum}, got {actual}"
            )
        print(f"    OK ({actual})")


def merge_into_catalog(catalog: dict[str, Any], entry: dict[str, Any]) -> None:
    """Merge entry['items'] into catalog['items'].

    - If an item with the same 'id' exists, it is replaced.
    - Otherwise, it is appended.
    - The catalog's 'updated_at' is set to the current UTC time.
    """
    existing_items = catalog.setdefault("items", [])
    index_by_id = {item["id"]: i for i, item in enumerate(existing_items)}

    for new_item in entry["items"]:
        item_id = new_item["id"]
        if item_id in index_by_id:
            pos = index_by_id[item_id]
            existing_items[pos] = new_item
            print(f"  Replaced existing item: {item_id}")
        else:
            existing_items.append(new_item)
            index_by_id[item_id] = len(existing_items) - 1
            print(f"  Added new item: {item_id}")

    catalog["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import a remote catalog entry into catalog.json"
    )
    parser.add_argument(
        "--url",
        required=True,
        help="URL of the catalog-entry.json to import",
    )
    parser.add_argument(
        "--catalog",
        type=Path,
        default=CATALOG_PATH,
        help="Path to the local catalog.json (default: catalog.json)",
    )
    parser.add_argument(
        "--schema",
        type=Path,
        default=SCHEMA_PATH,
        help="Path to catalog.schema.json (default: schema/catalog.schema.json)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and verify but do not write catalog.json",
    )
    args = parser.parse_args()

    # Load schema
    if not args.schema.is_file():
        print(f"Error: Schema not found at {args.schema}")
        return 2
    schema = load_json(args.schema)

    # Fetch entry
    print(f"Fetching entry from {args.url} ...")
    try:
        entry = fetch_json(args.url)
    except Exception as exc:
        print(f"Error: Failed to fetch entry: {exc}")
        return 2

    # Validate
    print("Validating entry against schema ...")
    try:
        validate_entry(entry, schema)
    except jsonschema.ValidationError as exc:
        print("Error: Entry validation failed:")
        print(f"  {exc.message}")
        if exc.path:
            print(f"  at path: {'.'.join(str(p) for p in exc.path)}")
        return 1

    # Verify checksums
    print("Verifying item checksums ...")
    try:
        verify_item_checksums(entry)
    except Exception as exc:
        print(f"Error: Checksum verification failed: {exc}")
        return 1

    # Load local catalog
    if not args.catalog.is_file():
        print(f"Error: Local catalog not found at {args.catalog}")
        return 2
    catalog = load_json(args.catalog)

    # Ensure catalog itself has the required top-level fields
    if "schema_version" not in catalog:
        catalog["schema_version"] = entry.get("schema_version", 1)
    if "items" not in catalog:
        catalog["items"] = []

    # Merge
    print("Merging items into local catalog ...")
    merge_into_catalog(catalog, entry)

    if args.dry_run:
        print("Dry-run: catalog.json not written.")
        return 0

    # Write back
    args.catalog.write_text(
        json.dumps(catalog, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Updated catalog written to {args.catalog}")
    return 0


if __name__ == "__main__":
    sys.exit(main())