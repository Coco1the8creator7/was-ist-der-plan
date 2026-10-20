# Crawl Zürich: Audit und Quelleninventar

Stand: 20.10.2026. Ausgangscommit `de37ce9`.

## Ausgangslage

744 veröffentlichte Datensätze, davon 397 aus elf Zürcher Adaptern:
Dynamo 154, Kaufleuten 89, EXIL 60, Plaza 32, Moods 32, Hive 14,
Gonzo 8, Supermarket 5, Kauz 2, Friedas Büxe 1, Stereo 0.
Die übrigen 347 Einträge stammen aus Bern/Umland.

Zürcher letzter Quellenstatus: acht erfolgreich, EXIL und Gonzo teilweise,
Stereo fehlgeschlagen. Helsinki und Rote Fabrik waren inaktiv. Die Zahlen
sind **kein Vollständigkeitsnachweis**: der Snapshot enthält auch aufbewahrte
Einträge aus früheren Läufen. Keine Zürcher Gemeinde, keine flächendeckende
Kulturagenda und keine quellenübergreifende kanonische Eventidentifikation.
Bisheriger Schlüssel Quelle/URL/Datum konnte mehrere Aufführungen übersehen.

## Verifizierte erste Welle

Live-HTTP-Prüfungen, öffentliches Frontend-JavaScript und Beispielantworten
wurden am 20.10.2026 untersucht. Mengen sind beobachtete Bruttomengen,
keine Versprechen zusätzlicher einzigartiger Events.

| Quelle und URL | Art / Gebiet / Formate | Beobachtetes Potenzial | Methode / Mehrfachtermine | Aufwand / Dublettenrisiko | Priorität |
|---|---|---|---|---|---|
| [Stadt Zürich](https://www.stadt-zuerich.ch/agenda) | Offizielle Stadtagenda; Kultur, Quartiere, Sport, Umwelt, Kurse | API meldet 1'051 Treffer für 90 Tage, inklusive Wiederholungen | `/stzh/search`, `compResource` aus öffentlichem Markup, Offset-Pagination; `calentry` behalten | mittel / mittel | P1, implementiert |
| [Kulturzüri](https://www.kulturzueri.ch/veranstaltungen/) | Kultur Zürich und Region; kleinere Institutionen, Literatur, Theater | 60 Teaser je Seite, Detailseiten enthalten mehrere Aufführungen | Öffentlicher HTML-POST wie im Frontend, Pager-Link; JSON-LD `eventSchedule`, alle expliziten Termine | mittel / hoch | P1, implementiert; Pilot 6 Seiten |
| [Rote Fabrik](https://rotefabrik.ch/programm) | Offizieller Kulturort; Theater, Konzerte, Workshops | 53 zukünftige Termininstanzen in der Probe | Verlinkte `kalender.rotefabrik.ch/api/events`; UTC-Tagesmarker lokal umrechnen, Türen separat | mittel / mittel | P1, implementiert |
| [UBWG](https://ubwg.ch/events/) | Elektronische Musik, Zürich/Umland und andere Regionen | API meldet 180 kommende Events vor Ortsfilterung | Öffentliches WordPress Tribe REST API; `next_rest_url`, Event- und Venue-Metadaten | gering / sehr hoch | P1, implementiert |
| [PETZI](https://www.petzi.ch/de/) | Club-/Konzertverband, auch kleine Kulturorte und Winterthur | Zürcher Suche bereits über eine Seite; genaue Nettomenge im Crawlbericht | `/de/search/` mit Ortsparameter `location` (nicht Volltextsuche), `page`; offizielle HTML-Details, Beginn und Türöffnung getrennt | mittel / hoch | P1, implementiert |
| [Thalwil](https://www.thalwil.ch/anlaesseaktuelles) | Offizielle Gemeinde; Vereine, Begegnungen, Sport, Märkte | 196 künftige Termine aus eingebetteten Daten in Probe | Wiederverwendbarer ICMS-Adapter `data-entities`; Uhrzeit unbekannt statt Mitternacht | gering / gering | P1, implementiert |
| [Regensdorf](https://www.regensdorf.ch/anlaesseaktuelles) | Offizielle Gemeinde, Furttal | Kein Mengenversprechen vor erfolgreichem Crawl | ICMS-Adapter, Schemaabweichung meldet Fehler | gering / gering | P1, Pilot |
| [Uster](https://www.uster.ch/anlaesseaktuelles) | Offizielle Gemeinde, Oberland | Kein Mengenversprechen vor erfolgreichem Crawl | ICMS-Adapter, Schemaabweichung meldet Fehler | gering / gering | P1, Pilot |
| [Kloten](https://www.kloten.ch/veranstaltungen) | Offizielle Gemeinde, Glattal | Kein Mengenversprechen vor erfolgreichem Crawl | ICMS-Adapter, Schemaabweichung meldet Fehler | gering / gering | P1, Pilot |

Die API-URLs wurden aus den öffentlich verwendeten Webseiten abgeleitet. Das
ist kein dokumentierter API-Vertrag; Änderungen werden über Tests und
Qualitätsberichte sichtbar. Robots werden vor dem Crawl geprüft, Abrufe sind
begrenzt und verzögert. Es werden keine Zugangssperren umgangen.

## Geprüfte Discovery-Quellen und nächste Welle

| Quelle / URL | Nutzen und Gebiet | Potenzial (qualitativ) | Technischer Stand | Aufwand / Dublettenrisiko | Priorität |
|---|---|---|---|---|---|
| [OnThur](https://www.onthur.ch/) | Gemeinsamer Winterthurer Clubkalender: Albani, Gaswerk, Kraftfeld, Portier, Salzhaus | 117 explizite Termine im 90-Tage-Fenster | ISO-Datum pro HTML-Tagesgruppe, Beginn und Format pro Karte; einmaliger Seitenabruf | gering / hoch mit PETZI | P1, implementiert |
| [Kraftfeld](https://www.kraftfeld.ch/de/programm.html) | Konzerte, Literatur, Barformate, Winterthur | mittel | Aktuelles offizielles Programm gefunden; Parser noch offen | mittel / hoch mit PETZI/OnThur | P1 |
| [Salzhaus](https://www.salzhaus.ch/de/programm) | Konzerte und Partys, Winterthur | mittel | Aktuelles offizielles Programm mit Live/Party-Labels gefunden | mittel / hoch | P1 |
| [zuri.net](https://zuri.net/de/zurich/agenda) | Breite Agenda; Discovery | hoch brutto, netto unklar | Seite nennt Eventfrog als Lieferant; keinen zweiten unkontrollierten Vollimport | mittel / sehr hoch | P2 |
| [Zürich Tourismus](https://www.zuerich.com/) | Regionale Discovery | begrenzter eigenständiger Zuwachs | Kulturzüri bestätigt Übernahme ihrer Agenda auf zuerich.com | mittel / sehr hoch | P2 |
| [El Lokal](https://www.ellokal.ch/) | Kleine internationale Live-Konzerte | mittel | Aktive offizielle Wix-Seite; Programm separat, noch kein validierter Parser | mittel / mittel | P1 |
| [Helsinki](https://www.helsinkiklub.ch/) | Kleine Bühne, Literatur, Konzerte, DJs | mittel | Öffentliches Programm vorhanden, teilweise über PETZI erfasst; direkte Nutzungshinweise vor zusätzlicher Integration prüfen | mittel / hoch mit PETZI | P2 |

Belege für Quellenteilung: [Kulturzüri über uns](https://kulturzueri.ch/zuerich/uber-uns/),
[zuri.net Agenda](https://zuri.net/de/zurich/agenda/22-08-2026).

## Recherchekandidaten, noch nicht technisch oder auf Aktualität verifiziert

Keine der folgenden Zeilen ist als funktionierender Adapter zu verstehen.
Potenzial ist eine Priorisierungshypothese, keine gemessene Menge.

| Kandidat / Start-URL | Gebiet / erwartete Typen | Zusätzliches Potenzial | Zu prüfende Methode | Aufwand / Dublettenrisiko | Priorität |
|---|---|---|---|---|---|
| [Eventfrog](https://eventfrog.ch/) | Zürich und 50 km; Vereine, Kleinanlässe, Dorffeste | hoch | Zulässige Partner/API-Nutzung, strukturierte Detaildaten, Geo-Pagination | hoch / sehr hoch | P1 Recherche |
| [Ticketino](https://www.ticketino.com/) | Regional; Kultur, Festivals | mittel | Öffentliche Schnittstelle/JSON-LD prüfen | mittel / hoch | P2 |
| [Resident Advisor](https://ra.co/events/ch/zurich) | Zürcher Clubs, Underground | mittel | Nutzungsbedingungen, erlaubter Datenzugang | hoch / sehr hoch | P2 |
| [Ron Orp](https://www.ronorp.net/) | Kleine Kultur- und Community-Anlässe | mittel | Offizielle Eventlinks als Discovery | mittel / hoch | P2 |
| [Zentralwäscherei](https://zentralwaescherei.space/) | Alternative Kultur, Zürich | hoch | Offizielles Programm; PETZI-Lücken prüfen | mittel / hoch | P1 |
| [Amboss Rampe](https://ambossrampe.ch/) | Bar-/Club-/Liveformate, Zürich | mittel | Offizielles HTML/JSON-LD/ICS prüfen | mittel / mittel | P1 |
| [Sender](https://sender.club/) | Kleine elektronische Musikformate | mittel | Offizielles Programm prüfen | mittel / mittel | P1 |
| [Ebrietas](https://ebrietas.ch/) | Kleine Konzerte/Bar | mittel | Offizielles Programm prüfen | mittel / mittel | P1 |
| [Longstreet](https://longstreetbar.ch/) | Bar, Musik, Party | mittel | Domain und Programm aktualitätsprüfen | mittel / mittel | P2 |
| [Klaus](https://klauszh.ch/) | Clubmusik | mittel | Domain/Programm überprüfen | mittel / hoch | P2 |
| [Mascotte](https://www.mascotte.ch/) | Konzerte/Party | mittel | Detaildaten und Pagination prüfen | mittel / hoch | P2 |
| [Photobastei](https://www.photobastei.ch/) | Kunst, Workshops | mittel | Öffentliche Agenda prüfen | mittel / mittel | P1 |
| [Kulturmarkt](https://www.kulturmarkt.ch/) | Theater, Konzerte, Kultur | mittel | Programme/Termininstanzen prüfen | mittel / hoch | P1 |
| [Papiersaal](https://www.papiersaal.ch/) | Konzerte/Kultur | mittel | Strukturierte Termine prüfen | mittel / hoch | P2 |
| [Literaturhaus](https://www.literaturhaus.ch/) | Literatur, Diskussionen | mittel | Kulturzüri-Abdeckung zuerst messen | mittel / hoch | P1 |
| [Schauspielhaus](https://www.schauspielhaus.ch/) | Theater, Mehrfachaufführungen | hoch brutto | Kulturzüri gegen offiziellen Spielplan prüfen | hoch / sehr hoch | P2 |
| [Opernhaus](https://www.opernhaus.ch/) | Oper, Ballett, Führungen | hoch brutto | Einzelaufführungen und Offerten prüfen | hoch / hoch | P2 |
| [Theater Neumarkt](https://www.theaterneumarkt.ch/) | Theater und Diskurs | mittel | Domain/Spielplan prüfen | mittel / hoch | P2 |
| [Theater am Hechtplatz](https://www.theaterhechtplatz.ch/) | Kleinkunst | mittel | Spielplan, Wiederholungen | mittel / hoch | P2 |
| [Tonhalle](https://www.tonhalle-orchester.ch/) | Klassische Konzerte | mittel | Kalender/Termine prüfen | mittel / hoch | P2 |
| [Kunsthaus](https://www.kunsthaus.ch/) | Führungen, Workshops | mittel | Einzelanlässe vs Dauerausstellungen trennen | mittel / hoch | P2 |
| [Museum Rietberg](https://rietberg.ch/) | Führungen, Kultur, Workshops | mittel | Programmstruktur prüfen | mittel / hoch | P2 |
| [ETH](https://ethz.ch/), [UZH](https://www.uzh.ch/), [ZHdK](https://www.zhdk.ch/) | Öffentliche Wissenschaft, Ausstellungen, Talks | hoch | Öffentliche Termine von internen Lehrveranstaltungen trennen | hoch / mittel | P2 |
| [Baden](https://www.baden.ch/), [Wettingen](https://www.wettingen.ch/) | Gemeinde-/Vereinsanlässe | mittel | Kalenderformat und ICMS-Kompatibilität prüfen | mittel / mittel | P1 nächste Gemeinden |
| [Dübendorf](https://www.duebendorf.ch/), [Wallisellen](https://www.wallisellen.ch/) | Glattal, Vereine, Märkte | mittel | Gemeindekalender prüfen | gering–mittel / gering | P1 |
| [Bülach](https://www.buelach.ch/), [Dietikon](https://www.dietikon.ch/) | Regionale Feste | mittel | Gemeindekalender prüfen | gering–mittel / gering | P1 |
| [Horgen](https://www.horgen.ch/), [Wädenswil](https://www.waedenswil.ch/), [Meilen](https://www.meilen.ch/) | Seeufer; Märkte und Dorffeste | mittel | Gemeindekalender prüfen | gering–mittel / gering | P1 |
| [Rapperswil-Jona](https://www.rapperswil-jona.ch/), [Affoltern a.A.](https://www.stadtaffoltern.ch/) | Südost/Südwest | mittel | Gemeindeagenda prüfen | mittel / mittel | P2 |
| [Züritipp](https://www.tagesanzeiger.ch/), [NZZ](https://www.nzz.ch/) | Redaktionelle Entdeckung | unbekannt | Nur öffentliche Artikel; Original-Veranstalter validieren, keine Paywall umgehen | hoch / hoch | P3 |

## Bewusste Grenzen dieser Implementierungswelle

- Kein Anspruch auf lückenlose 90-Tage-Erfassung bei begrenzten Kulturzüri-
  und PETZI-Seiten. Erreichte Limits erscheinen ausdrücklich als Teilstatus.
- Geografie nationaler Feeds wird anhand explizit veröffentlichter Lokalitäten
  begrenzt. Dies ersetzt keinen exakten 50-km-Filter. Fehlende Koordinaten
  bleiben unbekannt; der bestehende Frontend-Regionsfallback bleibt sichtbar.
- Gebäudegenaues Geocoding über die [offizielle Adresssuche](https://docs.geo.admin.ch/access-data/search.html) ist angebunden: nur eindeutige Treffer für Strasse, Hausnummer und Ort; Adresscache in `backend/data/venues.json`, maximal 40 neue Adressen je Lauf, 30 Tage Wiederverwendung. Kein Treffer aus Ortsmittelpunkten. Ein vollständiges Venue-Stammdatenmodell mit Raum-/Floor-Aliasverwaltung bleibt ein nächstes Arbeitspaket.
- ICMS-Listen geben verifizierte Tage und Orte, aber keine verifizierten
  Beginnzeiten. Diese Events erscheinen mit «Zeit offen»; Detail-Enrichment
  ist bewusst noch offen. Lang laufende Kurse werden nicht in erfundene
  wöchentliche Termine zerlegt.
- Fuzzy-Treffer werden geprüft/protokolliert, nicht automatisch verschmolzen.
  Bei unterschiedlichen Titeln kann daher noch eine Dublette sichtbar bleiben.
- Zusätzliche Floors/Spielstätten werden konservativ getrennt; Rote Fabrik
  hat ausdrückliche Hallen-IDs, die eine pauschale Gebäudezusammenführung verhindern.
- Ein einzelner Actions-Job mit vier gleichzeitigen Quellen bleibt vorerst
  angemessen. Erst tatsächliche Laufzeit beobachten; regionale Jobaufteilung
  erfordert getrennte Rohdatendateien und eine sequenzielle Konsolidierung,
  damit Zürich/Bern sich nicht gegenseitig überschreiben.
