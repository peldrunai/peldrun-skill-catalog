# PELDRUN Skill Catalog

> The official machine-readable catalog of installable Skills for [PELDRUN](https://github.com/peldrunai/peldrun).

This repository hosts a single JSON file — `catalog.json` — that PELDRUN instances can fetch over HTTPS to discover installable Skills. It is the remote companion to the built-in catalog shipped inside every PELDRUN backend (`backend/omweb/skills/catalog/builtin_catalog.json`).

---

## How PELDRUN uses this repository

PELDRUN fetches the remote catalog by default. The URL is configurable via `PELDRUN_SKILL_CATALOG_URL`, but the default points at this repository:

```
https://raw.githubusercontent.com/peldrunai/peldrun-skill-catalog/main/catalog.json
```

When the variable is **unset** (default), PELDRUN uses the URL above. When set to an empty string, remote fetching is disabled entirely.

On each fetch, PELDRUN:

1. Fetches `catalog.json` from this repository (24h TTL, negative-cached for 5 minutes on failure).
2. Caches it to disk at `backend/data/skill_catalog_remote_cache.json`.
3. Serves the cached copy if GitHub is unreachable (offline-safe).
4. Merges the remote items with the built-in and any custom local catalog, with this precedence (lowest first):
   - built-in
   - remote (this repository)
   - custom local (`PELDRUN_SKILL_CATALOG_PATH`)
   - test injections (`extra_paths`)

An item in a higher layer with the same `id` overrides the lower one.

See `backend/omweb/skills/catalog/catalog.py` for the full reference implementation.

---

## Repository structure

```
.
├── catalog.json                    # The file PELDRUN fetches. Edit this.
├── schema/
│   └── catalog.schema.json         # JSON Schema for catalog.json
├── docs/
│   ├── ADDING_A_SKILL.md           # Step-by-step guide
│   └── CHANGELOG.md                # Human-readable history
├── scripts/
│   └── validate.py                 # Local validation (pre-push)
└── .github/
    └── workflows/
        └── validate-catalog.yml    # CI validation on every push/PR
```

Only `catalog.json` is consumed by PELDRUN. Everything else exists to keep that one file correct, reviewable, and auditable.

---

## Security model

**A catalog item without a SHA-256 checksum is not installable.** This is enforced at three layers:

1. **This repository** — the CI validator rejects any `download_url` that lacks a matching `checksum_sha256`.
2. **PELDRUN's fetcher** (`catalog.py::is_installable`) — refuses to download a package when either field is missing or the checksum is malformed.
3. **PELDRUN's installer** — computes the SHA-256 of the downloaded ZIP and aborts on mismatch before any file reaches disk.

The intent: a compromised GitHub account cannot push a malicious catalog entry that causes PELDRUN users to install arbitrary instruction packs, because the attacker would also need the SHA-256 of a ZIP they control — and that hash must match what the ZIP bytes actually produce.

Additionally, every skill package is validated against PELDRUN's manifest schema **at install time** (`omweb/skills/manifest.py::load_skill_package`). This catches malformed manifests, path traversal in sub-skill declarations, oversized instructions, and unsafe SVG icons — independently of what the catalog claims.

Skills are **instructional only**. They cannot execute code and cannot access the network beyond what the agent's tools already allow. The threat model for this catalog is therefore narrower than the Provider Package catalog's — but the SHA-256 discipline is kept identical because any weakness in the download path is a supply-chain vector regardless of payload type.

---

## Adding a skill

See [`docs/ADDING_A_SKILL.md`](docs/ADDING_A_SKILL.md).

In short:

1. Package the skill as a `.zip` and publish it as a GitHub Release in the skill's own repository (e.g. `peldrunai/peldrun-skill-code-review`).
2. Compute `sha256sum` of that ZIP.
3. Add an entry to `catalog.json` under `items`.
4. Run `python scripts/validate.py` locally.
5. Commit, push, open a PR. CI validates before merge.

---

## For PELDRUN administrators

### Enable remote catalog fetching (default)

```bash
# Default — no action needed
export PELDRUN_SKILL_CATALOG_URL="https://raw.githubusercontent.com/peldrunai/peldrun-skill-catalog/main/catalog.json"
```

Restart the backend. The next **Store → Skills → Catalog** page load fetches the file.

### Force an immediate refresh

```bash
curl -X POST http://localhost:8088/api/skills/catalog/refresh
```

Bypasses both the 24-hour positive TTL and the 5-minute negative cache.

### Inspect the catalog state

```bash
curl http://localhost:8088/api/skills/catalog
```

The response's `status_info` field contains:

```json
{
  "enabled": true,
  "item_count": 3,
  "builtin_count": 3,
  "remote_count": 3,
  "remote_url_configured": true,
  "remote_url_effective": "https://raw.githubusercontent.com/peldrunai/peldrun-skill-catalog/main/catalog.json",
  "remote_cache_age_seconds": 342,
  "remote_last_attempt_age_seconds": 342,
  "remote_negative_cache_ttl_seconds": 300,
  "remote_last_error": null
}
```

### Disable remote fetching

```bash
export PELDRUN_SKILL_CATALOG_URL=""
```

PELDRUN reverts to its bundled catalog and skips the network call on every load.

### Hide the Catalog tab completely

```bash
export PELDRUN_SKILL_CATALOG_ENABLED=false
```

The **Catalog** tab is hidden from the Skills section. This is a kill switch — useful when a compromised or misconfigured remote catalog is affecting users. It does NOT delete anything; existing installed skills continue to work.

---

## Local validation

Requires Python 3.10+.

```bash
python scripts/validate.py
```

The script checks:

- `catalog.json` parses as JSON.
- `schema_version` matches a supported value.
- Every item passes `SkillCatalogItem` Pydantic validation (mirrored field-by-field).
- Every `download_url` is `https://`.
- Every `checksum_sha256` is a 64-character lowercase hex digest.
- `download_url` and `checksum_sha256` are both set or both `null` (supply-chain integrity).
- `brand_color`, when set, matches `^#[0-9A-Fa-f]{6}$`.
- `trust` is one of `verified`, `community`, `unverified`.
- `stability` is one of `experimental`, `beta`, `stable`, `deprecated`.
- `has_sub_skills` is consistent with `sub_skills_count` (both true/non-zero, or both false/zero).
- No duplicate `id` values.

Exit code is `0` on success, `1` on any failure. CI runs the same script.

---

## License

MIT — see [`LICENSE`](LICENSE).

---

## Related repositories

- [peldrun](https://github.com/peldrunai/peldrun) — the main application.
- [peldrun-provider-catalog](https://github.com/peldrunai/peldrun-provider-catalog) — the sibling catalog for Provider Packages (LLM adapters).
- [peldrun-skill-code-review](https://github.com/peldrunai/peldrun-skill-code-review) — the first skill package intended for this catalog.
- [peldrun-skill-debugging](https://github.com/peldrunai/peldrun-skill-debugging) — debugging toolkit skill.
- [peldrun-skill-test-planning](https://github.com/peldrunai/peldrun-skill-test-planning) — test planning skill.

