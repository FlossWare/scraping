from html.parser import HTMLParser
from urllib.parse import urljoin, urldefrag, urlparse
from urllib.robotparser import RobotFileParser
from urllib.request import Request, urlopen
import time


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
    def __init__(self, user_agent: str = "FlossWare-scraping/0.1"):
        self.user_agent = user_agent
        self._cache: dict[str, RobotFileParser] = {}

    def allowed(self, uri: str) -> bool:
        parsed = urlparse(uri)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        parser = self._cache.get(origin)
        if parser is None:
            parser = RobotFileParser(f"{origin}/robots.txt")
            try:
                parser.read()
            except OSError:
                return False
            self._cache[origin] = parser
        return parser.can_fetch(self.user_agent, uri)


def fetch(uri: str, *, timeout: float = 30.0, user_agent: str = "FlossWare-scraping/0.1") -> tuple[bytes, str]:
    request = Request(uri, headers={"User-Agent": user_agent, "Accept": "*/*"})
    with urlopen(request, timeout=timeout) as response:
        data = response.read()
        media_type = response.headers.get_content_type() or "application/octet-stream"
        return data, media_type


def crawl(start: str, *, depth: int, max_pages: int, rate_limit: float, scope: str, respect_robots: bool) -> list[tuple[str, bytes, str, str]]:
    queue: list[tuple[str, int]] = [(start, 0)]
    seen: set[str] = set()
    results = []
    robots = RobotsPolicy()
    while queue and len(results) < max_pages:
        uri, level = queue.pop(0)
        if uri in seen or level > depth:
            continue
        seen.add(uri)
        if not allowed_by_host(uri, start, scope):
            continue
        if respect_robots and not robots.allowed(uri):
            continue
        if results and rate_limit > 0:
            time.sleep(rate_limit)
        try:
            data, media_type = fetch(uri)
        except (OSError, ValueError):
            continue
        results.append((uri, data, media_type, "crawl"))
        if media_type == "text/html" and level < depth:
            for link in extract_links(data, uri):
                if link not in seen:
                    queue.append((link, level + 1))
    return results
