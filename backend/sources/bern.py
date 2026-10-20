"""Public Bern programmes. Conservative source-specific extraction (no guessed times).

Each source is independently reported in quality.json. Pages are requested with the
existing robots-aware, host-restricted and rate-limited HTTP client.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date, datetime
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from backend.categories import CULTURE, CONCERTS, SOUND, classify_category
from backend.sources.images import extract_event_image
from backend.sources.venues import RespectfulClient, TZ, Venue, is_future, make_event

@dataclass(frozen=True)
class BernSource:
    key: str
    venue: str
    index: str
    mode: str

BERN_SOURCES = (
    BernSource("dachstock_bern", "Dachstock / Reitschule", "https://www.dachstock.ch/events", "dachstock"),
    BernSource("gaskessel_bern", "Gaskessel Bern", "https://gaskessel.ch/programm/", "gaskessel"),
    BernSource("bierhuebeli_bern", "Bierhübeli", "https://bierhuebeli.ch/", "bierhuebeli"),
    BernSource("isc_bern", "ISC Club", "https://isc-club.ch/programm/next-up/", "isc"),
    BernSource("dampfzentrale_bern", "Dampfzentrale Bern", "https://www.dampfzentrale.ch/", "dampfzentrale"),
)

DATE_SHORT = re.compile(r"\b(\d{1,2})\.(\d{1,2})\.(20\d{2}|\d{2})\b")
DACH_URL = re.compile(r"/events/(\d{2})-(\d{2})-(20\d{2})-[^/?#]+/?$")
GAS_DATE = re.compile(r"^(?:Mo|Di|Mi|Do|Fr|Sa|So)\s+(\d{1,2})\.(\d{1,2})\.(\d{2})$", re.I)
DAMPF_OCCURRENCE = re.compile(r"\b(?:MO|DI|MI|DO|FR|SA|SO)[,\s]+(\d{1,2})\.(\d{1,2})\.(\d{2})\s+(\d{1,2}):(\d{2})\b", re.I)
ICS_DATETIME = re.compile(r"\b(20\d{2})-(\d{2})-(\d{2})\s+(\d{2}):(\d{2}):\d{2}\b")

def short_date(match):
    d, m, y = (int(x) for x in match.groups()[:3])
    if y < 100:
        y += 2000
    try:
        return date(y, m, d)
    except ValueError:
        return None

def title(doc):
    h = doc.find("h1")
    return h.get_text(" ", strip=True) if h else None

def textlines(doc):
    return [re.sub(r"\s+", " ", s).strip() for s in doc.get_text("\n", strip=True).splitlines() if s.strip()]

def match_clock(pattern, text):
    m = re.search(pattern, text, re.I)
    if m:
        h, minute = (int(x) for x in m.groups())
        if 0 <= h < 24 and 0 <= minute < 60:
            return f"{h:02d}:{minute:02d}"
    return None

def canonical_links(doc, root, prefix):
    host = urlparse(root).hostname
    result = []
    for a in doc.select("a[href]"):
        u = urljoin(root, a.get("href")).split("#", 1)[0]
        p = urlparse(u)
        if p.scheme == "https" and p.hostname == host and p.path.startswith(prefix) and p.path.rstrip("/") != prefix.rstrip("/"):
            if u not in result:
                result.append(u)
    return result

def event_for(source, day, clock, name, url, today, *,
              evidence="", venue=None, format_label=None, occ_key=None, doc=None, description=None):
    if not day or not clock or not is_future(day, today):
        return None
    v = Venue(source.key, source.venue, source.index, ())
    e = make_event(v, name, day, clock, url, today, evidence[:1800], venue or source.venue)
    if not e:
        return None
    # A specific published format has priority over the venue's normal music profile.
    if format_label:
        context = f"Veranstaltungsart: {format_label}. {evidence[:400]}"
    else:
        context = evidence[:600]
    e["category"] = classify_category(e["title"], source=source.key,
                                       venue=e["venue"], url=url, details=context,
                                       start_time=clock)
    # Every occurrence (including two shows on the same day) gets its own ID.
    raw_id = "|".join((source.key, url, day.isoformat(), clock, name.casefold(), occ_key or ""))
    e["id"] = source.key + "-" + hashlib.sha256(raw_id.encode()).hexdigest()[:16]
    e["municipality"] = "Bern"
    e["city"] = "Bern"
    e["region"] = "Bern"
    e["canton"] = "BE"
    e["country"] = "CH"
    e["description"] = description if description and len(description) >= 30 else None
    e["time_unknown"] = False
    if doc:
        e.update(extract_event_image(doc, url, source.key))
    return e

def detail_description(doc, heading):
    # Only text authored for the event; never copy the navigation or listing.
    main = doc.select_one("main, article") or doc
    paragraphs = [p.get_text(" ", strip=True) for p in main.select("p")]
    relevant = [p for p in paragraphs if len(p) >= 60 and p != heading]
    return relevant[0][:1400] if relevant else None

def dachstock(source, client, index, today):
    links = [u for u in canonical_links(index, source.index, "/events/") if DACH_URL.search(urlparse(u).path)]
    events, errors, ignored = [], [], 0
    for url in links[:85]:
        m = DACH_URL.search(urlparse(url).path)
        day = date(int(m[3]), int(m[2]), int(m[1]))
        if not is_future(day, today):
            ignored += 1
            continue
        try:
            doc = client.fetch(url)
            name = title(doc)
            content = doc.get_text(" ", strip=True)
            start = match_clock(r"\bDoors\s*:?\s*(\d{1,2}):(\d{2})", content)
            if not name or not start:
                errors.append(f"{url}: heading/doors missing")
                continue
            location = re.search(r"\bOrt\s*:\s*(Reitschule|Dachstock|Rössli)\b", content, re.I)
            venue = location[1] + " / Reitschule" if location else source.venue
            # Programme type printed directly before the H1, not unrelated band bios.
            idx = content.find(name)
            lead = content[max(0, idx - 120):idx + 300] if idx >= 0 else name
            explicit = re.search(r"\b(Konzert|Party|Festival)\b", lead, re.I)
            kind = explicit[1] if explicit and explicit[1].lower() != "festival" else None
            e = event_for(source, day, start, name, url, today, evidence=lead,
                          format_label=kind, venue=venue, doc=doc,
                          description=detail_description(doc, name))
            if e:
                events.append(e)
        except Exception as exc:
            errors.append(f"{url}: {type(exc).__name__}: {str(exc)[:100]}")
    return len(links) - ignored, events, errors, {"discovered_links": len(links), "skipped_out_of_range": ignored}

def gaskessel(source, client, index, today):
    lines = textlines(index)
    bounds = [(i, short_date(m)) for i, line in enumerate(lines) if (m := GAS_DATE.match(line))]
    events, errors, ignored, found = [], [], 0, 0
    for n, (i, day) in enumerate(bounds):
        if day is None or not is_future(day, today):
            ignored += 1
            continue
        found += 1
        block = lines[i + 1:bounds[n+1][0] if n+1 < len(bounds) else len(lines)]
        if not block:
            errors.append(f"{day}: empty event block")
            continue
        name = block[0]
        head = " ".join(block[:35])
        clock = match_clock(r"\bDoors\s+(\d{1,2}):(\d{2})\b", head)
        if not clock:
            errors.append(f"{day}: missing doors, {name[:80]}")
            continue
        labels = " ".join(block[:8])
        # Strong concert evidence only if the programme says "Konzert".
        kind = "Workshop" if re.search(r"\bworkshop|kurs\b", labels, re.I) else (
               "Party" if re.search(r"\bparty|rave|dj[- ]?set\b", labels, re.I) else
               "Konzert" if re.search(r"\bkonzert\b", labels, re.I) else None)
        e = event_for(source, day, clock, name, source.index, today,
                      format_label=kind, evidence=labels, occ_key=name,
                      description=" ".join(block[8:])[:1200])
        if e:
            # The listing supplies no unique detail permalink; retain the true programme URL.
            # Free text may mention shows and other artists: no inferred concert label.
            events.append(e)
    return found, events, errors, {"discovered_links": len(bounds), "skipped_out_of_range": ignored}

def bierhuebeli(source, client, index, today):
    links = {}
    # Separate public programme sections provide verified programme types.
    for path, label in (("/konzerte/", "Konzert"), ("/partys/", "Party")):
        doc = client.fetch(urljoin(source.index, path))
        for url in canonical_links(doc, source.index, "/event/"):
            links.setdefault(url, label)
    events, errors, ignored = [], [], 0
    for url, programme_kind in list(links.items())[:100]:
        try:
            doc = client.fetch(url)
            content = doc.get_text(" ", strip=True)
            m = DATE_SHORT.search(content)
            day = short_date(m) if m else None
            if not day or not is_future(day, today):
                ignored += 1
                continue
            name = title(doc)
            start = match_clock(r"\bBeginn\s*:?\s*(\d{1,2}):(\d{2})\b", content)
            if not name or not start:
                errors.append(f"{url}: no verified title/start")
                continue
            e = event_for(source, day, start, name, url, today,
                          evidence=content[content.find(name):content.find(name)+500],
                          format_label=programme_kind, doc=doc,
                          description=detail_description(doc, name))
            if e:
                events.append(e)
        except Exception as exc:
            errors.append(f"{url}: {type(exc).__name__}: {str(exc)[:100]}")
    return len(links)-ignored, events, errors, {"discovered_links": len(links), "skipped_out_of_range": ignored}

def isc(source, client, index, today):
    links = canonical_links(index, source.index, "/programm/")
    events, errors, ignored = [], [], 0
    for url in links[:100]:
        try:
            doc = client.fetch(url)
            name = title(doc)
            content = doc.get_text(" ", strip=True)
            # ISC's Add to Calendar widget embeds the full year and clock.
            # The visible '14.11.' header alone is insufficient for dating.
            found_ics = list(ICS_DATETIME.finditer(content))
            m = found_ics[0] if found_ics else None
            if not m:
                errors.append(f"{url}: full event start absent")
                continue
            day = date(int(m[1]), int(m[2]), int(m[3]))
            if not is_future(day, today):
                ignored += 1
                continue
            clock = f"{int(m[4]):02d}:{int(m[5]):02d}"
            ix = content.rfind(name) if name else -1
            lead = content[max(0, ix - 150):ix + 200] if ix >= 0 else ""
            format_match = re.search(r"\b(Konzert|Party|Clubnight|Workshop)\s*(?:[-&,]|$)", lead, re.I)
            kind = format_match[1] if format_match else None
            e = event_for(source, day, clock, name, url, today, evidence=lead,
                          format_label="Party" if kind == "Clubnight" else kind,
                          doc=doc, description=detail_description(doc, name))
            if e:
                events.append(e)
        except Exception as exc:
            errors.append(f"{url}: {type(exc).__name__}: {str(exc)[:100]}")
    return len(links)-ignored, events, errors, {"discovered_links": len(links), "skipped_out_of_range": ignored}

def dampfzentrale(source, client, index, today):
    # One event page can represent multiple separately timed performances.
    # The official overview lists occurrence-level dates alongside each event URL.
    entries = {}
    for a in index.select('a[href]'):
        url = urljoin(source.index, a.get("href")).split("#", 1)[0]
        p = urlparse(url)
        if p.hostname != urlparse(source.index).hostname or not p.path.startswith("/event/"):
            continue
        label = a.get_text(" ", strip=True)
        m = DAMPF_OCCURRENCE.search(label)
        if not m:
            continue
        day = short_date(m)
        if not day or not is_future(day, today):
            continue
        clock = f"{int(m[4]):02d}:{int(m[5]):02d}"
        name = label[:m.start()].strip(" -–|")
        if not name:
            continue
        entries[(url, day, clock, name)] = True
    events, errors = [], []
    # Read each detail once, protecting GitHub Actions runtime.
    details = {}
    for url in list(dict.fromkeys(k[0] for k in entries))[:50]:
        try:
            details[url] = client.fetch(url)
        except Exception as exc:
            errors.append(f"{url}: {type(exc).__name__}: {str(exc)[:100]}")
    for (url, day, clock, label) in entries:
        doc = details.get(url)
        if doc is None:
            continue
        name = title(doc) or label
        # Listing's individual date and time are authoritative; detail often
        # lists *several* performances under one programme entry.
        content = doc.get_text(" ", strip=True)
        e = event_for(source, day, clock, name, url, today, evidence=content[content.find(name):][:600],
                      doc=doc, description=detail_description(doc, name))
        if e:
            events.append(e)
    return len(entries), events, errors, {"discovered_links": len(entries), "skipped_out_of_range": 0}

CRAWLERS = {"dachstock": dachstock, "gaskessel": gaskessel, "bierhuebeli": bierhuebeli,
            "isc": isc, "dampfzentrale": dampfzentrale}

def crawl_bern(source: BernSource, today: date | None = None):
    today = today or datetime.now(TZ).date()
    client = RespectfulClient(source.index)
    index = client.fetch(source.index)
    return CRAWLERS[source.mode](source, client, index, today)
