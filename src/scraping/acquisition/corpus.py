import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse, unquote
from urllib.request import urlopen
from .models import AcquiredResource


class LocalCorpus:
    """Persist raw acquisition artifacts and an append-only JSONL manifest."""

    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser().resolve()
        (self.root / "raw").mkdir(parents=True, exist_ok=True)
        (self.root / "extracted").mkdir(exist_ok=True)
        (self.root / "normalized").mkdir(exist_ok=True)
        (self.root / "manifest").mkdir(exist_ok=True)
        (self.root / "state").mkdir(exist_ok=True)
        self.manifest = self.root / "manifest" / "manifest.jsonl"

    def store(self, uri: str, data: bytes, media_type: str, discovered_by: str) -> AcquiredResource | None:
        digest = hashlib.sha256(data).hexdigest()
        existing = self.root / "raw" / digest[:2] / digest[2:4]
        suffix = self._suffix(uri, media_type)
        raw_path = existing / f"{digest}{suffix}"
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        if raw_path.exists():
            return None
        raw_path.write_bytes(data)
        record = AcquiredResource(uri, media_type, digest, str(raw_path.relative_to(self.root)), len(data), AcquiredResource.now(), discovered_by)
        with self.manifest.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record.__dict__, sort_keys=True) + "\n")
        return record

    @staticmethod
    def _suffix(uri: str, media_type: str) -> str:
        path = unquote(urlparse(uri).path)
        suffix = Path(path).suffix.lower()
        if suffix and len(suffix) <= 10:
            return suffix
        return {"text/html": ".html", "application/pdf": ".pdf", "text/plain": ".txt"}.get(media_type, ".bin")


def read_file_uri(uri: str, *, max_size: int) -> tuple[bytes, str]:
    path = Path(unquote(urlparse(uri).path))
    size = path.stat().st_size
    if size > max_size:
        raise ValueError(f"resource exceeds max size: {size} > {max_size}")
    data = path.read_bytes()
    return data, _media_type(path.suffix)


def fetch_uri(uri: str, *, timeout: float = 30.0, max_size: int = 50_000_000, user_agent: str = "FlossWare-scraping/0.1") -> tuple[bytes, str]:
    if urlparse(uri).scheme == "file":
        return read_file_uri(uri, max_size=max_size)
    from urllib.request import Request
    request = Request(uri, headers={"User-Agent": user_agent, "Accept": "*/*"})
    with urlopen(request, timeout=timeout) as response:
        length = response.headers.get("Content-Length")
        if length and int(length) > max_size:
            raise ValueError("resource exceeds configured max size")
        data = response.read(max_size + 1)
        if len(data) > max_size:
            raise ValueError("resource exceeds configured max size")
        return data, response.headers.get_content_type() or "application/octet-stream"


def _media_type(suffix: str) -> str:
    return {".html": "text/html", ".htm": "text/html", ".pdf": "application/pdf", ".txt": "text/plain", ".md": "text/markdown", ".json": "application/json", ".xml": "application/xml"}.get(suffix.lower(), "application/octet-stream")
