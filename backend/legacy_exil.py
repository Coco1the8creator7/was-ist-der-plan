import json, re, time
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup
from backend.sources.images import extract_event_image

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "site/data/events.json"
QUALITY = ROOT / "site/data/quality.json"
HOME = "https://exil.club/"
TZ = ZoneInfo("Europe/Zurich")
UA = "was-ist-der-plan/0.1 (public events; GitHub Coco1the8creator7)"
DATE = re.compile(r"(\d{2})\.(\d{2})\.(\d{2,4})")
START = re.compile(r"\b(?:Start|Beginn)\s*:\s*(\d{1,2})[.:](\d{2})", re.I)

def crawl_exil():
    s = requests.Session()
    s.headers["User-Agent"] = UA
    from urllib.robotparser import RobotFileParser
    robots = s.get(urljoin(HOME, "robots.txt"), timeout=20)
    if robots.status_code == 200:
        rp = RobotFileParser()
        rp.parse(robots.text.splitlines())
        if not rp.can_fetch(UA, HOME):
            raise RuntimeError("robots.txt disallows EXIL")
    elif robots.status_code not in (404, 410):
        raise RuntimeError("robots.txt could not be confirmed")
    index = s.get(HOME, timeout=25)
    index.raise_for_status()
    today = datetime.now(TZ).date()
    links = {}
    for a in BeautifulSoup(index.text, "html.parser").select('a[href*="/events/"]'):
        label = a.get_text(" ", strip=True)
        match = DATE.search(label)
        if not match:
            continue
        d, m, y = map(int, match.groups())
        y = y + 2000 if y < 100 else y
        try:
            day = date(y, m, d)
        except ValueError:
            continue
        if not 0 <= (day - today).days <= 90:
            continue
        title = label[:match.start()].strip(" -|")
        url = urljoin(HOME, a.get("href", ""))
        if title and url.startswith(HOME + "events/"):
            links[url] = (title, day)
    events, errors = [], []
    for url, (title, day) in links.items():
        try:
            time.sleep(1.5)
            r = s.get(url, timeout=25)
            r.raise_for_status()
            doc = BeautifulSoup(r.text, "html.parser")
            art = extract_event_image(doc, url, "exil")
            for node in doc(["nav", "footer", "script", "style"]):
                node.decompose()
            text = doc.get_text(" ", strip=True)
            m = START.search(text)
            if not m:
                raise ValueError("start time absent")
            hour, minute = map(int, m.groups())
            if hour > 23 or minute > 59:
                raise ValueError("invalid time")
            local = datetime(day.year, day.month, day.day, hour, minute, tzinfo=TZ)
            events.append({
                "id": "exil-" + __import__("hashlib").sha256(url.encode()).hexdigest()[:16],
                "title": title, "date": day.isoformat(), "time": f"{hour:02d}:{minute:02d}",
                "start_at": local.isoformat(), "venue": "EXIL Club",
                "category": "Clubs & Nachtleben", "tags": [],
                "source": "exil", "source_url": url,
                "sources": [{"source":"exil", "url":url}],
                "status": "cancelled" if "abgesagt" in title.lower() else "scheduled",
                "price_chf": None, "description": None,
                "latitude": None, "longitude": None,
                **art,
            })
        except Exception as exc:
            errors.append(f"{url}: {str(exc)[:140]}")
    return len(links), events, errors

