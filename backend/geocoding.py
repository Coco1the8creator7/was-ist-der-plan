"""Bounded Swiss address verification and reusable venue/address cache.

Only exact street + house number + locality matches from the federal address
service become event coordinates. Ambiguous results and town centroids do not.
https://docs.geo.admin.ch/access-data/search.html
"""
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
import json
import re
from urllib.parse import urlencode
from backend.canonical import normalize
from backend.sources.venues import RespectfulClient, TZ

CACHE = Path(__file__).resolve().parent/'data/venues.json'


def address_query(e):
    city=e.get('city') or e.get('municipality')
    if not city or not e.get('address'): return None
    for part in e['address'].split(','):
        part=part.strip()
        # Require a street name plus explicit building number. Four-digit postal
        # codes alone, venue names and landmark-only locations are insufficient.
        m=re.fullmatch(r'([\wÀ-ž][\wÀ-ž .\-]+?)\s+(\d{1,3}[a-zA-Z]?)',part)
        if m: return m[1].strip(),m[2],city
    return None


def verified_address(data, street, number, city):
    matches={}
    for row in data.get('results',[]):
        a=row.get('attrs',{})
        if a.get('origin')!='address':continue
        label=re.sub('<[^>]+>','',a.get('label',''))
        norm=normalize(label)
        if not re.search(r'\b'+re.escape(normalize(street+' '+number))+r'\b',norm):continue
        if not re.search(r'\b'+re.escape(normalize(city))+r'\b',norm):continue
        lat,lon=a.get('lat'),a.get('lon')
        if not isinstance(lat,(float,int)) or not isinstance(lon,(float,int)):continue
        if not (45.7<=lat<=47.9 and 5.9<=lon<=10.6):continue
        matches[(round(lat,7),round(lon,7))]=dict(latitude=lat,longitude=lon,address_label=label,
                                               coordinate_source='geo.admin.ch official address directory',
                                               coordinate_precision='building',feature_id=a.get('featureId'))
    return next(iter(matches.values())) if len(matches)==1 else None


def enrich_coordinates(events, cache_path=None, limit=40):
    path=cache_path or CACHE
    try: cache=json.loads(path.read_text())
    except (OSError,ValueError): cache={}
    queries={}
    counts=Counter()
    for e in events:
        if e.get('latitude') is not None and e.get('longitude') is not None:continue
        query=address_query(e)
        if query:
            key='|'.join(normalize(v) for v in query)
            queries[key]=query
            counts[key]+=1
    if not queries:return dict(requested=0,enriched=0,verified_addresses=0)
    now=datetime.now(TZ)
    client=None
    requested=failures=enriched=0
    changed=False
    for key in sorted(queries,key=lambda k:(-counts[k],k)):
        saved=cache.get(key)
        fresh=saved and (now-datetime.fromisoformat(saved['checked_at'])).days<30
        if fresh or requested>=limit:continue
        try:
            if client is None:client=RespectfulClient('https://api3.geo.admin.ch/')
            query=queries[key]
            url='https://api3.geo.admin.ch/rest/services/ech/SearchServer?'+urlencode(dict(type='locations',origins='address',sr=4326,limit=5,searchText=' '.join(query)))
            requested+=1
            data=client.request(url).json()
            cache[key]=dict(checked_at=now.isoformat(),query=list(query),result=verified_address(data,*query))
            changed=True
        except Exception:
            failures+=1
            if failures>=3:break
    for e in events:
        if e.get('latitude') is not None and e.get('longitude') is not None:continue
        query=address_query(e)
        if not query:continue
        saved=cache.get('|'.join(normalize(v) for v in query),{})
        if saved.get('result'):
            for field in ['latitude','longitude','coordinate_source','coordinate_precision']:
                e[field]=saved['result'][field]
            enriched+=1
    if changed:
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(cache,ensure_ascii=False,indent=2)+'\n')
    return dict(requested=requested,enriched=enriched,verified_addresses=sum(bool(v.get('result')) for v in cache.values()),failures=failures)
