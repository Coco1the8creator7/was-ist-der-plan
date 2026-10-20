"""Conservative occurrence matching; auditable provenance, no fuzzy auto-merges.

Scores: exact occurrence URL/ID 100, exact title+venue+clock 98,
near-identical titles 85, partial token overlap 65. Only >=98 merges.
A group must match every member, preventing transitive fuzzy chains.
"""
from collections import defaultdict
from copy import deepcopy
from difflib import SequenceMatcher
import re
import unicodedata
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
import hashlib
from math import cos, radians, hypot

AGGREGATORS = {"kulturzueri", "petzi", "ubwg", "friedas_buexe"}
ALIASES = {"hiveclub": "hive", "hiveclubzurich": "hive", "kauzklub": "kauz",
           "plazaklub": "plaza", "gonzoclub": "gonzo", "exilclub": "exil",
           "friedasbuexe": "friedasbuxe", "helsinkiklub": "helsinki",
           "kulturraumzentralwascherei": "zentralwascherei", "rotefabrik": "rotefabrik"}


def normalize(value):
    value = str(value or "").casefold().replace("ß", "ss")
    return " ".join(re.findall(r"[a-z0-9]+", unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()))


def venue_key(e):
    if e.get("venue_id"):
        return e["venue_id"]
    key = normalize(e.get("venue")).replace(" ", "")
    key = re.sub(r"(?:zurich|zuerich)$", "", key)
    return ALIASES.get(key, key)


def canonical_url(url):
    p = urlsplit(str(url or ""))
    if p.scheme not in {"http", "https"} or not p.hostname:
        return ""
    # Retain occurrence selectors, ticket IDs, floor IDs and other semantic args.
    query = [(k, v) for k, v in parse_qsl(p.query) if not k.startswith("utm_") and k not in {"fbclid", "gclid"}]
    return urlunsplit(("https", p.netloc.lower().removeprefix("www."), p.path.rstrip("/"), urlencode(sorted(query)), ""))


def raw_identity(e):
    # IDs from old shared programme pages did not include clock/title. Use all
    # occurrence fields there; explicit upstream occurrence IDs remain stable.
    if e.get("source_event_id"):
        return (e["source"], str(e["source_event_id"]), e["date"])
    return (e.get("source"), canonical_url(e.get("source_url")), e.get("date"),
            e.get("time"), normalize(e.get("title")))


def match(a, b):
    if a.get("date") != b.get("date"):
        return 0, "different_date"
    if all(e.get(k) is not None for e in (a, b) for k in ("latitude", "longitude")):
        km = 111 * hypot(a["latitude"]-b["latitude"],
                         (a["longitude"]-b["longitude"])*cos(radians((a["latitude"]+b["latitude"])/2)))
        if km > .25:
            return 0, "contradictory_coordinates"
    va, vb = venue_key(a), venue_key(b)
    # Never merge distinct halls/floors just because their building is shared.
    if not va or va != vb:
        return 0, "different_or_unknown_venue"
    ca, cb = normalize(a.get("city")), normalize(b.get("city"))
    if ca and cb and ca != cb:
        return 0, "different_city"
    ta, tb = a.get("time"), b.get("time")
    if ta and tb and ta != tb:
        return 0, "different_start_time"
    title_a, title_b = normalize(a.get("title")), normalize(b.get("title"))
    urls_a = {canonical_url(a.get(k)) for k in ("source_url", "original_event_url")}
    urls_b = {canonical_url(b.get(k)) for k in ("source_url", "original_event_url")}
    # URL alone can be an entire programme, not an event. Require equal title.
    if title_a and title_a == title_b and (urls_a & urls_b) - {""} and ta == tb:
        return 100, "same_url_title_occurrence"
    if title_a and title_a == title_b and ta and tb:
        return 98, "same_title_venue_clock"
    if title_a and title_a == title_b:
        return 85, "same_title_time_unverified"
    ratio = SequenceMatcher(None, title_a, title_b).ratio()
    if ratio >= .84:
        return 85, "similar_title"
    tokens_a, tokens_b = set(title_a.split()), set(title_b.split())
    if min(len(tokens_a), len(tokens_b)) >= 2 and len(tokens_a & tokens_b) / min(len(tokens_a), len(tokens_b)) >= .5:
        return 65, "shared_title_tokens"
    return 0, "independent"


def canonicalize(records, previous=()):
    buckets = defaultdict(list)
    groups, reviews = [], []
    previous_ids = {}
    for e in previous:
        for member in e.get("raw_keys", []):
            previous_ids[member] = e["id"]
    for record in sorted(records, key=lambda e: (e.get("source") in AGGREGATORS, e.get("first_seen", ""), str(raw_identity(e)))):
        e = deepcopy(record)
        key = (e.get("date"), venue_key(e))
        target = None
        for group in buckets[key]:
            scores = [match(member, e) for member in group]
            if all(score >= 98 for score, _ in scores):
                target = group
                break
            best, reason = max(scores)
            if best >= 65:
                reviews.append({"left": group[0]["id"], "right": e["id"], "date": e["date"],
                                "score": best, "level": "probable" if best >= 85 else "uncertain", "reason": reason})
        if target is None:
            target = []
            buckets[key].append(target)
            groups.append(target)
        target.append(e)
    result = []
    merged_by_source = defaultdict(int)
    unique_by_source = defaultdict(int)
    used_ids = set()
    for group in groups:
        base = deepcopy(group[0])
        base["sources"], base["raw_keys"], base["field_sources"] = [], [], {}
        for i, member in enumerate(group):
            raw_key = repr(raw_identity(member))
            base["raw_keys"].append(raw_key)
            if i:
                merged_by_source[member["source"]] += 1
            else:
                unique_by_source[member["source"]] += 1
            provenance = {"source": member["source"], "url": member["source_url"],
                          "first_seen": member.get("first_seen"), "last_seen": member.get("last_seen")}
            if provenance not in base["sources"]:
                base["sources"].append(provenance)
            for field, value in member.items():
                if field in {"id", "source", "source_url", "sources", "raw_keys", "field_sources"}:
                    continue
                if value is not None and value != "" and (i == 0 or base.get(field) is None or base.get(field) == ""):
                    base[field] = value
                    base["field_sources"][field] = member["source"]
        # Preserve saved frontend favourites when an official source is added.
        base["id"] = next((previous_ids[k] for k in base["raw_keys"] if k in previous_ids),
                          min(group, key=lambda e: (e.get("first_seen", ""), e["id"]))["id"])
        base["match_confidence"] = "certain" if len(group) > 1 else "independent"
        base["normalized_title"] = normalize(base.get("title"))
        base.setdefault("original_title", base.get("title"))
        if base["id"] in used_ids:
            base["id"] += "-" + hashlib.sha256(base["raw_keys"][0].encode()).hexdigest()[:10]
        used_ids.add(base["id"])
        result.append(base)
    return result, reviews, dict(merged_by_source), dict(unique_by_source)
