# Curated URI catalogs

These files are version-controlled starting points for reproducible acquisition runs. They are not claims of exhaustive coverage, and each source remains subject to its terms of use, robots policy, licensing, authentication requirements, and rate limits.

- `patents.txt` - patent and intellectual-property sources
- `medical.txt` - medical and biomedical sources
- `engineering.txt` - engineering, standards, and technical references
- `science.txt` - general science and research sources

Use a catalog with:

```bash
scrape --uris sources/engineering.txt
```

The scraper treats each entry as a URI. HTTP(S), FTP, and file URIs are supported. Plain filesystem paths are normalized to `file://` URIs.
