import unittest
from datetime import date
from unittest.mock import patch
from bs4 import BeautifulSoup

from backend.categories import CONCERTS, CULTURE, SOUND
from backend.sources.koeniz import INDEX, crawl_koeniz, listing_items, months_to_crawl, parse_koeniz_listing

def page(items):
    return BeautifulSoup("<html><main><ul>" + items + "</ul></main></html>", "html.parser")

def item(date_line, name, event_id="123", occurrence="456"):
    return (
        f'<li><span>{date_line}</span>'
        f'<h2><a href="/freizeit/veranstaltungen.page/1093/event/{event_id}/eventdate/{occurrence}">'
        f'{name}</a></h2></li>'
    )

class KoenizParsingTests(unittest.TestCase):
    def test_website_occurrence_and_explicit_venue(self):
        html=page(
            item("23. Oktober 2026, ab 20:30 Uhr bis 23:30 Uhr",
                 "Naeim – Albumtaufe | Kulturhof Schloss Köniz")
            + item("24. Oktober 2026, ab 14:00 Uhr bis 21:00 Uhr",
                   "Reggae Alldayer | Dreigänger Köniz", "124", "457")
            + item("25. Oktober 2026, ab 17:00 Uhr bis 20:00 Uhr",
                   "Jubiläum Musikschule Köniz | Die Heitere Fahne", "125", "458")
        )
        found, events, errors, _=parse_koeniz_listing(html,date(2026,10,20))
        self.assertEqual((found,len(events),errors),(3,3,[]))
        self.assertEqual(events[0]["city"],"Köniz")
        self.assertEqual(events[0]["municipality"],"Köniz")
        self.assertEqual(events[0]["venue"],"Kulturhof Schloss Köniz")
        self.assertEqual(events[0]["time"],"20:30")
        self.assertEqual(events[0]["date"],"2026-10-23")
        self.assertEqual(events[0]["source_url"],"https://www.koeniz.ch/freizeit/veranstaltungen.page/1093/event/123/eventdate/456")
        self.assertTrue(all(e["region"]=="Bern" for e in events))

    def test_concert_and_cultural_policies(self):
        html=page(item("25. Oktober 2026, ab 19:00 Uhr",
                       "Matinée-Konzert | Aula Köniz", "101", "202")
                  +item("24. Oktober 2026, ab 13:00 Uhr", "Workshop GirlsCodeToo | aity AG Liebefeld", "102","203")
                  +item("23. Oktober 2026, ab 22:00 Uhr","Oldies Disco | Thomaskirche Liebefeld","103","204"))
        _,events,errors,_=parse_koeniz_listing(html,date(2026,10,20))
        self.assertEqual(errors,[])
        self.assertEqual([x["category"] for x in events],[CONCERTS,CULTURE,SOUND])

    def test_same_title_distinct_occurrence_urls(self):
        html=page(item("23. Oktober 2026, ab 16:00 Uhr","Doppelausstellung | Kulturhof","11","101")
                  +item("24. Oktober 2026, ab 11:00 Uhr","Doppelausstellung | Kulturhof","11","102"))
        _,events,errors,_=parse_koeniz_listing(html,date(2026,10,20))
        self.assertEqual(errors,[])
        self.assertNotEqual(events[0]["id"],events[1]["id"])
        self.assertNotEqual(events[0]["source_url"],events[1]["source_url"])

    def test_no_guessed_venue_or_time(self):
        html=page(item("23. Oktober 2026","Fest | Gemeindezentrum","5","7")
                  +item("23. Oktober 2026, ab 21:00 Uhr","Titel ohne Ort","6","8"))
        found,events,errors,_=parse_koeniz_listing(html,date(2026,10,20))
        self.assertEqual(found,1)
        self.assertEqual(events,[])
        self.assertEqual(len(errors),2)

    def test_ignores_old_events_and_out_of_window(self):
        html=page(item("12. Oktober 2026, ab 20:00 Uhr","Altes Event | Aula", "5", "7")
                  +item("16. Februar 2027, ab 20:00 Uhr","Späteres Event | Aula", "6", "8"))
        found,events,errors,skipped=parse_koeniz_listing(html,date(2026,10,20))
        self.assertEqual((found,len(events),skipped,len(errors)),(0,0,2,0))

    def test_monthly_year_rollover(self):
        self.assertEqual(list(months_to_crawl(date(2026,11,23))),
                         [(2026,11),(2026,12),(2027,1),(2027,2)])

    def test_only_official_detail_urls_are_accepted(self):
        doc=page(item("23. Oktober 2026, ab 20:00 Uhr","Fest | Köniz")
                 +'<li>23. Oktober 2026, ab 21:00 Uhr'
                 '<a href="https://other.example/freizeit/veranstaltungen.page/1093/event/12/eventdate/34">Fake</a></li>')
        self.assertEqual(len(list(listing_items(doc))),1)

    def test_crawler_aggregates_multiple_months(self):
        class FakeClient:
            def __init__(self, url):
                self.calls=[]
            def fetch(self, url):
                self.calls.append(url)
                return page(item("23. Oktober 2026, ab 20:00 Uhr","Dorffest | Kulturhof"))
        with patch("backend.sources.koeniz.RespectfulClient", FakeClient):
            found,events,errors,meta=crawl_koeniz(date(2026,10,20))
        self.assertEqual(found,4)
        self.assertEqual(len(events),1)
        self.assertEqual(errors,[])
        self.assertEqual(meta["discovered_links"],4)

if __name__ == "__main__":
    unittest.main()
