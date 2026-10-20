"""Reusable public municipal-event calendar adapter.

Initial pilot: Belp and Uttigen. The same HTML detail template can be
registered for additional towns without creating another Python parser.
No municipality is inferred from the source domain; it must be present on
the public event detail page. Unknown-time events are reported, not invented.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from backend.sources.venues import TZ, RespectfulClient, Venue, is_future, make_event
from backend.sources.images import extract_event_image

FULL_DATE = re.compile(r"(\d{1,2})\.(\d{1,2})\.(20\d{2})")
CLOCK = re.compile(r"\b(\d{1,2}):(\d{2})\s*Uhr\b", re.I)
FIELDS = {"Datum/Zeit", "Beschreibung", "Kategorie", "Lokalität", "Strasse", "Ort",
          "Adresse", "Veranstalter", "Homepage", "E-Mail", "Dokument", "Termin in Kalender eintragen"}

@dataclass(frozen=True)
class MunicipalSource:
    key: str
    index: str
    municipality: str
    province: str = "BE"
    region: str = "Bern"

MUNICIPAL_SOURCES = (
    MunicipalSource("gemeinde_belp", "https://www.belp.ch/de/veranstaltungen/", "Belp"),
    MunicipalSource("gemeinde_uttigen", "https://www.uttigen.ch/de/veranstaltungen/", "Uttigen"),
    MunicipalSource("gemeinde_ostermundigen", "https://www.ostermundigen.ch/de/veranstaltungen/", "Ostermundigen"),
)

def event_links(doc: BeautifulSoup, index: str) -> list[str]:
    """Municipal template: /de/veranstaltungen/NNNN_event-name."""
    parsed = urlparse(index)
    result = []
    for a in doc.select("a[href]"):
        u = urljoin(index, a.get("href", "")).split("#", 1)[0]
        p = urlparse(u)
        if p.scheme != "https" or p.hostname != parsed.hostname:
            continue
        if not re.match(r"^/de/veranstaltungen/\d+_", p.path, re.I):
            continue
        if u not in result:
            result.append(u)
    return result

def detail_lines(doc: BeautifulSoup) -> list[str]:
    for node in doc(["script", "style", "noscript"]):
        node.decompose()
    return [re.sub(r"\s+", " ", v).strip() for v in doc.get_text("\n", strip=True).splitlines() if v.strip()]

def read_fields(lines: list[str]) -> dict[str, str]:
    """Only extract labels from the actual detail section beneath its H1."""
    values = {}
    for i, line in enumerate(lines):
        if line not in FIELDS:
            continue
        if line in values:
            continue
        content = []
        for v in lines[i+1:]:
            if v in FIELDS or v.startswith("Fragen nicht beantwortet?") or v.startswith("Suchen"):
                break
            content.append(v)
            if len(" ".join(content)) > 2000:
                break
        values[line] = " ".join(content).strip()
    return values

def parse_municipal_detail(source: MunicipalSource, doc: BeautifulSoup, url: str, today: date):
    heading = doc.select_one("h1")
    name = heading.get_text(" ", strip=True) if heading else ""
    if not name or name.lower() in {"veranstaltungen", "details"}:
        return None, "missing event title"
    # The main public event H1 occurs after the site navigation.
    lines = detail_lines(doc)
    idx = next((i for i, line in enumerate(lines) if line == name), -1)
    if idx < 0:
        return None, "event detail section missing"
    fields = read_fields(lines[idx+1:])
    raw_date = fields.get("Datum/Zeit", "")
    md = FULL_DATE.search(raw_date)
    if not md:
        return None, "no verified full date"
    try:
        day = date(int(md[3]), int(md[2]), int(md[1]))
    except ValueError:
        return None, "invalid event date"
    if not is_future(day, today):
        return None, None
    if re.search(r"\b01:00\s*Uhr\s*-\s*00:00\s*Uhr\b", raw_date, re.I):
        return None, "time_unknown: likely all-day placeholder clock"
    mt = CLOCK.search(raw_date)
    if not mt:
        # All-day events and unspecified start times must be retained in the
        # QA report until the frontend supports time_unknown records.
        return None, "time_unknown: date known but no start clock"
    h, m = int(mt[1]), int(mt[2])
    if h > 23 or m > 59:
        return None, "invalid start clock"
    # A municipal calendar may include events taking place outside the town.
    # Prefer its explicit 'Ort' or an address containing a real locality.
    municipality = fields.get("Ort", "").strip()
    if not municipality:
        address = fields.get("Adresse", "")
        if source.municipality.casefold() in address.casefold():
            municipality = source.municipality
    if not municipality:
        return None, "no event-locality evidence on detail"
    local = municipality.casefold()
    # Do not assert that a calendar's municipality determines the event town.
    # Unverified coordinates remain null and distance remains approximate.
    where = fields.get("Lokalität") or fields.get("Adresse") or municipality
    v = Venue(source.key, where, source.index, ())
    # Only event fields, never a site-wide footer, contribute to classification.
    evidence = " ".join((fields.get("Kategorie", ""), fields.get("Beschreibung", "")[:500]))
    e = make_event(v, name, day, f"{h:02d}:{m:02d}", url, today, evidence, where)
    if not e:
        return None, "invalid event metadata"
    e.update({
        "city": municipality,
        "municipality": municipality,
        "region": source.region,
        "canton": source.province,
        "country": "CH",
        "time_unknown": False,
        "description": fields.get("Beschreibung") or None,
        "organizer": fields.get("Veranstalter") or None,
        "address": fields.get("Strasse") or None,
        "venue": where,
    })
    # Do not mistake official municipality opening hours for event location.
    e.update(extract_event_image(doc, url, source.key))
    return e, None

def crawl_municipality(source: MunicipalSource, today: date | None = None):
    today = today or datetime.now(TZ).date()
    client = RespectfulClient(source.index)
    listing = client.fetch(source.index)
    links = event_links(listing, source.index)
    events, errors, ignored = [], [], 0
    for url in links[:120]:
        try:
            doc = client.fetch(url)
            e, error = parse_municipal_detail(source, doc, url, today)
            if e is not None:
                events.append(e)
            elif error:
                errors.append(f"{url}: {error}")
            else:
                ignored += 1
        except Exception as exc:
            errors.append(f"{url}: {type(exc).__name__}: {str(exc)[:120]}")
    if not links:
        errors.append("No public municipality event detail links discovered")
    return len(links) - ignored, events, errors, {
        "discovered_links": len(links), "skipped_out_of_range": ignored,
    }
