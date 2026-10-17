"""Orchestrator: keep prior events on source failures, publish source-level quality."""
import json
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from backend.sources.venues import VENUES, PENDING, crawl_venue
from backend.legacy_exil import crawl_exil
from backend.sources.favourites import FAVORITES, crawl_favorite

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "site/data/events.json"
QUALITY = ROOT / "site/data/quality.json"
TZ = ZoneInfo("Europe/Zurich")


def load(path, fallback):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return fallback


def event_identity(event):
    # Programme pages can list several separate parties on one date.
    source = event.get("source")
    identity = (source, event.get("source_url"), event.get("date"))
    if source in {"gonzo", "stereo_bar", "supermarket"}:
        identity += (str(event.get("title", "")).casefold(),)
    return identity


def main():
    now = datetime.now(TZ).isoformat(timespec="seconds")
    today = datetime.now(TZ).date()
    old = load(OUT, {"events": []})
    prior = load(QUALITY, {"sources": {}})
    by_key = {
        event_identity(event): event
        for event in old.get("events", [])
        if isinstance(event, dict) and event.get("source_url")
    }
    quality = dict(prior.get("sources", {}))
    sources = [("exil", crawl_exil)] + [
        (v.key, lambda v=v: crawl_venue(v)) for v in VENUES
    ] + [(v.key, lambda v=v: crawl_favorite(v)) for v in FAVORITES]
    summary = []
    for key, crawler in sources:
        old_quality = quality.get(key, {})
        try:
            outcome = crawler()
            found, events, errors = outcome[:3]
            meta = outcome[3] if len(outcome) > 3 else {}
            distinct = {}
            for event in events:
                distinct[(event["source"], event["source_url"], event["date"], event["title"])] = event
            duplicates = len(events) - len(distinct)
            events = list(distinct.values())
            # Parsing a partial listing must never replace previously harvested good data.
            state = "success" if found > 0 and len(events) + duplicates == found and not errors else (
                "partial" if events else "failed"
            )
            for event in events:
                identity = event_identity(event)
                past = by_key.get(identity, {})
                # A temporarily missing image metadata tag should not erase a
                # previously checked URL for the exact same event and title.
                if not event.get("image_url") and past.get("image_url") and past.get("title") == event["title"]:
                    for field in ("image_url", "image_source", "image_type"):
                        event[field] = past.get(field)
                event["first_seen"] = past.get("first_seen", now)
                event["last_seen"] = now
                by_key[identity] = event
            if not found and not errors:
                errors = ["No eligible future events found; manual verification required"]
            errors = errors[:30]
        except Exception as exc:
            found, events, duplicates, state = 0, [], 0, "failed"
            errors = [f"{type(exc).__name__}: {exc}"[:300]]
            meta = {}
        with_images = sum(bool(e.get("image_url")) for e in events)
        quality[key] = {
            "status": state, "last_attempt": now,
            "images_imported": with_images,
            "image_coverage": round(with_images / len(events), 3) if events else None,
            "last_successful_import": now if state == "success" else old_quality.get("last_successful_import"),
            "listed": found, "imported": len(events), "duplicates": duplicates,
            "invalid": len(errors), "errors": errors,
            "discovered_links": meta.get("discovered_links", found),
            "skipped_out_of_range": meta.get("skipped_out_of_range", 0),
            "sample_coverage": old_quality.get("sample_coverage"),
            "sample_size": old_quality.get("sample_size", 0),
        }
        summary.append(f"{key}: {state} ({len(events)}/{found})")
    for key, reason in PENDING.items():
        if key in {v.key for v in FAVORITES}:
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
    catalog.sort(key=lambda e: e["start_at"])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "schema_version": 1, "generated_at": now, "timezone": "Europe/Zurich",
        "total": len(catalog), "events": catalog,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    QUALITY.write_text(json.dumps({
        "generated_at": now, "catalog_total": len(catalog),
        "sources": quality,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("\n".join(summary))
    print("Catalog events:", len(catalog))
    # Partial source failures are reported in quality.json without failing a useful
    # overall import. Hard-fail only when no usable event data remains.
    if not catalog:
        raise SystemExit("No valid future event data available; inspect quality.json.")


if __name__ == "__main__":
    main()
