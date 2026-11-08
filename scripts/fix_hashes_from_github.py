#!/usr/bin/env python3
# scripts/fix_hashes_from_github.py

import json
import hashlib
import urllib.request
from pathlib import Path

# Define paths
CATALOG_FILE = Path("catalog.json")
USER_AGENT = "PELDRUN-Catalog-Sync/1.0"

def fetch_and_hash(url: str) -> str:
    """
    Downloads the file from the given URL and returns its SHA-256 hash.
    Automatically follows redirects (e.g., GitHub Release 302 redirects).
    """
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    
    # 30 seconds timeout to prevent hanging indefinitely
    with urllib.request.urlopen(req, timeout=30) as response:
        data = response.read()
        if not data:
            raise ValueError("Downloaded file is empty")
        
        return hashlib.sha256(data).hexdigest()

def main():
    if not CATALOG_FILE.exists():
        print(f"Error: {CATALOG_FILE} not found in the current directory.")
        return

    # Load the existing catalog
    try:
        catalog = json.loads(CATALOG_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"Error: Failed to parse {CATALOG_FILE}: {e}")
        return

    items = catalog.get("items", [])
    if not items:
        print("No items found in the catalog.")
        return

    print(f"Found {len(items)} item(s) in the catalog. Starting hash sync...\n")

    updates_made = False

    for item in items:
        skill_id = item.get("id", "unknown")
        download_url = item.get("download_url")

        # Skip items without a download URL (e.g., preview-only items)
        if not download_url:
            print(f"[SKIP] {skill_id}: No download_url provided.")
            continue

        print(f"[FETCH] {skill_id} -> {download_url}")
        
        try:
            actual_hash = fetch_and_hash(download_url)
            current_hash = item.get("checksum_sha256")

            if current_hash != actual_hash:
                item["checksum_sha256"] = actual_hash
                updates_made = True
                print(f"  [FIXED] Hash updated.")
                print(f"          Old: {current_hash}")
                print(f"          New: {actual_hash}")
            else:
                print(f"  [OK] Hash is already correct: {actual_hash}")
                
        except Exception as e:
            print(f"  [ERROR] Failed to process {skill_id}: {e}")

        print("-" * 60)

    if updates_made:
        # Write back to catalog.json with standard formatting
        CATALOG_FILE.write_text(
            json.dumps(catalog, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8"
        )
        print("\nSuccess: catalog.json has been updated with the correct hashes.")
    else:
        print("\nNo updates were needed. All hashes are already correct.")

if __name__ == "__main__":
    main()