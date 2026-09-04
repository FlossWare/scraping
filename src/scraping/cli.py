import argparse
import time
from pathlib import Path
from urllib.parse import urlparse

from .acquisition import LocalCorpus, fetch_uri
from .acquisition.corpus import DEFAULT_MAX_SIZE
from .discovery.filesystem import filesystem_uris
from .discovery.sitemap import sitemap_urls
from .discovery.web import discover_links
from .uri import normalize_uri


def _read_uris(path: str) -> list[str]:
    return [
        normalize_uri(line.strip())
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="scrape", description="Acquire web and filesystem resources into a local corpus.")
    parser.add_argument("sources", nargs="*", help="URLs or filesystem paths")
    parser.add_argument("--uris", action="append", default=[], help="Text file containing one URI/path per line")
    parser.add_argument("--sitemap", action="append", default=[], help="Sitemap or sitemap-index URI")
    parser.add_argument("--output", default="scraped-data/corpus", help="Local corpus directory")
    parser.add_argument("--depth", type=int, default=2)
    parser.add_argument("--max-pages", type=int, default=1000)
    parser.add_argument("--scope", choices=("host", "domain"), default="host")
    parser.add_argument("--rate-limit", type=float, default=0.5, help="Minimum seconds between remote requests")
    parser.add_argument("--max-file-size", type=int, default=DEFAULT_MAX_SIZE)
    parser.add_argument("--sitemap-depth", type=int, default=3)
    parser.add_argument("--sitemap-max-urls", type=int, default=10_000)
    parser.add_argument("--sitemap-max-total-size", type=int, default=100_000_000)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--allow-private", action="store_true", help="Allow private/link-local remote addresses")
    parser.add_argument("--no-robots", action="store_true")
    args = parser.parse_args(argv)

    if args.depth < 0 or args.max_pages < 1 or args.max_file_size < 1 or args.timeout <= 0 or args.rate_limit < 0:
        parser.error("depth/max-pages/max-file-size must be positive where applicable; timeout > 0; rate-limit >= 0")
    if args.sitemap_depth < 0 or args.sitemap_max_urls < 1 or args.sitemap_max_total_size < 1:
        parser.error("sitemap limits are invalid")
    if not args.sources and not args.uris and not args.sitemap:
        parser.error("at least one source, --uris file, or --sitemap is required")

    corpus = LocalCorpus(args.output)
    targets: list[tuple[str, str]] = []
    failures = 0

    for source in args.sources:
        uri = normalize_uri(source)
        if uri.startswith("file://") and Path(urlparse(uri).path).is_dir():
            targets.extend((child, "filesystem") for child in filesystem_uris(urlparse(uri).path))
        elif uri.startswith(("http://", "https://")):
            try:
                discovered = discover_links(
                    uri, depth=args.depth, max_pages=args.max_pages, rate_limit=args.rate_limit,
                    scope=args.scope, respect_robots=not args.no_robots, timeout=args.timeout,
                    max_size=args.max_file_size, allow_private=args.allow_private,
                )
                targets.extend((item, "crawl") for item in discovered)
            except (OSError, ValueError) as exc:
                print(f"error: {uri}: {exc}")
                failures += 1
        else:
            targets.append((uri, "explicit"))

    for path in args.uris:
        try:
            targets.extend((uri, "uri-file") for uri in _read_uris(path))
        except OSError as exc:
            print(f"error: {path}: {exc}")
            failures += 1

    for sitemap in args.sitemap:
        try:
            targets.extend(
                (uri, "sitemap")
                for uri in sitemap_urls(
                    normalize_uri(sitemap), timeout=args.timeout, max_depth=args.sitemap_depth,
                    max_urls=args.sitemap_max_urls, max_size=args.max_file_size,
                    max_total_size=args.sitemap_max_total_size, allow_private=args.allow_private,
                )
            )
        except (OSError, ValueError) as exc:
            print(f"error: {sitemap}: {exc}")
            failures += 1

    seen: set[str] = set()
    stored = 0
    last_remote_request = 0.0
    for uri, discovered_by in targets:
        if uri in seen:
            continue
        seen.add(uri)
        is_remote = uri.startswith(("http://", "https://", "ftp://"))
        if is_remote and last_remote_request and args.rate_limit > 0:
            time.sleep(max(0.0, args.rate_limit - (time.monotonic() - last_remote_request)))
        try:
            if is_remote:
                last_remote_request = time.monotonic()
            data, media_type = fetch_uri(
                uri, timeout=args.timeout, max_size=args.max_file_size,
                allow_private=args.allow_private,
            )
            corpus.store(uri, data, media_type, discovered_by)
            stored += 1
        except (OSError, ValueError) as exc:
            print(f"error: {uri}: {exc}")
            failures += 1

    print(f"acquired {stored} resource(s) in {corpus.root}")
    return 1 if failures else 0
