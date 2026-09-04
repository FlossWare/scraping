"""URI discovery primitives."""
from .filesystem import filesystem_uris
from .sitemap import sitemap_urls
from .web import crawl, discover_links, extract_links

__all__ = ["crawl", "discover_links", "extract_links", "filesystem_uris", "sitemap_urls"]
