# was ist der plan? – Zürcher Eventkalender

Automatischer Eventkatalog, 90-Tage-Suchfenster, alle 6 Stunden über GitHub Actions.

## Stand

Zürich und Umgebung sowie Bern/Umland werden gemeinsam verarbeitet. Die erste
Zürcher Erweiterungswelle ergänzt Stadt Zürich, Kulturzüri, PETZI, Rote Fabrik,
UBWG, OnThur (Winterthur) und wiederverwendbare ICMS-Gemeindekalender. Tatsächliche Quellenergebnisse
und Grenzen stehen im [Quelleninventar](docs/zurich-source-inventory.md) und im
aktuellen `site/data/quality.json`. Ein registrierter Adapter ist kein Beleg
für eine vollständige oder erfolgreiche Erfassung.

## Import starten
Unter [Actions](https://github.com/Coco1the8creator7/was-ist-der-plan/actions) → **Eventdaten aktualisieren** → **Run workflow**.
Der Workflow führt zuerst Offline-Tests aus, danach die Quellenabrufe und speichert `site/data/events.json` und `site/data/quality.json`.
Teilweise oder fehlgeschlagene Quellen stehen in `quality.json`. Der Gesamtimport schlägt nur fehl, wenn kein brauchbarer Katalog übrig bleibt; erhaltene Events werden bei Quellausfällen weiter veröffentlicht.

## Dateien
- `backend/main.py`: Quellenorchestrierung, Status, Zusammenführung und JSON-Publikation
- `backend/legacy_exil.py`: EXIL-Adapter
- `backend/sources/zurich.py`: neue öffentliche APIs, JSON-LD-Termine und ICMS-Kalender
- `backend/canonical.py`: konservatives Matching, Feldherkunft und Quellenzusammenführung
- `backend/geocoding.py`: eindeutige Schweizer Gebäudeadressen mit Cache
- `backend/data/raw_events.json`: quellengetrennte Rohdatensätze
- `backend/data/canonical_provenance.json`: Feldherkunft und Rohdatenzuordnung; nicht Teil des Browser-Downloads
- `backend/data/matching_review.json`: wahrscheinliche und unklare Treffer, automatisch getrennt
- `backend/data/venues.json`: verifizierte und ergebnislose Adressabfragen
- `backend/sources/venues.py`: neue getrennt konfigurierte Pilot-Adapter für Veranstaltungsorte
- `tests/test_venues.py`: Offline-Parsertests
- `site/data/events.json`: öffentlicher Eventkatalog
- `site/data/quality.json`: Importzahlen, Fehler und manuelle Erfassungsquote pro Quelle

## Qualitätsregeln
Events benötigen einen prüfbaren Titel und ein vollständiges Datum. Unbekannte
Uhrzeiten werden als `time: null`, `start_at: null`, `time_unknown: true`
gespeichert; Karten und Kalender zeigen «Zeit offen». Kein künstlicher
Mitternachtsbeginn. Bestehende Adapter können unlesbare Zeiten weiterhin im
Qualitätsbericht zurückweisen, bis ihr Detailparser umgestellt ist.

Quellenfehler und unvollständige Pagination löschen keine alten guten Daten.
Nur eine explizit vollständige, erfolgreiche Quellensichtung darf fehlende
Einträge entfernen. `last_seen` und erhaltene Felder bleiben nachvollziehbar.

Sichere Übereinstimmungen erzeugen ein kanonisches Event mit `sources`,
`raw_keys` und `field_sources`; offizielle Quellen haben Vorrang. Identische
Titel an demselben Ort mit bestätigtem gleichem Beginn erreichen 98 Punkte,
übereinstimmende URL/Titel/Termin 100. Nur diese werden zusammengeführt.
Wahrscheinliche Treffer (85) und unklare Titelüberschneidungen (65) bleiben im
Prüfprotokoll getrennt. Verschiedene Tage, bestätigte Beginnzeiten, Räume oder
widersprüchliche Koordinaten verhindern eine Zusammenführung.

Geocoding übernimmt nur eindeutige Gebäudeadressen, keine Gemeindezentren.
Fehlende Koordinaten bleiben unbekannt. Feldabdeckung und Parserausbeute sind
keine Veranstaltungs-Erfassungsquote. `sample_coverage` bezeichnet ausschliesslich
eine dokumentierte Kontrollstichprobe und bleibt ohne eine solche leer.

## Lokale Ausführung
```bash
python3 -m pip install -r requirements.txt
python3 -m unittest discover -s tests -v
python3 -m backend.main
# Einzelne Quellen prüfen, ohne den übrigen Bestand zu verlieren:
python3 -m backend.main --sources onthur,stadt_zuerich
# Ohne HTTP aus gespeicherten Rohdaten neu konsolidieren:
python3 -m backend.main --rebuild
```
Die neue Version ist ein **Pilot**. Änderungen der Website-Strukturen, robots.txt oder Zugangsbeschränkungen können einzelne Adapter deaktivieren. Es werden keine Zugriffssperren umgangen.

## Eventbilder / Flyer (v0.6)

Der Crawler sucht auf **einzelnen Event-Detailseiten** zuerst nach Event-JSON-LD und dann nach Metadaten (`og:image`, Twitter-Vorschaubild) und ausdrücklich eventbezogenen Bildern.
Die Datenfelder sind:

- `image_url`: HTTPS-Bildadresse oder `null`
- `image_source`: Herkunftsadapter, beispielsweise `exil`, oder `null`
- `image_type`: `event_flyer`, wenn entsprechend bezeichnet; sonst `event_image` oder `null`

**Keine Bilder werden heruntergeladen oder ins Git-Repository geschrieben.** Die Webseite zeigt externe Bilder mit Lazy Loading und 5:3-Ausschnitt, und fällt bei fehlenden/gesperrten Bildern auf die bisherige Farbfläche zurück. Generische Logos/Platzhalter werden gefiltert. Vor einem breiten öffentlichen Einsatz sind die Bild-Nutzungsrechte und Hotlink-Richtlinien der Betreiber zu prüfen.

Programmseiten ohne eindeutige Bildzuordnung (etwa Gonzo oder Stereo) behalten zunächst bewusst leere Bildfelder. Das verhindert, dass ein beliebiges Clubfoto einem konkreten Event zugeordnet wird. Quellenadapter mit Event-Detailseiten (EXIL, Hive, Kaufleuten, Plaza, Kauz, Moods, Dynamo, Frieda via UBWG) lesen die Bild-URL aus demselben HTML, das ohnehin für das Event geladen wird.

`site/data/quality.json` protokolliert `images_imported` und `image_coverage` pro Quelle. Die Bildabdeckung ist **keine** vollständige Veranstaltungs-Erfassungsquote. Vorhandene ältere Events werden beim nächsten regulären Import um die Bildfelder ergänzt; ein Mangel an Bilddaten ist kein Crawlerfehler.

## Öffentliche Hauptkategorien (v1)

Alle Events werden in **genau einer** der folgenden drei Kategorien geführt:

1. `Sound & Clöb` – DJ-Auftritte, Partys, Raves und musikbezogene Bar-/Clubveranstaltungen (inkl. Supermarket).
2. `Kultur & Workshops` – Literatur, Kunst, Lesungen, Vorträge, Diskussionen, Community-Treffen, Workshops, Theater, Kulturformate (auch in Bars oder Clubs).
3. `Konzerte` – ausschliesslich als Konzert ausgewiesene Live-Musikveranstaltungen; einzelne DJ-Sets sind keine Konzerte.

Die verbindlichen Regeln stehen in `backend/categories.py`. Die jeweiligen Adapter rufen sie mit Titel, Veranstaltungsort, URL, Startzeit und – wenn verfügbar – einem Ausschnitt der spezifischen Event-Detailseite auf. Insbesondere ist **Moods keine pauschale Konzertzuordnung**: Konzert-Evidenz muss beim einzelnen Event vorliegen. Bei mangelnder Evidenz wird nicht spekulativ `Konzerte` vergeben.

Das Frontend `site/index.html` stellt den Filter in fixer Reihenfolge bereit und übernimmt die Kategorie aus `events.json`. Frühere Kategoriebezeichnungen werden nur für ältere Browser-/JSON-Zwischenstände vorübergehend übersetzt. Kategoriezuordnung beeinflusst die **Erfassung** und den Import der Events nicht.

Die historische `site/data/events.json` wurde migriert. Ein Event, dessen Kategorie mangels Detailinformationen noch unsicher ist, wird beim nächsten vollständigen Crawl erneut mit den Original-Detailinformationen klassifiziert. Die Kategorieabdeckung ist keine manuell verifizierte Klassifikationsgenauigkeit.
