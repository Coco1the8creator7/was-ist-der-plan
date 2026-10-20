"""Official Köniz municipality calendar: public occurrences from monthly listings.

Uses published start times and event-specific locations, without guessing times or
geocoordinates from the website domain. One index request per month; no login/API.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from backend.sources.venues import MONTHS, TZ, RespectfulClient, Venue, is_future, make_event

INDEX = "https://www.koeniz.ch/freizeit/veranstaltungen.page/436"
SOURCE = "gemeinde_koeniz"
DETAIL_PATH = re.compile(r"^/freizeit/veranstaltungen\.page/1093/event/\d+/eventdate/\d+/?$")
EVENT_DATE = re.compile(
    r"\b(\d{1,2})\.\s*(Januar|Februar|März|Maerz|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember)\s+(20\d{2})\s*,\s*ab\s+(\d{1,2}):(\d{2})\s*Uhr\b",
    re.I,
)
LOCATION_SEPARATOR = re.compile(r"\s*[|│]\s*")

def months_to_crawl(today):
    """Four pages cover the inclusive 90-day window, including year transitions."""
    for delta in range(4):
        year = today.year + (today.month - 1 + delta) // 12
        month = (today.month - 1 + delta) % 12 + 1
        yield year, month

def listing_items(doc: BeautifulSoup):
    """Yield detail links paired only with their containing item's explicit date.

    Avoid matching another event's date via navigation/body-wide text.
    """
    seen = set()
    for a in doc.select("a[href]"):
        link = urljoin(INDEX, a.get("href", "")).split("#", 1)[0]
        parsed = urlparse(link)
        if parsed.hostname != "www.koeniz.ch" or parsed.scheme != "https":
            continue
        if not DETAIL_PATH.match(parsed.path) or link in seen:
            continue
        seen.add(link)
        label = a.get_text(" ", strip=True)
        if not label:
            yield link, label, None, "missing title"
            continue
        # Every programme occurrence is linked separately inside its list item.
        item = a.find_parent("li")
        if item is None:
            yield link, label, None, "no individual listing container"
            continue
        # Reject layout/navigation containers spanning multiple event links.
        links_in_item = [
            x for x in item.select("a[href]")
            if DETAIL_PATH.match(urlparse(urljoin(INDEX, x.get("href", ""))).path)
        ]
        if len(links_in_item) != 1:
            yield link, label, None, "ambiguous listing container"
            continue
        raw = item.get_text(" ", strip=True)
        dates = list(EVENT_DATE.finditer(raw))
        if len(dates) != 1:
            yield link, label, None, "missing or ambiguous full date/start time"
            continue
        yield link, label, dates[0], None

def parse_koeniz_listing(doc: BeautifulSoup, today: date):
    events, errors, out_of_range, found = [], [], 0, 0
    for url, label, match, error in listing_items(doc):
        if error:
            errors.append(f"{url}: {error}")
            continue
        day_num, month_name, year, hour, minute = match.groups()
        try:
            start_day = date(int(year), MONTHS[month_name.lower()], int(day_num))
            hh, mm = int(hour), int(minute)
            if hh >= 24 or mm >= 60:
                raise ValueError("invalid clock")
        except (ValueError, KeyError):
            errors.append(f"{url}: invalid published event date/time")
            continue
        if not is_future(start_day, today):
            out_of_range += 1
            continue
        found += 1
        parts = LOCATION_SEPARATOR.split(label, maxsplit=1)
        title = parts[0].strip()
        location = parts[1].strip() if len(parts) == 2 else ""
        # No blanket venue assignment from the municipal website.
        if not title or not location:
            errors.append(f"{url}: explicit event venue missing")
            continue
        v = Venue(SOURCE, location, INDEX, (), mode="municipality")
        event = make_event(v, title, start_day, f"{hh:02d}:{mm:02d}", url, today,
                           text=title, venue_name=location)
        if event:
            event.update({
                "city": "Köniz", "municipality": "Köniz", "region": "Bern",
                "canton": "BE", "country": "CH", "time_unknown": False,
                "venue": location,
            })
            events.append(event)
        else:
            errors.append(f"{url}: invalid event record")
    return found, events, errors, out_of_range

def crawl_koeniz(today: date | None = None):
    today = today or datetime.now(TZ).date()
    client = RespectfulClient(INDEX)
    all_events = {}
    errors = []
    seen = 0
    ignored = 0
    for year, month in months_to_crawl(today):
        url = f"{INDEX}/ec_month/{month}/ec_year/{year}"
        try:
            doc = client.fetch(url)
        except Exception as exc:
            errors.append(f"{url}: {type(exc).__name__}: {str(exc)[:160]}")
            continue
        found, events, issues, out_of_range = parse_koeniz_listing(doc, today)
        seen += found
        ignored += out_of_range
        errors.extend(issues)
        for e in events:
            # Eventdate in the source URL differentiates distinct occurrences.
            all_events[e["source_url"]] = e
    if not all_events and not errors:
        errors.append("No validated future events in municipal calendar")
    return seen, list(all_events.values()), errors, {
        "discovered_links": seen + ignored,
        "skipped_out_of_range": ignored,
    }
