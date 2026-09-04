"""Acquisition primitives."""
from .filesystem import filesystem_uris
from .sitemap import sitemap_urls
from .web import crawl, extract_links

__all__ = ["crawl", "extract_links", "filesystem_uris", "sitemap_urls"]
