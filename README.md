# was ist der plan? – Zürcher Eventkalender

Automatischer Eventkatalog, 90-Tage-Suchfenster, alle 6 Stunden über GitHub Actions.

## Stand
- **EXIL**: echter Import am 17.10.2026 erfolgreich (58 Events, keine Parserfehler); manuelle Stichprobenabdeckung noch nicht ermittelt.
- **Hive, Kaufleuten, Plaza, Kauz, Moods, Dynamo, Supermarket**: erste konservative Parser implementiert, echter Live-Import pro Quelle noch **nicht verifiziert**.
- **Frieda's Büxe, Helsinki, Rote Fabrik**: erfasst als offene Quelladapter; kein behaupteter erfolgreicher Import.
- **Zukunft**: ehemaliger Club (Closing 2025), nicht als aktive Quelle.
- **Kaschemme**: liegt in Basel, deshalb nicht im Zürcher 50-km-Standardgebiet.

## Import starten
Unter [Actions](https://github.com/Coco1the8creator7/was-ist-der-plan/actions) → **Eventdaten aktualisieren** → **Run workflow**.
Der Workflow führt zuerst Offline-Tests aus, danach die Quellenabrufe und speichert `site/data/events.json` und `site/data/quality.json`.
**Wichtig:** Bei nicht erfolgreich importierten Prototyp-Quellen wird der Workflow zur besseren Erkennbarkeit rot, obwohl die gültigen Datensätze aus anderen Quellen erhalten bleiben und die Qualitätsdatei aktualisiert wird.

## Dateien
- `backend/main.py`: Quellenorchestrierung, Status, Zusammenführung und JSON-Publikation
- `backend/legacy_exil.py`: bestätigter EXIL-Adapter
- `backend/sources/venues.py`: neue getrennt konfigurierte Pilot-Adapter für Veranstaltungsorte
- `tests/test_venues.py`: Offline-Parsertests
- `site/data/events.json`: öffentlicher Eventkatalog
- `site/data/quality.json`: Importzahlen, Fehler und manuelle Erfassungsquote pro Quelle

## Qualitätsregeln
Nur Events mit prüfbarem Titel, vollständigem Datum und konkreter Startzeit werden übernommen. Ein fehlgeschlagener Abruf zählt nicht als Erfolg. Vorherige Events bleiben bei Quellausfall erhalten; ihre letzte Sichtung ist in `last_seen` erkennbar. Die aktuelle Dublettenprüfung entfernt wiederholte identische Einzel-Events, aber noch keine belastbaren Dubletten zwischen verschiedenen Ticketshops und Clubhomepages. `sample_coverage` bleibt leer, bis eine echte menschliche Kontrollstichprobe vorliegt.

## Lokale Ausführung
```bash
python3 -m pip install -r requirements.txt
python3 -m unittest discover -s tests -v
python3 -m backend.main
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

