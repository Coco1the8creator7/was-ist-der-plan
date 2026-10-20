"""Orchestrator: keep prior events on source failures, publish source-level quality."""
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from backend.sources.venues import VENUES, PENDING, crawl_venue
from backend.sources.bern import BERN_SOURCES, crawl_bern
from backend.sources.municipalities import MUNICIPAL_SOURCES, crawl_municipality
from backend.sources.koeniz import crawl_koeniz
from backend.legacy_exil import crawl_exil
from backend.sources.favourites import FAVORITES, crawl_favorite
from backend.sources.images import discard_repeated_generic_images, is_valid_image_url, empty_image_fields
from backend.categories import CATEGORIES, categorize_record
from backend.canonical import canonicalize, raw_identity
from backend.geocoding import enrich_coordinates
from backend.sources.zurich import SOURCES as ZURICH_SOURCES, crawl_zurich

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "site/data/events.json"
QUALITY = ROOT / "site/data/quality.json"
RAW = ROOT / "backend/data/raw_events.json"
MATCHES = ROOT / "backend/data/matching_review.json"
TZ = ZoneInfo("Europe/Zurich")


def load(path, fallback):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return fallback


def event_identity(event):
    return raw_identity(event)


def main(rebuild=False, source_filter=None):
    now = datetime.now(TZ).isoformat(timespec="seconds")
    today = datetime.now(TZ).date()
    old = load(OUT, {"events": []})
    prior = load(QUALITY, {"sources": {}})
    raw = load(RAW, {"events": old.get("events", [])})
    by_key = {
        event_identity(event): event
        for event in raw.get("events", [])
        if isinstance(event, dict) and event.get("source_url")
    }
    quality = dict(prior.get("sources", {}))
    sources = [("exil", crawl_exil)] + [
        (v.key, lambda v=v: crawl_venue(v)) for v in VENUES
     ] + [(v.key, lambda v=v: crawl_favorite(v)) for v in FAVORITES] + [
        (v.key, lambda v=v: crawl_bern(v)) for v in BERN_SOURCES
    ] + [
        (v.key, lambda v=v: crawl_municipality(v)) for v in MUNICIPAL_SOURCES
    ] + [("gemeinde_koeniz", crawl_koeniz)] + [
        (key, lambda key=key: crawl_zurich(key)) for key in ZURICH_SOURCES
    ]
    if rebuild:
        # Deterministic re-publication after matching-policy changes; no HTTP.
        sources = []
    elif source_filter:
        unknown = set(source_filter) - {key for key, _ in sources}
        if unknown:
            raise ValueError(f"Unknown sources: {sorted(unknown)}")
        sources = [(key, crawler) for key, crawler in sources if key in source_filter]
    # Independent domains may be fetched concurrently. Each source retains its own
    # robots-aware, rate-limited HTTP session; repository writes stay sequential.
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(crawler): key for key, crawler in sources}
        outcomes = {}
        for future in as_completed(futures):
            key = futures[future]
            try:
                outcomes[key] = future.result()
                print(f"Fetched {key}: {len(outcomes[key][1])} events", flush=True)
            except Exception as exc:
                outcomes[key] = exc
                print(f"Fetch failed {key}: {type(exc).__name__}", flush=True)
    summary = []
    for key, crawler in sources:
        old_quality = quality.get(key, {})
        try:
            outcome = outcomes[key]
            if isinstance(outcome, Exception):
                raise outcome
            found, events, errors = outcome[:3]
            meta = outcome[3] if len(outcome) > 3 else {}
            distinct = {}
            for event in events:
                distinct[event_identity(event)] = event
            duplicates = len(events) - len(distinct)
            events = list(distinct.values())
            generic_images_filtered, generic_image_urls = discard_repeated_generic_images(events)
            # Parsing a partial listing must never replace previously harvested good data.
            state = "success" if found > 0 and len(events) + duplicates == found and not errors else (
                "partial" if events else "failed"
            )
            if state == "success" and meta.get("pagination_complete") is True:
                # Only an explicitly complete, successful snapshot can retire
                # missing records. A partial/failed crawl never deletes them.
                observed = {event_identity(e) for e in events}
                by_key = {k: e for k, e in by_key.items() if e.get("source") != key or k in observed}
            for event in events:
                identity = event_identity(event)
                past = by_key.get(identity, {})
                retained = []
                for field in ("description", "price_chf", "latitude", "longitude", "organizer", "address", "ticket_url", "doors_time", "end_at"):
                    if event.get(field) is None and past.get(field) is not None:
                        event[field] = past[field]
                        retained.append(field)
                if retained:
                    event["retained_fields"] = retained
                # A temporarily missing image metadata tag should not erase a
                # previously checked URL for the exact same event and title.
                if (not event.get("image_url") and past.get("image_url")
                        and is_valid_image_url(past.get("image_url"))
                        and past.get("image_url") not in generic_image_urls
                        and past.get("title") == event["title"]):
                    for field in ("image_url", "image_source", "image_type"):
                        event[field] = past.get(field)
                event["first_seen"] = past.get("first_seen", now)
                event["last_seen"] = now
                by_key[identity] = event
            if not found and not errors:
                errors = ["No eligible future events found; manual verification required"]
            time_unknown_candidates = sum("time_unknown:" in str(error) for error in errors)
            invalid_count = len(errors)
            errors = errors[:30]
        except Exception as exc:
            found, events, duplicates, state = 0, [], 0, "failed"
            errors = [f"{type(exc).__name__}: {exc}"[:300]]
            invalid_count = 1
            meta = {}
            generic_images_filtered = 0
            time_unknown_candidates = 0
        with_images = sum(bool(e.get("image_url")) for e in events)
        with_description = sum(bool(e.get("description")) for e in events)
        with_price = sum(e.get("price_chf") is not None for e in events)
        with_coords = sum(e.get("latitude") is not None and e.get("longitude") is not None for e in events)
        with_city = sum(bool(e.get("city") or e.get("municipality")) for e in events)
        with_organizer = sum(bool(e.get("organizer")) for e in events)
        quality[key] = {
            "status": state, "last_attempt": now,
            "images_imported": with_images,
            "generic_images_filtered": generic_images_filtered,
            "image_coverage": round(with_images / len(events), 3) if events else None,
            "description_coverage": round(with_description / len(events), 3) if events else None,
            "price_coverage": round(with_price / len(events), 3) if events else None,
            "coordinate_coverage": round(with_coords / len(events), 3) if events else None,
            "municipality_coverage": round(with_city / len(events), 3) if events else None,
            "organizer_coverage": round(with_organizer / len(events), 3) if events else None,
            "time_unknown_candidates": time_unknown_candidates,
            "last_successful_import": now if state == "success" else old_quality.get("last_successful_import"),
            "last_nonempty_import": now if events else old_quality.get("last_nonempty_import"),
            "listed": found, "imported": len(events), "duplicates": duplicates,
            "invalid": invalid_count, "errors": errors,
            "low_yield_warning": bool(old_quality.get("imported", 0) >= 5 and len(events) < old_quality["imported"] * .4),
            "discovered_links": meta.get("discovered_links", found),
            "pagination_complete": meta.get("pagination_complete"),
            "upstream_total": meta.get("upstream_total"),
            "listing_pages": meta.get("listing_pages"),
            "skipped_out_of_range": meta.get("skipped_out_of_range", 0),
            "sample_coverage": old_quality.get("sample_coverage"),
            "sample_size": old_quality.get("sample_size", 0),
        }
        summary.append(f"{key}: {state} ({len(events)}/{found})")
    for key, reason in PENDING.items():
        if key in {v.key for v in FAVORITES} | set(ZURICH_SOURCES):
            continue
        quality[key] = {
            "status": "inactive", "reason": reason, "last_attempt": None,
            "last_successful_import": None, "listed": 0, "imported": 0,
            "duplicates": 0, "invalid": 0, "errors": [], "sample_coverage": None,
            "sample_size": 0,
        }
    catalog = []
    for e in by_key.values():
        try:
            if 0 <= (date.fromisoformat(e["date"]) - today).days <= 90:
                catalog.append(e)
        except (KeyError, TypeError, ValueError):
            continue
    # All published records, including retained historical imports, must use
    # the same three categories. Verified classifications are never downgraded.
    # Events with legacy categories are reclassified by title/source/venue/URL.
    # New crawls classify with richer detail-page evidence at extraction time.
    for event in catalog:
        if event.get("category") not in CATEGORIES:
            event["category"] = categorize_record(event)
    # Clear stale invalid links from previous snapshots (e.g. HTML event pages).
    for event in catalog:
        if not is_valid_image_url(event.get("image_url")):
            event.update(empty_image_fields())
    raw_catalog = catalog
    geocoding = enrich_coordinates(raw_catalog, limit=0 if rebuild else 40)
    catalog, reviews, merged, unique = canonicalize(raw_catalog, old.get("events", []))
    for key, q in quality.items():
        q["cross_source_merged"] = merged.get(key, 0)
        q["canonical_contribution"] = unique.get(key, 0)
        q["time_coverage"] = round(sum(bool(e.get("time")) for e in raw_catalog if e["source"] == key) / max(1, sum(e["source"] == key for e in raw_catalog)), 3)
        source_records = [e for e in raw_catalog if e["source"] == key]
        q["catalog_coordinate_coverage"] = round(sum(e.get("latitude") is not None and e.get("longitude") is not None for e in source_records) / max(1, len(source_records)), 3)
    catalog.sort(key=lambda e: (e["date"], e.get("time") or "", e["title"]))
    RAW.parent.mkdir(parents=True, exist_ok=True)
    RAW.write_text(json.dumps({"generated_at": now, "events": raw_catalog}, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    MATCHES.write_text(json.dumps({"generated_at": now, "candidates": reviews}, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "schema_version": 1, "generated_at": now, "timezone": "Europe/Zurich",
        "total": len(catalog), "events": catalog,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    QUALITY.write_text(json.dumps({
        "generated_at": now, "catalog_total": len(catalog),
        "raw_total": len(raw_catalog), "cross_source_merged": len(raw_catalog)-len(catalog),
        "matching_review_candidates": len(reviews),
        "geocoding": geocoding,
        "sources": quality,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("\n".join(summary))
    print("Catalog events:", len(catalog))
    # Partial source failures are reported in quality.json without failing a useful
    # overall import. Hard-fail only when no usable event data remains.
    if not catalog:
        raise SystemExit("No valid future event data available; inspect quality.json.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--rebuild", action="store_true", help="Rebuild canonical catalog from stored raw events without crawling")
    parser.add_argument("--sources", help="Comma-separated source keys for a targeted crawl; all others retain their raw records")
    args = parser.parse_args()
    main(rebuild=args.rebuild, source_filter=args.sources.split(",") if args.sources else None)
