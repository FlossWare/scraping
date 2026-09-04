from pathlib import Path
from urllib.parse import urlparse, urlunparse

SUPPORTED_SCHEMES = {"http", "https", "ftp", "file"}


def normalize_uri(value: str) -> str:
    """Normalize a user-supplied path or URI to a canonical URI."""
    value = value.strip()
    if not value:
        raise ValueError("URI/path cannot be empty")
    parsed = urlparse(value)
    if not parsed.scheme:
        return Path(value).expanduser().resolve().as_uri()
    scheme = parsed.scheme.lower()
    if scheme not in SUPPORTED_SCHEMES:
        raise ValueError(f"Unsupported URI scheme: {scheme}")
    if scheme == "file":
        return Path(parsed.path).expanduser().resolve().as_uri()
    return urlunparse((scheme, parsed.netloc, parsed.path or "/", parsed.params, parsed.query, ""))
