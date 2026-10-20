import unittest
from backend.geocoding import address_query, verified_address

class GeocodingTest(unittest.TestCase):
    def test_only_real_address_queries(self):
        self.assertEqual(address_query(dict(address='Museum, Augustinergasse 9, 8001 Zürich',city='Zürich')),('Augustinergasse','9','Zürich'))
        self.assertIsNone(address_query(dict(address='8001 Zürich',city='Zürich')))
        self.assertIsNone(address_query(dict(address='Josefwiese',city='Zürich')))

    def test_exact_building_match_and_ambiguous_candidates(self):
        row=dict(attrs=dict(origin='address',label='Augustinergasse 9 <b>8001 Zürich</b>',lat=47.37,lon=8.54,featureId='1'))
        self.assertIsNotNone(verified_address({'results':[row]},'Augustinergasse','9','Zürich'))
        self.assertIsNone(verified_address({'results':[row]},'Augustinergasse','90','Zürich'))
        self.assertIsNone(verified_address({'results':[row]},'Augustinergasse','9','Baden'))
        other=dict(attrs=dict(row['attrs'],lon=8.55))
        self.assertIsNone(verified_address({'results':[row,other]},'Augustinergasse','9','Zürich'))
        row['attrs']['origin']='gg25'
        self.assertIsNone(verified_address({'results':[row]},'Augustinergasse','9','Zürich'))
