#!/usr/bin/env python3
# scripts/sync_icons.py
"""
Sync icons from peldrun-office-skills into catalog.json.
Fetches raw SVG content and embeds it as inline SVG.
"""

import json
import urllib.request
from pathlib import Path

# Base URL for the raw SVGs
OFFICE_REPO_RAW = "https://raw.githubusercontent.com/peldrunai/peldrun-office-skills/main/skills"

# The skills that live in the peldrun-office-skills repo
OFFICE_SKILL_IDS = {
    "pdf_document",
    "docx_document",
    "xlsx_spreadsheet",
    "pptx_presentation",
    "csv_data",
    "markdown_doc",
}

def fetch_svg(skill_id: str) -> str:
    """Fetch the SVG content for a given skill from the office-skills repo."""
    url = f"{OFFICE_REPO_RAW}/{skill_id}/icon.svg"
    print(f"Fetching {url} ...")
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            svg_content = response.read().decode("utf-8").strip()
            # Basic validation: ensure it starts with <svg
            if not svg_content.startswith("<svg"):
                raise ValueError(f"Downloaded content is not a valid SVG for {skill_id}")
            return svg_content
    except Exception as e:
        print(f"Error fetching {skill_id}: {e}")
        return None

def main():
    catalog_path = Path("catalog.json")
    if not catalog_path.exists():
        print("Error: catalog.json not found in the current directory.")
        return

    # Load catalog
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))

    # Update each item
    updated_count = 0
    for item in catalog.get("items", []):
        skill_id = item.get("id")
        
        # Only process skills that belong to our office-skills repo
        if skill_id in OFFICE_SKILL_IDS:
            svg = fetch_svg(skill_id)
            if svg:
                item["icon"] = svg
                item["icon_type"] = "svg"
                updated_count += 1
                print(f"  -> Updated {skill_id} with inline SVG.")
        
        # For any other skill (e.g., code_review), keep it as is,
        # assuming it already has a valid Lucide name or custom SVG.

    # Write back
    catalog_path.write_text(
        json.dumps(catalog, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8"
    )
    print(f"\nSuccess! Updated {updated_count} skills in catalog.json.")

if __name__ == "__main__":
    main()