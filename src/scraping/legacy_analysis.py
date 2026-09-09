#!/usr/bin/env python3
"""Analyze schema/source relationships in a historical scraped corpus.

This utility is intentionally standalone and read-only. It performs a second
pass over JSON records to produce compatibility-oriented cross-tabs without
changing the historical corpus.
"""

import argparse
import json
import os
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def json_schema(record: dict[str, Any]) -> str:
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


def analyze(root: str | Path, top_n: int = 100) -> dict[str, Any]:
    root = Path(root).expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"corpus path is not a directory: {root}")

    category_schema: dict[str, Counter[str]] = defaultdict(Counter)
    source_schema: dict[str, Counter[str]] = defaultdict(Counter)
    schema_source: dict[str, Counter[str]] = defaultdict(Counter)
    category_source: dict[str, Counter[str]] = defaultdict(Counter)
    missing_category = Counter()
    missing_source = Counter()
    malformed = 0
    non_object = 0
    valid = 0

    for dirpath, _, filenames in os.walk(root):
        for filename in filenames:
            if not filename.lower().endswith(".json"):
                continue
            path = Path(dirpath) / filename
            try:
                with path.open("r", encoding="utf-8") as handle:
                    record = json.load(handle)
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                malformed += 1
                continue
            if not isinstance(record, dict):
                non_object += 1
                continue

            valid += 1
            schema = json_schema(record)
            category = record.get("category")
            source = record.get("source")
            category = category if isinstance(category, str) and category else "[missing]"
            source = source if isinstance(source, str) and source else "[missing]"

            category_schema[category][schema] += 1
            source_schema[source][schema] += 1
            schema_source[schema][source] += 1
            category_source[category][source] += 1
            if category == "[missing]":
                missing_category[schema] += 1
            if source == "[missing]":
                missing_source[schema] += 1

    def serialize(matrix: dict[str, Counter[str]]) -> dict[str, dict[str, int]]:
        return {
            key: dict(counter.most_common())
            for key, counter in sorted(matrix.items(), key=lambda item: (-sum(item[1].values()), item[0]))
        }

    def top(counter: Counter[str]) -> list[dict[str, Any]]:
        return [{"value": key, "count": count} for key, count in counter.most_common(top_n)]

    return {
        "corpus": {"path": str(root)},
        "json": {
            "valid": valid,
            "malformed": malformed,
            "non_object": non_object,
        },
        "category_schema": serialize(category_schema),
        "source_schema": serialize(source_schema),
        "schema_source": serialize(schema_source),
        "category_source": serialize(category_source),
        "missing": {
            "category_by_schema": dict(missing_category),
            "source_by_schema": dict(missing_source),
        },
        "top_categories": top(Counter({k: sum(v.values()) for k, v in category_schema.items()})),
        "top_sources": top(Counter({k: sum(v.values()) for k, v in source_schema.items()})),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Analyze legacy JSON schema/category/source relationships without modifying the corpus."
    )
    parser.add_argument("root", help="Root directory of the historical corpus")
    parser.add_argument("--output", "-o", default="legacy-analysis.json")
    parser.add_argument("--top", type=int, default=100, help="Maximum entries in top lists")
    args = parser.parse_args()
    if args.top < 1:
        parser.error("--top must be at least 1")

    try:
        report = analyze(args.root, args.top)
        output = Path(args.output).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except (OSError, ValueError) as exc:
        parser.error(str(exc))

    print(f"Analysis complete: {report['json']['valid']:,} valid JSON records")
    print(f"Categories: {len(report['category_schema']):,}")
    print(f"Sources: {len(report['source_schema']):,}")
    print(f"Report: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
