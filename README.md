# FlossWare scraping

Local-first resource acquisition and web scraping capability.

## Installation

The PyPI distribution is `flossware-scraping`; the import package remains `scraping`.

```bash
pip install flossware-scraping
scrape --help
```

## Supported sources

- `http://` and `https://` web resources
- `ftp://` resources
- `file://` local filesystem resources
- plain filesystem paths, normalized to `file://`
- URL/URI catalogs
- XML sitemaps and bounded sitemap indexes
- same-host or same-domain link discovery

## Quick start

```bash
scrape https://example.com/
scrape /exports/papers/foo.pdf
scrape --uris sources/patents.txt
scrape --sitemap https://example.com/sitemap.xml
```

A run creates a local corpus:

```text
scraped-data/corpus/
├── raw/
├── extracted/
├── normalized/
├── manifest/manifest.jsonl
└── state/
```

Raw acquisition artifacts are preserved and never modified by downstream processing. Content is addressed by SHA-256. Duplicate bytes are stored once, while every source URI still receives its own manifest record so provenance is retained.

## Web discovery defaults

- depth: `2`
- maximum discovered pages: `1000`
- scope: same host
- robots.txt: respected when available; an unavailable robots.txt is not treated as an explicit disallow
- rate limit: `0.5` seconds between requests
- maximum resource size: `50 MB`
- timeout: `30` seconds
- DNS resolution timeout: `5` seconds
- URL fragments are removed for identity/discovery
- private, loopback, link-local, multicast, reserved, and unspecified remote addresses are blocked by default
- redirects are followed only to allowed HTTP(S)/FTP targets; redirects to `file://` are rejected
- credentials embedded in remote URLs are rejected

Override these with `--depth`, `--max-pages`, `--scope`, `--rate-limit`, `--max-file-size`, `--timeout`, `--allow-private`, `--no-robots`, `--sitemap-depth`, `--sitemap-max-urls`, and `--sitemap-max-total-size`.

`--allow-private` is intended for trusted environments such as internal test networks. Do not expose it as an unrestricted public-fetch service.

DNS/IP validation is performed immediately before each remote request and redirect. This blocks ordinary SSRF attempts and bounds resolver hangs. A DNS-rebinding race between validation and connection remains dependent on the operating system resolver/network stack and is considered outside the local CLI threat model.

## URI catalogs

Curated starting points live under `sources/`. They are version-controlled repository resources, not claims of exhaustive coverage. Each source remains subject to its terms of use, robots policy, licensing, authentication requirements, and rate limits.

```bash
scrape --uris sources/engineering.txt
```

The catalogs are intentionally plain text so they can be reviewed, diffed, reused, and fed to automation.

## Architecture

Discovery and acquisition are separate capabilities:

```text
Discovery
  ├── explicit URI
  ├── URI catalog
  ├── sitemap
  ├── filesystem
  └── link traversal
          ↓
       URI set
          ↓
Acquisition
  ├── HTTP(S)
  ├── FTP
  └── filesystem
          ↓
   AcquiredResource
          ↓
     Local corpus
```

Link traversal performs bounded transient HTTP reads to discover additional links. Those bytes are not persisted as acquisition records until the acquisition stage consumes the discovered URI set. This intentionally means a page reached by link traversal may be fetched twice in a run: once for discovery and once for durable acquisition. The duplication keeps the capability boundary clean; a transient same-run cache can be added later without changing the public contract.

Parsing, extraction, normalization, chunking, embedding, indexing, graph construction, and retrieval remain downstream capabilities.

## Development

```bash
python -m pip install -e '.[dev]'
python -m pytest -q
python -m build
python -m twine check dist/*
```

Versioning uses FlossWare's `X.Y` convention. **Builds, tests, pull requests, and merges do not require Git tags.** The package version is read from `pyproject.toml`. Any future publication workflow is independent of normal CI/build validation.
