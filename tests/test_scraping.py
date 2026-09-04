import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from urllib.request import Request

from scraping.acquisition.corpus import LocalCorpus, _SafeRedirectHandler, fetch_uri, validate_remote_uri
from scraping.cli import main
from scraping.discovery.filesystem import filesystem_uris
from scraping.discovery.sitemap import sitemap_urls
from scraping.discovery.web import RobotsPolicy, crawl, discover_links, extract_links
from scraping.uri import normalize_uri


def test_package_import_smoke():
    import scraping
    assert scraping.AcquiredResource is not None


def test_normalize_path_to_file_uri(tmp_path):
    assert normalize_uri(str(tmp_path / "x.pdf")).startswith("file:///")


def test_normalize_rejects_remote_file_host():
    with pytest.raises(ValueError, match="remote file hosts"):
        normalize_uri("file://server/share/file.txt")


def test_extract_links_normalizes_fragments():
    html = b'<a href="/a">A</a><a href="https://example.org/b#x">B</a><a href="#local">C</a>'
    assert extract_links(html, "https://example.org/") == ["https://example.org/a", "https://example.org/b"]


def test_filesystem_discovery(tmp_path):
    (tmp_path / "a.pdf").write_bytes(b"pdf")
    (tmp_path / "b.txt").write_text("text", encoding="utf-8")
    assert len(filesystem_uris(str(tmp_path))) == 2


def test_corpus_stores_raw_and_manifest(tmp_path):
    corpus = LocalCorpus(tmp_path / "corpus")
    record = corpus.store("file:///tmp/a.txt", b"hello", "text/plain", "filesystem")
    duplicate = corpus.store("file:///tmp/b.txt", b"hello", "text/plain", "filesystem")
    assert record is not None
    assert duplicate is not None
    assert record.content_hash == duplicate.content_hash
    assert (corpus.root / record.raw_path).exists()
    rows = corpus.manifest.read_text(encoding="utf-8").splitlines()
    assert len(rows) == 2
    assert json.loads(rows[1])["uri"] == "file:///tmp/b.txt"


def test_fetch_uri_rejects_unsupported_scheme():
    with pytest.raises(ValueError, match="unsupported remote scheme"):
        fetch_uri("gopher://example.org/")


def test_validate_remote_uri_blocks_loopback():
    with pytest.raises(ValueError, match="private or non-public"):
        validate_remote_uri("http://127.0.0.1/")


def test_fetch_uri_rejects_remote_credentials():
    with pytest.raises(ValueError, match="credentials"):
        fetch_uri("https://user:secret@example.org/", allow_private=True)


def test_fetch_uri_enforces_size_limit(monkeypatch):
    class Headers:
        def get(self, name):
            return None
        def get_content_type(self):
            return "text/plain"

    class Response:
        headers = Headers()
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def read(self, size=-1):
            return b"x" * size

    monkeypatch.setattr(
        "scraping.acquisition.corpus.build_opener",
        lambda handler: type("O", (), {"open": lambda self, request, timeout: Response()})(),
    )
    with pytest.raises(ValueError, match="max size"):
        fetch_uri("https://example.org/large", max_size=10, allow_private=True)


def test_ftp_uses_shared_fetch_controls(monkeypatch):
    class Headers:
        def get(self, name):
            return None
        def get_content_type(self):
            return "text/plain"

    class Response:
        headers = Headers()
        def __init__(self):
            self.done = False
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def read(self, size=-1):
            if self.done:
                return b""
            self.done = True
            return b"ftp-data"

    monkeypatch.setattr(
        "scraping.acquisition.corpus.build_opener",
        lambda handler: type("O", (), {"open": lambda self, request, timeout: Response()})(),
    )
    data, media_type = fetch_uri("ftp://127.0.0.1/file.txt", max_size=100, allow_private=True)
    assert data == b"ftp-data"
    assert media_type == "text/plain"


def test_redirect_handler_rejects_file_redirect():
    handler = _SafeRedirectHandler(allow_private=True)
    with pytest.raises(ValueError, match="file://"):
        handler.redirect_request(Request("https://example.org/"), None, 302, "Found", {}, "file:///etc/passwd")


def test_robots_missing_allows(monkeypatch):
    monkeypatch.setattr("scraping.discovery.web.fetch_uri", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("missing")))
    assert RobotsPolicy().allowed("https://example.org/a") is True


def test_discovery_returns_uris_not_bodies(monkeypatch):
    pages = {
        "https://example.org/": (b'<a href="/child">child</a>', "text/html"),
        "https://example.org/child": (b"child", "text/plain"),
    }
    monkeypatch.setattr("scraping.discovery.web.fetch_uri", lambda uri, **kwargs: pages[uri])
    found = discover_links("https://example.org/", depth=1, max_pages=10, rate_limit=0, scope="host", respect_robots=False, allow_private=True)
    assert found == ["https://example.org/", "https://example.org/child"]


def test_crawl_alias_forwards_limits(monkeypatch):
    seen = {}

    def fake(start, **kwargs):
        seen.update(kwargs)
        return [start]

    monkeypatch.setattr("scraping.discovery.web.discover_links", fake)
    crawl("https://example.org/", timeout=7, max_size=123, allow_private=True)
    assert seen["timeout"] == 7
    assert seen["max_size"] == 123
    assert seen["allow_private"] is True


def test_sitemap_is_bounded_and_rejects_doctype(monkeypatch):
    xml = b'<!DOCTYPE foo><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>https://example.org/a</loc></url></urlset>'
    monkeypatch.setattr("scraping.discovery.sitemap.fetch_uri", lambda *args, **kwargs: (xml, "application/xml"))
    with pytest.raises(ValueError, match="DOCTYPE"):
        sitemap_urls("https://example.org/sitemap.xml", allow_private=True)


def test_sitemap_total_size_is_bounded(monkeypatch):
    xml = b'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>https://example.org/a</loc></url></urlset>'
    monkeypatch.setattr("scraping.discovery.sitemap.fetch_uri", lambda *args, **kwargs: (xml, "application/xml"))
    with pytest.raises(ValueError, match="total size"):
        sitemap_urls("https://example.org/sitemap.xml", max_size=10_000, max_total_size=10, allow_private=True)


def test_cli_returns_nonzero_on_acquisition_error(tmp_path, capsys):
    code = main([str(tmp_path / "missing.txt"), "--output", str(tmp_path / "corpus")])
    assert code == 1
    assert "error:" in capsys.readouterr().out


def test_cli_rejects_empty_invocation(capsys):
    with pytest.raises(SystemExit) as exc:
        main([])
    assert exc.value.code == 2
    assert "at least one source" in capsys.readouterr().err


def test_local_http_server_end_to_end(tmp_path):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = b"hello from local server"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        uri = f"http://127.0.0.1:{server.server_port}/resource.txt"
        data, media_type = fetch_uri(uri, allow_private=True)
        assert data == b"hello from local server"
        assert media_type == "text/plain"
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()
