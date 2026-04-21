#!/usr/bin/env python3
"""
harvest_fdps.py — Static FDP Index harvester
=============================================
Part of the StaticFDP ecosystem (https://github.com/StaticFDP/staticfdp-index).

Reads registered-fdps/*.yaml, fetches each FDP's catalog.ttl,
validates it as DCAT, and writes:
  docs/fdp-index/index.ttl    — DCAT catalog-of-catalogs (RDF Turtle)
  docs/fdp-index/index.jsonld — same as JSON-LD
  docs/index.html             — human-readable discovery page (HTML)

Environment variables (override config file):
  GITHUB_TOKEN       — fine-grained PAT (used to close/label registration issues)
  FORGEJO_TOKEN      — Codeberg token
  INFRASTRUCTURE_OVERRIDE — github | codeberg | both (overrides config file)
"""

import os
import sys
import json
import glob
import re
import textwrap
import urllib.request
import urllib.error
from datetime import date, datetime
from pathlib import Path

# ── Minimal YAML reader ────────────────────────────────────────────────────────

def _load_yaml(path):
    """Very small subset YAML parser — handles str/bool/int scalars and
    two-level nested mappings. No arrays, no anchors."""
    result = {}
    current = result
    parent_key = None
    try:
        with open(path) as f:
            for raw in f:
                line = raw.rstrip()
                if not line or line.lstrip().startswith('#'):
                    continue
                indent = len(line) - len(line.lstrip())
                key_val = line.strip()
                if ':' not in key_val:
                    continue
                k, _, v = key_val.partition(':')
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if indent == 0:
                    if not v:
                        parent_key = k
                        current = result.setdefault(k, {})
                    else:
                        result[k] = v
                        current = result
                        parent_key = None
                else:
                    if parent_key is None:
                        result[k] = v
                    else:
                        current[k] = v
    except FileNotFoundError:
        pass
    return result

_cfg_data = {}

def load_config():
    global _cfg_data
    p = Path(__file__).resolve().parent.parent / 'fdp-index-config.yaml'
    _cfg_data = _load_yaml(str(p))

def cfg(*keys, default=''):
    node = _cfg_data
    for k in keys:
        if not isinstance(node, dict):
            return default
        node = node.get(k, {})
    return node if node != {} else default

# ── Registered FDPs ───────────────────────────────────────────────────────────

def load_registered_fdps():
    """Read registered-fdps/*.yaml — each file describes one FDP."""
    base = Path(__file__).resolve().parent.parent / 'registered-fdps'
    fdps = []
    for path in sorted(base.glob('*.yaml')):
        data = _load_yaml(str(path))
        if data.get('catalog_url'):
            fdps.append(data)
    return fdps

# ── Fetch + validate a catalog ────────────────────────────────────────────────

def fetch_catalog(url, timeout=30):
    """Fetch a catalog URL and return (content_bytes, content_type).
    Returns (None, None) on error."""
    try:
        req = urllib.request.Request(
            url,
            headers={'Accept': 'text/turtle, application/ld+json, */*'},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read(), resp.headers.get('Content-Type', '')
    except Exception as e:
        print(f'  ⚠ fetch failed: {e}', file=sys.stderr)
        return None, None

def has_dcat_catalog(turtle_bytes):
    """Quick check: does the Turtle contain a dcat:Catalog triple?"""
    text = turtle_bytes.decode('utf-8', errors='replace')
    return 'dcat:Catalog' in text or 'https://www.w3.org/ns/dcat#Catalog' in text

# ── RDF generation ────────────────────────────────────────────────────────────

def build_index_ttl(fdps, base_url, today):
    lines = [
        '@prefix dcat:    <https://www.w3.org/ns/dcat#> .',
        '@prefix dcterms: <http://purl.org/dc/terms/> .',
        '@prefix foaf:    <http://xmlns.com/foaf/0.1/> .',
        '@prefix xsd:     <http://www.w3.org/2001/XMLSchema#> .',
        '@prefix fdp:     <https://w3id.org/fdp/fdp-o#> .',
        f'@prefix :        <{base_url}/fdp-index/> .',
        '',
        f'# StaticFDP Index — generated {today}',
        '',
        '# ── FDP Index root ───────────────────────────────────────────────────────────',
        '',
        f'<{base_url}/fdp-index/>',
        '    a                    fdp:MetadataService ;',
        f'    dcterms:title        "{cfg("fdp_index","title","My FDP Index")}"@en ;',
        '    dcterms:description  "A StaticFDP Index. Edit fdp-index-config.yaml to customise."@en ;',
        f'    dcterms:issued       "{today}"^^xsd:date ;',
        f'    dcterms:modified     "{today}"^^xsd:date ;',
        f'    dcterms:license      <{cfg("fdp_index","license","https://creativecommons.org/licenses/by/4.0/")}> ;',
        '    fdp:hasCatalog       :index-catalog .',
        '',
        '# ── Index catalog ─────────────────────────────────────────────────────────────',
        '',
        ':index-catalog a dcat:Catalog ;',
        f'    dcterms:title       "Registered FAIR Data Points"@en ;',
        f'    dcterms:description "All FDPs registered with this StaticFDP Index."@en ;',
        f'    dcterms:issued      "{today}"^^xsd:date ;',
        f'    dcterms:modified    "{today}"^^xsd:date ;',
    ]
    if fdps:
        refs = ' , '.join(f':fdp-{i}' for i in range(len(fdps)))
        lines.append(f'    dcat:dataset        {refs} ;')
    lines.append(f'    dcterms:publisher   :publisher .')
    lines.append('')
    pub_name = cfg('fdp_index', 'publisher_name', 'My Organisation')
    pub_url  = cfg('fdp_index', 'publisher_url',  'https://example.org/')
    lines += [
        ':publisher a foaf:Organization ;',
        f'    foaf:name  "{pub_name}" ;',
        f'    foaf:page  <{pub_url}> .',
        '',
        '# ── Registered FDPs ──────────────────────────────────────────────────────────',
        '',
    ]
    for i, fdp in enumerate(fdps):
        slug = f'fdp-{i}'
        title  = fdp.get('title', f'FDP {i}').replace('"', '\\"')
        cat_url = fdp.get('catalog_url', '')
        lines += [
            f':{slug} a dcat:Dataset ;',
            f'    dcterms:title       "{title}"@en ;',
            f'    dcterms:modified    "{today}"^^xsd:date ;',
            f'    dcat:landingPage    <{fdp.get("landing_page", cat_url)}> ;',
            f'    dcat:distribution   :{slug}-dist .',
            '',
            f':{slug}-dist a dcat:Distribution ;',
            f'    dcterms:format      "text/turtle" ;',
            f'    dcat:downloadURL    <{cat_url}> .',
            '',
        ]
    return '\n'.join(lines)

def build_index_jsonld(fdps, base_url, today):
    datasets = []
    for fdp in fdps:
        datasets.append({
            "@type": "DataCatalog",
            "name": fdp.get('title', 'Untitled FDP'),
            "url": fdp.get('landing_page', fdp.get('catalog_url', '')),
            "distribution": {"contentUrl": fdp.get('catalog_url', '')},
        })
    doc = {
        "@context": "https://schema.org/",
        "@type": "DataCatalog",
        "name": cfg('fdp_index', 'title', 'My FDP Index'),
        "url": f"{base_url}/fdp-index/",
        "dataset": datasets,
        "dateModified": today,
    }
    return json.dumps(doc, indent=2)

def build_index_html(fdps, base_url, today):
    cards = ''
    for fdp in fdps:
        name    = fdp.get('title', 'Untitled FDP')
        land    = fdp.get('landing_page', fdp.get('catalog_url', '#'))
        cat_url = fdp.get('catalog_url', '')
        desc    = fdp.get('description', '')
        harvested = fdp.get('_harvested', today)
        cards += f"""
      <div class="card">
        <h3>{name}</h3>
        <p>{desc}</p>
        <p style="font-size:12px;color:#9ca3af;margin-top:.4rem;">Last harvested: {harvested}</p>
        <div style="margin-top:.8rem;display:flex;gap:.5rem;flex-wrap:wrap;">
          <a href="{land}" style="font-size:12px;font-weight:600;color:#2563eb;border:1px solid #2563eb;padding:3px 10px;border-radius:5px;text-decoration:none;">Visit FDP →</a>
          <a href="{cat_url}" style="font-size:12px;font-weight:600;color:#6b7280;border:1px solid #d1d5db;padding:3px 10px;border-radius:5px;text-decoration:none;">catalog.ttl</a>
        </div>
      </div>"""

    index_ttl_url  = f"{base_url}/fdp-index/index.ttl"
    index_jsonld_url = f"{base_url}/fdp-index/index.jsonld"
    count = len(fdps)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>FDP Index</title>
  <script type="application/ld+json">
  {{
    "@context": "https://schema.org/",
    "@type": "DataCatalog",
    "name": "{cfg('fdp_index','title','My FDP Index')}",
    "url": "{base_url}/fdp-index/",
    "dateModified": "{today}"
  }}
  </script>
  <style>
    *,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
    body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;font-size:16px;line-height:1.6;color:#1a1a2e;background:#f8fafc}}
    a{{color:#2563eb}}
    .container{{max-width:860px;margin:0 auto;padding:0 24px}}
    header{{background:linear-gradient(135deg,#1e3a8a 0%,#2563eb 60%,#0f4c3a 100%);color:#fff;padding:44px 24px 36px;text-align:center}}
    header h1{{font-size:clamp(24px,4vw,40px);font-weight:800;letter-spacing:-.02em;margin-bottom:8px}}
    header p{{font-size:clamp(14px,2vw,17px);opacity:.85;max-width:560px;margin:0 auto 16px}}
    .badge{{display:inline-block;background:rgba(255,255,255,.18);border:1px solid rgba(255,255,255,.35);border-radius:20px;padding:3px 14px;font-size:12px;letter-spacing:.05em;text-transform:uppercase;margin-bottom:12px}}
    section{{padding:36px 0}}
    section+section{{border-top:1px solid #e5e7eb}}
    h2{{font-size:20px;font-weight:700;margin-bottom:8px}}
    .card-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:1rem;margin-top:1rem}}
    .card{{background:#fff;border:1px solid #e5e7eb;border-radius:10px;padding:1.2rem 1.4rem}}
    .card h3{{font-size:15px;margin-bottom:4px}}
    .card p{{font-size:14px;color:#6b7280}}
    code{{font-family:monospace;font-size:13px;background:#f1f5f9;padding:2px 6px;border-radius:4px}}
    pre{{background:#1e293b;color:#e2e8f0;padding:1rem 1.2rem;border-radius:8px;font-size:13px;overflow-x:auto;margin-top:.6rem}}
    footer{{background:#1a1a2e;color:rgba(255,255,255,.5);padding:20px;text-align:center;font-size:13px}}
    footer a{{color:rgba(255,255,255,.7)}}
  </style>
</head>
<body>
<header>
  <div class="container">
    <div class="badge">FDP Index</div>
    <h1>{cfg('fdp_index','title','My FDP Index')}</h1>
    <p>{count} registered FAIR Data Point{'s' if count != 1 else ''} &nbsp;·&nbsp; Last updated {today}</p>
    <div style="margin-top:12px;display:flex;gap:.6rem;justify-content:center;flex-wrap:wrap">
      <a href="{index_ttl_url}" style="font-size:13px;font-weight:600;color:#fff;border:1px solid rgba(255,255,255,.5);padding:4px 14px;border-radius:6px;text-decoration:none;">index.ttl (RDF)</a>
      <a href="{index_jsonld_url}" style="font-size:13px;font-weight:600;color:#fff;border:1px solid rgba(255,255,255,.5);padding:4px 14px;border-radius:6px;text-decoration:none;">index.jsonld</a>
    </div>
  </div>
</header>
<main class="container">
  <section>
    <h2>Registered FAIR Data Points</h2>
    <p>These FDPs are harvested daily. Click a card to visit the FDP or download its catalog.</p>
    <div class="card-grid">
      {cards if cards else '<p style="color:#9ca3af;margin-top:.8rem;">No FDPs registered yet. <a href="https://github.com/StaticFDP/staticfdp-index/issues/new?template=register-fdp.yml">Register yours →</a></p>'}
    </div>
  </section>
  <section>
    <h2>Machine-readable access</h2>
    <pre>curl {index_ttl_url}
# or
curl {index_jsonld_url}</pre>
    <pre style="margin-top:.6rem"># Python
from rdflib import Graph
g = Graph()
g.parse("{index_ttl_url}")
for s, p, o in g:
    print(s, p, o)</pre>
  </section>
  <section>
    <h2>Register your FDP</h2>
    <p>Open a <a href="https://github.com/StaticFDP/staticfdp-index/issues/new?template=register-fdp.yml">Register FDP issue</a> with your catalog URL and it will be included in the next harvest.</p>
  </section>
</main>
<footer>
  StaticFDP Ecosystem &nbsp;·&nbsp;
  <a href="https://github.com/StaticFDP/staticfdp-index">GitHub</a> &nbsp;·&nbsp;
  <a href="https://codeberg.org/StaticFDP/staticfdp-index">Codeberg</a>
</footer>
</body>
</html>"""

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    load_config()
    base_url = cfg('fdp_index', 'base_url', 'https://OWNER.github.io/staticfdp-index')
    today    = str(date.today())
    timeout  = int(cfg('harvest', 'timeout_seconds', 30))

    print(f'StaticFDP Index harvester — {today}')
    print(f'Base URL: {base_url}')

    fdps = load_registered_fdps()
    print(f'Registered FDPs: {len(fdps)}')

    # Harvest each FDP
    harvested = []
    for fdp in fdps:
        url = fdp.get('catalog_url', '')
        print(f'  → {fdp.get("title","?")}  {url}')
        body, ctype = fetch_catalog(url, timeout=timeout)
        if body and has_dcat_catalog(body):
            print(f'    ✓ valid DCAT catalog ({len(body)} bytes)')
            fdp['_harvested'] = today
            harvested.append(fdp)
        else:
            print(f'    ✗ skipped (unreachable or not a DCAT catalog)')
            if cfg('harvest', 'soft_fail', 'true').lower() in ('true', '1', 'yes'):
                # Still include in index with last known harvest date
                harvested.append(fdp)

    # Write outputs
    out_dir = Path(__file__).resolve().parent.parent / 'docs' / 'fdp-index'
    out_dir.mkdir(parents=True, exist_ok=True)

    (out_dir / 'index.ttl').write_text(build_index_ttl(harvested, base_url, today))
    print('Wrote docs/fdp-index/index.ttl')

    (out_dir / 'index.jsonld').write_text(build_index_jsonld(harvested, base_url, today))
    print('Wrote docs/fdp-index/index.jsonld')

    docs_dir = Path(__file__).resolve().parent.parent / 'docs'
    (docs_dir / 'index.html').write_text(build_index_html(harvested, base_url, today))
    print('Wrote docs/index.html')

    print(f'Done — {len(harvested)} FDPs in index.')

if __name__ == '__main__':
    main()
