# staticfdp-index

A **Static FDP Index** — the second layer of the StaticFDP ecosystem
([GitHub](https://github.com/StaticFDP/staticfdp) · [Codeberg](https://codeberg.org/StaticFDP/staticfdp)).

An FDP Index is a registry of FAIR Data Points. FDPs register by opening a
GitHub Issue or submitting a YAML pull request. A CI pipeline periodically
harvests all registered FDPs, validates their catalogs, and rebuilds a
machine-readable DCAT index served as static RDF + an HTML discovery page.
No dedicated server required.

---

## Part of the StaticFDP Ecosystem

| Repository | GitHub | Codeberg | Layer |
|---|---|---|---|
| staticfdp | [github.com/StaticFDP/staticfdp](https://github.com/StaticFDP/staticfdp) | [codeberg.org/StaticFDP/staticfdp](https://codeberg.org/StaticFDP/staticfdp) | FAIR Data Point |
| **staticfdp-index** ← you are here | [github.com/StaticFDP/staticfdp-index](https://github.com/StaticFDP/staticfdp-index) | [codeberg.org/StaticFDP/staticfdp-index](https://codeberg.org/StaticFDP/staticfdp-index) | FDP Index |
| staticfdp-vp | [github.com/StaticFDP/staticfdp-vp](https://github.com/StaticFDP/staticfdp-vp) | [codeberg.org/StaticFDP/staticfdp-vp](https://codeberg.org/StaticFDP/staticfdp-vp) | Virtual Platform |

---

## How it works

1. **Register** — an FDP operator opens a GitHub Issue using the *Register FDP* template,
   providing their FDP's catalog URL
2. **Harvest** — a scheduled CI pipeline (`scripts/harvest_fdps.py`) fetches every
   registered catalog, validates it as DCAT, and extracts titles / descriptions
3. **Publish** — the pipeline writes `docs/fdp-index/index.ttl` (DCAT catalog of catalogs)
   and `docs/fdp-index/index.jsonld`, then commits and pushes; GitHub / Codeberg Pages
   serves the result immediately

```
FDP operator opens Issue
        │
        ▼
  ┌────────────────────┐
  │  registered-fdps/  │  ← YAML registry of FDP catalog URLs
  └────────┬───────────┘
           │  harvest (scheduled CI)
           ▼
  scripts/harvest_fdps.py
           │
           ├──► docs/fdp-index/index.ttl
           ├──► docs/fdp-index/index.jsonld
           └──► docs/index.html  (human-readable discovery page)
```

---

## Quick start

**GitHub:**
```bash
git clone https://github.com/StaticFDP/staticfdp-index
cd staticfdp-index
bash scripts/setup.sh          # configure GitHub / Codeberg / both
```

**Codeberg:**
```bash
git clone https://codeberg.org/StaticFDP/staticfdp-index
cd staticfdp-index
bash scripts/setup.sh
```

Then:
1. Set secrets (`GITHUB_TOKEN` for GitHub Actions, `FORGEJO_TOKEN` for Woodpecker)
2. Enable GitHub Pages (branch `main`, path `/docs`)
3. Invite FDP operators to open *Register FDP* Issues

---

## Registering an FDP

Open an Issue using the **Register FDP** template and provide:
- FDP name
- Catalog URL (must resolve to valid Turtle containing a `dcat:Catalog`)
- Contact / maintainer

The harvest pipeline runs daily and on every new registration issue.

---

## Configuration (`fdp-index-config.yaml`)

```yaml
fdp_index:
  title: "My FDP Index"
  base_url: https://OWNER.github.io/staticfdp-index
  publisher_name: "My Organisation"
  publisher_url: https://example.org/

infrastructure:
  primary: github          # github | codeberg | both
  github:
    enabled: true
    repo: OWNER/staticfdp-index
    pages_url: https://OWNER.github.io/staticfdp-index
  codeberg:
    enabled: false
    repo: OWNER/staticfdp-index
    base_url: https://codeberg.org
    pages_url: https://OWNER.codeberg.page/staticfdp-index
```

---

## Secrets required

| Secret | Purpose |
|---|---|
| `GITHUB_TOKEN` | Commit generated files (GitHub Actions) |
| `FORGEJO_TOKEN` | Commit generated files (Woodpecker / Codeberg) |

---

## License

MIT.
