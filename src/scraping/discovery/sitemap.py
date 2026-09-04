from urllib.request import urlopen
from xml.etree import ElementTree


def sitemap_urls(uri: str, *, timeout: float = 30.0) -> list[str]:
    with urlopen(uri, timeout=timeout) as response:
        root = ElementTree.fromstring(response.read())
    tag = root.tag.rsplit("}", 1)[-1]
    if tag == "sitemapindex":
        urls = []
        for node in root.iter():
            if node.tag.rsplit("}", 1)[-1] == "loc" and node.text:
                urls.extend(sitemap_urls(node.text.strip(), timeout=timeout))
        return list(dict.fromkeys(urls))
    if tag != "urlset":
        raise ValueError(f"Unsupported sitemap root: {tag}")
    return list(dict.fromkeys(
        node.text.strip()
        for node in root.iter()
        if node.tag.rsplit("}", 1)[-1] == "loc" and node.text
    ))
