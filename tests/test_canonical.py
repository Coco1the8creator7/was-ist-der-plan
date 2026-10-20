import unittest
from backend.canonical import canonicalize, match, canonical_url, raw_identity


def event(source='official', **changes):
    obj = dict(id=source+'-1', source=source, source_url='https://'+source+'.ch/event/1',
               title='Sven Väth', date='2026-10-24', time='22:00', venue='Friedas Büxe',
               first_seen='2026-10-20', category='Sound & Clöb', price_chf=None)
    obj.update(changes)
    return obj


class CanonicalTest(unittest.TestCase):
    def test_official_fields_win_missing_fields_enriched(self):
        a=event(price_chf=25)
        b=event('ubwg',description='Details',price_chf=30)
        records,review,merged,unique=canonicalize([b,a])
        self.assertEqual(len(records),1)
        self.assertEqual(records[0]['price_chf'],25)
        self.assertEqual(records[0]['description'],'Details')
        self.assertEqual(records[0]['field_sources']['price_chf'],'official')
        self.assertEqual(len(records[0]['sources']),2)
        self.assertEqual(merged,{'ubwg':1})

    def test_other_dates_clocks_floors_and_cities_are_separate(self):
        for changes in [dict(date='2026-10-25'),dict(time='23:00'),dict(venue='Friedas Büxe Floor 2'),dict(city='Baden')]:
            a=event(city='Zürich')
            self.assertEqual(len(canonicalize([a,event('ubwg',**changes)])[0]),2)

    def test_programme_url_is_not_event_identity(self):
        a=event(source_url='https://venue.ch/programm')
        b=event('ubwg',source_url=a['source_url'],title='Different floor concert')
        self.assertEqual(len(canonicalize([a,b])[0]),2)

    def test_fuzzy_is_reviewed_not_merged(self):
        a=event(title='Clubnacht mit Sven Väth')
        b=event('ubwg',title='Friedas Büxe presents Sven Väth')
        records,reviews,_,_=canonicalize([a,b])
        self.assertEqual(len(records),2)
        self.assertEqual(reviews[0]['level'],'uncertain')

    def test_unknown_clock_never_merges_other_performances(self):
        records,reviews,_,_=canonicalize([event(),event('ubwg',time=None)])
        self.assertEqual(len(records),2)
        self.assertEqual(reviews[0]['level'],'probable')

    def test_ids_stay_stable_when_official_source_arrives(self):
        b=event('ubwg',first_seen='2026-10-19')
        old=canonicalize([b])[0]
        merged=canonicalize([event(),b],old)[0][0]
        self.assertEqual(merged['id'],b['id'])
        self.assertEqual(merged['source'],'official')

    def test_url_normalization_keeps_occurrence_selectors(self):
        self.assertEqual(canonical_url('http://www.x.ch/e/?calentry=2&utm_source=y#top'),'https://x.ch/e?calentry=2')
        self.assertNotEqual(canonical_url('https://x.ch/e?calentry=1'),canonical_url('https://x.ch/e?calentry=2'))

    def test_normalized_titles_and_venue_aliases(self):
        self.assertEqual(match(event(venue='Hive Club',title='SOIRÉE!'),event('ubwg',venue='Hive',title='Soiree'))[0],98)
