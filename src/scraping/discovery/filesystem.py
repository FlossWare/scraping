from pathlib import Path


def filesystem_uris(root: str, *, extensions: set[str] | None = None) -> list[str]:
    base = Path(root).expanduser().resolve()
    if not base.exists():
        raise FileNotFoundError(base)
    if base.is_file():
        return [base.as_uri()]
    result = []
    for path in sorted(p for p in base.rglob("*") if p.is_file()):
        if extensions and path.suffix.lower() not in extensions:
            continue
        result.append(path.as_uri())
    return result


def uri_file(path: str) -> str:
    return Path(path).expanduser().resolve().as_uri()
