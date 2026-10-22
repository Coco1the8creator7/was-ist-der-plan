from datetime import date
from bs4 import BeautifulSoup
from backend.sources.favourites import parse_friedas_ausgangheute

def test_friedas_alternate_listing_two_weekend_events():
    html = """
    <a href="/event/abc">Freitag, 23. Oktober 2026, 23:00 Uhr Family Affair techno</a>
    <a href="/event/def">Samstag, 24. Oktober 2026, 22:00 Uhr Clubnacht: Sven Väth party</a>
    <a href="/event/abc">Freitag, 23. Oktober 2026, 23:00 Uhr Family Affair techno</a>
    <a href="/venue/somewhere">Freitag, 23. Oktober 2026, 20:00 Uhr Unrelated</a>
    """
    found, events, errors, meta = parse_friedas_ausgangheute(BeautifulSoup(html, "html.parser"), date(2026, 10, 22))
    assert found == 2
    assert len(events) == 2
    assert not errors
    assert [e["time"] for e in events] == ["23:00", "22:00"]
    assert all(e["category"] == "Sound & Clöb" for e in events)
    assert all(e["venue"] == "Friedas Büxe" for e in events)
    assert meta["pagination_complete"] is False

def test_friedas_alternate_listing_rejects_unverified_time():
    html = '<a href="/event/no-clock">Freitag, 23. Oktober 2026 Party</a>'
    found, events, errors, _ = parse_friedas_ausgangheute(BeautifulSoup(html, "html.parser"), date(2026, 10, 22))
    assert found == 1
    assert not events
    assert "date/time absent" in errors[0]
