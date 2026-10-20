# Live-Validierung Zürich, 20.10.2026

Konsolidierter Stand: 2026-10-20T22:29:50+02:00. Ausgangscommit `de37ce9`.

| Kennzahl | Vorher | Nachher |
|---|---:|---:|
| Katalog, kanonische Events | 744 | 3195 |
| Zürich und Umgebung | 397 | 2823 |
| Bern und Umland | 347 | 372 |
| Quellengetrennte Rohdatensätze | 744 | 3271 |
| Zusammengeführte Mehrfacherfassungen | keine quellenübergreifende Engine | 76 |
| Prüf-Kandidaten, getrennt belassen | nicht ermittelt | 189 |
| Verifizierte bzw. quellenseitig georeferenzierte Events | nicht zentral ausgewertet | 1186 |
| Events mit explizit unbekannter Uhrzeit | technisch ausgeschlossen | 858 |

Nettozuwachs im Gesamtkatalog: **2451**. Für Zürich/Umland: **2426**. Die Werte vergleichen vollständige Snapshots; sie sind keine manuell verifizierte Erfassungsquote.

## Beitrag der neuen Quellen

| Quelle | Entdeckte Links/Einträge | Importierte Termininstanzen | Kanonischer Hauptquellenbeitrag | Zusammengeführt | Status |
|---|---:|---:|---:|---:|---|
| stadt_zuerich | 1027 | 799 | 796 | 3 | success |
| kulturzueri | 313 | 476 | 435 | 41 | partial |
| petzi | 259 | 84 | 84 | 0 | success |
| ubwg | 180 | 134 | 114 | 20 | success |
| rote_fabrik | 53 | 53 | 53 | 0 | success |
| onthur | 135 | 117 | 114 | 3 | success |
| gemeinde_thalwil | 585 | 196 | 196 | 0 | success |
| gemeinde_regensdorf | 45 | 23 | 23 | 0 | success |
| gemeinde_uster | 368 | 266 | 266 | 0 | success |
| gemeinde_kloten | 438 | 349 | 349 | 0 | success |

Kulturzüri: 313 Detail-URLs auf sechs Listenseiten; eine Detailseite kann mehrere Termine liefern. Importierte Instanzen sind daher nicht mit Linkanzahlen gleichzusetzen. Stadt Zürich: API meldete 1’051 Zeilen, davon 1’027 eindeutige URL-/Beginnkombinationen. 799 konnten mit explizit verifizierter zugelassener Lokalität übernommen werden. Ausschlüsse sind keine Aussage darüber, dass die übrigen Veranstaltungen nicht existieren.

## Kontrollstichprobe

**10/10** bewusst ausgewählte Termininstanzen stimmen mit den gespeicherten öffentlichen Originalbeispielen überein. Geprüft wurden Datum, Beginn bzw. unbekannte Uhrzeit; bei Rote Fabrik/PETZI zusätzlich die getrennte Türöffnung in den Regressionstests. Die Stichprobe ist nicht repräsentativ und misst keine Gesamt-Erfassungsquote.

| Quelle | Kontrollfall | Datum | Beginn | Ergebnis |
|---|---|---|---|---|
| rote_fabrik | Kümmernis | 2026-10-20 | 20:00 | gefunden |
| petzi | dominic oppliger buchvernissage | 2026-10-21 | 20:00 | gefunden |
| kulturzueri | Homers | 2026-10-21 | 12:30 | gefunden |
| kulturzueri | Homers | 2026-10-23 | 12:30 | gefunden |
| gemeinde_thalwil | Kafi Treff | 2026-10-20 | Zeit offen | gefunden |
| gemeinde_thalwil | Kafi Treff | 2026-10-27 | Zeit offen | gefunden |
| stadt_zuerich | Zürich liest 2026 | 2026-10-20 | Zeit offen | gefunden |
| ubwg | Kaltstart | 2026-10-21 | 18:00 | gefunden |
| onthur | PubQuiz | 2026-10-20 | 20:00 | gefunden |
| onthur | Makthaverskan | 2026-10-21 | 20:00 | gefunden |

## Tests und Laufzeit

- 104 Offline-Tests inklusive realer HTML-/JSON-Fixtures, Dubletten-Gegenbeispielen, Quellausfall-Erhalt, Adressvalidierung und Wiederholungs-Terminen.
- JavaScript-Syntax und Laufzeitprüfung für Events mit/ohne Uhrzeit und Quellenfilter erfolgreich.
- Vollständiger realer Erstlauf: ungefähr 24 Minuten mit vier gleichzeitigen Quellen; anschliessend gezielter Winterthur-Import und Adress-Enrichment. Die verbesserte PETZI-Ortsfilterung reduziert künftig irrelevante Abrufe.
- Adressdienst: insgesamt 69 eindeutige Gebäudeadressen im Cache. Im abschliessenden Lauf 40 neue Abfragen, 1110 Rohdatensätze angereichert, keine API-Fehler.

## Verbleibende Grenzen

- Kulturzüri ist ein Teilimport: sechs Listenseiten, 476 importierte Termininstanzen, 114 protokollierte Hinweise/ungeeignete oder unlesbare Detailseiten. Eine lückenlose 90-Tage-Erfassung wird nicht behauptet.
- Die erste PETZI-Vollerfassung nutzte noch Volltextsuche; der produktive Adapter verwendet den verifizierten Ortsfilter. Die aktuelle Stichprobe bestätigt den erhaltenen lokalen Bestand.
- 189 Matching-Kandidaten bleiben absichtlich getrennt. Einige sichtbare Dubletten sind damit möglich; keine automatischen Fuzzy-Zusammenlegungen.
- Zahlreiche Gemeindeeinträge enthalten in der Liste keinen Beginn und bleiben mit «Zeit offen». Detail-Enrichment und fortgeschrittene Behandlung bereits laufender mehrtägiger Formate bleiben nächste Arbeitspakete.
- Fehlende Adressen/Koordinaten begrenzen die exakte Kilometerfilterung. Keine Stadtzentren werden als Eventstandorte ausgegeben.
- Stereo liefert weiterhin keine Termine. Köniz schlug in diesem Lauf fehl; 123 frühere Rohdatensätze bleiben erhalten. Bern/Umland wurde durch Ostermundigen erweitert und durch die neue Engine ebenfalls konsolidiert.
- Quellen-/Parserausbeute, Bildabdeckung, Feldabdeckung und Stichprobe sind getrennte Messgrössen. Erfolgreiches HTTP und ein grüner Gesamtlauf belegen keine vollständige Quellenabdeckung.

Siehe auch [Quelleninventar](zurich-source-inventory.md).
