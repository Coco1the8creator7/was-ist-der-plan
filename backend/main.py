"""Orchestrator: keep prior events on source failures, publish source-level quality."""
import json
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from backend.sources.venues import VENUES, PENDING, crawl_venue
from backend.legacy_exil import crawl_exil

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "site/data/events.json"
QUALITY = ROOT / "site/data/quality.json"
TZ = ZoneInfo("Europe/Zurich")


def load(path, fallback):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return fallback


def main():
    now = datetime.now(TZ).isoformat(timespec="seconds")
    today = datetime.now(TZ).date()
    old = load(OUT, {"events": []})
    prior = load(QUALITY, {"sources": {}})
    by_key = {
        (event.get("source"), event.get("source_url"), event.get("date")): event
        for event in old.get("events", [])
        if isinstance(event, dict) and event.get("source_url")
    }
    quality = dict(prior.get("sources", {}))
    sources = [("exil", crawl_exil)] + [
        (v.key, lambda v=v: crawl_venue(v)) for v in VENUES
    ]
    summary = []
    for key, crawler in sources:
        old_quality = quality.get(key, {})
        try:
            found, events, errors = crawler()
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
                identity = (key, event["source_url"], event["date"])
                past = by_key.get(identity, {})
                event["first_seen"] = past.get("first_seen", now)
                event["last_seen"] = now
                by_key[identity] = event
            if not found and not errors:
                errors = ["No eligible future events found; manual verification required"]
            errors = errors[:30]
        except Exception as exc:
            found, events, duplicates, state = 0, [], 0, "failed"
            errors = [f"{type(exc).__name__}: {exc}"[:300]]
        quality[key] = {
            "status": state, "last_attempt": now,
            "last_successful_import": now if state == "success" else old_quality.get("last_successful_import"),
            "listed": found, "imported": len(events), "duplicates": duplicates,
            "invalid": len(errors), "errors": errors,
            "sample_coverage": old_quality.get("sample_coverage"),
            "sample_size": old_quality.get("sample_size", 0),
        }
        summary.append(f"{key}: {state} ({len(events)}/{found})")
    for key, reason in PENDING.items():
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
    # The workflow should flag any degradation even when a previous catalog remains valid.
    if any(quality[key]["status"] != "success" for key, _ in sources):
        raise SystemExit("Some sources are partial/failed. See quality.json; previous events retained.")


if __name__ == "__main__":
    main()
