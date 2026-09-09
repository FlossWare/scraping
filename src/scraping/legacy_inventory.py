import hashlib
import json
import os
from collections import Counter
from pathlib import Path
from typing import Any


_JSON_FIELD_NAMES = ("url", "title", "content", "source", "category")


def _extension(path: Path) -> str:
    suffix = path.suffix.lower()
    return suffix if suffix else "[no extension]"


def _json_schema(record: dict[str, Any]) -> str:
    keys = set(record)
    if "question_id" in keys and "link" in keys and "answer_count" in keys:
        return "stackoverflow"
    if "content" in keys and "url" in keys and "title" in keys:
        if "metadata" in keys or "authors" in keys or "published_date" in keys:
            return "research-enriched"
        return "url-title-content"
    if "url" in keys and "content" in keys:
        return "url-content"
    if "link" in keys and "body" in keys:
        return "link-body"
    if "url" in keys:
        return "url-other"
    return "other"


def _value_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int) and not isinstance(value, bool):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def inventory_corpus(root: str | Path) -> dict[str, Any]:
    """Read-only, streaming inventory of a historical scraped corpus."""
    root = Path(root).expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"corpus path is not a directory: {root}")

    total_files = 0
    total_bytes = 0
    files_by_type = Counter()
    extensions = Counter()
    categories = Counter()
    category_files = Counter()
    category_bytes = Counter()
    json_valid = 0
    json_malformed = 0
    json_field_presence = Counter()
    json_field_types: dict[str, Counter] = {name: Counter() for name in _JSON_FIELD_NAMES}
    json_schemas = Counter()
    json_url_count = 0
    json_url_duplicates = 0
    seen_urls: set[str] = set()
    md5_url_matches = 0
    md5_url_mismatches = 0
    json_non_object = 0
    size_buckets = Counter()
    top_level_files = Counter()
    top_level_bytes = Counter()

    for dirpath, _, filenames in os.walk(root):
        directory = Path(dirpath)
        for filename in filenames:
            path = directory / filename
            try:
                size = path.stat().st_size
            except OSError:
                continue
            total_files += 1
            total_bytes += size
            ext = _extension(path)
            extensions[ext] += 1
            if size < 1024:
                size_bucket = "<1KB"
            elif size < 10 * 1024:
                size_bucket = "1KB-10KB"
            elif size < 100 * 1024:
                size_bucket = "10KB-100KB"
            elif size < 1024 * 1024:
                size_bucket = "100KB-1MB"
            else:
                size_bucket = ">1MB"
            size_buckets[size_bucket] += 1

            relative = path.relative_to(root)
            top = relative.parts[0] if relative.parts else "[root]"
            top_level_files[top] += 1
            top_level_bytes[top] += size

            if ext == ".json":
                files_by_type["json"] += 1
                try:
                    with path.open("r", encoding="utf-8") as handle:
                        record = json.load(handle)
                except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                    json_malformed += 1
                    continue
                if not isinstance(record, dict):
                    json_non_object += 1
                    continue
                json_valid += 1
                json_schemas[_json_schema(record)] += 1
                category = record.get("category")
                if isinstance(category, str) and category:
                    categories[category] += 1
                    category_files[category] += 1
                    category_bytes[category] += size
                for field in _JSON_FIELD_NAMES:
                    if field in record:
                        json_field_presence[field] += 1
                        json_field_types[field][_value_type(record[field])] += 1
                url = record.get("url")
                if isinstance(url, str) and url:
                    json_url_count += 1
                    if url in seen_urls:
                        json_url_duplicates += 1
                    else:
                        seen_urls.add(url)
                    if hashlib.md5(url.encode("utf-8")).hexdigest() == path.stem.lower():
                        md5_url_matches += 1
                    else:
                        md5_url_mismatches += 1
            elif ext == ".pdf":
                files_by_type["pdf"] += 1
            else:
                files_by_type["other"] += 1

    return {
        "corpus": {"path": str(root), "files": total_files, "bytes": total_bytes},
        "file_types": dict(files_by_type),
        "extensions": dict(extensions.most_common()),
        "size_distribution": dict(size_buckets),
        "categories": {
            category: {"files": category_files[category], "bytes": category_bytes[category]}
            for category in sorted(categories)
        },
        "top_level": {
            category: {"files": top_level_files[category], "bytes": top_level_bytes[category]}
            for category in sorted(top_level_files)
        },
        "json": {
            "valid": json_valid,
            "malformed": json_malformed,
            "non_object": json_non_object,
            "schemas": dict(json_schemas),
            "field_presence": dict(json_field_presence),
            "field_types": {field: dict(counter) for field, counter in json_field_types.items()},
            "url_count": json_url_count,
            "url_duplicates": json_url_duplicates,
            "filename_identity": {
                "md5_url_matches": md5_url_matches,
                "md5_url_mismatches": md5_url_mismatches,
            },
        },
    }


def write_inventory(root: str | Path, output: str | Path) -> dict[str, Any]:
    report = inventory_corpus(root)
    output = Path(output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report
