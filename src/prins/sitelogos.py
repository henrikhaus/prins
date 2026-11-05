"""Finds a company's own logo on its website, for the label agent.

A search gives page addresses, not images. This reads one page (through the design engine's
public-address guard) and lists the image addresses on it that could be the site's logo, best first.
A homepage is full of other pictures, often other companies' logos, so the site's own icons
come before anything that merely has "logo" in its name.
"""

from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from .design import assets

MAX_CANDIDATES = 10
_LOGO_WORDS = re.compile(r"logo|brand|wordmark", re.IGNORECASE)
_IMAGE_EXT = re.compile(r"\.(svg|png|jpe?g|webp|gif|ico)(\?|#|$)", re.IGNORECASE)


class _Collector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.found: list[tuple[int, str, str]] = []  # (rank, kind, href); lower ranks come first

    def _add(self, rank: int, kind: str, href: str | None) -> None:
        if href and not href.startswith("data:"):
            self.found.append((rank, kind, href.strip()))

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "link":
            rel = a.get("rel", "").lower().split()
            href = a.get("href")
            if "mask-icon" in rel or ("icon" in rel and href and href.lower().split("?")[0].endswith(".svg")):
                self._add(1, "svg icon", href)
            elif "apple-touch-icon" in rel or "apple-touch-icon-precomposed" in rel:
                self._add(2, "app icon", href)
            elif "icon" in rel:
                self._add(4, "favicon", href)
        elif tag == "meta":
            name = (a.get("property") or a.get("name") or "").lower()
            if name in ("og:image", "twitter:image", "og:image:url"):
                self._add(5, "social share image (often a banner, not the logo)", a.get("content"))
        elif tag in ("img", "source"):
            src = a.get("src") or a.get("srcset", "").split(",")[0].split(" ")[0] or a.get("data-src")
            marks = " ".join((src or "", a.get("alt", ""), a.get("class", ""), a.get("id", "")))
            if src and _LOGO_WORDS.search(marks):
                self._add(3, "image named logo (may be another company's)", src)


def _json_ld_logos(html: str) -> list[str]:
    found: list[str] = []
    for block in re.findall(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', html, re.IGNORECASE | re.DOTALL):
        try:
            data = json.loads(block)
        except ValueError:
            continue
        stack = [data]
        while stack:
            item = stack.pop()
            if isinstance(item, list):
                stack.extend(item)
            elif isinstance(item, dict):
                logo = item.get("logo")
                if isinstance(logo, str):
                    found.append(logo)
                elif isinstance(logo, dict) and isinstance(logo.get("url"), str):
                    found.append(logo["url"])
                stack.extend(v for v in item.values() if isinstance(v, (dict, list)))
    return found


def find_logo_images(url: str) -> list[dict[str, str]]:
    """Candidate logo images on `url`, best first, as absolute web addresses. Raises AssetError."""
    html = assets.fetch_public_page(url).decode("utf-8", "replace")
    collector = _Collector()
    collector.feed(html)
    ranked = [(0, "logo from the site's own data", href) for href in _json_ld_logos(html)] + sorted(collector.found, key=lambda item: item[0])
    seen: set[str] = set()
    out: list[dict[str, str]] = []
    for _rank, kind, href in ranked:
        absolute = urljoin(url, href)
        if urlsplit(absolute).scheme not in ("http", "https") or absolute in seen:
            continue
        if not (_IMAGE_EXT.search(absolute) or kind.startswith(("svg", "app", "logo from"))):
            continue
        seen.add(absolute)
        out.append({"url": absolute, "kind": kind})
        if len(out) >= MAX_CANDIDATES:
            break
    return out
