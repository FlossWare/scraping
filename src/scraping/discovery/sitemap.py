from urllib.parse import urlparse
from xml.etree import ElementTree

from ..acquisition.corpus import DEFAULT_MAX_SIZE, fetch_uri


def sitemap_urls(
    uri: str,
    *,
    timeout: float = 30.0,
    max_depth: int = 3,
    max_urls: int = 10_000,
    max_size: int = DEFAULT_MAX_SIZE,
    max_total_size: int = 100_000_000,
    allow_private: bool = False,
) -> list[str]:
    """Discover URLs from a bounded sitemap or sitemap-index tree."""
    if max_depth < 0 or max_urls < 1 or max_size < 1 or max_total_size < 1:
        raise ValueError("sitemap limits must be positive and max_depth must be >= 0")
    parsed = urlparse(uri)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("sitemaps must use http:// or https://")
    seen_sitemaps: set[str] = set()
    results: list[str] = []
    total_size = 0

    def visit(current: str, depth: int) -> None:
        nonlocal total_size
        if current in seen_sitemaps or depth > max_depth or len(results) >= max_urls:
            return
        seen_sitemaps.add(current)
        data, _ = fetch_uri(current, timeout=timeout, max_size=max_size, allow_private=allow_private)
        total_size += len(data)
        if total_size > max_total_size:
            raise ValueError("sitemap data exceeds configured total size")
        if b"<!DOCTYPE" in data.upper():
            raise ValueError("DOCTYPE is not permitted in sitemaps")
        root = ElementTree.fromstring(data)
        tag = root.tag.rsplit("}", 1)[-1]
        if tag == "sitemapindex":
            for node in root.iter():
                if node.tag.rsplit("}", 1)[-1] == "loc" and node.text and len(results) < max_urls:
                    visit(node.text.strip(), depth + 1)
            return
        if tag != "urlset":
            raise ValueError(f"Unsupported sitemap root: {tag}")
        for node in root.iter():
            if node.tag.rsplit("}", 1)[-1] == "loc" and node.text and len(results) < max_urls:
                value = node.text.strip()
                if value and value not in results:
                    results.append(value)

    visit(uri, 0)
    return results
