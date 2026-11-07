# Adding a Skill to the Catalog

This guide walks through every step required to publish a new Skill in the PELDRUN catalog. It assumes the skill's source files (manifest, SKILL.md, sub-skills) have been authored and are ready to package.

The catalog itself only carries **metadata**. The actual ZIP archive lives elsewhere — by convention, as a GitHub Release asset on the skill's own repository (e.g. `github.com/peldrunai/peldrun-skill-code-review`).

---

## Prerequisites

Before you can add an item to `catalog.json`, you need:

1. **A published ZIP** of the skill package, built from the skill's own repository.
2. **The SHA-256 checksum** of that exact ZIP.
3. **The manifest fields** that the catalog item mirrors:
   - `id` — the skill package's canonical ID (from `manifest.json`).
   - `name`, `display_name`, `description`.
   - `version` — the semantic version from `manifest.json`.
   - `tags`, `trust`, `stability`, `license`, `homepage`.
   - `has_sub_skills` / `sub_skills_count` — computed from `sub_skills` in the manifest.
   - `brand_color` — optional 6-digit hex, propagated to the installed skill's manifest.

If the skill has no Release yet, complete those steps first. The catalog cannot reference a ZIP that does not exist at a stable URL.

---

## Anatomy of a Skill package

Every skill is a ZIP archive with a flat root:

```
code-review-2.0.0.zip
├── manifest.json
├── SKILL.md
└── sub_skills/                    (only for router skills)
    ├── security_audit/SKILL.md
    ├── performance_review/SKILL.md
    ├── style_check/SKILL.md
    └── logic_review/SKILL.md
```

**Rules:**
- `manifest.json` and `SKILL.md` MUST be at the archive root (no wrapping directory).
- `SKILL.md` must start with a YAML frontmatter block (`---\n...\n---`).
- Sub-skill instructions MUST live under `sub_skills/` and end in `.md`.
- Each sub-skill declared in the manifest must have a `description` (10-500 chars) and an `instructions_file` starting with `sub_skills/`.

See PELDRUN's manifest schema for the full contract:
[`backend/omweb/skills/_manifest_schema.json`](https://github.com/peldrunai/peldrun/blob/main/backend/omweb/skills/_manifest_schema.json)

---

## Step 1 — Create a new repository for the skill

Each skill lives in its own repository so its version history is isolated. The convention is:

```
github.com/peldrunai/peldrun-skill-<skill_id>
```

For example:
- `peldrun-skill-code-review`
- `peldrun-skill-debugging`
- `peldrun-skill-test-planning`

Initialize the repo with:

```bash
mkdir peldrun-skill-code-review
cd peldrun-skill-code-review
git init -b main
```

---

## Step 2 — Author the skill package

At the repo root, create:

```
peldrun-skill-code-review/
├── manifest.json
├── SKILL.md
├── sub_skills/                   (optional — router skills only)
│   └── security_audit/SKILL.md
├── icons/                        (optional)
│   └── code_review.svg
└── scripts/
    └── build.sh                  (produces dist/code-review-2.0.0.zip)
```

### `manifest.json` example

```json
{
  "schema_version": "1.0.0",
  "id": "code_review",
  "version": "2.0.0",
  "name": "Code Review",
  "display_name": "Code Review",
  "description": "Systematic code review with router-based sub-skill selection.",
  "brand_color": "#8B5CF6",
  "author": {
    "name": "PELDRUN Team",
    "url": "https://peldrun.ai"
  },
  "homepage": "https://peldrun.ai/skills/code_review",
  "license": "MIT",
  "trust": "verified",
  "stability": "stable",
  "release_date": "2026-11-08",
  "tags": ["review", "audit", "security", "router"],
  "execution": {
    "type": "instructions",
    "instructions_file": "SKILL.md"
  },
  "sub_skills": [
    {
      "id": "security_audit",
      "description": "Identify security vulnerabilities: injection, auth flaws, exposed secrets, and unsafe deserialization.",
      "triggers": ["security", "vulnerability", "injection", "auth"],
      "instructions_file": "sub_skills/security_audit/SKILL.md"
    },
    {
      "id": "performance_review",
      "description": "Identify performance issues: N+1 queries, unnecessary allocations, blocking IO in hot paths.",
      "triggers": ["performance", "latency", "query", "allocation"],
      "instructions_file": "sub_skills/performance_review/SKILL.md"
    }
  ]
}
```

### `SKILL.md` example

```markdown
---
name: Code Review
description: Systematic code review with router-based sub-skill selection.
---

# Code Review

You are a code review router. When the user asks you to review code,
analyze the request and load the sub-skill that best matches:

- **security_audit** — for anything touching auth, input parsing,
  network boundaries, or secrets.
- **performance_review** — for anything in a hot path, loop, or query.

If unsure, load BOTH and combine their guidance. Only the selected
sub-skills' instructions should drive the review.
```

### `sub_skills/security_audit/SKILL.md` example

```markdown
---
name: Security Audit
description: Identify security vulnerabilities.
---

# Security Audit

Review the code for:

1. **Injection** — SQL, shell, template, path traversal.
2. **Auth flaws** — missing checks, privilege escalation, session fixation.
3. **Exposed secrets** — API keys, passwords, tokens in source or logs.
4. **Unsafe deserialization** — pickle, yaml.load, eval of user input.

For each finding, report:
- The exact file and line.
- A one-sentence description of the risk.
- A concrete remediation (code snippet preferred).
```

---

## Step 3 — Build the ZIP

The build script should produce a deterministic ZIP (same input → same bytes → same SHA-256). A minimal example:

**`scripts/build.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail

SKILL_ID="code_review"
VERSION="2.0.0"
ZIP_NAME="code-review-${VERSION}.zip"

mkdir -p dist
rm -f "dist/${ZIP_NAME}"

# Zip only the package files — exclude scripts/, dist/, and dotfiles.
# Use -X to strip extra file attributes so bytes are deterministic
# across operating systems.
zip -r -X "dist/${ZIP_NAME}" \
  manifest.json \
  SKILL.md \
  sub_skills/ \
  icons/ 2>/dev/null || true

echo "Built dist/${ZIP_NAME}"
```

Make it executable:

```bash
chmod +x scripts/build.sh
./scripts/build.sh
```

**Windows PowerShell equivalent** — if you develop on Windows, use `Compress-Archive` or install `zip` via Git for Windows. The key requirement is **deterministic bytes**: same input must produce the same ZIP hash, or the catalog's `checksum_sha256` will mismatch on rebuilds.

---

## Step 4 — Compute the SHA-256 checksum

```bash
# Linux / macOS
sha256sum dist/code-review-2.0.0.zip

# Windows PowerShell
Get-FileHash -Algorithm SHA256 -Path dist\code-review-2.0.0.zip
```

The output is a 64-character lowercase hex string. Save it — it goes into `catalog.json` as `checksum_sha256`.

```
8f3a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a
```

**This checksum is not optional.** PELDRUN refuses to install any package whose catalog entry lacks a valid SHA-256. The intent is supply-chain integrity: if someone compromises the download server, the checksum will not match and the install aborts.

---

## Step 5 — Publish the ZIP as a GitHub Release

In the **skill's own repository**:

```bash
gh release create v2.0.0 \
  --repo peldrunai/peldrun-skill-code-review \
  --title "Code Review Skill v2.0.0" \
  --notes "Initial stable release with router-based sub-skill selection." \
  dist/code-review-2.0.0.zip
```

Or via the web UI:

1. Open `https://github.com/peldrunai/peldrun-skill-code-review/releases/new`.
2. Fill in `Tag: v2.0.0`, `Title: ...`, `Description: ...`.
3. Drag `dist/code-review-2.0.0.zip` into the attachments area.
4. Click **Publish release**.

The resulting direct download URL will have this shape:

```
https://github.com/peldrunai/peldrun-skill-code-review/releases/download/v2.0.0/code-review-2.0.0.zip
```

**Do not use** `https://github.com/.../archive/refs/tags/v2.0.0.zip` — that returns the source tree, not the built ZIP, and its SHA-256 will not match what your build script produced.

**Do not use** `https://raw.githubusercontent.com/.../dist/code-review-2.0.0.zip` — raw URLs are size-capped and not intended for release artifacts.

---

## Step 6 — Verify the download URL

From any machine with internet access:

```bash
curl -L -o /tmp/code-review-test.zip \
  "https://github.com/peldrunai/peldrun-skill-code-review/releases/download/v2.0.0/code-review-2.0.0.zip"

sha256sum /tmp/code-review-test.zip
```

The hash must equal the one computed in Step 4. If it differs, the ZIP was modified after publishing — re-upload the Release asset and retry.

---

## Step 7 — Add the item to `catalog.json`

Open `catalog.json` (in **this** repository — `peldrun-skill-catalog`) and either update an existing entry or append a new one under `items`. A minimal installable item looks like this:

```json
{
  "id": "code_review",
  "name": "Code Review",
  "display_name": "Code Review",
  "description": "Systematic code review with router-based sub-skill selection.",
  "version": "2.0.0",
  "download_url": "https://github.com/peldrunai/peldrun-skill-code-review/releases/download/v2.0.0/code-review-2.0.0.zip",
  "checksum_sha256": "8f3a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a",
  "brand_color": "#8B5CF6",
  "icon": "code_review",
  "icon_type": "name",
  "author": "PELDRUN Team",
  "author_url": "https://peldrun.ai",
  "developer": {
    "name": "PELDRUN Team",
    "url": "https://peldrun.ai",
    "github_username": "peldrunai",
    "verified": true
  },
  "repository_url": "https://github.com/peldrunai/peldrun-skill-code-review",
  "homepage": "https://peldrun.ai/skills/code_review",
  "license": "MIT",
  "tags": ["review", "audit", "security", "router"],
  "has_sub_skills": true,
  "sub_skills_count": 2,
  "trust": "verified",
  "stability": "stable",
  "release_date": "2026-11-08",
  "install_warnings": []
}
```

### Field reference

| Field | Required | Notes |
|---|---|---|
| `id` | ✅ | Lowercase, `[a-z0-9_]`, 3-64 chars, must match the manifest's `id` |
| `name` | ✅ | Technical name |
| `version` | ✅ | Semver, must match the ZIP's `manifest.json` |
| `description` | ✅ | 1-500 chars, shown on the catalog card |
| `download_url` | Either both, or neither | HTTPS only |
| `checksum_sha256` | Either both, or neither | 64-char lowercase hex |
| `display_name` | Optional | Falls back to `name` |
| `brand_color` | Optional | `#RRGGBB` — propagated to installed manifest |
| `icon`, `icon_type` | Optional | `name` uses the store's Lucide icon; `svg` uses inline SVG |
| `developer` | Optional | Structured publisher metadata (preferred over `author`) |
| `has_sub_skills`, `sub_skills_count` | Optional | Must be consistent: `true` ↔ `count > 0` |
| `trust` | Optional | `verified` / `community` / `unverified` (default) |
| `stability` | Optional | `experimental` / `beta` / `stable` (default) / `deprecated` |
| `tags` | Optional | Max 20, unique, each ≤32 chars |
| `install_warnings` | Optional | Max 10, each ≤500 chars |

### Preview-only items

If the ZIP is not ready yet, add the item with both `download_url` and `checksum_sha256` set to `null`:

```json
{
  "id": "future_skill",
  "name": "Future Skill",
  "version": "1.0.0",
  "description": "Coming soon.",
  "download_url": null,
  "checksum_sha256": null,
  "tags": ["preview"]
}
```

PELDRUN renders preview-only items in the store with a **Preview** badge and a disabled **Install** button. Users can see that the skill exists, without being able to install an unfinished package.

---

## Step 8 — Validate locally

```bash
python scripts/validate.py
```

Expected output:

```
Validating /path/to/peldrun-skill-catalog/catalog.json
OK: catalog.json is valid (0 warning(s)).
```

The validator enforces every rule that PELDRUN's runtime enforces:

- `id` matches `^[a-z0-9][a-z0-9_]{2,63}$`
- `version` matches semver
- `description` is 1-500 chars
- `download_url` is `https://`
- `checksum_sha256` is a valid SHA-256 hex digest
- The two integrity fields are both set or both `null`
- `brand_color` is `#RRGGBB` when present
- `trust` and `stability` are in the allowed enums
- `has_sub_skills` and `sub_skills_count` are consistent
- `tags` are unique and within length limits
- No duplicate `id` values

If it reports errors, fix them before continuing. The same script runs in CI — a failing local check will fail the PR.

---

## Step 9 — Update `docs/CHANGELOG.md`

Add an entry to the top of the changelog under the current date:

```markdown
## 2026-11-08

### Added

- `code_review` v2.0.0 — Router skill with security_audit and
  performance_review sub-skills. Requires PELDRUN >= 1.0.0.
```

Every catalog change must be accompanied by a changelog entry. The changelog is the authoritative record of what changed and when.

---

## Step 10 — Commit and open a pull request

```bash
git checkout -b add-code-review-skill
git add catalog.json docs/CHANGELOG.md
git commit -m "Add code_review skill v2.0.0"
git push -u origin add-code-review-skill
```

Then open a pull request against `main`. The CI workflow (`Validate Catalog`) runs automatically and blocks merge on any failure.

### Pull request checklist

- [ ] `catalog.json` validates locally (`python scripts/validate.py` returns 0).
- [ ] The new `download_url` is a GitHub Releases asset (not a raw URL or archive tag).
- [ ] The `checksum_sha256` matches the exact ZIP at that URL.
- [ ] The ZIP's `manifest.json` `id` and `version` match the catalog entry.
- [ ] `has_sub_skills` matches the manifest (`true` if `sub_skills` is non-empty).
- [ ] `docs/CHANGELOG.md` has a corresponding entry.
- [ ] Only the intended files are touched (no unrelated reformatting).

---

## Step 11 — Post-merge propagation

After the PR is merged to `main`, GitHub Pages deploys the updated `catalog.json` automatically (typically within 60 seconds). PELDRUN instances will pick up the new item at the next TTL expiry (24 hours by default) — or immediately, if an administrator runs:

```bash
curl -X POST http://localhost:8088/api/skills/catalog/refresh
```

Verify the fetch succeeded:

```bash
curl http://localhost:8088/api/skills/catalog
```

Expected response includes:

```json
{
  "status": "success",
  "items": [
    { "id": "code_review", "version": "2.0.0", "installable": true, ... }
  ],
  "total": 1,
  "status_info": {
    "remote_url_configured": true,
    "remote_count": 1,
    "remote_last_error": null
  }
}
```

The new skill is now visible in **Store → Skills → Catalog** with an **Install** button.

---

## Updating an existing skill

When a skill publishes a new version:

1. Build and publish a new ZIP as a GitHub Release (e.g. `v2.1.0`).
2. Compute its SHA-256.
3. In `catalog.json`, update **only** these fields on the existing item:
   - `version`
   - `download_url`
   - `checksum_sha256`
   - `release_date`
   - `has_sub_skills` / `sub_skills_count` (if sub-skills changed)
4. Add a changelog entry.
5. Open a PR.

Do **not** duplicate the item. PELDRUN treats the `id` field as the identity — two items with the same `id` fail the validator. Updating in place preserves user-facing continuity (the skill appears at the same position in the store, with the same tags and metadata).

PELDRUN detects the version mismatch between the catalog's `version` and the installed skill's version, and renders an **Update available** badge on the card. Clicking it re-downloads the new ZIP, verifies its SHA-256, and replaces the on-disk package atomically.

---

## Removing a skill from the catalog

To hide a skill from the store without breaking users who already installed it:

1. Set `download_url` and `checksum_sha256` to `null` (demote to preview-only).
2. Add a changelog entry explaining why.

To fully remove a skill:

1. Delete the item from `catalog.json`.
2. Add a changelog entry.

Existing installations on user machines are **not** affected. Removing a catalog item only affects future installs — PELDRUN never uninstalls a skill because it disappeared from the catalog. Users who want to remove it do so manually via **Store → Skills → Installed → Delete**.

---

## Deprecating a skill

For skills that will eventually be removed but are still safe to use:

1. Set `"stability": "deprecated"`.
2. Optionally set `"deprecation_message": "Use <new_skill_id> instead."`.
3. Optionally add `"install_warnings": ["Deprecated: use <new_skill_id> instead."]`.

PELDRUN renders a **Deprecated** badge on the catalog card and shows the warning in the install confirmation dialog. Deprecated skills remain installable so users can reproduce old setups, but new users are discouraged.

---

## Common mistakes

| Symptom | Cause | Fix |
|---|---|---|
| PELDRUN shows "Preview only" for an item you marked installable | `checksum_sha256` is missing or malformed | Verify it's 64 lowercase hex characters |
| Install fails with "checksum mismatch" | ZIP was re-uploaded after the checksum was recorded | Recompute the SHA-256 and update `catalog.json` |
| Install fails with "HTTP 404 from download_url" | The GitHub Release was deleted, or the tag is wrong | Verify the URL in a browser first |
| Install fails with "manifest schema validation failed" | The ZIP's `manifest.json` is missing a required field or uses a wrong pattern | Run `load_skill_package` locally against the extracted ZIP |
| Router badge missing after install | `has_sub_skills: false` in the catalog entry, even though the manifest declares sub-skills | Set `has_sub_skills: true` and `sub_skills_count: N` |
| Installed card shows no brand color | `brand_color` is set in the catalog but not in the ZIP's `manifest.json` | Add `brand_color` to the manifest, OR let PELDRUN propagate it automatically on catalog install |
| CI fails on `trailing whitespace` | Editor added spaces at line ends | Enable "trim trailing whitespace on save" |
| CI fails on `CRLF line endings` | File saved with Windows line endings | Configure editor to use LF, or run `dos2unix catalog.json` |
| PELDRUN shows a stale item after a merge | 24-hour TTL has not expired on that instance | Call `POST /api/skills/catalog/refresh` |

---

## See also

- [`../README.md`](../README.md) — repository overview and admin commands.
- [`../schema/catalog.schema.json`](../schema/catalog.schema.json) — JSON Schema reference.
- [`CHANGELOG.md`](CHANGELOG.md) — full history of catalog changes.
- [PELDRUN manifest schema](https://github.com/peldrunai/peldrun/blob/main/backend/omweb/skills/_manifest_schema.json) — the full skill package contract.
- [PELDRUN catalog fetcher](https://github.com/peldrunai/peldrun/blob/main/backend/omweb/skills/catalog/catalog.py) — the reference implementation PELDRUN runs.
```

---

## الملف 8/9: `peldrun-skill-catalog/docs/CHANGELOG.md`

```markdown
# Changelog

All notable changes to the PELDRUN Skill Catalog are recorded in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Changes are listed in reverse chronological order (newest first). Each entry corresponds to a merged pull request that modified `catalog.json` or the catalog's supporting infrastructure.

---

## [Unreleased]

_Changes that have been merged but not yet reflected in any catalog consumer's cache. Consumers refresh automatically within 24 hours of merge, or immediately via `POST /api/skills/catalog/refresh`._

### Added

_No entries yet._

### Changed

_No entries yet._

### Removed

_No entries yet._

---

## 2026-11-08

### Added

- **Repository bootstrap.** Initial creation of `peldrun-skill-catalog` with:
  - `catalog.json` — three preview-only skill entries (`code_review`, `debugging`, `test_planning`), schema version 1.
  - `schema/catalog.schema.json` — JSON Schema Draft-07 definition.
  - `scripts/validate.py` — local validation script mirroring PELDRUN's runtime rules.
  - `.github/workflows/validate-catalog.yml` — CI validation on push and pull request.
  - `README.md`, `LICENSE` (MIT), `docs/ADDING_A_SKILL.md`, and supporting files.

_All three catalog entries are preview-only at bootstrap time — no `download_url` and no `checksum_sha256` are declared yet. They will become installable once the corresponding skill repositories (`peldrun-skill-code-review`, `peldrun-skill-debugging`, `peldrun-skill-test-planning`) publish their first GitHub Release and their ZIP hashes are recorded here._

---

## Entry format

Every entry added to this changelog must include:

1. **Date** — ISO-8601 (`YYYY-MM-DD`), matching the merge date of the pull request.
2. **Category** — one of `Added`, `Changed`, `Removed`, `Deprecated`, `Fixed`, `Security`.
3. **Item reference** — the catalog item's `id` in backticks, followed by the version it applies to.
4. **Summary** — a single line describing the change, written for a user who reads the changelog without opening the diff.

### Example entries

```markdown
### Added
- `code_review` v2.0.0 — Router skill with security_audit and
  performance_review sub-skills. Requires PELDRUN >= 1.0.0.

### Changed
- `code_review` v2.0.0 → v2.1.0 — Updated download URL and SHA-256
  to point at the v2.1.0 release. Adds logic_review sub-skill.

### Removed
- `legacy_linter` — Withdrawn from the catalog after upstream
  maintenance ended. No user-visible uninstall is triggered; existing
  installations remain functional.

### Deprecated
- `code_review` v1.x — Superseded by v2.x's router-based sub-skill
  selection. Old versions remain installable but are hidden from the
  "New" carousel.
```

---

## Versioning policy

The catalog is not itself a software package — it has no version number and no release tags. Instead:

- Every push to `main` is treated as a **catalog snapshot** identified by its commit SHA.
- Consumers cache the snapshot for 24 hours.
- A "catalog version" is therefore a function of `(commit_sha, fetch_timestamp)`, not a human-readable tag.

This policy avoids the common trap of trying to version a data file that changes item-by-item: a `v1.2.0` tag would be meaningless to a consumer whose cache still holds `v1.1.0` for another 23 hours.

The `schema_version` field inside `catalog.json` is a **format** version, not a **content** version. It is incremented only when the on-disk shape changes in a way that requires consumer code changes (e.g. adding a required field, renaming a field). In that case, PELDRUN's fetcher rejects caches whose `schema_version` does not match what its `catalog.py` knows how to parse.

---

## Related repositories

- [peldrun](https://github.com/peldrunai/peldrun) — the main application.
- [peldrun-skill-code-review](https://github.com/peldrunai/peldrun-skill-code-review) — router-based code review skill.
- [peldrun-skill-debugging](https://github.com/peldrunai/peldrun-skill-debugging) — debugging toolkit skill.
- [peldrun-skill-test-planning](https://github.com/peldrunai/peldrun-skill-test-planning) — test planning skill.
- [peldrun-provider-catalog](https://github.com/peldrunai/peldrun-provider-catalog) — the sibling catalog for Provider Packages.
```
 
 