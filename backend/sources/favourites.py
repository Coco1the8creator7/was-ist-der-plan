"""Adapters for three Zurich venues: Gonzo, Frieda's Büxe via UBWG, Stereo.

Rules:
- Never invent a start time. Stereo's 22:00 is explicitly published for DJ nights.
- Gonzo/Stereo yearless dates are inferred only within the 90-day future window.
- Frieda's date is read from the official UBWG event URL and verified on-page.
- Missing dates and ambiguous titles are reported, not silently marked as successful.
"""
from __future__ import annotations

import hashlib
import re
from datetime import date, datetime
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from backend.sources.venues import Venue, MONTHS, RespectfulClient, is_future, make_event
from backend.sources.images import extract_event_image

TZ = ZoneInfo("Europe/Zurich")

FAVORITES = (
    Venue("gonzo", "Gonzo Club", "https://gonzoclub.ch/", (), "Clubs & Nachtleben", "gonzo"),
    Venue("friedas_buexe", "Friedas Büxe", "https://ubwg.ch/location/friedas-buexe/", (), "Clubs & Nachtleben", "ubwg"),
    Venue("stereo_bar", "Stereo Bar", "https://www.stereo-bar.ch/", (), "Bars & Musik", "stereo"),
)

# Gonzo uses "SAMSTAG 17. Oktober, 23H" rather than a calendar/API.
GONZO_DATE = re.compile(
    r"^(?:MONTAG|DIENSTAG|MITTWOCH|DONNERSTAG|FREITAG|SAMSTAG|SONNTAG)"
    r"\s*,?\s*(\d{1,2})\.\s*(JANUAR|FEBRUAR|MÄRZ|MAERZ|APRIL|MAI|JUNI|JULI|AUGUST|SEPTEMBER|OKTOBER|NOVEMBER|DEZEMBER)"
    r"\s*,?\s*(\d{1,2})H\b",
    re.I,
)
# Full dates published under *LIVE* do not include a verified start time.
GONZO_LIVE = re.compile(r"^(\d{1,2})\.(\d{1,2})\.(20\d{2})\s+(.+)$")

STEREO_DATE = re.compile(r"^\s*(\d{1,2})\.(\d{1,2})\.\s+(.+?)\s*$")
STEREO_OPEN = re.compile(
    r"donnerstags?,?\s*freitags?\s*und\s*samstags?\s+ab\s+(\d{1,2})[:.](\d{2})\s*Uhr",
    re.I | re.S,
)
UBWG_LINK = re.compile(r"^/event/[^?#]*-friedas-buexe-zuerich-(\d{1,2})-(\d{1,2})-(20\d{2})/?$")
UBWG_VISIBLE = re.compile(
    r"\b(\d{1,2})\.\s*(Januar|Februar|März|Maerz|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember)"
    r"\s*[·•]\s*ab\s*(\d{1,2})[:.](\d{2})",
    re.I,
)


def event_yearless(day: int, month: int, today: date, weekday: int | None = None):
    """Return only an occurrence with an unambiguous date in the future window."""
    choices = []
    for year in (today.year - 1, today.year, today.year + 1):
        try:
            d = date(year, month, day)
        except ValueError:
            continue
        if is_future(d, today) and (weekday is None or d.weekday() == weekday):
            choices.append(d)
    return choices[0] if len(choices) == 1 else None


def lines_from(doc: BeautifulSoup):
    return [re.sub(r"\s+", " ", x).strip() for x in doc.get_text("\n", strip=True).splitlines() if x.strip()]


def stable_list_id(event: dict):
    """Distinct events on one programme page may share date + source URL."""
    s = "|".join([event["source"], event["source_url"], event["date"], event["title"].casefold()])
    event["id"] = event["source"] + "-" + hashlib.sha256(s.encode()).hexdigest()[:16]
    return event


def parse_gonzo(doc: BeautifulSoup, today: date):
    v = FAVORITES[0]
    lines = lines_from(doc)
    boundaries = [(i, m) for i, line in enumerate(lines) if (m := GONZO_DATE.match(line))]
    events, errors, past, found = [], [], 0, 0
    for j, (i, match) in enumerate(boundaries):
        finish = boundaries[j+1][0] if j+1 < len(boundaries) else len(lines)
        # Stop before the separate concerts and page footer.
        block = lines[i:finish]
        end = next((k for k, t in enumerate(block) if t.lower().strip("* ") == "live"), len(block))
        block = block[:end]
        day = event_yearless(int(match[1]), MONTHS[match[2].lower()], today)
        if day is None:
            past += 1
            continue
        found += 1
        clock = f"{int(match[3]):02d}:00"
        adult = next((k for k, row in enumerate(block) if re.search(r"Mindestalter\s*20\s*\+", row, re.I)), None)
        if adult is None:
            errors.append(f"Gonzo {day}: missing minimum-age/title marker")
            continue
        title = next((t for t in block[adult+1:] if t and not t.startswith("---") and not t.lower().startswith("vvk")), "")
        if not title:
            errors.append(f"Gonzo {day}: missing event title")
            continue
        source_text = " ".join(block)
        event = make_event(v, title, day, clock, v.index, today, source_text)
        if not event:
            errors.append(f"Gonzo {day}: event validation failed")
            continue
        event["year_basis"] = "inferred_from_current_programme"
        if re.search(r"\bgratis\s+Eintritt\b", source_text, re.I):
            event["price_chf"] = 0.0
        else:
            cost = re.search(r"\b(\d{1,3})\s*\.-\s*CHF\b", source_text, re.I)
            if cost:
                event["price_chf"] = float(cost[1])
        events.append(stable_list_id(event))
    # Additional on-page LIVE listings are preserved in the QA report if the
    # homepage gives a date but no start time.
    for line in lines:
        match = GONZO_LIVE.match(line)
        if not match:
            continue
        try:
            d = date(int(match[3]), int(match[2]), int(match[1]))
        except ValueError:
            continue
        if is_future(d, today):
            found += 1
            errors.append(f"Gonzo LIVE {d} {match[4][:65]}: no verified start time")
    return found, events, errors, {"discovered_links": len(boundaries), "skipped_out_of_range": past}


def parse_stereo(doc: BeautifulSoup, today: date):
    v = FAVORITES[2]
    lines = lines_from(doc)
    all_text = " ".join(lines)
    # Opening hours at the end of the page (19:00) are NOT event start times.
    first = next((i for i, line in enumerate(lines) if "PROGRAMM" == line.upper().strip("[]# ")), -1)
    if first < 0:
        return 0, [], ["STEREO: programme section not found"], {"discovered_links": 0, "skipped_out_of_range": 0}
    end = next((j for j in range(first+1, len(lines)) if lines[j].upper().strip("[]# ") == "MENU"), len(lines))
    programme = lines[first+1:end]
    # Standard Thursday/Friday/Saturday programmes explicitly start at 22:00.
    start = STEREO_OPEN.search(all_text)
    if not start:
        return 0, [], ["STEREO: official programme start time not found"], {"discovered_links": 0, "skipped_out_of_range": 0}
    hour, minute = int(start[1]), int(start[2])
    if not (0 <= hour <= 23 and 0 <= minute < 60):
        return 0, [], ["STEREO: invalid official start time"], {}
    events, errors, past, found = [], [], 0, 0
    for line in programme:
        match = STEREO_DATE.match(line)
        if not match:
            continue
        d = event_yearless(int(match[1]), int(match[2]), today)
        if d is None:
            past += 1
            continue
        found += 1
        # If the site introduces a special Sunday event, do not invent its start.
        if d.weekday() not in {3, 4, 5}:
            errors.append(f"STEREO {d}: no confirmed start for this weekday")
            continue
        title = match[3].strip()
        event = make_event(v, title, d, f"{hour:02d}:{minute:02d}", v.index + "#programm", today)
        if not event:
            errors.append(f"STEREO {d}: invalid programme title")
            continue
        event["year_basis"] = "inferred_from_current_programme"
        event["time_basis"] = "official_programme_standard_start"
        events.append(stable_list_id(event))
    return found, events, errors, {"discovered_links": found + past, "skipped_out_of_range": past}


def parse_ubwg_detail(doc: BeautifulSoup, url: str, today: date):
    v = FAVORITES[1]
    match = UBWG_LINK.match(urlparse(url).path)
    if not match:
        return None, "Not a Friedas-Büxe event link"
    try:
        d = date(int(match[3]), int(match[2]), int(match[1]))
    except ValueError:
        return None, "Invalid date in UBWG event URL"
    if not is_future(d, today):
        return None, None
    title = next((h.get_text(" ", strip=True) for h in doc.select("h1")
                  if h.get_text(" ", strip=True) and h.get_text(" ", strip=True).casefold() != "friedas büxe"), None)
    if not title:
        return None, "Missing event heading"
    headings = [h.get_text(" ", strip=True) for h in doc.select("h2, h3")]
    detail = next((m for x in headings if (m := UBWG_VISIBLE.search(x))), None)
    if not detail:
        # Prefer content very near the event heading; never parse sidebar events.
        return None, "Event date/start time not present in event heading"
    day, month, hour, minute = int(detail[1]), MONTHS[detail[2].lower()], int(detail[3]), int(detail[4])
    if (d.day, d.month) != (day, month) or hour > 23 or minute > 59:
        return None, "URL and displayed date/time disagree"
    event = make_event(v, title, d, f"{hour:02d}:{minute:02d}", url, today)
    if event:
        event.update(extract_event_image(doc, url, v.key))
    return (event, None) if event else (None, "Event validation failed")


def crawl_favorite(v: Venue, today: date | None = None):
    today = today or datetime.now(TZ).date()
    client = RespectfulClient(v.index)
    doc = client.fetch(v.index)
    if v.mode == "gonzo":
        return parse_gonzo(doc, today)
    if v.mode == "stereo":
        return parse_stereo(doc, today)
    if v.mode != "ubwg":
        raise ValueError(f"Unknown mode {v.mode}")
    # UBWG location pages contain past event links and sidebar recommendations.
    # Restrict links to the Friedas-Büxe canonical event URL pattern.
    links = []
    skipped = 0
    for a in doc.select("a[href]"):
        url = urljoin(v.index, a["href"]).split("#", 1)[0]
        path = urlparse(url).path
        m = UBWG_LINK.match(path)
        if not m or urlparse(url).hostname != "ubwg.ch":
            continue
        try:
            d = date(int(m[3]), int(m[2]), int(m[1]))
        except ValueError:
            continue
        if not is_future(d, today):
            skipped += 1
            continue
        if url not in links:
            links.append(url)
    events, errors = [], []
    for url in links[:150]:
        try:
            detail = client.fetch(url)
            event, problem = parse_ubwg_detail(detail, url, today)
            if event:
                events.append(event)
            elif problem:
                errors.append(f"{url}: {problem}")
        except Exception as exc:
            # Do not stop other Club adapters on a single inaccessible event.
            errors.append(f"{url}: {type(exc).__name__}: {str(exc)[:160]}")
    if not links:
        errors.append("UBWG: no upcoming Friedas-Büxe event links discovered")
    return len(links), events, errors, {
        "discovered_links": len(links), "skipped_out_of_range": skipped,
    }
