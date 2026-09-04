# FlossWare scraping

Local-first resource acquisition and web scraping capability.

## Supported sources

- `http://` and `https://` web resources
- `ftp://` resources
- `file://` local filesystem resources
- plain filesystem paths, normalized to `file://`
- URL/URI catalogs
- XML sitemaps and sitemap indexes
- same-host or same-domain link crawling

## Quick start

```bash
pip install scraping
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

Raw acquisition artifacts are preserved and are never modified by downstream processing. Content is addressed by SHA-256 and duplicate raw content is not stored twice.

## Web crawling defaults

- depth: `2`
- maximum pages: `1000`
- scope: same host
- robots.txt: respected
- rate limit: `0.5` seconds between requests
- maximum resource size: `50 MB`
- URL fragments are removed for identity/discovery

Override these with `--depth`, `--max-pages`, `--scope`, `--rate-limit`, `--max-file-size`, and `--no-robots`.

## URI catalogs

Curated starting points live under `sources/`. They are deliberately plain text so they can be reviewed, diffed, reused, and fed to automation.

## Architecture

Discovery is separate from acquisition. Discovery finds resources; acquisition preserves the original bytes and records provenance. Parsing, normalization, chunking, embedding, indexing, and retrieval are downstream capabilities.

This repository follows FlossWare engineering standards and treats released artifacts as derived, reproducible delivery outputs.

## Development

```bash
python -m pip install -e '.[dev]'
python -m unittest discover -s tests -v
python -m build
```

Versioning uses FlossWare's `X.Y` convention. Release tags are exactly `X.Y`, without a `v` prefix.
