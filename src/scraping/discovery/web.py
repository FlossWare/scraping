from html.parser import HTMLParser
import time
from urllib.parse import urldefrag, urljoin, urlparse
from urllib.request import Request, urlopen

from ..acquisition.corpus import DEFAULT_MAX_SIZE, DEFAULT_USER_AGENT, fetch_uri


class LinkExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "a":
            return
        for key, value in attrs:
            if key.lower() == "href" and value:
                self.links.append(value)


def extract_links(html: bytes, base_uri: str) -> list[str]:
    parser = LinkExtractor()
    parser.feed(html.decode("utf-8", errors="replace"))
    result = []
    for link in parser.links:
        absolute, _ = urldefrag(urljoin(base_uri, link))
        if urlparse(absolute).scheme in {"http", "https"}:
            result.append(absolute)
    return list(dict.fromkeys(result))


def allowed_by_host(uri: str, root: str, scope: str = "host") -> bool:
    a, b = urlparse(uri), urlparse(root)
    if a.scheme not in {"http", "https"}:
        return False
    if scope == "domain":
        return a.hostname == b.hostname or (a.hostname or "").endswith("." + (b.hostname or ""))
    return a.hostname == b.hostname


class RobotsPolicy:
    def __init__(self, user_agent: str = DEFAULT_USER_AGENT):
        self.user_agent = user_agent
        self._cache: dict[str, object] = {}

    def allowed(self, uri: str) -> bool:
        parsed = urlparse(uri)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if origin not in self._cache:
            try:
                request = Request(f"{origin}/robots.txt", headers={"User-Agent": self.user_agent})
                with urlopen(request, timeout=10) as response:
                    body = response.read(1_000_001)
                    if len(body) > 1_000_000:
                        self._cache[origin] = None
                        return True
                from urllib.robotparser import RobotFileParser
                parser = RobotFileParser()
                parser.set_url(f"{origin}/robots.txt")
                parser.parse(body.decode("utf-8", errors="replace").splitlines())
                self._cache[origin] = parser
            except OSError:
                # robots.txt being unavailable is not an explicit disallow rule.
                self._cache[origin] = None
        parser = self._cache[origin]
        return True if parser is None else parser.can_fetch(self.user_agent, uri)


def discover_links(
    start: str,
    *,
    depth: int = 2,
    max_pages: int = 1000,
    rate_limit: float = 0.5,
    scope: str = "host",
    respect_robots: bool = True,
    timeout: float = 30.0,
    max_size: int = DEFAULT_MAX_SIZE,
    allow_private: bool = False,
) -> list[str]:
    """Discover URI identities by traversing HTML pages.

    Page bodies are fetched only transiently to inspect links. Durable acquisition
    is performed separately by ``fetch_uri``/``LocalCorpus``.
    """
    if depth < 0 or max_pages < 1:
        raise ValueError("depth must be >= 0 and max_pages must be >= 1")
    queue: list[tuple[str, int]] = [(urldefrag(start)[0], 0)]
    seen: set[str] = set()
    discovered: list[str] = []
    robots = RobotsPolicy() if respect_robots else None
    while queue and len(discovered) < max_pages:
        uri, level = queue.pop(0)
        if uri in seen or level > depth:
            continue
        seen.add(uri)
        if not allowed_by_host(uri, start, scope):
            continue
        if robots and not robots.allowed(uri):
            continue
        if discovered and rate_limit > 0:
            time.sleep(rate_limit)
        try:
            data, media_type = fetch_uri(uri, timeout=timeout, max_size=max_size, allow_private=allow_private)
        except (OSError, ValueError):
            continue
        discovered.append(uri)
        if media_type == "text/html" and level < depth:
            for link in extract_links(data, uri):
                if link not in seen and allowed_by_host(link, start, scope):
                    queue.append((link, level + 1))
    return discovered


# Compatibility alias for callers that used the original name.
def crawl(start: str, *, depth: int, max_pages: int, rate_limit: float, scope: str, respect_robots: bool) -> list[str]:
    return discover_links(start, depth=depth, max_pages=max_pages, rate_limit=rate_limit, scope=scope, respect_robots=respect_robots)
