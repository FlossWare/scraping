import argparse
from pathlib import Path
from urllib.parse import urlparse

from .acquisition import LocalCorpus, fetch_uri
from .discovery.filesystem import filesystem_uris
from .discovery.sitemap import sitemap_urls
from .discovery.web import crawl
from .uri import normalize_uri


def _read_uris(path: str) -> list[str]:
    return [normalize_uri(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip() and not line.lstrip().startswith("#")]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="scrape", description="Acquire web and filesystem resources into a local corpus.")
    parser.add_argument("sources", nargs="*", help="URLs or filesystem paths")
    parser.add_argument("--uris", action="append", default=[], help="Text file containing one URI/path per line")
    parser.add_argument("--sitemap", action="append", default=[], help="Sitemap or sitemap-index URI")
    parser.add_argument("--output", default="scraped-data/corpus", help="Local corpus directory")
    parser.add_argument("--depth", type=int, default=2)
    parser.add_argument("--max-pages", type=int, default=1000)
    parser.add_argument("--scope", choices=("host", "domain"), default="host")
    parser.add_argument("--rate-limit", type=float, default=0.5, help="Seconds between web requests")
    parser.add_argument("--max-file-size", type=int, default=50_000_000)
    parser.add_argument("--no-robots", action="store_true")
    args = parser.parse_args(argv)

    corpus = LocalCorpus(args.output)
    targets: list[tuple[str, str]] = []
    for source in args.sources:
        uri = normalize_uri(source)
        if uri.startswith("file://"):
            path = urlparse(uri).path
            for child in filesystem_uris(path):
                targets.append((child, "filesystem"))
        elif uri.startswith(("http://", "https://")):
            targets.append((uri, "explicit"))
        else:
            targets.append((uri, "explicit"))
    for path in args.uris:
        targets.extend((uri, "uri-file") for uri in _read_uris(path))
    for sitemap in args.sitemap:
        targets.extend((uri, "sitemap") for uri in sitemap_urls(normalize_uri(sitemap)))

    seen = set()
    stored = 0
    for uri, discovered_by in targets:
        if uri in seen:
            continue
        seen.add(uri)
        try:
            if uri.startswith(("http://", "https://")) and discovered_by == "explicit":
                results = crawl(uri, depth=args.depth, max_pages=args.max_pages, rate_limit=args.rate_limit, scope=args.scope, respect_robots=not args.no_robots)
                for item_uri, data, media_type, method in results:
                    if len(data) > args.max_file_size:
                        continue
                    if corpus.store(item_uri, data, media_type, method):
                        stored += 1
            else:
                data, media_type = fetch_uri(uri, max_size=args.max_file_size)
                if corpus.store(uri, data, media_type, discovered_by):
                    stored += 1
        except (OSError, ValueError) as exc:
            print(f"error: {uri}: {exc}")
    print(f"stored {stored} new resource(s) in {corpus.root}")
    return 0
