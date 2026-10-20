"""Parser regression fixtures captured from the public sources on 2026-10-20."""
import json
from datetime import date
from pathlib import Path
import unittest
from bs4 import BeautifulSoup
from backend.sources.zurich import parse_city, parse_rote, parse_ubwg, parse_kultur, parse_petzi, parse_icms

P=Path(__file__).parent/'fixtures/zurich'
TODAY=date(2026,10,20)
def doc(name): return BeautifulSoup((P/(name+'.html')).read_text(),'html.parser')
def rows(name): return json.loads((P/(name+'.json')).read_text())

class ZurichFixtures(unittest.TestCase):
    def test_rote_utc_date_converted_before_clock_applied(self):
        e=parse_rote(rows('rote')[0],TODAY)
        self.assertEqual(e['date'],'2026-10-20')
        self.assertEqual(e['time'],'20:00')
        self.assertEqual(e['doors_time'],'19:30')
        self.assertIsNone(e['price_chf']) # CMS numeric zero is not a free ticket
        self.assertEqual(e['category'],'Kultur & Workshops')

    def test_city_unknown_midnight_not_presented_as_time(self):
        row=next(r for r in rows('city') if 'Karl' in r.get('eventLocation',''))
        e=parse_city(row,TODAY)
        self.assertTrue(e['time_unknown'])
        self.assertIsNone(e['start_at'])
        self.assertIsNone(e['time'])
        self.assertIn('calentry=',e['source_url'])

    def test_city_does_not_invent_locality_for_unknown_place(self):
        row=rows('city')[0]
        row['eventLocation']='Unbekannte Lokalität'
        self.assertIsNone(parse_city(row,TODAY))

    def test_ubwg_locality_and_event_image(self):
        e=parse_ubwg(rows('ubwg')[0],TODAY)
        self.assertEqual(e['venue'],'Kauz')
        self.assertEqual(e['city'],'Zürich')
        self.assertEqual(e['category'],'Sound & Clöb')
        self.assertIn('kaltstart',e['image_url'])
        self.assertNotIn('logo',e['image_url'])

    def test_kultur_all_schedule_instances_not_parent_start_date(self):
        events=parse_kultur(doc('kultur-detail'),'https://www.kulturzueri.ch/db/veranstaltungen/example/',TODAY)
        self.assertEqual([e['date'] for e in events],['2026-10-21','2026-10-23'])
        self.assertEqual([e['time'] for e in events],['12:30','12:30'])
        self.assertTrue(all(e['category']=='Kultur & Workshops' for e in events))

    def test_petzi_start_separate_from_door(self):
        e=parse_petzi(doc('petzi-detail'),'https://www.petzi.ch/de/events/64702-test/',TODAY)
        self.assertEqual(e['time'],'20:00')
        self.assertEqual(e['doors_time'],'19:30')
        self.assertEqual(e['price_chf'],15)
        self.assertEqual(e['category'],'Kultur & Workshops')

    def test_icms_embedded_rows_date_precision_and_unicode(self):
        found,events,errors,meta=parse_icms(doc('icms'),'gemeinde_thalwil','https://www.thalwil.ch/anlaesseaktuelles',TODAY)
        self.assertEqual(len(events),2)
        self.assertEqual(events[0]['title'],'Kafi Treff')
        self.assertTrue(events[0]['time_unknown'])
        self.assertIsNone(events[0]['time'])
        self.assertNotIn('\\',events[0]['title'])

    def test_rote_cancellation_state(self):
        row=rows('rote')[0]
        row['rf_event']['state']=4
        self.assertEqual(parse_rote(row,TODAY)['status'],'cancelled')

    def test_petzi_biographical_date_cannot_override_event(self):
        d=doc('petzi-detail')
        d.select_one('.text_block').insert(0,'Archivdatum 1. Januar 2020. ')
        e=parse_petzi(d,'https://www.petzi.ch/de/events/64702-test/',TODAY)
        self.assertEqual(e['date'],'2026-10-21')

    def test_pagination_failure_preserves_first_city_page(self):
        from unittest.mock import patch, Mock
        from backend.sources.zurich import crawl_city
        client=Mock()
        response=Mock()
        response.json.return_value={'results':rows('city'),'meta':{'total':101}}
        client.request.side_effect=[response,RuntimeError('temporary failure')]
        with patch('backend.sources.zurich.RespectfulClient',return_value=client):
            _,events,errors,meta=crawl_city(TODAY)
        self.assertTrue(events)
        self.assertTrue(errors)
        self.assertFalse(meta['pagination_complete'])

    def test_onthur_shared_programme_explicit_formats(self):
        from backend.sources.zurich import parse_onthur
        _,events,errors,_=parse_onthur(doc('onthur'),TODAY)
        self.assertEqual(len(events),3)
        self.assertFalse(errors)
        self.assertEqual(events[0]['category'],'Kultur & Workshops')
        concert=next(e for e in events if 'Makthaverskan' in e['title'])
        self.assertEqual(concert['category'],'Konzerte')
        self.assertEqual(concert['city'],'Winterthur')
        self.assertEqual(concert['date'],'2026-10-21')
