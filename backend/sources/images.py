"""Extract event-specific artwork URLs without downloading any image bytes.

Only candidate links from a detail page are considered. Avoid homepage/listing
social preview fields because these often contain generic club branding.
"""
from __future__ import annotations

import json
import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

GENERIC_IMAGE = re.compile(
    r"(?:^|[/_-])(?:logo|favicon|placeholder|fallback|avatar|sprite|"
    r"icon|blank|spacer|tracking|pixel|default-share|site-logo|"
    r"og-default|default-og)(?:[/_.-]|$)",
    re.I,
)
FLYER_HINT = re.compile(r"\b(flyer|poster|eventposter|partyflyer)\b", re.I)


def empty_image_fields() -> dict:
    return {"image_url": None, "image_source": None, "image_type": None}


def _normalise_image(candidate, page_url: str):
    """Resolve and validate HTTPS image links; never fetch the image itself."""
    if isinstance(candidate, dict):
        candidate = candidate.get("url") or candidate.get("contentUrl") or candidate.get("@id")
    if isinstance(candidate, list):
        for item in candidate:
            url = _normalise_image(item, page_url)
            if url:
                return url
        return None
    if not isinstance(candidate, str):
        return None
    raw = candidate.strip()
    if not raw or len(raw) > 2200 or raw.startswith(("data:", "blob:", "javascript:")):
        return None
    try:
        url = urljoin(page_url, raw)
        parsed = urlparse(url)
    except ValueError:
        return None
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        return None
    if parsed.hostname in {"localhost", "127.0.0.1", "::1"}:
        return None
    if parsed.path.lower().endswith((".svg", ".ico", ".pdf")):
        return None
    if GENERIC_IMAGE.search(parsed.path):
        return None
    return parsed._replace(fragment="").geturl()


def _event_objects(value):
    """Yield schema.org Event nodes, including JSON-LD @graph containers."""
    if isinstance(value, list):
        for item in value:
            yield from _event_objects(item)
    if not isinstance(value, dict):
        return
    kinds = value.get("@type", [])
    if isinstance(kinds, str):
        kinds = [kinds]
    if any(str(kind).rsplit("/", 1)[-1] in {"Event", "MusicEvent", "Festival", "TheaterEvent",
                                           "ExhibitionEvent", "EducationEvent", "SportsEvent"}
           for kind in kinds):
        yield value
    for key in ("@graph", "mainEntity"):
        if key in value:
            yield from _event_objects(value[key])


def _candidates(doc: BeautifulSoup):
    # 1. Structured event-level image, never publisher/organisation logos.
    for script in doc.select('script[type="application/ld+json"]'):
        raw = script.string or script.get_text()
        if not raw or len(raw) > 250_000:
            continue
        try:
            structured = json.loads(raw)
        except (TypeError, ValueError):
            continue
        for obj in _event_objects(structured):
            if obj.get("image"):
                yield obj["image"], "json_ld_event", ""

    # 2. The individual event detail's social preview image.
    for selector in (
        'meta[property="og:image:secure_url"]',
        'meta[property="og:image"]',
        'meta[name="twitter:image"]',
        'meta[itemprop="image"]',
    ):
        for meta in doc.select(selector):
            if meta.get("content"):
                yield meta["content"], "event_preview", ""

    # 3. Explicit event photo/hero/cover in the page's primary content.
    for selector in (
        '[itemprop="image"] img',
        'img[itemprop="image"]',
        '.event-image img',
        '.event-poster img',
        '.event-flyer img',
        '.event-hero img',
        '.event-detail img',
        'article img',
        'main img',
    ):
        for img in doc.select(selector):
            attrs = " ".join(str(img.get(k, "")) for k in ("alt", "title", "class", "id"))
            if selector in ("article img", "main img") and not FLYER_HINT.search(attrs):
                # Too broad: article pages may carry ads and related events.
                continue
            for attr in ("data-src", "data-lazy-src", "src"):
                if img.get(attr):
                    yield img[attr], "detail_image", attrs
                    break


def extract_event_image(doc: BeautifulSoup, event_url: str, source: str) -> dict:
    """Return image_url/image_source/image_type or explicit nulls.

    This is cheap: it only reads HTML already downloaded by the event parser.
    event_image means plausibly event-specific, not a confirmed printed flyer.
    """
    for candidate, origin, hint in _candidates(doc):
        url = _normalise_image(candidate, event_url)
        if not url:
            continue
        kind = "event_flyer" if FLYER_HINT.search(urlparse(url).path + " " + hint) else "event_image"
        return {"image_url": url, "image_source": source, "image_type": kind}
    return empty_image_fields()



def discard_repeated_generic_images(events: list[dict]) -> tuple[int, set[str]]:
    """Suppress likely site-wide preview images shared by unrelated events.

    Legitimate recurring editions often reuse a flyer under the *same* title;
    therefore the threshold counts distinct titles, not calendar occurrences.
    """
    from collections import defaultdict

    titles = defaultdict(set)
    for event in events:
        url = event.get("image_url")
        if url:
            titles[url].add(str(event.get("title", "")).casefold())
    generic_urls = {url for url, names in titles.items() if len(names) >= 4}
    rejected = 0
    for event in events:
        if event.get("image_url") in generic_urls:
            event.update(empty_image_fields())
            rejected += 1
    return rejected, generic_urls
