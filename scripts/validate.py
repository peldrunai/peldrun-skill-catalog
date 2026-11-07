#!/usr/bin/env python3
# scripts/validate.py
"""
Local validation for catalog.json.

Mirrors the checks performed by the CI workflow
(.github/workflows/validate-catalog.yml) so contributors can catch
problems BEFORE pushing. No third-party dependencies -- only the
Python standard library -- so it runs on any machine with Python 3.10+.

Checks
------
    1. catalog.json exists and parses as JSON.
    2. schema_version is a supported integer (currently only 1).
    3. Every item in "items" is a JSON object.
    4. Every item passes the field-level rules enforced by PELDRUN's
       runtime (backend/omweb/skills/catalog/schema.py):
         - id matches ^[a-z0-9][a-z0-9_]{2,63}$
         - version matches semver
         - description is a non-empty string (1-500 chars)
         - download_url, when set, is https://
         - checksum_sha256, when set, is a 64-char lowercase hex digest
         - download_url and checksum_sha256 are both set, or both null
           (supply-chain integrity -- non-negotiable)
         - brand_color, when set, matches ^#[0-9A-Fa-f]{6}$
         - icon_type in {name, svg}
         - trust in {verified, community, unverified}
         - stability in {experimental, beta, stable, deprecated}
         - has_sub_skills and sub_skills_count are consistent
           (true requires count > 0; count > 0 requires true)
         - tags is an array of strings (max 20, unique)
         - install_warnings is an array of strings (max 10)
    5. No duplicate "id" values.
    6. Cross-item warnings (not errors):
         - An item marked has_sub_skills but the description does not
           mention "router" or "sub-skill" (soft hint).
         - release_date is in the future.

Exit code
---------
    0   All checks passed.
    1   One or more checks failed. All failures are printed so the
        contributor can fix them in one pass.

Usage
-----
    python scripts/validate.py
    python scripts/validate.py --catalog path/to/catalog.json

The --catalog flag is for testing alternate catalogs (e.g. a local
override file). CI always runs without it, so the default path
(repo root / catalog.json) is the authoritative one.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Constants -- must stay in lockstep with
# backend/omweb/skills/catalog/schema.py
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CATALOG_PATH = REPO_ROOT / "catalog.json"

SUPPORTED_SCHEMA_VERSIONS = {1}

SKILL_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_]{2,63}$")
VERSION_PATTERN = re.compile(
    r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$"
)
SHA256_HEX_PATTERN = re.compile(r"^[0-9a-f]{64}$")
BRAND_COLOR_PATTERN = re.compile(r"^#[0-9A-Fa-f]{6}$")
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")

ALLOWED_ICON_TYPES = {"name", "svg"}
ALLOWED_TRUST = {"verified", "community", "unverified"}
ALLOWED_STABILITY = {"experimental", "beta", "stable", "deprecated"}

MAX_TAGS = 20
MAX_TAG_LEN = 32
MAX_WARNINGS = 10
MAX_WARNING_LEN = 500
MAX_DESCRIPTION_LEN = 500


# ---------------------------------------------------------------------------
# ANSI colours -- degrade gracefully on terminals without support
# ---------------------------------------------------------------------------

def _supports_colour() -> bool:
    import os
    if sys.platform == "win32":
        return "ANSICON" in os.environ or "WT_SESSION" in os.environ
    return sys.stdout.isatty()


_RED = "\033[31m" if _supports_colour() else ""
_GREEN = "\033[32m" if _supports_colour() else ""
_YELLOW = "\033[33m" if _supports_colour() else ""
_DIM = "\033[2m" if _supports_colour() else ""
_RESET = "\033[0m" if _supports_colour() else ""


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------

class CatalogValidator:
    """
    Accumulate every error in one pass, then report them together.

    Reporting all errors at once (rather than exiting on the first
    failure) is deliberate: a contributor who fixes one issue should
    not have to re-run the script to discover the next.
    """

    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def _err(self, message: str) -> None:
        self.errors.append(message)

    def _warn(self, message: str) -> None:
        self.warnings.append(message)

    # ------------------------------------------------------------------
    # Top-level
    # ------------------------------------------------------------------

    def validate_file(self, catalog_path: Path) -> bool:
        """
        Load and validate catalog.json.

        Returns True when the file loads and every structural check
        passes. Individual item checks are still recorded on
        ``self.errors`` -- the caller decides how to report them.
        """
        if not catalog_path.is_file():
            self._err(f"catalog.json not found at {catalog_path}")
            return False

        try:
            raw = catalog_path.read_text(encoding="utf-8")
        except OSError as exc:
            self._err(f"Could not read catalog.json: {exc}")
            return False

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            self._err(
                f"catalog.json is not valid JSON: {exc.msg} "
                f"(line {exc.lineno}, column {exc.colno})"
            )
            return False

        if not isinstance(payload, dict):
            self._err(
                f"catalog.json root must be a JSON object, "
                f"got {type(payload).__name__}"
            )
            return False

        self._validate_top_level(payload)
        return not self.errors

    def _validate_top_level(self, payload: dict[str, Any]) -> None:
        # schema_version
        version = payload.get("schema_version")
        if version is None:
            self._err(
                "catalog.json is missing required field 'schema_version'"
            )
        elif not isinstance(version, int):
            self._err(
                f"'schema_version' must be an integer, "
                f"got {type(version).__name__}"
            )
        elif version not in SUPPORTED_SCHEMA_VERSIONS:
            self._err(
                f"Unsupported 'schema_version' {version}. "
                f"Supported: {sorted(SUPPORTED_SCHEMA_VERSIONS)}"
            )

        # items
        items = payload.get("items")
        if items is None:
            self._err("catalog.json is missing required field 'items'")
            return
        if not isinstance(items, list):
            self._err(
                f"'items' must be a JSON array, "
                f"got {type(items).__name__}"
            )
            return

        if len(items) == 0:
            self._warn(
                "catalog.json contains zero items. This is valid, but "
                "PELDRUN will render an empty Catalog tab with a "
                "'Catalog is empty' message."
            )

        seen_ids: set[str] = set()
        for index, item in enumerate(items):
            self._validate_item(item, index, seen_ids)

    # ------------------------------------------------------------------
    # Per-item
    # ------------------------------------------------------------------

    def _validate_item(
        self,
        item: Any,
        index: int,
        seen_ids: set[str],
    ) -> None:
        label = f"items[{index}]"

        if not isinstance(item, dict):
            self._err(
                f"{label} must be a JSON object, "
                f"got {type(item).__name__}"
            )
            return

        # --- id ------------------------------------------------------
        raw_id = item.get("id")
        if not isinstance(raw_id, str) or not raw_id:
            self._err(f"{label}.id must be a non-empty string")
        else:
            label = f"items[{index}] (id={raw_id!r})"
            if not SKILL_ID_PATTERN.match(raw_id):
                self._err(
                    f"{label}.id must match "
                    f"{SKILL_ID_PATTERN.pattern}, got {raw_id!r}"
                )
            if raw_id in seen_ids:
                self._err(f"{label}.id is a duplicate")
            else:
                seen_ids.add(raw_id)

        # --- name ----------------------------------------------------
        name = item.get("name")
        if not isinstance(name, str) or not name:
            self._err(f"{label}.name must be a non-empty string")

        # --- display_name (optional) ---------------------------------
        display_name = item.get("display_name")
        if display_name is not None and (
            not isinstance(display_name, str) or not display_name
        ):
            self._err(
                f"{label}.display_name must be a non-empty string "
                f"or null"
            )

        # --- description ---------------------------------------------
        description = item.get("description")
        if not isinstance(description, str) or not description:
            self._err(f"{label}.description must be a non-empty string")
        elif len(description) > MAX_DESCRIPTION_LEN:
            self._err(
                f"{label}.description is {len(description)} characters; "
                f"max is {MAX_DESCRIPTION_LEN}"
            )

        # --- version -------------------------------------------------
        version = item.get("version")
        if not isinstance(version, str) or not version:
            self._err(f"{label}.version must be a non-empty string")
        elif not VERSION_PATTERN.match(version):
            self._err(
                f"{label}.version must be semver "
                f"(e.g. '1.0.0', '1.0.0-beta.1'), got {version!r}"
            )

        # --- download_url --------------------------------------------
        download_url = item.get("download_url")
        if download_url is not None:
            if not isinstance(download_url, str) or not download_url:
                self._err(
                    f"{label}.download_url must be a non-empty string "
                    f"or null"
                )
            elif not download_url.lower().startswith("https://"):
                self._err(
                    f"{label}.download_url must use https://, "
                    f"got {download_url!r}"
                )

        # --- checksum_sha256 -----------------------------------------
        checksum = item.get("checksum_sha256")
        if checksum is not None:
            if not isinstance(checksum, str) or not checksum:
                self._err(
                    f"{label}.checksum_sha256 must be a non-empty "
                    f"string or null"
                )
            elif not SHA256_HEX_PATTERN.match(checksum):
                self._err(
                    f"{label}.checksum_sha256 must be a 64-character "
                    f"lowercase hex digest, got {checksum!r}"
                )

        # --- integrity: both or neither -------------------------------
        has_url = isinstance(download_url, str) and bool(download_url)
        has_hash = isinstance(checksum, str) and bool(checksum)
        if has_url and not has_hash:
            self._err(
                f"{label}: download_url is set but checksum_sha256 "
                f"is missing. PELDRUN refuses to install a skill "
                f"without a published SHA-256 -- this is a "
                f"supply-chain integrity requirement."
            )
        elif has_hash and not has_url:
            self._err(
                f"{label}: checksum_sha256 is set but download_url "
                f"is missing. Either publish the ZIP and its hash "
                f"together, or set both to null for a preview-only "
                f"item."
            )

        # --- brand_color (optional) ----------------------------------
        brand_color = item.get("brand_color")
        if brand_color is not None:
            if not isinstance(brand_color, str):
                self._err(f"{label}.brand_color must be a string or null")
            elif not BRAND_COLOR_PATTERN.match(brand_color):
                self._err(
                    f"{label}.brand_color must be a 6-digit hex string "
                    f"(e.g. '#8B5CF6'), got {brand_color!r}"
                )

        # --- icon / icon_type ----------------------------------------
        icon = item.get("icon")
        if icon is not None and not isinstance(icon, str):
            self._err(f"{label}.icon must be a string or null")

        icon_type = item.get("icon_type", "name")
        if icon_type not in ALLOWED_ICON_TYPES:
            self._err(
                f"{label}.icon_type must be one of "
                f"{sorted(ALLOWED_ICON_TYPES)}, got {icon_type!r}"
            )

        # --- author / homepage (optional) ----------------------------
        author = item.get("author")
        if author is not None and not isinstance(author, str):
            self._err(f"{label}.author must be a string or null")

        homepage = item.get("homepage")
        if homepage is not None and not (
            isinstance(homepage, str)
            and homepage.startswith(("https://", "http://"))
        ):
            self._warn(
                f"{label}.homepage should be an http(s) URL, "
                f"got {homepage!r}"
            )

        # --- trust / stability ---------------------------------------
        trust = item.get("trust", "unverified")
        if trust not in ALLOWED_TRUST:
            self._err(
                f"{label}.trust must be one of "
                f"{sorted(ALLOWED_TRUST)}, got {trust!r}"
            )

        stability = item.get("stability", "stable")
        if stability not in ALLOWED_STABILITY:
            self._err(
                f"{label}.stability must be one of "
                f"{sorted(ALLOWED_STABILITY)}, got {stability!r}"
            )

        # --- has_sub_skills / sub_skills_count -----------------------
        has_subs = item.get("has_sub_skills", False)
        sub_count = item.get("sub_skills_count", 0)
        if not isinstance(has_subs, bool):
            self._err(f"{label}.has_sub_skills must be a boolean")
        if not isinstance(sub_count, int) or sub_count < 0:
            self._err(
                f"{label}.sub_skills_count must be a non-negative "
                f"integer, got {sub_count!r}"
            )
        elif isinstance(has_subs, bool):
            if has_subs and sub_count == 0:
                self._err(
                    f"{label}: has_sub_skills=true requires "
                    f"sub_skills_count > 0"
                )
            if not has_subs and sub_count > 0:
                self._err(
                    f"{label}: sub_skills_count > 0 requires "
                    f"has_sub_skills=true"
                )

        # --- tags ----------------------------------------------------
        tags = item.get("tags")
        if tags is not None:
            if not isinstance(tags, list):
                self._err(f"{label}.tags must be a JSON array")
            else:
                if len(tags) > MAX_TAGS:
                    self._err(
                        f"{label}.tags has {len(tags)} items; "
                        f"max is {MAX_TAGS}"
                    )
                seen_tags: set[str] = set()
                for t_index, tag in enumerate(tags):
                    if not isinstance(tag, str) or not tag:
                        self._err(
                            f"{label}.tags[{t_index}] must be a "
                            f"non-empty string"
                        )
                        continue
                    if len(tag) > MAX_TAG_LEN:
                        self._err(
                            f"{label}.tags[{t_index}] is "
                            f"{len(tag)} characters; max is "
                            f"{MAX_TAG_LEN}"
                        )
                    if tag in seen_tags:
                        self._err(
                            f"{label}.tags contains duplicate "
                            f"{tag!r}"
                        )
                    seen_tags.add(tag)

        # --- install_warnings ----------------------------------------
        warnings_list = item.get("install_warnings")
        if warnings_list is not None:
            if not isinstance(warnings_list, list):
                self._err(
                    f"{label}.install_warnings must be a JSON array"
                )
            else:
                if len(warnings_list) > MAX_WARNINGS:
                    self._err(
                        f"{label}.install_warnings has "
                        f"{len(warnings_list)} items; max is "
                        f"{MAX_WARNINGS}"
                    )
                for w_index, w in enumerate(warnings_list):
                    if not isinstance(w, str) or not w:
                        self._err(
                            f"{label}.install_warnings[{w_index}] "
                            f"must be a non-empty string"
                        )
                    elif len(w) > MAX_WARNING_LEN:
                        self._err(
                            f"{label}.install_warnings[{w_index}] "
                            f"is {len(w)} characters; max is "
                            f"{MAX_WARNING_LEN}"
                        )

        # --- release_date (optional) ---------------------------------
        release_date = item.get("release_date")
        if release_date is not None:
            if not isinstance(release_date, str) or not DATE_PATTERN.match(release_date):
                self._err(
                    f"{label}.release_date must be YYYY-MM-DD, "
                    f"got {release_date!r}"
                )
            else:
                try:
                    parsed = datetime.strptime(release_date, "%Y-%m-%d")
                    if parsed.date() > datetime.now(timezone.utc).date():
                        self._warn(
                            f"{label}.release_date "
                            f"({release_date}) is in the future"
                        )
                except ValueError:
                    self._err(
                        f"{label}.release_date is not a valid date: "
                        f"{release_date!r}"
                    )

        # --- soft hints ----------------------------------------------
        if has_subs and isinstance(description, str):
            lower = description.lower()
            if "router" not in lower and "sub-skill" not in lower:
                self._warn(
                    f"{label}: has_sub_skills=true but description "
                    f"does not mention 'router' or 'sub-skill'. "
                    f"Consider adding a hint -- users find router "
                    f"skills easier to discover when the badge is "
                    f"explained."
                )

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def report(self) -> int:
        """Print all warnings and errors, then return an exit code."""
        if self.warnings:
            print(f"{_YELLOW}Warnings:{_RESET}")
            for w in self.warnings:
                print(f"  {_YELLOW}~{_RESET} {w}")
            print()

        if self.errors:
            print(f"{_RED}Errors:{_RESET}")
            for e in self.errors:
                print(f"  {_RED}x{_RESET} {e}")
            print()
            print(
                f"{_RED}FAILED{_RESET}: {len(self.errors)} error(s), "
                f"{len(self.warnings)} warning(s)."
            )
            return 1

        print(
            f"{_GREEN}OK{_RESET}: catalog.json is valid "
            f"({len(self.warnings)} warning(s))."
        )
        return 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Validate catalog.json against PELDRUN's skill catalog rules. "
            "Run from anywhere; the script resolves the default path "
            "relative to its own location."
        )
    )
    parser.add_argument(
        "--catalog",
        type=Path,
        default=DEFAULT_CATALOG_PATH,
        help=(
            f"Path to the catalog.json to validate. "
            f"Default: {DEFAULT_CATALOG_PATH}"
        ),
    )
    args = parser.parse_args(argv)

    print(f"{_DIM}Validating {args.catalog}{_RESET}")
    validator = CatalogValidator()
    validator.validate_file(args.catalog)
    return validator.report()


if __name__ == "__main__":
    sys.exit(main())