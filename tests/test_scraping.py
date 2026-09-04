import json

from scraping.acquisition.corpus import LocalCorpus
from scraping.discovery.filesystem import filesystem_uris
from scraping.discovery.web import extract_links
from scraping.uri import normalize_uri


def test_normalize_path_to_file_uri(tmp_path):
    assert normalize_uri(str(tmp_path / "x.pdf")).startswith("file:///")


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
    assert record is not None
    assert (corpus.root / record.raw_path).exists()
    rows = corpus.manifest.read_text(encoding="utf-8").splitlines()
    assert json.loads(rows[0])["content_hash"] == record.content_hash
    assert (tmp_path / "corpus" / "extracted").is_dir()
