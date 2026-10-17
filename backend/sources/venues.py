"""Conservative, source-specific parsers for public Zurich venue programmes.

No fabricated times: an event without a verified date and start time is rejected.
No login, blocked-resource bypass, or Playwright fingerprinting.
"""
from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass
from datetime import date, datetime
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

TZ = ZoneInfo("Europe/Zurich")
UA = "was-ist-der-plan/0.2 (+https://github.com/Coco1the8creator7/was-ist-der-plan)"
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
    category: str = "Clubs & Nachtleben"
    mode: str = "detail"


VENUES = (
    Venue("hive", "Hive Club", "https://www.hiveclub.ch/programm/", ("/events/",)),
    Venue("kaufleuten", "Kaufleuten", "https://kaufleuten.ch/events/", ("/event/",), "Kultur & Unterhaltung"),
    Venue("plaza", "Plaza Klub", "https://tickets.plaza-zurich.ch/de/", ("/de/events/",)),
    Venue("kauz", "Kauz Klub", "https://tickets.kauzig.ch/", ("/events/",)),
    Venue("moods", "Moods", "https://www.moods.ch/programm", ("/programm/",), "Konzerte"),
    Venue("dynamo", "Dynamo Zürich", "https://www.dynamo.ch/events-kurse", ("/veranstaltung/", "/kurs/"), "Kultur & Unterhaltung"),
    Venue("supermarket", "Supermarket", "https://www.supermarket.li/programm", (), "Clubs & Nachtleben", "supermarket"),
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
    if not m and key in {"plaza", "kauz"}:
        # Ticketshop detail pages display "Sa., 17. Oktober 2026, 18:00 Uhr".
        m = re.search(r"\b20\d{2}\s*,\s*(\d{1,2})[.:](\d{2})\s*Uhr", text, re.I)
    if not m and key == "dynamo":
        # Dynamo detail: "Fr. 09/01/2026 18:00–01:00".
        m = re.search(r"\b\d{1,2}/\d{1,2}/20\d{2}\s+(\d{1,2})[.:](\d{2})", text)
    if not m:
        return None
    hour, minute = map(int, m.groups())
    return f"{hour:02d}:{minute:02d}" if hour < 24 and minute < 60 else None


def category_for(key: str, title: str, default: str, path: str) -> str:
    name = title.lower()
    if key == "dynamo" and "/kurs/" in path:
        return "Workshops & Kurse"
    if any(x in name for x in ("yoga", "workshop", "crochet", "knit", "maschenrausch")):
        return "Workshops & Kurse"
    if any(x in name for x in ("konzert", "concert", "live musik")) or key == "moods":
        return "Konzerte"
    if any(x in name for x in ("lesung", "literatur", "podcast", "comedy", "kabarett", "theater")):
        return "Kultur & Unterhaltung"
    return default


def make_event(v: Venue, title: str, day: date, clock: str, url: str,
               today: date, text: str = "", venue_name: str | None = None) -> dict | None:
    title = re.sub(r"\s+", " ", title).strip(" -–|")
    if not title or len(title) < 2 or len(title) > 260 or not is_future(day, today):
        return None
    h, m = map(int, clock.split(":"))
    local = datetime(day.year, day.month, day.day, h, m, tzinfo=TZ)
    identity = f"{v.key}|{url}|{day.isoformat()}|{title.casefold()}"
    price = re.search(r"\bCHF\s*(\d{1,4}(?:[.,]\d{1,2})?)", text, re.I)
    return {
        "id": f"{v.key}-{hashlib.sha256(identity.encode()).hexdigest()[:16]}",
        "title": title, "date": day.isoformat(), "time": clock,
        "start_at": local.isoformat(), "venue": venue_name or v.name,
        "category": category_for(v.key, title, v.category, urlparse(url).path),
        "tags": [], "source": v.key, "source_url": url,
        "sources": [{"source": v.key, "url": url}],
        "status": "cancelled" if re.search(r"abgesagt|cancelled", title, re.I) else
                  "postponed" if re.search(r"verschoben|postponed", title, re.I) else "scheduled",
        "price_chf": float(price[1].replace(",", ".")) if price else None,
        "description": None, "latitude": None, "longitude": None,
    }


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

    def fetch(self, url: str) -> BeautifulSoup:
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname != self.root_host:
            raise ValueError(f"foreign or insecure URL: {url}")
        if self.robots and not self.robots.can_fetch(UA, url):
            raise RuntimeError("robots.txt disallows requested page")
        # Gentle access; no attempts to evade blocks or CAPTCHA.
        wait = 1.1 - (time.monotonic() - self.last_request)
        if wait > 0:
            time.sleep(wait)
        res = self.s.get(url, timeout=25)
        self.last_request = time.monotonic()
        res.raise_for_status()
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
    title = title_from_document(doc, v.key)
    if not title:
        return None
    for x in doc(["script", "style", "noscript", "footer"]):
        x.decompose()
    text = doc.get_text(" ", strip=True)
    # Date/time live in the detail itself. URL date applies only for Moods.
    day = known_date(text[:1500], url if v.key == "moods" else "")
    clock = known_time(text[:2500], v.key)
    if not day or not clock:
        return None
    venue_name = v.name
    if v.key == "kaufleuten":
        near_title = text[text.find(title):][:600] if title in text else text[:600]
        venue_match = re.search(r"Veranstaltungsort\s*:\s*(.{3,65}?)(?=\s+(?:Teilen|Samstag|Freitag|Sonntag|Montag|Dienstag|Mittwoch|Donnerstag|Tickets)\b|$)", near_title, re.I)
        if venue_match:
            venue_name = venue_match[1].strip()
    return make_event(v, title, day, clock, url, today, text[:3000], venue_name)


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


def supermarket_events(v: Venue, doc: BeautifulSoup, today: date) -> tuple[int, list[dict], list[str]]:
    # Supermarket publishes month/day/hour/title together on the programme page.
    # Each record points to the official programme (there are no detail links).
    lines = [re.sub(r"\s+", " ", s).strip() for s in doc.get_text("\n").splitlines()]
    current_month, current_year = None, None
    events, errors, listed = [], [], 0
    for line in lines:
        head = MONTH_HEADER.match(line)
        if head:
            current_month, current_year = MONTHS[head[1].lower()], int(head[2])
            continue
        m = SUPERMARKET_LINE.match(line)
        if not m or current_year is None:
            continue
        try:
            day = date(current_year, current_month, int(m[1]))
            if not is_future(day, today):
                continue
            listed += 1
            title = m[3].strip()
            event = make_event(v, title, day, f"{int(m[2]):02d}:00", v.index, today)
            if event:
                events.append(event)
            else:
                errors.append(f"Cannot validate {day} {line[:100]}")
        except ValueError as exc:
            errors.append(f"Invalid programme line {line[:100]}: {exc}")
    return listed, events, errors


def crawl_venue(v: Venue, today: date | None = None) -> tuple[int, list[dict], list[str]]:
    today = today or datetime.now(TZ).date()
    client = RespectfulClient(v.index)
    index = client.fetch(v.index)
    if v.mode == "supermarket":
        return supermarket_events(v, index, today)
    urls = discover_links(v, index, today)
    if not urls:
        return 0, [], ["No event detail links found (possibly changed markup or blocked rendering)"]
    events, errors = [], []
    for url in urls:
        try:
            doc = client.fetch(url)
            event = parse_detail(v, doc, url, today)
            if event:
                events.append(event)
            else:
                errors.append(f"Required title/date/start time missing or outside 90 days: {url}")
        except (requests.RequestException, ValueError, RuntimeError) as exc:
            errors.append(f"{url}: {type(exc).__name__}: {str(exc)[:180]}")
    return len(urls), events, errors
