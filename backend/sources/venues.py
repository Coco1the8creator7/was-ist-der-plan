"""Conservative, source-specific parsers for public Zurich venue programmes.

No fabricated times: an event without a verified date and start time is rejected.
No login, blocked-resource bypass, or Playwright fingerprinting.
"""
from __future__ import annotations

import hashlib
import re
import time
from threading import Lock
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup
from backend.sources.images import extract_event_image, empty_image_fields
from backend.categories import SOUND, CULTURE, CONCERTS, classify_category

TZ = ZoneInfo("Europe/Zurich")
UA = "was-ist-der-plan/0.2 (+https://github.com/Coco1the8creator7/was-ist-der-plan)"
DOMAIN_LOCKS = defaultdict(Lock)
DOMAIN_LAST_REQUEST = {}
MONTHS = {
    "januar": 1, "january": 1, "jan": 1, "februar": 2, "february": 2, "feb": 2,
    "märz": 3, "maerz": 3, "march": 3, "mar": 3, "april": 4, "apr": 4,
    "mai": 5, "may": 5, "juni": 6, "june": 6, "jun": 6, "juli": 7,
    "july": 7, "jul": 7, "august": 8, "aug": 8, "september": 9, "sep": 9,
    "oktober": 10, "october": 10, "okt": 10, "oct": 10,
    "november": 11, "nov": 11, "dezember": 12, "december": 12, "dez": 12, "dec": 12,
}
LONG_DATE = re.compile(
    r"\b(\d{1,2})\.\s*(Januar|January|Jan|Februar|February|Feb|März|Maerz|March|Mar|April|Apr|Mai|May|Juni|June|Jun|Juli|July|Jul|August|Aug|September|Sep|Oktober|October|Okt|Oct|November|Nov|Dezember|December|Dez|Dec)\s+(\d{4})\b",
    re.IGNORECASE,
)
NUM_DATE = re.compile(r"\b(\d{1,2})[./](\d{1,2})[./](20\d{2})\b")
TIME_LABEL = re.compile(
    r"\b(?:Beginn|Start|Showbeginn|Konzertbeginn|Tür-?\s*/\s*Kassenöffnung|Türöffnung)\s*:?\s*(\d{1,2})[.:](\d{2})\b",
    re.IGNORECASE,
)
CLOCK = re.compile(r"\b(\d{1,2})[.:](\d{2})\s*(?:Uhr|um)?\b", re.IGNORECASE)
DATE_URL = re.compile(r"(20\d{2})-(\d{2})-(\d{2})(?:[/?#-]|$)")
SUPERMARKET_LINE = re.compile(
    r"^(?:MO|DI|MI|DO|FR|SA|SO)\s+(\d{1,2})\s+(\d{1,2})H(?:\s+|$)(.+)",
    re.IGNORECASE,
)
MONTH_HEADER = re.compile(r"^(JANUAR|FEBRUAR|MÄRZ|MAERZ|APRIL|MAI|JUNI|JULI|AUGUST|SEPTEMBER|OKTOBER|NOVEMBER|DEZEMBER)\s+(20\d{2})", re.IGNORECASE)


@dataclass(frozen=True)
class Venue:
    key: str
    name: str
    index: str
    paths: tuple[str, ...]
    category: str = SOUND
    mode: str = "detail"


VENUES = (
    Venue("hive", "Hive Club", "https://www.hiveclub.ch/programm/", ("/events/",)),
    Venue("kaufleuten", "Kaufleuten", "https://kaufleuten.ch/events/", ("/event/",), CULTURE),
    Venue("plaza", "Plaza Klub", "https://tickets.plaza-zurich.ch/de/", ("/de/events/",)),
    Venue("kauz", "Kauz Klub", "https://tickets.kauzig.ch/", ("/events/",)),
    Venue("moods", "Moods", "https://www.moods.ch/programm", ("/programm/",), CULTURE),
    Venue("dynamo", "Dynamo Zürich", "https://www.dynamo.ch/events-kurse", ("/veranstaltung/", "/kurs/"), CULTURE),
    Venue("supermarket", "Supermarket", "https://www.supermarket.li/programm", (), SOUND, "supermarket"),
)

# Not silently presented as working: access/schema must first be established.
PENDING = {
    "friedas_buexe": "Official programme not reliably readable; adapter pending",
    "helsinki": "Website access/robots must be checked; adapter pending",
    "rote_fabrik": "Official programme structure not verified; adapter pending",
    "zukunft": "Closed in March 2025: historical archive, not an active source",
    "kaschemme": "Basel venue: outside the 50 km Zurich default radius",
}


def is_future(day: date, today: date, horizon: int = 90) -> bool:
    return 0 <= (day - today).days <= horizon


def known_date(text: str, url: str = "") -> date | None:
    """Read only explicit full dates, never guess a year from a weekday."""
    m = LONG_DATE.search(text)
    if m:
        try:
            return date(int(m[3]), MONTHS[m[2].lower()], int(m[1]))
        except (ValueError, KeyError):
            pass
    m = NUM_DATE.search(text)
    if m:
        try:
            return date(int(m[3]), int(m[2]), int(m[1]))
        except ValueError:
            pass
    # Moods detail URLs contain verified YYYY-MM-DD programme occurrence keys.
    m = DATE_URL.search(url)
    if m:
        try:
            return date(*map(int, m.groups()))
        except ValueError:
            pass
    return None


def known_time(text: str, key: str) -> str | None:
    m = TIME_LABEL.search(text)
    if not m and key == "hive":
        # Official Hive details: "Start: 17. October 2026 um 22:00"
        m = re.search(
            r"\b(?:Start\s*:\s*)?\d{1,2}\.\s+[A-Za-zäöüÄÖÜ]+\s+20\d{2}\s+um\s+(\d{1,2})[.:](\d{2})\b",
            text, re.I,
        )
    if not m and key in {"plaza", "kauz"}:
        # Ticketshop detail pages display "Sa., 17. Oktober 2026, 18:00 Uhr".
        m = re.search(r"\b20\d{2}\s*,\s*(\d{1,2})[.:](\d{2})\s*Uhr", text, re.I)
    if not m and key == "dynamo":
        # Official detail: "Sa. 17/10/2026 20:00–04:00"
        m = re.search(r"\b\d{1,2}/\d{1,2}/20\d{2}\s+(\d{1,2})[.:](\d{2})", text)
        if not m:
            # Date and time may be separate HTML elements.
            m = re.search(r"\b\d{1,2}/\d{1,2}/20\d{2}\s+(\d{1,2})[.:](\d{2})\s*[–-]\s*\d", text)
    if not m:
        return None
    hour, minute = map(int, m.groups())
    return f"{hour:02d}:{minute:02d}" if hour < 24 and minute < 60 else None


def category_for(key: str, title: str, default: str, path: str,
                 details: str = "", venue: str = "", start_time: str = "") -> str:
    """Compatibility wrapper; the actual policy lives in backend.categories."""
    return classify_category(title, source=key, venue=venue, url=path,
                             details=details, start_time=start_time)


def make_event(v: Venue, title: str, day: date, clock: str, url: str,
               today: date, text: str = "", venue_name: str | None = None) -> dict | None:
    title = re.sub(r"\s+", " ", title).strip(" -–|")
    if not title or len(title) < 2 or len(title) > 260 or not is_future(day, today):
        return None
    local = datetime.combine(day, datetime.strptime(clock, "%H:%M").time(), TZ) if clock else None
    identity = f"{v.key}|{url}|{day.isoformat()}" + (f"|{title.casefold()}" if v.key == "supermarket" else "")
    price = re.search(r"\bCHF\s*(\d{1,4}(?:[.,]\d{1,2})?)", text, re.I)
    event = {
        "id": f"{v.key}-{hashlib.sha256(identity.encode()).hexdigest()[:16]}",
        "title": title, "date": day.isoformat(), "time": clock,
        "start_at": local.isoformat() if local else None, "time_unknown": not bool(clock),
        "venue": venue_name or v.name,
        "category": category_for(v.key, title, v.category, url, text, venue_name or v.name, clock),
        "tags": [], "source": v.key, "source_url": url,
        "sources": [{"source": v.key, "url": url}],
        "status": "cancelled" if re.search(r"abgesagt|cancelled", title, re.I) else
                  "postponed" if re.search(r"verschoben|postponed", title, re.I) else "scheduled",
        "price_chf": float(price[1].replace(",", ".")) if price else None,
        "description": None, "latitude": None, "longitude": None,
    }
    event.update(empty_image_fields())
    return event


class RespectfulClient:
    def __init__(self, index_url: str):
        self.root_host = urlparse(index_url).hostname
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": UA, "Accept": "text/html,application/xhtml+xml"})
        origin = f"{urlparse(index_url).scheme}://{self.root_host}/"
        robots_url = urljoin(origin, "robots.txt")
        res = self.s.get(robots_url, timeout=20)
        if res.status_code == 200:
            self.robots = RobotFileParser()
            self.robots.parse(res.text.splitlines())
        elif res.status_code in (404, 410):
            self.robots = None
        else:
            raise RuntimeError(f"robots.txt unavailable ({res.status_code}); crawl skipped")
        self.last_request = 0.0

    def request(self, url: str, method: str = "GET", redirects: int = 0):
        if redirects > 5:
            raise RuntimeError("Too many redirects")
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname != self.root_host:
            raise ValueError(f"foreign or insecure URL: {url}")
        if self.robots and not self.robots.can_fetch(UA, url):
            raise RuntimeError("robots.txt disallows requested page")
        # Gentle access; no attempts to evade blocks or CAPTCHA.
        delay = max(1.1, self.robots.crawl_delay(UA) or self.robots.crawl_delay("*") or 0) if self.robots else 1.1
        with DOMAIN_LOCKS[self.root_host]:
            wait = delay - (time.monotonic() - DOMAIN_LAST_REQUEST.get(self.root_host, 0))
            if wait > 0:
                time.sleep(wait)
            try:
                res = self.s.request(method, url, timeout=25, allow_redirects=False,
                                     headers={"X-Requested-With": "XMLHttpRequest"} if method == "POST" else {})
            finally:
                self.last_request = DOMAIN_LAST_REQUEST[self.root_host] = time.monotonic()
        # Validate every redirect before following it; never leave this host or
        # inadvertently follow a redirect into a robots-disallowed resource.
        if res.is_redirect:
            target = urljoin(url, res.headers["Location"])
            if target == url:
                raise RuntimeError("Redirect loop")
            return self.request(target, method, redirects + 1)
        res.raise_for_status()
        return res

    def fetch(self, url: str, method: str = "GET") -> BeautifulSoup:
        res = self.request(url, method)
        return BeautifulSoup(res.text, "html.parser")


def title_from_document(doc: BeautifulSoup, key: str) -> str | None:
    heading = doc.select_one("h1")
    if heading and heading.get_text(" ", strip=True):
        return heading.get_text(" ", strip=True)
    meta = doc.select_one('meta[property="og:title"]')
    if meta and meta.get("content"):
        return str(meta["content"]).split(" | ")[0].strip()
    if key == "moods":
        heads = [x.get_text(" ", strip=True) for x in doc.select("main h2, main h3, h2, h3")]
        return next((x for x in heads if x and x.lower() not in {"programm", "carte blanche"}), None)
    return None


def parse_detail(v: Venue, doc: BeautifulSoup, url: str, today: date) -> dict | None:
    art = extract_event_image(doc, url, v.key)
    title = title_from_document(doc, v.key)
    if not title:
        return None
    for x in doc(["script", "style", "noscript", "footer"]):
        x.decompose()
    text = doc.get_text(" ", strip=True)
    # Restrict the date search to the event heading and following content.
    # Site-wide navigation, opening hours or recommendations may contain other dates.
    position = text.find(title)
    detail_text = text[position:position + 4500] if position >= 0 else text[:4500]
    day = known_date(detail_text, url if v.key == "moods" else "")
    clock = known_time(detail_text, v.key)
    if not day or not clock:
        return None
    venue_name = v.name
    if v.key == "kaufleuten":
        near_title = text[text.find(title):][:600] if title in text else text[:600]
        venue_match = re.search(r"Veranstaltungsort\s*:\s*(.{3,65}?)(?=\s+(?:Teilen|Samstag|Freitag|Sonntag|Montag|Dienstag|Mittwoch|Donnerstag|Tickets)\b|$)", near_title, re.I)
        if venue_match:
            venue_name = venue_match[1].strip()
    event = make_event(v, title, day, clock, url, today, detail_text[:3000], venue_name)
    if event:
        event.update(art)
    return event


def discover_links(v: Venue, index: BeautifulSoup, today: date) -> list[str]:
    found = []
    for a in index.select("a[href]"):
        url = urljoin(v.index, a["href"]).split("#")[0]
        parsed = urlparse(url)
        path = parsed.path
        if parsed.hostname != urlparse(v.index).hostname:
            continue
        if not any(path.startswith(prefix) and path.rstrip("/") != prefix.rstrip("/")
                   for prefix in v.paths):
            continue
        if re.search(r"/page/\d+/?$", path):
            continue
        if v.key == "moods":
            m = DATE_URL.search(path)
            if not m:
                continue
            try:
                if not is_future(date(*map(int, m.groups())), today):
                    continue
            except ValueError:
                continue
        if url not in found:
            found.append(url)
    return found[:250]



# Tokenise the flattened calendar, because HTML nodes often split the month,
# weekday, date, time and artist line into separate elements.
PROGRAM_TOKENS = re.compile(
    r"(?P<month>JANUAR|FEBRUAR|MÄRZ|MAERZ|APRIL|MAI|JUNI|JULI|AUGUST|SEPTEMBER|OKTOBER|NOVEMBER|DEZEMBER)\s+(?P<year>20\d{2})"
    r"|(?<!\w)(?P<weekday>MO|DI|MI|DO|FR|SA|SO)\s+(?P<day>\d{1,2})\s+(?P<hour>\d{1,2})H\b",
    re.IGNORECASE,
)
DYNAMO_OCCURRENCE = re.compile(
    r"\b(\d{1,2})/(\d{1,2})/(20\d{2})\s+(\d{1,2})[.:](\d{2})(?!\d)"
)


def supermarket_events(v: Venue, doc: BeautifulSoup, today: date):
    text = re.sub(r"\s+", " ", doc.get_text(" ", strip=True))
    tokens = list(PROGRAM_TOKENS.finditer(text))
    current_month, current_year = None, None
    events, errors, skipped, candidates = [], [], 0, 0
    for i, token in enumerate(tokens):
        if token.group("month"):
            current_month = MONTHS[token.group("month").lower()]
            current_year = int(token.group("year"))
            continue
        if not token.group("weekday") or current_month is None:
            continue
        candidates += 1
        try:
            day = date(current_year, current_month, int(token.group("day")))
            if not is_future(day, today):
                skipped += 1
                continue
            hour = int(token.group("hour"))
            if hour > 23:
                raise ValueError("hour outside valid range")
            next_pos = tokens[i+1].start() if i+1 < len(tokens) else len(text)
            raw_title = text[token.end():next_pos].strip(" ›-–")
            # The colon normally separates the event name from its DJ lineup.
            title = raw_title.split(":", 1)[0].strip()
            event = make_event(v, title, day, f"{hour:02d}:00", v.index, today)
            if event:
                events.append(event)
            else:
                errors.append(f"Cannot validate {day}: {raw_title[:100]}")
        except ValueError as exc:
            errors.append(f"Invalid programme occurrence: {exc}")
    return len(events)+len(errors), events, errors, {
        "discovered_links": candidates,
        "skipped_out_of_range": skipped,
    }


def dynamo_events(v: Venue, doc: BeautifulSoup, url: str, today: date):
    art = extract_event_image(doc, url, v.key)
    title = title_from_document(doc, v.key)
    if not title:
        return [], 0, "Missing event title"
    for node in doc(["script", "style", "noscript", "footer"]):
        node.decompose()
    text = doc.get_text(" ", strip=True)
    pos = text.find(title)
    body = text[pos:pos+3500] if pos >= 0 else text[:3500]
    seen, results, skipped = set(), [], 0
    for match in DYNAMO_OCCURRENCE.finditer(body):
        try:
            day = date(int(match[3]), int(match[2]), int(match[1]))
            hour, minute = int(match[4]), int(match[5])
            if hour > 23 or minute > 59:
                continue
            if not is_future(day, today):
                skipped += 1
                continue
            when = (day, hour, minute)
            if when in seen:
                continue
            seen.add(when)
            event = make_event(v, title, day, f"{hour:02d}:{minute:02d}", url, today, body)
            if event:
                event.update(art)
                results.append(event)
        except ValueError:
            continue
    if results:
        return results, skipped, None
    if skipped and any(DYNAMO_OCCURRENCE.finditer(body)):
        return [], skipped, None
    # Some stand-alone events use a labelled clock and full textual date.
    day = known_date(body)
    if day and not is_future(day, today):
        return [], 1, None
    event = parse_detail(v, doc, url, today)
    if event:
        event.update(art)
        return [event], skipped, None
    return [], skipped, "No verifiable future occurrence with start time"


def crawl_venue(v: Venue, today: date | None = None):
    today = today or datetime.now(TZ).date()
    client = RespectfulClient(v.index)
    index = client.fetch(v.index)
    if v.mode == "supermarket":
        return supermarket_events(v, index, today)
    urls = discover_links(v, index, today)
    if not urls:
        return 0, [], ["No event detail links found (possible markup change or rendering required)"], {
            "discovered_links": 0, "skipped_out_of_range": 0,
        }
    events, errors, skipped = [], [], 0
    for url in urls:
        try:
            doc = client.fetch(url)
            if v.key == "dynamo":
                occurrences, ignored, problem = dynamo_events(v, doc, url, today)
                skipped += ignored
                events.extend(occurrences)
                if problem:
                    errors.append(f"{url}: {problem}")
                continue
            title = title_from_document(doc, v.key)
            if not title:
                errors.append(f"{url}: missing title")
                continue
            text = doc.get_text(" ", strip=True)
            pos = text.find(title)
            detail = text[pos:pos+4500] if pos >= 0 else text[:4500]
            day = known_date(detail, url if v.key == "moods" else "")
            if day and not is_future(day, today):
                skipped += 1
                continue
            event = parse_detail(v, doc, url, today)
            if event:
                events.append(event)
            else:
                errors.append(f"{url}: date/time absent or unreadable")
        except (requests.RequestException, ValueError, RuntimeError) as exc:
            errors.append(f"{url}: {type(exc).__name__}: {str(exc)[:180]}")
    # "listed" counts only in-window event occurrences and failed parsing attempts,
    # not historical or beyond-horizon detail pages.
    return len(events) + len(errors), events, errors, {
        "discovered_links": len(urls), "skipped_out_of_range": skipped,
    }
