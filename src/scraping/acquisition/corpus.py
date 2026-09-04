import hashlib
import json
import os
import queue
import socket
import threading
from ipaddress import ip_address
from pathlib import Path
from urllib.parse import unquote, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from ..models import AcquiredResource

DEFAULT_USER_AGENT = "FlossWare-scraping/0.1"
DEFAULT_MAX_SIZE = 50_000_000
DEFAULT_DNS_TIMEOUT = 5.0


def _resolve_addresses(hostname: str, timeout: float = DEFAULT_DNS_TIMEOUT) -> set[str]:
    result: queue.Queue[object] = queue.Queue(maxsize=1)

    def resolve():
        try:
            result.put({info[4][0] for info in socket.getaddrinfo(hostname, None)})
        except BaseException as exc:  # propagate resolver failure to the caller
            result.put(exc)

    thread = threading.Thread(target=resolve, daemon=True)
    thread.start()
    thread.join(timeout)
    if thread.is_alive():
        raise OSError(f"DNS resolution timed out for remote host: {hostname}")
    resolved = result.get_nowait()
    if isinstance(resolved, BaseException):
        if isinstance(resolved, socket.gaierror):
            raise OSError(f"unable to resolve remote host: {hostname}") from resolved
        raise OSError(f"unable to resolve remote host: {hostname}") from resolved
    return resolved  # type: ignore[return-value]


def _blocked_address(hostname: str, *, dns_timeout: float = DEFAULT_DNS_TIMEOUT) -> bool:
    addresses = _resolve_addresses(hostname, dns_timeout)
    return any(
        any(
            (
                ip_address(address).is_private,
                ip_address(address).is_loopback,
                ip_address(address).is_link_local,
                ip_address(address).is_multicast,
                ip_address(address).is_unspecified,
                ip_address(address).is_reserved,
            )
        )
        for address in addresses
    )


def validate_remote_uri(
    uri: str, *, allow_private: bool = False, dns_timeout: float = DEFAULT_DNS_TIMEOUT
) -> None:
    parsed = urlparse(uri)
    if parsed.scheme not in {"http", "https", "ftp"}:
        raise ValueError(f"unsupported remote scheme: {parsed.scheme or '<none>'}")
    if not parsed.hostname:
        raise ValueError("remote URI has no hostname")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("credentials in remote URIs are not supported")
    if not allow_private and _blocked_address(parsed.hostname, dns_timeout=dns_timeout):
        raise ValueError(f"refusing private or non-public remote address: {parsed.hostname}")


class _SafeRedirectHandler(HTTPRedirectHandler):
    def __init__(self, *, allow_private: bool, dns_timeout: float = DEFAULT_DNS_TIMEOUT):
        super().__init__()
        self.allow_private = allow_private
        self.dns_timeout = dns_timeout

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urlparse(newurl).scheme == "file":
            raise ValueError("refusing redirect to file://")
        validate_remote_uri(newurl, allow_private=self.allow_private, dns_timeout=self.dns_timeout)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class LocalCorpus:
    """Persist raw acquisition artifacts and a provenance-preserving JSONL manifest."""

    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser().resolve()
        (self.root / "raw").mkdir(parents=True, exist_ok=True)
        (self.root / "extracted").mkdir(exist_ok=True)
        (self.root / "normalized").mkdir(exist_ok=True)
        (self.root / "manifest").mkdir(exist_ok=True)
        (self.root / "state").mkdir(exist_ok=True)
        self.manifest = self.root / "manifest" / "manifest.jsonl"

    def store(self, uri: str, data: bytes, media_type: str, discovered_by: str) -> AcquiredResource:
        digest = hashlib.sha256(data).hexdigest()
        existing = self.root / "raw" / digest[:2] / digest[2:4]
        raw_path = existing / f"{digest}{self._suffix(uri, media_type)}"
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        if not raw_path.exists():
            tmp = raw_path.with_name(raw_path.name + f".{os.getpid()}.tmp")
            tmp.write_bytes(data)
            tmp.replace(raw_path)
        record = AcquiredResource(
            uri, media_type, digest, str(raw_path.relative_to(self.root)), len(data),
            AcquiredResource.now(), discovered_by,
        )
        line = (json.dumps(record.__dict__, sort_keys=True) + "\n").encode("utf-8")
        fd = os.open(self.manifest, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
        try:
            os.write(fd, line)
            os.fsync(fd)
        finally:
            os.close(fd)
        return record

    @staticmethod
    def _suffix(uri: str, media_type: str) -> str:
        suffix = Path(unquote(urlparse(uri).path)).suffix.lower()
        if suffix and len(suffix) <= 10:
            return suffix
        return {"text/html": ".html", "application/pdf": ".pdf", "text/plain": ".txt"}.get(media_type, ".bin")


def read_file_uri(uri: str, *, max_size: int) -> tuple[bytes, str]:
    parsed = urlparse(uri)
    if parsed.scheme != "file":
        raise ValueError("not a file URI")
    if parsed.netloc not in {"", "localhost"}:
        raise ValueError("remote file hosts are not supported")
    if max_size < 1:
        raise ValueError("max_size must be positive")
    path = Path(unquote(parsed.path)).resolve()
    size = path.stat().st_size
    if size > max_size:
        raise ValueError(f"resource exceeds max size: {size} > {max_size}")
    return path.read_bytes(), _media_type(path.suffix)


def fetch_uri(
    uri: str,
    *,
    timeout: float = 30.0,
    max_size: int = DEFAULT_MAX_SIZE,
    user_agent: str = DEFAULT_USER_AGENT,
    allow_private: bool = False,
    dns_timeout: float = DEFAULT_DNS_TIMEOUT,
) -> tuple[bytes, str]:
    if timeout <= 0 or max_size < 1 or dns_timeout <= 0:
        raise ValueError("timeout, max_size, and dns_timeout must be positive")
    parsed = urlparse(uri)
    if parsed.scheme == "file":
        return read_file_uri(uri, max_size=max_size)
    validate_remote_uri(uri, allow_private=allow_private, dns_timeout=dns_timeout)
    request = Request(uri, headers={"User-Agent": user_agent, "Accept": "*/*"})
    opener = build_opener(_SafeRedirectHandler(allow_private=allow_private, dns_timeout=dns_timeout))
    with opener.open(request, timeout=timeout) as response:
        length = response.headers.get("Content-Length")
        if length:
            try:
                length_value = int(length)
            except ValueError as exc:
                raise ValueError("invalid Content-Length") from exc
            if length_value > max_size:
                raise ValueError("resource exceeds configured max size")
        data = _read_limited(response, max_size)
        return data, response.headers.get_content_type() or "application/octet-stream"


def _read_limited(response, max_size: int, *, chunk_size: int = 64 * 1024) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = response.read(min(chunk_size, max_size - total + 1))
        if not chunk:
            break
        total += len(chunk)
        if total > max_size:
            raise ValueError("resource exceeds configured max size")
        chunks.append(chunk)
    return b"".join(chunks)


def _media_type(suffix: str) -> str:
    return {
        ".html": "text/html", ".htm": "text/html", ".pdf": "application/pdf", ".txt": "text/plain",
        ".md": "text/markdown", ".json": "application/json", ".xml": "application/xml",
    }.get(suffix.lower(), "application/octet-stream")
