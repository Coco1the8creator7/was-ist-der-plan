# Backend audit and Bern source inventory — 2026-10-20

## Measured catalog health
Snapshot: site/data/events.json generated 2026-10-20T15:07:36+02:00.
388 events: 388 titled/dated/timed/source-linked; 324 with images; 192 with a numeric
price; **0 descriptions; 0 coordinates**. Field coverage is not venue recall.
All sample_coverage fields are null and sample_size=0: a 95% completeness
claim is currently **not supported**. Four same-title/date/venue records are
duplicate *suspects*; simultaneous performances must be checked manually.

| Source | Events | Image URLs | Last status | Primary QA concern |
|---|---:|---:|---|---|
| dynamo | 151 | 118 | success | Course occurrences, incomplete images |
| kaufleuten | 89 | 85 | success | Concert vs nightlife, venue metadata |
| exil | 54 | 54 | success | Compare programme with sampled real dates |
| moods | 32 | 32 | success | Double performances, concert evidence |
| plaza | 32 | 32 | success | Ticket inventory vs recorded dates |
| hive | 14 | 0 | success | Missing event images |
| gonzo | 8 | 0 | partial | Unknown start time causes exclusions |
| supermarket | 5 | 0 | success | Images, missing descriptions |
| kauz | 2 | 2 | success | Low event volume: check recall |
| friedas_buexe | 1 | 1 | success | Check pagination / completeness |
| stereo_bar | 0 | 0 | failed | Page/parser verification |
| helsinki, rote_fabrik | 0 | 0 | inactive | Adapter not verified |

Unknown without a human source-to-catalog audit: recall, event accuracy,
cancellation detection, address accuracy, event recurrence and classification
precision. A successful crawl status does not imply a 95% capture rate.

## Bern source inventory

Availability below means a dated public programme was observed on 2026-10-20.
It does not mean the code successfully imported the programme yet.

| Priority | Provider | Programme | Area | Parsing route | State |
|---|---|---|---|---|---|
| P0 | Dachstock / Reitschule | https://www.dachstock.ch/events | Bern | Dated /events/ URLs + Doors + detail format | Adapter, awaiting live |
| P0 | Gaskessel | https://gaskessel.ch/programm/ | Bern | Date blocks on one page; Doors; workshops | Adapter, awaiting live |
| P0 | Bierhübeli | https://bierhuebeli.ch/ | Bern | /konzerte/ and /partys/ -> /event/; Beginn | Adapter, awaiting live |
| P0 | ISC | https://isc-club.ch/programm/next-up/ | Bern | /programm/ cards; calendar dates on details | Adapter, awaiting live; verify index longevity |
| P0 | Dampfzentrale | https://www.dampfzentrale.ch/ | Bern | Dated overview occurrences; shared detail URL | Adapter, awaiting live |
| P1 | PROGR | https://www.progr.ch/de/agenda/ | Bern | Mixed forms, exhibitions, recurring dates | Verified public programme, no adapter |
| P1 | Bern Welcome | https://bern.com/de/aktuelles/veranstaltungskalender/ | Bern, Emmental, Gantrisch, Laupen | Regional aggregator and organiser links | Programme found, no adapter |
| P1 | Köniz | https://www.koeniz.ch/freizeit/veranstaltungen.page/436 | Köniz | Official event calendar / citymobile links | Programme found, no adapter |
| P1 | Belp | https://www.belp.ch/de/veranstaltungen/ | Belp | Municipal date/time + organiser | Programme found, no adapter |
| P1 | Uttigen | https://www.uttigen.ch/de/veranstaltungen/ | Uttigen | Reusable municipal calendar structure | Programme found, no adapter |
| P1 | Kulturhof | https://www.kulturhof.ch/ | Bern area | Date-card pages | Programme found, venue location to verify |
| P2 | Stadt Bern | https://www.bern.ch/themen/freizeit-und-sport/veranstaltungen | Bern | Directory to further event feeds | Verified link directory |
| P2 | Eventfrog | https://eventfrog.ch/de/events/koeniz.html | Bern area | Discovery/dedup, original organiser preferred | Candidate |
| P2 | BKA | https://www.bka.ch/ | Bern | Cultural aggregator and listings | Candidate |
| P2 | Resident Advisor | https://ra.co/ | Bern | Club-event discovery; respect access restrictions | Candidate |
| Hold | Kapitel Bollwerk | https://ubwg.ch/event/kapitel-bollwerk-closing-kapitel-bern-08-06-2024/ | Bern | Historical closing programme in 2024 | Do not assume venue is active |

Additional research leads: associations, fire-brigade festivals, fair
committees, community centres, and municipal calendars in Ostermundigen,
Ittigen, Zollikofen, Burgdorf, Münsingen, Worb, Rubigen, Köniz and Laupen.
The initial inventory is not exhaustive.

## Scalable municipality pipeline — next step
1. Configure town sources by recurring municipality website template, not one
   bespoke adapter per place. Store municipal territory separately from
   actual event location.
2. Prefer public Event JSON-LD, ICS/iCal, RSS/Atom, or official programme
   endpoints; otherwise parse event lists and relevant detail pages.
3. Save a quality review queue for date-only and time-unknown event candidates.
   The existing frontend relies on start_at, so add compatible v2 migration
   before publishing records with null times.
4. Low-change municipalities use daily cadence; status changes and holidays
   require a faster check near event time if permitted.
5. Build a provenance-aware venue/address/municipality registry; no guessing
   coordinates based on source domain. Geocode approved verified addresses,
   then compute distances from Zurich and Bern city centres.
6. Measure source recall on manually checked listings: events imported divided
   by source events actually listed within the same period. Separately measure
   precision, duplicates, classification mistakes, and stale cancellations.
7. Require explicit cancellation evidence or multiple successful reconciled
   snapshots before removing an event; transport failures must not erase it.

## Compatibility and risks
Bern records add optional municipality, city, region, canton, country and
time_unknown=false fields under schema v1. Zurich events and image fallbacks
are unchanged. No coordinates are invented, so the geographic 50-km filter
cannot yet be declared accurate. Existing RespectfulClient enforces HTTPS,
host restrictions, robots directives and polite pacing. Adapters have offline
fixtures only until the GitHub workflow reports real live imports. A separate
verified coordinate registry and frontend regression test are necessary
before region-specific distance filtering is enabled.
