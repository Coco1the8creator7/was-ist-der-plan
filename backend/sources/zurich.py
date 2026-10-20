"""Public Zurich APIs and structured calendars, with bounded pagination.

No credentials or browser execution. Every request uses the robots-aware client.
Pagination caps are reported as partial coverage, never asserted as full recall.
"""
from datetime import date, datetime, timedelta
import json
import hashlib
import re
from urllib.parse import urljoin, urlencode, parse_qs, urlsplit
from bs4 import BeautifulSoup
from backend.sources.venues import RespectfulClient, Venue, TZ, make_event, is_future, known_date
from backend.sources.images import extract_event_image, is_valid_image_url
from backend.categories import classify_category

SOURCES = ("stadt_zuerich", "rote_fabrik", "ubwg", "kulturzueri", "petzi", "gemeinde_thalwil", "gemeinde_regensdorf", "gemeinde_uster", "gemeinde_kloten")
# Explicitly verified programme localities; unknown places remain excluded from
# national feeds until independently verified. No guessed GPS coordinates.
LOCALITIES = {"Zürich", "Winterthur", "Baden", "Wettingen", "Uster", "Wetzikon", "Dübendorf", "Wallisellen",
              "Bülach", "Kloten", "Regensdorf", "Schlieren", "Dietikon", "Horgen", "Thalwil", "Wädenswil",
              "Meilen", "Rapperswil", "Rapperswil-Jona", "Affoltern am Albis", "Zug", "Gockhausen Zürich",
              "Gattikon", "Adliswil", "Glattbrugg", "Opfikon", "Zollikon", "Stäfa", "Küsnacht", "Rüti ZH"}


def text(value):
    value = str(value or "")
    return BeautifulSoup(value, "html.parser").get_text(" ", strip=True) if '<' in value else value.strip()


def image(event, url):
    if is_valid_image_url(url):
        event.update(image_url=url, image_type="event", image_source=event["source"])


def build(key, title, start, clock, url, venue, today, description="", city=None, **fields):
    day = date.fromisoformat(start[:10])
    if not is_future(day, today):
        return None
    e = make_event(Venue(key, venue, url, ()), title, day, clock, url, today, description)
    if e:
        e.update(description=description or None, region="Zürich", city=city, municipality=city,
                 country="CH", original_title=title, **fields)
        if e.get("source_event_id"):
            identity = f"{e['source_event_id']}|{day}|{clock or 'unknown'}"
            e["id"] = key + '-' + hashlib.sha256(identity.encode()).hexdigest()[:16]
        # Keep event evidence so legacy migrations use the same classifier.
        e["classification_context"] = description[:1600]
        for tag, pattern in {"Markt": r"\b(?:markt|flohmarkt|bazaar)\b", "Dorffest": r"\b(?:dorffest|chilbi|quartierfest)\b",
                             "Sport": r"\b(?:sport|turnier|lauf|schwimmen)\b", "Food": r"\b(?:food|kulinarik|degustation)\b"}.items():
            if re.search(pattern, title+" "+description[:500], re.I) and tag not in e["tags"]:
                e["tags"].append(tag)
    return e


def result(events, errors, discovered, skipped=0, **meta):
    return len(events) + len(errors), events, errors, dict(discovered_links=discovered, skipped_out_of_range=skipped, **meta)


def parse_city(row, today):
    start = row["eventDateStart"]
    # 00:00 is the agenda's all-day/unknown placeholder, not a verified clock.
    clock = start[11:16] if len(start) >= 16 and start[11:16] != "00:00" else None
    location = re.sub(r"^\(weitere Daten vorhanden\)\s*", "", row.get("eventLocation", "")).strip()
    city = next((c for c in sorted(LOCALITIES, key=len, reverse=True) if re.search(r"\b" + re.escape(c) + r"\b", location)), None)
    # A city-owned agenda can include excursions outside the region; require
    # an explicit local place rather than assigning Zürich by source domain.
    if not city:
        return None
    url = urljoin("https://www.stadt-zuerich.ch", row["href"])
    e = build("stadt_zuerich", row["heading"], start, clock, url, location.split(",")[0], today,
              row.get("description", ""), city, address=location,
              source_event_id=row["href"], date_precision="datetime" if clock else "date")
    if e and row.get("eventDateEnd"):
        e["end_at"] = datetime.fromisoformat(row["eventDateEnd"]).replace(tzinfo=TZ).isoformat()
    return e


def crawl_city(today):
    c = RespectfulClient("https://www.stadt-zuerich.ch/agenda")
    events, errors, seen, skipped, total, complete = [], [], set(), 0, 0, False
    for page in range(30):
        params = dict(lang="de", compResource="/content/web/de/aktuell/veranstaltungen/jcr:content/mainparsys/search",
                      limit=100, offset=page*100, q_date=today.strftime("%d.%m.%Y"),
                      q_dateend=(today+timedelta(days=90)).strftime("%d.%m.%Y"))
        try:
            data = c.request("https://www.stadt-zuerich.ch/stzh/search?" + urlencode(params)).json()
        except Exception as exc:
            errors.append(f"City page {page+1}: {type(exc).__name__}: {str(exc)[:100]}")
            break
        if data.get("error"):
            raise ValueError("City API returned error")
        rows = data.get("results", [])
        total = data.get("meta", {}).get("total", 0)
        for row in rows:
            identity = (row.get("href"), row.get("eventDateStart"))
            if identity in seen:
                continue
            seen.add(identity)
            try:
                e = parse_city(row, today)
                if e: events.append(e)
                else: skipped += 1
            except (KeyError, ValueError, TypeError) as exc:
                errors.append(f"{identity}: {exc}")
        if (page+1)*100 >= total:
            complete = True
            break
        if not rows:
            errors.append("City pagination ended before upstream total")
            break
    else:
        errors.append("Pagination cap: city results truncated")
    return result(events, errors, len(seen), skipped, upstream_total=total, pagination_complete=complete)


def parse_rote(row, today):
    obj = row["rf_event"]
    if row.get("deleted_at") or obj.get("deleted_at") or not obj.get("publish"):
        return None
    # API stores local-midnight dates as UTC on the previous day (DST matters).
    day = datetime.fromisoformat(row["date"].replace("Z", "+00:00")).astimezone(TZ).date()
    clock = row.get("from", "")[:5] if not row.get("allday") else None
    cats = [v["name"] for v in obj.get("categories", [])]
    description = text(obj.get("description"))
    url = f"https://rotefabrik.ch/programm#/events/{row['id']}"
    e = build("rote_fabrik", obj["title"], day.isoformat(), clock, url, "Rote Fabrik " + obj.get("location", {}).get("name", ""), today,
              description, "Zürich", source_event_id=str(row["id"]), doors_time=(row.get("door") or "")[:5] or None,
              ticket_url=obj.get("ticket_link") or None, tags=cats, venue_id="rotefabrik:"+str(obj.get("location_id")))
    if e:
        if obj.get("state") == 4:
            e["status"] = "cancelled"
        context = "Format: " + ("Konzert" if "Konzert" in cats else cats[0] if cats else "")
        e["category"] = classify_category(e["title"], venue=e["venue"], details=context+" "+description)
        # Numeric price=0 is a CMS default even on paid events. Preserve the
        # published price information and do not mislabel these as free.
        e["price_text"] = obj.get("price_information") or None
        if row.get("to") and clock:
            end = datetime.combine(day, datetime.strptime(row["to"][:5], "%H:%M").time(), TZ)
            if row["to"][:5] < clock: end += timedelta(days=1)
            e["end_at"] = end.isoformat()
        files = json.loads(obj.get("files") or "{}")
        for f in files.get("main-image", {}).values():
            image(e, "https://kalender.rotefabrik.ch/thumbs/1200x0/" + f["path"].removeprefix("public/"))
            break
    return e


def crawl_rote(today):
    c = RespectfulClient("https://kalender.rotefabrik.ch/")
    url = "https://kalender.rotefabrik.ch/api/events?" + urlencode(dict(from_=today.isoformat())).replace("from_=", "from=")
    url += "&to="+(today+timedelta(days=90)).isoformat()+"&limit=500"
    data = c.request(url).json()
    rows = list(data.values()) if isinstance(data, dict) else data
    events, errors, skipped = [], [], 0
    for row in rows:
        try:
            e = parse_rote(row, today)
            if e: events.append(e)
            else: skipped += 1
        except (KeyError, ValueError, TypeError) as exc: errors.append(f"{row.get('id')}: {exc}")
    if len(rows) >= 500: errors.append("Pagination cap: Rote Fabrik API limit reached")
    return result(events, errors, len(rows), skipped, pagination_complete=len(rows) < 500)


def parse_ubwg(row, today):
    v = row.get("venue") or {}
    city = v.get("city")
    if city not in LOCALITIES:
        return None
    start = row["start_date"]
    description = text(row.get("description"))
    e = build("ubwg", text(row["title"]), start, None if row.get("all_day") else start[11:16], row["url"],
              text(v.get("venue")), today, description, city, source_event_id=str(row["id"]),
              address=v.get("address"), original_event_url=row.get("website") or None)
    if e:
        e["category"] = classify_category(e["title"], source="ubwg", venue=e["venue"], details=description)
        image(e, (row.get("image") or {}).get("url"))
        if v.get("geo_lat") and v.get("geo_lng"):
            e.update(latitude=float(v["geo_lat"]), longitude=float(v["geo_lng"]), coordinate_source="UBWG venue metadata")
        # Currency_code in the upstream API can be incorrectly set to USD.
        # Retain the price string; don't assert a numeric CHF price.
        e["price_text"] = row.get("cost") or None
    return e


def crawl_ubwg(today):
    c = RespectfulClient("https://ubwg.ch/events/")
    url = "https://ubwg.ch/wp-json/tribe/events/v1/events?"+urlencode(dict(start_date=today.isoformat(), end_date=(today+timedelta(days=90)).isoformat(), per_page=50))
    events, errors, seen, skipped = [], [], set(), 0
    for page in range(12):
        try:
            data = c.request(url).json()
        except Exception as exc:
            errors.append(f"UBWG page {page+1}: {type(exc).__name__}: {str(exc)[:100]}")
            break
        for row in data.get("events", []):
            if row["id"] in seen: continue
            seen.add(row["id"])
            try:
                e = parse_ubwg(row, today)
                if e: events.append(e)
                else: skipped += 1
            except (ValueError, KeyError, TypeError) as exc: errors.append(f"{row['id']}: {exc}")
        url = data.get("next_rest_url")
        if not url: break
    else: errors.append("Pagination cap: UBWG results truncated")
    return result(events, errors, len(seen), skipped, pagination_complete=not bool(url))


def jsonld(doc):
    def walk(obj):
        if isinstance(obj, list):
            for v in obj: yield from walk(v)
        elif isinstance(obj, dict):
            types = obj.get("@type", [])
            if isinstance(types, str): types = [types]
            if any(t.endswith("Event") for t in types): yield obj
            for field in ("@graph", "mainEntity", "itemListElement", "item"):
                if field in obj: yield from walk(obj[field])
    for node in doc.select('script[type="application/ld+json"]'):
        try: yield from walk(json.loads(node.string or node.text))
        except (ValueError, TypeError): continue


def parse_kultur(doc, url, today):
    events = []
    for obj in jsonld(doc):
        location = obj.get("location") or {}
        address = location.get("address") or {}
        if not isinstance(address, dict): continue
        city = address.get("addressLocality")
        if city not in LOCALITIES: continue
        schedule = obj.get("eventSchedule") or [{"startDate":obj.get("startDate")}]
        if isinstance(schedule, dict): schedule = [schedule]
        for occurrence in schedule:
            start = occurrence.get("startDate") or obj.get("startDate")
            if not start: continue
            clock = occurrence.get("startTime") or (start[11:16] if "T" in start else None)
            offers = obj.get("offers") or {}
            if isinstance(offers, list): offers = offers[0] if offers else {}
            e = build("kulturzueri", obj["name"], start, clock, url, location.get("name", ""), today,
                      text(obj.get("description")), city, address=address.get("streetAddress"),
                      organizer=(obj.get("organizer") or {}).get("name"), ticket_url=offers.get("url"),
                      original_event_url=obj.get("url"), source_event_id=url+"|"+str(clock))
            if e:
                image(e, obj.get("image") if isinstance(obj.get("image"), str) else None)
                if occurrence.get("endDate") and occurrence.get("endTime"):
                    e["end_at"] = datetime.fromisoformat(occurrence["endDate"][:10]+"T"+occurrence["endTime"]).replace(tzinfo=TZ).isoformat()
                if str(obj.get("eventStatus", "")).endswith("EventCancelled"):
                    e["status"] = "cancelled"
                if offers.get("priceCurrency") == "CHF" and offers.get("price") is not None:
                    e["price_chf"] = float(offers["price"])
                intro = doc.select_one('.cp-activity-detail-intro .intro-text')
                if intro:
                    e["description"] = intro.get_text(" ", strip=True)
                    e["classification_context"] = e["description"][:1600]
                    e["category"] = classify_category(e["title"], venue=e["venue"], details=e["classification_context"])
                events.append(e)
    return events


def crawl_kultur(today):
    root = "https://www.kulturzueri.ch"
    c = RespectfulClient(root+"/veranstaltungen/")
    links, errors, events, pages, complete = [], [], [], set(), False
    url = root+"/veranstaltungen/"
    # Public frontend makes this exact POST to obtain its HTML list.
    for _ in range(6):
        if url in pages: break
        pages.add(url)
        try:
            doc = c.fetch(url, "POST")
        except Exception as exc:
            errors.append(f"Kulturzüri listing: {type(exc).__name__}: {str(exc)[:100]}")
            break
        for a in doc.select('a[href^="/db/veranstaltungen/"]'):
            u = urljoin(root, a["href"])
            if u not in links: links.append(u)
        more = doc.select_one('.MarkupPagerNavNext a')
        if not more:
            complete = True
            break
        url = urljoin(root, more["href"])
    if not complete: errors.append("Pagination cap: Kulturzüri pilot limited to 6 listing pages")
    for url in links:
        try:
            parsed = parse_kultur(c.fetch(url), url, today)
            if parsed: events.extend(parsed)
            # Pages may legitimately contain only out-of-range/out-of-region dates.
            else: errors.append(f"{url}: no eligible structured occurrence")
        except Exception as exc: errors.append(f"{url}: {type(exc).__name__}: {str(exc)[:100]}")
    return result(events, errors, len(links), pagination_complete=complete, listing_pages=len(pages))


def parse_petzi(doc, url, today):
    detail = doc.select_one('.events__details')
    if not detail: return None
    heading = detail.select_one('h1')
    loc = detail.select_one('h4')
    location = next((h.get_text(' ', strip=True) for h in detail.select('h4') if ' – ' in h.text), '')
    if ' – ' not in location: return None
    venue, city = location.rsplit(' – ', 1)
    if city not in LOCALITIES: return None
    body = detail.get_text(' ', strip=True)
    start = re.search(r'Die Veranstaltung beginnt um:\s*(\d{2}:\d{2})', body)
    # Event biographies may contain older full dates. Read the date heading,
    # then the published calendar link for multi-day headings, never the bio.
    date_heading = detail.select_one('h3')
    day = known_date(date_heading.get_text(' ', strip=True)) if date_heading else None
    calendar = detail.select_one('a[href*="outlook.live.com/calendar"]')
    if calendar:
        startdt = parse_qs(urlsplit(calendar['href']).query).get('startdt', [])
        if startdt:
            day = datetime.fromisoformat(startdt[0]).astimezone(TZ).date()
    if not day: return None
    clock = start[1] if start else None
    desc = detail.select_one('.text_block')
    organizer = detail.select_one('h5 a')
    e = build('petzi', heading.get_text(' ', strip=True), day.isoformat(), clock, url, venue, today,
              desc.get_text(' ', strip=True) if desc else '', city,
              organizer=organizer.get_text(' ',strip=True) if organizer else None,
              source_event_id=re.search(r'/events/(\d+)',url)[1])
    if e:
        doors = re.search(r'Türöffnung:\s*(\d{2}:\d{2})',body)
        e['doors_time'] = doors[1] if doors else None
        price = re.search(r'Ab CHF\s*(\d+(?:[.,]\d+)?)',body)
        if price: e['price_chf'] = float(price[1].replace(',','.'))
        art = detail.select_one('.event-picture img')
        if art: image(e, art.get('src'))
        ticket = detail.select_one('a[href$="/tickets/"]')
        if ticket: e['ticket_url'] = urljoin(url,ticket['href'])
    return e


def crawl_petzi(today):
    c = RespectfulClient('https://www.petzi.ch/de/')
    links, errors, events = set(), [], []
    for city in ['Zürich', 'Winterthur', 'Baden', 'Wetzikon', 'Rapperswil']:
        for page in range(1,5):
            url = 'https://www.petzi.ch/de/search/?'+urlencode(dict(q=city,from_date=today.isoformat(),to_date=(today+timedelta(days=90)).isoformat(),page=page))
            try:
                doc = c.fetch(url)
            except Exception as exc:
                errors.append(f"PETZI {city} page {page}: {type(exc).__name__}: {str(exc)[:100]}")
                break
            current = {urljoin(url,a['href']) for a in doc.select('a.tile[href*="/events/"]')}
            if not current or current <= links: break
            links.update(current)
            if doc.select_one('.js-no-more-event'): break
        else: errors.append(f'Pagination cap: PETZI {city} search truncated')
    for url in sorted(links):
        try:
            e = parse_petzi(c.fetch(url),url,today)
            if e: events.append(e)
        except Exception as exc: errors.append(f'{url}: {type(exc).__name__}: {str(exc)[:100]}')
    return result(events, errors, len(links))


ICMS = {'gemeinde_thalwil':('https://www.thalwil.ch/anlaesseaktuelles','Thalwil'),
        'gemeinde_regensdorf':('https://www.regensdorf.ch/anlaesseaktuelles','Regensdorf'),
        'gemeinde_uster':('https://www.uster.ch/anlaesseaktuelles','Uster'),
        'gemeinde_kloten':('https://www.kloten.ch/veranstaltungen','Kloten')}


def unescape_icms(value):
    value = re.sub(r'\\+u([0-9a-fA-F]{4})', lambda m: chr(int(m[1],16)),str(value or ''))
    return re.sub(r'\\+(["/])',r'\1',value)


def parse_icms(doc,key,index,today):
    events, errors, seen = [], [], set()
    for table in doc.select('[data-entities]'):
        payload = json.loads(table['data-entities'])
        for row in payload.get('data',[]):
            if row['id'] in seen: continue
            seen.add(row['id'])
            city = text(unescape_icms(row.get('ort') or row.get('_ort')))
            if city not in LOCALITIES: continue
            start = row.get('_datumVon')
            if not start or not is_future(date.fromisoformat(start),today):continue
            title = text(unescape_icms(row.get('name')))
            # Millisecond timestamps are local-midnight date placeholders, not
            # event clocks. Do not silently display them as midnight starts.
            url = urljoin(index,'/_rte/anlass/'+str(row['id']))
            e = build(key,title,start,None,url,text(unescape_icms(row.get('lokalitaet'))) or city,today,
                      city=city,organizer=text(unescape_icms(row.get('organisator'))) or None,
                      source_event_id=str(row['id']), date_precision='date')
            if e:
                events.append(e)
    if not seen: errors.append('No embedded ICMS calendar rows found; schema or endpoint changed')
    return result(events, errors, len(seen), len(seen)-len(events), pagination_complete=True)


def crawl_zurich(key,today=None):
    today = today or datetime.now(TZ).date()
    if key in ICMS:
        index,_ = ICMS[key]
        return parse_icms(RespectfulClient(index).fetch(index),key,index,today)
    return {'stadt_zuerich':crawl_city,'rote_fabrik':crawl_rote,'ubwg':crawl_ubwg,
            'kulturzueri':crawl_kultur,'petzi':crawl_petzi}[key](today)
