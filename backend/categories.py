"""Single backend authority for the three public event categories.

This is a conservative rule classifier. Venue name is only a *default*; explicit
event format wins. A DJ set must never become a concert simply because it is
hosted by a concert venue. Unknown non-nightlife formats fall back to culture.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

SOUND = "Sound & Clöb"
CULTURE = "Kultur & Workshops"
CONCERTS = "Konzerte"
CATEGORIES = (SOUND, CULTURE, CONCERTS)

# Sources whose published programmes are mostly parties, club nights or bar DJ sets.
NIGHTLIFE_SOURCES = frozenset({
    "exil", "hive", "plaza", "kauz", "gonzo", "friedas_buexe",
    "supermarket", "stereo_bar",
    "dachstock_bern", "gaskessel_bern", "isc_bern", "bierhuebeli_bern",
})

# The strongest evidence is an explicit event type in the title or URL.
CULTURE_EVENT = re.compile(
    r"\b(?:literatur|(?:vor|autoren|buch)?lesung(?:en)?|buchvernissage|buchpräsentation|"
    r"poetry[ -]?slam|spoken[ -]?word|kultur(?:anlass|event)?|theater|schauspiel|kabarett|"
    r"comedy|stand[ -]?up|satire|kunst|vernissage|galerie|"
    r"ausstellung|museum|filmvorführung|filmabend|kino|"
    r"workshop|kurs(?:e)?|seminar|vortrag|lecture|talk(?:s)?|"
    r"panel|diskussion(?:en)?|debatt(?:e|en)|podium(?:sdiskussion)?|"
    r"podcast|lesekreis|community|meetup|quartier(?:anlass|treff)|"
    r"networking|führung|fuehrung|science|wissenschaft|"
    r"tanzbattle|dance[ -]?battle|breakdance[ -]?battle|"
    r"red bull dance your style|quiz(?:abend)?|pub[ -]?quiz)\b",
    re.I,
)
CONCERT_EVENT = re.compile(r"\b(?:[\wäöüÄÖÜ]*konzert(?:e|en|s)?|concert(?:s)?)\b", re.I)
DJ_EVENT = re.compile(
    r"\b(?:djs?|dj[ -]?set(?:s)?|b2b|back[ -]?to[ -]?back|"
    r"all[ -]?night[ -]?long|open[ -]?decks|clubnacht|"
    r"club[ -]?night|disco[ -]?party|rave)\b", re.I
)
SOUND_EVENT = re.compile(
    r"\b(?:party|parties|afterparty|aftershow|clubbing|clubnacht|"
    r"nachtleben|nightlife|night[ -]?out|girls[ -]?night|club[ -]?night|"
    r"dancefloor|daydance|rave|disco|techno|hardtechno|"
    r"trance|house|hip[ -]?hop|karaoke|basslines?|beats?|"
    r"dancehall|reggaeton|musikabend|live[ -]?musik|"
    r"jam(?:[ -]?session)?|dj|djs|b2b)\b",
    re.I,
)
CLUB_LOCATION = re.compile(
    r"\b(?:club|klub|bar|büxe|buexe|exil|hive|gonzo|plaza|"
    r"supermarket|kauz|jade|klubsaal|pelikanbar)\b", re.I
)
# Concert evidence in Moods detail: an actual on-stage lineup with instruments.
INSTRUMENTS = re.compile(
    r"\b(?:gesang|vocals?|gitarre|guitar|bass|schlagzeug|drums|"
    r"keyboard(?:s)?|klavier|piano|saxofon|saxophon|trumpet|"
    r"trompete|violine|geige|cello|flöte|flute|"
    r"orchester|quartett?|quintett?|ensemble)\b", re.I
)
EXPLICIT_FORMAT = re.compile(
    r"\b(?:veranstaltungsart|veranstaltungstyp|event(?:-|[ ])?typ|"
    r"event(?:-|[ ])?art|kategorie|format)\s*:\s*"
    r"(konzert|concert|lesung|literatur|workshop|vortrag|diskussion|"
    r"theater|comedy|ausstellung|party|clubnacht)\b", re.I
)
CONCERT_PATH = re.compile(r"(?:^|[/_-])(?:konzert|concert)(?:[/_-]|$)", re.I)
CULTURE_PATH = re.compile(
    r"(?:^|[/_-])(?:kurs|workshop|literatur|lesung|theater|"
    r"comedy|podcast|vortrag|diskussion|ausstellung)(?:[/_-]|$)", re.I
)


def classify_category(
    title: str,
    *,
    source: str = "",
    venue: str = "",
    url: str = "",
    details: str = "",
    start_time: str = "",
) -> str:
    """Return precisely one of CATEGORIES from verifiable event information.

    details should contain only the event-specific portion of a detail page.
    Do not pass a listing page, navigation or related-events section.
    """
    title = title or ""
    source = (source or "").lower()
    venue = venue or ""
    path = urlparse(url or "").path
    lead = (details or "")[:1600]

    # A bar's literature night stays cultural; a dedicated course always does too.
    if CULTURE_EVENT.search(title) or CULTURE_PATH.search(path):
        return CULTURE

    # Explicitly stated event type in the event-specific header.
    header = EXPLICIT_FORMAT.search(lead[:650])
    if header:
        label = header[1].lower()
        if label in ("konzert", "concert"):
            return SOUND if DJ_EVENT.search(title) else CONCERTS
        if label in ("party", "clubnacht"):
            return SOUND
        return CULTURE

    explicit_concert = bool(CONCERT_EVENT.search(title) or CONCERT_PATH.search(path))
    if explicit_concert:
        # "DJ Konzert" is still a DJ performance, not a live concert.
        return SOUND if DJ_EVENT.search(title) else CONCERTS

    # The label only appears in details: an *event-specific* heading, not a
    # biography mentioning past concerts or a global footer saying "Konzerte".
    if re.search(r"\b(?:das|dieses|ein)\s+konzert\b", lead[:500], re.I):
        return SOUND if DJ_EVENT.search(title) else CONCERTS

    # Moods publishes both stage concerts and DJ/dance events.
    # Only identify a live concert from clear live-band evidence.
    if source == "moods":
        if re.search(r"\b(?:dance your style|battle|tanzwettbewerb)\b", title, re.I):
            return CULTURE
        if not DJ_EVENT.search(title) and (
            ("Line-Up" in lead and INSTRUMENTS.search(lead))
            or re.search(r"\b(?:live[ -]?trio|jazz[ -]?trio|orchester|orchestra|quartet|quartett|ensemble)\b", title, re.I)
        ):
            return CONCERTS

    # Nightlife or bar music, unless an explicit cultural format above overrides.
    if source in NIGHTLIFE_SOURCES or source == "moods" or CLUB_LOCATION.search(venue):
        return SOUND
    if SOUND_EVENT.search(title):
        return SOUND
    if source == "kaufleuten":
        # Late-night openings on this mixed-use venue are typically parties.
        # Explicit concert/culture cues above always win.
        if re.match(r"^(?:22|23):[0-5][0-9]$", start_time or ""):
            return SOUND
        # Kaufleuten has cultural events *and* parties; prefer event-format
        # evidence, e.g. "LOCO HOUSE", over venue-only attribution.
        if re.search(
            r"\b(?:jade club|kaufleuten klub|tanzfläche|hiphop|"
            r"hip-hop|r&b|dancehall|dj[ -]|beats?|party)\b", lead[:1200], re.I
        ):
            return SOUND
    # Unlabelled cultural/general events cannot become concerts by venue alone.
    return CULTURE


def categorize_record(event: dict) -> str:
    """Classify imported and pre-existing records with the same rules."""
    return classify_category(
        str(event.get("title") or ""),
        source=str(event.get("source") or ""),
        venue=str(event.get("venue") or ""),
        url=str(event.get("source_url") or event.get("url") or ""),
        details=str(event.get("classification_context") or ""),
        start_time=str(event.get("time") or ""),
    )
