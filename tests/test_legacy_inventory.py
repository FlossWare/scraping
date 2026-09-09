import hashlib
import json

from scraping.legacy_inventory import inventory_corpus


def test_inventory_classifies_files_and_json_variants(tmp_path):
    category = tmp_path / "category"
    category.mkdir()
    url = "https://example.org/article"
    (category / f"{hashlib.md5(url.encode()).hexdigest()}.json").write_text(
        json.dumps({"url": url, "title": "Article", "content": "text", "source": "test", "category": "category"}),
        encoding="utf-8",
    )
    (category / "stackoverflow.json").write_text(
        json.dumps({"question_id": 1, "link": "https://stackoverflow.com/q/1", "answer_count": 2}),
        encoding="utf-8",
    )
    (category / "broken.json").write_text("{broken", encoding="utf-8")
    (category / "thing.pdf").write_bytes(b"pdf")
    (category / "README.md").write_text("readme", encoding="utf-8")

    report = inventory_corpus(tmp_path)

    assert report["corpus"]["files"] == 5
    assert report["file_types"] == {"json": 3, "pdf": 1, "other": 1}
    assert report["json"]["valid"] == 2
    assert report["json"]["malformed"] == 1
    assert report["json"]["schemas"]["url-title-content"] == 1
    assert report["json"]["schemas"]["stackoverflow"] == 1
    assert report["json"]["url_count"] == 1
    assert report["json"]["filename_identity"]["md5_url_matches"] == 1
    assert report["json"]["filename_identity"]["md5_url_mismatches"] == 0
    assert report["categories"]["category"]["files"] == 1
    assert report["extensions"][".json"] == 3


def test_inventory_is_read_only(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    path = source / "a.txt"
    path.write_text("hello", encoding="utf-8")
    before = path.stat().st_mtime_ns

    inventory_corpus(source)

    assert path.read_text(encoding="utf-8") == "hello"
    assert path.stat().st_mtime_ns == before
